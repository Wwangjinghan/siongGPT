from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api.v1.sources import get_storage
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.embeddings.factory import get_embedding_provider
from app.main import app
from app.storage.local import LocalStorageAdapter
from app.workers.ingestion import IngestionWorker
from tests.integration.postgres.base import PostgresGateCase
from tests.test_parsers import docx_fixture, native_text_pdf, xlsx_fixture


class VerticalSliceGateTests(PostgresGateCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.original_storage_root = settings.source_storage_root
        settings.source_storage_root = str(Path(self.temporary.name) / "source-storage")
        get_storage.cache_clear()
        get_embedding_provider.cache_clear()
        self.storage = LocalStorageAdapter(settings.source_storage_root)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

        def integration_db():
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = integration_db
        self.clients = []
        self.identities = self._seed_identities()

    def tearDown(self):
        for client in self.clients:
            client.close()
        app.dependency_overrides.clear()
        get_storage.cache_clear()
        get_embedding_provider.cache_clear()
        settings.source_storage_root = self.original_storage_root
        self.temporary.cleanup()

    def _seed_identities(self):
        suffix = uuid4().hex[:10]
        department_a, department_b = uuid4(), uuid4()
        roles = {
            code: uuid4()
            for code in ("SYSTEM_ADMIN", "DEPARTMENT_ADMIN", "EMPLOYEE", "UNKNOWN_ROLE")
        }
        password = "Gate-" + uuid4().hex
        identities = {}
        definitions = (
            ("system", "SYSTEM_ADMIN", None),
            ("admin", "DEPARTMENT_ADMIN", department_a),
            ("user", "EMPLOYEE", department_a),
            ("other", "EMPLOYEE", department_b),
            ("unknown", "UNKNOWN_ROLE", department_a),
        )
        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO departments (id,code,name) VALUES "
                "(:a,:code_a,:name_a),(:b,:code_b,:name_b)"
            ), {
                "a": department_a, "b": department_b,
                "code_a": f"GA{suffix}", "code_b": f"GB{suffix}",
                "name_a": f"Gate A {suffix}", "name_b": f"Gate B {suffix}",
            })
            for code, role_id in roles.items():
                connection.execute(
                    text("INSERT INTO roles (id,code,name) VALUES (:id,:code,:name)"),
                    {"id": role_id, "code": code, "name": code},
                )
            password_hash = hash_password(password)
            for label, role_code, department_id in definitions:
                user_id = uuid4()
                email = f"gate-{label}-{suffix}@invalid.example"
                connection.execute(text(
                    "INSERT INTO users (id,email,password_hash,display_name,status,department_id) "
                    "VALUES (:id,:email,:password_hash,:display_name,'ACTIVE',:department_id)"
                ), {
                    "id": user_id, "email": email, "password_hash": password_hash,
                    "display_name": f"Gate {label}", "department_id": department_id,
                })
                connection.execute(text(
                    "INSERT INTO user_roles (user_id,role_id) VALUES (:user_id,:role_id)"
                ), {"user_id": user_id, "role_id": roles[role_code]})
                identities[label] = {
                    "id": user_id, "email": email, "password": password,
                    "department_id": department_id,
                }
        identities["department_a"] = department_a
        return identities

    def _login(self, label: str) -> TestClient:
        identity = self.identities[label]
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": identity["email"], "password": identity["password"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.get("/api/v1/auth/me").status_code, 200)
        self.clients.append(client)
        return client

    def _create_department_source(self, client: TestClient, title: str) -> str:
        response = client.post("/api/v1/sources", json={
            "title": title,
            "source_type": "DOCUMENT",
            "scope_type": "DEPARTMENT",
            "department_id": str(self.identities["department_a"]),
            "access_level": "INTERNAL",
            "business_scene": "integration-gate",
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _upload_and_process(self, client: TestClient, source_id: str, filename: str, mime: str, payload: bytes) -> str:
        uploaded = client.post(
            f"/api/v1/sources/{source_id}/versions",
            files={"file": (filename, payload, mime)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        version_id = uploaded.json()["id"]
        queued = client.post(f"/api/v1/source-versions/{version_id}/process")
        self.assertEqual(queued.status_code, 202, queued.text)
        worker = IngestionWorker(
            session_factory=self.session_factory,
            storage=self.storage,
            embedding_provider=get_embedding_provider(),
            worker_id="phase45-e2e-worker",
        )
        self.assertTrue(worker.run_once())
        version = client.get(f"/api/v1/source-versions/{version_id}")
        self.assertEqual(version.status_code, 200, version.text)
        self.assertEqual(version.json()["processing_status"], "READY")
        self.assertEqual(version.json()["publication_status"], "DRAFT")
        self.assertFalse(version.json()["is_current"])
        return version_id

    @staticmethod
    def _bytes(stream) -> bytes:
        stream.seek(0)
        return stream.read()

    def test_login_upload_real_ingestion_publish_search_and_role_matrix(self):
        system = self._login("system")
        admin = self._login("admin")
        user = self._login("user")
        other = self._login("other")
        unknown = self._login("unknown")

        source_id = self._create_department_source(admin, "Gate reimbursement policy")
        self.assertEqual(system.get(f"/api/v1/sources/{source_id}").status_code, 200)
        self.assertEqual(user.get(f"/api/v1/sources/{source_id}").status_code, 200)
        self.assertEqual(other.get(f"/api/v1/sources/{source_id}").status_code, 404)
        self.assertEqual(unknown.get(f"/api/v1/sources/{source_id}").status_code, 404)
        user_department_create = user.post("/api/v1/sources", json={
            "title": "Forbidden formal source",
            "source_type": "DOCUMENT",
            "scope_type": "DEPARTMENT",
            "department_id": str(self.identities["department_a"]),
            "access_level": "INTERNAL",
        })
        self.assertEqual(user_department_create.status_code, 403)
        first_version = self._upload_and_process(
            admin,
            source_id,
            "reimbursement.txt",
            "text/plain",
            b"GATE-OLD reimbursement requires PO, DO, receipt, and approval.",
        )
        before_publish = user.post("/api/v1/search", json={"query": "GATE-OLD", "limit": 10})
        self.assertEqual(before_publish.status_code, 200)
        self.assertEqual(before_publish.json()["results"], [])
        self.assertIn(user.post(f"/api/v1/source-versions/{first_version}/publish").status_code, (403, 404))
        published = admin.post(f"/api/v1/source-versions/{first_version}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        self.assertTrue(published.json()["is_current"])

        for client in (system, admin, user):
            response = client.post("/api/v1/search", json={"query": "GATE-OLD reimbursement", "limit": 10})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(any(item["source_id"] == source_id for item in response.json()["results"]))
            rendered = response.text.lower()
            self.assertNotIn("storage_key", rendered)
            self.assertNotIn('"embedding"', rendered)
            self.assertNotIn(str(Path(self.temporary.name)).lower(), rendered)

        for client in (other, unknown):
            response = client.post("/api/v1/search", json={"query": "GATE-OLD reimbursement", "limit": 10})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(any(item["source_id"] == source_id for item in response.json()["results"]))

        second_version = self._upload_and_process(
            admin,
            source_id,
            "reimbursement-v2.txt",
            "text/plain",
            b"GATE-NEW reimbursement now requires PO, DO, tax invoice, receipt, and approval.",
        )
        self.assertEqual(admin.post(f"/api/v1/source-versions/{second_version}/publish").status_code, 200)
        old_search = user.post("/api/v1/search", json={"query": "GATE-OLD", "limit": 10})
        self.assertFalse(any(item["source_version_id"] == first_version for item in old_search.json()["results"]))

        fixtures = (
            ("Gate PDF", "policy.pdf", "application/pdf", self._bytes(native_text_pdf("GATE-PDF PO policy"))),
            ("Gate DOCX", "policy.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", self._bytes(docx_fixture())),
            ("Gate XLSX", "codes.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", self._bytes(xlsx_fixture())),
        )
        for title, filename, mime, payload in fixtures:
            format_source = self._create_department_source(admin, title)
            self._upload_and_process(admin, format_source, filename, mime, payload)

        personal = user.post("/api/v1/sources", json={
            "title": "Gate personal draft",
            "scope_type": "PERSONAL_DRAFT",
            "source_type": "DOCUMENT",
            "access_level": "INTERNAL",
        })
        self.assertEqual(personal.status_code, 201, personal.text)
        self.assertEqual(other.get(f"/api/v1/sources/{personal.json()['id']}").status_code, 404)
        unknown_personal = unknown.post("/api/v1/sources", json={
            "title": "Forbidden unknown draft",
            "scope_type": "PERSONAL_DRAFT",
            "source_type": "DOCUMENT",
            "access_level": "INTERNAL",
        })
        self.assertEqual(unknown_personal.status_code, 403)
        personal_version = self._upload_and_process(
            user, personal.json()["id"], "personal.txt", "text/plain", b"GATE-PERSONAL private draft"
        )
        self.assertIn(user.post(f"/api/v1/source-versions/{personal_version}/publish").status_code, (403, 404))
        personal_search = user.post("/api/v1/search", json={"query": "GATE-PERSONAL", "limit": 10})
        self.assertEqual(personal_search.json()["results"], [])

        project = system.post("/api/v1/sources", json={
            "title": "Gate project source",
            "scope_type": "PROJECT",
            "source_type": "DOCUMENT",
            "project_id": str(uuid4()),
            "access_level": "INTERNAL",
        })
        self.assertIn(project.status_code, (403, 404))

        withdrawn = admin.post(f"/api/v1/source-versions/{second_version}/withdraw")
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        after_withdraw = user.post("/api/v1/search", json={"query": "GATE-NEW", "limit": 10})
        self.assertEqual(after_withdraw.json()["results"], [])
