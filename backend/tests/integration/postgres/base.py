from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from scripts.integration_gate_support import allowed_ci_hosts_from_environment, require_protected_test_database
from scripts.integration_gate_support import BASELINE_DATABASE_ENV, IntegrationGateSafetyError


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
ONLINE_ENABLED = bool(TEST_DATABASE_URL and os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS") == "true")


@unittest.skipUnless(
    ONLINE_ENABLED,
    "requires protected PostgreSQL TEST_DATABASE_URL and ALLOW_DESTRUCTIVE_DB_TESTS=true",
)
class PostgresGateCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        baseline = os.getenv(BASELINE_DATABASE_ENV)
        if not baseline:
            raise IntegrationGateSafetyError(
                "Baseline development database identity was not propagated to online tests"
            )
        protected = require_protected_test_database(
            TEST_DATABASE_URL,
            allow_destructive=os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS"),
            development_url=baseline,
            allowed_ci_hosts=allowed_ci_hosts_from_environment(),
        )
        cls.engine = create_engine(protected.url.render_as_string(hide_password=False), pool_pre_ping=True)
        with cls.engine.connect() as connection:
            actual = connection.scalar(text("SELECT current_database()"))
        if actual != protected.database:
            cls.engine.dispose()
            raise RuntimeError("Connected database identity does not match protected target")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()

    def tearDown(self):
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def seed_document(self, *, content: str = "PO DO GST PRJ-001", content_hash: str = "c" * 64):
        department_id, user_id, source_id, version_id, chunk_id = (uuid4() for _ in range(5))
        suffix = uuid4().hex[:10]
        self.connection.execute(
            text("INSERT INTO departments (id, code, name) VALUES (:id, :code, :name)"),
            {"id": department_id, "code": f"G{suffix}", "name": f"Gate {suffix}"},
        )
        self.connection.execute(
            text(
                "INSERT INTO users (id,email,password_hash,display_name,status,department_id) "
                "VALUES (:id,:email,'not-a-login-hash','Gate User','ACTIVE',:department_id)"
            ),
            {"id": user_id, "email": f"gate-{suffix}@invalid.example", "department_id": department_id},
        )
        self.connection.execute(
            text(
                "INSERT INTO sources (id,title,source_type,scope_type,department_id,access_level,status,created_by) "
                "VALUES (:id,'Gate document','DOCUMENT','DEPARTMENT',:department_id,'INTERNAL','ACTIVE',:user_id)"
            ),
            {"id": source_id, "department_id": department_id, "user_id": user_id},
        )
        self.connection.execute(
            text(
                "INSERT INTO source_versions "
                "(id,source_id,version_no,original_filename,mime_type,file_size,file_hash,storage_key,"
                "processing_status,publication_status,is_current,uploaded_by,published_by,published_at) "
                "VALUES (:id,:source_id,1,'gate.txt','text/plain',10,:file_hash,:storage_key,"
                "'READY','PUBLISHED',true,:user_id,:user_id,:published_at)"
            ),
            {
                "id": version_id, "source_id": source_id, "file_hash": uuid4().hex * 2,
                "storage_key": f"gate/{uuid4().hex}", "user_id": user_id,
                "published_at": datetime.now(timezone.utc),
            },
        )
        self.connection.execute(
            text(
                "INSERT INTO document_chunks "
                "(id,source_version_id,chunk_index,content,content_hash,block_type,locator,metadata) "
                "VALUES (:id,:version_id,0,:content,:content_hash,'PARAGRAPH',"
                "CAST('{\"line_start\":1}' AS jsonb),CAST('{}' AS jsonb))"
            ),
            {"id": chunk_id, "version_id": version_id, "content": content, "content_hash": content_hash},
        )
        return {
            "department_id": department_id, "user_id": user_id, "source_id": source_id,
            "version_id": version_id, "chunk_id": chunk_id, "content_hash": content_hash,
        }
