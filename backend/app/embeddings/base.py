import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.domain_types import IngestionErrorCode


@dataclass(frozen=True, slots=True)
class EmbeddingProfileSpec:
    provider_type: str
    model_name: str
    model_revision: str
    dimensions: int = 384
    distance_metric: str = "cosine"
    normalized: bool = True
    query_prefix: str = "query: "
    passage_prefix: str = "passage: "


@dataclass(frozen=True, slots=True)
class EmbeddingHealth:
    configured: bool
    available: bool
    provider_type: str
    model_name: str
    revision: str
    dimensions: int
    mode: str = "local"
    last_load_error_code: str | None = None


class EmbeddingError(Exception):
    def __init__(self, code: IngestionErrorCode, safe_message: str):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class EmbeddingProvider(ABC):
    def __init__(self, profile: EmbeddingProfileSpec, batch_size: int):
        self._profile = profile
        self.batch_size = batch_size

    def profile(self) -> EmbeddingProfileSpec:
        return self._profile

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        prepared = self._prepare(texts, self._profile.passage_prefix)
        return self._validate(self._encode(prepared), len(prepared))

    def embed_query(self, text: str) -> list[float]:
        prepared = self._prepare([text], self._profile.query_prefix)
        return self._validate(self._encode(prepared), 1)[0]

    def ensure_profile_matches(self, profile) -> None:
        expected = self.profile()
        fields = (
            "provider_type", "model_name", "model_revision", "dimensions",
            "distance_metric", "normalized", "query_prefix", "passage_prefix",
        )
        if any(getattr(profile, field) != getattr(expected, field) for field in fields):
            raise EmbeddingError(
                IngestionErrorCode.EMBEDDING_REVISION_MISMATCH,
                "Active embedding profile does not match the configured provider",
            )

    @abstractmethod
    def _encode(self, prefixed_texts: list[str]): ...

    @abstractmethod
    def health(self) -> EmbeddingHealth: ...

    @staticmethod
    def _prepare(texts: list[str], prefix: str) -> list[str]:
        if not texts:
            raise EmbeddingError(IngestionErrorCode.EMBEDDING_INVALID_OUTPUT, "Embedding input must not be empty")
        prepared = []
        for text in texts:
            value = text.strip() if isinstance(text, str) else ""
            if not value:
                raise EmbeddingError(IngestionErrorCode.EMBEDDING_INVALID_OUTPUT, "Embedding text must not be empty")
            prepared.append(value if value.startswith(prefix) else prefix + value)
        return prepared

    def _validate(self, raw_vectors, expected_count: int) -> list[list[float]]:
        vectors = list(raw_vectors)
        if len(vectors) != expected_count:
            raise EmbeddingError(IngestionErrorCode.EMBEDDING_INVALID_OUTPUT, "Embedding provider returned an unexpected vector count")
        normalized = []
        for raw in vectors:
            vector = [float(value) for value in raw]
            if len(vector) != self._profile.dimensions or not all(map(math.isfinite, vector)):
                raise EmbeddingError(IngestionErrorCode.EMBEDDING_INVALID_OUTPUT, "Embedding provider returned an invalid vector")
            norm = math.sqrt(sum(value * value for value in vector))
            if not math.isfinite(norm) or norm <= 0:
                raise EmbeddingError(IngestionErrorCode.EMBEDDING_INVALID_OUTPUT, "Embedding provider returned a zero or invalid vector")
            normalized.append([value / norm for value in vector])
        return normalized
