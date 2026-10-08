from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.domain_types import EmbeddingProfileStatus
from app.models.document_chunk import DocumentChunk
from app.models.document_chunk_embedding import DocumentChunkEmbedding
from app.models.embedding_profile import EmbeddingProfile


class EmbeddingRepository:
    def __init__(self, db: Session):
        self.db = db

    def active_profile(self) -> EmbeddingProfile | None:
        return self.db.scalar(
            select(EmbeddingProfile).where(
                EmbeddingProfile.status == EmbeddingProfileStatus.ACTIVE.value
            )
        )

    def add_for_chunks(
        self,
        chunks: list[DocumentChunk],
        profile: EmbeddingProfile,
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and embedding counts differ")
        self.db.add_all(
            [
                DocumentChunkEmbedding(
                    chunk_id=chunk.id,
                    embedding_profile_id=profile.id,
                    embedding=vector,
                    content_hash=chunk.content_hash,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        self.db.flush()

    def upsert_batch(
        self,
        chunks: list[DocumentChunk],
        profile: EmbeddingProfile,
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and embedding counts differ")
        if not chunks:
            return
        rows = [
            {
                "chunk_id": chunk.id,
                "embedding_profile_id": profile.id,
                "embedding": vector,
                "content_hash": chunk.content_hash,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        statement = insert(DocumentChunkEmbedding).values(rows)
        statement = statement.on_conflict_do_update(
            constraint="uq_chunk_embeddings_chunk_profile",
            set_={
                "embedding": statement.excluded.embedding,
                "content_hash": statement.excluded.content_hash,
                "updated_at": func.now(),
            },
        )
        self.db.execute(statement)

    def version_is_complete(self, version_id: UUID, profile_id: UUID) -> bool:
        chunk_count = self.db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.source_version_id == version_id
            )
        ) or 0
        matched_count = self.db.scalar(
            select(func.count())
            .select_from(DocumentChunkEmbedding)
            .join(DocumentChunk, DocumentChunk.id == DocumentChunkEmbedding.chunk_id)
            .where(
                DocumentChunk.source_version_id == version_id,
                DocumentChunkEmbedding.embedding_profile_id == profile_id,
                DocumentChunkEmbedding.content_hash == DocumentChunk.content_hash,
            )
        ) or 0
        return chunk_count > 0 and chunk_count == matched_count

    def chunks_for_version_batch(
        self, version_id: UUID, *, offset: int, limit: int
    ) -> list[DocumentChunk]:
        return list(
            self.db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.source_version_id == version_id)
                .order_by(DocumentChunk.chunk_index)
                .offset(offset)
                .limit(limit)
            ).all()
        )
