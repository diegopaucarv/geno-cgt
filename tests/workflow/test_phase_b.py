"""Static contracts for the Phase B / F2.3 extraction fixes.

Why static?
-----------
``transitions.py`` imports Celery and SQLAlchemy, and ``pattern_extractor.py``
imports the worker-only ``database``/``llm_client`` modules. Neither import
works from the host test process (and both would need Redis/Postgres). These
tests therefore read the sources and assert on their text/structure — the same
approach as ``test_workers_tasks.py``.

Fixes pinned here
-----------------
1. **F3 tail batch** — ``_maybe_trigger_phase_b`` compared ``listos`` against the
   project total, so a final batch of 1-2 documents could never fire Phase B.
   It now gates on the documents that still have not entered open coding.
2. **Idempotent extraction** — ``begin_extraction`` / ``reset_after_cancel``
   replace the two raw ``UPDATE documentos SET estado = 'extrayendo'`` writes
   that let a re-run rewind an already-advanced document (or leave it stuck).
3. **Loud failures** — ``ExtractionFailed`` replaced the ``{"error": ...}`` /
   ``{"mock": True}`` returns that Celery reported as SUCCESS, so a failed
   extraction could be marked as ``codificado``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TRANSITIONS = REPO / "backend" / "app" / "agents" / "transitions.py"
PATTERN_EXTRACTOR = REPO / "workers" / "heavy" / "pattern_extractor.py"
HEAVY_TASKS = REPO / "workers" / "heavy" / "tasks.py"
PROCESSING_STATES_MODEL = (
    REPO / "backend" / "app" / "models" / "domain" / "synthesis.py"
)

EXPECTED_FILES = (
    TRANSITIONS,
    PATTERN_EXTRACTOR,
    HEAVY_TASKS,
    PROCESSING_STATES_MODEL,
)


# ── Parsing helpers ────────────────────────────────────────────────────


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(source: str, path: Path) -> ast.Module:
    return ast.parse(source, filename=str(path))


def _function_node(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Return the first function named ``name`` (methods included)."""
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    raise AssertionError(f"Function {name!r} not found in parsed module")


def _function_source(source: str, path: Path, name: str) -> str:
    segment = ast.get_source_segment(source, _function_node(_tree(source, path), name))
    assert segment is not None, (
        "ast.get_source_segment returned None; the file was likely parsed with a "
        "different source string"
    )
    return segment


def _is_none_annotation(node: ast.AST | None) -> bool:
    """``-> None`` is ast.Constant(None) on 3.9+, ast.Name('None') before."""
    return (isinstance(node, ast.Constant) and node.value is None) or (
        isinstance(node, ast.Name) and node.id == "None"
    )


def _squash(text: str) -> str:
    """Drop all whitespace so reflowing the source does not break a test."""
    return re.sub(r"\s+", "", text)


def _defaults(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, ast.AST | None]:
    """Map every parameter name to its default AST node (``None`` if required)."""
    args = func.args
    positional = [*args.posonlyargs, *args.args]
    mapped: dict[str, ast.AST | None] = {arg.arg: None for arg in positional}
    mapped.update({arg.arg: None for arg in args.kwonlyargs})
    mapped.update({arg.arg: None for arg in (args.vararg, args.kwarg) if arg})
    for arg, default in zip(
        positional[len(positional) - len(args.defaults) :], args.defaults
    ):
        mapped[arg.arg] = default
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        mapped[arg.arg] = default
    return mapped


# ── Guard ──────────────────────────────────────────────────────────────


def test_expected_sources_exist() -> None:
    """Fail loudly (instead of erroring on a missing file) if the tree moves."""
    missing = [str(p.relative_to(REPO)) for p in EXPECTED_FILES if not p.is_file()]
    assert not missing, f"static-contract sources moved; missing: {missing}"


# ── 1. Phase B trigger: F3 tail-batch gate ─────────────────────────────


