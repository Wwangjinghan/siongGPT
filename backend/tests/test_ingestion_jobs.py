import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy.dialects.postgresql import dialect

from app.core.domain_types import (
    AccessLevel,
    IngestionErrorCode,
    IngestionJobStatus,
    ProcessingStatus,
    PublicationStatus,
    ScopeType,
    SourceStatus,
    SourceType,
)
from app.core.principal import Principal
from app.ingestion.service import IngestionJobService, LeaseLostError
from app.models.ingestion_job import IngestionJob
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.permissions.service import PermissionService
from app.sources.errors import InvalidTransitionError, SourceNotFoundError


class Collections:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeJobSession:
    def __init__(self, *, scalars=(), scalar_collections=(), get_map=None):
        self.scalar_values = list(scalars)
        self.collections = list(scalar_collections)
        self.get_map = get_map or {}
        self.added = []
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    def scalars(self, statement):
        self.statements.append(statement)
        return Collections(self.collections.pop(0) if self.collections else [])

    def get(self, model, identifier):
        value = self.get_map.get(model)
        if isinstance(value, dict):
            return value.get(identifier)
        return value

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, _value):
        pass

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(rowcount=1)


class JobFixture(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.department_id = uuid4()
        self.source = Source(
            id=uuid4(), title="Policy", source_type=SourceType.DOCUMENT.value,
            scope_type=ScopeType.DEPARTMENT.value, department_id=self.department_id,
            access_level=AccessLevel.INTERNAL.value, status=SourceStatus.ACTIVE.value,
            created_by=self.user_id,
        )
        self.version = SourceVersion(
            id=uuid4(), source_id=self.source.id, version_no=1,
            original_filename="policy.txt", mime_type="text/plain", file_size=10,
            file_hash="a" * 64, storage_key="sha256/aa/aa/" + "a" * 64,
            processing_status=ProcessingStatus.PENDING.value,
            publication_status=PublicationStatus.DRAFT.value, is_current=False,
            uploaded_by=self.user_id,
        )
        self.principal = Principal(
            self.user_id, self.department_id, frozenset({"FINANCE_ADMIN"}), True, True
        )

    def job(self, status=IngestionJobStatus.QUEUED, attempts=0, maximum=3):
        now = datetime.now(timezone.utc)
        return IngestionJob(
            id=uuid4(), source_version_id=self.version.id,
            job_type="DOCUMENT_INGESTION", status=status.value,
            attempt_count=attempts, max_attempts=maximum, available_at=now,
            created_by=self.user_id, created_at=now, updated_at=now,
        )

    def service(self, session):
        return IngestionJobService(
            session, PermissionService(), max_attempts=3,
            lease_seconds=60, retry_base_seconds=10,
        )


class IngestionJobTests(JobFixture):
    def test_enqueue_creates_queued_job_and_reuses_active_job(self):
        session = FakeJobSession(scalars=[self.source.id, self.source, self.version, None])
        job, created = self.service(session).enqueue(self.principal, self.version.id)
        self.assertTrue(created)
        self.assertEqual(job.status, IngestionJobStatus.QUEUED.value)
        self.assertEqual(job.attempt_count, 0)
        active = self.job()
        session = FakeJobSession(scalars=[self.source.id, self.source, self.version, active])
        returned, created = self.service(session).enqueue(self.principal, self.version.id)
        self.assertIs(returned, active)
        self.assertFalse(created)

    def test_claim_uses_skip_locked_sets_lease_and_attempt(self):
        job = self.job()
        session = FakeJobSession(scalars=[job], scalar_collections=[[], []])
        claimed = self.service(session).claim_next("SYSTEM_WORKER:test")
        self.assertIs(claimed, job)
        self.assertEqual(job.status, IngestionJobStatus.RUNNING.value)
        self.assertEqual(job.attempt_count, 1)
        self.assertEqual(job.lease_owner, "SYSTEM_WORKER:test")
        self.assertIsNotNone(job.lease_expires_at)
        self.assertIn(
            "SKIP LOCKED",
            str(session.statements[-1].compile(dialect=dialect())),
        )

    def test_expired_lease_is_requeued_and_reclaimed(self):
        job = self.job(IngestionJobStatus.RUNNING, attempts=1)
        job.lease_owner = "old-worker"
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session = FakeJobSession(scalars=[job], scalar_collections=[[job], []])
        claimed = self.service(session).claim_next("new-worker")
        self.assertEqual(claimed.lease_owner, "new-worker")
        self.assertEqual(claimed.attempt_count, 2)

    def test_expired_final_lease_dead_letters_job_and_fails_version(self):
        job = self.job(IngestionJobStatus.RUNNING, attempts=3, maximum=3)
        job.lease_owner = "lost-worker"
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session = FakeJobSession(
            scalars=[None],
            scalar_collections=[[job], []],
            get_map={SourceVersion: {self.version.id: self.version}},
        )
        self.assertIsNone(self.service(session).claim_next("new-worker"))
        self.assertEqual(job.status, IngestionJobStatus.DEAD_LETTER.value)
        self.assertEqual(job.error_code, IngestionErrorCode.LEASE_LOST.value)
        self.assertEqual(self.version.processing_status, ProcessingStatus.FAILED.value)
        self.assertEqual(
            self.version.processing_error_code, IngestionErrorCode.LEASE_LOST.value
        )

    def test_stale_worker_cannot_lock_or_finish_job(self):
        session = FakeJobSession(scalars=[None])
        with self.assertRaises(LeaseLostError):
            self.service(session).lock_owned_running_job(uuid4(), "old-worker")

    def test_failure_retries_then_dead_letters_at_max_attempts(self):
        for attempts, expected in ((1, IngestionJobStatus.FAILED), (3, IngestionJobStatus.DEAD_LETTER)):
            job = self.job(IngestionJobStatus.RUNNING, attempts=attempts, maximum=3)
            job.lease_owner = "worker"
            job.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
            version = self.version
            session = FakeJobSession(
                scalars=[job], get_map={SourceVersion: {version.id: version}}
            )
            self.assertTrue(
                self.service(session).fail_owned_job(
                    job.id, "worker", IngestionErrorCode.PARSER_FAILED, "Parsing failed"
                )
            )
            self.assertEqual(job.status, expected.value)
            self.assertEqual(version.processing_status, ProcessingStatus.FAILED.value)

    def test_cancel_only_queued_and_succeeded_cannot_retry(self):
        queued = self.job()
        session = FakeJobSession(
            scalars=[queued], get_map={SourceVersion: self.version, Source: self.source}
        )
        cancelled = self.service(session).cancel(self.principal, queued.id)
        self.assertEqual(cancelled.status, IngestionJobStatus.CANCELLED.value)

        running = self.job(IngestionJobStatus.RUNNING)
        session = FakeJobSession(
            scalars=[running], get_map={SourceVersion: self.version, Source: self.source}
        )
        with self.assertRaises(InvalidTransitionError):
            self.service(session).cancel(self.principal, running.id)

        succeeded = self.job(IngestionJobStatus.SUCCEEDED, attempts=1)
        session = FakeJobSession(
            scalars=[succeeded], get_map={SourceVersion: self.version, Source: self.source}
        )
        with self.assertRaises(InvalidTransitionError):
            self.service(session).retry(self.principal, succeeded.id)

    def test_failed_retry_requeues_without_erasing_failure_history(self):
        failed = self.job(IngestionJobStatus.FAILED, attempts=1)
        failed.error_code = IngestionErrorCode.PARSER_FAILED.value
        failed.error_message = "Parsing failed"
        session = FakeJobSession(
            scalars=[failed], get_map={SourceVersion: self.version, Source: self.source}
        )
        retried, created = self.service(session).retry(self.principal, failed.id)
        self.assertFalse(created)
        self.assertEqual(retried.status, IngestionJobStatus.QUEUED.value)
        self.assertEqual(retried.error_code, IngestionErrorCode.PARSER_FAILED.value)

    def test_dead_letter_manual_retry_creates_new_job(self):
        dead = self.job(IngestionJobStatus.DEAD_LETTER, attempts=3)
        session = FakeJobSession(
            scalars=[dead, None], get_map={SourceVersion: self.version, Source: self.source}
        )
        replacement, created = self.service(session).retry(self.principal, dead.id)
        self.assertTrue(created)
        self.assertNotEqual(replacement.id, dead.id)
        self.assertEqual(dead.status, IngestionJobStatus.DEAD_LETTER.value)

    def test_personal_owner_can_enqueue_but_unknown_and_project_are_denied(self):
        personal = Source(
            id=uuid4(), title="Draft", source_type=SourceType.DOCUMENT.value,
            scope_type=ScopeType.PERSONAL_DRAFT.value, owner_user_id=self.user_id,
            access_level=AccessLevel.INTERNAL.value, status=SourceStatus.ACTIVE.value,
            created_by=self.user_id,
        )
        self.version.source_id = personal.id
        employee = Principal(
            self.user_id, self.department_id, frozenset({"EMPLOYEE"}), True, True
        )
        session = FakeJobSession(scalars=[personal.id, personal, self.version, None])
        job, _ = self.service(session).enqueue(employee, self.version.id)
        self.assertEqual(job.status, IngestionJobStatus.QUEUED.value)

        unknown = Principal(
            self.user_id, self.department_id, frozenset({"UNKNOWN"}), True, True
        )
        session = FakeJobSession(scalars=[personal.id, personal, self.version])
        with self.assertRaises(SourceNotFoundError):
            self.service(session).enqueue(unknown, self.version.id)

        project = Source(
            id=uuid4(), title="Project", source_type=SourceType.DOCUMENT.value,
            scope_type=ScopeType.PROJECT.value, project_id=uuid4(),
            access_level=AccessLevel.INTERNAL.value, status=SourceStatus.ACTIVE.value,
            created_by=self.user_id,
        )
        self.version.source_id = project.id
        admin = Principal(
            self.user_id, self.department_id, frozenset({"SYSTEM_ADMIN"}), True, True
        )
        session = FakeJobSession(scalars=[project.id, project, self.version])
        with self.assertRaises(SourceNotFoundError):
            self.service(session).enqueue(admin, self.version.id)

    def test_ready_published_version_can_enqueue_embedding_backfill_idempotently(self):
        self.version.processing_status = ProcessingStatus.READY.value
        self.version.publication_status = PublicationStatus.PUBLISHED.value
        self.version.is_current = True
        session = FakeJobSession(scalars=[self.source.id, self.source, self.version, None])
        job, created = self.service(session).enqueue_embedding(self.principal, self.version.id)
        self.assertTrue(created)
        self.assertEqual(job.job_type, "DOCUMENT_EMBEDDING")
        active = self.job()
        active.job_type = "DOCUMENT_EMBEDDING"
        session = FakeJobSession(scalars=[self.source.id, self.source, self.version, active])
        returned, created = self.service(session).enqueue_embedding(self.principal, self.version.id)
        self.assertIs(returned, active)
        self.assertFalse(created)

    def test_embedding_backfill_requires_manage_or_approve_and_ready(self):
        employee = Principal(
            self.user_id, self.department_id, frozenset({"EMPLOYEE"}), True, True
        )
        self.version.processing_status = ProcessingStatus.READY.value
        session = FakeJobSession(scalars=[self.source.id, self.source, self.version])
        with self.assertRaises(SourceNotFoundError):
            self.service(session).enqueue_embedding(employee, self.version.id)
        self.version.processing_status = ProcessingStatus.PENDING.value
        session = FakeJobSession(scalars=[self.source.id, self.source, self.version])
        with self.assertRaises(InvalidTransitionError):
            self.service(session).enqueue_embedding(self.principal, self.version.id)

        failed = self.job(IngestionJobStatus.FAILED, attempts=1)
        failed.job_type = "DOCUMENT_EMBEDDING"
        self.version.processing_status = ProcessingStatus.READY.value
        session = FakeJobSession(
            scalars=[failed], get_map={SourceVersion: self.version, Source: self.source}
        )
        with self.assertRaises(SourceNotFoundError):
            self.service(session).retry(employee, failed.id)
