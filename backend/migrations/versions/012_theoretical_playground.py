"""T01_T05_theoretical_playground

Revision ID: 012
Revises: 011
Create Date: 2026-06-16

Crea las 5 tablas del Theoretical Playground (Fase 6b):
- theoretical_codes (T01)
- category_definition_versions (T02)
- conceptual_relationships (T03)
- elaboration_memos (T04)
- ecosystem_layouts (T05)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "012"
down_revision: Union[str, Sequence[str], None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # T01
    op.create_table(
        "theoretical_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("family", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("glaserian", sa.Boolean(), default=False),
        sa.Column("user_defined", sa.Boolean(), default=False),
        sa.Column("evaluation_logic", JSONB(), default=dict),
        sa.Column("output_schema", JSONB(), default=dict),
        sa.Column("compatible_with", JSONB(), default=list),
        sa.Column("layer", sa.String(50), default="undefined"),
        sa.Column("visualization_hint", sa.String(50), default="tendril"),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # T02
    op.create_table(
        "category_definition_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categorias.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name_at_version", sa.String(200), nullable=False),
        sa.Column("definition_at_version", sa.Text(), nullable=False),
        sa.Column("properties_at_version", JSONB(), default=dict),
        sa.Column("incident_count_at_version", sa.Integer(), default=0),
        sa.Column("trigger", sa.String(50), nullable=False),
        sa.Column("trigger_detail", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # T03
    op.create_table(
        "conceptual_relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=False,
        ),
        sa.Column("category_ids", JSONB(), default=list),
        sa.Column(
            "theoretical_code_id",
            UUID(as_uuid=True),
            sa.ForeignKey("theoretical_codes.id"),
            nullable=False,
        ),
        sa.Column("researcher_question", sa.Text(), nullable=False),
        sa.Column("elaboration_status", sa.String(50), default="emerging"),
        sa.Column("direction", sa.String(100), nullable=True),
        sa.Column("converging_incident_ids", JSONB(), default=list),
        sa.Column("converging_doc_count", sa.Integer(), default=0),
        sa.Column("diverging_incident_ids", JSONB(), default=list),
        sa.Column("diverging_doc_count", sa.Integer(), default=0),
        sa.Column("divergence_resolution", sa.Text(), nullable=True),
        sa.Column("origin_memo_ids", JSONB(), default=list),
        sa.Column("origin_hypothesis_ids", JSONB(), default=list),
        sa.Column("conceptual_fit", sa.Float(), default=0.0),
        sa.Column("layer", sa.String(50), nullable=True),
        sa.Column("position_tension", sa.Float(), default=0.0),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # T04
    op.create_table(
        "elaboration_memos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=False,
        ),
        sa.Column("elaboration_type", sa.String(50), nullable=False),
        sa.Column(
            "relationship_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conceptual_relationships.id"),
            nullable=True,
        ),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categorias.id"),
            nullable=True,
        ),
        sa.Column(
            "memo_id", UUID(as_uuid=True), sa.ForeignKey("memos.id"), nullable=True
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("ecosystem_snapshot", JSONB(), default=dict),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # T05
    op.create_table(
        "ecosystem_layouts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("blob_positions", JSONB(), default=dict),
        sa.Column("ghost_positions", JSONB(), default=dict),
        sa.Column("fog_zones", JSONB(), default=dict),
        sa.Column("physics_params", JSONB(), default=dict),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("ecosystem_layouts")
    op.drop_table("elaboration_memos")
    op.drop_table("conceptual_relationships")
    op.drop_table("category_definition_versions")
    op.drop_table("theoretical_codes")
