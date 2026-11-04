"""Idempotency contract for the unified pattern extractor.

Why this test exists
--------------------
``extract_patterns_and_incidents`` used to INSERT one ``extracted_incidents``
row per incident on every run and never remove the previous batch. Re-running
the same document for the same project (a retry, a resumed pipeline, or a
manual trigger from the UI) therefore duplicated every incident, and the
duplicates then fed the comparison stage.

The fix adds ``replace_existing=True``: once the LLM call has succeeded, the
document's previous incidents (plus the ``incident_comparisons`` rows that
reference them, whose FKs are ``NO ACTION``) are deleted before the new rows
are inserted.

Two layers of coverage:

* a fast, hermetic static test that the parameter exists and the deletes are
  ordered before the INSERT (the worker module cannot be imported on the host:
  it needs sqlalchemy and the container's ``/app`` path);
* an opt-in ``slow`` probe that runs inside ``worker-heavy`` against the live
  docker compose stack and calls the extractor twice.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

from tests.workflow.conftest import docker_compose_exec

REPO_ROOT = Path(__file__).resolve().parents[2]
PATTERN_EXTRACTOR = REPO_ROOT / "workers" / "heavy" / "pattern_extractor.py"
FUNC_NAME = "extract_patterns_and_incidents"

# Calls the extractor twice against one document and fails if the second run
# changed the number of persisted incidents. Document/project arrive via argv
# so the probe text needs no interpolation. Runs inside worker-heavy.
IDEMPOTENCY_PROBE = r"""
import sys

from sqlalchemy import text

from database import SessionLocal
from pattern_extractor import extract_patterns_and_incidents

doc, project = sys.argv[1], sys.argv[2]


def count_incidents():
    session = SessionLocal()
    try:
        return session.execute(
            text(
                "SELECT COUNT(*) FROM extracted_incidents "
                "WHERE documento_id = :did AND proyecto_id = :pid"
            ),
            {"did": doc, "pid": project},
        ).scalar_one()
    finally:
        session.close()


result1 = extract_patterns_and_incidents(doc, project)
after_first = count_incidents()
print(f"after run 1: incidents={after_first} result={result1}", flush=True)

result2 = extract_patterns_and_incidents(doc, project)
after_second = count_incidents()
print(f"after run 2: incidents={after_second} result={result2}", flush=True)

if after_second != after_first:
    raise SystemExit(
        f"NOT IDEMPOTENT: {after_first} incidents after run 1, "
        f"{after_second} after run 2 (doc={doc} project={project})"
    )

print("ok")
"""


# ── Static contract (fast, no stack) ───────────────────────────────────


def _function_node(
    path: Path, name: str
) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return source, node
    raise AssertionError(f"Function {name!r} not found in {path}")


def _squash(text: str) -> str:
    """Drop all whitespace so SQL/formatting changes do not break the test."""
    return re.sub(r"\s+", "", text)


def test_extract_patterns_and_incidents_accepts_replace_existing():
    """Re-runs need an opt-out, and the default must preserve idempotency."""
    _, func = _function_node(PATTERN_EXTRACTOR, FUNC_NAME)

    params = {arg.arg: arg for arg in (*func.args.args, *func.args.kwonlyargs)}
    assert "replace_existing" in params, (
        f"{FUNC_NAME} has no replace_existing parameter; re-running it for the "
        "same document would duplicate every incident. Found parameters: "
        f"{sorted(params)}"
    )

    positional = [arg.arg for arg in func.args.args]
    default_start = len(positional) - len(func.args.defaults)
    defaults = {
        positional[default_start + i]: default
        for i, default in enumerate(func.args.defaults)
    }
    assert "replace_existing" in defaults, (
        "replace_existing must have a default; existing callers "
        "(workers/heavy/tasks.py) call the extractor with two positional args"
    )
    default = defaults["replace_existing"]
    assert isinstance(default, ast.Constant) and default.value is True, (
        "replace_existing must default to True so the idempotent path is the "
        "one taken by the pipeline"
    )


def test_deletes_precede_inserts_and_follow_the_mock_guard():
    """Dependent rows first, then incidents, then the new INSERT."""
    source, func = _function_node(PATTERN_EXTRACTOR, FUNC_NAME)
    segment = ast.get_source_segment(source, func)
    assert segment is not None, "ast.get_source_segment returned None"
    body = _squash(segment)

    guard = body.find('response.get("mock_note")')
    comparisons_delete = body.find("DELETEFROMincident_comparisons")
    incidents_delete = body.find("DELETEFROMextracted_incidents")
    insert = body.find("INSERTINTOextracted_incidents")

    assert guard != -1, (
        f"{FUNC_NAME} no longer short-circuits on the mock/error response; the "
        "delete must stay behind that guard so a failed LLM call cannot wipe "
        "existing incidents"
    )
    assert comparisons_delete != -1, (
        f"{FUNC_NAME} never runs `DELETE FROM incident_comparisons`. Both FKs "
        "(incident_a_id, incident_b_id) are ON DELETE NO ACTION, so deleting "
        "extracted_incidents first would raise a foreign-key violation"
    )
    assert incidents_delete != -1, (
        f"{FUNC_NAME} never runs `DELETE FROM extracted_incidents`; re-runs "
        "would keep duplicating incidents"
    )
    assert insert != -1, (
        f"{FUNC_NAME} no longer inserts into extracted_incidents; this test "
        "must be updated alongside the persistence layer"
    )

    assert guard < comparisons_delete, (
        "the mock/error guard must precede the deletes: the LLM result is only "
        "trustworthy after it"
    )
    assert comparisons_delete < incidents_delete, (
        "incident_comparisons must be deleted before extracted_incidents; its "
        "FKs are NO ACTION, so the reverse order fails with a FK violation"
    )
    assert incidents_delete < insert, (
        "previous incidents must be deleted before the new rows are inserted"
    )


# ── Live stack probe (opt-in) ──────────────────────────────────────────


@pytest.mark.slow
def test_extract_patterns_and_incidents_is_idempotent(docker):
    """Two consecutive runs must leave the same number of incidents.

    Mutating: it deletes and rewrites the extraction output for the document
    under test, so ids must be supplied explicitly through the environment.
    """
    doc_id = (os.environ.get("GENO_IDEMPOTENCY_DOC") or "").strip()
    project_id = (os.environ.get("GENO_PROJECT_ID") or "").strip()
    if not doc_id or not project_id:
        pytest.skip(
            "set GENO_IDEMPOTENCY_DOC=<document uuid> and "
            "GENO_PROJECT_ID=<project uuid> to run this mutating probe"
        )

    proc = docker_compose_exec(
        "worker-heavy",
        "python",
        "-c",
        IDEMPOTENCY_PROBE,
        doc_id,
        project_id,
        timeout=600,
    )
    output = f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1200]}"
    assert proc.returncode == 0, (
        "extract_patterns_and_incidents is not idempotent (or the probe "
        f"crashed) for doc={doc_id} project={project_id}:\n{output}"
    )
    assert "ok" in proc.stdout, f"probe produced no success marker:\n{output}"
