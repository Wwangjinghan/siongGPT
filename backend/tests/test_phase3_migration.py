import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


class Phase3MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "e91c3b7d42a6_create_ingestion_and_chunks.py"
        )
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_revision_extends_phase2_and_is_the_only_head(self):
        self.assertIn('down_revision: Union[str, Sequence[str], None] = "c4f6a1d28e90"', self.text)
        script = ScriptDirectory.from_config(Config("alembic.ini"))
        self.assertEqual(len(script.get_heads()), 1)
        self.assertIn("e91c3b7d42a6", [revision.revision for revision in script.walk_revisions()])

    def test_migration_contains_jobs_chunks_fts_and_concurrency_guards(self):
        for expected in (
            '"ingestion_jobs"',
            '"document_chunks"',
            "uq_ingestion_jobs_active_version",
            "status IN ('QUEUED','RUNNING')",
            "ck_ingestion_jobs_running_lease",
            "uq_document_chunks_version_index",
            "to_tsvector('simple'::regconfig, content)",
            "postgresql_using=\"gin\"",
            'sa.ForeignKeyConstraint(["source_version_id"], ["source_versions.id"])',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.text)

    def test_downgrade_only_removes_phase3_objects(self):
        downgrade = self.text.split("def downgrade()", 1)[1]
        self.assertIn('drop_table("document_chunks")', downgrade)
        self.assertIn('drop_table("ingestion_jobs")', downgrade)
        self.assertNotIn('drop_table("source_versions")', downgrade)
        self.assertNotIn('drop_table("users")', downgrade)
        self.assertNotIn("DROP EXTENSION", downgrade)
