import logging
import os
import signal
import socket
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.chunks.chunker import DeterministicChunker
from app.chunks.repository import DocumentChunkRepository
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.domain_types import (
    IngestionErrorCode,
    IngestionJobStatus,
    ProcessingStatus,
    IngestionJobType,
)
from app.embeddings.base import EmbeddingError
from app.embeddings.factory import get_embedding_provider
from app.embeddings.repository import EmbeddingRepository
from app.ingestion.service import IngestionJobService, LeaseLostError
from app.models.source_version import SourceVersion
from app.parsers.base import ParserLimits
from app.parsers.errors import IngestionError
from app.parsers.registry import ParserRegistry
from app.permissions.service import PermissionService
from app.storage.local import LocalStorageAdapter


logger = logging.getLogger(__name__)


def parser_limits_from_settings() -> ParserLimits:
    return ParserLimits(
        max_pdf_pages=settings.ingestion_max_pdf_pages,
        max_extracted_chars=settings.ingestion_max_extracted_chars,
        max_zip_entries=settings.ingestion_max_zip_entries,
        max_uncompressed_bytes=settings.ingestion_max_uncompressed_bytes,
        max_compression_ratio=settings.ingestion_max_compression_ratio,
        max_xlsx_sheets=settings.ingestion_max_xlsx_sheets,
        max_xlsx_rows_per_sheet=settings.ingestion_max_xlsx_rows_per_sheet,
        max_xlsx_cells_per_row=settings.ingestion_max_xlsx_cells_per_row,
        max_xlsx_nonempty_cells=settings.ingestion_max_xlsx_nonempty_cells,
        max_cell_chars=settings.ingestion_max_cell_chars,
    )


