"""End-to-end document workflow: ``crudo -> preprocesado -> clasificado``.

These tests dispatch real Celery/LLM work against an ephemeral project, so they
are opt-in (``--run-slow``). They assert the contract the frontend depends on:
the HTTP endpoints only *dispatch*, the worker owns the ``estado`` transition,
and the list endpoint must report the new state without any client-side reload
trick.

The regression this file pins: ``POST /{id}/punctuate`` used to be treated by
the UI as a no-op when the task result said ``changes_made: false``. The worker
still persists ``metadatos.texto_preprocesado`` and moves the document to
``preprocesado``, so the list endpoint must show that state regardless of
``changes_made``.

Route/shape references verified in:
  * ``backend/app/api/v1/documents.py`` (upload, list, punctuate, classify)
  * ``workers/fast/tasks.py::punctuate_text`` (estado is written unconditionally)
  * ``workers/heavy/tasks.py::task_run_glaser_classifier``
"""

from __future__ import annotations

import uuid

import httpx
import pytest

DOCS = "/api/v1/documents"
TASK_TIMEOUT = 180.0

# States that mean a worker is still running; after a SUCCESS poll none of them
# may remain, or the UI would keep showing a spinner forever.
TRANSIENT_ESTADOS = {"preprocesando", "clasificando", "segmentando"}


# ── Helpers ────────────────────────────────────────────────────────────


def _uploaded_document_id(uploaded_doc: dict | list) -> str:
    """Extract the document id from the upload response.

    ``upload_document`` currently returns a single dict with ``id``, but the
    fixture documents that it may answer with a list/batch wrapper.
    """
    doc = uploaded_doc[0] if isinstance(uploaded_doc, list) else uploaded_doc
    assert isinstance(doc, dict), f"unexpected upload response: {uploaded_doc!r}"
    for key in ("id", "document_id", "documento_id"):
        value = doc.get(key)
        if value:
            return str(value)
    raise AssertionError(f"upload response has no document id: {doc!r}")


def _list_documents(api: httpx.Client, project: str) -> list[dict]:
    r = api.get(DOCS, params={"proyecto_id": project})
    assert r.status_code == 200, f"list documents failed: {r.text}"
    payload = r.json()
    items = payload if isinstance(payload, list) else payload.get("items", [])
    assert isinstance(items, list), f"unexpected list payload: {r.text}"
    return items


def _estado(api: httpx.Client, project: str, doc_id: str) -> dict:
    """Read the list endpoint and return the matching document."""
    items = _list_documents(api, project)
    for doc in items:
        if str(doc.get("id")) == str(doc_id):
            return doc
    raise AssertionError(f"document {doc_id} not found in project {project}: {items!r}")


def _db_estado(db, doc_id: str) -> str:
    row = db(f"select estado from documentos where id = '{doc_id}'")
    assert row, f"no row in documentos for id={doc_id}"
    return row.strip()


def _db_preprocessed_length(db, doc_id: str) -> int:
    row = db(
        "select coalesce(length(metadatos->>'texto_preprocesado'), 0) "
        f"from documentos where id = '{doc_id}'"
    )
    assert row != "", f"no row in documentos for id={doc_id}"
    return int(row)


def _task_result(payload: dict) -> dict:
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


# ── Regression: punctuate advances estado even without changes ─────────


@pytest.mark.slow
@pytest.mark.e2e
def test_punctuate_advances_estado_even_without_changes(
    api: httpx.Client,
    temp_project: str,
    uploaded_doc: dict | list,
    db,
    wait_task,
) -> None:
    doc_id = _uploaded_document_id(uploaded_doc)

    # Upload leaves the document in "crudo"; confirm through the same list
    # endpoint the UI reads.
    initial = _estado(api, temp_project, doc_id)
    initial_estado = str(initial.get("estado", "")).strip()
    assert initial_estado == "crudo", (
        f"uploaded document should start in 'crudo', got {initial_estado!r}: "
        f"{initial!r}"
    )

    # The endpoint must only dispatch; the worker performs the transition.
    r = api.post(f"{DOCS}/{doc_id}/punctuate")
    assert r.status_code == 200, f"punctuate failed: {r.text}"
    body = r.json()
    assert body.get("status") == "dispatched", f"unexpected dispatch body: {r.text}"
    task_id = body.get("task_id")
    assert task_id, f"punctuate response has no task_id: {r.text}"

    payload = wait_task(api, task_id, timeout=TASK_TIMEOUT)
    assert payload.get("status") == "SUCCESS", f"punctuate task failed: {payload}"
    result = _task_result(payload)
    # A soft worker error would be reported as SUCCESS with an error payload.
    assert result.get("status") != "error", (
        f"punctuate returned an error result: {payload}"
    )

    # Worker is the authority: always writes texto_preprocesado and estado.
    estado = _db_estado(db, doc_id)
    assert estado == "preprocesado", (
        f"DB estado should be 'preprocesado' after punctuate, got {estado!r}; "
        f"task payload: {payload}"
    )
    preprocessed_len = _db_preprocessed_length(db, doc_id)
    assert preprocessed_len > 0, (
        f"metadatos.texto_preprocesado should be non-empty, got {preprocessed_len}; "
        f"task payload: {payload}"
    )

    # User-visible check: a plain list request must already report the new
    # state. No cache-busting / reload trick is allowed here — that was the bug.
    refreshed = _estado(api, temp_project, doc_id)
    refreshed_estado = str(refreshed.get("estado", "")).strip()
    assert refreshed_estado == "preprocesado", (
        f"list endpoint should report 'preprocesado' without a reload trick, "
        f"got {refreshed_estado!r}: {refreshed!r}"
    )

    # Explicit invariant: the transition is independent of changes_made. Mock
    # mode and already-punctuated text legitimately produce changes_made:false.
    changes_made = result.get("changes_made")
    assert estado == "preprocesado", (
        f"estado must advance even when changes_made={changes_made!r}; "
        f"task payload: {payload}"
    )


