import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


class PgvectorMigrationTests(unittest.TestCase):
    def test_upgrade_is_idempotent_and_downgrade_is_conservative(self):
        migration_path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "8b72f0a6c341_enable_pgvector_extension.py"
        )
        spec = importlib.util.spec_from_file_location("pgvector_migration", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with patch.object(migration.op, "execute") as execute:
            migration.upgrade()
        execute.assert_called_once_with("CREATE EXTENSION IF NOT EXISTS vector")

        migration.downgrade()
