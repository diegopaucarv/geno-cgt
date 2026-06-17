"""add_database_nodes_and_edges

Revision ID: 3de4964dd68c
Revises: 018f5945d0ca
Create Date: 2026-06-16 05:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3de4964dd68c"
down_revision: Union[str, Sequence[str], None] = "018f5945d0ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "database_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("is_core", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categorias.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["proyectos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "database_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column(
            "direction",
            sa.String(length=20),
            nullable=False,
            server_default="unidirectional",
        ),
        sa.Column(
            "strength", sa.String(length=20), nullable=False, server_default="moderate"
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["proyectos.id"]),
        sa.ForeignKeyConstraint(["source_node_id"], ["database_nodes.id"]),
        sa.ForeignKeyConstraint(["target_node_id"], ["database_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("database_edges")
    op.drop_table("database_nodes")
