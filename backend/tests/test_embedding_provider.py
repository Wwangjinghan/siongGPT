import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.core.config import Settings
from app.core.domain_types import IngestionErrorCode
from app.embeddings.base import EmbeddingError
from app.embeddings.local_e5 import LocalE5Provider
from tests.embedding_fakes import FakeEmbeddingProvider


class EmbeddingProviderTests(unittest.TestCase):
    def test_prefixes_are_centralized_nonduplicating_and_ordered(self):
        provider = FakeEmbeddingProvider(
            lambda _text, index: [float(index + 1)] + [1.0] * 383
        )
        vectors = provider.embed_passages(["first", "passage: second"])
        provider.embed_query("question")
        provider.embed_query("query: existing")
        self.assertEqual(
            provider.seen,
            ["passage: first", "passage: second", "query: question", "query: existing"],
        )
        self.assertEqual(len(vectors), 2)
        self.assertNotEqual(vectors[0], vectors[1])
        self.assertTrue(all(math.isclose(sum(x * x for x in vector), 1.0) for vector in vectors))

    def test_invalid_dimensions_nan_infinity_and_zero_are_rejected(self):
        invalid = (
            [1.0] * 383,
            [math.nan] + [1.0] * 383,
            [math.inf] + [1.0] * 383,
            [0.0] * 384,
        )
        for vector in invalid:
            with self.subTest(first=vector[0]):
                provider = FakeEmbeddingProvider(lambda _text, _index, value=vector: value)
                with self.assertRaises(EmbeddingError) as raised:
                    provider.embed_query("test")
                self.assertEqual(raised.exception.code, IngestionErrorCode.EMBEDDING_INVALID_OUTPUT)

    def test_empty_input_is_rejected(self):
        provider = FakeEmbeddingProvider()
        for value in ("", "  "):
            with self.assertRaises(EmbeddingError):
                provider.embed_query(value)
        with self.assertRaises(EmbeddingError):
            provider.embed_passages([])

    def test_local_provider_is_unavailable_without_model_and_never_downloads(self):
        provider = LocalE5Provider(
            model_name="intfloat/multilingual-e5-small",
            revision="f" * 40,
            local_path="Z:/definitely/missing/model",
            allow_download=False,
            device="cpu",
            batch_size=2,
            max_sequence_length=512,
        )
        self.assertFalse(provider.health().available)
        with self.assertRaises(EmbeddingError) as raised:
            provider.embed_query("hello")
        self.assertEqual(raised.exception.code, IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE)

    def test_local_revision_marker_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, ".siong-model-revision").write_text("wrong", encoding="utf-8")
            provider = LocalE5Provider(
                model_name="intfloat/multilingual-e5-small",
                revision="f" * 40,
                local_path=temporary,
                allow_download=False,
                device="cpu",
                batch_size=2,
                max_sequence_length=512,
            )
            with self.assertRaises(EmbeddingError) as raised:
                provider.embed_query("hello")
            self.assertEqual(raised.exception.code, IngestionErrorCode.EMBEDDING_REVISION_MISMATCH)

    def test_local_load_pins_revision_and_rejects_silent_truncation(self):
        revision = "f" * 40
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, ".siong-model-revision").write_text(revision, encoding="utf-8")
            model = SimpleNamespace(
                max_seq_length=None,
                tokenizer=lambda texts, **_kwargs: {"input_ids": [[1] * 9 for _ in texts]},
                encode=Mock(return_value=[[1.0] + [0.0] * 383]),
            )
            provider = LocalE5Provider(
                model_name="intfloat/multilingual-e5-small", revision=revision,
                local_path=temporary, allow_download=False, device="cpu",
                batch_size=2, max_sequence_length=8,
            )
            with patch("sentence_transformers.SentenceTransformer", return_value=model) as constructor:
                with self.assertRaises(EmbeddingError) as raised:
                    provider.embed_query("too long")
            self.assertEqual(raised.exception.code, IngestionErrorCode.EMBEDDING_INPUT_TOO_LONG)
            self.assertEqual(model.max_seq_length, 8)
            self.assertEqual(constructor.call_args.kwargs["revision"], revision)
            self.assertTrue(constructor.call_args.kwargs["local_files_only"])

    def test_production_settings_reject_fake_provider(self):
        with self.assertRaises(ValidationError):
            Settings(
                database_url="postgresql+psycopg://example",
                jwt_secret="secret",
                embedding_provider="fake",
                _env_file=None,
            )
