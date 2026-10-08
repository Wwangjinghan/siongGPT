import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models.embedding_profile import EmbeddingProfile
from app.models.embedding_profile import protect_embedding_profile_identity
from sqlalchemy.orm.attributes import set_committed_value


class Phase4MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (
            Path(__file__).parents[1]
            / "alembic" / "versions"
            / "f2a7c9d31b84_create_embeddings_and_vector_search.py"
        ).read_text(encoding="utf-8")

    def test_single_head_and_parent(self):
        self.assertIn('down_revision: Union[str, Sequence[str], None] = "e91c3b7d42a6"', self.text)
        self.assertEqual(ScriptDirectory.from_config(Config("alembic.ini")).get_heads(), ["f2a7c9d31b84"])

    def test_vector_profile_constraints_and_indexes_are_declared(self):
        for expected in (
            '"embedding_profiles"', '"document_chunk_embeddings"', "VECTOR(384)",
            "uq_embedding_profiles_one_active", "status = 'ACTIVE'",
            "uq_chunk_embeddings_chunk_profile", "ix_chunk_embeddings_hnsw_cosine",
            'postgresql_using="hnsw"', '"embedding": "vector_cosine_ops"',
            "fd1525a9fd15316a2d503bf26ab031a61d056e98",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.text)

    def test_profile_model_has_no_secret_or_local_path(self):
        columns = set(EmbeddingProfile.__table__.columns.keys())
        self.assertFalse(columns.intersection({"api_key", "token", "secret", "local_path"}))
        self.assertIn("model_revision", columns)

    def test_new_profile_defaults_inactive_and_identity_cannot_change_in_place(self):
        profile = EmbeddingProfile(
            provider_type="LOCAL_E5", model_name="model", model_revision="f" * 40,
            dimensions=384, distance_metric="cosine", normalized=True,
            query_prefix="query: ", passage_prefix="passage: ",
        )
        self.assertEqual(profile.status, None)
        set_committed_value(profile, "model_revision", "f" * 40)
        profile.model_revision = "e" * 40
        with self.assertRaises(ValueError):
            protect_embedding_profile_identity(None, None, profile)

    def test_downgrade_preserves_history_and_extension(self):
        downgrade = self.text.split("def downgrade()", 1)[1]
        self.assertNotIn('drop_table("document_chunks")', downgrade)
        self.assertNotIn('drop_table("source_versions")', downgrade)
        self.assertNotIn('drop_table("users")', downgrade)
        self.assertNotIn("DROP EXTENSION", downgrade)
