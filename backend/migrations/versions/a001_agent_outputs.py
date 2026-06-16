"""add agent metadata tables

Revision ID: a001_agent_outputs
Create Date: 2026-06-16

Tres tablas nuevas para la capa agencial:
- agent_outputs: metadata polimorfica de outputs de agentes
- agent_loop_logs: trazabilidad de bucles agenciales
- output_modifications: historial HITL (P5)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "a001_agent_outputs"
down_revision: Union[str, None] = "018f5945d0ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── agent_loop_logs (primero, porque agent_outputs lo referencia) ──
    op.create_table(
        "agent_loop_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "proyecto_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("pattern", sa.String(50), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_cost_est", sa.Float(), server_default="0.0"),
        sa.Column("had_reasoning", sa.Boolean(), server_default="false"),
        sa.Column("tool_calls", postgresql.JSONB(), server_default="[]"),
        sa.Column("llm_calls", postgresql.JSONB(), server_default="[]"),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(100), nullable=False),
        sa.Column("finished_at", sa.String(100), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_index("idx_loop_logs_proyecto", "agent_loop_logs", ["proyecto_id"])
    op.create_index("idx_loop_logs_agent", "agent_loop_logs", ["agent_id"])
    # ── agent_families (tabla de referencia metodologica) ────────────
    op.create_table(
        "agent_families",
        sa.Column("family", sa.String(50), primary_key=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("icon", sa.String(10), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("research_question", sa.Text(), nullable=False),
        sa.Column("verification_method", sa.Text(), nullable=False),
        sa.Column("accepted_questions", postgresql.JSONB(), nullable=False),
        sa.Column("rejected_questions", postgresql.JSONB(), nullable=False),
        sa.Column("recommended_tools", postgresql.JSONB(), nullable=False),
    )

    # ── Seed: 6 familias CGT ────────────────────────────────────────
    op.bulk_insert(
        sa.table(
            "agent_families",
            sa.column("family", sa.String(50)),
            sa.column("label", sa.String(100)),
            sa.column("icon", sa.String(10)),
            sa.column("description", sa.Text()),
            sa.column("research_question", sa.Text()),
            sa.column("verification_method", sa.Text()),
            sa.column("accepted_questions", postgresql.JSONB()),
            sa.column("rejected_questions", postgresql.JSONB()),
            sa.column("recommended_tools", postgresql.JSONB()),
        ),
        [
            {
                "family": "inductive_data",
                "label": "Inductiva a datos",
                "icon": "🔍",
                "description": "Preguntan a segmentos/textos. Bottom-up puro. La teoria emerge de los datos crudos.",
                "research_question": "Que emerge de los datos crudos?",
                "verification_method": "Comparacion constante contra segmentos originales. Si la evidencia textual no respalda el output, esta mal.",
                "accepted_questions": [
                    "Este codigo esta bien nombrado?",
                    "La definicion captura todas las propiedades observadas?",
                    "Hay indicadores que contradicen esta definicion?",
                    "El gerundio captura bien el patron de comportamiento?"
                ],
                "rejected_questions": [
                    "No puedo evaluar relaciones entre codigos (usa el Playground para eso)",
                    "No puedo evaluar hipotesis (eso corresponde al agente B3)",
                    "No puedo cambiar el estilo de codificacion (es configuracion global)"
                ],
                "recommended_tools": ["search_segments", "compare_embeddings"]
            },
            {
                "family": "inductive_concepts",
                "label": "Inductiva a conceptos",
                "icon": "🧠",
                "description": "Operan sobre codigos ya existentes. Abstraccion de orden superior. La teoria emerge de los conceptos.",
                "research_question": "Que patron teorico indican estos conceptos?",
                "verification_method": "Triangulacion entre codigos. Si el concepto no relaciona 2+ codigos con evidencia, esta mal.",
                "accepted_questions": [
                    "El main concern captura la esencia del fenomeno?",
                    "Esta hipotesis tiene suficiente evidencia?",
                    "La relacion entre codigos esta bien caracterizada?",
                    "Hay evidencia divergente que matice esta hipotesis?"
                ],
                "rejected_questions": [
                    "No puedo evaluar si un codigo individual esta bien definido (usa modificacion de codigos)",
                    "No puedo cambiar datos crudos (eso es pre-procesamiento)"
                ],
                "recommended_tools": ["get_code_details", "find_similar_codes", "search_segments"]
            },
            {
                "family": "descriptive_data",
                "label": "Descriptiva a datos",
                "icon": "📋",
                "description": "No generan conceptos nuevos. Comprimen, sintetizan, organizan informacion existente.",
                "research_question": "Como resumir/describir sin inducir teoria nueva?",
                "verification_method": "Fidelidad al original. Si el resumen omite, distorsiona o agrega informacion no presente en los datos, esta mal.",
                "accepted_questions": [
                    "Hay detalles del entrevistado que no se capturaron?",
                    "El proceso identificado es realmente lo que el entrevistado intenta resolver?",
                    "La comparacion con el entrevistado anterior es correcta?"
                ],
                "rejected_questions": [
                    "No puedo inducir teoria nueva desde este agente (es descriptivo, no inductivo)",
                    "No puedo evaluar la calidad teorica de un concepto (usa los critics para eso)"
                ],
                "recommended_tools": ["search_segments", "get_code_details"]
            },
            {
                "family": "evaluative",
                "label": "Evaluativa / Critica",
                "icon": "⚖️",
                "description": "No proponen nada. Solo auditan, evaluan, verifican grounding metodologico.",
                "research_question": "Es solida esta propuesta?",
                "verification_method": "Grounding score + criterios metodologicos CGT. Si el veredicto no referencia evidencia especifica, esta mal.",
                "accepted_questions": [
                    "Este veredicto SAT/MOD/FORCED es correcto?",
                    "Hay evidencia que el critic no considero?",
                    "El grounding score esta bien calculado?"
                ],
                "rejected_questions": [
                    "No puedo proponer codigos alternativos (soy critic, no proposer)",
                    "No puedo evaluar si un codigo es 'interesante' (solo evaluo grounding metodologico)"
                ],
                "recommended_tools": ["get_code_details", "compare_embeddings"]
            },
            {
                "family": "structural",
                "label": "Estructural / Transformacional",
                "icon": "🏗️",
                "description": "Transforman el sistema conceptual en una estructura formal (nodos, edges, reporte).",
                "research_question": "Como convertir conceptos en modelo?",
                "verification_method": "Integridad del modelo. Si un nodo/edge no tiene respaldo en categorias/hypotheses, esta mal.",
                "accepted_questions": [
                    "Este nodo representa bien la categoria?",
                    "El entity_type es correcto?",
                    "Falta alguna categoria en el modelo?",
                    "Esta relacion tiene respaldo en los datos?"
                ],
                "rejected_questions": [
                    "No puedo modificar la definicion de una categoria desde el modelo",
                    "No puedo crear nuevas categorias (eso es codificacion, no modelado)"
                ],
                "recommended_tools": ["get_code_details", "search_segments", "get_change_impact"]
            },
            {
                "family": "elaborative",
                "label": "Elaborativa",
                "icon": "🔬",
                "description": "Comparan un incidente/dato nuevo contra un concepto existente. Ni inductivo puro ni descriptivo: es comparativo.",
                "research_question": "Este nuevo incidente expande el concepto?",
                "verification_method": "Test de intercambiabilidad de indicadores. Si el incidente es intercambiable con los existentes, no expande.",
                "accepted_questions": [
                    "La evidencia convergente/divergente esta bien evaluada?",
                    "El conceptual_fit refleja la realidad de los datos?",
                    "Hay dimensiones de la relacion que no se consideraron?"
                ],
                "rejected_questions": [
                    "No puedo crear un concepto nuevo desde un solo incidente",
                    "No puedo evaluar si el concepto es 'util' (solo evaluo si el incidente expande o no)"
                ],
                "recommended_tools": ["compare_embeddings", "search_segments", "get_code_details"]
            },
        ],
    )



    # ── agent_outputs ───────────────────────────────────────────────
    op.create_table(
        "agent_outputs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "proyecto_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=False,
        ),
        sa.Column("output_table", sa.String(100), nullable=False),
        sa.Column("output_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("agent_family", sa.String(50), nullable=False),
        sa.Column("agent_tier", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("is_final", sa.Boolean(), server_default="true"),
        sa.Column("prompt_id", sa.String(100), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column(
            "loop_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_loop_logs.id"),
            nullable=True,
        ),
        sa.Column("iteration_number", sa.Integer(), nullable=True),
        sa.Column(
            "parent_output_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_outputs.id"),
            nullable=True,
        ),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_index("idx_agent_outputs_proyecto", "agent_outputs", ["proyecto_id"])
    op.create_index("idx_agent_outputs_agent", "agent_outputs", ["agent_id"])
    op.create_index(
        "idx_agent_outputs_ref",
        "agent_outputs",
        ["output_table", "output_id"],
        unique=True,
    )

    # ── output_modifications ────────────────────────────────────────
    op.create_table(
        "output_modifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "proyecto_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proyectos.id"),
            nullable=False,
        ),
        sa.Column(
            "modified_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuarios.id"),
            nullable=True,
        ),
        sa.Column(
            "agent_output_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_outputs.id"),
            nullable=False,
        ),
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("rewritten_request", sa.Text(), nullable=True),
        sa.Column("recommended", sa.Boolean(), nullable=True),
        sa.Column("recommendation_reason", sa.Text(), nullable=True),
        sa.Column("recommendation_confidence", sa.Float(), nullable=True),
        sa.Column("original_content", postgresql.JSONB(), nullable=False),
        sa.Column("modified_content", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_collected", postgresql.JSONB(), server_default="[]"),
        sa.Column("verification_plan", postgresql.JSONB(), nullable=True),
        sa.Column("applied", sa.Boolean(), server_default="false"),
        sa.Column("applied_at", sa.String(100), nullable=True),
        sa.Column("wiped_tables", postgresql.JSONB(), server_default="[]"),
        sa.Column("pipeline_restarted_from", sa.String(100), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_index(
        "idx_modifications_output", "output_modifications", ["agent_output_id"]
    )
    op.create_index(
        "idx_modifications_proyecto", "output_modifications", ["proyecto_id"]
    )


def downgrade() -> None:
    op.drop_table("output_modifications")
    op.drop_table("agent_outputs")
    op.drop_table("agent_loop_logs")
    op.drop_table("agent_families")
