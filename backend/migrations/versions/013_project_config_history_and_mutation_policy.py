"""project_config_history_and_mutation_policy

Revision ID: 013
Revises: ff33a5c05513
Create Date: 2026-06-17

Añade:
- Columna config_mutation_policy (JSONB) a proyectos
- Tabla project_config_history para registro inmutable de cambios de config
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: Union[str, Sequence[str], None] = "ff33a5c05513"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Añadir columna de política de mutaciones a proyectos
    op.add_column(
        "proyectos",
        sa.Column(
            "config_mutation_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # 2. Crear tabla de historial de configuración
    op.create_table(
        "project_config_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proyecto_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column(
            "triggered_by", sa.String(length=50), nullable=False, server_default="user"
        ),
        sa.Column("agent_run_id", sa.String(length=100), nullable=True),
        sa.Column("mutation_level", sa.String(length=20), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["proyecto_id"],
            ["proyectos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_config_history_proyecto_id"),
        "project_config_history",
        ["proyecto_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_config_history_field"),
        "project_config_history",
        ["field"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_project_config_history_field"),
        table_name="project_config_history",
    )
    op.drop_index(
        op.f("ix_project_config_history_proyecto_id"),
        table_name="project_config_history",
    )
    op.drop_table("project_config_history")
    op.drop_column("proyectos", "config_mutation_policy")
