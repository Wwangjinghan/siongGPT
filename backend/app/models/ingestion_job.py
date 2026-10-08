import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.domain_types import IngestionJobStatus, IngestionJobType
from app.core.model_mixins import TimestampMixin


class IngestionJob(TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('DOCUMENT_INGESTION','DOCUMENT_EMBEDDING')", name="ck_ingestion_jobs_type"
        ),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','DEAD_LETTER','CANCELLED')",
            name="ck_ingestion_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_count"),
        CheckConstraint("max_attempts > 0", name="ck_ingestion_jobs_max_attempts"),
        CheckConstraint(
            "attempt_count <= max_attempts", name="ck_ingestion_jobs_attempt_limit"
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR status <> 'RUNNING'",
            name="ck_ingestion_jobs_running_lease",
        ),
        Index(
            "uq_ingestion_jobs_active_version",
            "source_version_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED','RUNNING')"),
        ),
        Index("ix_ingestion_jobs_claim", "status", "available_at", "created_at"),
        Index("ix_ingestion_jobs_lease", "status", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_versions.id"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=IngestionJobType.DOCUMENT_INGESTION.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=IngestionJobStatus.QUEUED.value
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    source_version = relationship("SourceVersion", back_populates="ingestion_jobs")
    creator = relationship("User", foreign_keys=[created_by])
