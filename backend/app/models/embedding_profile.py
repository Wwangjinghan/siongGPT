import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, event, inspect, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.domain_types import EmbeddingProfileStatus
from app.core.model_mixins import TimestampMixin


class EmbeddingProfile(TimestampMixin, Base):
    __tablename__ = "embedding_profiles"
    __table_args__ = (
        CheckConstraint("provider_type IN ('LOCAL_E5')", name="ck_embedding_profiles_provider"),
        CheckConstraint("dimensions = 384", name="ck_embedding_profiles_dimensions"),
        CheckConstraint("distance_metric = 'cosine'", name="ck_embedding_profiles_metric"),
        CheckConstraint("normalized", name="ck_embedding_profiles_normalized"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_embedding_profiles_status"),
        Index(
            "uq_embedding_profiles_one_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, default=384)
    distance_metric: Mapped[str] = mapped_column(String(16), nullable=False, default="cosine")
    normalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    query_prefix: Mapped[str] = mapped_column(String(32), nullable=False, default="query: ")
    passage_prefix: Mapped[str] = mapped_column(String(32), nullable=False, default="passage: ")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EmbeddingProfileStatus.INACTIVE.value
    )

    chunk_embeddings = relationship("DocumentChunkEmbedding", back_populates="profile")


@event.listens_for(EmbeddingProfile, "before_update")
def protect_embedding_profile_identity(_mapper, _connection, target: EmbeddingProfile) -> None:
    state = inspect(target)
    immutable = (
        "provider_type", "model_name", "model_revision", "dimensions",
        "distance_metric", "normalized", "query_prefix", "passage_prefix",
    )
    if any(state.attrs[field].history.has_changes() for field in immutable):
        raise ValueError("Embedding profile identity is immutable; create a new profile")
