import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx

from app.api.v1.search import get_retrieval_service
from app.core.database import get_db
from app.core.domain_types import RetrievalMode
from app.core.principal import Principal, get_current_principal
from app.main import app
from app.retrieval.service import RetrievalOutcome
from app.retrieval.types import FusedCandidate, RetrievalCandidate
from tests.embedding_fakes import FakeEmbeddingProvider


class Client:
    def request(self, method, path, **kwargs):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(send())

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)


class FakeRetrievalService:
    def __init__(self, results):
        self.results = results
        self.calls = []
        self.profile = SimpleNamespace(
            id=uuid4(), model_name="intfloat/multilingual-e5-small",
            model_revision="f" * 40, dimensions=384,
        )

    def search(self, principal, query, filters, limit):
        self.calls.append((principal, query, filters, limit))
        return RetrievalOutcome(RetrievalMode.HYBRID, True, self.profile, self.results)


class HealthDb:
    def __init__(self, profile):
        self.profile = profile

    def scalar(self, _statement):
        return self.profile


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal(uuid4(), uuid4(), frozenset({"EMPLOYEE"}), True, True)
        candidate = RetrievalCandidate(
            chunk_id=uuid4(), source_id=uuid4(), source_version_id=uuid4(),
            source_title="Expense policy", original_filename="policy.txt", version_no=2,
            content="A" * 800, locator={"page": 2}, section="Claims",
            business_scene="reimbursement", scope_type="DEPARTMENT",
            fts_rank=0.7, semantic_similarity=0.8,
        )
        fused = FusedCandidate(
            candidate=candidate, fusion_score=0.04,
            matched_by={"FTS", "SEMANTIC"}, rerank_reasons=["DUAL_CHANNEL"],
        )
        self.service = FakeRetrievalService([fused])
        app.dependency_overrides[get_current_principal] = lambda: self.principal
        app.dependency_overrides[get_retrieval_service] = lambda: self.service
        self.client = Client()

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_search_success_is_bounded_and_does_not_leak_vectors_or_paths(self):
        response = self.client.post(
            "/api/v1/search",
            json={"query": "expense claim", "limit": 10, "filters": {"scope_type": "DEPARTMENT"}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["retrieval_mode"], "HYBRID")
        self.assertTrue(body["semantic_available"])
        self.assertEqual(len(body["results"][0]["content_snippet"]), 500)
        serialized = response.text.lower()
        for forbidden in ("embedding\"", "storage_key", "lease_owner", "absolute_path"):
            self.assertNotIn(forbidden, serialized)

    def test_empty_results_invalid_filters_and_limit(self):
        self.service.results = []
        empty = self.client.post("/api/v1/search", json={"query": "nothing"})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["results"], [])
        invalid = self.client.post(
            "/api/v1/search", json={"query": "test", "filters": {"include_draft": True}}
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(
            self.client.post("/api/v1/search", json={"query": "test", "limit": 51}).status_code,
            422,
        )

    def test_unauthenticated_search_and_health_are_rejected(self):
        app.dependency_overrides.pop(get_current_principal)
        self.assertEqual(self.client.post("/api/v1/search", json={"query": "test"}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/health/embedding").status_code, 401)

    def test_embedding_health_is_redacted(self):
        profile = self.service.profile
        app.dependency_overrides[get_db] = lambda: HealthDb(profile)
        with patch("app.api.v1.search.get_embedding_provider", return_value=FakeEmbeddingProvider()):
            response = self.client.get("/api/v1/health/embedding")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_profile_id"], str(profile.id))
        for forbidden in ("local_path", "token", "api_key", "traceback"):
            self.assertNotIn(forbidden, response.text.lower())
