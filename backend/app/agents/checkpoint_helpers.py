"""Checkpoint helpers compartidos para workers Celery.

Permite que las tareas escriban checkpoints por paso y puedan
resumir desde donde se quedaron tras una cancelación.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)


def checkpoint(session, documento_id: str, step: str, status: str) -> None:
    """Escribe un checkpoint de paso. Commit inmediato para visibilidad tras crash.

    Uso:
        checkpoint(s, doc_id, "a1_population_context", "in_progress")
        ... ejecutar paso ...
        checkpoint(s, doc_id, "a1_population_context", "completed")
    """
    session.execute(
        text(
            "INSERT INTO task_step_checkpoints "
            "(id, document_id, step_name, status, affected_rows) "
            "VALUES (gen_random_uuid(), :did, :step, :status, '{}'::jsonb)"
        ),
        {"did": documento_id, "step": step, "status": status},
    )
    session.commit()


def load_checkpoints(session, documento_id: str) -> tuple[set[str], set[str]]:
    """Carga checkpoints existentes para un documento.

    Returns:
        (completed_steps, dirty_steps) donde:
        - completed_steps: pasos ya terminados (saltar)
        - dirty_steps: pasos que quedaron "in_progress" (limpiar antes de re-ejecutar)
    """
    rows = session.execute(
        text(
            "SELECT step_name, status FROM task_step_checkpoints "
            "WHERE document_id = :did ORDER BY creado_en"
        ),
        {"did": documento_id},
    ).fetchall()

    completed = set()
    dirty = set()
    for row in rows:
        if row[1] == "completed":
            completed.add(row[0])
            dirty.discard(row[0])  # si había un in_progress previo, ya fue completado
        elif row[1] == "in_progress":
            if row[0] not in completed:
                dirty.add(row[0])

    return completed, dirty


def cleanup_step(session, step: str, documento_id: str) -> None:
    """Limpia datos parciales de un paso que quedó in_progress.

    Cada paso sabe qué tablas toca y cómo limpiarlas.
    """
    if step in ("segmentation", "a0_segmentation"):
        session.execute(
            text("DELETE FROM segmentos WHERE documento_id = :did"),
            {"did": documento_id},
        )
        logger.info(
            "Checkpoint cleanup: deleted partial segments for doc=%s", documento_id
        )

    elif step == "anchoring":
        session.execute(
            text(
                "UPDATE segmentos SET first_10 = NULL, start_char = NULL, "
                "end_char = NULL, is_exact_match = true WHERE documento_id = :did"
            ),
            {"did": documento_id},
        )
        logger.info("Checkpoint cleanup: reset anchors for doc=%s", documento_id)

    elif step == "a2_identify_process":
        session.execute(
            text("UPDATE segmentos SET parafrasis = NULL WHERE documento_id = :did"),
            {"did": documento_id},
        )
        logger.info("Checkpoint cleanup: reset parafrasis for doc=%s", documento_id)

    elif step in ("a3_make_sense", "sense_making"):
        session.execute(
            text("DELETE FROM document_processes WHERE documento_id = :did"),
            {"did": documento_id},
        )
        logger.info(
            "Checkpoint cleanup: deleted partial document_processes for doc=%s",
            documento_id,
        )

    elif step == "punctuation":
        # Revertir preprocesado (texto_extraido ya es inmutable)
        session.execute(
            text(
                "UPDATE documentos SET metadatos = "
                "metadatos - 'texto_preprocesado' - 'texto_puntuado' "
                "WHERE id = :did"
            ),
            {"did": documento_id},
        )
        logger.info(
            "Checkpoint cleanup: removed preprocessed text for doc=%s", documento_id
        )

    elif step == "a1_population_context":
        # population_contexts son por proyecto, no por doc. No limpiar.
        pass

    elif step in ("extract_prime_mover", "b2_open_code", "b3_hypotheses"):
        # Estos pasos son idempotentes (INSERT con verificacion previa)
        pass

    session.commit()
