"""Static contracts for the worker-side ``pipeline_runs`` close hook.

Why static?
-----------
pytest is not installed inside the worker images and the host does not have the
workers' runtime dependencies, so importing ``app.services.pipeline_run_close``
(pulls SQLAlchemy) or ``workers.*.tasks`` (pulls celery) is not an option. As in
``test_workers_tasks.py``, the sources are parsed with ``ast`` instead.

What is pinned
--------------
1. The hook is registered by all three workers, *after* their ``Celery`` app
   exists and inside a guarded import: a broken hook must never stop tasks from
   being registered.
2. The three properties that make the hook safe:
   - it ignores its own task when looking for siblings, so a run that still has
     work in flight is not closed by the first task that finishes;
   - a freshly opened run is protected, because the API dispatches its tasks one
     by one and the first one can finish before the last is recorded;
   - a Celery lookup that answers UNKNOWN (Redis down) blocks the close.
3. It only updates rows that are still 'running' (idempotent with the API-side
   reconciliation in ``pipeline_state.close_finished_runs``) and never writes
   ``pipeline_tasks.status``, from which the UI derives the ↻/▶ controls.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

HOOK = ROOT / "backend" / "app" / "services" / "pipeline_run_close.py"
WORKER_TASKS = (
    ROOT / "workers" / "fast" / "tasks.py",
    ROOT / "workers" / "heavy" / "tasks.py",
    ROOT / "workers" / "nlp" / "tasks.py",
)

REQUIRED_FUNCTIONS = ("close_run_if_finished", "register_run_close_hook")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path))


def _module_functions(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _module_constants(tree: ast.Module) -> dict[str, ast.expr]:
    constants: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                constants[target.id] = node.value
    return constants


def _celery_app_lineno(tree: ast.Module) -> int:
    """Línea del ``Celery(...)`` del worker."""
    lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Celery"
    ]
    assert lines, "el worker ya no construye una app de Celery"
    return max(lines)


def _guarded_hook_registration(tree: ast.Module) -> int | None:
    """Línea del ``register_run_close_hook(app)`` dentro de un ``try``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        dump = ast.dump(ast.Module(body=node.body, type_ignores=[]))
        if "pipeline_run_close" not in dump or "register_run_close_hook" not in dump:
            continue
        for inner in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if isinstance(func, ast.Name) and func.id == "register_run_close_hook":
                return inner.lineno
    return None


def test_the_hook_module_keeps_its_public_surface() -> None:
    tree = _tree(HOOK)
    missing = set(REQUIRED_FUNCTIONS) - _module_functions(tree)
    assert not missing, f"faltan funciones en {HOOK.name}: {sorted(missing)}"


def test_every_worker_registers_the_hook_after_building_its_app() -> None:
    for path in WORKER_TASKS:
        tree = _tree(path)
        lineno = _guarded_hook_registration(tree)
        assert lineno is not None, (
            f"{path.name} no registra el cierre de runs dentro de un try/except"
        )
        assert lineno > _celery_app_lineno(tree), (
            f"{path.name} registra el hook antes de crear la app de Celery"
        )


def test_hook_ignores_its_own_task_when_looking_for_siblings() -> None:
    source = _source(HOOK)
    assert "celery_task_id <> :tid" in source, (
        "sin excluir la tarea actual, el run se cerraría al terminar la primera "
        "tarea aunque queden hermanas en vuelo"
    )


def test_hook_protects_a_freshly_opened_run() -> None:
    constants = _module_constants(_tree(HOOK))
    min_age = constants.get("_MIN_RUN_AGE_S")
    assert isinstance(min_age, ast.Constant) and min_age.value > 0, (
        "falta el margen que protege un run recién abierto"
    )


def test_unknown_celery_state_blocks_the_close() -> None:
    tree = _tree(HOOK)
    constants = _module_constants(tree)
    unknown = constants.get("_UNKNOWN_STATE")
    open_states = constants.get("_OPEN_STATES")
    assert isinstance(unknown, ast.Constant), "_UNKNOWN_STATE debe ser una constante"
    assert open_states is not None, "falta _OPEN_STATES"
    names = {node.id for node in ast.walk(open_states) if isinstance(node, ast.Name)}
    assert "_UNKNOWN_STATE" in names, (
        "si Celery no responde (Redis caído) no se puede cerrar a ciegas"
    )


def test_hook_only_closes_running_runs_and_never_touches_task_status() -> None:
    source = _source(HOOK)
    assert "AND pr.status = 'running'" in source, (
        "el cierre tiene que ser idempotente con la reconciliación de la API"
    )
    assert "UPDATE pipeline_tasks" not in source, (
        "pipeline_tasks.status alimenta los ↻/▶ de la UI: no se toca desde aquí"
    )
