from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.principal import Principal
from app.embeddings.local_e5 import LocalE5Provider
from app.embeddings.repository import EmbeddingRepository
from app.permissions.service import PermissionService
from app.retrieval.evaluation import calculate_metrics
from app.retrieval.fusion import deterministic_rerank, reciprocal_rank_fusion
from app.retrieval.repository import RetrievalRepository
from app.retrieval.types import RetrievalFilters
from tests.integration.postgres.base import PostgresGateCase
from tests.integration.postgres.test_constraints_and_vector import vector


POLICY_TEXT = {
    "reimbursement": (
        "Employee reimbursement claims require the purchase order PO, delivery order DO, "
        "itemized receipt, approval record, and expense claim form. 员工报销需要采购订单、送货单、收据和审批记录。"
    ),
    "gst": (
        "GST may be claimed for eligible fictional medical expenses only when a valid tax invoice "
        "states the supplier registration number. 医疗费用 GST 申报需要有效税务发票。"
    ),
    "project": (
        "Project Code PRJ-001 is assigned by the project administration team before procurement. "
        "项目编号 PRJ-001 必须在采购前分配。"
    ),
    "restricted": (
        "Confidential other-department procedure with a secret reimbursement override and PRJ-001."
    ),
}


class RealRetrievalEvaluationTests(PostgresGateCase):
    def test_real_fts_vector_and_hybrid_baseline(self):
        fixture = json.loads(
            (Path(__file__).parents[2] / "fixtures" / "retrieval_evaluation.json").read_text(encoding="utf-8")
        )
        documents = [self.seed_document(content=POLICY_TEXT[item["id"]]) for item in fixture["sources"]]
        authorized_department = documents[0]["department_id"]
        for document in documents[:3]:
            self.connection.execute(
                text("UPDATE sources SET department_id=:department_id WHERE id=:source_id"),
                {"department_id": authorized_department, "source_id": document["source_id"]},
            )

        provider = LocalE5Provider(
            model_name=settings.embedding_model_name,
            revision=settings.embedding_model_revision,
            local_path=settings.embedding_model_local_path,
            allow_download=False,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
            max_sequence_length=settings.embedding_max_sequence_length,
        )
        passage_vectors = provider.embed_passages([POLICY_TEXT[item["id"]] for item in fixture["sources"]])
        profile_id = self.connection.scalar(text("SELECT id FROM embedding_profiles WHERE status='ACTIVE'"))
        for document, embedding in zip(documents, passage_vectors, strict=True):
            self.connection.execute(text(
                "INSERT INTO document_chunk_embeddings "
                "(id,chunk_id,embedding_profile_id,embedding,content_hash) "
                "VALUES (:id,:chunk_id,:profile_id,CAST(:embedding AS vector),:content_hash)"
            ), {
                "id": uuid4(), "chunk_id": document["chunk_id"], "profile_id": profile_id,
                "embedding": vector(embedding), "content_hash": document["content_hash"],
            })

        labels: dict[UUID, str] = {
            document["chunk_id"]: source["chunk"]
            for document, source in zip(documents, fixture["sources"], strict=True)
        }
        principal = Principal(uuid4(), authorized_department, frozenset({"EMPLOYEE"}), True, True)
        session = Session(bind=self.connection)
        rankings = {"fts": {}, "vector": {}, "hybrid": {}}
        top_k = {}
        try:
            profile = EmbeddingRepository(session).active_profile()
            provider.ensure_profile_matches(profile)
            repository = RetrievalRepository(session)
            for case in fixture["queries"]:
                query = case["query"]
                fts = repository.fts(principal, PermissionService(), query, RetrievalFilters(), 5)
                semantic = repository.semantic(
                    principal, PermissionService(), provider.embed_query(query), profile,
                    RetrievalFilters(), 5, mode="exact", hnsw_ef_search=40,
                )
                fused = deterministic_rerank(
                    reciprocal_rank_fusion(fts, semantic, fts_weight=1.0, vector_weight=1.0, rrf_k=60),
                    query,
                    0.01,
                )[:5]
                rankings["fts"][case["id"]] = [labels[item.chunk_id] for item in fts]
                rankings["vector"][case["id"]] = [labels[item.chunk_id] for item in semantic]
                rankings["hybrid"][case["id"]] = [labels[item.candidate.chunk_id] for item in fused]
                top_k[case["id"]] = {
                    "query_type": case["query_type"],
                    "fts": rankings["fts"][case["id"]],
                    "vector": rankings["vector"][case["id"]],
                    "hybrid": rankings["hybrid"][case["id"]],
                }
        finally:
            session.close()

        restricted = "unauthorized-chunk"
        for mode_rankings in rankings.values():
            self.assertTrue(all(restricted not in ranked for ranked in mode_rankings.values()))

        report = {}
        for mode, mode_rankings in rankings.items():
            metrics = calculate_metrics(fixture["queries"], mode_rankings)
            failures = [
                case["id"] for case in fixture["queries"]
                if case["acceptable_chunks"]
                and not set(case["acceptable_chunks"]).intersection(mode_rankings.get(case["id"], [])[:5])
            ]
            report[mode] = {
                "recall_at_1": metrics.recall_at_1,
                "recall_at_3": metrics.recall_at_3,
                "recall_at_5": metrics.recall_at_5,
                "mrr": metrics.mrr,
                "failed_queries": failures,
            }
        report["top_k"] = top_k
        report["unauthorized_results"] = 0
        print("REAL_RETRIEVAL_EVALUATION_JSON=" + json.dumps(report, ensure_ascii=False, sort_keys=True))
        self.assertEqual(report["unauthorized_results"], 0)
