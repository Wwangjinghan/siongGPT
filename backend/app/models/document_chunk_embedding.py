import uuid

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.model_mixins import TimestampMixin


class DocumentChunkEmbedding(TimestampMixin, Base):
    __tablename__ = "document_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "embedding_profile_id", name="uq_chunk_embeddings_chunk_profile"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_chunk_embeddings_sha256"),
        Index("ix_chunk_embeddings_profile_chunk", "embedding_profile_id", "chunk_id"),
        Index(
            "ix_chunk_embeddings_hnsw_cosine",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=False
    )
    embedding_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("embedding_profiles.id"), nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(VECTOR(384), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    chunk = relationship("DocumentChunk", back_populates="embeddings")
    profile = relationship("EmbeddingProfile", back_populates="chunk_embeddings")
