"""A2_A6_anchor_and_saturation_docs

Revision ID: 008
Revises: 007
Create Date: 2026-06-16

A2: Añade columnas de reconstrucción determinista a segmentos (first_10, start_char, end_char, is_exact_match).
A6: Añade saturation_docs a categorias (array de UUIDs de docs saturados).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A2: Anchor-based reconstruction columns
    op.add_column("segmentos", sa.Column("first_10", sa.String(200), nullable=True))
    op.add_column("segmentos", sa.Column("start_char", sa.Integer(), nullable=True))
    op.add_column("segmentos", sa.Column("end_char", sa.Integer(), nullable=True))
    op.add_column(
        "segmentos",
        sa.Column(
            "is_exact_match",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # A6: TheoSampler saturation_docs
    op.add_column(
        "categorias",
        sa.Column(
            "saturation_docs",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("categorias", "saturation_docs")
    op.drop_column("segmentos", "is_exact_match")
    op.drop_column("segmentos", "end_char")
    op.drop_column("segmentos", "start_char")
    op.drop_column("segmentos", "first_10")
