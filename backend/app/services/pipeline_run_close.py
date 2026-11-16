"""Cierre de ``pipeline_runs`` desde el propio worker, al terminar la tarea.

``app.services.pipeline_state.close_finished_runs`` ya reconcilia en cada
``GET /pipeline/log``, pero eso solo ocurre mientras alguien mira el proyecto:
si el usuario cierra la pestaña, el último run de la sesión se queda 'running'
para siempre y el botón "cerrar ejecución anterior" reaparece al volver.

Este módulo registra un handler de ``task_postrun`` en cada worker: al terminar
una tarea comprueba si quedan hermanas en vuelo dentro del mismo run y, si no
queda ninguna, cierra el run. Un run puede hospedar varias tareas, así que la
comprobación de hermanas es imprescindible: cerrar al terminar la primera tarea
cortaría un run que sigue trabajando.

Es **síncrono y con psycopg2** a propósito: las imágenes de los workers no
instalan asyncpg y Celery es síncrono. Se usa desde
``workers/{heavy,nlp,fast}/tasks.py`` con ``register_run_close_hook(app)``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Estados en los que una tarea hermana aún no ha terminado.
_ACTIVE_STATES = ("PENDING", "STARTED", "RETRY", "RECEIVED")

# Si no se pudo preguntar a Celery, no se cierra nada.
_UNKNOWN_STATE = "UNKNOWN"

_OPEN_STATES = (*_ACTIVE_STATES, _UNKNOWN_STATE)

# Misma ventana que ``pipeline_state``: más allá, Celery ya olvidó el task id y
# respondería 'PENDING' para siempre.
_ACTIVE_WINDOW = timedelta(hours=4)

# Un run recién abierto está recibiendo sus tareas una a una desde la API. Si la
# primera termina antes de que se despache la última, cerraríamos un run que aún
# no ha visto todas sus tareas: este margen cubre el despacho en curso.
_MIN_RUN_AGE_S = 30

# Estado final del run, heredado del peor estado de sus tareas.
_CLOSE_STATUS_CASE = (
    "CASE "
    "  WHEN EXISTS (SELECT 1 FROM pipeline_tasks pt "
    "               WHERE pt.run_id = pr.id AND pt.status = 'cancelled') "
    "    THEN 'cancelled' "
    "  WHEN EXISTS (SELECT 1 FROM pipeline_tasks pt "
    "               WHERE pt.run_id = pr.id AND pt.status = 'failed') "
    "    THEN 'failed' "
    "  ELSE 'completed' END"
)

_session_factory: Any = None


def _session() -> Any:
    """Sesión síncrona propia. El engine se crea al primer uso (por proceso)."""
    global _session_factory
    if _session_factory is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        url = os.getenv("DATABASE_URL", "")
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        if url and not url.startswith("postgresql+psycopg2"):
            # SQLAlchemy >= 2.1 resolvería 'postgresql://' a psycopg v3, que las
            # imágenes de los workers no instalan (mismo motivo que en nlp).
            url = url.replace("postgresql://", "postgresql+psycopg2://")
        engine = create_engine(url, pool_size=1, max_overflow=1, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=engine)
    return _session_factory()


def _celery_states(celery_app: Any, task_ids: list[str]) -> dict[str, str]:
    from celery.result import AsyncResult

    states: dict[str, str] = {}
    for task_id in task_ids:
        try:
            states[task_id] = AsyncResult(task_id, app=celery_app).status
        except Exception:
            states[task_id] = _UNKNOWN_STATE
    return states


def close_run_if_finished(
    celery_app: Any, task_id: str | None, *, min_age_s: int = _MIN_RUN_AGE_S
) -> bool:
    """Cierra el run de ``task_id`` si esa era su última tarea viva.

    Devuelve True solo si ha cerrado el run. Cualquier error se registra y se
    ignora: el gancho nunca debe romper una tarea.
    """
    if not task_id:
        return False

    session = _session()
    try:
        row = session.execute(
            text(
                "SELECT pt.run_id, pr.status, pr.creado_en "
                "FROM pipeline_tasks pt "
                "JOIN pipeline_runs pr ON pr.id = pt.run_id "
                "WHERE pt.celery_task_id = :tid"
            ),
            {"tid": task_id},
        ).fetchone()
        if row is None:
            return False

        run_id, run_status, run_created = row
        if run_status != "running":
            return False

        if run_created is not None:
            created = (
                run_created
                if run_created.tzinfo
                else run_created.replace(tzinfo=timezone.utc)
            )
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=min_age_s)
            if created > cutoff:
                return False

        siblings = [
            tid
            for tid in session.execute(
                text(
                    "SELECT celery_task_id FROM pipeline_tasks "
                    "WHERE run_id = :rid AND celery_task_id <> :tid "
                    "AND creado_en > now() - CAST(:window AS interval)"
                ),
                {"rid": run_id, "tid": task_id, "window": _ACTIVE_WINDOW},
            ).scalars()
            if tid
        ]
        if siblings:
            states = _celery_states(celery_app, siblings)
            if any(states.get(tid) in _OPEN_STATES for tid in siblings):
                return False

        result = session.execute(
            text(
                f"UPDATE pipeline_runs pr SET status = {_CLOSE_STATUS_CASE}, "
                "  actualizado_en = now() "
                "WHERE pr.id = :rid AND pr.status = 'running'"
            ),
            {"rid": run_id},
        )
        session.commit()
        return bool(result.rowcount)
    except Exception:
        session.rollback()
        logger.warning(
            "No se pudo cerrar el run de la tarea %s", task_id, exc_info=True
        )
        return False
    finally:
        session.close()


def register_run_close_hook(
    celery_app: Any, *, min_age_s: int = _MIN_RUN_AGE_S
) -> None:
    """Cuelga el cierre de runs del ``task_postrun`` del worker."""
    from celery.signals import task_postrun

    def _on_task_postrun(task_id: str | None = None, **_kwargs: Any) -> None:
        # Sin log de éxito a propósito: ``worker-nlp`` reenvía cada INFO al log
        # de pipeline que ve el usuario en la UI, y una línea por run con un
        # uuid no aporta nada ahí. El resultado se ve en el estado del run.
        close_run_if_finished(celery_app, task_id, min_age_s=min_age_s)

    task_postrun.connect(_on_task_postrun, weak=False)
    logger.debug("Gancho de cierre de pipeline_runs registrado")
