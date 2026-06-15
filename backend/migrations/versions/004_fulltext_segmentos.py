"""fulltext_search_on_segmentos

Revision ID: 004
Revises: 003
Create Date: 2026-06-14

Añade columna tsvector generada + índice GIN para búsqueda full-text (BM25).
Configuración para español.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Computed
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Columna tsvector generada automáticamente desde 'texto'
    op.add_column(
        "segmentos",
        sa.Column(
            "texto_tsv",
            TSVECTOR(),
            Computed("to_tsvector('spanish', coalesce(texto, ''))", persisted=True),
            nullable=True,
        ),
    )

    # 2. Índice GIN para búsqueda full-text rápida
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_segmentos_texto_tsv
        ON segmentos
        USING GIN (texto_tsv);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_segmentos_texto_tsv;")
    op.drop_column("segmentos", "texto_tsv")
