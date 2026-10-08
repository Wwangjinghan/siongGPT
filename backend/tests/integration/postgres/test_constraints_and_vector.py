from __future__ import annotations

import math
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.core.principal import Principal
from app.embeddings.repository import EmbeddingRepository
from app.permissions.service import PermissionService
from app.retrieval.repository import RetrievalRepository
from app.retrieval.types import RetrievalFilters
from tests.integration.postgres.base import PostgresGateCase


def vector(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


class SchemaAndConstraintGateTests(PostgresGateCase):
    def assert_rejected(self, statement: str, parameters: dict):
        savepoint = self.connection.begin_nested()
        try:
            with self.assertRaises((IntegrityError, DataError)):
                self.connection.execute(text(statement), parameters)
        finally:
            savepoint.rollback()

    def test_extension_generated_fts_and_required_indexes_are_online(self):
        extension = self.connection.scalar(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
        indexes = set(self.connection.scalars(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname IN "
            "('uq_source_versions_one_current','uq_ingestion_jobs_active_version',"
            "'ix_document_chunks_search_vector','uq_embedding_profiles_one_active',"
            "'ix_chunk_embeddings_hnsw_cosine')"
        )))
        generation = self.connection.scalar(text(
            "SELECT generation_expression FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='document_chunks' AND column_name='search_vector'"
        ))
        self.assertEqual(extension, "vector")
        self.assertEqual(len(indexes), 5)
        self.assertIn("to_tsvector", generation)

    def test_source_version_unique_current_and_state_constraints_reject_real_rows(self):
        seeded = self.seed_document()
        insert = (
            "INSERT INTO source_versions "
            "(id,source_id,version_no,original_filename,mime_type,file_size,file_hash,storage_key,"
            "processing_status,publication_status,is_current,uploaded_by,published_by,published_at,effective_from,effective_to) VALUES "
            "(:id,:source_id,:version_no,'duplicate.txt','text/plain',1,:file_hash,:storage_key,"
            ":processing,:publication,:current,:user_id,:published_by,:published_at,:effective_from,:effective_to)"
        )
        base = {
            "id": uuid4(), "source_id": seeded["source_id"], "user_id": seeded["user_id"],
            "file_hash": "a" * 64, "storage_key": f"gate/{uuid4().hex}",
            "processing": "PENDING", "publication": "DRAFT", "current": False,
            "published_by": None, "published_at": None,
            "effective_from": None, "effective_to": None,
        }
        self.assert_rejected(insert, base | {"version_no": 1})
        existing_hash = self.connection.scalar(text("SELECT file_hash FROM source_versions WHERE id=:id"), {"id": seeded["version_id"]})
        self.assert_rejected(insert, base | {"id": uuid4(), "version_no": 2, "file_hash": existing_hash})
        self.assert_rejected(insert, base | {
            "id": uuid4(), "version_no": 2, "current": True,
            "processing": "READY", "publication": "PUBLISHED",
            "published_by": seeded["user_id"], "published_at": "2026-01-01T00:00:00+00:00",
        })
        self.assert_rejected(insert, base | {
            "id": uuid4(), "version_no": 2,
            "effective_from": "2026-02-01T00:00:00+00:00",
            "effective_to": "2026-01-01T00:00:00+00:00",
        })

    def test_job_chunk_and_active_profile_constraints_reject_real_rows(self):
        seeded = self.seed_document()
        self.connection.execute(text(
            "INSERT INTO ingestion_jobs "
            "(id,source_version_id,job_type,status,attempt_count,max_attempts,available_at,created_by) "
            "VALUES (:id,:version_id,'DOCUMENT_EMBEDDING','QUEUED',0,3,now(),:user_id)"
        ), {"id": uuid4(), "version_id": seeded["version_id"], "user_id": seeded["user_id"]})
        self.assert_rejected(
            "INSERT INTO ingestion_jobs (id,source_version_id,job_type,status,attempt_count,max_attempts,available_at,created_by) "
            "VALUES (:id,:version_id,'DOCUMENT_EMBEDDING','RUNNING',1,3,now(),:user_id)",
            {"id": uuid4(), "version_id": seeded["version_id"], "user_id": seeded["user_id"]},
        )
        self.assert_rejected(
            "INSERT INTO document_chunks (id,source_version_id,chunk_index,content,content_hash,block_type,locator,metadata) "
            "VALUES (:id,:version_id,0,'duplicate',:hash,'PARAGRAPH','{}','{}')",
            {"id": uuid4(), "version_id": seeded["version_id"], "hash": "d" * 64},
        )
        self.assert_rejected(
            "INSERT INTO embedding_profiles "
            "(id,provider_type,model_name,model_revision,dimensions,distance_metric,normalized,query_prefix,passage_prefix,status) "
            "VALUES (:id,'LOCAL_E5','other',:revision,384,'cosine',true,'query: ','passage: ','ACTIVE')",
            {"id": uuid4(), "revision": "f" * 40},
        )

    def test_generated_fts_recalls_codes_and_updates(self):
        seeded = self.seed_document(content="PO DO GST PRJ-001")
        for term in ("PO", "DO", "GST", "PRJ-001"):
            found = self.connection.scalar(text(
                "SELECT count(*) FROM document_chunks WHERE id=:id "
                "AND search_vector @@ plainto_tsquery('simple', :query)"
            ), {"id": seeded["chunk_id"], "query": term})
            self.assertEqual(found, 1, term)
        self.connection.execute(text("UPDATE document_chunks SET content='UPDATED-CODE' WHERE id=:id"), {"id": seeded["chunk_id"]})
        updated = self.connection.scalar(text(
            "SELECT count(*) FROM document_chunks WHERE id=:id "
            "AND search_vector @@ plainto_tsquery('simple','UPDATED-CODE')"
        ), {"id": seeded["chunk_id"]})
        self.assertEqual(updated, 1)

    def test_vector_dimension_uniqueness_cosine_and_hnsw_execution(self):
        seeded = self.seed_document()
        profile_id = self.connection.scalar(text("SELECT id FROM embedding_profiles WHERE status='ACTIVE'"))
        unit = [1.0] + [0.0] * 383
        self.connection.execute(text(
            "INSERT INTO document_chunk_embeddings "
            "(id,chunk_id,embedding_profile_id,embedding,content_hash) "
            "VALUES (:id,:chunk_id,:profile_id,CAST(:embedding AS vector),:hash)"
        ), {"id": uuid4(), "chunk_id": seeded["chunk_id"], "profile_id": profile_id, "embedding": vector(unit), "hash": seeded["content_hash"]})
        similarity = self.connection.scalar(text(
            "SELECT 1 - (embedding <=> CAST(:query AS vector)) FROM document_chunk_embeddings WHERE chunk_id=:chunk_id"
        ), {"query": vector(unit), "chunk_id": seeded["chunk_id"]})
        self.assertTrue(math.isclose(float(similarity), 1.0, rel_tol=1e-7, abs_tol=1e-7))
        second_chunk = uuid4()
        self.connection.execute(text(
            "INSERT INTO document_chunks "
            "(id,source_version_id,chunk_index,content,content_hash,block_type,locator,metadata) "
            "VALUES (:id,:version_id,1,'dimension check',:hash,'PARAGRAPH','{}','{}')"
        ), {"id": second_chunk, "version_id": seeded["version_id"], "hash": "e" * 64})
        self.assert_rejected(
            "INSERT INTO document_chunk_embeddings "
            "(id,chunk_id,embedding_profile_id,embedding,content_hash) "
            "VALUES (:id,:chunk_id,:profile_id,CAST('[1,0]' AS vector),:hash)",
            {"id": uuid4(), "chunk_id": second_chunk, "profile_id": profile_id, "hash": "e" * 64},
        )
        self.connection.execute(text("SET LOCAL hnsw.ef_search = 40"))
        rows = list(self.connection.execute(text(
            "SELECT chunk_id FROM document_chunk_embeddings ORDER BY embedding <=> CAST(:query AS vector) LIMIT 5"
        ), {"query": vector(unit)}))
        self.assertEqual(rows[0].chunk_id, seeded["chunk_id"])
        self.connection.execute(text("SET LOCAL enable_seqscan = off"))
        self.connection.execute(text("SET LOCAL enable_indexscan = on"))
        hnsw_plan = "\n".join(self.connection.scalars(text(
            "EXPLAIN SELECT chunk_id FROM document_chunk_embeddings "
            "ORDER BY embedding <=> CAST(:query AS vector) LIMIT 5"
        ), {"query": vector(unit)}))
        self.assertIn("ix_chunk_embeddings_hnsw_cosine", hnsw_plan)
        self.connection.execute(text("SET LOCAL enable_seqscan = on"))
        self.connection.execute(text("SET LOCAL enable_indexscan = off"))
        self.connection.execute(text("SET LOCAL enable_bitmapscan = off"))
        exact_plan = "\n".join(self.connection.scalars(text(
            "EXPLAIN SELECT chunk_id FROM document_chunk_embeddings "
            "ORDER BY embedding <=> CAST(:query AS vector) LIMIT 5"
        ), {"query": vector(unit)}))
        self.assertNotIn("ix_chunk_embeddings_hnsw_cosine", exact_plan)

    def test_semantic_search_enforces_department_and_content_hash(self):
        seeded = self.seed_document()
        profile_id = self.connection.scalar(text("SELECT id FROM embedding_profiles WHERE status='ACTIVE'"))
        unit = [1.0] + [0.0] * 383
        embedding_id = uuid4()
        self.connection.execute(text(
            "INSERT INTO document_chunk_embeddings "
            "(id,chunk_id,embedding_profile_id,embedding,content_hash) "
            "VALUES (:id,:chunk_id,:profile_id,CAST(:embedding AS vector),:hash)"
        ), {
            "id": embedding_id, "chunk_id": seeded["chunk_id"], "profile_id": profile_id,
            "embedding": vector(unit), "hash": seeded["content_hash"],
        })
        session = Session(bind=self.connection)
        try:
            profile = EmbeddingRepository(session).active_profile()
            repository = RetrievalRepository(session)
            same_department = Principal(uuid4(), seeded["department_id"], frozenset({"EMPLOYEE"}), True, True)
            other_department = Principal(uuid4(), uuid4(), frozenset({"EMPLOYEE"}), True, True)
            allowed = repository.semantic(
                same_department, PermissionService(), unit, profile,
                RetrievalFilters(), 5, mode="exact", hnsw_ef_search=40,
            )
            denied = repository.semantic(
                other_department, PermissionService(), unit, profile,
                RetrievalFilters(), 5, mode="exact", hnsw_ef_search=40,
            )
            self.assertEqual([item.chunk_id for item in allowed], [seeded["chunk_id"]])
            self.assertEqual(denied, [])
            self.connection.execute(text(
                "UPDATE document_chunk_embeddings SET content_hash=:hash WHERE id=:id"
            ), {"hash": "f" * 64, "id": embedding_id})
            stale = repository.semantic(
                same_department, PermissionService(), unit, profile,
                RetrievalFilters(), 5, mode="exact", hnsw_ef_search=40,
            )
            self.assertEqual(stale, [])
        finally:
            session.close()
