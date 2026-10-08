import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.domain_types import AccessLevel, ScopeType, SourceStatus, SourceType
from app.core.model_mixins import TimestampMixin


class Source(TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('DOCUMENT','EXPERT_NOTE','MANUAL_ATTESTATION')",
            name="ck_sources_source_type",
        ),
        CheckConstraint(
            "scope_type IN ('COMPANY','DEPARTMENT','PROJECT','PERSONAL_DRAFT')",
            name="ck_sources_scope_type",
        ),
        CheckConstraint(
            "access_level IN ('INTERNAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_sources_access_level",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','ARCHIVED')",
            name="ck_sources_status",
        ),
        CheckConstraint(
            "(scope_type = 'COMPANY' AND department_id IS NULL AND project_id IS NULL) OR "
            "(scope_type = 'DEPARTMENT' AND department_id IS NOT NULL AND project_id IS NULL) OR "
            "(scope_type = 'PERSONAL_DRAFT' AND owner_user_id IS NOT NULL AND project_id IS NULL) OR "
            "(scope_type = 'PROJECT' AND project_id IS NOT NULL)",
            name="ck_sources_scope_fields",
        ),
        Index("ix_sources_scope_status", "scope_type", "status"),
        Index("ix_sources_department", "department_id"),
        Index("ix_sources_owner", "owner_user_id"),
        Index("ix_sources_type", "source_type"),
        Index("ix_sources_business_scene", "business_scene"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SourceType.DOCUMENT.value
    )
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    access_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AccessLevel.INTERNAL.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SourceStatus.ACTIVE.value
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    department = relationship("Department", foreign_keys=[department_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    creator = relationship("User", foreign_keys=[created_by])
    versions = relationship(
        "SourceVersion", back_populates="source", order_by="SourceVersion.version_no"
    )
