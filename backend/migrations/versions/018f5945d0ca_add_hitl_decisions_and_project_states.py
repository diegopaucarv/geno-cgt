"""add_hitl_decisions_and_project_states

Revision ID: 018f5945d0ca
Revises: 9f999ca4430f
Create Date: 2026-06-16 04:15:28.869932

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "018f5945d0ca"
down_revision: Union[str, Sequence[str], None] = "9f999ca4430f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Crear tabla hitl_decisions ──
    op.create_table(
        "hitl_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("gate_name", sa.String(length=100), nullable=False),
        sa.Column("proposal", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "critic_verdict", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("researcher_decision", sa.String(length=20), nullable=True),
        sa.Column("researcher_note", sa.Text(), nullable=True),
        sa.Column("researcher_feedback", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["proyectos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Migrar proyectos existentes: ACTIVO → collecting ──
    op.execute("UPDATE proyectos SET estado = 'collecting' WHERE estado = 'ACTIVO'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("hitl_decisions")
    op.execute("UPDATE proyectos SET estado = 'ACTIVO' WHERE estado = 'collecting'")
