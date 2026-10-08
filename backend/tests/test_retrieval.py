import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.dialects.postgresql import dialect

from app.core.config import Settings
from app.core.domain_types import IngestionErrorCode, RetrievalMode
from app.core.principal import Principal
from app.embeddings.base import EmbeddingError
from app.models.embedding_profile import EmbeddingProfile
from app.permissions.service import PermissionService
from app.retrieval.evaluation import calculate_metrics
from app.retrieval.fusion import deterministic_rerank, reciprocal_rank_fusion
from app.retrieval.repository import RetrievalRepository
from app.retrieval.service import RetrievalService
from app.retrieval.types import RetrievalCandidate, RetrievalFilters
from tests.embedding_fakes import FakeEmbeddingProvider


def candidate(chunk_id=None, *, fts=None, semantic=None, title="Expense policy", content="PO-001 required", section="Claims"):
    return RetrievalCandidate(
        chunk_id=chunk_id or uuid4(), source_id=uuid4(), source_version_id=uuid4(),
        source_title=title, original_filename="policy.txt", version_no=1,
        content=content, locator={"line_start": 1}, section=section,
        business_scene="reimbursement", scope_type="DEPARTMENT",
        fts_rank=fts, semantic_similarity=semantic,
    )


class FusionTests(unittest.TestCase):
    def test_rrf_rank_starts_at_one_deduplicates_and_is_stable(self):
        shared = uuid4()
        fused = reciprocal_rank_fusion(
            [candidate(shared, fts=1.0), candidate(fts=0.5)],
            [candidate(shared, semantic=0.9)],
            fts_weight=1.0, vector_weight=1.0, rrf_k=60,
        )
        self.assertEqual(len(fused), 2)
        self.assertEqual(fused[0].candidate.chunk_id, shared)
        self.assertAlmostEqual(fused[0].fusion_score, 2 / 61)
        self.assertEqual(fused[0].matched_by, {"FTS", "SEMANTIC"})
        self.assertEqual(fused[0].candidate.fts_rank, 1.0)
        self.assertEqual(fused[0].candidate.semantic_similarity, 0.9)

    def test_rrf_parameters_and_rerank_boost_are_bounded(self):
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([], [], fts_weight=0, vector_weight=1, rrf_k=60)
        item = reciprocal_rank_fusion(
            [candidate(fts=1.0)], [], fts_weight=1, vector_weight=1, rrf_k=60
        )[0]
        base = item.fusion_score
        reranked = deterministic_rerank([item], "PO-001", 0.01)[0]
        self.assertLessEqual(reranked.fusion_score - base, 0.01)
        self.assertIn("EXACT_CODE", reranked.rerank_reasons)


class CaptureSession:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: [])


class RetrievalRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = CaptureSession()
        self.repo = RetrievalRepository(self.db)
        self.principal = Principal(uuid4(), uuid4(), frozenset({"EMPLOYEE"}), True, True)
        self.profile = EmbeddingProfile(
            id=uuid4(), provider_type="LOCAL_E5", model_name="model",
            model_revision="f" * 40, dimensions=384, distance_metric="cosine",
            normalized=True, query_prefix="query: ", passage_prefix="passage: ", status="ACTIVE",
        )

    def test_fts_is_parameterized_and_has_hard_filters(self):
        malicious = "GST'); DROP TABLE sources; --"
        self.repo.fts(self.principal, PermissionService(), malicious, RetrievalFilters(), 10)
        compiled = self.db.statements[-1].compile(dialect=dialect())
        sql = str(compiled)
        self.assertNotIn("DROP TABLE", sql)
        self.assertIn(malicious, compiled.params.values())
        for fragment in (
            "sources.status =", "source_versions.processing_status =",
            "source_versions.publication_status =", "source_versions.is_current IS true",
            "sources.scope_type IN", "sources.department_id",
        ):
            self.assertIn(fragment, sql)

    def test_semantic_has_profile_hash_completeness_permission_and_safe_hnsw(self):
        self.repo.semantic(
            self.principal, PermissionService(), [1.0] + [0.0] * 383,
            self.profile, RetrievalFilters(), 10, mode="hnsw", hnsw_ef_search=40,
        )
        self.assertEqual(len(self.db.statements), 2)
        setting = self.db.statements[0].compile(dialect=dialect())
        self.assertIn("set_config", str(setting))
        self.assertIn("40", setting.params.values())
        sql = str(self.db.statements[1].compile(dialect=dialect()))
        self.assertIn("document_chunk_embeddings.content_hash = document_chunks.content_hash", sql)
        self.assertIn("embedding_profiles.status =", sql)
        self.assertIn("NOT (EXISTS", sql)
        self.assertIn("sources.department_id", sql)

    def test_exact_mode_disables_approximate_index_for_full_recall(self):
        self.repo.semantic(
            self.principal, PermissionService(), [1.0] + [0.0] * 383,
            self.profile, RetrievalFilters(), 10, mode="exact", hnsw_ef_search=40,
        )
        setting = self.db.statements[0].compile(dialect=dialect())
        self.assertIn("set_config", str(setting))
        self.assertIn("enable_indexscan", setting.params.values())
        self.assertIn("off", setting.params.values())


class UnavailableProvider(FakeEmbeddingProvider):
    def _encode(self, _texts):
        raise EmbeddingError(IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE, "unavailable")


