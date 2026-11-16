"""CRUD contracts for the ``hitl_decisions`` resource.

Why this module exists
----------------------
The HITL panel needs to list, inspect, edit and delete stored decisions beyond
the original ``pending`` / ``decide`` / ``reset`` trio, without breaking those
legacy routes. Every row used here is created through the API inside a
throw-away project (``temp_project``), so the seeded project is never touched.

Routes under test (``backend/app/api/v1/hitl.py``, prefix ``/api/v1``):

    GET    /projects/{pid}/hitl/decisions
    POST   /projects/{pid}/hitl/decisions
    GET    /projects/{pid}/hitl/decisions/{id}
    PATCH  /projects/{pid}/hitl/decisions/{id}
    DELETE /projects/{pid}/hitl/decisions/{id}
    DELETE /projects/{pid}/hitl/decisions
    GET    /projects/{pid}/hitl/pending        (compatibilidad)
"""

from __future__ import annotations

import uuid

import httpx
import pytest

DECISIONS = "/api/v1/projects/{pid}/hitl/decisions"
DECISION = "/api/v1/projects/{pid}/hitl/decisions/{did}"
PENDING = "/api/v1/projects/{pid}/hitl/pending"


@pytest.fixture
def hitl_project(api: httpx.Client, temp_project: str) -> str:
    """``temp_project`` con purga de sus ``hitl_decisions`` antes del borrado.

    La FK ``hitl_decisions.project_id`` no tiene ``ON DELETE CASCADE`` (migración
    018f5945d0ca), así que una fila sobrante haría fallar el DELETE del proyecto
    en el teardown de ``temp_project``. Este finalizador corre antes que el
    suyo porque depende de él.
    """
    yield temp_project

    listing = api.get(DECISIONS.format(pid=temp_project), params={"limit": 500})
    if listing.status_code != 200:
        return
    ids = [item["id"] for item in listing.json().get("items", [])]
    if ids:
        _delete_json(api, DECISIONS.format(pid=temp_project), {"ids": ids})


def _delete_json(api: httpx.Client, url: str, payload: dict) -> httpx.Response:
    """DELETE con body.

    ``httpx.Client.delete`` no acepta ``json=`` en esta versión, así que el
    body de los borrados masivos se envía con ``request``.
    """
    return api.request("DELETE", url, json=payload)


def _create(api: httpx.Client, pid: str, **overrides) -> dict:
    """Crea una decisión vía API y devuelve el payload de respuesta."""
    body = {"gate_name": "pattern_of_interest", "note": "", **overrides}
    resp = api.post(DECISIONS.format(pid=pid), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Alta + listado ─────────────────────────────────────────────────────


def test_create_then_list_with_counts(api, hitl_project):
    """Un alta 201 debe aparecer en el listado con ``counts`` coherente."""
    created = _create(api, hitl_project, note="semilla")
    assert created["id"], created
    assert created["status"] == "pending"
    assert created["researcher_note"] == "semilla"
    # proposal/critic_verdict salen como objetos, nunca como null.
    assert created["proposal"] == {}, created
    assert created["critic_verdict"] == {}, created

    resp = api.get(DECISIONS.format(pid=hitl_project))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert [item["id"] for item in body["items"]] == [created["id"]], body
    assert body["total"] == 1, body
    assert set(body["counts"]) == {"pending", "accepted", "modified", "rejected"}
    assert body["counts"]["pending"] == 1, body
    assert body["counts"]["accepted"] == 0, body


def test_list_filter_keeps_project_wide_counts(api, hitl_project):
    """``total`` respeta el filtro; ``counts`` sigue mirando todo el proyecto."""
    pending = _create(api, hitl_project)
    accepted = _create(api, hitl_project, status="accepted")
    assert accepted["decided_at"] is not None, accepted

    resp = api.get(DECISIONS.format(pid=hitl_project), params={"status": "accepted"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 1, body
    assert [item["id"] for item in body["items"]] == [accepted["id"]], body
    # Las pastillas del filtro no deben encogerse al filtrar.
    assert body["counts"]["pending"] == 1, body
    assert body["counts"]["accepted"] == 1, body
    assert pending["id"] not in [item["id"] for item in body["items"]], body


# ── Detalle ────────────────────────────────────────────────────────────


def test_get_by_id_and_404_for_unknown(api, hitl_project):
    created = _create(api, hitl_project)

    resp = api.get(DECISION.format(pid=hitl_project, did=created["id"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == created["id"]

    missing = api.get(DECISION.format(pid=hitl_project, did=uuid.uuid4()))
    assert missing.status_code == 404, missing.text


# ── Edición ────────────────────────────────────────────────────────────


def test_patch_note_does_not_resolve(api, hitl_project):
    """Cambiar solo la nota no toca el estado ni ``decided_at``."""
    created = _create(api, hitl_project)

    resp = api.patch(
        DECISION.format(pid=hitl_project, did=created["id"]),
        json={"note": "revisada por el investigador"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["researcher_note"] == "revisada por el investigador"
    assert body["status"] == "pending"
    assert body["researcher_decision"] is None
    assert body["decided_at"] is None


def test_patch_to_accepted_sets_decision_and_timestamp(api, hitl_project):
    """Resolver a ``accepted`` escribe ``researcher_decision`` y ``decided_at``."""
    created = _create(api, hitl_project)

    resp = api.patch(
        DECISION.format(pid=hitl_project, did=created["id"]),
        json={"status": "accepted"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["researcher_decision"] == "accept"
    assert body["decided_at"] is not None


# ── Borrado ────────────────────────────────────────────────────────────


def test_delete_individual_removes_it_from_listing(api, hitl_project):
    created = _create(api, hitl_project)

    resp = api.delete(DECISION.format(pid=hitl_project, did=created["id"]))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "deleted": 1}, resp.text

    listing = api.get(DECISIONS.format(pid=hitl_project)).json()
    assert created["id"] not in [item["id"] for item in listing["items"]], listing

    # Repetir el delete es un 404, nunca un éxito silencioso.
    again = api.delete(DECISION.format(pid=hitl_project, did=created["id"]))
    assert again.status_code == 404, again.text


def test_bulk_delete_without_filters_is_400(api, hitl_project):
    """Un body vacío no puede borrar todo el proyecto por accidente."""
    _create(api, hitl_project)

    resp = _delete_json(api, DECISIONS.format(pid=hitl_project), {})
    assert resp.status_code == 400, resp.text
    assert "filtro" in resp.json()["detail"].lower(), resp.text

    listing = api.get(DECISIONS.format(pid=hitl_project)).json()
    assert listing["total"] == 1, listing


def test_bulk_delete_by_ids(api, hitl_project):
    first = _create(api, hitl_project)
    second = _create(api, hitl_project)

    resp = _delete_json(api, DECISIONS.format(pid=hitl_project), {"ids": [first["id"]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 1, resp.text

    listing = api.get(DECISIONS.format(pid=hitl_project)).json()
    remaining = [item["id"] for item in listing["items"]]
    assert first["id"] not in remaining, listing
    assert second["id"] in remaining, listing


# ── Compatibilidad ─────────────────────────────────────────────────────


def test_pending_route_still_responds(api, hitl_project):
    """El endpoint heredado ``/hitl/pending`` debe seguir devolviendo 200."""
    _create(api, hitl_project)

    resp = api.get(PENDING.format(pid=hitl_project))
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list), resp.text
