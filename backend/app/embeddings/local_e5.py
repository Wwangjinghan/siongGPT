from pathlib import Path
from threading import Lock

from app.core.domain_types import EmbeddingProviderType, IngestionErrorCode
from app.embeddings.base import EmbeddingError, EmbeddingHealth, EmbeddingProfileSpec, EmbeddingProvider


class LocalE5Provider(EmbeddingProvider):
    """Lazy local-first E5 provider; importing it never loads model weights."""

    def __init__(self, *, model_name: str, revision: str, local_path: str, allow_download: bool, device: str, batch_size: int, max_sequence_length: int):
        super().__init__(EmbeddingProfileSpec(provider_type=EmbeddingProviderType.LOCAL_E5.value, model_name=model_name, model_revision=revision), batch_size)
        self.local_path = Path(local_path)
        self.allow_download = allow_download
        self.device = device
        self.max_sequence_length = max_sequence_length
        self._model = None
        self._load_lock = Lock()
        self._last_error_code = None

    def health(self) -> EmbeddingHealth:
        local_ready = self.local_path.is_dir() and self._local_revision_matches()
        return EmbeddingHealth(
            configured=True,
            available=self._model is not None or local_ready or self.allow_download,
            provider_type=self.profile().provider_type,
            model_name=self.profile().model_name,
            revision=self.profile().model_revision,
            dimensions=self.profile().dimensions,
            last_load_error_code=self._last_error_code,
        )

    def _encode(self, prefixed_texts: list[str]):
        model = self._load()
        self._reject_overlong(model, prefixed_texts)
        try:
            return model.encode(prefixed_texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        except Exception as exc:
            raise EmbeddingError(IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE, "Local embedding provider failed") from exc

    def _load(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            source = self.profile().model_name
            local_only = not self.allow_download
            if self.local_path.is_dir():
                if not self._local_revision_matches():
                    self._last_error_code = IngestionErrorCode.EMBEDDING_REVISION_MISMATCH.value
                    raise EmbeddingError(IngestionErrorCode.EMBEDDING_REVISION_MISMATCH, "Local model revision does not match the configured revision")
                source = str(self.local_path.resolve())
                local_only = True
            elif not self.allow_download:
                self._last_error_code = IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE.value
                raise EmbeddingError(IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE, "Local embedding model is unavailable")
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(source, revision=self.profile().model_revision, device=self.device, local_files_only=local_only)
                self._model.max_seq_length = self.max_sequence_length
                self._last_error_code = None
                return self._model
            except Exception as exc:
                self._last_error_code = IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE.value
                raise EmbeddingError(IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE, "Local embedding model could not be loaded") from exc

    def _local_revision_matches(self) -> bool:
        revision = self.profile().model_revision
        if revision in self.local_path.parts:
            return True
        for name in (".siong-model-revision", "model_revision.txt"):
            marker = self.local_path / name
            try:
                if marker.is_file() and marker.read_text(encoding="utf-8").strip() == revision:
                    return True
            except OSError:
                return False
        return False

    def _reject_overlong(self, model, texts: list[str]) -> None:
        try:
            encoded = model.tokenizer(texts, add_special_tokens=True, truncation=False)
            lengths = [len(ids) for ids in encoded["input_ids"]]
        except Exception as exc:
            raise EmbeddingError(IngestionErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE, "Embedding tokenizer failed") from exc
        if any(length > self.max_sequence_length for length in lengths):
            raise EmbeddingError(IngestionErrorCode.EMBEDDING_INPUT_TOO_LONG, "Chunk exceeds the configured embedding token limit")
