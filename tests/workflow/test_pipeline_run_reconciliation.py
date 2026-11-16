"""Regresión: un run terminado no puede quedarse en 'running' para siempre.

``pipeline_runs`` se inserta como 'running' y solo lo cerraban el despacho del
paso siguiente, los endpoints de memos o el botón manual. El último run de cada
sesión de trabajo, por tanto, seguía abierto con el pipeline ya parado, y la UI
mostraba "Cerrar ejecución anterior" aunque todos los documentos hubieran
terminado.

``GET /pipeline/log`` ahora reconcilia contra Celery antes de contar
``summary.open_runs``: cierra los runs cuyas tareas ya no están en vuelo y solo
deja abiertos los que tienen alguna tarea viva (o cuyo estado no se pudo leer).

El test solo escribe en un proyecto desechable (``temp_project``) y borra sus
filas al terminar, para que el borrado del proyecto en el teardown no choque con
la FK de ``pipeline_runs``.
"""

from __future__ import annotations

import uuid

import pytest

LOG = "/api/v1/projects/{pid}/pipeline/log"

# Un run sin tareas es el caso del run huérfano: nada puede estar en vuelo.
_INSERT_RUN = (
    "INSERT INTO pipeline_runs "
    "  (id, project_id, status, triggered_by, summary, creado_en, actualizado_en) "
    "VALUES ('{run_id}', '{pid}', 'running', 'user', '{{}}'::jsonb, {when}, {when})"
)


def _insert_run(query, project_id: str, when: str) -> str:
    run_id = str(uuid.uuid4())
    query(_INSERT_RUN.format(run_id=run_id, pid=project_id, when=when))
    return run_id


def _statuses(query, project_id: str) -> dict[str, str]:
    rows = query(
        f"SELECT id, status FROM pipeline_runs WHERE project_id = '{project_id}'"
    )
    return dict(line.split("|") for line in rows.splitlines() if line)


@pytest.fixture
def _throwaway_run_project(temp_project: str, uploaded_doc: dict) -> str:
    """Proyecto desechable con un documento: /pipeline/log sin docs no reconcilia."""
    return temp_project


def test_finished_run_is_closed_when_log_is_polled(
    _throwaway_run_project: str, api, db
) -> None:
    stale = _insert_run(db, _throwaway_run_project, "now() - interval '5 minutes'")
    try:
        resp = api.get(LOG.format(pid=_throwaway_run_project))
        assert resp.status_code == 200, resp.text

        assert _statuses(db, _throwaway_run_project)[stale] == "completed"
        assert resp.json()["summary"]["open_runs"] == 0
    finally:
        db(f"DELETE FROM pipeline_runs WHERE project_id = '{_throwaway_run_project}'")


def test_run_inside_the_grace_window_is_left_open(
    _throwaway_run_project: str, api, db
) -> None:
    """Entre el INSERT del run y el de sus tareas hay un hueco: no tocar recientes."""
    fresh = _insert_run(db, _throwaway_run_project, "now()")
    try:
        resp = api.get(LOG.format(pid=_throwaway_run_project))
        assert resp.status_code == 200, resp.text

        assert _statuses(db, _throwaway_run_project)[fresh] == "running"
        assert resp.json()["summary"]["open_runs"] == 1
    finally:
        db(f"DELETE FROM pipeline_runs WHERE project_id = '{_throwaway_run_project}'")
