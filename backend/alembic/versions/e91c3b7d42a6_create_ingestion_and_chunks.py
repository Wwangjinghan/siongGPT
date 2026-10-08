"""create ingestion jobs, document chunks, and PostgreSQL FTS

Revision ID: e91c3b7d42a6
Revises: c4f6a1d28e90
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e91c3b7d42a6"
down_revision: Union[str, Sequence[str], None] = "c4f6a1d28e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_version_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "job_type IN ('DOCUMENT_INGESTION')", name="ck_ingestion_jobs_type"
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','DEAD_LETTER','CANCELLED')",
            name="ck_ingestion_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_ingestion_jobs_max_attempts"),
        sa.CheckConstraint(
            "attempt_count <= max_attempts", name="ck_ingestion_jobs_attempt_limit"
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR status <> 'RUNNING'",
            name="ck_ingestion_jobs_running_lease",
        ),
        sa.ForeignKeyConstraint(["source_version_id"], ["source_versions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ingestion_jobs_active_version",
        "ingestion_jobs",
        ["source_version_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"),
    )
    op.create_index(
        "ix_ingestion_jobs_claim",
        "ingestion_jobs",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_ingestion_jobs_lease", "ingestion_jobs", ["status", "lease_expires_at"]
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_version_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=500), nullable=True),
        sa.Column("sheet", sa.String(length=255), nullable=True),
        sa.Column("row_start", sa.Integer(), nullable=True),
        sa.Column("row_end", sa.Integer(), nullable=True),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, content)", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index"),
        sa.CheckConstraint(
            "length(btrim(content)) > 0", name="ck_document_chunks_content"
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_document_chunks_sha256"
        ),
        sa.CheckConstraint("page IS NULL OR page > 0", name="ck_document_chunks_page"),
        sa.CheckConstraint(
            "row_start IS NULL OR row_start > 0", name="ck_document_chunks_row_start"
        ),
        sa.CheckConstraint(
            "row_end IS NULL OR row_end > 0", name="ck_document_chunks_row_end"
        ),
        sa.CheckConstraint(
            "row_end IS NULL OR row_start IS NULL OR row_end >= row_start",
            name="ck_document_chunks_row_range",
        ),
        sa.CheckConstraint(
            "block_type IN ('PARAGRAPH','HEADING','TABLE','SPREADSHEET_ROWS')",
            name="ck_document_chunks_block_type",
        ),
        sa.ForeignKeyConstraint(["source_version_id"], ["source_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_version_id", "chunk_index", name="uq_document_chunks_version_index"
        ),
    )
    op.create_index(
        "ix_document_chunks_version",
        "document_chunks",
        ["source_version_id", "chunk_index"],
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_search_vector", table_name="document_chunks")
    op.drop_index("ix_document_chunks_version", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_ingestion_jobs_lease", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_claim", table_name="ingestion_jobs")
    op.drop_index("uq_ingestion_jobs_active_version", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
