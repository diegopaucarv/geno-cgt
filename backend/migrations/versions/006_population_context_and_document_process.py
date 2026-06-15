"""population_context_and_document_process

Revision ID: 006
Revises: 005
Create Date: 2026-06-15

Añade tablas para memoria de largo plazo (PopulationContext) y
memoria de corto plazo por documento (DocumentProcess).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "population_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proyecto_id", sa.Uuid(), nullable=False),
        sa.Column("surprising_details", sa.Text(), nullable=False, server_default=""),
        sa.Column("language_patterns", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "data_production_context", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column("source_document_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "document_processes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("documento_id", sa.Uuid(), nullable=False),
        sa.Column("proyecto_id", sa.Uuid(), nullable=False),
        sa.Column("process_description", sa.Text(), nullable=False),
        sa.Column("similarity_to_previous", sa.Text(), nullable=True),
        sa.Column("difference_from_previous", sa.Text(), nullable=True),
        sa.Column("previous_document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"]),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"]),
        sa.ForeignKeyConstraint(["previous_document_id"], ["documentos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("document_processes")
    op.drop_table("population_contexts")
