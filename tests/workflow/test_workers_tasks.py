"""Static (AST-based) contracts for the worker tasks behind the document pipeline.

Why static?
-----------
pytest is not installed inside the worker images, and the host does not have the
workers' runtime dependencies (celery, sqlalchemy, redis). Importing
``workers.fast.tasks`` or ``workers.heavy.tasks`` from the test process would
fail before a single assertion ran. These tests parse the source files with
``ast`` and assert on their structure instead: Celery task names, signatures,
SQL persistence, and exception re-raises.

The suite is fast and hermetic: no stack, no network, no LLM call.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FAST_TASKS = ROOT / "workers" / "fast" / "tasks.py"
HEAVY_TASKS = ROOT / "workers" / "heavy" / "tasks.py"
GLASER_CLASSIFIER = ROOT / "workers" / "heavy" / "glaser_classifier.py"
DOCUMENTS_API = ROOT / "backend" / "app" / "api" / "v1" / "documents.py"

EXPECTED_WORKER_FILES = (FAST_TASKS, HEAVY_TASKS, GLASER_CLASSIFIER)

_TRY_NODES: tuple[type[ast.AST], ...] = (ast.Try,)
if hasattr(ast, "TryStar"):  # Python >= 3.11
    _TRY_NODES += (ast.TryStar,)


# ── Parsing helpers ────────────────────────────────────────────────────


@functools.lru_cache(maxsize=None)
def _read(path: Path) -> tuple[str, ast.Module]:
    """Return ``(source, parsed tree)`` for ``path``, parsed once per session."""
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source, filename=str(path))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    raise AssertionError(f"Function {name!r} not found in parsed module")


def _task_decorator(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> ast.Call | None:
    """Return the ``@app.task(...)`` call decorating ``func``, if any."""
    for decorator in func.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "task"
        ):
            return decorator
    return None


def _keyword(call: ast.Call, name: str) -> ast.keyword | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw
    return None


def _keyword_value(call: ast.Call, name: str):
    """Return the literal value of keyword ``name``, or ``None`` if absent."""
    kw = _keyword(call, name)
    if kw is None or not isinstance(kw.value, ast.Constant):
        return None
    return kw.value.value


def _task_names(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map every Celery ``name=...`` declared with ``@app.task`` to its function."""
    names: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorator = _task_decorator(node)
        if decorator is None:
            continue
        name = _keyword_value(decorator, "name")
        if isinstance(name, str):
            names[name] = node
    return names


def _send_task_calls(tree: ast.Module) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "send_task"
        ):
            calls.append(node)
    return calls


def _send_task_name(call: ast.Call) -> str | None:
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _dispatched_names(tree: ast.Module) -> set[str]:
    return {
        name
        for call in _send_task_calls(tree)
        if (name := _send_task_name(call)) is not None
    }


def _send_task_call_for(tree: ast.Module, name: str) -> ast.Call | None:
    for call in _send_task_calls(tree):
        if _send_task_name(call) == name:
            return call
    return None


def _function_source(source: str, func: ast.AST) -> str:
    segment = ast.get_source_segment(source, func)
    assert segment is not None, (
        "ast.get_source_segment returned None; the file was likely parsed with "
        "a different source string"
    )
    return segment


def _squash(text: str) -> str:
    """Drop all whitespace so SQL/formatting changes do not break the test."""
    return re.sub(r"\s+", "", text)


# ── Exception / scope helpers ──────────────────────────────────────────


def _walk_without_nested_scope(node: ast.AST):
    """Walk ``node``'s descendants, stopping at nested function/class scopes."""
    scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        if isinstance(current, scopes):
            continue
        yield current
        stack.extend(ast.iter_child_nodes(current))


def _exception_handlers(try_stmt: ast.AST) -> list[ast.ExceptHandler]:
    return [
        handler
        for handler in try_stmt.handlers
        if isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
    ]


def _direct_tries(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.AST]:
    """Only ``try`` statements that are direct statements of the function body."""
    return [stmt for stmt in func.body if isinstance(stmt, _TRY_NODES)]


