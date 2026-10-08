import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.api.v1.ingestion import get_ingestion_service
from app.core.domain_types import IngestionJobStatus
from app.core.principal import Principal, get_current_principal
from app.main import app
from app.models.ingestion_job import IngestionJob
from app.sources.errors import InvalidTransitionError, SourceNotFoundError


class Client:
    def request(self, method, path, **kwargs):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(send())

    def get(self, path):
        return self.request("GET", path)

    def post(self, path):
        return self.request("POST", path)


class FakeIngestionService:
    def __init__(self, job):
        self.job = job

    def enqueue(self, _principal, version_id):
        if version_id.int == 0:
            raise SourceNotFoundError("Ingestion job not found")
        self.job.source_version_id = version_id
        return self.job, True

    def enqueue_embedding(self, _principal, version_id):
        self.job.source_version_id = version_id
        self.job.job_type = "DOCUMENT_EMBEDDING"
        return self.job, True

    def get_for_principal(self, _principal, job_id):
        if job_id != self.job.id:
            raise SourceNotFoundError("Ingestion job not found")
        return self.job

    def retry(self, principal, job_id):
        job = self.get_for_principal(principal, job_id)
        if job.status == IngestionJobStatus.SUCCEEDED.value:
            raise InvalidTransitionError("Only failed jobs can be retried")
        job.status = IngestionJobStatus.QUEUED.value
        return job, False

    def cancel(self, principal, job_id):
        job = self.get_for_principal(principal, job_id)
        if job.status != IngestionJobStatus.QUEUED.value:
            raise InvalidTransitionError("Only queued jobs can be cancelled")
        job.status = IngestionJobStatus.CANCELLED.value
        return job


class IngestionApiTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.user_id = uuid4()
        self.job = IngestionJob(
            id=uuid4(), source_version_id=uuid4(), job_type="DOCUMENT_INGESTION",
            status=IngestionJobStatus.QUEUED.value, attempt_count=0, max_attempts=3,
            available_at=now, created_by=self.user_id, created_at=now, updated_at=now,
        )
        principal = Principal(
            self.user_id, uuid4(), frozenset({"FINANCE_ADMIN"}), True, True
        )
        app.dependency_overrides[get_current_principal] = lambda: principal
        app.dependency_overrides[get_ingestion_service] = lambda: FakeIngestionService(self.job)
        self.client = Client()

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_process_returns_202_without_running_parser(self):
        response = self.client.post(f"/api/v1/source-versions/{uuid4()}/process")
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["created_new"])
        self.assertEqual(response.json()["job"]["status"], "QUEUED")
        self.assertNotIn("lease_owner", response.json()["job"])

    def test_embedding_reindex_returns_202_without_loading_model(self):
        response = self.client.post(
            f"/api/v1/source-versions/{uuid4()}/embeddings/reindex"
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job"]["job_type"], "DOCUMENT_EMBEDDING")

    def test_get_retry_cancel_and_stable_errors(self):
        self.assertEqual(
            self.client.get(f"/api/v1/ingestion-jobs/{self.job.id}").status_code, 200
        )
        self.job.status = IngestionJobStatus.FAILED.value
        retried = self.client.post(f"/api/v1/ingestion-jobs/{self.job.id}/retry")
        self.assertEqual(retried.json()["job"]["status"], "QUEUED")
        cancelled = self.client.post(f"/api/v1/ingestion-jobs/{self.job.id}/cancel")
        self.assertEqual(cancelled.json()["status"], "CANCELLED")
        missing = self.client.get(f"/api/v1/ingestion-jobs/{uuid4()}")
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn("Traceback", missing.text)

    def test_unauthenticated_is_rejected(self):
        app.dependency_overrides.pop(get_current_principal)
        self.assertEqual(self.client.get(f"/api/v1/ingestion-jobs/{self.job.id}").status_code, 401)