class IngestionWorker:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        storage=None,
        parser_registry=None,
        chunker=None,
        embedding_provider=None,
        worker_id: str | None = None,
    ):
        self.session_factory = session_factory
        self.storage = storage or LocalStorageAdapter(settings.source_storage_root)
        self.parser_registry = parser_registry or ParserRegistry(parser_limits_from_settings())
        self.chunker = chunker or DeterministicChunker(
            settings.chunk_max_chars,
            settings.chunk_overlap_chars,
            settings.xlsx_rows_per_chunk,
        )
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.worker_id = worker_id or (
            f"SYSTEM_WORKER:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        )

    def run_once(self) -> bool:
        db = self.session_factory()
        service = IngestionJobService(
            db,
            PermissionService(),
            max_attempts=settings.ingestion_job_max_attempts,
            lease_seconds=settings.ingestion_job_lease_seconds,
            retry_base_seconds=settings.ingestion_retry_base_seconds,
        )
        try:
            job = service.claim_next(self.worker_id)
            if job is None:
                return False
            if job.job_type == IngestionJobType.DOCUMENT_EMBEDDING.value:
                self._process_embedding_backfill(db, service, job)
            else:
                self._process_claimed(db, service, job)
            return True
        finally:
            db.close()

    def _process_claimed(self, db, service: IngestionJobService, job) -> None:
        stream = None
        try:
            version = db.get(SourceVersion, job.source_version_id)
            if version is None:
                raise IngestionError(
                    IngestionErrorCode.FILE_NOT_FOUND, "Source version no longer exists"
                )
            if version.processing_status not in {
                ProcessingStatus.PENDING.value,
                ProcessingStatus.FAILED.value,
                ProcessingStatus.PROCESSING.value,
            }:
                raise IngestionError(
                    IngestionErrorCode.PARSER_FAILED,
                    "Source version is not in a processable state",
                )
            version.processing_status = ProcessingStatus.PROCESSING.value
            version.processing_error_code = None
            db.commit()

            if not self.storage.exists(version.storage_key):
                raise IngestionError(
                    IngestionErrorCode.FILE_NOT_FOUND, "Stored source file was not found"
                )
            try:
                stream = self.storage.open(version.storage_key)
            except OSError as exc:
                raise IngestionError(
                    IngestionErrorCode.STORAGE_READ_FAILED,
                    "Stored source file could not be opened",
                ) from exc

            parser = self.parser_registry.get(version.original_filename, version.mime_type)
            blocks = parser.parse(
                stream,
                filename=version.original_filename,
                mime_type=version.mime_type,
                source_version_id=version.id,
            )
            if not service.heartbeat(job.id, self.worker_id):
                raise LeaseLostError("Lease expired during parsing")
            try:
                drafts = self.chunker.chunk(blocks)
            except Exception as exc:
                raise IngestionError(
                    IngestionErrorCode.CHUNKING_FAILED, "Document chunking failed"
                ) from exc
            if not drafts:
                raise IngestionError(
                    IngestionErrorCode.EMPTY_DOCUMENT, "Document produced no searchable content"
                )
            if not service.heartbeat(job.id, self.worker_id):
                raise LeaseLostError("Lease expired before persistence")

            embedding_repository = EmbeddingRepository(db)
            profile = embedding_repository.active_profile()
            if profile is None:
                raise EmbeddingError(
                    IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE,
                    "No active embedding profile is configured",
                )
            self.embedding_provider.ensure_profile_matches(profile)
            vectors = self.embedding_provider.embed_passages([draft.content for draft in drafts])
            if not service.heartbeat(job.id, self.worker_id):
                raise LeaseLostError("Lease expired during embedding")

            owned_job = service.lock_owned_running_job(job.id, self.worker_id)
            locked_version = db.scalar(
                select(SourceVersion)
                .where(SourceVersion.id == job.source_version_id)
                .with_for_update()
            )
            if locked_version is None:
                raise IngestionError(
                    IngestionErrorCode.FILE_NOT_FOUND, "Source version no longer exists"
                )
            chunks = DocumentChunkRepository(db).replace_for_version(locked_version.id, drafts)
            EmbeddingRepository(db).add_for_chunks(chunks, profile, vectors)
            locked_version.processing_status = ProcessingStatus.READY.value
            locked_version.processing_error_code = None
            owned_job.status = IngestionJobStatus.SUCCEEDED.value
            owned_job.finished_at = datetime.now(timezone.utc)
            owned_job.error_code = None
            owned_job.error_message = None
            owned_job.lease_owner = None
            owned_job.lease_expires_at = None
            owned_job.heartbeat_at = None
            db.commit()
        except LeaseLostError:
            db.rollback()
            logger.warning("Ingestion lease lost for job %s", job.id)
        except (IngestionError, EmbeddingError) as exc:
            db.rollback()
            service.fail_owned_job(job.id, self.worker_id, exc.code, exc.safe_message)
            logger.warning("Ingestion job %s failed with %s", job.id, exc.code.value)
        except Exception:
            db.rollback()
            service.fail_owned_job(
                job.id,
                self.worker_id,
                IngestionErrorCode.DATABASE_WRITE_FAILED,
                "Ingestion persistence failed",
            )
            logger.error("Ingestion job %s failed with an internal error", job.id)
        finally:
            if stream is not None:
                stream.close()

    def _process_embedding_backfill(self, db, service: IngestionJobService, job) -> None:
        try:
            version = db.get(SourceVersion, job.source_version_id)
            if version is None or version.processing_status != ProcessingStatus.READY.value:
                raise EmbeddingError(
                    IngestionErrorCode.EMBEDDING_INCOMPLETE,
                    "Only READY source versions can be reindexed",
                )
            repository = EmbeddingRepository(db)
            profile = repository.active_profile()
            if profile is None:
                raise EmbeddingError(
                    IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE,
                    "No active embedding profile is configured",
                )
            self.embedding_provider.ensure_profile_matches(profile)
            offset = 0
            while True:
                chunks = repository.chunks_for_version_batch(
                    version.id, offset=offset, limit=self.embedding_provider.batch_size
                )
                if not chunks:
                    break
                vectors = self.embedding_provider.embed_passages([chunk.content for chunk in chunks])
                repository.upsert_batch(chunks, profile, vectors)
                db.commit()
                offset += len(chunks)
                if not service.heartbeat(job.id, self.worker_id):
                    raise LeaseLostError("Lease expired during embedding backfill")
            if not repository.version_is_complete(version.id, profile.id):
                raise EmbeddingError(
                    IngestionErrorCode.EMBEDDING_INCOMPLETE,
                    "Embedding backfill is incomplete",
                )
            owned_job = service.lock_owned_running_job(job.id, self.worker_id)
            owned_job.status = IngestionJobStatus.SUCCEEDED.value
            owned_job.finished_at = datetime.now(timezone.utc)
            owned_job.error_code = None
            owned_job.error_message = None
            owned_job.lease_owner = None
            owned_job.lease_expires_at = None
            owned_job.heartbeat_at = None
            db.commit()
        except LeaseLostError:
            db.rollback()
            logger.warning("Embedding lease lost for job %s", job.id)
        except EmbeddingError as exc:
            db.rollback()
            service.fail_owned_job(
                job.id, self.worker_id, exc.code, exc.safe_message, affect_version=False
            )
            logger.warning("Embedding job %s failed with %s", job.id, exc.code.value)
        except Exception:
            db.rollback()
            service.fail_owned_job(
                job.id,
                self.worker_id,
                IngestionErrorCode.DATABASE_WRITE_FAILED,
                "Embedding persistence failed",
                affect_version=False,
            )
            logger.error("Embedding job %s failed with an internal error", job.id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    worker = IngestionWorker()
    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    logger.info("Starting ingestion worker %s", worker.worker_id)
    while not stopping:
        processed = 0
        for _ in range(settings.ingestion_worker_batch_size):
            if stopping or not worker.run_once():
                break
            processed += 1
        if processed == 0 and not stopping:
            time.sleep(settings.ingestion_job_poll_seconds)
    logger.info("Ingestion worker stopped")


if __name__ == "__main__":
    main()
