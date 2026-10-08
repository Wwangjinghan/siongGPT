import unittest
from pathlib import Path


class SourceMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "c4f6a1d28e90_create_source_registry.py"
        ).read_text(encoding="utf-8")

    def test_revision_has_current_head_as_parent(self):
        self.assertIn('down_revision: Union[str, Sequence[str], None] = "8b72f0a6c341"', self.text)

    def test_migration_contains_critical_constraints_and_indexes(self):
        for expected in (
            '"sources"',
            '"source_versions"',
            "uq_source_versions_hash",
            "uq_source_versions_number",
            "uq_source_versions_one_current",
            'postgresql_where=sa.text("is_current")',
            "ck_sources_scope_fields",
            "ck_source_versions_current_published_ready",
            "ix_source_versions_states",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.text)

    def test_downgrade_does_not_touch_auth_or_pgvector(self):
        downgrade = self.text.split("def downgrade()", 1)[1]
        self.assertNotIn('drop_table("users")', downgrade)
        self.assertNotIn("DROP EXTENSION", downgrade)
