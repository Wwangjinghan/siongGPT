import unittest

from pydantic import ValidationError

from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_query_retention_has_safe_development_default(self):
        settings = Settings(
            database_url="postgresql+psycopg://example",
            jwt_secret="test-secret",
            _env_file=None,
        )
        self.assertEqual(settings.query_event_retention_days, 30)
        self.assertEqual(settings.source_storage_root, "../../siong-gpt-data/source-storage")
        self.assertEqual(settings.source_max_upload_bytes, 25 * 1024 * 1024)
        self.assertEqual(settings.ingestion_job_max_attempts, 3)
        self.assertEqual(settings.ingestion_job_lease_seconds, 300)
        self.assertEqual(settings.chunk_max_chars, 2_000)
        self.assertEqual(settings.chunk_overlap_chars, 200)

    def test_query_retention_must_be_positive(self):
        with self.assertRaises(ValidationError):
            Settings(
                database_url="postgresql+psycopg://example",
                jwt_secret="test-secret",
                query_event_retention_days=0,
                _env_file=None,
            )

    def test_source_storage_configuration_rejects_unsafe_empty_values(self):
        for values in (
            {"source_storage_root": ""},
            {"source_max_upload_bytes": 0},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Settings(
                    database_url="postgresql+psycopg://example",
                    jwt_secret="test-secret",
                    _env_file=None,
                    **values,
                )

    def test_ingestion_configuration_rejects_invalid_limits(self):
        for values in (
            {"ingestion_job_max_attempts": 0},
            {"ingestion_job_lease_seconds": 0},
            {"ingestion_max_pdf_pages": 0},
            {"ingestion_max_xlsx_cells_per_row": 0},
            {"chunk_max_chars": 100, "chunk_overlap_chars": 100},
            {"xlsx_rows_per_chunk": 0},
            {"retrieval_fts_weight": 0},
            {"retrieval_vector_weight": 0},
            {"vector_search_mode": "unsafe"},
            {"retrieval_candidate_limit": 10, "retrieval_max_result_limit": 20},
            {"vector_candidate_limit": 10, "retrieval_max_result_limit": 20},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Settings(
                    database_url="postgresql+psycopg://example",
                    jwt_secret="test-secret",
                    _env_file=None,
                    **values,
                )
