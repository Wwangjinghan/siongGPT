import uuid

from sqlalchemy import CheckConstraint, Computed, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.model_mixins import TimestampMixin


class DocumentChunk(TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id", "chunk_index", name="uq_document_chunks_version_index"
        ),
        CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index"),
        CheckConstraint("length(btrim(content)) > 0", name="ck_document_chunks_content"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_document_chunks_sha256"
        ),
        CheckConstraint("page IS NULL OR page > 0", name="ck_document_chunks_page"),
        CheckConstraint(
            "row_start IS NULL OR row_start > 0", name="ck_document_chunks_row_start"
        ),
        CheckConstraint(
            "row_end IS NULL OR row_end > 0", name="ck_document_chunks_row_end"
        ),
        CheckConstraint(
            "row_end IS NULL OR row_start IS NULL OR row_end >= row_start",
            name="ck_document_chunks_row_range",
        ),
        CheckConstraint(
            "block_type IN ('PARAGRAPH','HEADING','TABLE','SPREADSHEET_ROWS')",
            name="ck_document_chunks_block_type",
        ),
        Index("ix_document_chunks_version", "source_version_id", "chunk_index"),
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_versions.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    processing_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, content)", persisted=True),
        nullable=False,
    )

    source_version = relationship("SourceVersion", back_populates="document_chunks")
    embeddings = relationship("DocumentChunkEmbedding", back_populates="chunk")
