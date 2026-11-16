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
from pathlib import Path

import httpx
import pytest

DOCS = "/api/v1/documents"

REPO = Path(__file__).resolve().parents[2]
DOCUMENTS_SOURCE = REPO / "backend" / "app" / "api" / "v1" / "documents.py"

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


def test_delete_incidents_unknown_document_is_idempotent(api: httpx.Client) -> None:
    # Mismo patrón que `classify-glaser`: SQL directo sin cargar el documento,
    # así que un id inexistente responde 200 con 0 filas borradas.
    r = api.delete(f"{DOCS}/{_uuid()}/incidents")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "ok", r.text
    assert body.get("deleted") == 0, r.text


def test_delete_incidents_requires_auth(anon_api: httpx.Client) -> None:
    r = anon_api.delete(f"{DOCS}/{_uuid()}/incidents")
    assert r.status_code in (401, 403), r.text


def test_list_incidents_unknown_document_returns_empty(api: httpx.Client) -> None:
    # Los readers por documento no validan existencia: un UUID ausente devuelve
    # el payload vacío en vez de 404.
    r = api.get(f"{DOCS}/{_uuid()}/incidents")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("incidents") == [], r.text
    assert body.get("prime_mover") is None, r.text
    assert body.get("prime_mover_confidence") is None, r.text


def test_list_incidents_requires_auth(anon_api: httpx.Client) -> None:
    r = anon_api.get(f"{DOCS}/{_uuid()}/incidents")
    assert r.status_code in (401, 403), r.text


def test_list_incidents_unknown_document_payload_keys(api: httpx.Client) -> None:
    # Contrato que consume el panel de incidentes: forma fija aunque no haya
    # filas, para que la UI no tenga que distinguir "vacío" de "otra cosa".
    resp = api.get(f"{DOCS}/{_uuid()}/incidents")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"incidents", "prime_mover", "prime_mover_confidence"}, (
        resp.text
    )


def test_segment_without_classification_is_rejected(
    api: httpx.Client, uploaded_doc: dict
) -> None:
    """Classify-first: un doc recién subido no tiene clasificación.

    El guard responde 409 antes de encolar nada, así que este test no dispara
    trabajo de Celery.
    """
    r = api.post(f"{DOCS}/{uploaded_doc['id']}/segment")
    assert r.status_code == 409, r.text
    assert "clasific" in r.json().get("detail", "").lower(), r.text


def test_delete_segments_with_keep_classification_is_accepted(
    api: httpx.Client, uploaded_doc: dict
) -> None:
    """El parámetro nuevo tiene que llegar al handler y ejecutar su SQL.

    El documento recién subido no tiene segmentos ni clasificación, así que el
    DELETE es un no-op: sirve para validar el camino ``keep_classification``
    sin tocar datos reales.
    """
    resp = api.delete(f"{DOCS}/{uploaded_doc['id']}/segments?keep_classification=true")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("status") == "ok", resp.text


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


def _handler(src: str, name: str) -> str:
    """Cuerpo de un handler, desde su ``def`` hasta el siguiente ``@router.``."""
    start = src.index(f"async def {name}(")
    rest = src[start + 1 :]
    end = rest.find("@router.")
    return rest if end == -1 else rest[:end]


def test_classify_guard_runs_before_segmentation() -> None:
    """Classify-first: la clasificación sigue al preprocesado, no a segmentar.

    Antes de la reversión el guard exigía ``segmentado``; ahora la clasificación
    es la entrada de la segmentación, así que acepta los estados previos y
    rechaza los posteriores.
    """
    body = _handler(
        DOCUMENTS_SOURCE.read_text(encoding="utf-8"), "classify_glaser_document"
    )

    assert '"crudo"' in body and '"preprocesado"' in body, (
        "the classifier must accept a document that was only loaded/preprocessed"
    )
    assert '"segmentado"' not in body, (
        "a segmented document is past classification under classify-first"
    )
    assert "La clasificación es el paso siguiente al preprocesado" in body, (
        "the 409 message must explain that classification follows preprocessing"
    )
    # El chequeo de "sin texto" sigue DESPUÉS del guard de estado.
    guard_at = body.index("not in (")
    text_at = body.index("no tiene texto extraído para clasificar")
    assert guard_at < text_at, "the no-text 400 must stay after the state guard"


def test_segment_deletion_can_keep_the_classification() -> None:
    """Los segmentos derivan del texto clasificado: borrarlos puede conservarlo.

    Bajo classify-first la clasificación no dependen de los segmentos, así que
    ``keep_classification=True`` debe conservar los metadatos, dejar el estado en
    'clasificado' y no tocar la fila de progreso del clasificador.
    """
    src = DOCUMENTS_SOURCE.read_text(encoding="utf-8")
    body = _handler(src, "delete_document_segments")

    assert "keep_classification: bool = False" in body, (
        "DELETE /{document_id}/segments must expose the keep_classification param"
    )
    keep_branch = body[body.index("if keep_classification:") : body.index("else:")]
    assert "'clasificado'" in keep_branch, (
        "keeping the classification must leave estado='clasificado'"
    )
    assert "metadatos - 'texto_clasificado'" not in keep_branch, (
        "the keep branch must not strip the classifier's metadata"
    )
    assert "agent_id = 'segmentar_documento'" in keep_branch, (
        "only the segmenter's stage-progress row becomes invalid"
    )

    # El camino por defecto conserva el comportamiento previo (borrar todo).
    default_branch = body[body.index("else:", body.index("if keep_classification:")) :]
    assert "metadatos - 'texto_clasificado'" in default_branch, (
        "the default path must keep stripping the classification"
    )

    # El endpoint de proyecto ofrece la misma opción.
    assert "keep_classification: bool = False" in _handler(
        src, "delete_all_segments"
    ), "DELETE /project/{project_id}/segments must expose keep_classification too"


def test_delete_classified_text_also_drops_segments() -> None:
    """Borrar solo la clasificación dejaría segmentos huérfanos.

    Bajo classify-first los segmentos nacen con la etiqueta del clasificador:
    si se borra la clasificación sin los segmentos, queda una categoría que
    ninguna etapa posterior vuelve a asignar.
    """
    body = _handler(
        DOCUMENTS_SOURCE.read_text(encoding="utf-8"), "delete_classified_text"
    )

    assert "DELETE FROM segmentos WHERE documento_id = :did" in body, (
        "delete_classified_text must drop the segments that derived from it"
    )
    assert "DELETE FROM extracted_incidents WHERE documento_id = :did" in body, (
        "incidents extracted from those segments become orphans"
    )
    assert "DELETE FROM codigos_segmento" in body, (
        "codes hang off the segments, so they go with them"
    )
    assert "'preprocesado'" in body and "'crudo'" in body, (
        "the estado must fall back to preprocesado/crudo, never to segmentado"
    )


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