def test_phase_b_batch_size_reads_env_with_default_three() -> None:
    """pin: batch size comes from GT_OPEN_CODING_BATCH_SIZE, defaulting to 3."""
    body = _function_source(_source(TRANSITIONS), TRANSITIONS, "_maybe_trigger_phase_b")
    assert re.search(
        r"_os\.getenv\(\s*[\"']GT_OPEN_CODING_BATCH_SIZE[\"']\s*,\s*[\"']3[\"']\s*\)",
        body,
    ), (
        "_maybe_trigger_phase_b no longer reads GT_OPEN_CODING_BATCH_SIZE with "
        "default '3'"
    )
    assert re.search(r"batch_size\s*=\s*int\(", body), (
        "the env batch size must be coerced to int"
    )


def test_phase_b_returns_none_when_nothing_ready() -> None:
    """pin: no document in a batch-ready state -> no Phase B dispatch."""
    body = _function_source(_source(TRANSITIONS), TRANSITIONS, "_maybe_trigger_phase_b")
    assert re.search(r"if\s+listos\s*==\s*0\s*:(?:\s|#[^\n]*\n)*return\s+None", body), (
        "`listos == 0` must short-circuit to None (no empty Phase B dispatch)"
    )


def test_phase_b_tail_batch_gate_uses_pendientes() -> None:
    """pin: F3 — the gate compares against *pendientes*, not the project total.

    Before the fix the condition was effectively ``listos < batch_size`` alone,
    so the final 1-2 documents of a project never triggered synthesis.
    """
    body = _function_source(_source(TRANSITIONS), TRANSITIONS, "_maybe_trigger_phase_b")

    assert re.search(
        r"if\s+listos\s*<\s*batch_size\s+and\s+listos\s*<\s*pendientes\s*:",
        body,
    ), (
        "_maybe_trigger_phase_b lost the `listos < batch_size and listos < "
        "pendientes` gate; a tail batch of 1-2 docs would never fire Phase B"
    )

    # pendientes = docs that have not entered (or failed) open coding.
    assert re.search(
        r"NOT\s+IN\s*\(\s*['\"]codificando['\"]\s*,\s*['\"]codificado['\"]"
        r"\s*,\s*['\"]error['\"]\s*\)",
        body,
    ), (
        "the `pendientes` counter must exclude codificando/codificado/error, "
        "otherwise the tail-batch gate counts already-coded documents"
    )


def test_phase_b_dedupe_step_key_includes_doc_count() -> None:
    """pin: the processing_states marker is per run *and* per batch size.

    Without ``_n{listos}`` a second, larger batch would be suppressed by the
    marker written by the first one.
    """
    body = _function_source(_source(TRANSITIONS), TRANSITIONS, "_maybe_trigger_phase_b")
    assert re.search(
        r"f[\"']phase_b_run_\{run_id\}_n\{listos\}[\"']",
        body,
    ), (
        'the Phase B dedupe key must be f"phase_b_run_{run_id}_n{listos}"; '
        "dropping the count lets an earlier marker block a later batch"
    )
    assert re.search(r"step\s*=", body), (
        "the dedupe key must be stored in a `step` variable used by the "
        "processing_states insert"
    )


# ── 2. transitions.py public helpers ───────────────────────────────────


def test_begin_extraction_exists_and_returns_bool() -> None:
    """pin: begin_extraction is the only gate that decides the final transition."""
    src = _source(TRANSITIONS)
    func = _function_node(_tree(src, TRANSITIONS), "begin_extraction")

    assert isinstance(func.returns, ast.Name) and func.returns.id == "bool", (
        "begin_extraction must be annotated `-> bool` (True = this caller owns "
        "the extrayendo -> incidentes_extraidos transition)"
    )

    body = _squash(ast.get_source_segment(src, func) or "")
    assert "returnTrue" in body, (
        "begin_extraction must return True when its UPDATE won the row"
    )
    assert "returnbool(" in body, (
        "begin_extraction must return a bool on the re-execution path "
        "(row already 'extrayendo')"
    )


def test_begin_extraction_only_accepts_transient_states() -> None:
    """pin: a re-run must not rewind an already terminal document."""
    src = _source(TRANSITIONS)
    func_source = _function_source(src, TRANSITIONS, "begin_extraction")

    assert re.search(
        r"IN\s*\(\s*['\"]segmentado['\"]\s*,\s*['\"]procesando['\"]"
        r"\s*,\s*['\"]error['\"]\s*\)",
        func_source,
    ), (
        "begin_extraction must only move a doc from "
        "('segmentado', 'procesando', 'error'); anything broader would regress "
        "a terminal document"
    )
    # The UPDATE really targets the estado column.
    assert re.search(
        r"UPDATE\s+documentos\s+SET\s+estado\s*=\s*['\"]extrayendo['\"]",
        func_source,
    ), "begin_extraction no longer sets estado = 'extrayendo'"


