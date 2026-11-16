"""Read-only HTTP contracts for the pipeline router.

Scope
-----
Every test here is non-mutating and fast.  The GET routes are exercised
against the seeded project, while the POST routes only ever send payloads
that the server rejects *before* ``celery_app.send_task`` is reached.

That constraint matters: ``run-agent`` does not validate ``agent_id``
against a registry (it forwards the string straight to Celery), and
``celery_app`` has no eager mode, so pairing a real document id with an
unknown agent id would publish a message to the broker.  We therefore use
an absent document id for the negative run-agent contract and rely on the
``404 Documento no encontrado`` guard.  No valid stage or agent id is ever
posted from this module.

Routes under test (``backend/app/api/v1/pipeline.py``, prefix ``/api/v1``):

    GET  /projects/{project_id}/pipeline/status
    GET  /projects/{project_id}/pipeline/log
    GET  /projects/{project_id}/pipeline/decisions
    GET  /projects/{project_id}/pipeline/tail
    GET  /projects/{project_id}/agent-logs
    GET  /projects/{project_id}/agent-memos
    POST /projects/{project_id}/pipeline/run-agent/{agent_id}
    POST /projects/{project_id}/pipeline/run-stage/{stage_name}
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

PIPELINE = "/api/v1/projects/{pid}/pipeline"
AGENT_LOGS = "/api/v1/projects/{pid}/agent-logs"
AGENT_MEMOS = "/api/v1/projects/{pid}/agent-memos"

REPO = Path(__file__).resolve().parents[2]
PIPELINE_SOURCE = REPO / "backend" / "app" / "api" / "v1" / "pipeline.py"

INCONSISTENCY_CODES = (
    "missing_classified",
    "missing_segmented",
    "segmented_without_segments",
    "segments_unclassified",
)

# (path template, expected top-level JSON type, required keys)
GET_CONTRACTS = [
    pytest.param(
        PIPELINE + "/status",
        dict,
        ("project_id", "documents", "segments", "categories", "hypotheses", "stages"),
        id="status",
    ),
    pytest.param(
        PIPELINE + "/log",
        dict,
        ("project_id", "documents", "summary"),
        id="log",
    ),
    pytest.param(
        PIPELINE + "/decisions",
        dict,
        ("project_id", "decisions", "saturation"),
        id="decisions",
    ),
    pytest.param(PIPELINE + "/tail", dict, ("logs", "count"), id="tail"),
    pytest.param(AGENT_LOGS, list, None, id="agent-logs"),
    pytest.param(AGENT_MEMOS, dict, ("memos", "total", "families"), id="agent-memos"),
]

STATUS_STAGES = (
    "upload",
    "precoding",
    "open_coding",
    "cross_doc",
    "pattern_of_interest",
    "selective",
    "saturation",
)


def _get(api, project_id: str, template: str):
    url = template.format(pid=project_id)
    return api.get(url)


@pytest.mark.parametrize(
    "template,expected_type,required_keys",
    GET_CONTRACTS,
)
def test_get_route_contract(api, project_id, template, expected_type, required_keys):
    """Seeded project: 200, correct payload type, documented keys present."""
    resp = _get(api, project_id, template)
    assert resp.status_code == 200, f"{template} -> {resp.status_code}: {resp.text}"

    payload = resp.json()
    assert isinstance(payload, expected_type), (
        f"{template} returned {type(payload).__name__}, expected "
        f"{expected_type.__name__}: {resp.text}"
    )
    for key in required_keys or ():
        assert key in payload, f"{template} missing key {key!r}: {resp.text}"


def test_status_payload_has_stage_map(api, project_id):
    """``/pipeline/status`` reports every pipeline stage with a known state."""
    resp = api.get(PIPELINE.format(pid=project_id) + "/status")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    stages = body["stages"]
    assert isinstance(stages, dict), resp.text
    assert set(STATUS_STAGES) <= set(stages), (
        f"missing stages {set(STATUS_STAGES) - set(stages)}: {resp.text}"
    )
    for stage, state in stages.items():
        assert state in ("done", "in_progress", "pending"), (
            f"stage {stage!r} has unexpected state {state!r}: {resp.text}"
        )

    assert body["project_id"] == project_id, resp.text
    assert isinstance(body["documents"], int), resp.text
    assert isinstance(body["segments"], int), resp.text
    assert isinstance(body["categories"], int), resp.text
    assert isinstance(body["hypotheses"], int), resp.text


@pytest.mark.parametrize(
    "template,expected_type,required_keys",
    GET_CONTRACTS,
)
def test_unknown_project_returns_empty_payload(
    api, template, expected_type, required_keys
):
    """Unknown UUIDs are not 404s: the routes are project-state readers.

    ``/status``, ``/log``, ``/decisions``, ``/tail`` and ``/agent-memos``
    never look up the project row, so they answer 200 with an empty body.
    ``/agent-logs`` answers with a bare empty list.
    """
    missing_pid = str(uuid.uuid4())
    resp = _get(api, missing_pid, template)

    assert resp.status_code == 200, f"{template} -> {resp.status_code}: {resp.text}"
    payload = resp.json()
    assert isinstance(payload, expected_type), resp.text

    if template.endswith("/status"):
        assert payload["documents"] == 0, resp.text
        assert payload["segments"] == 0, resp.text
        assert payload["categories"] == 0, resp.text
        assert payload["hypotheses"] == 0, resp.text
        assert all(state == "pending" for state in payload["stages"].values()), (
            resp.text
        )
    elif template.endswith("/log"):
        assert payload["documents"] == [], resp.text
        assert payload["summary"]["total"] == 0, resp.text
    elif template.endswith("/decisions"):
        assert payload["decisions"] == [], resp.text
        assert payload["saturation"] == {}, resp.text
    elif template.endswith("/tail"):
        assert payload["logs"] == [], resp.text
        assert payload["count"] == 0, resp.text
    elif template.endswith("/agent-memos"):
        assert payload["memos"] == [], resp.text
        assert payload["total"] == 0, resp.text
    elif template.endswith("/agent-logs"):
        assert payload == [], resp.text


def test_status_requires_auth(anon_api, project_id):
    """``/pipeline/status`` depends on ``get_current_user``."""
    resp = anon_api.get(PIPELINE.format(pid=project_id) + "/status")
    assert resp.status_code in (401, 403), (
        f"unauthenticated status -> {resp.status_code}: {resp.text}"
    )


def test_run_agent_requires_auth(anon_api, project_id):
    """``/pipeline/run-agent/{id}`` depends on ``get_current_user``."""
    url = PIPELINE.format(pid=project_id) + "/run-agent/does-not-exist-agent"
    resp = anon_api.post(url, json={"document_id": str(uuid.uuid4())})
    assert resp.status_code in (401, 403), (
        f"unauthenticated run-agent -> {resp.status_code}: {resp.text}"
    )


def test_run_agent_unknown_document_returns_404(api, project_id, documents):
    """An absent document id is rejected before any Celery dispatch.

    The handler first resolves ``body["document_id"]``; a missing document
    yields ``404 Documento no encontrado``.  This is the only safe way to
    exercise the run-agent error path without publishing a task: with a
    real document id the handler would call ``celery_app.send_task`` with
    the unknown agent name (Celery does not validate task names).
    """
    if not documents:
        pytest.skip("the test project has no documents")

    # Prove the fixture ids are UUID-shaped, i.e. the documented body shape
    # would reach the document lookup rather than failing parsing.
    uuid.UUID(str(documents[0]["id"]))

    absent_doc = str(uuid.uuid4())
    url = PIPELINE.format(pid=project_id) + "/run-agent/does-not-exist-agent"
    resp = api.post(url, json={"document_id": absent_doc})

    assert resp.status_code == 404, (
        f"run-agent with absent document -> {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "detail" in body, f"missing detail field: {resp.text}"
    assert "documento" in str(body["detail"]).lower(), resp.text


def test_run_stage_unknown_stage_returns_400(api, project_id):
    """Unknown stage names are rejected with 400, never a 500 or dispatch."""
    url = PIPELINE.format(pid=project_id) + "/run-stage/not-a-stage"
    resp = api.post(url)

    assert resp.status_code == 400, (
        f"run-stage with unknown stage -> {resp.status_code}: {resp.text}"
    )
    assert resp.status_code < 500, resp.text
    body = resp.json()
    assert "detail" in body, f"missing detail field: {resp.text}"
    assert "unknown stage" in str(body["detail"]).lower(), resp.text


# ── Classify-first ladder ─────────────────────────────────────────────


def test_log_payload_exposes_classification_and_inconsistencies(api, project_id):
    """Each document reports classification, incidents and inconsistencies.

    ``classified_count``/``incidents_count`` feed the per-document badges and
    ``inconsistencies`` feeds the detector that warns about states the
    classify-first ladder cannot produce.
    """
    resp = api.get(PIPELINE.format(pid=project_id) + "/log")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    summary = body["summary"]
    assert isinstance(summary.get("docs_inconsistent"), int), resp.text
    assert isinstance(summary.get("docs_need_classify"), int), resp.text
    # The pre-existing keys must keep their type.
    assert isinstance(summary["need_classify"], int), resp.text
    assert isinstance(summary["total"], int), resp.text

    for doc in body["documents"]:
        assert isinstance(doc.get("has_classification"), bool), resp.text
        assert isinstance(doc.get("classified_count"), int), resp.text
        assert isinstance(doc.get("incidents_count"), int), resp.text
        assert isinstance(doc.get("inconsistencies"), list), resp.text

        assert isinstance(doc["steps"].get("classified"), bool), resp.text
        assert isinstance(doc["steps"].get("incidents"), bool), resp.text
        # Si el detector reporta una inconsistencia, tiene que ser un código
        # conocido por la UI.
        for code in doc["inconsistencies"]:
            assert code in INCONSISTENCY_CODES, f"unknown code {code!r}: {resp.text}"


def test_next_action_ladder_checks_classification_before_segments():
    """Source pin: the ladder is classify-first.

    Under classify-first the classifier runs on the text and segmentation
    derives from it, so a document without classification metadata is a
    ``classify`` case even when it already has segments. Checking ``n_segs``
    first would send a classify-first document straight to segmentation.
    """
    src = PIPELINE_SOURCE.read_text(encoding="utf-8")

    class_start = src.index("async def get_pipeline_log(")
    classify_at = src.index("elif not has_classification:", class_start)
    segment_at = src.index("elif not n_segs:", class_start)
    assert classify_at < segment_at, (
        "get_pipeline_log must test `not has_classification` before `not n_segs`"
    )

    # Classification is read from the DB, not inferred from estado;
    # texto_clasificado cubre los documentos legacy.
    assert "metadatos ? 'glaser_blocks'" in src, (
        "has_classification must come from metadatos ? 'glaser_blocks'"
    )
    assert "metadatos ? 'texto_clasificado'" in src, (
        "legacy documents store the classification in texto_clasificado"
    )

    for code in INCONSISTENCY_CODES:
        assert f'"{code}"' in src, f"inconsistency code {code!r} missing from the log"


def test_extractor_guard_accepts_segmented_documents():
    """Source pin: the 409 guard mirrors EXTRACTOR_STATES under classify-first.

    ``process_document_agents_a`` consumes segments that already carry their
    Glaser tag, so ``segmentado`` is the normal entry point and ``clasificado``
    (no segments yet) is not.
    """
    src = PIPELINE_SOURCE.read_text(encoding="utf-8")
    guard_at = src.index('if task_name == "process_document_agents_a"')
    guard = src[guard_at : src.index("task = celery_app.send_task", guard_at)]

    assert '"segmentado"' in guard, (
        "the extractor guard must accept segmentado, the normal classify-first "
        "input (segments already tagged)"
    )
    assert "Segmentá el texto ya clasificado antes de extraer." in guard, (
        "the guard message must explain that the text has to be classified and "
        "segmented first"
    )
