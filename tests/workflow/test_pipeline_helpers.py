"""Static contracts for the pipeline *helpers* fixes (admin rollback + dispatch).

Why static?
-----------
``admin.py`` and ``pipeline.py`` are FastAPI routers: importing them pulls in
SQLAlchemy models, Celery and the settings module, and the orchestrator imports
the ORM models. None of that is available (or desirable) in the host test
process, and the HTTP contract tests already need a live stack. Following
``test_workers_tasks.py``, these tests read the sources instead.

Fixes pinned here
-----------------
1. ``admin.stop_project_pipeline`` / ``admin.cancel_task`` roll documents back
   only from *transient* states, and that list includes the three extraction /
   coding states that used to be omitted (``extrayendo``, ``clasificando``,
   ``codificando``). A stale task can no longer rewind an advanced document.
2. ``pipeline.run_single_agent`` rejects unknown project-level agent ids with a
   400, tracks per-document dispatches in ``pipeline_tasks``, and pins the
   prompt cache affinity; ``run-stage/open_coding`` dispatches only docs that
   are really ``segmentado``.
3. ``pipeline_orchestrator.start_pipeline`` skips terminal states, uses
   ``ready == len(docs) and ready >= 3`` for the direct Phase B trigger, and
   honours an optimistic-lock miss (``rowcount == 0`` -> no dispatch).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADMIN = REPO / "backend" / "app" / "api" / "v1" / "admin.py"
PIPELINE = REPO / "backend" / "app" / "api" / "v1" / "pipeline.py"
ORCHESTRATOR = REPO / "backend" / "app" / "services" / "pipeline_orchestrator.py"

EXPECTED_FILES = (ADMIN, PIPELINE, ORCHESTRATOR)

TRANSIENT_ROLLBACK_STATES = ("extrayendo", "clasificando", "codificando")


# ── Parsing helpers ────────────────────────────────────────────────────


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(source: str, path: Path) -> ast.Module:
    return ast.parse(source, filename=str(path))


def _function_node(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
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


def _string_tuples(node: ast.AST) -> list[tuple[str, ...]]:
    """Every tuple literal made only of string constants inside ``node``."""
    found: list[tuple[str, ...]] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Tuple) or not child.elts:
            continue
        if all(
            isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            for elt in child.elts
        ):
            found.append(tuple(elt.value for elt in child.elts))
    return found


def _rollback_tuple(body: ast.AST) -> tuple[str, ...] | None:
    """The rollback state tuple: a string tuple mentioning 'segmentando'."""
    for values in _string_tuples(body):
        if "segmentando" in values and "procesando" in values:
            return values
    return None


def _region(source: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    """Slice ``source`` between ``start_marker`` and the first ``end_marker``."""
    start = source.index(start_marker)
    rest = source[start + len(start_marker) :]
    ends = [rest.index(marker) for marker in end_markers if marker in rest]
    end = min(ends) if ends else len(rest)
    return rest[:end]


def _stage_branch(source: str, stage: str) -> str:
    """The body of ``elif stage_name == "<stage>":`` inside run_pipeline_stage."""
    return _region(
        source,
        f'elif stage_name == "{stage}":',
        ("\n    elif stage_name ==", "\n    else:"),
    )


# ── Guard ──────────────────────────────────────────────────────────────


def test_expected_sources_exist() -> None:
    missing = [str(p.relative_to(REPO)) for p in EXPECTED_FILES if not p.is_file()]
    assert not missing, f"static-contract sources moved; missing: {missing}"


# ── 5. admin.py — rollback state tuples ────────────────────────────────


def test_stop_project_pipeline_resets_all_transient_states() -> None:
    """pin: the no-run reset must unstick extraction/coding documents too."""
    src = _source(ADMIN)
    func = _function_node(_tree(src, ADMIN), "stop_project_pipeline")

    sql_constants = [
        node.value
        for node in ast.walk(func)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "UPDATE documentos SET estado = 'crudo'" in node.value
    ]
    assert sql_constants, (
        "stop_project_pipeline no longer resets documents with "
        "`UPDATE documentos SET estado = 'crudo' WHERE estado IN (...)`"
    )
    reset_sql = sql_constants[0]
    for estado in TRANSIENT_ROLLBACK_STATES:
        assert f"'{estado}'" in reset_sql, (
            f"the inline reset SQL omits '{estado}'; those documents would stay "
            "stuck after Stop"
        )


def test_stop_project_pipeline_rollback_tuple_has_coding_states() -> None:
    """pin: the per-task rollback only rewinds transient documents."""
    src = _source(ADMIN)
    func = _function_node(_tree(src, ADMIN), "stop_project_pipeline")

    states = _rollback_tuple(func)
    assert states is not None, (
        "stop_project_pipeline lost its rollback state tuple "
        "(segmentando/procesando/preprocesando/resumiendo/...)"
    )
    missing = [e for e in TRANSIENT_ROLLBACK_STATES if e not in states]
    assert not missing, (
        f"the rollback tuple omits {missing}: a finished/cancelled document in "
        "one of those states would never be rewound"
    )


def test_cancel_task_rollback_tuple_has_coding_states() -> None:
    """pin: cancelling one task rewinds extraction/classification/coding docs."""
    src = _source(ADMIN)
    func = _function_node(_tree(src, ADMIN), "cancel_task")

    states = _rollback_tuple(func)
    assert states is not None, "cancel_task lost its rollback state tuple"
    missing = [e for e in TRANSIENT_ROLLBACK_STATES if e not in states]
    assert not missing, (
        f"cancel_task's rollback tuple omits {missing}: the document would be "
        "left mid-flight"
    )


def test_cancel_task_rollback_is_guarded_to_transient_states() -> None:
    """pin: a stale task must not rewind a document that already advanced."""
    body = _function_source(_source(ADMIN), ADMIN, "cancel_task")

    guard = re.search(
        r"if\s+\(current_estado\s+or\s+(?:\"\"|'')\s*\)\.strip\(\)\s+in\s*\(",
        body,
    )
    assert guard is not None, (
        "cancel_task no longer checks the *current* estado against the transient "
        "set before rewinding; an old task could undo a newer transition"
    )

    update = body.index("UPDATE documentos SET estado = :estado")
    assert guard.start() < update, (
        "the transient-state guard must run before the rollback UPDATE"
    )


# ── 6. pipeline.py — dispatch helpers ──────────────────────────────────


def test_project_level_task_names_guard_exists() -> None:
    """pin: unknown project-level agent ids are rejected with 400, not dispatched."""
    src = _source(PIPELINE)
    tree = _tree(src, PIPELINE)

    assert re.search(r"_PROJECT_LEVEL_TASK_NAMES\s*=\s*frozenset\(", src), (
        "pipeline.py lost the _PROJECT_LEVEL_TASK_NAMES registry"
    )

    body = _function_source(src, PIPELINE, "run_single_agent")
    assert re.search(
        r"if\s+agent_id\s+not\s+in\s+_PROJECT_LEVEL_TASK_NAMES\s*:"
        r"(?:\s|#[^\n]*\n)*raise\s+HTTPException\(\s*400",
        body,
    ), (
        "run_single_agent must reject an unregistered project-level agent id "
        "with HTTP 400; otherwise Celery accepts the name and nothing runs"
    )

    registry = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_PROJECT_LEVEL_TASK_NAMES"
                for t in node.targets
            )
        ),
        None,
    )
    assert registry is not None and isinstance(registry.value, ast.Call), (
        "_PROJECT_LEVEL_TASK_NAMES must stay a literal registry"
    )
    members = {
        elt.value
        for elt in ast.walk(registry.value)
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    }
    assert {"process_synthesis_agents_b", "selective_coding_coordinator"} <= members, (
        "the registry lost a Phase B / selective coordinator task name"
    )


def test_open_coding_stage_dispatches_only_segmentado() -> None:
    """pin: 'crudo' / 'clasificado' / 'segmentando' dispatches always failed.

    ``process_document_agents_a`` calls ``_ensure_segmented``, which raises when
    the document has no segments, and it assumes the segments already carry a
    Glaser category. Under the classify-first ladder a document only owns both
    after ``segmentado``, so that is the only estado dispatched here.
    """
    branch = _stage_branch(_source(PIPELINE), "open_coding")

    assert re.search(
        r"if\s+\(doc\.estado\s+or\s+(?:\"\"|'')\s*\)\.strip\(\)\s*==\s*"
        r"[\"']segmentado[\"']\s*:",
        branch,
    ), "the open_coding guard must be an equality check against 'segmentado'"
    assert "send_task" in branch and "process_document_agents_a" in branch, (
        "the open_coding branch no longer dispatches process_document_agents_a"
    )
    assert not re.search(r"strip\(\)\s+in\s*\(", branch), (
        "the open_coding guard is a membership test again; only ('segmentado',) "
        "may pass, and an equality check is what pins that"
    )
    assert not re.search(r"strip\(\)\s+in\s*\([^)]*(?:clasificado|crudo)", branch), (
        "another estado was added alongside 'segmentado' in the open_coding "
        "guard; those dispatches fail inside _ensure_segmented"
    )


def test_cross_doc_clears_phase_b_markers_before_dispatch() -> None:
    """pin: a manual Cross-doc run must not be skipped by a stale marker."""
    branch = _stage_branch(_source(PIPELINE), "cross_doc")

    assert re.search(r"DELETE\s+FROM\s+processing_states", branch, re.IGNORECASE), (
        "cross_doc no longer clears process_synthesis_agents_b's dedupe markers"
    )
    assert re.search(r"LIKE\s+['\"]phase_b_run_%['\"]", branch), (
        "cross_doc must delete the `step LIKE 'phase_b_run_%'` markers"
    )
    delete = branch.index("DELETE FROM processing_states")
    dispatch = branch.index('"process_synthesis_agents_b"')
    assert delete < dispatch, (
        "the marker cleanup must run before the dispatch, otherwise Phase B "
        "still skips the run"
    )


def test_run_single_agent_tracks_per_document_dispatch() -> None:
    """pin: without tracking, stop/cancel cannot revert the document."""
    src = _source(PIPELINE)
    body = _function_source(src, PIPELINE, "run_single_agent")

    assert "_track_pipeline_task(" in body, (
        "run_single_agent no longer records the dispatch in pipeline_tasks"
    )
    per_doc = body.index("if doc_id:")
    project_level = body.index("# Project-level agents")
    call = body.index("_track_pipeline_task(")
    assert per_doc < call < project_level, (
        "_track_pipeline_task must run inside the per-document branch"
    )

    track = _function_source(src, PIPELINE, "_track_pipeline_task")
    assert "_get_or_create_running_run_id(" in track, (
        "_track_pipeline_task must attach the task to a running PipelineRun"
    )
    assert re.search(r"INSERT\s+INTO\s+pipeline_tasks", track, re.IGNORECASE), (
        "_track_pipeline_task no longer inserts into pipeline_tasks"
    )

    create_run = _function_source(src, PIPELINE, "_get_or_create_running_run_id")
    assert re.search(r"status\s*=\s*'running'", create_run), (
        "_get_or_create_running_run_id must create a 'running' PipelineRun"
    )


def test_run_single_agent_pins_prompt_cache_affinity() -> None:
    """pin: punctuation for one project lands on the same worker replica."""
    body = _function_source(_source(PIPELINE), PIPELINE, "run_single_agent")

    punctuate_start = body.index('agent_id in ("punctuate_text", "util_punctuator")')
    punctuate_branch = body[punctuate_start:]
    punctuate_branch = punctuate_branch[: punctuate_branch.index("else:")]

    assert re.search(
        r"[\"']cache_key[\"']\s*:\s*str\(project_id\)", punctuate_branch
    ), (
        "the punctuate_text dispatch no longer passes "
        "cache_key=str(project_id); prompt caching would fan out across replicas"
    )


# ── 7. pipeline_orchestrator.py ────────────────────────────────────────


def test_start_pipeline_skips_terminal_states() -> None:
    """pin: re-running the pipeline must not re-dispatch finished documents."""
    src = _source(ORCHESTRATOR)
    func = _function_node(_tree(src, ORCHESTRATOR), "start_pipeline")

    expected = {
        "incidentes_extraidos",
        "procesado",
        "listo",
        "codificando",
        "codificado",
        "error",
    }
    skip_sets = [
        {elt.value for elt in node.elts}
        for node in ast.walk(func)
        if isinstance(node, ast.Set)
        and all(
            isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            for elt in node.elts
        )
    ]
    assert any(expected <= values for values in skip_sets), (
        "start_pipeline's skip set lost one of "
        f"{sorted(expected)}; finished docs would be dispatched again"
    )

    # Every document of the project is considered (fan-out then filter).
    assert re.search(
        r"SELECT\s+id,\s*estado,\s*metadatos\s+FROM\s+documentos\s+"
        r"WHERE\s+proyecto_id\s*=\s*:pid\s+ORDER\s+BY\s+sort_order",
        _function_source(src, ORCHESTRATOR, "start_pipeline"),
    ), "start_pipeline no longer fans out over every document of the project"


def test_start_pipeline_direct_phase_b_trigger_requires_full_batch() -> None:
    """pin: only a project whose every doc is batch-ready triggers Phase B."""
    body = _function_source(_source(ORCHESTRATOR), ORCHESTRATOR, "start_pipeline")

    assert re.search(
        r"if\s+ready\s*==\s*len\(docs\)\s+and\s+ready\s*>=\s*3\s*:", body
    ), (
        "the direct Phase B trigger must be "
        "`ready == len(docs) and ready >= 3`; a partial batch would synthesise "
        "too early"
    )
    assert re.search(r"_maybe_trigger_phase_b\(", body), (
        "start_pipeline no longer triggers Phase B when all docs are ready"
    )


def test_start_pipeline_is_classify_first() -> None:
    """pin: clasificar → segmentar → extraer, en ese orden.

    ``clasificado`` deja la clasificación en ``metadatos.glaser_blocks`` sin
    crear segmentos, así que la decisión no puede empezar por ``n_segs``: un
    documento crudo tiene 0 segmentos y aun así su primer paso es clasificar.
    """
    body = _function_source(_source(ORCHESTRATOR), ORCHESTRATOR, "start_pipeline")

    assert "has_classification" in body, (
        "start_pipeline no longer reads the classification out of metadatos; "
        "without it the first step degrades to segmentation"
    )
    classify_pos = body.find("not has_classification")
    segment_pos = body.find("n_segs == 0 or n_classified == 0")
    extract_pos = body.find("n_incidents == 0 and n_codes == 0")
    assert -1 not in (classify_pos, segment_pos, extract_pos), (
        "start_pipeline lost one of its three dispatch branches "
        "(classify / segment / extract)"
    )
    assert classify_pos < segment_pos < extract_pos, (
        "start_pipeline dispatch order is no longer classify → segment → extract"
    )
    assert "_count_incidents" in body, (
        "start_pipeline no longer checks extracted incidents; docs whose "
        "incidents already exist would be re-dispatched"
    )


def test_dispatch_respects_optimistic_lock() -> None:
    """pin: a row that already transitioned is not dispatched stale."""
    body = _function_source(_source(ORCHESTRATOR), ORCHESTRATOR, "_dispatch")

    assert re.search(r"if\s+result\.rowcount\s*==\s*0\s*:", body), (
        "_dispatch no longer checks `result.rowcount == 0`"
    )
    match = re.search(
        r"if\s+result\.rowcount\s*==\s*0\s*:.{0,400}?return\s+None", body, re.S
    )
    assert match is not None, (
        "_dispatch must return None when the optimistic UPDATE matched no row; "
        "otherwise two workers dispatch the same document"
    )
    update = body.index("UPDATE documentos SET estado")
    assert update < match.start(), (
        "the rowcount check must come after the optimistic UPDATE"
    )