def test_reset_after_cancel_defaults_to_segmentado() -> None:
    """pin: a cancelled extraction returns the doc to a retryable state."""
    src = _source(TRANSITIONS)
    func = _function_node(_tree(src, TRANSITIONS), "reset_after_cancel")

    defaults = _defaults(func)
    assert "to_state" in defaults, "reset_after_cancel lost its to_state parameter"
    default = defaults["to_state"]
    assert isinstance(default, ast.Constant) and default.value == "segmentado", (
        "reset_after_cancel must default to to_state='segmentado'"
    )


def test_transition_accepts_keyword_only_fail_to() -> None:
    """pin: a failed extraction can route to 'segmentado' instead of 'error'."""
    src = _source(TRANSITIONS)
    func = _function_node(_tree(src, TRANSITIONS), "transition")

    keyword_only = {arg.arg for arg in func.args.kwonlyargs}
    assert "fail_to" in keyword_only, (
        "transition() must accept a keyword-only `fail_to` parameter; callers "
        "pass fail_to='segmentado' so a failed F2.3 run stays retryable"
    )
    assert "fail_to" not in {arg.arg for arg in func.args.args}, (
        "`fail_to` must stay keyword-only, otherwise positional callers break"
    )

    default = _defaults(func)["fail_to"]
    assert isinstance(default, ast.Constant) and default.value == "error", (
        "transition(fail_to=...) must default to 'error'"
    )


def test_to_error_accepts_to_state_default_error() -> None:
    """pin: _to_error's target state is configurable (default 'error')."""
    src = _source(TRANSITIONS)
    func = _function_node(_tree(src, TRANSITIONS), "_to_error")

    defaults = _defaults(func)
    assert "to_state" in defaults, "_to_error lost its to_state parameter"
    default = defaults["to_state"]
    assert isinstance(default, ast.Constant) and default.value == "error", (
        "_to_error must default to to_state='error'"
    )


# ── 3. pattern_extractor.ExtractionFailed ──────────────────────────────


def test_extraction_failed_is_runtime_error() -> None:
    src = _source(PATTERN_EXTRACTOR)
    node = next(
        (
            n
            for n in ast.walk(_tree(src, PATTERN_EXTRACTOR))
            if isinstance(n, ast.ClassDef) and n.name == "ExtractionFailed"
        ),
        None,
    )
    assert node is not None, (
        "workers/heavy/pattern_extractor.py has no ExtractionFailed"
    )
    bases = [
        b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases
    ]
    assert "RuntimeError" in bases, (
        f"ExtractionFailed must subclass RuntimeError; found bases {bases}"
    )


def test_extraction_failure_paths_raise() -> None:
    """pin: every failure path raises, so Celery reports FAILURE not SUCCESS."""
    src = _source(PATTERN_EXTRACTOR)

    assert src.count("raise ExtractionFailed(") >= 3, (
        "expected at least three `raise ExtractionFailed(...)` sites (advisory "
        "lock, missing baseline segments, mock/LLM error, partial insert); "
        f"found {src.count('raise ExtractionFailed(')}"
    )

    for message, label in (
        ("sin segmentos baseline", "no-baseline path"),
        ("respuesta mock/error del LLM", "mock/LLM-error path"),
        ("incidentes no se pudieron persistir", "partial-insert path"),
    ):
        assert re.search(
            r"raise\s+ExtractionFailed\([^()]*" + re.escape(message), src
        ), (
            f"the {label} must `raise ExtractionFailed(...)` with {message!r}; "
            "returning an error dict makes Celery report SUCCESS"
        )


def test_extractor_never_returns_mock_or_error_dict() -> None:
    """pin: no early ``return {"mock": True}`` / ``return {"error": ...}``."""
    src = _source(PATTERN_EXTRACTOR)

    assert not re.search(r"return\s*\{\s*[\"']mock[\"']\s*:\s*True", src), (
        "pattern_extractor still returns {'mock': True}; that result is marked "
        "as a successful Celery task"
    )
    assert not re.search(r"return\s*\{\s*[\"']error[\"']\s*:", src), (
        "pattern_extractor still returns {'error': ...}; raise ExtractionFailed instead"
    )


