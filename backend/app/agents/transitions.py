"""Transitions — ÚNICO módulo que modifica documentos.estado y despacha tareas.

Montado en workers vía docker-compose (./backend/app/agents:/app/agents:ro).

Principios:
- SOLO este módulo hace UPDATE documentos SET estado = ...
- SOLO este módulo despacha la siguiente tarea (con PipelineTask tracking)
- SOLO este módulo dispara Phase B (con deduplicación vía processing_states)
- Optimistic locking: WHERE estado = from_state previene race conditions

Workers llaman:
  transition(session, doc_id, proj_id, "segmentando", "segmentar_documento", True)
  transition(session, doc_id, proj_id, "procesando", "process_document_agents_a", True)
  transition(session, doc_id, proj_id, estado_actual, task_name, False)  # error
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# State machine: current_state → (next_state, next_task)
# ═══════════════════════════════════════════════════════════════════════

NEXT: dict[str, tuple[str, str | None, str | None]] = {
    # (estado_actual) → (next_state, next_task_name, queue)
    "crudo": ("segmentando", "segmentar_documento", "nlp"),
    "segmentando": ("segmentado", None, None),  # NLP actualiza al terminar
    "segmentado": ("procesando", "process_document_agents_a", "heavy"),
    "procesando": ("listo", None, None),  # heavy actualiza al terminar
    "listo": (None, None, None),  # terminal (open coding completado)
    "sintetizado": (None, None, None),  # terminal (cross-doc synthesis completada)
    "error": ("crudo", None, None),  # reset en retry
}

# Estados terminales (no se despacha nada después)
TERMINAL = {"listo", "sintetizado", "error"}

# ═══════════════════════════════════════════════════════════════════════
# Project state machine (nivel proyecto — post open coding)
# ═══════════════════════════════════════════════════════════════════════

PROJECT_STATES: dict[str, str] = {
    "collecting": "coding",
    "coding": "finding_cc",
    "finding_cc": "reducing",
    "reducing": "saturating",
    "saturating": "building_db",
    "building_db": "playground_ready",
    "playground_ready": "completed",
}


def transition(
    session,
    documento_id: str,
    proyecto_id: str,
    from_state: str,
    task_name: str,
    success: bool,
) -> dict | None:
    """Transiciona el estado de un documento y despacha la siguiente tarea.

    Args:
        session: SQLAlchemy session
        documento_id: UUID del documento
        proyecto_id: UUID del proyecto
        from_state: estado ACTUAL del documento (para optimistic lock)
        task_name: nombre de la tarea que acaba de terminar
        success: True si la tarea se completó, False si falló

    Returns:
        dict con next_task si se despachó algo, None si no.
    """
    if not success:
        return _to_error(session, documento_id)

    info = NEXT.get(from_state)
    if not info:
        logger.warning("Unknown state '%s' for doc=%s", from_state, documento_id)
        return None

    next_state, next_task, queue = info

    # ── 1. Transicionar estado (optimistic lock) ──
    if next_state:
        result = session.execute(
            text(
                "UPDATE documentos SET estado = :next "
                "WHERE id = :did AND estado = :current"
            ),
            {"next": next_state, "did": documento_id, "current": from_state},
        )
        session.commit()
        if result.rowcount == 0:
            logger.info("Doc %s already transitioned from %s", documento_id, from_state)
            return None
    else:
        # Sin next_state → terminal, no actualizar
        pass

    # ── 2. Despachar siguiente tarea ──
    if next_task and queue:
        return _dispatch_next(
            session,
            documento_id,
            proyecto_id,
            next_task,
            queue,
            next_state or from_state,
        )

    # ── 3. Si llegó a listo, verificar Phase B ──
    if next_state == "listo":
        return _maybe_trigger_phase_b(session, proyecto_id)

    return None


# ═══════════════════════════════════════════════════════════════════════
# Internal
# ═══════════════════════════════════════════════════════════════════════


def _to_error(session, documento_id: str) -> None:
    """Marca documento como error."""
    session.rollback()  # clear any previously aborted transaction
    session.execute(
        text("UPDATE documentos SET estado = 'error' WHERE id = :did"),
        {"did": documento_id},
    )
    session.commit()


def _dispatch_next(
    session,
    documento_id: str,
    proyecto_id: str,
    task_name: str,
    queue: str,
    doc_estado_before: str,
) -> dict | None:
    """Despacha una tarea Celery y crea PipelineTask tracking."""
    import os as _os

    from celery import Celery

    app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))

    # Despachar según tipo de tarea
    if task_name == "segmentar_documento":
        texto = _get_texto(session, documento_id)
        if not texto:
            return None
        task = app.send_task(
            task_name,
            args=[texto, 1024, "", "TEXTO", "", documento_id],
            queue=queue,
        )
    else:
        task = app.send_task(
            task_name,
            args=[documento_id, proyecto_id],
            queue=queue,
        )

    # Tracking: buscar PipelineRun activo
    run_id = _get_active_run(session, proyecto_id)
    if run_id:
        session.execute(
            text(
                "INSERT INTO pipeline_tasks "
                "(id, run_id, document_id, celery_task_id, task_name, queue, status, doc_estado_before, segments_before, codes_before) "
                "VALUES (gen_random_uuid(), :rid, :did, :tid, :tn, :q, 'queued', :before, 0, 0)"
            ),
            {
                "rid": run_id,
                "did": documento_id,
                "tid": task.id,
                "tn": task_name,
                "q": queue,
                "before": doc_estado_before,
            },
        )
        session.commit()

    logger.info("Dispatched %s for doc=%s (task=%s)", task_name, documento_id, task.id)
    return {"next_task": task_name, "task_id": task.id}


def _maybe_trigger_phase_b(session, proyecto_id: str) -> dict | None:
    """Dispara Phase B si >= 3 docs listos y no se disparó ya."""
    listos = session.execute(
        text(
            "SELECT COUNT(*) FROM documentos "
            "WHERE proyecto_id = :pid AND estado = 'listo'"
        ),
        {"pid": proyecto_id},
    ).fetchone()[0]

    if listos < 3:
        return None

    step = f"phase_b_dc_{listos}"
    already = session.execute(
        text(
            "SELECT step FROM processing_states "
            "WHERE entity_type = 'project' AND entity_id = :pid AND step = :step"
        ),
        {"pid": proyecto_id, "step": step},
    ).fetchone()

    if already:
        return None

    # Marcar ANTES de despachar (previene race condition)
    session.execute(
        text(
            "INSERT INTO processing_states (entity_type, entity_id, step) "
            "VALUES ('project', :pid, :step) ON CONFLICT DO NOTHING"
        ),
        {"pid": proyecto_id, "step": step},
    )
    session.commit()

    import os as _os

    from celery import Celery

    app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))
    task = app.send_task(
        "process_synthesis_agents_b",
        args=[proyecto_id],
        queue="heavy",
    )

    logger.info(
        "Phase B triggered: project=%s (%d docs listos, task=%s)",
        proyecto_id,
        listos,
        task.id,
    )
    return {"next_task": "process_synthesis_agents_b", "task_id": task.id}


def _get_active_run(session, proyecto_id: str) -> str | None:
    """Busca el PipelineRun activo para el proyecto."""
    row = session.execute(
        text(
            "SELECT id FROM pipeline_runs "
            "WHERE project_id = :pid AND status = 'running' "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"pid": proyecto_id},
    ).fetchone()
    return str(row[0]) if row else None


def _get_texto(session, documento_id: str) -> str:
    """Obtiene el texto extraído de un documento."""
    row = session.execute(
        text("SELECT metadatos FROM documentos WHERE id = :did"),
        {"did": documento_id},
    ).fetchone()
    if row and row[0]:
        meta = row[0] if isinstance(row[0], dict) else {}
        return meta.get("texto_extraido", "")
    return ""


# ═══════════════════════════════════════════════════════════════════════
# Project-level transitions (para el selective coding coordinator)
# ═══════════════════════════════════════════════════════════════════════


def transition_project(
    session,
    proyecto_id: str,
    from_state: str,
    to_state: str,
) -> bool:
    """Transiciona el estado de un proyecto con optimistic locking.

    Usado por el selective_coding_coordinator para avanzar entre fases.
    No afecta el pipeline de documentos (transition() tradicional).

    Returns:
        True si la transición se aplicó, False si otro proceso ya transicionó.
    """
    result = session.execute(
        text(
            "UPDATE proyectos SET estado = :next WHERE id = :pid AND estado = :current"
        ),
        {"next": to_state, "pid": proyecto_id, "current": from_state},
    )
    session.commit()
    if result.rowcount == 0:
        logger.warning(
            "Project %s already transitioned from %s (expected %s)",
            proyecto_id,
            from_state,
            to_state,
        )
        return False
    logger.info("Project %s: %s → %s", proyecto_id, from_state, to_state)
    return True


def hitl_gate(
    session,
    project_id: str,
    gate_name: str,
    proposal: dict,
    critic_verdict: dict,
) -> str:
    """Guarda una decisión HITL pendiente y notifica al frontend.

    REGLA 0.1 — Todo paso de decisión teórica requiere HITL.
    El pipeline se PAUSA aquí. El coordinator espera a que el investigador
    decida vía el endpoint POST /projects/{id}/hitl/{gate}/decide.

    Returns:
        'pending' — la decisión queda a la espera.
        El resultado real (accepted/modified/rejected) se obtiene
        consultando hitl_decisions periódicamente.
    """
    import json

    session.execute(
        text(
            "INSERT INTO hitl_decisions "
            "(id, project_id, gate_name, proposal, critic_verdict, status) "
            "VALUES (gen_random_uuid(), :pid, :gate, :prop, :verdict, 'pending')"
        ),
        {
            "pid": project_id,
            "gate": gate_name,
            "prop": json.dumps(proposal, ensure_ascii=False),
            "verdict": json.dumps(critic_verdict, ensure_ascii=False),
        },
    )
    session.commit()

    # Notificar frontend vía Redis pub/sub
    try:
        import redis as _redis

        r = _redis.from_url("redis://redis:6379", decode_responses=True)
        payload = json.dumps(
            {
                "type": "hitl_required",
                "gate": gate_name,
                "proposal": proposal,
                "critic_verdict": critic_verdict,
            },
            ensure_ascii=False,
        )
        r.publish(f"project:{project_id}:events", payload)
    except Exception as e:
        logger.warning("Failed to publish hitl_required event: %s", e)

    logger.info(
        "HITL gate '%s' for project=%s: proposal saved, awaiting researcher decision",
        gate_name,
        project_id,
    )
    return "pending"


def _maybe_trigger_selective_coding(session, proyecto_id: str) -> dict | None:
    """Dispara el selective_coding_coordinator cuando todos los docs están sintetizados.

    Análogo a _maybe_trigger_phase_b pero para la transición
    open coding → selective coding.
    """
    import os as _os

    from celery import Celery

    sintetizados = session.execute(
        text(
            "SELECT COUNT(*) FROM documentos "
            "WHERE proyecto_id = :pid AND estado = 'sintetizado'"
        ),
        {"pid": proyecto_id},
    ).fetchone()[0]

    total = session.execute(
        text("SELECT COUNT(*) FROM documentos WHERE proyecto_id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()[0]

    if sintetizados < total or total == 0:
        return None

    step = f"selective_coding_dc_{sintetizados}"
    already = session.execute(
        text(
            "SELECT step FROM processing_states "
            "WHERE entity_type = 'project' AND entity_id = :pid AND step = :step"
        ),
        {"pid": proyecto_id, "step": step},
    ).fetchone()

    if already:
        return None

    session.execute(
        text(
            "INSERT INTO processing_states (entity_type, entity_id, step) "
            "VALUES ('project', :pid, :step) ON CONFLICT DO NOTHING"
        ),
        {"pid": proyecto_id, "step": step},
    )
    session.commit()

    app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))
    task = app.send_task(
        "selective_coding_coordinator",
        args=[proyecto_id],
        queue="heavy",
    )

    logger.info(
        "Selective coding triggered: project=%s (%d docs sintetizados, task=%s)",
        proyecto_id,
        sintetizados,
        task.id,
    )
    return {"next_task": "selective_coding_coordinator", "task_id": task.id}
