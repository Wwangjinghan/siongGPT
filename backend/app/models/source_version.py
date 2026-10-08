import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.domain_types import ProcessingStatus, PublicationStatus
from app.core.model_mixins import TimestampMixin


class SourceVersion(TimestampMixin, Base):
    __tablename__ = "source_versions"
    __table_args__ = (
        UniqueConstraint("source_id", "version_no", name="uq_source_versions_number"),
        UniqueConstraint("source_id", "file_hash", name="uq_source_versions_hash"),
        CheckConstraint("version_no > 0", name="ck_source_versions_positive_version"),
        CheckConstraint("file_size > 0", name="ck_source_versions_positive_size"),
        CheckConstraint(
            "file_hash ~ '^[0-9a-f]{64}$'", name="ck_source_versions_sha256"
        ),
        CheckConstraint(
            "processing_status IN ('PENDING','PROCESSING','READY','FAILED')",
            name="ck_source_versions_processing_status",
        ),
        CheckConstraint(
            "publication_status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN','ARCHIVED')",
            name="ck_source_versions_publication_status",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_source_versions_effective_range",
        ),
        CheckConstraint(
            "NOT is_current OR (processing_status = 'READY' AND publication_status = 'PUBLISHED')",
            name="ck_source_versions_current_published_ready",
        ),
        CheckConstraint(
            "(publication_status IN ('PUBLISHED','SUPERSEDED','WITHDRAWN') "
            "AND published_by IS NOT NULL AND published_at IS NOT NULL) OR "
            "publication_status IN ('DRAFT','ARCHIVED')",
            name="ck_source_versions_publication_actor",
        ),
        Index(
            "uq_source_versions_one_current",
            "source_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_source_versions_source_number", "source_id", "version_no"),
        Index("ix_source_versions_file_hash", "file_hash"),
        Index(
            "ix_source_versions_states", "publication_status", "processing_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProcessingStatus.PENDING.value
    )
    processing_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    publication_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PublicationStatus.DRAFT.value
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    source = relationship("Source", back_populates="versions")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    publisher = relationship("User", foreign_keys=[published_by])
    ingestion_jobs = relationship(
        "IngestionJob", back_populates="source_version", order_by="IngestionJob.created_at"
    )
    document_chunks = relationship(
        "DocumentChunk",
        back_populates="source_version",
        order_by="DocumentChunk.chunk_index",
    )