# ── 4. workers/heavy/tasks.py wiring ───────────────────────────────────


def test_heavy_tasks_imports_transition_helpers() -> None:
    src = _source(HEAVY_TASKS)
    imported: set[str] = set()
    for node in ast.walk(_tree(src, HEAVY_TASKS)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
            "agents.transitions"
        ):
            imported.update(alias.name for alias in node.names)

    missing = {"begin_extraction", "reset_after_cancel"} - imported
    assert not missing, (
        f"worker-heavy must import {sorted(missing)} from agents.transitions; "
        "found only " + str(sorted(imported))
    )


def test_process_document_agents_a_uses_begin_extraction_result() -> None:
    """pin: the final transition only runs when begin_extraction won the row."""
    body = _function_source(
        _source(HEAVY_TASKS), HEAVY_TASKS, "process_document_agents_a"
    )

    assert re.search(
        r"needs_final_transition\s*=\s*begin_extraction\(\s*session\s*,\s*documento_id\s*\)",
        body,
    ), (
        "process_document_agents_a must store "
        "`needs_final_transition = begin_extraction(session, documento_id)`"
    )
    assert re.search(r"if\s+needs_final_transition\s*:", body), (
        "the extrayendo -> incidentes_extraidos transition must be guarded by "
        "needs_final_transition"
    )


def test_no_raw_extrayendo_update_in_extraction_task() -> None:
    """pin: both inline ``UPDATE ... 'extrayendo'`` writes were deleted."""
    body = _function_source(
        _source(HEAVY_TASKS), HEAVY_TASKS, "process_document_agents_a"
    )
    assert not re.search(
        r"UPDATE\s+documentos\s+SET\s+estado\s*=\s*['\"]extrayendo['\"]",
        body,
        re.IGNORECASE,
    ), (
        "process_document_agents_a writes estado='extrayendo' with raw SQL again; "
        "begin_extraction owns that write (and its idempotency guarantee)"
    )

    # And nowhere else in the worker, since only transitions.py may write it.
    src = _source(HEAVY_TASKS)
    assert not re.search(
        r"UPDATE\s+documentos\s+SET\s+estado\s*=\s*['\"]extrayendo['\"]",
        src,
        re.IGNORECASE,
    ), "worker-heavy must not write estado='extrayendo' outside transitions.py"


def test_restore_phase_b_docs_is_module_level_and_called_on_both_errors() -> None:
    """pin: cancelled *and* failed Phase B runs must unstick 'codificando' docs."""
    src = _source(HEAVY_TASKS)
    tree = _tree(src, HEAVY_TASKS)

    restore = _function_node(tree, "_restore_phase_b_docs")
    module_level = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_restore_phase_b_docs" in module_level, (
        "_restore_phase_b_docs must stay a module-level helper"
    )
    params = [arg.arg for arg in restore.args.args]
    assert params[:2] == ["session", "proyecto_id"], (
        f"_restore_phase_b_docs signature changed: {params}"
    )
    assert _is_none_annotation(restore.returns), (
        "_restore_phase_b_docs must be annotated `-> None`"
    )

    # Locate the two handlers of process_synthesis_agents_b that call it.
    func = _function_node(tree, "process_synthesis_agents_b")
    calling_handlers: list[ast.ExceptHandler] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "_restore_phase_b_docs"
            for child in ast.walk(node)
        ):
            calling_handlers.append(node)

    handler_types = [
        handler.type.id
        for handler in calling_handlers
        if isinstance(handler.type, ast.Name)
    ]
    assert len(calling_handlers) >= 2, (
        "process_synthesis_agents_b must call _restore_phase_b_docs from both "
        f"except handlers (cancel and failure); found {len(calling_handlers)}"
    )
    assert "TaskCancelledError" in handler_types, (
        "the cancellation handler no longer restores the docs; they would stay "
        "stuck in 'codificando'"
    )
    assert "Exception" in handler_types, (
        "the failure handler no longer restores the docs or clears the "
        "phase_b_run_* marker, so a retry would be skipped"
    )