def _contains_bare_raise(node: ast.AST) -> bool:
    """True if ``node`` contains a bare ``raise`` (``ast.Raise(exc=None)``)."""
    return any(
        isinstance(child, ast.Raise) and child.exc is None
        for child in _walk_without_nested_scope(node)
    )


# ── Guard ──────────────────────────────────────────────────────────────


def test_expected_worker_sources_exist():
    """Fail loudly (instead of erroring on a missing file) if the tree moves."""
    missing = [
        str(path.relative_to(ROOT))
        for path in EXPECTED_WORKER_FILES
        if not path.is_file()
    ]
    assert not missing, (
        "These static worker-contract tests read the worker sources directly; "
        f"update the paths in this file if the tree moved. Missing: {missing}"
    )


# ── punctuate_text ─────────────────────────────────────────────────────


def test_punctuate_task_name_matches_api_dispatch():
    """The name registered by the worker is the name the API sends."""
    _, fast_tree = _read(FAST_TASKS)
    task_names = _task_names(fast_tree)
    assert "punctuate_text" in task_names, (
        "workers/fast/tasks.py no longer registers a Celery task named "
        f"'punctuate_text'; found {sorted(task_names)}"
    )

    worker_name = _keyword_value(_task_decorator(task_names["punctuate_text"]), "name")
    assert worker_name, "punctuate_text's @app.task decorator has no name= keyword"

    _, api_tree = _read(DOCUMENTS_API)
    dispatched = _dispatched_names(api_tree)
    assert worker_name in dispatched, (
        f"Worker registers task {worker_name!r}, but documents.py dispatches "
        f"only {sorted(dispatched)}. The UI would wait for a task Celery never "
        "routes to that name."
    )


def test_punctuate_signature_accepts_expected_kwargs():
    """The API passes ``texto``, ``max_chars`` and ``documento_id`` as kwargs."""
    _, tree = _read(FAST_TASKS)
    func = _function(tree, "punctuate_text")

    params = {
        arg.arg
        for arg in (
            *func.args.posonlyargs,
            *func.args.args,
            *func.args.kwonlyargs,
        )
    }
    expected = {"texto", "max_chars", "documento_id"}
    missing = expected - params
    assert not missing, (
        f"punctuate_text signature {sorted(params)} is missing {sorted(missing)}; "
        "the API sends these as keyword arguments and Celery would reject the call"
    )


def test_punctuate_persists_texto_preprocesado():
    """Success writes the punctuated text to metadatos and advances estado."""
    source, tree = _read(FAST_TASKS)
    func = _function(tree, "punctuate_text")
    normalized = _squash(_function_source(source, func))

    assert "UPDATEdocumentosSETestado='preprocesado'" in normalized, (
        "punctuate_text no longer runs "
        "`UPDATE documentos SET estado = 'preprocesado'` on success"
    )
    assert 'meta["texto_preprocesado"]' in normalized, (
        "punctuate_text no longer stores the result under "
        "metadatos['texto_preprocesado']"
    )
    assert "UPDATEdocumentosSETmetadatos=:meta" in normalized, (
        "punctuate_text no longer persists the metadatos JSONB column"
    )


def test_punctuate_reraises_on_exception():
    """A failed punctuation must fail the Celery task, not report silent success."""
    source, tree = _read(FAST_TASKS)
    func = _function(tree, "punctuate_text")

    handlers = [
        handler
        for try_stmt in _direct_tries(func)
        for handler in _exception_handlers(try_stmt)
    ]
    assert handlers, (
        "punctuate_text has no top-level `except Exception` handler; the DB "
        "estado can no longer be reset to 'error' on failure"
    )
    assert any(_contains_bare_raise(handler) for handler in handlers), (
        "punctuate_text's top-level `except Exception` never re-raises. Returning "
        "an error dict makes Celery report SUCCESS while the document is not "
        "preprocessed — the exact 'silent success' regression this guards."
    )


