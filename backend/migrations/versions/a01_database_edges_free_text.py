"""widen_database_edges_for_free_text

Revision ID: a01
Revises: 3de4964dd68c
Create Date: 2026-06-18 00:00:00.000000

Widens relationship_type from VARCHAR(50) to TEXT to support free-text
relationship descriptions (replacing the enum-based approach).
Also adds a dedicated description TEXT column for the new schema format.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a01_database_edges_free_text"
down_revision: Union[str, Sequence[str], None] = "3de4964dd68c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Widen relationship_type to support free-text descriptions
    op.alter_column(
        "database_edges",
        "relationship_type",
        existing_type=sa.String(length=50),
        type_=sa.Text(),
        existing_nullable=False,
    )

    # 2. Add description column for the new free-text schema
    op.add_column(
        "database_edges",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("database_edges", "description")
    # Downgrade back to VARCHAR(50) — will truncate any data longer than 50 chars
    op.alter_column(
        "database_edges",
        "relationship_type",
        existing_type=sa.Text(),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
