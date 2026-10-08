from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.domain_types import RetrievalMode, ScopeType, SourceType


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: ScopeType | None = None
    department_id: UUID | None = None
    source_type: SourceType | None = None
    business_scene: str | None = Field(default=None, max_length=100)
    mime_type: str | None = Field(default=None, max_length=255)
    effective_at: datetime | None = None


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class ActiveEmbeddingProfileResponse(BaseModel):
    id: UUID
    model_name: str
    model_revision: str
    dimensions: int


class SearchResultResponse(BaseModel):
    chunk_id: UUID
    source_id: UUID
    source_version_id: UUID
    source_title: str
    original_filename: str
    version_no: int
    content_snippet: str
    locator: dict
    business_scene: str | None
    scope_type: ScopeType
    matched_by: list[str]
    fts_rank: float | None
    semantic_similarity: float | None
    fusion_score: float
    rerank_reasons: list[str]


class SearchResponse(BaseModel):
    query: str
    retrieval_mode: RetrievalMode
    semantic_available: bool
    active_embedding_profile: ActiveEmbeddingProfileResponse | None
    results: list[SearchResultResponse]


class EmbeddingHealthResponse(BaseModel):
    configured: bool
    available: bool
    provider_type: str
    model_name: str
    revision: str
    dimensions: int
    active_profile_id: UUID | None
    mode: str
    last_load_error_code: str | None
