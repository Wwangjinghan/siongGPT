from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.domain_types import (
    AccessLevel,
    ProcessingStatus,
    PublicationStatus,
    ScopeType,
    SourceStatus,
    SourceType,
)


class SourceCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    source_type: SourceType = SourceType.DOCUMENT
    business_scene: str | None = Field(default=None, max_length=100)
    scope_type: ScopeType
    department_id: UUID | None = None
    project_id: UUID | None = None
    owner_user_id: UUID | None = None
    access_level: AccessLevel = AccessLevel.INTERNAL


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    source_type: SourceType
    business_scene: str | None
    scope_type: ScopeType
    department_id: UUID | None
    project_id: UUID | None
    owner_user_id: UUID | None
    access_level: AccessLevel
    status: SourceStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class SourcePageResponse(BaseModel):
    items: list[SourceResponse]
    total: int
    page: int
    page_size: int


class SourceVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    version_no: int
    original_filename: str
    mime_type: str
    file_size: int
    file_hash: str
    processing_status: ProcessingStatus
    processing_error_code: str | None
    publication_status: PublicationStatus
    is_current: bool
    effective_from: datetime | None
    effective_to: datetime | None
    uploaded_by: UUID
    published_by: UUID | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
