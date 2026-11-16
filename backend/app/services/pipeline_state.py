"""Estado real de ejecución del pipeline de un proyecto.

``pipeline_runs.status`` no es de fiar por sí solo: los runs se crean como
'running' y solo se cierran al despachar el paso siguiente, al tocar memos o
cuando alguien reconcilia a mano. Un run cuyo trabajo ya terminó, por tanto,
deja el proyecto marcado como "pipeline en ejecución" hasta que ocurre una de
esas cosas. ``pipeline_tasks`` tampoco sirve: sus filas se insertan como 'queued'
y nadie las mueve (ver el comentario de ``get_pipeline_log``).

La única fuente fiable es el result backend de Celery, que es la misma que usa
``GET /pipeline/log`` para pintar los spinners de los agentes. Este módulo es el
único sitio que debe preguntar "¿está el pipeline trabajando?", y además
reconcilia los runs colgados para que la columna se autocure.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Estados en los que la tarea aún no ha terminado.
_ACTIVE_STATES = ("PENDING", "STARTED", "RETRY", "RECEIVED")

# Si no se pudo preguntar a Celery (Redis caído), no se cierra nada: es
# preferible un run fantasma a cerrar uno que sí estaba trabajando.
_UNKNOWN_STATE = "UNKNOWN"

_OPEN_STATES = (*_ACTIVE_STATES, _UNKNOWN_STATE)

# Ventana para descartar filas huérfanas de runs abandonados: Celery olvida los
# task ids viejos (``result_expires``) y responderían 'PENDING' para siempre.
# Es la misma ventana que usa /pipeline/log, para que ambos endpoints coincidan.
# Se pasa como parámetro: asyncpg solo acepta ``timedelta`` para ``interval``.
_ACTIVE_WINDOW = timedelta(hours=4)

# ``PENDING`` es el único estado ambiguo: Celery lo responde también para un id
# que nunca vio (tarea encolada que ningún worker tomó, o cuyo worker murió).
# Una cadena real siempre tiene alguna tarea en STARTED, así que "todo PENDING"
# significa cola trabada o fantasma. Pasado este margen se presume perdida y
# deja de bloquear la curación manual; antes bloqueaba hasta agotar las 4 h.
_PENDING_GRACE = timedelta(minutes=15)

# Un run recién insertado todavía no tiene sus tareas registradas (se crean unas
# líneas después en otra transacción). No se reconcilia hasta pasado este margen.
_MIN_RUN_AGE_S = 60

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


def _celery_states(task_ids: list[str]) -> dict[str, str]:
    """Resuelve el estado de cada tarea contra Redis. Bloquea: usar to_thread."""
    from app.core.celery_app import celery_app
    from celery.result import AsyncResult

    states: dict[str, str] = {}
    for tid in task_ids:
        try:
            states[tid] = AsyncResult(tid, app=celery_app).status
        except Exception:
            states[tid] = _UNKNOWN_STATE
    return states


def _as_utc(value: datetime) -> datetime:
    """Normaliza a UTC las columnas ``timestamp`` sin zona horaria."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _active_task_ids(db: AsyncSession, project_id: UUID) -> list[str] | None:
    """Celery task ids de los runs abiertos que siguen en vuelo.

    Devuelve ``None`` si no se pudo consultar la BD: quien llama debe tratarlo
    como "puede estar corriendo".

    El estado se interpreta así:

    * ``STARTED`` / ``RECEIVED`` / ``RETRY``: trabajo en vuelo, sin discusión.
    * ``PENDING``: sólo cuenta dentro de ``_PENDING_GRACE`` (ver constante).
    * ``UNKNOWN`` (Redis no responde): cuenta como en vuelo, para que la
      escritura manual no compita con un agente que quizá sí está escribiendo.
    """
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT pt.celery_task_id, pt.creado_en FROM pipeline_tasks pt "
                    "JOIN pipeline_runs pr ON pr.id = pt.run_id "
                    "WHERE pr.project_id = :pid "
                    "AND pr.status = 'running' "
                    "AND pt.creado_en > now() - CAST(:window AS interval) "
                    "ORDER BY pt.creado_en DESC "
                    "LIMIT 50"
                ),
                {"pid": str(project_id), "window": _ACTIVE_WINDOW},
            )
        ).all()
    except Exception:
        logger.warning(
            "No se pudo consultar el estado del pipeline de %s",
            project_id,
            exc_info=True,
        )
        return None

    tasks = [(row[0], row[1]) for row in rows if row[0]]
    if not tasks:
        return []

    states = await asyncio.to_thread(_celery_states, [tid for tid, _ in tasks])

    now = datetime.now(timezone.utc)
    active: list[str] = []
    for task_id, created in tasks:
        state = states.get(task_id)

        if state == "PENDING":
            age = now - _as_utc(created) if created else None
            if age is not None and age > _PENDING_GRACE:
                logger.info(
                    "Tarea %s sigue PENDING tras %s: se presume perdida y no "
                    "bloquea la curación de %s",
                    task_id,
                    age,
                    project_id,
                )
                continue
            active.append(task_id)
        elif state == _UNKNOWN_STATE or state in _ACTIVE_STATES:
            if state == _UNKNOWN_STATE:
                logger.warning("Redis no responde por %s: se asume en vuelo", task_id)
            active.append(task_id)

    return active


async def _commit_preserving_objects(db: AsyncSession) -> None:
    """Commit sin expirar los ORM ya cargados en la sesión.

    ``get_pipeline_log`` reconcilia a mitad de request con instancias de
    ``Documento`` vivas: expirarlas forzaría un lazy-load async y reventaría con
    ``MissingGreenlet``.
    """
    sync = db.sync_session
    previous = sync.expire_on_commit
    sync.expire_on_commit = False
    try:
        await db.commit()
    finally:
        sync.expire_on_commit = previous


