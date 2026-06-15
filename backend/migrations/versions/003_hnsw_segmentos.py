"""hnsw_index_on_segmentos

Revision ID: 003
Revises: 2d24bb976ce8
Create Date: 2026-06-14

Añade índice HNSW en segmentos.embedding para búsqueda vectorial rápida.
Parámetros según Plan §1.3: m=16, ef_construction=64.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "2d24bb976ce8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_segmentos_embedding_hnsw
        ON segmentos
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_segmentos_embedding_hnsw;")