def test_punctuate_routes_to_fast_queue():
    """punctuate_text must execute on the fast queue.

    workers/fast/tasks.py does not pin a queue on the task decorator (the
    worker container subscribes to ``-Q fast``); routing is therefore expressed
    by the API's ``send_task(..., queue="fast")`` call. If the worker ever pins
    a queue on the decorator, it must also be "fast".
    """
    _, fast_tree = _read(FAST_TASKS)
    func = _function(fast_tree, "punctuate_text")
    decorator = _task_decorator(func)
    assert decorator is not None, "punctuate_text is no longer an @app.task"

    declared_queue = _keyword_value(decorator, "queue")
    assert declared_queue in (None, "fast"), (
        "punctuate_text's @app.task decorator pins queue="
        f"{declared_queue!r}; the fast worker only consumes the 'fast' queue"
    )

    _, api_tree = _read(DOCUMENTS_API)
    dispatch = _send_task_call_for(api_tree, "punctuate_text")
    assert dispatch is not None, (
        "documents.py no longer dispatches a task named 'punctuate_text'"
    )
    dispatch_queue = _keyword_value(dispatch, "queue")
    assert dispatch_queue == "fast", (
        "documents.py must route punctuate_text to the 'fast' queue; found "
        f"queue={dispatch_queue!r} on celery_app.send_task(). The heavy worker "
        "would otherwise pick it up (or no worker would)."
    )


# ── Glaser classifier ──────────────────────────────────────────────────


def test_heavy_glaser_task_reraises():
    """A Glaser failure must fail the task so the UI cannot show 'Clasificado'."""
    _, tree = _read(HEAVY_TASKS)
    func = _function(tree, "task_run_glaser_classifier")

    decorator = _task_decorator(func)
    assert decorator is not None, (
        "task_run_glaser_classifier is no longer decorated with @app.task"
    )
    task_name = _keyword_value(decorator, "name")
    assert isinstance(task_name, str) and task_name, (
        "task_run_glaser_classifier's @app.task decorator has no name= keyword"
    )

    handlers: list[ast.ExceptHandler] = []
    for node in _walk_without_nested_scope(func):
        if isinstance(node, _TRY_NODES):
            handlers.extend(_exception_handlers(node))

    assert handlers, (
        "task_run_glaser_classifier has no `except Exception` handler; failures "
        "would escape without the intended logging"
    )
    assert any(_contains_bare_raise(handler) for handler in handlers), (
        "task_run_glaser_classifier's `except Exception` does not re-raise. "
        "Celery would mark the task SUCCESS and the document would appear "
        "classified after a failure."
    )


def test_glaser_classifier_reports_completed():
    """The orchestrator returns a dict whose status is 'completed' on success."""
    _, tree = _read(GLASER_CLASSIFIER)
    func = _function(tree, "classify_document_with_validation")

    string_constants = {
        node.value
        for node in ast.walk(func)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "completed" in string_constants, (
        "classify_document_with_validation no longer reports "
        "status='completed'; task_run_glaser_classifier relies on that value "
        "(alongside 'ok'/'warning') to mark the document 'clasificado'"
    )


# ── Result backend ─────────────────────────────────────────────────────


def _celery_app_call(tree: ast.Module) -> ast.Call | None:
    """Return the ``Celery(...)`` call assigned to the module-level ``app``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "app"
            for target in node.targets
        ):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Celery"
        ):
            return value
    return None


def test_heavy_worker_configures_result_backend():
    """Heavy tasks must publish results, or the UI's task polling never resolves.

    The frontend polls ``GET /api/v1/documents/tasks/{id}`` after classify /
    segment / extract. Celery only stores a result in a backend configured on the
    *worker* app, so a broker-only heavy app leaves every heavy task ``PENDING``
    from the API's point of view: the document state changes in Postgres, but the
    card spins until the frontend's 120s timeout.
    """
    _, tree = _read(HEAVY_TASKS)
    call = _celery_app_call(tree)
    assert call is not None, (
        "workers/heavy/tasks.py no longer builds `app = Celery(...)`"
    )
    assert _keyword(call, "backend") is not None, (
        "the heavy Celery app has no backend=; classify/segment/extract will "
        "stay PENDING for the frontend and end in a 120s timeout even though "
        "the DB state advances"
    )
