"""A1_paradigm_states

Revision ID: 009
Revises: 008
Create Date: 2026-06-16

A1: Crea tabla paradigm_states para el Integrador Paradigmático.
Almacena el estado paradigmático (dimensions, conditions, consequences, strategies)
y la señal booleana did_state_expand por iteración.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "009"
down_revision: Union[str, Sequence[str], None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paradigm_states",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "code_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categorias.id"),
            nullable=False,
        ),
        sa.Column(
            "proyecto_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=False,
        ),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column(
            "did_state_expand",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("expansion_type", sa.String(50), nullable=True),
        sa.Column(
            "paradigm_snapshot",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("integration_memo", sa.Text(), nullable=True),
        sa.Column("metadata_group", sa.String(200), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
    )

    # Índices para búsquedas comunes
    op.create_index(
        "idx_paradigm_states_code_iter", "paradigm_states", ["code_id", "iteration"]
    )
    op.create_index("idx_paradigm_states_proyecto", "paradigm_states", ["proyecto_id"])


def downgrade() -> None:
    op.drop_index("idx_paradigm_states_proyecto")
    op.drop_index("idx_paradigm_states_code_iter")
    op.drop_table("paradigm_states")
