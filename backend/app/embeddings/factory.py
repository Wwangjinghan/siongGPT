from functools import lru_cache

from app.core.config import settings
from app.embeddings.local_e5 import LocalE5Provider


@lru_cache(maxsize=1)
def get_embedding_provider() -> LocalE5Provider:
    if settings.embedding_provider != "local_e5":
        raise RuntimeError("Test embedding providers are not valid production configuration")
    return LocalE5Provider(
        model_name=settings.embedding_model_name,
        revision=settings.embedding_model_revision,
        local_path=settings.embedding_model_local_path,
        allow_download=settings.embedding_allow_download,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        max_sequence_length=settings.embedding_max_sequence_length,
    )
