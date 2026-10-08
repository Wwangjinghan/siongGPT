import io
import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.api.v1.sources import get_source_service, get_version_service
from app.core.domain_types import (
    AccessLevel,
    ProcessingStatus,
    PublicationStatus,
    ScopeType,
    SourceStatus,
    SourceType,
)
from app.core.principal import Principal, get_current_principal
from app.main import app
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.sources.errors import DuplicateVersionError, SourceNotFoundError
from app.sources.services import VersionFile


class ASGITestClient:
    def request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)


class FakeSourceApiService:
    def __init__(self, source):
        self.source = source

    def create_source(self, _principal, _data):
        return self.source

    def list_sources(self, _principal, **_filters):
        return [self.source], 1

    def get_source(self, _principal, source_id):
        if source_id != self.source.id:
            raise SourceNotFoundError("Source not found")
        return self.source

    def archive_source(self, _principal, source_id):
        source = self.get_source(_principal, source_id)
        source.status = SourceStatus.ARCHIVED.value
        return source


class FakeVersionApiService:
    def __init__(self, version):
        self.version = version

    def upload_version(self, _principal, source_id, stream, _filename, _mime):
        if stream.read() == b"duplicate":
            raise DuplicateVersionError("This file already exists for the source")
        self.version.source_id = source_id
        return self.version

    def list_versions(self, _principal, _source_id):
        return [self.version]

    def get_version(self, _principal, version_id):
        if version_id != self.version.id:
            raise SourceNotFoundError("Source version not found")
        return self.version

    def open_version_file(self, principal, version_id):
        return VersionFile(self.get_version(principal, version_id), io.BytesIO(b"download"))

    def publish_version(self, principal, version_id):
        version = self.get_version(principal, version_id)
        version.processing_status = ProcessingStatus.READY.value
        version.publication_status = PublicationStatus.PUBLISHED.value
        version.is_current = True
        version.published_by = principal.user_id
        version.published_at = datetime.now(timezone.utc)
        version.effective_from = version.published_at
        return version

    def withdraw_version(self, principal, version_id):
        version = self.get_version(principal, version_id)
        version.publication_status = PublicationStatus.WITHDRAWN.value
        version.is_current = False
        version.effective_to = datetime.now(timezone.utc)
        return version


class SourceApiTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.user_id = uuid4()
        self.source = Source(
            id=uuid4(),
            title="Policy",
            description=None,
            source_type=SourceType.DOCUMENT.value,
            business_scene="onboarding",
            scope_type=ScopeType.COMPANY.value,
            access_level=AccessLevel.INTERNAL.value,
            status=SourceStatus.ACTIVE.value,
            created_by=self.user_id,
            created_at=now,
            updated_at=now,
        )
        self.version = SourceVersion(
            id=uuid4(),
            source_id=self.source.id,
            version_no=1,
            original_filename="policy.txt",
            mime_type="text/plain",
            file_size=8,
            file_hash="a" * 64,
            storage_key="sha256/aa/aa/" + "a" * 64,
            processing_status=ProcessingStatus.PENDING.value,
            processing_error_code=None,
            publication_status=PublicationStatus.DRAFT.value,
            is_current=False,
            uploaded_by=self.user_id,
            created_at=now,
            updated_at=now,
        )
        principal = Principal(
            user_id=self.user_id,
            department_id=None,
            roles=frozenset({"SYSTEM_ADMIN"}),
            authenticated=True,
            active=True,
        )
        app.dependency_overrides[get_current_principal] = lambda: principal
        app.dependency_overrides[get_source_service] = lambda: FakeSourceApiService(
            self.source
        )
        app.dependency_overrides[get_version_service] = lambda: FakeVersionApiService(
            self.version
        )
        self.client = ASGITestClient()

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_source_create_list_get_and_archive_contracts(self):
        created = self.client.post(
            "/api/v1/sources",
            json={"title": "Policy", "scope_type": "COMPANY"},
        )
        self.assertEqual(created.status_code, 201)
        listed = self.client.get("/api/v1/sources")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)
        fetched = self.client.get(f"/api/v1/sources/{self.source.id}")
        self.assertEqual(fetched.status_code, 200)
        archived = self.client.post(f"/api/v1/sources/{self.source.id}/archive")
        self.assertEqual(archived.json()["status"], "ARCHIVED")

    def test_version_upload_list_get_download_publish_and_withdraw(self):
        uploaded = self.client.post(
            f"/api/v1/sources/{self.source.id}/versions",
            files={"file": ("policy.txt", b"content", "text/plain")},
        )
        self.assertEqual(uploaded.status_code, 201)
        self.assertNotIn("storage_key", uploaded.json())
        self.assertNotIn("C:\\", str(uploaded.json()))
        self.assertEqual(
            self.client.get(f"/api/v1/sources/{self.source.id}/versions").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/source-versions/{self.version.id}").status_code,
            200,
        )
        download = self.client.get(
            f"/api/v1/source-versions/{self.version.id}/download"
        )
        self.assertEqual(download.content, b"download")
        self.assertIn("attachment", download.headers["content-disposition"])
        published = self.client.post(
            f"/api/v1/source-versions/{self.version.id}/publish"
        )
        self.assertEqual(published.json()["publication_status"], "PUBLISHED")
        withdrawn = self.client.post(
            f"/api/v1/source-versions/{self.version.id}/withdraw"
        )
        self.assertEqual(withdrawn.json()["publication_status"], "WITHDRAWN")

    def test_not_found_and_duplicate_are_stable_non_leaking_errors(self):
        response = self.client.get(f"/api/v1/sources/{uuid4()}")
        self.assertEqual(response.status_code, 404)
        duplicate = self.client.post(
            f"/api/v1/sources/{self.source.id}/versions",
            files={"file": ("policy.txt", b"duplicate", "text/plain")},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertNotIn("storage_key", duplicate.text)

    def test_unauthenticated_source_request_is_rejected(self):
        app.dependency_overrides.pop(get_current_principal)
        response = self.client.get("/api/v1/sources")
        self.assertEqual(response.status_code, 401)

    def test_worker_state_methods_are_not_public_routes(self):
        paths = set(app.openapi()["paths"])
        self.assertNotIn("/api/v1/source-versions/{version_id}/mark-ready", paths)
        self.assertNotIn("/api/v1/source-versions/{version_id}/mark-failed", paths)
        self.assertIn("/api/v1/source-versions/{version_id}/process", paths)
