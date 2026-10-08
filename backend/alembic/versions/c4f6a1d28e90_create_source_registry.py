"""create source registry and immutable versions

Revision ID: c4f6a1d28e90
Revises: 8b72f0a6c341
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f6a1d28e90"
down_revision: Union[str, Sequence[str], None] = "8b72f0a6c341"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("business_scene", sa.String(length=100), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("access_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_type IN ('DOCUMENT','EXPERT_NOTE','MANUAL_ATTESTATION')",
            name="ck_sources_source_type",
        ),
        sa.CheckConstraint(
            "scope_type IN ('COMPANY','DEPARTMENT','PROJECT','PERSONAL_DRAFT')",
            name="ck_sources_scope_type",
        ),
        sa.CheckConstraint(
            "access_level IN ('INTERNAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_sources_access_level",
        ),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_sources_status"),
        sa.CheckConstraint(
            "(scope_type = 'COMPANY' AND department_id IS NULL AND project_id IS NULL) OR "
            "(scope_type = 'DEPARTMENT' AND department_id IS NOT NULL AND project_id IS NULL) OR "
            "(scope_type = 'PERSONAL_DRAFT' AND owner_user_id IS NOT NULL AND project_id IS NULL) OR "
            "(scope_type = 'PROJECT' AND project_id IS NOT NULL)",
            name="ck_sources_scope_fields",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sources_scope_status", "sources", ["scope_type", "status"])
    op.create_index("ix_sources_department", "sources", ["department_id"])
    op.create_index("ix_sources_owner", "sources", ["owner_user_id"])
    op.create_index("ix_sources_type", "sources", ["source_type"])
    op.create_index("ix_sources_business_scene", "sources", ["business_scene"])

    op.create_table(
        "source_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("processing_status", sa.String(length=20), nullable=False),
        sa.Column("processing_error_code", sa.String(length=100), nullable=True),
        sa.Column("publication_status", sa.String(length=20), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=False),
        sa.Column("published_by", sa.UUID(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version_no > 0", name="ck_source_versions_positive_version"),
        sa.CheckConstraint("file_size > 0", name="ck_source_versions_positive_size"),
        sa.CheckConstraint(
            "file_hash ~ '^[0-9a-f]{64}$'", name="ck_source_versions_sha256"
        ),
        sa.CheckConstraint(
            "processing_status IN ('PENDING','PROCESSING','READY','FAILED')",
            name="ck_source_versions_processing_status",
        ),
        sa.CheckConstraint(
            "publication_status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN','ARCHIVED')",
            name="ck_source_versions_publication_status",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_source_versions_effective_range",
        ),
        sa.CheckConstraint(
            "NOT is_current OR (processing_status = 'READY' AND publication_status = 'PUBLISHED')",
            name="ck_source_versions_current_published_ready",
        ),
        sa.CheckConstraint(
            "(publication_status IN ('PUBLISHED','SUPERSEDED','WITHDRAWN') "
            "AND published_by IS NOT NULL AND published_at IS NOT NULL) OR "
            "publication_status IN ('DRAFT','ARCHIVED')",
            name="ck_source_versions_publication_actor",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "file_hash", name="uq_source_versions_hash"),
        sa.UniqueConstraint("source_id", "version_no", name="uq_source_versions_number"),
    )
    op.create_index(
        "uq_source_versions_one_current",
        "source_versions",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_source_versions_source_number", "source_versions", ["source_id", "version_no"]
    )
    op.create_index("ix_source_versions_file_hash", "source_versions", ["file_hash"])
    op.create_index(
        "ix_source_versions_states",
        "source_versions",
        ["publication_status", "processing_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_versions_states", table_name="source_versions")
    op.drop_index("ix_source_versions_file_hash", table_name="source_versions")
    op.drop_index("ix_source_versions_source_number", table_name="source_versions")
    op.drop_index("uq_source_versions_one_current", table_name="source_versions")
    op.drop_table("source_versions")
    op.drop_index("ix_sources_business_scene", table_name="sources")
    op.drop_index("ix_sources_type", table_name="sources")
    op.drop_index("ix_sources_owner", table_name="sources")
    op.drop_index("ix_sources_department", table_name="sources")
    op.drop_index("ix_sources_scope_status", table_name="sources")
    op.drop_table("sources")
