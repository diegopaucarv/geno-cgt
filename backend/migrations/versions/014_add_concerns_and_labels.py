"""add_concerns_and_labels

Revision ID: 014
Revises: 013
Create Date: 2026-06-18

Añade:
- Tabla concerns (gerund concerns identificadas por el labeler A14)
- Columnas concern_label y population_label en categorias
- Columnas concern_labels (JSONB) y batch_number en hypotheses
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: Union[str, Sequence[str], None] = "f8f6587c86c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Crear tabla concerns
    op.create_table(
        "concerns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'candidate'::character varying"),
        ),
        sa.Column("identified_at_batch", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["proyectos.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_concerns_project_id"),
        "concerns",
        ["project_id"],
        unique=False,
    )

    # 2. Añadir columnas a categorias
    op.add_column(
        "categorias",
        sa.Column("concern_label", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "categorias",
        sa.Column("population_label", sa.String(length=255), nullable=True),
    )

    # 3. Añadir columnas a hypotheses
    op.add_column(
        "hypotheses",
        sa.Column(
            "concern_labels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "hypotheses",
        sa.Column("batch_number", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hypotheses", "batch_number")
    op.drop_column("hypotheses", "concern_labels")

    op.drop_column("categorias", "population_label")
    op.drop_column("categorias", "concern_label")

    op.drop_index(op.f("ix_concerns_project_id"), table_name="concerns")
    op.drop_table("concerns")
