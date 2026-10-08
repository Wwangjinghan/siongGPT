import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.chunks.chunker import DeterministicChunker
from app.core.domain_types import (
    IngestionErrorCode,
    IngestionJobStatus,
    ProcessingStatus,
    PublicationStatus,
)
from app.models.ingestion_job import IngestionJob
from app.models.source_version import SourceVersion
from app.models.embedding_profile import EmbeddingProfile
from app.models.document_chunk import DocumentChunk
from app.embeddings.base import EmbeddingError
from app.parsers.registry import ParserRegistry
from app.storage.local import LocalStorageAdapter
from app.workers.ingestion import IngestionWorker, parser_limits_from_settings
from tests.test_parsers import docx_fixture, native_text_pdf, xlsx_fixture
from tests.embedding_fakes import FakeEmbeddingProvider


class WorkerDb:
    def __init__(self, version, profile):
        self.version = version
        self.profile = profile
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, _identifier):
        return self.version if model is SourceVersion else None

    def scalar(self, _statement):
        descriptions = getattr(_statement, "column_descriptions", ())
        if descriptions and descriptions[0].get("entity") is EmbeddingProfile:
            return self.profile
        return self.version

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class WorkerJobService:
    def __init__(self, job, version):
        self.job = job
        self.version = version
        self.failed = None

    def heartbeat(self, _job_id, _worker_id):
        return True

    def lock_owned_running_job(self, _job_id, _worker_id):
        return self.job

    def fail_owned_job(self, _job_id, _worker_id, code, message, *, affect_version=True):
        self.failed = (code, message)
        self.job.status = IngestionJobStatus.FAILED.value
        if affect_version:
            self.version.processing_status = ProcessingStatus.FAILED.value
            self.version.processing_error_code = code.value
        return True


class CapturingRepository:
    drafts = None

    def __init__(self, _db):
        pass

    def replace_for_version(self, _version_id, drafts):
        type(self).drafts = list(drafts)
        return []


class CapturingEmbeddingRepository:
    def __init__(self, db):
        self.db = db

    def active_profile(self):
        return self.db.profile

    def add_for_chunks(self, chunks, profile, vectors):
        self.db.saved_vectors = vectors


class BackfillEmbeddingRepository(CapturingEmbeddingRepository):
    chunks = []
    saved = []

    def chunks_for_version_batch(self, _version_id, *, offset, limit):
        return type(self).chunks[offset : offset + limit]

    def upsert_batch(self, chunks, _profile, vectors):
        type(self).saved.extend(zip(chunks, vectors, strict=True))

    def version_is_complete(self, _version_id, _profile_id):
        return len(type(self).saved) == len(type(self).chunks) and bool(type(self).chunks)


class UnavailableEmbeddingProvider(FakeEmbeddingProvider):
    def _encode(self, _texts):
        raise EmbeddingError(
            IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE, "model unavailable"
        )


class IngestionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = LocalStorageAdapter(Path(self.temp.name) / "storage")
        self.saved = self.storage.save(io.BytesIO(b"PO-001 GST\n\nApproval required"), max_bytes=1000)
        self.version = SourceVersion(
            id=uuid4(), source_id=uuid4(), version_no=1,
            original_filename="policy.txt", mime_type="text/plain", file_size=self.saved.file_size,
            file_hash=self.saved.file_hash, storage_key=self.saved.storage_key,
            processing_status=ProcessingStatus.PENDING.value,
            publication_status=PublicationStatus.DRAFT.value, is_current=False,
            uploaded_by=uuid4(),
        )
        now = datetime.now(timezone.utc)
        self.job = IngestionJob(
            id=uuid4(), source_version_id=self.version.id, job_type="DOCUMENT_INGESTION",
            status=IngestionJobStatus.RUNNING.value, attempt_count=1, max_attempts=3,
            available_at=now, lease_owner="worker", lease_expires_at=now + timedelta(seconds=60),
            created_by=uuid4(),
        )
        self.profile = EmbeddingProfile(
            id=uuid4(), provider_type="LOCAL_E5",
            model_name="intfloat/multilingual-e5-small",
            model_revision="fd1525a9fd15316a2d503bf26ab031a61d056e98",
            dimensions=384, distance_metric="cosine", normalized=True,
            query_prefix="query: ", passage_prefix="passage: ", status="ACTIVE",
        )
        self.worker = IngestionWorker(
            session_factory=lambda: None,
            storage=self.storage,
            parser_registry=ParserRegistry(parser_limits_from_settings()),
            chunker=DeterministicChunker(100, 10, 10),
            embedding_provider=FakeEmbeddingProvider(),
            worker_id="worker",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_txt_pipeline_commits_chunks_ready_draft_without_publish(self):
        db = WorkerDb(self.version, self.profile)
        service = WorkerJobService(self.job, self.version)
        with patch("app.workers.ingestion.DocumentChunkRepository", CapturingRepository), patch("app.workers.ingestion.EmbeddingRepository", CapturingEmbeddingRepository):
            self.worker._process_claimed(db, service, self.job)
        self.assertTrue(CapturingRepository.drafts)
        self.assertEqual(self.version.processing_status, ProcessingStatus.READY.value)
        self.assertEqual(self.version.publication_status, PublicationStatus.DRAFT.value)
        self.assertFalse(self.version.is_current)
        self.assertEqual(self.job.status, IngestionJobStatus.SUCCEEDED.value)

    def test_parser_failure_marks_failed_and_worker_survives(self):
        bad = self.storage.save(io.BytesIO(b"\xff\xfe"), max_bytes=1000)
        self.version.storage_key = bad.storage_key
        self.version.file_hash = bad.file_hash
        db = WorkerDb(self.version, self.profile)
        service = WorkerJobService(self.job, self.version)
        self.worker._process_claimed(db, service, self.job)
        self.assertEqual(service.failed[0], IngestionErrorCode.INVALID_TEXT_ENCODING)
        self.assertEqual(self.version.processing_status, ProcessingStatus.FAILED.value)
        self.assertEqual(self.version.publication_status, PublicationStatus.DRAFT.value)

    def test_new_document_provider_failure_never_marks_version_ready(self):
        db = WorkerDb(self.version, self.profile)
        service = WorkerJobService(self.job, self.version)
        worker = IngestionWorker(
            session_factory=lambda: None, storage=self.storage,
            parser_registry=ParserRegistry(parser_limits_from_settings()),
            chunker=DeterministicChunker(100, 10, 10),
            embedding_provider=UnavailableEmbeddingProvider(), worker_id="worker",
        )
        with patch("app.workers.ingestion.DocumentChunkRepository", CapturingRepository), patch("app.workers.ingestion.EmbeddingRepository", CapturingEmbeddingRepository):
            worker._process_claimed(db, service, self.job)
        self.assertEqual(service.failed[0], IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE)
        self.assertEqual(self.version.processing_status, ProcessingStatus.FAILED.value)
        self.assertEqual(self.version.publication_status, PublicationStatus.DRAFT.value)
        self.assertFalse(self.version.is_current)

    def test_pdf_docx_and_xlsx_complete_worker_pipeline(self):
        fixtures = (
            ("policy.pdf", "application/pdf", native_text_pdf("PO-002 GST policy")),
            (
                "policy.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                docx_fixture(),
            ),
            (
                "codes.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                xlsx_fixture(),
            ),
        )
        for filename, mime_type, stream in fixtures:
            with self.subTest(filename=filename):
                saved = self.storage.save(stream, max_bytes=1_000_000)
                self.version.original_filename = filename
                self.version.mime_type = mime_type
                self.version.storage_key = saved.storage_key
                self.version.file_hash = saved.file_hash
                self.version.file_size = saved.file_size
                self.version.processing_status = ProcessingStatus.PENDING.value
                self.version.processing_error_code = None
                self.version.publication_status = PublicationStatus.DRAFT.value
                self.version.is_current = False
                self.job.status = IngestionJobStatus.RUNNING.value
                db = WorkerDb(self.version, self.profile)
                service = WorkerJobService(self.job, self.version)
                CapturingRepository.drafts = None
                with patch(
                    "app.workers.ingestion.DocumentChunkRepository",
                    CapturingRepository,
                ), patch("app.workers.ingestion.EmbeddingRepository", CapturingEmbeddingRepository):
                    self.worker._process_claimed(db, service, self.job)
                self.assertTrue(CapturingRepository.drafts)
                self.assertEqual(
                    self.version.processing_status, ProcessingStatus.READY.value
                )
                self.assertEqual(
                    self.version.publication_status, PublicationStatus.DRAFT.value
                )
                self.assertFalse(self.version.is_current)
                self.assertEqual(self.job.status, IngestionJobStatus.SUCCEEDED.value)

    def test_ready_published_version_backfill_preserves_publication(self):
        self.version.processing_status = ProcessingStatus.READY.value
        self.version.publication_status = PublicationStatus.PUBLISHED.value
        self.version.is_current = True
        self.job.job_type = "DOCUMENT_EMBEDDING"
        BackfillEmbeddingRepository.chunks = [
            DocumentChunk(
                id=uuid4(), source_version_id=self.version.id, chunk_index=0,
                content="PO-001 required", content_hash="b" * 64,
                block_type="PARAGRAPH", locator={}, processing_metadata={},
            )
        ]
        BackfillEmbeddingRepository.saved = []
        db = WorkerDb(self.version, self.profile)
        service = WorkerJobService(self.job, self.version)
        with patch("app.workers.ingestion.EmbeddingRepository", BackfillEmbeddingRepository):
            self.worker._process_embedding_backfill(db, service, self.job)
        self.assertEqual(self.job.status, IngestionJobStatus.SUCCEEDED.value)
        self.assertEqual(self.version.processing_status, ProcessingStatus.READY.value)
        self.assertEqual(self.version.publication_status, PublicationStatus.PUBLISHED.value)
        self.assertTrue(self.version.is_current)
        self.assertEqual(len(BackfillEmbeddingRepository.saved), 1)

    def test_backfill_provider_failure_keeps_ready_and_publication(self):
        self.version.processing_status = ProcessingStatus.READY.value
        self.version.publication_status = PublicationStatus.PUBLISHED.value
        self.version.is_current = True
        self.job.job_type = "DOCUMENT_EMBEDDING"
        BackfillEmbeddingRepository.chunks = [
            DocumentChunk(
                id=uuid4(), source_version_id=self.version.id, chunk_index=0,
                content="text", content_hash="c" * 64,
                block_type="PARAGRAPH", locator={}, processing_metadata={},
            )
        ]
        BackfillEmbeddingRepository.saved = []
        db = WorkerDb(self.version, self.profile)
        service = WorkerJobService(self.job, self.version)
        worker = IngestionWorker(
            session_factory=lambda: None, storage=self.storage,
            parser_registry=ParserRegistry(parser_limits_from_settings()),
            chunker=DeterministicChunker(100, 10, 10),
            embedding_provider=UnavailableEmbeddingProvider(), worker_id="worker",
        )
        with patch("app.workers.ingestion.EmbeddingRepository", BackfillEmbeddingRepository):
            worker._process_embedding_backfill(db, service, self.job)
        self.assertEqual(service.failed[0], IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE)
        self.assertEqual(self.version.processing_status, ProcessingStatus.READY.value)
        self.assertEqual(self.version.publication_status, PublicationStatus.PUBLISHED.value)
