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


# ── 4. The classifier's PRO call must not cap a reasoning model's budget ──
#
# DeepSeek V4.1 and Nemotron are reasoning models: before emitting the XML they
# write a long ``reasoning_content`` block. Measured on a 33-segment document
# (3 591 chars of text) with the real CLASSIFIER_SYSTEM_PROMPT:
#
#   max_tokens=8192   → reasoning 32 198 chars, content 0     ← degraded
#   max_tokens=32768  → reasoning 36 747 chars, content 4 400 ← OK
#
# With the 8 192 cap ``content`` came back empty, `_step1_classify_xml` raised
# "Empty response from LLM" and fell back to wrapping the whole document in
# `<baseline_data>`. The degraded run still reported status="completed" and
# valid=True, so every segment looked classified while none actually was.

GLASER_CLASSIFIER = REPO / "workers" / "heavy" / "glaser_classifier.py"

#: 8 192 tokens is ~30k chars of reasoning — not enough for a real document.
MIN_PRO_MAX_TOKENS = 32768


def test_step1_classifier_does_not_cap_max_tokens() -> None:
    """`_step1_classify_xml` must inherit MODEL_PRO_MAX_TOKENS."""
    source = GLASER_CLASSIFIER.read_text(encoding="utf-8")
    match = re.search(r"def _step1_classify_xml\(.*?(?=\ndef )", source, re.DOTALL)
    assert match, "_step1_classify_xml not found in glaser_classifier.py"
    body = match.group(0)

    calls = re.findall(r"max_tokens\s*=\s*([^,\n]+)", body)
    assert not calls, (
        "the step-1 classifier must not override max_tokens; a cap below "
        f"{MIN_PRO_MAX_TOKENS} is consumed by the model's reasoning and "
        f"returns empty content. Found: {calls}"
    )


# ── 5. A degraded classification must not look like a completed one ────
#
# The old code wrapped the whole document in `<baseline_data>` when Step 1
# produced nothing usable and still returned status="completed", valid=True.
# Every segment looked classified while none actually was. Step 1 now raises
# ``ClassificationUnavailable`` and the orchestrator returns status="degraded"
# with valid=False, so the task can fail loudly and leave the doc retryable.

_DEGRADED_PROBE = r"""
import sys

sys.path.insert(0, "/app")

import glaser_classifier as gc


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeSession:
    def __init__(self):
        self.committed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        if "SELECT metadatos" in sql:
            return FakeResult([({"texto_extraido": "Primero uno. Luego dos."},)])
        if "FROM segmentos" in sql:
            return FakeResult(
                [
                    ("11111111-1111-1111-1111-111111111111", "Primero uno.", 0),
                    ("22222222-2222-2222-2222-222222222222", "Luego dos.", 1),
                ]
            )
        return FakeResult([])

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def fake_step1(*args, **kwargs):
    raise gc.ClassificationUnavailable("probe: contenido vacío")


assert hasattr(gc, "ClassificationUnavailable"), "no ClassificationUnavailable"
gc._step1_classify_xml = fake_step1

result = gc.classify_document_with_validation(
    "doc-12345678", "proj-12345678", FakeSession(), llm_client=None
)

assert result["status"] == "degraded", result
assert result["valid"] is False, result
assert "probe" in (result.get("reason") or ""), result
assert result["segments_classified"] == 2, result

print("ok")
"""


def test_classifier_reports_degraded_instead_of_completed(docker: bool) -> None:
    from tests.workflow.conftest import docker_compose_exec

    proc = docker_compose_exec(
        "worker-heavy", "python", "-c", _DEGRADED_PROBE, timeout=90
    )
    assert proc.returncode == 0, (
        "a failed Step 1 is still reported as a successful classification:\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1200]}"
    )
    assert "ok" in proc.stdout


def test_degraded_status_fails_the_run() -> None:
    """Neither caller may let a degraded classification pass as success."""
    source = (REPO / "workers" / "heavy" / "tasks.py").read_text(encoding="utf-8")
    assert source.count('result.get("status") == "degraded"') >= 2, (
        "both _classify_glaser_types_for_doc and task_run_glaser_classifier must "
        "treat status='degraded' as a failure"
    )
    assert "raise ClassificationUnavailable" in source
