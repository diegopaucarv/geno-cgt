"""pipeline_run_tracking

Revision ID: 9f999ca4430f
Revises: 012
Create Date: 2026-06-16 01:48:37.630478

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f999ca4430f"
down_revision: Union[str, Sequence[str], None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("triggered_by", sa.String(length=50), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
    op.create_table(
        "pipeline_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=100), nullable=False),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column("queue", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("doc_estado_before", sa.String(length=50), nullable=True),
        sa.Column("segments_before", sa.Integer(), nullable=False),
        sa.Column("codes_before", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documentos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["pipeline_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("celery_task_id"),
    )
    op.create_table(
        "task_step_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_task_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "affected_rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documentos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_task_id"],
            ["pipeline_tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("task_step_checkpoints")
    op.drop_table("pipeline_tasks")
    op.drop_table("pipeline_runs")
