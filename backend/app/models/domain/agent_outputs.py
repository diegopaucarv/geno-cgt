# backend/app/models/domain/agent_outputs.py
"""
Tablas de metadata para la capa agencial.

Proporcionan trazabilidad completa sin modificar las tablas de dominio existentes.
Siguen el patron de LangSmith/MLflow: una capa de metadata que referencia
polymorficamente los outputs de cualquier agente.

Tablas:
- agent_outputs: metadata de cada output de agente (que agente, que familia, version)
- agent_loop_logs: trazabilidad de bucles agenciales (iteraciones, tokens, tools)
- output_modifications: historial de modificaciones HITL (P5)
"""

import uuid

from app.models.base import Base
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class AgentOutput(Base):
    """Metadata de cada output producido por un agente CGT.

    Referencia polymorphicamente la fila concreta en la tabla de dominio
    (categorias, hypotheses, population_contexts, etc.) via output_table + output_id.

    No modifica las tablas existentes — solo agrega metadata encima.
    """

    __tablename__ = "agent_outputs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # ── Proyecto ───────────────────────────────────────────────────
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), nullable=False
    )

    # ── Referencia polimorfica al output ──────────────────────────
    output_table: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Tabla donde esta el output concreto"
    )
    # Valores: 'categorias', 'hypotheses', 'population_contexts',
    #          'document_processes', 'conceptual_relationships'

    output_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, comment="ID de la fila en output_table"
    )

    # ── Metadata del agente ────────────────────────────────────────
    agent_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="ID del agente: b2b, b3, a1, etc."
    )
    agent_family: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Familia del prompt"
    )
    # Valores: 'inductive_data', 'inductive_concepts', 'descriptive_data',
    #          'evaluative', 'structural', 'elaborative'

    agent_tier: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="PRO o FLASH"
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_final: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="False para iteraciones intermedias de bucles agenciales",
    )

    # ── Trazabilidad del prompt ────────────────────────────────────
    prompt_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Archivo de prompt usado"
    )
    prompt_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Hash SHA-256 del prompt renderizado"
    )

    # ── Metadata multi-agente ──────────────────────────────────────
    loop_log_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_loop_logs.id"),
        nullable=True,
        comment="Si fue producido por un bucle agencial",
    )
    iteration_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Numero de iteracion en el bucle"
    )
    parent_output_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_outputs.id"),
        nullable=True,
        comment="Version anterior de este output (auto-referencia)",
    )


class AgentLoopLog(Base):
    """Trazabilidad de ejecucion de bucles agenciales.

    Un log por cada invocacion de SelfRefinementLoop, ReactRunner, o PlanExecutor.
    """

    __tablename__ = "agent_loop_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # ── Proyecto ───────────────────────────────────────────────────
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), nullable=False
    )

    # ── Identificacion ─────────────────────────────────────────────
    agent_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Agente que ejecuto el bucle"
    )
    pattern: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Patron agencial usado"
    )
    # Valores: 'self_refinement', 'react', 'plan_execute', 'debate', 'hitl_modification'

    # ── Metricas ───────────────────────────────────────────────────
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_est: Mapped[float] = mapped_column(Float, default=0.0)
    had_reasoning: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="¿DeepSeek V4 Pro genero reasoning_content?"
    )

    # ── Trazabilidad detallada ─────────────────────────────────────
    tool_calls: Mapped[dict] = mapped_column(
        JSONB, default=list, comment="[{tool_name, input, observation, timestamp}]"
    )
    llm_calls: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        comment="[{tier, model, tokens_in, tokens_out, duration_ms}]",
    )

    result_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Primeros 500 chars del output final"
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error si el bucle fallo"
    )

    # ── Timestamps ─────────────────────────────────────────────────
    started_at: Mapped[str] = mapped_column(String(100), nullable=False)
    finished_at: Mapped[str] = mapped_column(String(100), nullable=False)


class OutputModification(Base):
    """Historial de modificaciones HITL (P5: Modification Agent).

    Cada fila representa un pedido de modificacion de un usuario
    sobre un output de agente, con el veredicto del sistema.
    """

    __tablename__ = "output_modifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # ── Proyecto y usuario ─────────────────────────────────────────
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), nullable=False
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )

    # ── Referencia al output ───────────────────────────────────────
    agent_output_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_outputs.id"), nullable=False
    )

    # ── Pedido del usuario ─────────────────────────────────────────
    user_request: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Que pidio el usuario"
    )
    rewritten_request: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Rewordeado por PRO planner"
    )

    # ── Veredicto del sistema ──────────────────────────────────────
    recommended: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="Veredicto del evaluador PRO"
    )
    recommendation_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Por que es o no recomendable"
    )
    recommendation_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="0-1 confianza del evaluador"
    )

    # ── Contenido ──────────────────────────────────────────────────
    original_content: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Snapshot del output antes de modificar"
    )
    modified_content: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Version modificada (null si no se aplico)"
    )

    # ── Evidencia y plan ───────────────────────────────────────────
    evidence_collected: Mapped[dict] = mapped_column(
        JSONB, default=list, comment="Evidencia recolectada por las tools de busqueda"
    )
    verification_plan: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Plan producido por PRO planner"
    )

    # ── Aplicacion ─────────────────────────────────────────────────
    applied: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="¿El usuario confirmo la modificacion?"
    )
    applied_at: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="ISO timestamp de cuando se aplico"
    )
    wiped_tables: Mapped[dict] = mapped_column(
        JSONB, default=list, comment="Tablas limpiadas como consecuencia"
    )
    pipeline_restarted_from: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Nodo del pipeline donde se reinicio"
    )


class AgentFamilyReference(Base):
    """Tabla de referencia: que implica cada familia de agentes en CGT.

    Describe metodologicamente que tipo de preguntas responde cada familia,
    que metodo de verificacion usa, y que criterios de calidad aplican.
    Usado por el FLASH filter en P5 para guiar al usuario.
    """

    __tablename__ = "agent_families"

    family: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="Clave primaria: nombre de la familia"
    )
    # Valores: inductive_data, inductive_concepts, descriptive_data,
    #          evaluative, structural, elaborative

    label: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Nombre legible en español"
    )
    icon: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="Emoji de la familia"
    )

    # ── Descripcion metodologica ────────────────────────────────────
    description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Que hace esta familia en terminos CGT"
    )
    research_question: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Pregunta clave que intenta responder"
    )
    verification_method: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Como se verifica si un output es correcto"
    )

    # ── P5: Modification Agent ──────────────────────────────────────
    accepted_questions: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Ejemplos de preguntas que SI acepta este agente"
    )
    rejected_questions: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Ejemplos de preguntas que NO acepta y por que"
    )
    recommended_tools: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Tools recomendadas para verificar modificaciones"
    )
