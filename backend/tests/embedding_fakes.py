from app.core.domain_types import EmbeddingProviderType
from app.embeddings.base import EmbeddingHealth, EmbeddingProfileSpec, EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """Test-only data-flow double. It makes no semantic quality claim."""

    def __init__(self, encoder=None, *, available=True):
        super().__init__(
            EmbeddingProfileSpec(
                provider_type=EmbeddingProviderType.LOCAL_E5.value,
                model_name="intfloat/multilingual-e5-small",
                model_revision="fd1525a9fd15316a2d503bf26ab031a61d056e98",
            ),
            batch_size=2,
        )
        self.encoder = encoder or (lambda _text, _index: [1.0] + [0.0] * 383)
        self.available = available
        self.seen = []

    def _encode(self, prefixed_texts):
        self.seen.extend(prefixed_texts)
        return [self.encoder(text, index) for index, text in enumerate(prefixed_texts)]

    def health(self):
        spec = self.profile()
        return EmbeddingHealth(
            configured=True,
            available=self.available,
            provider_type=spec.provider_type,
            model_name=spec.model_name,
            revision=spec.model_revision,
            dimensions=spec.dimensions,
        )
