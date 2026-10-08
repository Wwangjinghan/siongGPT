from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.postgres.base import PostgresGateCase


class ConcurrencyAndTransactionGateTests(PostgresGateCase):
    def _delete_seeded(self, documents: list[dict]) -> None:
        source_ids = [item["source_id"] for item in documents]
        version_ids = [item["version_id"] for item in documents]
        chunk_ids = [item["chunk_id"] for item in documents]
        user_ids = [item["user_id"] for item in documents]
        department_ids = [item["department_id"] for item in documents]
        with self.engine.begin() as cleanup:
            cleanup.execute(text("DELETE FROM document_chunk_embeddings WHERE chunk_id = ANY(:ids)"), {"ids": chunk_ids})
            cleanup.execute(text("DELETE FROM ingestion_jobs WHERE source_version_id = ANY(:ids)"), {"ids": version_ids})
            cleanup.execute(text("DELETE FROM document_chunks WHERE source_version_id = ANY(:ids)"), {"ids": version_ids})
            cleanup.execute(text("DELETE FROM source_versions WHERE source_id = ANY(:ids)"), {"ids": source_ids})
            cleanup.execute(text("DELETE FROM sources WHERE id = ANY(:ids)"), {"ids": source_ids})
            cleanup.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": user_ids})
            cleanup.execute(text("DELETE FROM departments WHERE id = ANY(:ids)"), {"ids": department_ids})

    def _commit_seeded(self, count: int) -> list[dict]:
        documents = [self.seed_document() for _ in range(count)]
        self.transaction.commit()
        return documents

    def test_skip_locked_claims_distinct_jobs(self):
        documents = self._commit_seeded(2)
        try:
            with self.engine.begin() as setup:
                for index, document in enumerate(documents):
                    setup.execute(text(
                        "INSERT INTO ingestion_jobs "
                        "(id,source_version_id,job_type,status,attempt_count,max_attempts,available_at,created_by) "
                        "VALUES (:id,:version_id,'DOCUMENT_EMBEDDING','QUEUED',0,3,:available,:user_id)"
                    ), {
                        "id": uuid4(), "version_id": document["version_id"],
                        "available": datetime.now(timezone.utc) + timedelta(seconds=index),
                        "user_id": document["user_id"],
                    })
            first = self.engine.connect()
            second = self.engine.connect()
            first_tx = first.begin()
            second_tx = second.begin()
            try:
                claim = text(
                    "SELECT id FROM ingestion_jobs WHERE status='QUEUED' "
                    "ORDER BY available_at FOR UPDATE SKIP LOCKED LIMIT 1"
                )
                first_id = first.scalar(claim)
                second_id = second.scalar(claim)
                self.assertIsNotNone(first_id)
                self.assertIsNotNone(second_id)
                self.assertNotEqual(first_id, second_id)
            finally:
                first_tx.rollback()
                second_tx.rollback()
                first.close()
                second.close()
        finally:
            self._delete_seeded(documents)

    def test_lease_fencing_rejects_stale_owner(self):
        documents = self._commit_seeded(1)
        document = documents[0]
        job_id = uuid4()
        try:
            with self.engine.begin() as setup:
                setup.execute(text(
                    "INSERT INTO ingestion_jobs "
                    "(id,source_version_id,job_type,status,attempt_count,max_attempts,available_at,"
                    "lease_owner,lease_expires_at,heartbeat_at,created_by) VALUES "
                    "(:id,:version_id,'DOCUMENT_EMBEDDING','RUNNING',1,3,now(),"
                    "'worker-a',now()-interval '1 minute',now()-interval '2 minutes',:user_id)"
                ), {"id": job_id, "version_id": document["version_id"], "user_id": document["user_id"]})
            with self.engine.begin() as takeover:
                locked = takeover.scalar(text(
                    "SELECT id FROM ingestion_jobs WHERE id=:id AND lease_expires_at <= now() "
                    "FOR UPDATE SKIP LOCKED"
                ), {"id": job_id})
                self.assertEqual(locked, job_id)
                takeover.execute(text(
                    "UPDATE ingestion_jobs SET lease_owner='worker-b',lease_expires_at=now()+interval '5 minutes' "
                    "WHERE id=:id"
                ), {"id": job_id})
            with self.engine.begin() as fencing:
                stale = fencing.execute(text(
                    "UPDATE ingestion_jobs SET status='SUCCEEDED' WHERE id=:id AND status='RUNNING' "
                    "AND lease_owner='worker-a' AND lease_expires_at > now()"
                ), {"id": job_id})
                current = fencing.execute(text(
                    "UPDATE ingestion_jobs SET status='SUCCEEDED',lease_owner=NULL,lease_expires_at=NULL "
                    "WHERE id=:id AND status='RUNNING' AND lease_owner='worker-b' AND lease_expires_at > now()"
                ), {"id": job_id})
                self.assertEqual(stale.rowcount, 0)
                self.assertEqual(current.rowcount, 1)
        finally:
            self._delete_seeded(documents)

    def test_source_row_lock_serializes_version_numbers(self):
        documents = self._commit_seeded(1)
        document = documents[0]
        barrier = Barrier(2)

        def allocate(index: int) -> int:
            barrier.wait(timeout=10)
            with self.engine.begin() as connection:
                connection.execute(text("SELECT id FROM sources WHERE id=:id FOR UPDATE"), {"id": document["source_id"]})
                number = connection.scalar(text(
                    "SELECT coalesce(max(version_no),0)+1 FROM source_versions WHERE source_id=:id"
                ), {"id": document["source_id"]})
                connection.execute(text(
                    "INSERT INTO source_versions "
                    "(id,source_id,version_no,original_filename,mime_type,file_size,file_hash,storage_key,"
                    "processing_status,publication_status,is_current,uploaded_by) VALUES "
                    "(:id,:source_id,:number,:filename,'text/plain',1,:hash,:key,'PENDING','DRAFT',false,:user_id)"
                ), {
                    "id": uuid4(), "source_id": document["source_id"], "number": number,
                    "filename": f"concurrent-{index}.txt", "hash": str(index) * 64,
                    "key": f"gate/{uuid4().hex}", "user_id": document["user_id"],
                })
                return number

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(allocate, index) for index in (1, 2)]
                numbers = sorted(future.result(timeout=20) for future in futures)
            self.assertEqual(numbers, [2, 3])
        finally:
            self._delete_seeded(documents)

    def test_publication_and_chunk_replacement_roll_back_atomically(self):
        seeded = self.seed_document(content="old complete chunk")
        savepoint = self.connection.begin_nested()
        try:
            self.connection.execute(text(
                "UPDATE source_versions SET is_current=false,publication_status='SUPERSEDED' WHERE id=:id"
            ), {"id": seeded["version_id"]})
            self.connection.execute(text("DELETE FROM document_chunks WHERE source_version_id=:id"), {"id": seeded["version_id"]})
            with self.assertRaises(IntegrityError):
                self.connection.execute(text(
                    "INSERT INTO source_versions "
                    "(id,source_id,version_no,original_filename,mime_type,file_size,file_hash,storage_key,"
                    "processing_status,publication_status,is_current,uploaded_by) VALUES "
                    "(:id,:source_id,2,'bad.txt','text/plain',1,:hash,:key,'PENDING','DRAFT',true,:user_id)"
                ), {
                    "id": uuid4(), "source_id": seeded["source_id"], "hash": "b" * 64,
                    "key": f"gate/{uuid4().hex}", "user_id": seeded["user_id"],
                })
        finally:
            savepoint.rollback()
        state = self.connection.execute(text(
            "SELECT is_current,publication_status FROM source_versions WHERE id=:id"
        ), {"id": seeded["version_id"]}).one()
        chunks = self.connection.scalar(text(
            "SELECT count(*) FROM document_chunks WHERE source_version_id=:id AND content='old complete chunk'"
        ), {"id": seeded["version_id"]})
        self.assertEqual(tuple(state), (True, "PUBLISHED"))
        self.assertEqual(chunks, 1)