async def _close_runs(db: AsyncSession, run_ids: list[UUID]) -> int:
    """Cierra los runs indicados heredando el peor estado de sus tareas."""
    if not run_ids:
        return 0

    placeholders = ", ".join(f"CAST(:id{i} AS uuid)" for i in range(len(run_ids)))
    params = {f"id{i}": str(rid) for i, rid in enumerate(run_ids)}
    result = await db.execute(
        text(
            f"UPDATE pipeline_runs pr SET status = {_CLOSE_STATUS_CASE}, "
            "  actualizado_en = now() "
            f"WHERE pr.id IN ({placeholders}) AND pr.status = 'running'"
        ),
        params,
    )
    return result.rowcount or 0


async def _mark_open_runs_closed(db: AsyncSession, project_id: UUID) -> int:
    """Cierra los runs 'running' del proyecto heredando el peor estado de sus tareas."""
    result = await db.execute(
        text(
            f"UPDATE pipeline_runs pr SET status = {_CLOSE_STATUS_CASE}, "
            "  actualizado_en = now() "
            "WHERE pr.project_id = :pid AND pr.status = 'running'"
        ),
        {"pid": str(project_id)},
    )
    await _commit_preserving_objects(db)
    return result.rowcount or 0


async def close_finished_runs(
    db: AsyncSession, project_id: UUID, *, min_age_s: int = _MIN_RUN_AGE_S
) -> tuple[int, int] | None:
    """Cierra los runs 'running' cuyo trabajo ya terminó.

    Devuelve ``(cerrados, abiertos)`` después de reconciliar, o ``None`` si no se
    pudo leer el estado real: quien llama debe caer al conteo crudo antes que
    cerrar a ciegas.

    Un run se cierra cuando ninguna de sus tareas sigue en vuelo según Celery.
    Las tareas fuera de ``_ACTIVE_WINDOW`` se ignoran (Celery ya las olvidó) y los
    runs todavía sin tareas más nuevos que ``min_age_s`` no se tocan, porque sus
    tareas aún no están registradas (el INSERT del run y el de sus tareas van en
    transacciones distintas). En cuanto un run tiene tareas, se evalúa al momento:
    no hay nada que esperar.

    No modifica ``pipeline_tasks.status``: ``get_pipeline_log`` deriva de esas
    filas los agentes ↻/▶ de la UI.
    """
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT pr.id, pr.creado_en, pt.celery_task_id, "
                    "  pt.creado_en > now() - CAST(:window AS interval) AS recent "
                    "FROM pipeline_runs pr "
                    "LEFT JOIN pipeline_tasks pt ON pt.run_id = pr.id "
                    "WHERE pr.project_id = :pid AND pr.status = 'running'"
                ),
                {"pid": str(project_id), "window": _ACTIVE_WINDOW},
            )
        ).all()
    except Exception:
        logger.warning(
            "No se pudieron reconciliar los runs de %s", project_id, exc_info=True
        )
        return None

    if not rows:
        return (0, 0)

    run_created: dict[UUID, datetime | None] = {}
    run_tasks: dict[UUID, list[str]] = {}
    for run_id, created, celery_task_id, recent in rows:
        run_created[run_id] = created
        task_ids = run_tasks.setdefault(run_id, [])
        # ``recent`` es NULL cuando el run no tiene tareas: se descarta igual.
        if celery_task_id and recent:
            task_ids.append(celery_task_id)

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=min_age_s)
    settled = [
        run_id
        for run_id, created in run_created.items()
        if run_tasks[run_id] or created is None or _as_utc(created) <= cutoff
    ]

    pending_ids = [tid for run_id in settled for tid in run_tasks[run_id]]
    states = await asyncio.to_thread(_celery_states, pending_ids) if pending_ids else {}

    finished = [
        run_id
        for run_id in settled
        if not any(states.get(tid) in _OPEN_STATES for tid in run_tasks[run_id])
    ]

    closed = await _close_runs(db, finished)
    if closed:
        await _commit_preserving_objects(db)
        logger.info("Reconciled %d finished pipeline run(s) for %s", closed, project_id)

    return (closed, len(run_created) - closed)


async def pipeline_really_running(
    db: AsyncSession, project_id: UUID, *, heal: bool = False
) -> bool:
    """¿Hay trabajo del pipeline en vuelo de verdad para este proyecto?

    Con ``heal=True`` cierra además los runs que quedaron marcados 'running' sin
    tarea activa, de modo que la columna se corrige sola en cuanto alguien mira
    el proyecto (no hay proceso periódico que barra runs huérfanos).

    Ante cualquier duda responde True: es preferible bloquear una escritura
    manual de más que competir con un agente que está escribiendo.
    """
    active = await _active_task_ids(db, project_id)
    if active is None or active:
        return True

    if heal:
        closed = await _mark_open_runs_closed(db, project_id)
        if closed:
            logger.info(
                "Reconciled %d stale pipeline run(s) for %s", closed, project_id
            )
    return False


async def close_idle_runs(db: AsyncSession, project_id: UUID) -> int:
    """Cierra los runs abiertos que no tienen ninguna tarea en vuelo.

    No revoca tareas ni toca documentos (a diferencia de
    ``POST /admin/projects/{id}/stop``): solo arregla la columna ``status``.
    Devuelve cuántos runs cerró.
    """
    if await _active_task_ids(db, project_id):
        return 0
    return await _mark_open_runs_closed(db, project_id)
