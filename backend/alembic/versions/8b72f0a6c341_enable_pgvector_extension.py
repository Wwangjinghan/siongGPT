"""enable pgvector extension

Revision ID: 8b72f0a6c341
Revises: ecfdcf98a416
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op


revision: str = "8b72f0a6c341"
down_revision: Union[str, Sequence[str], None] = "ecfdcf98a416"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Deliberately retain the extension. Dropping it with CASCADE could destroy
    # future vector columns; dropping without CASCADE makes rollback fragile once
    # dependants exist. Alembic still rolls back the revision marker safely.
    pass
