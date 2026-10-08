import unittest
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects.postgresql import dialect

from app.embeddings.repository import EmbeddingRepository
from app.models.document_chunk import DocumentChunk
from app.models.document_chunk_embedding import DocumentChunkEmbedding
from app.models.embedding_profile import EmbeddingProfile


class FakeSession:
    def __init__(self, scalar_values=()):
        self.scalar_values = list(scalar_values)
        self.added = []
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    def add_all(self, values):
        self.added.extend(values)

    def flush(self):
        pass

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace()


def profile():
    return EmbeddingProfile(
        id=uuid4(), provider_type="LOCAL_E5", model_name="model",
        model_revision="f" * 40, dimensions=384, distance_metric="cosine",
        normalized=True, query_prefix="query: ", passage_prefix="passage: ", status="ACTIVE",
    )


def chunk(index=0):
    return DocumentChunk(
        id=uuid4(), source_version_id=uuid4(), chunk_index=index, content="content",
        content_hash=(hex(index + 10)[2:] * 64)[:64], block_type="PARAGRAPH",
        locator={}, processing_metadata={},
    )


class EmbeddingRepositoryTests(unittest.TestCase):
    def test_add_keeps_chunk_hash_and_profile_identity(self):
        db = FakeSession()
        repository = EmbeddingRepository(db)
        source_chunk = chunk()
        active = profile()
        repository.add_for_chunks([source_chunk], active, [[1.0] + [0.0] * 383])
        self.assertEqual(len(db.added), 1)
        embedding = db.added[0]
        self.assertIsInstance(embedding, DocumentChunkEmbedding)
        self.assertEqual(embedding.content_hash, source_chunk.content_hash)
        self.assertEqual(embedding.embedding_profile_id, active.id)

    def test_batch_upsert_is_idempotent_by_chunk_and_profile(self):
        db = FakeSession()
        repository = EmbeddingRepository(db)
        repository.upsert_batch([chunk()], profile(), [[1.0] + [0.0] * 383])
        sql = str(db.statements[-1].compile(dialect=dialect()))
        self.assertIn("ON CONFLICT ON CONSTRAINT uq_chunk_embeddings_chunk_profile DO UPDATE", sql)
        self.assertIn("content_hash", sql)

    def test_completeness_requires_nonzero_equal_counts_and_matching_hash_query(self):
        version_id = uuid4()
        profile_id = uuid4()
        for counts, expected in (((0, 0), False), ((2, 1), False), ((2, 2), True)):
            db = FakeSession(counts)
            self.assertEqual(
                EmbeddingRepository(db).version_is_complete(version_id, profile_id), expected
            )
            if counts[0]:
                sql = str(db.statements[-1].compile(dialect=dialect()))
                self.assertIn(
                    "document_chunk_embeddings.content_hash = document_chunks.content_hash",
                    sql,
                )

    def test_no_repository_operation_deletes_historical_embeddings(self):
        import inspect

        source = inspect.getsource(EmbeddingRepository)
        self.assertNotIn("delete(DocumentChunkEmbedding", source)
