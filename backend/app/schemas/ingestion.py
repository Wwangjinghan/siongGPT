from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.domain_types import IngestionJobStatus, IngestionJobType


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_version_id: UUID
    job_type: IngestionJobType
    status: IngestionJobStatus
    attempt_count: int
    max_attempts: int
    available_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class IngestionJobActionResponse(BaseModel):
    job: IngestionJobResponse
    created_new: bool
