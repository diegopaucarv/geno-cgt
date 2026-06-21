# backend/app/models/domain/pipeline_run.py
"""PipelineRun — tracking de ejecuciones del pipeline para stop/cancel/resume/restart."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class PipelineRun(Base, TimestampMixin):
    """Una ejecución del pipeline. Agrupa todas las tareas disparadas."""

    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    status: Mapped[str] = mapped_column(String(20), default="running")
    # "running" | "completed" | "cancelled" | "failed"

    triggered_by: Mapped[str] = mapped_column(String(50), default="user")
    # "user" | "auto"

    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {total_docs, need_segment, need_agents, already_done}


class PipelineTask(Base, TimestampMixin):
    """Una tarea individual dentro de un PipelineRun."""

    __tablename__ = "pipeline_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documentos.id"), nullable=True
    )

    celery_task_id: Mapped[str] = mapped_column(String(100), unique=True)
    task_name: Mapped[str] = mapped_column(String(100))
    # "segmentar_documento" | "process_document_agents_a" | "punctuate_text" | etc.

    queue: Mapped[str] = mapped_column(String(20), default="heavy")
    # "nlp" | "fast" | "heavy"

    status: Mapped[str] = mapped_column(String(20), default="queued")
    # "queued" | "running" | "completed" | "cancelled" | "failed"

    doc_estado_before: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Estado del documento ANTES de ejecutar (para rollback)
    # "crudo" | "segmentando" | "segmentado" | "listo" | "error"

    segments_before: Mapped[int] = mapped_column(Integer, default=0)
    codes_before: Mapped[int] = mapped_column(Integer, default=0)


class TaskStepCheckpoint(Base, TimestampMixin):
    """Checkpoint por paso dentro de una tarea. Permite resumir tras cancel.

    Cada paso escribe:
      - status="in_progress" al empezar (visible inmediatamente por commit)
      - status="completed" al terminar

    Si la tarea se cancela, los pasos "in_progress" se limpian
    y se re-ejecutan en el siguiente intento (resume).
    """

    __tablename__ = "task_step_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_tasks.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentos.id"), nullable=True
    )

    step_name: Mapped[str] = mapped_column(String(100))
    # "a1_population_context" | "segmentation" | "anchoring" |
    # "a2_identify_process" | "extract_prime_mover" | "a3_make_sense" |
    # "b2_open_code" | "b3_hypotheses" | "punctuation" | etc.

    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # "in_progress" | "completed" | "failed"

    affected_rows: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Snapshot de lo que se insertó/modificó en este paso (para limpieza en resume)
    # Ej: {"table": "segmentos", "count": 45}


class BatchExecution(Base, TimestampMixin):
    """Registro de ejecución batch (Map-Reduce / fragmentación de contexto).

    Cuando los datos del proyecto exceden la ventana de contexto,
    se fragmentan en batches. Esta tabla registra cada ejecución batch
    para trazabilidad y debugging del ContextWindowManager.
    """

    __tablename__ = "batch_executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    agent_id: Mapped[str] = mapped_column(String(100))
    """Qué agente se ejecutó en batch (ej. 'open_coding', 'memo_proposer')."""

    total_items: Mapped[int] = mapped_column(Integer)
    """Total de items a procesar (segmentos, incidentes, memos)."""

    batches: Mapped[int] = mapped_column(Integer)
    """Número de batches en que se dividió el trabajo."""

    items_per_batch: Mapped[int] = mapped_column(Integer)
    """Items promedio por batch."""

    tokens_per_batch: Mapped[int] = mapped_column(Integer, default=0)
    """Tokens estimados por batch."""

    map_strategy: Mapped[str] = mapped_column(String(30))
    """Estrategia de Map: 'ai_only' | 'map_reduce' | 'hybrid_react'."""

    status: Mapped[str] = mapped_column(String(20), default="running")
    """Estado de la ejecución batch: 'running' | 'completed' | 'failed'."""

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Timestamp de inicio de la ejecución batch."""

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Timestamp de finalización de la ejecución batch."""
