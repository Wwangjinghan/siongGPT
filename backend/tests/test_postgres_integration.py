import os
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import settings
from scripts.integration_gate_support import (
    BASELINE_DATABASE_ENV,
    IntegrationGateSafetyError,
    allowed_ci_hosts_from_environment,
    require_protected_test_database,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
DESTRUCTIVE_TESTS_ALLOWED = os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS") == "true"


@unittest.skipUnless(
    TEST_DATABASE_URL and DESTRUCTIVE_TESTS_ALLOWED,
    "requires a protected PostgreSQL TEST_DATABASE_URL and ALLOW_DESTRUCTIVE_DB_TESTS=true",
)
class PostgreSQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            baseline = os.getenv(BASELINE_DATABASE_ENV)
            if not baseline:
                raise IntegrationGateSafetyError(
                    "Baseline development database identity was not propagated to online tests"
                )
            require_protected_test_database(
                TEST_DATABASE_URL,
                allow_destructive=os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS"),
                development_url=baseline,
                allowed_ci_hosts=allowed_ci_hosts_from_environment(),
            )
        except IntegrationGateSafetyError as exc:
            raise RuntimeError(f"Unsafe integration database refused: {exc}") from exc
        cls.original_url = settings.database_url
        settings.database_url = TEST_DATABASE_URL
        command.upgrade(Config("alembic.ini"), "head")
        cls.engine = create_engine(TEST_DATABASE_URL)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        settings.database_url = cls.original_url

    def test_pgvector_and_phase2_migration_are_online(self):
        with self.engine.connect() as connection:
            extension = connection.scalar(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            tables = set(
                connection.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name IN "
                        "('sources','source_versions')"
                    )
                )
            )
        self.assertEqual(extension, "vector")
        self.assertEqual(tables, {"sources", "source_versions"})

    def test_postgres_partial_unique_index_and_checks_exist(self):
        with self.engine.connect() as connection:
            index_definition = connection.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname='uq_source_versions_one_current'"
                )
            )
            checks = set(
                connection.scalars(
                    text(
                        "SELECT conname FROM pg_constraint WHERE conname IN "
                        "('ck_sources_scope_fields',"
                        "'ck_source_versions_current_published_ready')"
                    )
                )
            )
        self.assertIn("WHERE is_current", index_definition)
        self.assertEqual(
            checks,
            {"ck_sources_scope_fields", "ck_source_versions_current_published_ready"},
        )

    def test_phase3_generated_fts_gin_and_active_job_index_are_online(self):
        with self.engine.connect() as connection:
            expression = connection.scalar(
                text(
                    "SELECT generation_expression FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='document_chunks' "
                    "AND column_name='search_vector'"
                )
            )
            gin_definition = connection.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname='ix_document_chunks_search_vector'"
                )
            )
            active_definition = connection.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname='uq_ingestion_jobs_active_version'"
                )
            )
        self.assertIn("to_tsvector", expression)
        self.assertIn("USING gin", gin_definition)
        self.assertIn("UNIQUE", active_definition)
        self.assertIn("QUEUED", active_definition)
        self.assertIn("RUNNING", active_definition)

    def test_phase4_vector_dimension_profile_unique_and_hnsw_are_online(self):
        with self.engine.connect() as connection:
            dimensions = connection.scalar(
                text("SELECT vector_dims(array_fill(0::real, ARRAY[384])::vector)")
            )
            active_index = connection.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname='uq_embedding_profiles_one_active'"
                )
            )
            hnsw_index = connection.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname='ix_chunk_embeddings_hnsw_cosine'"
                )
            )
            vector_type = connection.scalar(
                text(
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                    "WHERE c.relname='document_chunk_embeddings' "
                    "AND a.attname='embedding'"
                )
            )
        self.assertEqual(dimensions, 384)
        self.assertEqual(vector_type, "vector(384)")
        self.assertIn("UNIQUE", active_index)
        self.assertIn("WHERE", active_index)
        self.assertIn("USING hnsw", hnsw_index)
        self.assertIn("vector_cosine_ops", hnsw_index)

    def test_phase4_cosine_exact_operator_is_online(self):
        with self.engine.connect() as connection:
            similarity = connection.scalar(
                text("SELECT 1 - ('[1,0]'::vector <=> '[1,0]'::vector)")
            )
        self.assertAlmostEqual(float(similarity), 1.0)
