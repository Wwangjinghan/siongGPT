from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievalFilters:
    scope_type: str | None = None
    department_id: UUID | None = None
    source_type: str | None = None
    business_scene: str | None = None
    mime_type: str | None = None
    effective_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    chunk_id: UUID
    source_id: UUID
    source_version_id: UUID
    source_title: str
    original_filename: str
    version_no: int
    content: str
    locator: dict
    section: str | None
    business_scene: str | None
    scope_type: str
    fts_rank: float | None = None
    semantic_similarity: float | None = None


@dataclass(slots=True)
class FusedCandidate:
    candidate: RetrievalCandidate
    fusion_score: float = 0.0
    matched_by: set[str] = field(default_factory=set)
    rerank_reasons: list[str] = field(default_factory=list)
