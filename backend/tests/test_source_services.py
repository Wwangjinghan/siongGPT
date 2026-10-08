import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.domain_types import (
    AccessLevel,
    ProcessingStatus,
    PublicationStatus,
    ResourceAction,
    ScopeType,
    SourceStatus,
    SourceType,
)
from app.core.principal import Principal
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.permissions.service import PermissionService
from app.sources.errors import (
    DuplicateVersionError,
    InvalidSourceError,
    InvalidTransitionError,
    PermissionDeniedError,
    SourceNotFoundError,
)
from app.sources.services import SourceCreate, SourceService, SourceVersionService
from app.storage.local import LocalStorageAdapter


class ScalarCollection:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeSession:
    def __init__(
        self, scalar_values=(), get_value=None, fail_commit=False, rollback_objects=()
    ):
        self.scalar_values = list(scalar_values)
        self.get_value = get_value
        self.fail_commit = fail_commit
        self.added = []
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.snapshots = {
            item: {
                "publication_status": getattr(item, "publication_status", None),
                "is_current": getattr(item, "is_current", None),
                "effective_from": getattr(item, "effective_from", None),
                "effective_to": getattr(item, "effective_to", None),
                "published_by": getattr(item, "published_by", None),
                "published_at": getattr(item, "published_at", None),
            }
            for item in rollback_objects
        }

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarCollection([])

    def get(self, _model, _identifier):
        if isinstance(self.get_value, dict):
            return self.get_value.get(_model)
        return self.get_value

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("database unavailable")

    def rollback(self):
        self.rollbacks += 1
        for item, values in self.snapshots.items():
            for name, value in values.items():
                setattr(item, name, value)

    def refresh(self, _value):
        pass


