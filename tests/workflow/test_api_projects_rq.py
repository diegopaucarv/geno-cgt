"""HTTP contract tests for the research-question endpoints.

The frontend's "Generar" button calls
``POST /api/v1/projects/{id}/research-question/generate`` (see
``frontend/src/api/client.ts``). That route used to be missing, so the call
returned 404 and the button appeared to do nothing. These tests pin the route,
its persistence into ``population_assumption.research_question`` (the shape
read back by ``GET .../research-question``), and the ``pronoun`` regression in
the project-scoped preview endpoint.

Everything here is deterministic (spaCy conjugation + declarative templates);
no Celery or LLM work is dispatched, so nothing is marked ``slow``.
"""

from __future__ import annotations

import httpx

PROJECTS = "/api/v1/projects"
QUESTION_FIELDS = (
    "research_question",
    "operational_question",
    "oq_discovery",
    "oq_selective",
    "oq_theoretical",
)
OVERRIDE = {
    "population": "niñas",
    "object_of_study": "behavior",
    "processing_verb": "adaptar",
}


def _url(project_id: str, suffix: str) -> str:
    return f"{PROJECTS}/{project_id}/research-question/{suffix}"


def test_generate_route_exists(api: httpx.Client, project_id: str) -> None:
    r = api.post(_url(project_id, "generate"), json={})
    assert r.status_code == 200, r.text

    body = r.json()
    assert body.get("project_id") == project_id
    assert body.get("research_question"), body
    assert body.get("operational_question"), body


def test_generate_persists_and_get_matches(api: httpx.Client, project_id: str) -> None:
    generated = api.post(_url(project_id, "generate"), json={})
    assert generated.status_code == 200, generated.text
    gen_body = generated.json()

    r = api.get(_url(project_id, "").rstrip("/"))
    assert r.status_code == 200, r.text
    stored = r.json()

    for field in QUESTION_FIELDS:
        assert stored.get(field) == gen_body.get(field), field
    assert stored.get("generated_at"), stored


def test_generate_is_idempotent(api: httpx.Client, project_id: str) -> None:
    first = api.post(_url(project_id, "generate"), json=OVERRIDE)
    assert first.status_code == 200, first.text
    second = api.post(_url(project_id, "generate"), json=OVERRIDE)
    assert second.status_code == 200, second.text

    first_body = first.json()
    second_body = second.json()
    for field in QUESTION_FIELDS:
        assert first_body.get(field) == second_body.get(field), field


def test_generate_rejects_missing_population(
    api: httpx.Client, temp_project: str
) -> None:
    r = api.post(_url(temp_project, "generate"), json={})
    if r.status_code == 200:
        # The project got a default population, so exercise the explicit
        # empty-override path instead.
        r = api.post(_url(temp_project, "generate"), json={"population": ""})

    assert r.status_code == 400, r.text
    assert "population" in str(r.json().get("detail", "")).lower(), r.text


def test_preview_does_not_500(api: httpx.Client, project_id: str) -> None:
    r = api.post(_url(project_id, "preview"), json=OVERRIDE)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body.get("research_question"), body
    # Regression: the handler used to reference an undefined ``pronoun``.
    assert "pronoun" in body, body
    assert body["pronoun"], body
