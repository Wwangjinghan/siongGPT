from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.principal import Principal, get_current_principal
from app.embeddings.factory import get_embedding_provider
from app.embeddings.repository import EmbeddingRepository
from app.permissions.service import PermissionService
from app.retrieval.service import RetrievalService
from app.retrieval.types import RetrievalFilters
from app.schemas.search import (
    ActiveEmbeddingProfileResponse,
    EmbeddingHealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
)


router = APIRouter(tags=["Search"])


def get_retrieval_service(db: Session = Depends(get_db)) -> RetrievalService:
    return RetrievalService(db, PermissionService(), get_embedding_provider(), settings)


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    _principal: Principal = Depends(get_current_principal),
    service: RetrievalService = Depends(get_retrieval_service),
):
    filters = RetrievalFilters(
        scope_type=request.filters.scope_type.value if request.filters.scope_type else None,
        department_id=request.filters.department_id,
        source_type=request.filters.source_type.value if request.filters.source_type else None,
        business_scene=request.filters.business_scene,
        mime_type=request.filters.mime_type,
        effective_at=request.filters.effective_at,
    )
    try:
        outcome = service.search(_principal, request.query, filters, request.limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = outcome.active_profile
    return SearchResponse(
        query=request.query,
        retrieval_mode=outcome.mode,
        semantic_available=outcome.semantic_available,
        active_embedding_profile=(
            ActiveEmbeddingProfileResponse(
                id=profile.id,
                model_name=profile.model_name,
                model_revision=profile.model_revision,
                dimensions=profile.dimensions,
            ) if profile else None
        ),
        results=[
            SearchResultResponse(
                chunk_id=item.candidate.chunk_id,
                source_id=item.candidate.source_id,
                source_version_id=item.candidate.source_version_id,
                source_title=item.candidate.source_title,
                original_filename=item.candidate.original_filename,
                version_no=item.candidate.version_no,
                content_snippet=item.candidate.content[: settings.retrieval_snippet_chars],
                locator=item.candidate.locator,
                business_scene=item.candidate.business_scene,
                scope_type=item.candidate.scope_type,
                matched_by=sorted(item.matched_by),
                fts_rank=item.candidate.fts_rank,
                semantic_similarity=item.candidate.semantic_similarity,
                fusion_score=item.fusion_score,
                rerank_reasons=item.rerank_reasons,
            ) for item in outcome.results
        ],
    )


@router.get("/health/embedding", response_model=EmbeddingHealthResponse)
def embedding_health(
    _principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    provider = get_embedding_provider()
    health = provider.health()
    profile = EmbeddingRepository(db).active_profile()
    return EmbeddingHealthResponse(
        configured=health.configured,
        available=health.available,
        provider_type=health.provider_type,
        model_name=health.model_name,
        revision=health.revision,
        dimensions=health.dimensions,
        active_profile_id=profile.id if profile else None,
        mode=health.mode,
        last_load_error_code=health.last_load_error_code,
    )