class ServiceFixture(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.department_id = uuid4()
        self.permissions = PermissionService()

    def principal(self, role="FINANCE_ADMIN", *, user_id=None, department_id=None):
        return Principal(
            user_id=user_id or self.user_id,
            department_id=department_id or self.department_id,
            roles=frozenset({role}),
            authenticated=True,
            active=True,
        )

    def source(self, *, source_id=None, department_id=None, scope=ScopeType.DEPARTMENT):
        return Source(
            id=source_id or uuid4(),
            title="Policy",
            source_type=SourceType.DOCUMENT.value,
            scope_type=scope.value,
            department_id=department_id or self.department_id,
            owner_user_id=self.user_id if scope is ScopeType.PERSONAL_DRAFT else None,
            access_level=AccessLevel.INTERNAL.value,
            status=SourceStatus.ACTIVE.value,
            created_by=self.user_id,
        )


class SourceServiceTests(ServiceFixture):
    def data(self, scope=ScopeType.DEPARTMENT, **overrides):
        values = dict(
            title="Policy",
            description=None,
            source_type=SourceType.DOCUMENT,
            business_scene=None,
            scope_type=scope,
            department_id=self.department_id if scope is ScopeType.DEPARTMENT else None,
            project_id=None,
            owner_user_id=None,
            access_level=AccessLevel.INTERNAL,
        )
        values.update(overrides)
        return SourceCreate(**values)

    def test_system_admin_creates_company_and_department_admin_own_department(self):
        for principal, data in (
            (self.principal("SYSTEM_ADMIN"), self.data(ScopeType.COMPANY)),
            (self.principal(), self.data()),
        ):
            session = FakeSession()
            created = SourceService(session, self.permissions).create_source(principal, data)
            self.assertEqual(created.created_by, principal.user_id)
            self.assertEqual(session.commits, 1)

    def test_department_user_cannot_create_formal_department_source(self):
        with self.assertRaises(PermissionDeniedError):
            SourceService(FakeSession(), self.permissions).create_source(
                self.principal("EMPLOYEE"), self.data()
            )

    def test_personal_owner_is_server_enforced(self):
        with self.assertRaises(InvalidSourceError):
            SourceService(FakeSession(), self.permissions).create_source(
                self.principal("EMPLOYEE"),
                self.data(ScopeType.PERSONAL_DRAFT, owner_user_id=uuid4()),
            )
        session = FakeSession()
        source = SourceService(session, self.permissions).create_source(
            self.principal("EMPLOYEE"), self.data(ScopeType.PERSONAL_DRAFT)
        )
        self.assertEqual(source.owner_user_id, self.user_id)

    def test_project_creation_is_denied(self):
        with self.assertRaises(PermissionDeniedError):
            SourceService(FakeSession(), self.permissions).create_source(
                self.principal("SYSTEM_ADMIN"),
                self.data(ScopeType.PROJECT, project_id=uuid4()),
            )

    def test_archive_changes_status_without_deleting_versions(self):
        source = self.source()
        version = SourceVersion(id=uuid4(), source_id=source.id, version_no=1)
        source.versions = [version]
        session = FakeSession(get_value=source)
        archived = SourceService(session, self.permissions).archive_source(
            self.principal(), source.id
        )
        self.assertEqual(archived.status, SourceStatus.ARCHIVED.value)
        self.assertEqual(archived.versions, [version])

    def test_list_builds_database_visibility_filter(self):
        session = FakeSession(scalar_values=[0])
        SourceService(session, self.permissions).list_sources(
            self.principal("EMPLOYEE"), page=1, page_size=20
        )
        sql = " ".join(str(statement) for statement in session.statements)
        self.assertIn("sources.owner_user_id", sql)
        self.assertIn("sources.department_id", sql)
        self.assertIn("sources.status", sql)

    def test_unauthorized_get_is_non_disclosing_not_found(self):
        other = self.source(department_id=uuid4())
        session = FakeSession(get_value=other)
        with self.assertRaises(SourceNotFoundError):
            SourceService(session, self.permissions).get_source(
                self.principal("EMPLOYEE"), other.id
            )


class SourceVersionServiceTests(ServiceFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.storage = LocalStorageAdapter(Path(self.temp.name) / "storage")
        self.source_record = self.source()

    def tearDown(self):
        self.temp.cleanup()

    def service(self, session):
        return SourceVersionService(session, self.permissions, self.storage, 1024)

    def upload(self, session, data=b"first version"):
        return self.service(session).upload_version(
            self.principal(),
            self.source_record.id,
            io.BytesIO(data),
            "policy.txt",
            "text/plain",
        )

    def test_first_and_later_uploads_allocate_incrementing_versions(self):
        first_session = FakeSession(scalar_values=[self.source_record, None, None])
        first = self.upload(first_session, b"first")
        second_session = FakeSession(scalar_values=[self.source_record, None, 1])
        second = self.upload(second_session, b"second")
        self.assertEqual((first.version_no, second.version_no), (1, 2))
        self.assertEqual(first.processing_status, ProcessingStatus.PENDING.value)
        self.assertEqual(first.publication_status, PublicationStatus.DRAFT.value)
        self.assertFalse(first.is_current)
        self.assertIn("FOR UPDATE", str(first_session.statements[0]))

    def test_same_source_duplicate_hash_conflicts(self):
        self.storage.save(io.BytesIO(b"same"), max_bytes=100)
        session = FakeSession(scalar_values=[self.source_record, uuid4()])
        with self.assertRaises(DuplicateVersionError):
            self.upload(session, b"same")
        self.assertEqual(session.added, [])

    def test_same_hash_can_back_versions_for_different_sources(self):
        first_session = FakeSession(scalar_values=[self.source_record, None, None])
        first = self.upload(first_session, b"shared")
        other_source = self.source()
        second_session = FakeSession(scalar_values=[other_source, None, None])
        second = self.service(second_session).upload_version(
            self.principal(), other_source.id, io.BytesIO(b"shared"), "other.txt", "text/plain"
        )
        self.assertNotEqual(first.source_id, second.source_id)
        self.assertEqual(first.storage_key, second.storage_key)

    def test_database_failure_cleans_only_new_unreferenced_object(self):
        session = FakeSession(
            scalar_values=[self.source_record, None, None, 0], fail_commit=True
        )
        with self.assertRaises(RuntimeError):
            self.upload(session, b"new object")
        added = session.added[0]
        self.assertFalse(self.storage.exists(added.storage_key))

    def test_unauthorized_upload_is_compensated(self):
        other = self.source(department_id=uuid4())
        session = FakeSession(scalar_values=[other, 0])
        with self.assertRaises(SourceNotFoundError):
            self.service(session).upload_version(
                self.principal("EMPLOYEE"),
                other.id,
                io.BytesIO(b"private"),
                "private.txt",
                "text/plain",
            )
        self.assertEqual(
            [
                path
                for path in (self.storage.root / "sha256").rglob("*")
                if path.is_file()
            ]
            if (self.storage.root / "sha256").exists()
            else [],
            [],
        )

    def test_pending_and_failed_versions_cannot_publish(self):
        for processing in (ProcessingStatus.PENDING, ProcessingStatus.FAILED):
            version = self.version(processing=processing)
            session = FakeSession(
                scalar_values=[version.source_id, self.source_record, version]
            )
            with self.subTest(processing=processing), self.assertRaises(InvalidTransitionError):
                self.service(session).publish_version(self.principal(), version.id)

    def test_ready_draft_publish_supersedes_previous_current(self):
        version = self.version(processing=ProcessingStatus.READY)
        previous = self.version(processing=ProcessingStatus.READY, number=1)
        previous.publication_status = PublicationStatus.PUBLISHED.value
        previous.is_current = True
        session = FakeSession(
            scalar_values=[version.source_id, self.source_record, version, previous]
        )
        published = self.service(session).publish_version(self.principal(), version.id)
        self.assertEqual(published.publication_status, PublicationStatus.PUBLISHED.value)
        self.assertTrue(published.is_current)
        self.assertEqual(previous.publication_status, PublicationStatus.SUPERSEDED.value)
        self.assertFalse(previous.is_current)
        self.assertIsNotNone(previous.effective_to)

    def test_publish_failure_rolls_back_transaction(self):
        version = self.version(processing=ProcessingStatus.READY)
        previous = self.version(processing=ProcessingStatus.READY, number=1)
        previous.publication_status = PublicationStatus.PUBLISHED.value
        previous.is_current = True
        session = FakeSession(
            scalar_values=[version.source_id, self.source_record, version, previous],
            fail_commit=True,
            rollback_objects=[version, previous],
        )
        with self.assertRaises(RuntimeError):
            self.service(session).publish_version(self.principal(), version.id)
        self.assertEqual(session.rollbacks, 1)
        self.assertEqual(previous.publication_status, PublicationStatus.PUBLISHED.value)
        self.assertTrue(previous.is_current)
        self.assertEqual(version.publication_status, PublicationStatus.DRAFT.value)
        self.assertFalse(version.is_current)

    def test_withdraw_does_not_restore_superseded_version(self):
        current = self.version(processing=ProcessingStatus.READY)
        current.publication_status = PublicationStatus.PUBLISHED.value
        current.is_current = True
        old = self.version(processing=ProcessingStatus.READY, number=1)
        old.publication_status = PublicationStatus.SUPERSEDED.value
        old.is_current = False
        session = FakeSession(
            scalar_values=[current.source_id, self.source_record, current]
        )
        withdrawn = self.service(session).withdraw_version(self.principal(), current.id)
        self.assertEqual(withdrawn.publication_status, PublicationStatus.WITHDRAWN.value)
        self.assertFalse(withdrawn.is_current)
        self.assertFalse(old.is_current)

    def test_download_rechecks_source_permission_before_opening_storage(self):
        other = self.source(department_id=uuid4())
        version = self.version()
        version.source_id = other.id
        session = FakeSession(
            get_value={SourceVersion: version, Source: other}
        )
        with self.assertRaises(SourceNotFoundError):
            self.service(session).open_version_file(
                self.principal("EMPLOYEE"), version.id
            )

    def test_processing_worker_transitions_are_controlled(self):
        version = self.version(processing=ProcessingStatus.PENDING)
        service = self.service(FakeSession())
        service.mark_processing(version)
        service.mark_ready(version)
        self.assertEqual(version.processing_status, ProcessingStatus.READY.value)
        with self.assertRaises(InvalidTransitionError):
            service.mark_processing(version)

    def test_no_public_update_method_for_immutable_fields(self):
        self.assertFalse(hasattr(SourceVersionService, "update_version"))

    def version(self, *, processing=ProcessingStatus.PENDING, number=2):
        now = datetime.now(timezone.utc)
        return SourceVersion(
            id=uuid4(),
            source_id=self.source_record.id,
            version_no=number,
            original_filename="policy.txt",
            mime_type="text/plain",
            file_size=4,
            file_hash="a" * 64,
            storage_key="sha256/aa/aa/" + "a" * 64,
            processing_status=processing.value,
            publication_status=PublicationStatus.DRAFT.value,
            is_current=False,
            uploaded_by=self.user_id,
            created_at=now,
            updated_at=now,
        )
