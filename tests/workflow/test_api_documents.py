"""HTTP contract tests for the document endpoints the frontend actually calls.

The UI talks to the API through the rsbuild proxy on ``http://localhost:3000``,
so these tests exercise that exact surface. They are deliberately read-mostly:
nothing here dispatches Celery work or mutates a real document.

Two behaviours are pinned because they caused frontend bugs:

* ``POST /{document_id}/punctuate`` answers ``{"status": "dispatched",
  "task_id": ...}``; the worker later owns the ``estado`` transition (even when
  ``changes_made`` is false, it ends at ``preprocesado``). The frontend must
  refetch after the task, not infer the state from the POST response.
* The list endpoint always exposes ``texto_original``/``texto_extraido`` (empty
  strings are used as "no text"), and ``estado`` is a free varchar, so the UI
  has to tolerate every value in :data:`KNOWN_ESTADOS`.

Route behaviour was verified against ``backend/app/api/v1/documents.py``.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

DOCS = "/api/v1/documents"

# Values observed in the backend workers, transition table and UI. ``estado`` is
# a free varchar, so this is the contract the UI has to render without crashing.
KNOWN_ESTADOS = {
    "crudo",
    "preprocesando",
    "preprocesado",
    "clasificando",
    "clasificado",
    "segmentando",
    "segmentado",
    "procesando",
    "incidentes_extraidos",
    "procesado",
    "listo",
    "codificando",
    "codificado",
    "error",
    "resumiendo",
    "resumido",
    "sintetizado",
}


def _uuid() -> str:
    """A random UUID that cannot belong to any real document."""
    return str(uuid.uuid4())


# ── Listing ────────────────────────────────────────────────────────────


def test_list_documents_returns_items_with_known_estado(
    api: httpx.Client, project_id: str
) -> None:
    r = api.get(DOCS, params={"proyecto_id": project_id})
    assert r.status_code == 200, r.text

    payload = r.json()
    assert isinstance(payload, list), r.text
    for doc in payload:
        assert "id" in doc, r.text
        assert "estado" in doc, r.text
        estado = str(doc["estado"]).strip()
        assert estado in KNOWN_ESTADOS, f"unexpected estado {estado!r}: {r.text}"
        # The frontend reads these fields to pick the text shown on a card.
        assert "texto_original" in doc, r.text
        assert "texto_extraido" in doc, r.text


def test_list_documents_for_unknown_project_is_empty(
    api: httpx.Client,
) -> None:
    r = api.get(DOCS, params={"proyecto_id": _uuid()})
    assert r.status_code == 200, r.text
    assert r.json() == [], r.text


def test_list_documents_requires_proyecto_id(api: httpx.Client) -> None:
    # `proyecto_id: UUID = Query(...)` is required, so omitting it is a 422.
    r = api.get(DOCS)
    assert r.status_code == 422, r.text


def test_list_documents_rejects_malformed_proyecto_id(api: httpx.Client) -> None:
    r = api.get(DOCS, params={"proyecto_id": "not-a-uuid"})
    assert r.status_code == 422, r.text


def test_list_documents_requires_auth(anon_api: httpx.Client, project_id: str) -> None:
    # HTTPBearer rejects a missing Authorization header (401 or 403 depending
    # on the FastAPI version); either is fine as long as data is not leaked.
    r = anon_api.get(DOCS, params={"proyecto_id": project_id})
    assert r.status_code in (401, 403), r.text


# ── Punctuation (the endpoint behind the "dispatched" bug) ────────────


def test_punctuate_unknown_document_returns_not_found(api: httpx.Client) -> None:
    r = api.post(f"{DOCS}/{_uuid()}/punctuate")
    assert r.status_code == 404, r.text
    assert "no encontrado" in r.json().get("detail", "").lower(), r.text


def test_punctuate_requires_auth(anon_api: httpx.Client) -> None:
    r = anon_api.post(f"{DOCS}/{_uuid()}/punctuate")
    assert r.status_code in (401, 403), r.text


# ── Deletion ──────────────────────────────────────────────────────────


def test_delete_unknown_document_returns_not_found(api: httpx.Client) -> None:
    r = api.delete(f"{DOCS}/{_uuid()}")
    assert r.status_code == 404, r.text
    assert "no encontrado" in r.json().get("detail", "").lower(), r.text


def test_delete_document_requires_auth(anon_api: httpx.Client) -> None:
    r = anon_api.delete(f"{DOCS}/{_uuid()}")
    assert r.status_code in (401, 403), r.text


def test_delete_glaser_classification_unknown_document_is_idempotent(
    api: httpx.Client,
) -> None:
    # Source check: the handler issues a bare UPDATE ... WHERE id = :did and
    # never loads the document, so a missing id is a silent no-op with 200,
    # not a 404. Pinned here so a future route change is visible.
    r = api.delete(f"{DOCS}/{_uuid()}/classify-glaser")
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "ok", r.text


# ── Segmentation ──────────────────────────────────────────────────────


def test_segment_unknown_document_returns_not_found(api: httpx.Client) -> None:
    # `segment_document` fetches the row before looking at the text.
    r = api.post(f"{DOCS}/{_uuid()}/segment")
    assert r.status_code == 404, r.text
    assert "no encontrado" in r.json().get("detail", "").lower(), r.text


# ── Task polling ──────────────────────────────────────────────────────


def test_task_status_reports_status_for_unknown_task(api: httpx.Client) -> None:
    # `get_task_status` never checks the database or the broker result: it
    # wraps AsyncResult and always answers 200 with a `status` field.
    task_id = _uuid()
    r = api.get(f"{DOCS}/tasks/{task_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("task_id") == task_id, r.text
    assert isinstance(body.get("status"), str) and body["status"], r.text


# ── Glaser classification guard ───────────────────────────────────────


def test_classify_glaser_on_crudo_document_without_text_is_rejected(
    api: httpx.Client, doc_by_state
) -> None:
    doc = doc_by_state("crudo")
    if doc is None:
        pytest.skip("the test project has no document in estado='crudo'")

    # The handler reads *metadatos*, not the model property, and documents that
    # still carry text would dispatch a real heavy Celery job (200, not 400).
    # Skip instead of triggering LLM work from a contract test.
    if (
        str(doc.get("texto_preprocesado") or "").strip()
        or str(doc.get("texto_extraido") or "").strip()
    ):
        pytest.skip(
            "crudo document still carries text; POST would dispatch the Glaser "
            "classifier instead of returning the 400 no-text branch"
        )

    r = api.post(f"{DOCS}/{doc['id']}/classify-glaser")
    assert r.status_code == 400, r.text
    assert "texto" in r.json().get("detail", "").lower(), r.text
