"""Add sort_order to documentos for drag-and-drop ordering.

Revision ID: a02_sort_order
Revises: a01_database_edges_free_text
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a02_sort_order"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documentos", sa.Column("sort_order", sa.Float(), nullable=True))
    # Initialize with alphabetical order
    op.execute("""
        UPDATE documentos d
        SET sort_order = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (ORDER BY original_filename) AS rn
            FROM documentos
        ) sub
        WHERE d.id = sub.id
    """)


def downgrade() -> None:
    op.drop_column("documentos", "sort_order")
