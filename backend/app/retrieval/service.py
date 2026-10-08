from dataclasses import dataclass

from app.core.domain_types import RetrievalMode
from app.core.principal import Principal
from app.embeddings.base import EmbeddingError, EmbeddingProvider
from app.embeddings.repository import EmbeddingRepository
from app.permissions.service import PermissionService
from app.retrieval.fusion import deterministic_rerank, reciprocal_rank_fusion
from app.retrieval.repository import RetrievalRepository
from app.retrieval.types import FusedCandidate, RetrievalFilters


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    mode: RetrievalMode
    semantic_available: bool
    active_profile: object | None
    results: list[FusedCandidate]


class RetrievalService:
    def __init__(self, db, permissions: PermissionService, provider: EmbeddingProvider, settings):
        self.db = db
        self.permissions = permissions
        self.provider = provider
        self.settings = settings
        self.repository = RetrievalRepository(db)

    def search(self, principal: Principal, query: str, filters: RetrievalFilters, limit: int) -> RetrievalOutcome:
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty")
        if len(query) > self.settings.retrieval_max_query_chars:
            raise ValueError("Search query is too long")
        if limit < 1 or limit > self.settings.retrieval_max_result_limit:
            raise ValueError("Search result limit is outside the allowed range")
        candidate_limit = min(
            self.settings.retrieval_candidate_limit,
            self.settings.vector_candidate_limit,
        )
        fts = self.repository.fts(principal, self.permissions, query, filters, candidate_limit)
        profile = EmbeddingRepository(self.db).active_profile()
        semantic = []
        semantic_available = False
        if profile is not None:
            try:
                self.provider.ensure_profile_matches(profile)
                query_vector = self.provider.embed_query(query)
                semantic = self.repository.semantic(
                    principal, self.permissions, query_vector, profile, filters,
                    candidate_limit, mode=self.settings.vector_search_mode,
                    hnsw_ef_search=self.settings.vector_hnsw_ef_search,
                )
                semantic_available = True
            except EmbeddingError:
                semantic_available = False
        fused = reciprocal_rank_fusion(
            fts, semantic, fts_weight=self.settings.retrieval_fts_weight,
            vector_weight=self.settings.retrieval_vector_weight,
            rrf_k=self.settings.retrieval_rrf_k,
        )
        reranked = deterministic_rerank(fused, query, self.settings.retrieval_max_rerank_boost)[:limit]
        mode = RetrievalMode.HYBRID if fts and semantic else RetrievalMode.VECTOR_ONLY if semantic else RetrievalMode.FTS_ONLY
        return RetrievalOutcome(mode, semantic_available, profile, reranked)
