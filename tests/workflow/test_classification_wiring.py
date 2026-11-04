"""Classification wiring: task name, sync DB driver and XML validator.

These tests pin the three defects that made "Clasificar" silently do nothing or
burn three LLM rounds:

1. The sidebar agent id ``fa_glaser_data_classifier`` was sent to Celery as a
   task name, but the registered task is ``run_glaser_classifier``.
2. ``worker-nlp`` built its SQLAlchemy engine from a bare ``postgresql://`` URL;
   SQLAlchemy >= 2.1 resolves that to psycopg v3, which is not installed, so the
   ``segmentado`` transition never ran.
3. The XML validator's nesting regex also matched sequential tags, so a
   correctly multi-tag classification was reported as invalid every round.

Only the first two are static/source checks. The validator is deterministic, so
it runs inside ``worker-heavy`` (no LLM involved).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "backend" / "app" / "api" / "v1" / "pipeline.py"
NLP_TASKS = REPO / "workers" / "nlp" / "tasks.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── 1. Sidebar agent id -> registered Celery task ──────────────────────


def test_glaser_agent_id_maps_to_registered_task() -> None:
    src = _source(PIPELINE)
    assert "fa_glaser_data_classifier" in src, (
        "pipeline.py no longer special-cases the sidebar agent id; the UI would "
        "dispatch an unregistered Celery task again"
    )
    assert '"run_glaser_classifier"' in src, (
        "pipeline.py must dispatch the registered task name run_glaser_classifier"
    )

    # The mapping must live inside the per-document (doc_id) branch, before the
    # generic ``send_task(agent_id, ...)`` fallback.
    bridge = src.index('"fa_glaser_data_classifier"')
    generic = src.index("# Project-level agents")
    assert bridge < generic, (
        "the fa_glaser_data_classifier branch must precede the generic "
        "project-level dispatch"
    )

    # And the worker really registers that name.
    heavy_tasks = _source(REPO / "workers" / "heavy" / "tasks.py")
    assert re.search(r'name="run_glaser_classifier"', heavy_tasks), (
        "worker-heavy no longer registers run_glaser_classifier"
    )


# ── 1b. "Extraer incidentes" -> registered Celery task ────────────────


def test_extract_patterns_maps_to_registered_task() -> None:
    """The UI dispatches agent id ``extract_patterns``, which is NOT a Celery
    task. It must be translated to ``process_document_agents_a``."""
    src = _source(PIPELINE)
    assert '"extract_patterns": "process_document_agents_a"' in src, (
        "pipeline.py no longer maps extract_patterns to a registered task; the UI "
        "would dispatch the unregistered extract_patterns task again"
    )
    # Confirm the mapping is load-bearing: extract_patterns must NOT be a
    # registered task name in worker-heavy.
    heavy_tasks = _source(REPO / "workers" / "heavy" / "tasks.py")
    assert not re.search(r'name="extract_patterns"', heavy_tasks), (
        "extract_patterns became a real task; the per_doc_task_names mapping in "
        "pipeline.py is now stale"
    )
    assert re.search(r'name="process_document_agents_a"', heavy_tasks)


def test_extrayendo_state_has_transition() -> None:
    """process_document_agents_a sets estado='extrayendo' and then transitions
    FROM it. Without a NEXT entry the state machine logs 'Unknown state' and
    leaves the document stuck forever."""
    src = _source(REPO / "backend" / "app" / "agents" / "transitions.py")
    assert '"extrayendo": ("incidentes_extraidos", None, None)' in src, (
        "transitions.NEXT lost the extrayendo -> incidentes_extraidos entry"
    )


# ── 2. Sync SQLAlchemy URL must pin psycopg2 ───────────────────────────


def test_nlp_transitions_use_pinned_sync_driver() -> None:
    src = _source(NLP_TASKS)
    assert "def _sync_sqlalchemy_url(" in src, (
        "nlp/tasks.py must normalise SQLAlchemy URLs to the psycopg2 driver; "
        "a bare postgresql:// resolves to psycopg v3 on SQLAlchemy >= 2.1"
    )
    assert "postgresql+psycopg2://" in src

    # Every engine built from DATABASE_URL must go through the helper. The bare
    # ``postgresql://`` rewrite is still legitimate for the direct
    # ``psycopg2.connect(...)`` paths, which is why this checks the engine sites.
    assert src.count("db_url_sa = _sync_sqlalchemy_url()") >= 3, (
        "expected the three create_engine sites (transition + two error paths) "
        "to use _sync_sqlalchemy_url()"
    )
    assert src.count("create_engine(") == src.count(
        "db_url_sa = _sync_sqlalchemy_url()"
    ), "a create_engine() call still receives a URL that was not pinned to psycopg2"


# ── 3. XML validator (deterministic, runs in the worker) ───────────────

_VALIDATOR_PROBE = r"""
from glaser_classifier import _algorithmic_validate_xml, _has_nested_tags

sequential = (
    "<contextual_data>intro</contextual_data>"
    "<baseline_data>uno</baseline_data>"
    "<processual_data>dos</processual_data>"
    "<baseline_data>tres</baseline_data>"
)
nested = "<baseline_data>uno<contextual_data>dos</contextual_data></baseline_data>"
overlap = "<baseline_data>uno<contextual_data>dos</baseline_data>tres</contextual_data>"
naked = "<baseline_data>uno</baseline_data>texto suelto"
unbalanced = "<baseline_data>uno</baseline_data><baseline_data>dos"

assert _has_nested_tags(sequential) is False, "sequential tags flagged as nested"
seq = _algorithmic_validate_xml(sequential)
assert seq["valid"] is True, f"sequential multi-tag output rejected: {seq['issues']}"

assert _has_nested_tags(nested) is True, "nested tags not detected"
assert _algorithmic_validate_xml(nested)["valid"] is False
assert _algorithmic_validate_xml(overlap)["valid"] is False
assert _algorithmic_validate_xml(naked)["valid"] is False, "naked text accepted"
assert _algorithmic_validate_xml(unbalanced)["valid"] is False, "unbalanced accepted"

print("VALIDATOR_OK")
"""


def test_glaser_validator_accepts_sequential_tags(docker: bool) -> None:
    from tests.workflow.conftest import docker_compose_exec

    proc = docker_compose_exec(
        "worker-heavy", "python", "-c", _VALIDATOR_PROBE, timeout=90
    )
    if proc.returncode != 0:
        pytest.skip(
            "cannot run the validator inside worker-heavy: "
            f"{(proc.stderr or proc.stdout).strip()[:500]}"
        )
    assert "VALIDATOR_OK" in proc.stdout, proc.stdout
