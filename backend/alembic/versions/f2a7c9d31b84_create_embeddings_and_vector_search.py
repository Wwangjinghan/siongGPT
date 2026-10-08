"""create embedding profiles and chunk vectors

Revision ID: f2a7c9d31b84
Revises: e91c3b7d42a6
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import VECTOR
import sqlalchemy as sa


revision: str = "f2a7c9d31b84"
down_revision: Union[str, Sequence[str], None] = "e91c3b7d42a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_PROFILE_ID = "7b991672-4f0d-4da1-8858-61e93585c2af"
DEFAULT_MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"


def upgrade() -> None:
    op.drop_constraint("ck_ingestion_jobs_type", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_type",
        "ingestion_jobs",
        "job_type IN ('DOCUMENT_INGESTION','DOCUMENT_EMBEDDING')",
    )
    op.create_table(
        "embedding_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_revision", sa.String(length=64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("distance_metric", sa.String(length=16), nullable=False),
        sa.Column("normalized", sa.Boolean(), nullable=False),
        sa.Column("query_prefix", sa.String(length=32), nullable=False),
        sa.Column("passage_prefix", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("provider_type IN ('LOCAL_E5')", name="ck_embedding_profiles_provider"),
        sa.CheckConstraint("dimensions = 384", name="ck_embedding_profiles_dimensions"),
        sa.CheckConstraint("distance_metric = 'cosine'", name="ck_embedding_profiles_metric"),
        sa.CheckConstraint("normalized", name="ck_embedding_profiles_normalized"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_embedding_profiles_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_embedding_profiles_one_active",
        "embedding_profiles",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    profile_table = sa.table(
        "embedding_profiles",
        sa.column("id", sa.UUID()),
        sa.column("provider_type", sa.String()),
        sa.column("model_name", sa.String()),
        sa.column("model_revision", sa.String()),
        sa.column("dimensions", sa.Integer()),
        sa.column("distance_metric", sa.String()),
        sa.column("normalized", sa.Boolean()),
        sa.column("query_prefix", sa.String()),
        sa.column("passage_prefix", sa.String()),
        sa.column("status", sa.String()),
    )
    op.bulk_insert(
        profile_table,
        [{
            "id": DEFAULT_PROFILE_ID,
            "provider_type": "LOCAL_E5",
            "model_name": "intfloat/multilingual-e5-small",
            "model_revision": DEFAULT_MODEL_REVISION,
            "dimensions": 384,
            "distance_metric": "cosine",
            "normalized": True,
            "query_prefix": "query: ",
            "passage_prefix": "passage: ",
            "status": "ACTIVE",
        }],
    )
    op.create_table(
        "document_chunk_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("embedding_profile_id", sa.UUID(), nullable=False),
        sa.Column("embedding", VECTOR(384), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_chunk_embeddings_sha256"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"]),
        sa.ForeignKeyConstraint(["embedding_profile_id"], ["embedding_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "embedding_profile_id", name="uq_chunk_embeddings_chunk_profile"),
    )
    op.create_index(
        "ix_chunk_embeddings_profile_chunk",
        "document_chunk_embeddings",
        ["embedding_profile_id", "chunk_id"],
    )
    op.create_index(
        "ix_chunk_embeddings_hnsw_cosine",
        "document_chunk_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_embeddings_hnsw_cosine", table_name="document_chunk_embeddings")
    op.drop_index("ix_chunk_embeddings_profile_chunk", table_name="document_chunk_embeddings")
    op.drop_table("document_chunk_embeddings")
    op.drop_index("uq_embedding_profiles_one_active", table_name="embedding_profiles")
    op.drop_table("embedding_profiles")
    op.drop_constraint("ck_ingestion_jobs_type", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_type", "ingestion_jobs", "job_type IN ('DOCUMENT_INGESTION')"
    )