# ── 6. Phase B idempotency key must fit processing_states.step ─────────
#
# Bug pinned here: `_maybe_trigger_phase_b` builds
#     step = f"phase_b_run_{run_id}_n{listos}"
# With `run_id` being a 36-character UUID string that is 51 characters against
# a `character varying(50)` column. Every INSERT raised
# `StringDataRightTruncation`, the exception escaped `transition()`, and the
# `except` in `process_document_agents_a` treated it as an extraction failure
# and rewound the document to 'segmentado' — with the incidents already
# committed. The project could therefore never reach three terminal documents,
# so Phase B never fired and "Extraer incidentes" appeared to do nothing.

PHASE_B_STEP_PREFIX = "phase_b_run_"
UUID_TEXT_LEN = 36


def _phase_b_step_key_max_len() -> int:
    """Longest realistic key: prefix + UUID + '_n' + 6-digit doc count."""
    return len(PHASE_B_STEP_PREFIX) + UUID_TEXT_LEN + len("_n") + 6


def _processing_states_step_width() -> int:
    """Read the ``step`` column width out of the ProcessingState model."""
    tree = _tree(_source(PROCESSING_STATES_MODEL), PROCESSING_STATES_MODEL)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ProcessingState":
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign):
                    continue
                target = stmt.target
                if not (isinstance(target, ast.Name) and target.id == "step"):
                    continue
                for child in ast.walk(stmt.value):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "String"
                        and child.args
                        and isinstance(child.args[0], ast.Constant)
                    ):
                        return int(child.args[0].value)
    raise AssertionError("could not locate ProcessingState.step width")


def test_phase_b_step_key_fits_model_column() -> None:
    """The dedupe key must fit the declared column width."""
    width = _processing_states_step_width()
    needed = _phase_b_step_key_max_len()
    assert width >= needed, (
        f"processing_states.step is String({width}) but the Phase B key needs "
        f"{needed} characters; the INSERT raises StringDataRightTruncation"
    )


def test_phase_b_step_key_matches_transitions_source() -> None:
    """Guard the constant above against the real f-string in transitions.py."""
    source = _source(TRANSITIONS)
    assert PHASE_B_STEP_PREFIX in source, (
        "the Phase B dedupe key prefix changed; update PHASE_B_STEP_PREFIX and "
        "the migration that sizes processing_states.step"
    )
    assert len(PHASE_B_STEP_PREFIX) == 12


def test_batch_trigger_failures_do_not_demote_document() -> None:
    """A failing batch trigger must not rewind an already-committed estado.

    ``transition()`` commits the document's new estado before running the
    batch-side effects, so those are advisory. Before the fix the exception
    escaped and the worker's ``except`` demoted the doc (``fail_to``).
    """
    tree = _tree(_source(TRANSITIONS), TRANSITIONS)
    func = _function_node(tree, "transition")

    guarded: list[ast.Try] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Try):
            continue
        body_src = _squash(ast.unparse(ast.Module(body=node.body, type_ignores=[])))
        if "_maybe_trigger_phase_b" in body_src:
            guarded.append(node)

    assert guarded, (
        "transition() calls _maybe_trigger_phase_b outside a try/except; a "
        "failing idempotency marker demotes the document via fail_to"
    )

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("exception", "error")
        for try_node in guarded
        for handler in try_node.handlers
        for node in ast.walk(handler)
    ), "the batch-trigger guard must log the failure (logger.exception)"


def test_processing_states_step_live_width(docker: bool) -> None:
    """The running database must have accepted migration 019."""
    from tests.workflow.conftest import docker_compose_exec

    proc = docker_compose_exec(
        "postgres",
        "psql",
        "-U",
        "app_user",
        "-d",
        "gt-db",
        "-t",
        "-A",
        "-c",
        "select character_maximum_length from information_schema.columns "
        "where table_name='processing_states' and column_name='step';",
    )
    assert proc.returncode == 0, proc.stderr[:500]
    width = int(proc.stdout.strip())
    needed = _phase_b_step_key_max_len()
    assert width >= needed, (
        f"live processing_states.step is varchar({width}), needs >= {needed}. "
        "Migration 019_widen_processing_states_step was not applied."
    )
