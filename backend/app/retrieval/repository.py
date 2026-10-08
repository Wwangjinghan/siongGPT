from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.domain_types import EmbeddingProfileStatus, ProcessingStatus, PublicationStatus, ScopeType, SourceStatus
from app.core.principal import Principal
from app.models.document_chunk import DocumentChunk
from app.models.document_chunk_embedding import DocumentChunkEmbedding
from app.models.embedding_profile import EmbeddingProfile
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.permissions.service import PermissionService
from app.retrieval.types import RetrievalCandidate, RetrievalFilters
from app.sources.services import SourceService


class RetrievalRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _filters(principal: Principal, permissions: PermissionService, filters: RetrievalFilters):
        effective_at = filters.effective_at or datetime.now().astimezone()
        clauses = [
            SourceService.visibility_expression(principal, permissions),
            Source.status == SourceStatus.ACTIVE.value,
            Source.scope_type.in_([ScopeType.COMPANY.value, ScopeType.DEPARTMENT.value]),
            SourceVersion.processing_status == ProcessingStatus.READY.value,
            SourceVersion.publication_status == PublicationStatus.PUBLISHED.value,
            SourceVersion.is_current.is_(True),
            or_(SourceVersion.effective_from.is_(None), SourceVersion.effective_from <= effective_at),
            or_(SourceVersion.effective_to.is_(None), SourceVersion.effective_to >= effective_at),
        ]
        if filters.scope_type:
            clauses.append(Source.scope_type == filters.scope_type)
        if filters.department_id:
            clauses.append(Source.department_id == filters.department_id)
        if filters.source_type:
            clauses.append(Source.source_type == filters.source_type)
        if filters.business_scene:
            clauses.append(Source.business_scene == filters.business_scene)
        if filters.mime_type:
            clauses.append(SourceVersion.mime_type == filters.mime_type)
        return clauses

    @staticmethod
    def _columns():
        return (
            DocumentChunk.id.label("chunk_id"), Source.id.label("source_id"),
            SourceVersion.id.label("source_version_id"), Source.title.label("source_title"),
            SourceVersion.original_filename, SourceVersion.version_no, DocumentChunk.content,
            DocumentChunk.locator, DocumentChunk.section, Source.business_scene, Source.scope_type,
        )

    @staticmethod
    def _candidate(row, *, fts_rank=None, semantic_similarity=None):
        return RetrievalCandidate(
            chunk_id=row.chunk_id, source_id=row.source_id, source_version_id=row.source_version_id,
            source_title=row.source_title, original_filename=row.original_filename,
            version_no=row.version_no, content=row.content, locator=row.locator,
            section=row.section, business_scene=row.business_scene, scope_type=row.scope_type,
            fts_rank=fts_rank, semantic_similarity=semantic_similarity,
        )

    def fts(self, principal: Principal, permissions: PermissionService, query: str, filters: RetrievalFilters, limit: int) -> list[RetrievalCandidate]:
        tsquery = func.plainto_tsquery("simple", query)
        rank = func.ts_rank(DocumentChunk.search_vector, tsquery)
        statement = (
            select(*self._columns(), rank.label("score"))
            .join(SourceVersion, SourceVersion.id == DocumentChunk.source_version_id)
            .join(Source, Source.id == SourceVersion.source_id)
            .where(*self._filters(principal, permissions, filters), DocumentChunk.search_vector.op("@@")(tsquery))
            .order_by(rank.desc(), DocumentChunk.id)
            .limit(limit)
        )
        return [self._candidate(row, fts_rank=float(row.score)) for row in self.db.execute(statement).all()]

    def semantic(self, principal: Principal, permissions: PermissionService, query_vector: list[float], profile: EmbeddingProfile, filters: RetrievalFilters, limit: int, *, mode: str, hnsw_ef_search: int) -> list[RetrievalCandidate]:
        if mode == "hnsw":
            self.db.execute(select(
                func.set_config("enable_indexscan", "on", True),
                func.set_config("enable_bitmapscan", "on", True),
                func.set_config("hnsw.ef_search", str(hnsw_ef_search), True),
            ))
        else:
            self.db.execute(select(
                func.set_config("enable_indexscan", "off", True),
                func.set_config("enable_bitmapscan", "off", True),
            ))
        missing_chunk = aliased(DocumentChunk)
        matching_embedding = aliased(DocumentChunkEmbedding)
        incomplete = exists(
            select(1).select_from(missing_chunk).where(
                missing_chunk.source_version_id == SourceVersion.id,
                ~exists(select(1).select_from(matching_embedding).where(
                    matching_embedding.chunk_id == missing_chunk.id,
                    matching_embedding.embedding_profile_id == profile.id,
                    matching_embedding.content_hash == missing_chunk.content_hash,
                )),
            )
        )
        distance = DocumentChunkEmbedding.embedding.cosine_distance(query_vector)
        similarity = (1.0 - distance).label("score")
        statement = (
            select(*self._columns(), similarity)
            .join(DocumentChunkEmbedding, DocumentChunkEmbedding.chunk_id == DocumentChunk.id)
            .join(EmbeddingProfile, EmbeddingProfile.id == DocumentChunkEmbedding.embedding_profile_id)
            .join(SourceVersion, SourceVersion.id == DocumentChunk.source_version_id)
            .join(Source, Source.id == SourceVersion.source_id)
            .where(
                *self._filters(principal, permissions, filters),
                EmbeddingProfile.id == profile.id,
                EmbeddingProfile.status == EmbeddingProfileStatus.ACTIVE.value,
                DocumentChunkEmbedding.content_hash == DocumentChunk.content_hash,
                ~incomplete,
            )
            .order_by(distance, DocumentChunk.id)
            .limit(limit)
        )
        return [self._candidate(row, semantic_similarity=float(row.score)) for row in self.db.execute(statement).all()]