class StaticRetrievalRepository:
    def __init__(self, fts, semantic):
        self.fts_candidates = fts
        self.semantic_candidates = semantic

    def fts(self, *_args, **_kwargs):
        return self.fts_candidates

    def semantic(self, *_args, **_kwargs):
        return self.semantic_candidates


class ActiveProfileRepository:
    profile = None

    def __init__(self, _db):
        pass

    def active_profile(self):
        return self.profile


class RetrievalServiceTests(unittest.TestCase):
    @staticmethod
    def settings():
        return Settings(database_url="postgresql+psycopg://example", jwt_secret="secret", _env_file=None)

    @staticmethod
    def principal():
        return Principal(uuid4(), uuid4(), frozenset({"EMPLOYEE"}), True, True)

    @staticmethod
    def profile_for(provider):
        spec = provider.profile()
        return SimpleNamespace(
            **{field: getattr(spec, field) for field in spec.__dataclass_fields__},
            id=uuid4(),
        )

    def test_provider_unavailable_degrades_to_fts_only(self):
        provider = UnavailableProvider()
        ActiveProfileRepository.profile = self.profile_for(provider)
        service = RetrievalService(object(), PermissionService(), provider, self.settings())
        service.repository = StaticRetrievalRepository([candidate(fts=1.0)], [])
        with patch("app.retrieval.service.EmbeddingRepository", ActiveProfileRepository):
            outcome = service.search(self.principal(), "PO", RetrievalFilters(), 10)
        self.assertEqual(outcome.mode, RetrievalMode.FTS_ONLY)
        self.assertFalse(outcome.semantic_available)
        self.assertEqual(len(outcome.results), 1)

    def test_hybrid_and_vector_only_modes(self):
        provider = FakeEmbeddingProvider()
        ActiveProfileRepository.profile = self.profile_for(provider)
        shared = uuid4()
        cases = (
            ([candidate(shared, fts=1)], [candidate(shared, semantic=0.9)], RetrievalMode.HYBRID),
            ([], [candidate(semantic=0.8)], RetrievalMode.VECTOR_ONLY),
        )
        for fts, semantic, expected in cases:
            service = RetrievalService(object(), PermissionService(), provider, self.settings())
            service.repository = StaticRetrievalRepository(fts, semantic)
            with patch("app.retrieval.service.EmbeddingRepository", ActiveProfileRepository):
                outcome = service.search(self.principal(), "claim documents", RetrievalFilters(), 10)
            self.assertEqual(outcome.mode, expected)
            self.assertTrue(outcome.semantic_available)

    def test_query_and_limit_validation(self):
        service = RetrievalService(object(), PermissionService(), FakeEmbeddingProvider(), self.settings())
        for query, limit in ((" ", 10), ("x" * 501, 10), ("ok", 51)):
            with self.subTest(query_len=len(query), limit=limit), self.assertRaises(ValueError):
                service.search(self.principal(), query, RetrievalFilters(), limit)


class EvaluationTests(unittest.TestCase):
    def test_fixture_metrics_repeat_and_permission_negative_is_never_relevant(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "retrieval_evaluation.json").read_text(encoding="utf-8")
        )
        rankings = {case["id"]: list(case["acceptable_chunks"]) for case in fixture["queries"]}
        rankings["unauthorized"] = ["unauthorized-chunk"]
        first = calculate_metrics(fixture["queries"], rankings)
        self.assertEqual(first, calculate_metrics(fixture["queries"], rankings))
        self.assertEqual(first.evaluated_queries, 6)
        self.assertEqual(first.recall_at_1, 1.0)
        self.assertEqual(first.mrr, 1.0)
        unauthorized = next(case for case in fixture["queries"] if case["id"] == "unauthorized")
        self.assertEqual(unauthorized["acceptable_chunks"], [])

    def test_fake_algorithm_baselines_are_reported_separately(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "retrieval_evaluation.json").read_text(encoding="utf-8")
        )
        rankings = {
            "fts": {
                "po": ["reimbursement-docs"],
                "rewrite": ["gst-conditions"],
                "zh": [],
                "mixed": ["reimbursement-docs", "gst-conditions"],
                "gst": ["gst-conditions"],
                "code": ["project-code"],
            },
            "vector": {
                "po": ["gst-conditions", "reimbursement-docs"],
                "rewrite": ["reimbursement-docs"],
                "zh": ["reimbursement-docs"],
                "mixed": ["gst-conditions"],
                "gst": ["project-code", "gst-conditions"],
                "code": [],
            },
            "hybrid": {
                case["id"]: list(case["acceptable_chunks"])
                for case in fixture["queries"]
            },
        }
        metrics = {mode: calculate_metrics(fixture["queries"], values) for mode, values in rankings.items()}
        self.assertEqual(metrics["fts"].recall_at_1, 0.5)
        self.assertAlmostEqual(metrics["fts"].recall_at_3, 4 / 6)
        self.assertAlmostEqual(metrics["fts"].mrr, 3.5 / 6)
        self.assertEqual(metrics["vector"].recall_at_1, 0.5)
        self.assertAlmostEqual(metrics["vector"].recall_at_3, 5 / 6)
        self.assertAlmostEqual(metrics["vector"].mrr, 4 / 6)
        self.assertEqual(metrics["hybrid"].recall_at_1, 1.0)
        self.assertEqual(metrics["hybrid"].mrr, 1.0)
