"""Deletion contracts for the agent-memo endpoints.

Why this module exists
----------------------
The UI reads its memo cards from ``GET /projects/{id}/agent-memos``, which
composes them from ``population_contexts`` (``pc-*``), ``document_processes``
(``dp-*``) and ``categorias`` (``cat-*``) — not from the ``memos`` table.
``DELETE /projects/{id}/agent-memos`` is the bulk counterpart: it removes rows
from exactly those three tables, in one transaction, and never reports success
when it deleted nothing.

Covered here:

* the bulk delete removes the rows of *that* project only;
* the ``family`` filter is honoured (other families survive);
* an empty project is a 404, not a silent ``{"deleted": 0}``;
* unknown projects / unknown families are 404 / 400;
* ``DELETE /agent-outputs/{memo_id}`` answers 404 for an absent row.

The fixtures below create throw-away projects through the API and write their
``population_contexts`` rows with ``psql`` (the API has no endpoint that
creates one directly), then remove both the rows and the projects. Nothing in
here touches the seeded project.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

AGENT_MEMOS = "/api/v1/projects/{pid}/agent-memos"
AGENT_OUTPUTS = "/api/v1/agent-outputs/{memo_id}"


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def memo_projects(api: httpx.Client, db):
    """Factory for throw-away projects, with automatic cleanup.

    ``new_project()`` returns a project id; ``add_pc(pid)`` inserts one
    ``population_contexts`` row in it and returns the row id.
    """

    project_ids: list[str] = []
    row_ids: list[str] = []
    prefix = f"workflow-memos-{uuid.uuid4().hex[:8]}"

    def new_project() -> str:
        resp = api.post(
            "/api/v1/projects",
            json={"nombre": f"{prefix}-{len(project_ids)}"},
        )
        assert resp.status_code in (200, 201), resp.text
        pid = resp.json()["id"]
        project_ids.append(pid)
        return pid

    def add_pc(pid: str) -> str:
        row_id = str(uuid.uuid4())
        db(
            "INSERT INTO population_contexts (id, proyecto_id, surprising_details, "
            "language_patterns, data_production_context) VALUES "
            f"('{row_id}', '{pid}', 'fixture pc', '', '')"
        )
        row_ids.append(row_id)
        return row_id

    try:
        yield new_project, add_pc
    finally:
        # Rows first: proyectos has no cascade onto population_contexts, so a
        # leftover row would make the project DELETE fail with a FK error.
        for row_id in row_ids:
            db(f"DELETE FROM population_contexts WHERE id = '{row_id}'")
        for pid in project_ids:
            api.delete(f"/api/v1/projects/{pid}")
        # A POST that timed out client-side can still have created the project,
        # and then its id never reaches ``project_ids``. Sweep them by name.
        listing = api.get("/api/v1/projects")
        if listing.status_code == 200:
            payload = listing.json()
            projects = (
                payload if isinstance(payload, list) else payload.get("items", [])
            )
            for proj in projects:
                if str(proj.get("nombre", "")).startswith(prefix):
                    api.delete(f"/api/v1/projects/{proj['id']}")


def _memo_ids(api: httpx.Client, pid: str) -> list[str]:
    resp = api.get(AGENT_MEMOS.format(pid=pid))
    assert resp.status_code == 200, resp.text
    return [memo["id"] for memo in resp.json()["memos"]]


# ── Bulk delete ────────────────────────────────────────────────────────


def test_bulk_delete_removes_only_the_target_project(api, memo_projects):
    """The rows of the addressed project go; another project keeps its own."""
    new_project, add_pc = memo_projects
    target = new_project()
    other = new_project()
    target_row = add_pc(target)
    other_row = add_pc(other)

    assert f"pc-{target_row}" in _memo_ids(api, target)
    assert f"pc-{other_row}" in _memo_ids(api, other)

    resp = api.delete(AGENT_MEMOS.format(pid=target))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] == 1, resp.text
    assert body["by_table"]["population_contexts"] == 1, resp.text
    assert {k: v for k, v in body["by_table"].items() if v} == {
        "population_contexts": 1
    }, resp.text

    assert _memo_ids(api, target) == [], resp.text
    assert f"pc-{other_row}" in _memo_ids(api, other), resp.text


def test_bulk_delete_family_filter_spares_other_families(api, memo_projects):
    """``?family=inductive_data`` only looks at ``categorias``."""
    new_project, add_pc = memo_projects
    pid = new_project()
    row_id = add_pc(pid)

    resp = api.delete(AGENT_MEMOS.format(pid=pid), params={"family": "inductive_data"})
    assert resp.status_code == 404, resp.text

    assert f"pc-{row_id}" in _memo_ids(api, pid), (
        "a descriptive_data row was removed by the inductive_data filter"
    )


def test_bulk_delete_404_when_there_is_nothing_to_delete(api, memo_projects):
    """No rows is an explicit 404, never a silent success."""
    new_project, _ = memo_projects
    pid = new_project()

    resp = api.delete(AGENT_MEMOS.format(pid=pid))
    assert resp.status_code == 404, resp.text
    detail = resp.json()["detail"].lower()
    assert "memos" in detail, resp.text
    assert "deleted" not in resp.json(), resp.text


def test_bulk_delete_unknown_project_returns_404(api):
    resp = api.delete(AGENT_MEMOS.format(pid=uuid.uuid4()))
    assert resp.status_code == 404, resp.text
    assert "proyecto" in resp.json()["detail"].lower(), resp.text


def test_bulk_delete_rejects_unknown_family(api, memo_projects):
    new_project, _ = memo_projects
    pid = new_project()

    resp = api.delete(AGENT_MEMOS.format(pid=pid), params={"family": "nope"})
    assert resp.status_code == 400, resp.text
    assert "familia" in resp.json()["detail"].lower(), resp.text


def test_bulk_delete_requires_auth(anon_api, project_id):
    resp = anon_api.delete(AGENT_MEMOS.format(pid=project_id))
    assert resp.status_code in (401, 403), resp.text


# ── Single agent output ────────────────────────────────────────────────


@pytest.mark.parametrize("prefix", ["pc", "dp", "cat"])
def test_delete_unknown_agent_output_returns_404(api, prefix):
    """A delete that removes no row must not answer 200."""
    resp = api.delete(AGENT_OUTPUTS.format(memo_id=f"{prefix}-{uuid.uuid4()}"))
    assert resp.status_code == 404, resp.text
    assert "no encontrado" in resp.json()["detail"].lower(), resp.text


def test_delete_agent_output_rejects_unknown_prefix(api):
    resp = api.delete(AGENT_OUTPUTS.format(memo_id=f"zz-{uuid.uuid4()}"))
    assert resp.status_code == 400, resp.text


def test_delete_agent_output_requires_auth(anon_api):
    resp = anon_api.delete(AGENT_OUTPUTS.format(memo_id=f"pc-{uuid.uuid4()}"))
    assert resp.status_code in (401, 403), resp.text
