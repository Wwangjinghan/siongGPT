import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.chunks.chunker import ChunkDraft
from app.core.domain_types import ProcessingStatus, PublicationStatus, ScopeType, SourceStatus
from app.core.principal import Principal
from app.models.document_chunk import DocumentChunk
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.permissions.service import PermissionService
from app.sources.services import SourceService


class DocumentChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def replace_for_version(self, source_version_id: UUID, drafts: list[ChunkDraft]) -> list[DocumentChunk]:
        self.db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.source_version_id == source_version_id
            )
        )
        chunks = [
                DocumentChunk(
                    source_version_id=source_version_id,
                    chunk_index=draft.chunk_index,
                    content=draft.content,
                    content_hash=draft.content_hash,
                    block_type=draft.block_type.value,
                    page=draft.page,
                    section=draft.section,
                    sheet=draft.sheet,
                    row_start=draft.row_start,
                    row_end=draft.row_end,
                    locator=draft.locator,
                    processing_metadata=draft.metadata,
                )
                for draft in drafts
            ]
        self.db.add_all(chunks)
        self.db.flush()
        return chunks

    def search_authorized(
        self,
        principal: Principal,
        permissions: PermissionService,
        query: str,
        *,
        limit: int = 20,
        prefix: bool = False,
    ):
        query = query.strip()
        if not query:
            return []
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        visibility = SourceService.visibility_expression(principal, permissions)
        if prefix:
            terms = re.findall(r"\w+", query, flags=re.UNICODE)
            if not terms:
                return []
            tsquery = func.to_tsquery("simple", " & ".join(f"{term}:*" for term in terms))
        else:
            tsquery = func.plainto_tsquery("simple", query)
        return list(
            self.db.execute(
                select(
                    DocumentChunk,
                    func.ts_rank(DocumentChunk.search_vector, tsquery).label("rank"),
                )
                .join(SourceVersion, SourceVersion.id == DocumentChunk.source_version_id)
                .join(Source, Source.id == SourceVersion.source_id)
                .where(
                    visibility,
                    Source.status == SourceStatus.ACTIVE.value,
                    Source.scope_type.in_([ScopeType.COMPANY.value, ScopeType.DEPARTMENT.value]),
                    SourceVersion.processing_status == ProcessingStatus.READY.value,
                    SourceVersion.publication_status == PublicationStatus.PUBLISHED.value,
                    SourceVersion.is_current.is_(True),
                    (SourceVersion.effective_from.is_(None) | (SourceVersion.effective_from <= datetime.now(timezone.utc))),
                    (SourceVersion.effective_to.is_(None) | (SourceVersion.effective_to >= datetime.now(timezone.utc))),
                    DocumentChunk.search_vector.op("@@")(tsquery),
                )
                .order_by(func.ts_rank(DocumentChunk.search_vector, tsquery).desc())
                .limit(limit)
            ).all()
        )
