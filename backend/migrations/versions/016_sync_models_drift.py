"""sync models drift: batch_executions + columnas faltantes

Revision ID: 016
Revises: 015
Create Date: 2026-10-30

La cadena de migraciones anterior no crea estas columnas ni esta tabla en una
base de datos desde cero (solo existían en bases heredadas), lo que dejaba
drift bloqueante frente a los modelos SQLAlchemy. Todo se aplica de forma
idempotente para no romper bases que ya las tengan.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, Sequence[str], None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("batch_executions"):
        op.create_table(
            "batch_executions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("agent_id", sa.String(length=100), nullable=False),
            sa.Column("total_items", sa.Integer(), nullable=False),
            sa.Column("batches", sa.Integer(), nullable=False),
            sa.Column("items_per_batch", sa.Integer(), nullable=False),
            sa.Column("tokens_per_batch", sa.Integer(), nullable=False),
            sa.Column("map_strategy", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "creado_en",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["project_id"], ["proyectos.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "source_memo_id" not in _columns("categorias"):
        op.add_column(
            "categorias", sa.Column("source_memo_id", sa.Uuid(), nullable=True)
        )
        op.create_foreign_key(
            "fk_categorias_source_memo_id",
            "categorias",
            "memos",
            ["source_memo_id"],
            ["id"],
        )

    if "user_created" not in _columns("memos"):
        # NOT NULL con backfill y luego se quita el default: el modelo solo
        # declara default a nivel Python (False).
        op.add_column(
            "memos",
            sa.Column(
                "user_created",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.alter_column("memos", "user_created", server_default=None)

    if "stage_at_creation" not in _columns("memos"):
        op.add_column(
            "memos", sa.Column("stage_at_creation", sa.String(length=50), nullable=True)
        )

    if "config_segmentacion" not in _columns("proyectos"):
        op.add_column(
            "proyectos",
            sa.Column(
                "config_segmentacion",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )

    if "context_window_real" not in _columns("proyectos"):
        op.add_column(
            "proyectos",
            sa.Column(
                "context_window_real",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("150000"),
            ),
        )
        op.alter_column("proyectos", "context_window_real", server_default=None)

    if "tipo_dato_glaser" not in _columns("segmentos"):
        op.add_column(
            "segmentos",
            sa.Column("tipo_dato_glaser", sa.String(length=50), nullable=True),
        )


def downgrade() -> None:
    if "tipo_dato_glaser" in _columns("segmentos"):
        op.drop_column("segmentos", "tipo_dato_glaser")

    if "context_window_real" in _columns("proyectos"):
        op.drop_column("proyectos", "context_window_real")

    if "config_segmentacion" in _columns("proyectos"):
        op.drop_column("proyectos", "config_segmentacion")

    memo_columns = _columns("memos")
    if "stage_at_creation" in memo_columns:
        op.drop_column("memos", "stage_at_creation")
    if "user_created" in memo_columns:
        op.drop_column("memos", "user_created")

    if "source_memo_id" in _columns("categorias"):
        op.drop_constraint(
            "fk_categorias_source_memo_id", "categorias", type_="foreignkey"
        )
        op.drop_column("categorias", "source_memo_id")

    if _has_table("batch_executions"):
        op.drop_table("batch_executions")
