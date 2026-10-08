import unittest
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects.postgresql import dialect

from app.chunks.repository import DocumentChunkRepository
from app.core.principal import Principal
from app.permissions.service import PermissionService


class CaptureSession:
    def __init__(self):
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(all=lambda: [])


class ChunkRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.session = CaptureSession()
        self.repository = DocumentChunkRepository(self.session)
        self.principal = Principal(
            uuid4(), uuid4(), frozenset({"EMPLOYEE"}), True, True
        )

    def test_fts_query_joins_source_and_filters_current_published_ready(self):
        self.repository.search_authorized(
            self.principal, PermissionService(), "expense policy", prefix=False
        )
        compiled = self.session.statement.compile(dialect=dialect())
        sql = str(compiled)
        self.assertIn("JOIN source_versions", sql)
        self.assertIn("JOIN sources", sql)
        self.assertIn("source_versions.processing_status =", sql)
        self.assertIn("source_versions.publication_status =", sql)
        self.assertIn("READY", compiled.params.values())
        self.assertIn("PUBLISHED", compiled.params.values())
        self.assertIn("source_versions.is_current IS true", sql)
        self.assertIn("plainto_tsquery", sql)
        self.assertIn("sources.department_id", sql)
        self.assertIn("sources.owner_user_id", sql)

    def test_prefix_query_is_explicit_and_empty_query_does_not_hit_database(self):
        self.repository.search_authorized(
            self.principal, PermissionService(), "reimburse policy", prefix=True
        )
        compiled = self.session.statement.compile(dialect=dialect())
        sql = str(compiled)
        self.assertIn("to_tsquery", sql)
        self.assertIn("reimburse:* & policy:*", compiled.params.values())

        self.session.statement = None
        self.assertEqual(
            self.repository.search_authorized(
                self.principal, PermissionService(), "   "
            ),
            [],
        )
        self.assertIsNone(self.session.statement)

    def test_search_limit_is_bounded(self):
        for limit in (0, 101):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.repository.search_authorized(
                    self.principal, PermissionService(), "policy", limit=limit
                )