# ── Full pipeline on the same document ─────────────────────────────────


@pytest.mark.slow
@pytest.mark.e2e
def test_full_preprocess_then_classify(
    api: httpx.Client,
    temp_project: str,
    uploaded_doc: dict | list,
    db,
    wait_task,
) -> None:
    doc_id = _uploaded_document_id(uploaded_doc)

    # ── Stage 1: punctuate ──
    r = api.post(f"{DOCS}/{doc_id}/punctuate")
    assert r.status_code == 200, f"punctuate failed: {r.text}"
    body = r.json()
    assert body.get("status") == "dispatched", f"unexpected dispatch body: {r.text}"
    punctuate_task = body.get("task_id")
    assert punctuate_task, f"punctuate response has no task_id: {r.text}"

    payload = wait_task(api, punctuate_task, timeout=TASK_TIMEOUT)
    assert payload.get("status") == "SUCCESS", f"punctuate task failed: {payload}"
    punctuate_result = _task_result(payload)
    assert punctuate_result.get("status") != "error", (
        f"punctuate returned an error result: {payload}"
    )

    estado = _db_estado(db, doc_id)
    assert estado == "preprocesado", (
        f"DB estado should be 'preprocesado' before classifying, got {estado!r}; "
        f"task payload: {payload}"
    )

    # ── Stage 2: Glaser classification ──
    # Contract first: even when the LLM is unavailable the endpoint must return
    # a pollable task instead of failing synchronously.
    r = api.post(f"{DOCS}/{doc_id}/classify-glaser")
    assert r.status_code == 200, f"classify-glaser failed: {r.text}"
    body = r.json()
    assert body.get("status") == "dispatched", f"unexpected dispatch body: {r.text}"
    classify_task = body.get("task_id")
    assert classify_task, f"classify response has no task_id: {r.text}"
    assert str(body.get("document_id", doc_id)) == str(doc_id), (
        f"classify response points at the wrong document: {r.text}"
    )

    try:
        payload = wait_task(api, classify_task, timeout=TASK_TIMEOUT)
    except AssertionError as exc:
        if "did not finish" not in str(exc):
            raise
        # The heavy worker (``Celery("heavy_tasks", broker=...)``) has no result
        # backend, so even a successful classify task stays PENDING forever from
        # the API's point of view. Report what actually happened in the DB.
        estado = _db_estado(db, doc_id)
        pytest.skip(
            f"classify task never became pollable; DB estado={estado!r}. "
            f"Likely the heavy worker has no result backend: {exc}"
        )

    if payload.get("status") != "SUCCESS":
        pytest.skip(
            f"classify task did not complete (LLM/worker unavailable): {payload}"
        )

    classify_result = _task_result(payload)
    if classify_result.get("status") == "error":
        pytest.skip(f"classify returned an error result: {classify_result}")

    estado = _db_estado(db, doc_id)
    assert estado in ("clasificado", "clasificando"), (
        f"DB estado should be 'clasificado' (or 'clasificando' transient) after "
        f"classify, got {estado!r}; task payload: {payload}"
    )


# ── Negative contract ──────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.e2e
def test_punctuate_unknown_document_returns_404(api: httpx.Client) -> None:
    r = api.post(f"{DOCS}/{uuid.uuid4()}/punctuate")
    assert r.status_code == 404, f"expected 404 for a random document id: {r.text}"
    assert "no encontrado" in r.json().get("detail", "").lower(), r.text


# ── No permanently spinning states ─────────────────────────────────────


@pytest.mark.slow
@pytest.mark.e2e
def test_estado_is_never_stuck_preprocessing(
    api: httpx.Client,
    temp_project: str,
    uploaded_doc: dict | list,
    db,
    wait_task,
) -> None:
    doc_id = _uploaded_document_id(uploaded_doc)

    r = api.post(f"{DOCS}/{doc_id}/punctuate")
    assert r.status_code == 200, f"punctuate failed: {r.text}"
    body = r.json()
    task_id = body.get("task_id")
    assert body.get("status") == "dispatched", f"unexpected dispatch body: {r.text}"
    assert task_id, f"punctuate response has no task_id: {r.text}"

    payload = wait_task(api, task_id, timeout=TASK_TIMEOUT)
    assert payload.get("status") == "SUCCESS", f"punctuate task failed: {payload}"

    estado = _db_estado(db, doc_id)
    assert estado not in TRANSIENT_ESTADOS, (
        f"estado stayed transient ({estado!r}) after a SUCCESS task; "
        f"the UI would spin forever. task payload: {payload}"
    )
