import asyncio
import logging
import uuid
from uuid import UUID

import magic
from app.core.config import ORCHESTRATION_MODE, SEGMENTATION_MODE
from app.core.minio_client import minio_client
from app.core.nlp_models import get_current_spacy
from app.db.database import get_db
from app.models.domain.document import Documento
from app.models.domain.segment import Segmento
from app.models.domain.user import Usuario
from app.schemas import DocumentResponse
from app.services.auth import get_current_user
from app.services.incident_curation import build_incidents_payload
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_MIME_TYPES = [
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _needs_punctuation(text: str, max_sample: int = 2000) -> bool:
    """Heurística sin LLM: caracteres extraños + ratio de puntuación.

    Detecta texto que necesita mejora de formato si:
    - Tiene caracteres no imprimibles o artefactos de encoding
    - El ratio de signos de puntuación por token es demasiado bajo
      (menos de 1 signo cada ~15 tokens)
    """
    import re

    sample = text[:max_sample]
    if len(sample) < 50:
        return False

    # ── Caracteres extraños: non-printable, null bytes, BOM ────
    weird = re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]", sample)
    if len(weird) > 0:
        return True

    # ── Ratio de puntuación ────────────────────────────────────
    punct_marks = re.findall(r"[.!?]", sample)
    tokens = sample.split()
    if len(tokens) < 10:
        return False

    ratio = len(punct_marks) / max(len(tokens), 1)
    # Menos de 1 signo de puntuación cada ~8 tokens → necesita mejorar
    return ratio < (1 / 20)


# ═══════════════════════════════════════════════════════════════════
# Estados transitorios con guarda optimista
# ═══════════════════════════════════════════════════════════════════


async def _claim_transient_estado(
    db: AsyncSession, document_id: UUID, trans: str, expected: str
) -> bool:
    """Escribe un estado transitorio sólo si el doc sigue en ``expected``.

    El API marca el documento "en curso" justo antes (o después) de despachar
    la tarea. Si el worker terminó antes y ya lo avanzó —o el usuario re-disparó
    el paso—, una asignación a ciegas pisaría el estado nuevo y el documento
    quedaría clavado en el transitorio. Devuelve False cuando nadie escribió.
    """
    result = await db.execute(
        text(
            "UPDATE documentos SET estado = :trans "
            "WHERE id = :did AND TRIM(estado) = :expected"
        ),
        {"trans": trans, "did": document_id, "expected": expected},
    )
    await db.commit()
    return result.rowcount > 0


async def _revert_transient(
    db: AsyncSession, document_id: UUID, trans: str, prev: str
) -> None:
    """Devuelve el doc a ``prev`` si sigue en el transitorio ``trans``.

    Se usa cuando el despacho falla: sin tarea pendiente, nadie sacaría al
    documento del estado transitorio.
    """
    await db.execute(
        text(
            "UPDATE documentos SET estado = :prev "
            "WHERE id = :did AND TRIM(estado) = :trans"
        ),
        {"prev": prev, "did": document_id, "trans": trans},
    )
    await db.commit()


async def _read_estado(db: AsyncSession, document_id: UUID) -> str | None:
    """Estado actual del documento (None si ya no existe)."""
    return (
        await db.execute(
            text("SELECT estado FROM documentos WHERE id = :did"),
            {"did": document_id},
        )
    ).scalar_one_or_none()


@router.post("/upload/{project_id}")
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Validar tipo MIME
    content = await file.read(1024)
    await file.seek(0)
    mime = magic.from_buffer(content, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Tipo de archivo no permitido: {mime}")

    # 2. Validar tamaño
    file_size = 0
    chunk = await file.read(8192)
    while chunk:
        file_size += len(chunk)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(413, "Archivo demasiado grande")
        chunk = await file.read(8192)
    await file.seek(0)

    # 3. Generar storage_key única
    storage_key = f"projects/{project_id}/{current_user.id}_{uuid.uuid4().hex[:8]}_{file.filename}"

    # 4. Subir a MinIO
    await minio_client.upload_file(file, storage_key, content_type=mime)

    # 5. Extraer texto
    texto_extraido = ""
    try:
        await file.seek(0)
        file_bytes = await file.read()
        if mime == "application/pdf":
            import fitz  # PyMuPDF

            doc_pdf = fitz.open(stream=file_bytes, filetype="pdf")
            texto_extraido = "\n".join(page.get_text() for page in doc_pdf)
            doc_pdf.close()
            # Detectar si el texto extraído tiene problemas de encoding
            if "\ufffd" in texto_extraido:
                # Intentar pasar a Latin-1 y volver a UTF-8
                try:
                    fixed = texto_extraido.encode("latin-1", errors="replace").decode(
                        "utf-8", errors="replace"
                    )
                    if fixed.count("\ufffd") < texto_extraido.count("\ufffd"):
                        texto_extraido = fixed
                except Exception:
                    pass
        elif mime == "text/plain":
            # Detectar encoding: probar UTF-8, si tiene U+FFFD → Latin-1
            texto_utf8 = file_bytes.decode("utf-8", errors="replace")
            if "\ufffd" in texto_utf8:
                texto_latin1 = file_bytes.decode("latin-1", errors="replace")
                # Usar el que tenga menos caracteres de reemplazo
                if texto_latin1.count("\ufffd") < texto_utf8.count("\ufffd"):
                    texto_extraido = texto_latin1
                else:
                    texto_extraido = texto_utf8
            else:
                texto_extraido = texto_utf8
        elif "wordprocessingml" in mime:
            from io import BytesIO

            import docx

            doc_docx = docx.Document(BytesIO(file_bytes))
            texto_extraido = "\n".join(p.text for p in doc_docx.paragraphs)
    except Exception as e:
        print(f"[Upload] Error extrayendo texto: {e}")

    # 5.5 Opcional: mejorar puntuación si el texto lo necesita
    # Se dispara después de guardar para tener el doc_id
    needs_punct = texto_extraido and _needs_punctuation(texto_extraido)

    # 6. Guardar metadatos en DB
    new_doc = Documento(
        proyecto_id=project_id,
        original_filename=file.filename,
        storage_key=storage_key,
        mime_type=mime,
        size_bytes=file_size,
        tipo_de_fuente="TEXTO",
        estado="crudo",
        metadatos={
            "texto_original": texto_extraido,
            "texto_extraido": texto_extraido,
            "needs_punctuation": needs_punct,
        }
        if texto_extraido
        else {},
    )
    db.add(new_doc)
    await db.flush()
    # Set initial sort_order
    from sqlalchemy import text as sa_text

    await db.execute(
        sa_text(
            "UPDATE documentos SET sort_order = (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM documentos WHERE proyecto_id = :pid) WHERE id = :did"
        ),
        {"pid": project_id, "did": new_doc.id},
    )
    await db.commit()
    await db.refresh(new_doc)

    # El pipeline NO se dispara automáticamente.
    # El usuario decide qué pasos ejecutar desde la UI.

    return {
        "id": new_doc.id,
        "storage_key": storage_key,
        "filename": file.filename,
        "estado": "crudo",
        "needs_punctuation": needs_punct,
    }


@router.get("/download/{document_id}")
async def download_document(
    document_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    file_bytes = await minio_client.download_file(doc.storage_key)
    headers = {"Content-Disposition": f'attachment; filename="{doc.original_filename}"'}
    return Response(content=file_bytes, media_type=doc.mime_type, headers=headers)


@router.get("/presigned/{document_id}")
async def get_presigned_url(
    document_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve una URL temporal para descarga directa desde MinIO"""
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    url = await minio_client.generate_presigned_url(doc.storage_key, expiration=600)
    return {"url": url}


@router.post("/{document_id}/segment")
async def segment_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """(Re)segmenta el documento desde su texto plano ya clasificado.

    Orden del pipeline: preprocesado → clasificando → clasificado →
    segmentando → segmentado. Segmentar NO toca la clasificación: los
    segmentos heredan la etiqueta del texto clasificado, así que la decisión
    del clasificador sobrevive a una re-segmentación.
    Precedencia del despacho: modo ``spacy`` local > worker-nlp
    (``segmentar_documento``) > segmentador LLM (``segmentar_documento_llm``
    en la cola heavy).
    """
    from app.agents.transitions import segmenters_available

    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    meta = doc.metadatos or {}
    # Re-segmentar parte siempre del texto plano: el XML clasificado deriva de
    # los segmentos y no es una fuente de entrada válida.
    texto = meta.get("texto_preprocesado") or doc.texto_extraido
    if not texto:
        raise HTTPException(400, "No hay texto extraído para segmentar")

    # Classify-first: el clasificador etiqueta el texto y sólo después se
    # segmenta. Sin esa etiqueta los segmentos nacerían sin categoría y ninguna
    # etapa posterior los volvería a clasificar.
    if not (meta.get("glaser_blocks") or meta.get("texto_clasificado")):
        raise HTTPException(409, "Clasificá el texto antes de segmentar.")

    # El broadcast de Celery bloquea: fuera del event loop.
    have_segmenters = await asyncio.to_thread(segmenters_available)

    # Precedencia real del despacho. ``SEGMENTATION_MODE`` NO puede decidirla:
    # vale "progressive" por defecto, y entonces se mandaba
    # ``segmentar_documento`` a la cola 'nlp' aunque no hubiera worker
    # escuchando —la tarea nunca corría y el doc quedaba en 'segmentando'.
    use_spacy = SEGMENTATION_MODE == "spacy"

    # Estado transitorio con guarda optimista: si el documento avanzó mientras
    # se resolvía el modo, no se pisa su estado ni se reemplazan sus segmentos.
    expected = (doc.estado or "").strip()
    if not await _claim_transient_estado(db, document_id, "segmentando", expected):
        estado = await _read_estado(db, document_id)
        logger.warning(
            "segment_document: doc=%s pasó de '%s' a '%s'; no se segmenta",
            document_id,
            expected,
            estado,
        )
        return {
            "status": "skipped",
            "reason": "El documento cambió de estado mientras se lanzaba la segmentación",
            "estado": estado,
        }

    if have_segmenters and not use_spacy:
        from app.core.celery_app import celery_app

        try:
            task = celery_app.send_task(
                "segmentar_documento",
                args=[texto, 1024],
                kwargs={"documento_id": str(document_id)},
                queue="nlp",
            )
        except Exception:
            await _revert_transient(db, document_id, "segmentando", expected)
            raise
        return {"status": "dispatched", "task_id": task.id}

    # Rutas local/LLM: los segmentos previos se borran siempre, incluso si el
    # segmentador va a re-segmentar, o quedarían segmentos obsoletos en la
    # tabla. FK hijas primero (mismo orden que restore_document_original).
    await db.execute(
        text(
            "DELETE FROM extracted_incidents WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("DELETE FROM segmentos WHERE documento_id = :did"),
        {"did": document_id},
    )

    if use_spacy:
        # Escape hatch explícito del operador: segmentación local con spaCy,
        # sin workers ni LLM. Sólo se alcanza con ese modo configurado.
        nlp = get_current_spacy()
        doc_nlp = nlp(texto)

        for i, sent in enumerate(doc_nlp.sents):
            segmento = Segmento(
                documento_id=document_id,
                texto=sent.text.strip(),
                posicion=i + 1,
                conteo_tokens=len(sent.text.split()),
            )
            db.add(segmento)

        # El estado debe avanzar o la UI no ofrece el paso "Extraer".
        await db.execute(
            text(
                "UPDATE documentos SET estado = 'segmentado' "
                "WHERE id = :did AND TRIM(estado) = 'segmentando'"
            ),
            {"did": document_id},
        )
        await db.commit()
        return {
            "status": "done",
            "num_segmentos": len(doc_nlp.sents),
            "estado": "segmentado",
        }

    # Fallback: segmentador LLM dedicado, que recibe el documento (no el texto)
    # y conserva la clasificación ya persistida.
    from app.core.celery_app import celery_app

    try:
        task = celery_app.send_task(
            "segmentar_documento_llm",
            args=[str(document_id), str(doc.proyecto_id)],
            queue="heavy",
        )
    except Exception:
        await _revert_transient(db, document_id, "segmentando", expected)
        raise
    return {"status": "dispatched", "task_id": task.id, "used_fallback": True}


@router.get("")
async def list_documents(
    proyecto_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Documento)
        .where(Documento.proyecto_id == proyecto_id)
        .order_by(Documento.sort_order)
    )
    docs = result.scalars().all()
    print(f"[list_documents] Found {len(docs)} documents for project {proyecto_id}")
    response = []
    for doc in docs:
        try:
            item = {
                **DocumentResponse.model_validate(doc).model_dump(),
                "texto_extraido": doc.texto_extraido,
                "texto_preprocesado": (doc.metadatos or {}).get(
                    "texto_preprocesado", ""
                ),
                "texto_original": (doc.metadatos or {}).get("texto_original", ""),
                "texto_clasificado": (doc.metadatos or {}).get("texto_clasificado", ""),
                "glaser_blocks": (doc.metadatos or {}).get("glaser_blocks", []),
                "glaser_used_fallback": (doc.metadatos or {}).get(
                    "glaser_used_fallback", False
                ),
                "preprocess_warning": (doc.metadatos or {}).get(
                    "preprocess_warning", ""
                ),
            }
            response.append(item)
        except Exception as e:
            print(f"[list_documents] ERROR validating doc {doc.id}: {e}")
    print(f"[list_documents] Returning {len(response)} documents")
    return response


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    from app.core.celery_app import celery_app
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }


@router.post("/{document_id}/segments-from-task", status_code=201)
async def save_task_segments(
    document_id: UUID,
    task_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from app.core.celery_app import celery_app
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)
    if not result.ready():
        raise HTTPException(400, "La tarea aún no ha terminado")

    task_data = result.result
    segmentos_texto = task_data.get("segmentos", [])

    # Limpiar previos
    existing = (
        (await db.execute(select(Segmento).where(Segmento.documento_id == document_id)))
        .scalars()
        .all()
    )
    for s in existing:
        await db.delete(s)

    for i, texto_seg in enumerate(segmentos_texto):
        segmento = Segmento(
            documento_id=document_id,
            texto=texto_seg,
            posicion=i + 1,
            conteo_tokens=len(texto_seg.split()),
        )
        db.add(segmento)

    await db.commit()
    return {"num_segmentos": len(segmentos_texto)}


@router.post("/{document_id}/punctuate")
async def punctuate_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Mejora la puntuación del texto extraído usando LLM (FLASH)."""
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    texto = doc.texto_extraido  # uses model property (falls back to texto_original)
    if not texto:
        raise HTTPException(400, "No hay texto extraído para puntuar")

    # Always dispatch to worker — it handles both "changed" and "no changes" consistently
    from app.core.celery_app import celery_app

    task = celery_app.send_task(
        "punctuate_text",
        kwargs={
            "texto": texto,
            "max_chars": 10000,
            "documento_id": str(document_id),
            # All documents of the same project share one replica, which is
            # what makes the cached instruction+schema prefix reusable.
            "cache_key": str(doc.proyecto_id),
        },
        queue="fast",
    )

    return {"status": "dispatched", "task_id": task.id}


@router.post("/{document_id}/process")
async def process_document(
    document_id: UUID,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Ejecuta pasos de procesamiento seleccionados por el usuario.

    Body: {"steps": ["punctuate", "segment", "agents"]}
    Si no se especifica, ejecuta todos.
    """
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    meta = doc.metadatos or {}
    texto_extraido_raw = doc.texto_extraido
    texto_best = meta.get("texto_preprocesado") or texto_extraido_raw
    if not texto_extraido_raw:
        raise HTTPException(400, "No hay texto extraído para procesar")

    steps = (body or {}).get("steps", ["punctuate", "segment", "agents"])

    from app.core.celery_app import celery_app
    from celery.result import AsyncResult

    result: dict = {"document_id": str(document_id), "steps": {}}

    if "punctuate" in steps:
        needs = _needs_punctuation(texto_extraido_raw)
        if needs:
            task = celery_app.send_task(
                "punctuate_text",
                kwargs={
                    "texto": texto_extraido_raw,
                    "max_chars": 10000,
                    "documento_id": str(document_id),
                    "cache_key": str(doc.proyecto_id),
                },
                queue="fast",
            )
            result["steps"]["punctuate"] = {"task_id": task.id, "status": "dispatched"}
        else:
            result["steps"]["punctuate"] = {
                "status": "skipped",
                "reason": "puntuación OK",
            }

    if "segment" in steps:
        task = celery_app.send_task(
            "segmentar_documento",
            args=[
                texto_best,
                1024,
                doc.original_filename,
                "TEXTO",
                "",
                str(document_id),
            ],
            queue="nlp",
        )
        result["steps"]["segment"] = {"task_id": task.id, "status": "dispatched"}

    if "agents" in steps:
        task = celery_app.send_task(
            "process_document_agents_a",
            args=[str(document_id), str(doc.proyecto_id)],
            queue="heavy",
        )
        import asyncio

        async_result = AsyncResult(task.id, app=celery_app)
        try:
            output = await asyncio.to_thread(async_result.get, timeout=600)
            result["steps"]["agents"] = {"status": "done", "result": output}
            # Solo marcar como listo si los agentes terminaron bien
            doc.estado = "listo"
        except Exception:
            result["steps"]["agents"] = {"status": "error", "message": "Timeout"}
            # Si fallaron los agentes pero la segmentación sí corrió, marcar segmentado
            if "segment" in steps:
                doc.estado = "segmentado"
    elif "segment" in steps:
        # Solo segmentación, sin agentes
        doc.estado = "segmentado"

    await db.commit()

    return result


@router.post("/{document_id}/undo-punctuate")
async def undo_punctuate(
    document_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Restaura el texto original antes de la puntuación."""
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    original = body.get("original_text", "")
    if not original:
        raise HTTPException(400, "Se requiere original_text")

    meta = doc.metadatos or {}
    if isinstance(meta, str):
        import json as _json

        meta = _json.loads(meta)
    # texto_extraido ya no se sobreescribe; solo eliminamos el preprocesado
    meta.pop("texto_preprocesado", None)
    meta["texto_puntuado"] = False
    doc.metadatos = meta
    await db.commit()
    return {"status": "restored"}


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina un documento y sus referencias."""
    from sqlalchemy import text

    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # Borrar dependencias primero (pipeline_tasks, segments, etc.)
    await db.execute(
        text(
            "DELETE FROM task_step_checkpoints WHERE pipeline_task_id IN (SELECT id FROM pipeline_tasks WHERE document_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("DELETE FROM pipeline_tasks WHERE document_id = :did"),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM extracted_incidents WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("DELETE FROM segmentos WHERE documento_id = :did"),
        {"did": document_id},
    )
    await minio_client.delete_file(doc.storage_key)
    await db.delete(doc)
    await db.commit()


@router.delete("/project/{project_id}/segments", status_code=200)
async def delete_all_segments(
    project_id: UUID,
    keep_classification: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina todos los segmentos de un proyecto y resetea sus docs.

    Con ``keep_classification=True`` la clasificación de cada documento
    sobrevive (los docs vuelven a 'clasificado' y solo se invalida el progreso
    del segmentador), que es la regla classify-first: los segmentos son una
    derivación del texto ya etiquetado.
    """
    from sqlalchemy import text

    await db.execute(
        text(
            "DELETE FROM extracted_incidents WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid))"
        ),
        {"pid": project_id},
    )
    await db.execute(
        text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid))"
        ),
        {"pid": project_id},
    )
    await db.execute(
        text(
            "DELETE FROM segmentos WHERE documento_id IN (SELECT id FROM documentos WHERE proyecto_id = :pid)"
        ),
        {"pid": project_id},
    )

    if keep_classification:
        await db.execute(
            text(
                "DELETE FROM document_stage_progress "
                "WHERE documento_id IN (SELECT id FROM documentos WHERE proyecto_id = :pid) "
                "AND agent_id = 'segmentar_documento'"
            ),
            {"pid": project_id},
        )
        await db.execute(
            text(
                "UPDATE documentos SET estado = CASE "
                " WHEN metadatos ? 'glaser_blocks' "
                "  OR metadatos ? 'texto_clasificado' THEN 'clasificado' "
                " WHEN metadatos ? 'texto_preprocesado' THEN 'preprocesado' "
                " ELSE 'crudo' END "
                "WHERE proyecto_id = :pid"
            ),
            {"pid": project_id},
        )
        await db.commit()
        return {
            "status": "ok",
            "message": "Segmentos eliminados, docs reseteados a clasificado",
        }

    await db.execute(
        text(
            "UPDATE documentos SET estado = CASE "
            " WHEN metadatos ? 'texto_preprocesado' THEN 'preprocesado' "
            " ELSE 'crudo' END, "
            "metadatos = metadatos - 'texto_clasificado' - 'baseline_tags' "
            "- 'glaser_blocks' - 'glaser_used_fallback' "
            "WHERE proyecto_id = :pid"
        ),
        {"pid": project_id},
    )
    # Clear stage progress for segmenter y clasificador
    await db.execute(
        text(
            "DELETE FROM document_stage_progress "
            "WHERE documento_id IN (SELECT id FROM documentos WHERE proyecto_id = :pid) "
            "AND agent_id IN ('segmentar_documento', 'fa_glaser_data_classifier')"
        ),
        {"pid": project_id},
    )
    await db.commit()
    return {
        "status": "ok",
        "message": "Segmentos eliminados, docs reseteados a preprocesado/crudo",
    }


@router.delete("/{document_id}/segments", status_code=200)
async def delete_document_segments(
    document_id: UUID,
    keep_classification: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina los segmentos de UN documento.

    Por defecto también limpia su clasificación: bajo la escalera clásica un
    documento sin segmentos no podía estar clasificado, así que el estado vuelve
    a 'preprocesado' (o 'crudo' si tampoco hay texto preprocesado) y se borran
    los metadatos derivados del clasificador.

    ``keep_classification=True`` conserva la clasificación: la escalera es
    classify-first, los segmentos son una derivación del texto etiquetado, y
    volver a segmentar no obliga a volver a clasificar. En ese caso el estado
    vuelve a 'clasificado' y solo se limpia el progreso del segmentador.
    """
    from sqlalchemy import text

    # FK hijas primero (mismo orden que restore_document_original).
    await db.execute(
        text(
            "DELETE FROM extracted_incidents WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("DELETE FROM segmentos WHERE documento_id = :did"),
        {"did": document_id},
    )
    # El prime mover se extrae de los segmentos: sin segmentos queda huérfano y
    # la vista de incidentes mostraría un proceso viejo.
    await db.execute(
        text("DELETE FROM document_processes WHERE documento_id = :did"),
        {"did": document_id},
    )

    if keep_classification:
        # Solo se invalida la etapa de segmentación; el clasificador conservó su
        # resultado y su fila de progreso sigue siendo válida.
        await db.execute(
            text(
                "DELETE FROM document_stage_progress "
                "WHERE documento_id = :did AND agent_id = 'segmentar_documento'"
            ),
            {"did": document_id},
        )
        await db.execute(
            text(
                "UPDATE documentos SET estado = CASE "
                " WHEN metadatos ? 'glaser_blocks' "
                "  OR metadatos ? 'texto_clasificado' THEN 'clasificado' "
                " WHEN metadatos ? 'texto_preprocesado' THEN 'preprocesado' "
                " ELSE 'crudo' END "
                "WHERE id = :did"
            ),
            {"did": document_id},
        )
    else:
        # Clear stage progress for segmenter y clasificador
        await db.execute(
            text(
                "DELETE FROM document_stage_progress "
                "WHERE documento_id = :did AND agent_id IN "
                "('segmentar_documento', 'fa_glaser_data_classifier')"
            ),
            {"did": document_id},
        )
        await db.execute(
            text(
                "UPDATE documentos SET estado = CASE "
                " WHEN metadatos ? 'texto_preprocesado' THEN 'preprocesado' "
                " ELSE 'crudo' END, "
                "metadatos = metadatos - 'texto_clasificado' - 'baseline_tags' "
                "- 'glaser_blocks' - 'glaser_used_fallback' "
                "WHERE id = :did"
            ),
            {"did": document_id},
        )
    await db.commit()
    return {"status": "ok", "message": f"Segmentos del doc {document_id} eliminados"}


@router.get("/{document_id}/incidents")
async def list_document_incidents(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Incidentes extraídos de un documento y el prime mover asociado.

    La forma del payload la define :func:`build_incidents_payload`, compartida con
    los endpoints de curación (``/api/v1/incidents/...``), para que la UI reciba
    siempre la misma representación. Claves de nivel superior: ``incidents``,
    ``prime_mover`` y ``prime_mover_confidence`` — no agregar más.
    """
    return await build_incidents_payload(db, document_id)


@router.delete("/{document_id}/incidents", status_code=200)
async def delete_document_incidents(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra los incidentes extraídos del documento y vuelve a 'segmentado'.

    ``incident_comparisons`` referencia ``extracted_incidents`` con dos FK
    NO ACTION (``incident_a_id``/``incident_b_id``): si no se borran primero,
    el DELETE de incidentes falla. ``incident_groups.incident_ids_json`` es
    JSONB débil y sin FK, así que conserva ids obsoletos; la Fase B regenera
    los grupos al volver a extraer.
    """
    from sqlalchemy import text

    await db.execute(
        text(
            "DELETE FROM incident_comparisons "
            "WHERE incident_a_id IN "
            "(SELECT id FROM extracted_incidents WHERE documento_id = :did) "
            "OR incident_b_id IN "
            "(SELECT id FROM extracted_incidents WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    deleted = await db.execute(
        text("DELETE FROM extracted_incidents WHERE documento_id = :did"),
        {"did": document_id},
    )
    # El prime mover es una salida de la extracción: si sobrevive, la vista de
    # incidentes sigue mostrando el proceso de la corrida anterior.
    await db.execute(
        text("DELETE FROM document_processes WHERE documento_id = :did"),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM document_stage_progress WHERE documento_id = :did "
            "AND agent_id = 'fa_document_pattern_extractor'"
        ),
        {"did": document_id},
    )
    # Solo retroceden los estados que implicaban incidentes extraídos; un doc
    # en 'segmentado' ya está en la etapa correcta.
    await db.execute(
        text(
            "UPDATE documentos SET estado = 'segmentado' "
            "WHERE id = :did AND TRIM(estado) IN "
            "('incidentes_extraidos', 'procesado', 'codificado', 'listo')"
        ),
        {"did": document_id},
    )
    await db.commit()
    return {"status": "ok", "deleted": deleted.rowcount}


@router.post("/{document_id}/restore-original", status_code=200)
async def restore_document_original(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra texto_preprocesado, warning, segmentos y clasificación, y deja el
    doc en crudo."""
    from sqlalchemy import text

    await db.execute(
        text(
            "UPDATE documentos SET estado = 'crudo', "
            "metadatos = metadatos - 'texto_preprocesado' - 'preprocess_warning' - 'texto_puntuado' "
            "- 'texto_clasificado' - 'baseline_tags' - 'glaser_blocks' - 'glaser_used_fallback' "
            "WHERE id = :did"
        ),
        {"did": document_id},
    )
    # Clear stage progress for this agent and the downstream stages
    await db.execute(
        text(
            "DELETE FROM document_stage_progress "
            "WHERE documento_id = :did AND agent_id IN "
            "('util_punctuator', 'segmentar_documento', 'fa_glaser_data_classifier')"
        ),
        {"did": document_id},
    )
    # Also delete segments so the doc really goes back to raw
    # Delete FK dependencies first
    await db.execute(
        text(
            "DELETE FROM extracted_incidents WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("DELETE FROM segmentos WHERE documento_id = :did"),
        {"did": document_id},
    )
    await db.commit()
    return {"status": "ok", "message": f"Doc {document_id} restored to original"}


@router.post("/project/{project_id}/reset-to-crudo", status_code=200)
async def reset_all_docs_to_crudo(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Resetea TODOS los docs del proyecto a 'crudo'.
    Borra: preprocesado, clasificado, segmentos, incidentes y stage_progress."""
    from sqlalchemy import text

    # Delete FK-dependent data first. Las comparaciones van antes de los
    # incidentes: sus dos FK son NO ACTION y sin esto el DELETE falla.
    await db.execute(
        text(
            "DELETE FROM incident_comparisons "
            "WHERE incident_a_id IN "
            "(SELECT id FROM extracted_incidents WHERE proyecto_id = :pid) "
            "OR incident_b_id IN "
            "(SELECT id FROM extracted_incidents WHERE proyecto_id = :pid)"
        ),
        {"pid": project_id},
    )
    await db.execute(
        text(
            "DELETE FROM extracted_incidents WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid))"
        ),
        {"pid": project_id},
    )
    await db.execute(
        text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid))"
        ),
        {"pid": project_id},
    )
    await db.execute(
        text(
            "DELETE FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid)"
        ),
        {"pid": project_id},
    )
    # Clear all stage progress for project
    await db.execute(
        text(
            "DELETE FROM document_stage_progress WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid)"
        ),
        {"pid": project_id},
    )
    # Reset all docs: estado=crudo, strip all processing keys from metadatos
    result = await db.execute(
        text(
            "UPDATE documentos SET estado = 'crudo', "
            "metadatos = metadatos - 'texto_preprocesado' - 'preprocess_warning' "
            "- 'texto_puntuado' - 'texto_clasificado' - 'baseline_tags' "
            "- 'glaser_blocks' - 'glaser_used_fallback' "
            "WHERE proyecto_id = :pid"
        ),
        {"pid": project_id},
    )
    await db.commit()
    return {
        "status": "ok",
        "message": f"{result.rowcount} documentos reseteados a crudo",
    }


@router.post("/project/{project_id}/reorder", status_code=200)
async def reorder_documents(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Reordena documentos. Body: {"order": [{"id": "...", "sort_order": 1.0}, ...]}"""
    from sqlalchemy import text

    items = body.get("order", [])
    if not items:
        raise HTTPException(400, "Se requiere order[] con {id, sort_order}")

    for item in items:
        await db.execute(
            text("UPDATE documentos SET sort_order = :so WHERE id = :did"),
            {"so": item["sort_order"], "did": item["id"]},
        )
    await db.commit()
    return {"status": "ok", "count": len(items)}


@router.post("/{document_id}/classify-glaser")
async def classify_glaser_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Dispara el clasificador Glaser sobre el texto plano del documento.

    La clasificación es el paso que sigue al preprocesado: el clasificador
    etiqueta el texto en las 5 categorías canónicas y persiste
    ``glaser_blocks``/``texto_clasificado``/``baseline_tags`` en
    ``documentos.metadatos``. Los segmentos se crean DESPUÉS (etapa
    ``segmentar_documento``) heredando la etiqueta, así que aquí no hace falta
    tener segmentos. Despacha ``run_glaser_classifier`` a la cola 'heavy'.
    """
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # Verify document belongs to user's project
    # (get_current_user already ensures auth; cross-project access is handled by
    #  the Celery task which validates internally)

    # La clasificación es el paso posterior a la extracción/carga del texto, no
    # el posterior a la segmentación: solo se rechaza cuando el documento ya
    # avanzó más allá (segmentado y compañía) o no tiene texto que clasificar.
    if (doc.estado or "").strip() not in (
        "crudo",
        "preprocesado",
        "clasificado",
        "error",
    ):
        raise HTTPException(
            409,
            f"Documento en estado '{doc.estado}'. "
            "La clasificación es el paso siguiente al preprocesado; "
            "revertí el documento a preprocesado antes de clasificar.",
        )

    # Check document has text to classify (texto plano: la clasificación aún no
    # existe, así que no hay texto_clasificado que leer).
    meta = doc.metadatos or {}
    texto = meta.get("texto_preprocesado") or doc.texto_extraido
    if not texto:
        raise HTTPException(400, "El documento no tiene texto extraído para clasificar")

    from app.core.celery_app import celery_app

    # El worker escribe 'clasificado' él mismo, así que el transitorio se marca
    # ANTES de despachar (con guarda): si el documento cambió de estado, no se
    # lanza una clasificación obsoleta ni se pisa el estado nuevo.
    expected = (doc.estado or "").strip()
    if not await _claim_transient_estado(db, document_id, "clasificando", expected):
        estado = await _read_estado(db, document_id)
        logger.warning(
            "classify_glaser_document: doc=%s pasó de '%s' a '%s'; no se clasifica",
            document_id,
            expected,
            estado,
        )
        return {
            "status": "skipped",
            "reason": "El documento cambió de estado mientras se lanzaba la clasificación",
            "document_id": str(document_id),
            "estado": estado,
        }

    try:
        task = celery_app.send_task(
            "run_glaser_classifier",
            args=[str(document_id), str(doc.proyecto_id)],
            queue="heavy",
        )
    except Exception:
        await _revert_transient(db, document_id, "clasificando", expected)
        raise

    return {
        "status": "dispatched",
        "task_id": task.id,
        "document_id": str(document_id),
        "estado": "clasificando",
    }


@router.delete("/{document_id}/classify-glaser")
async def delete_classified_text(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra la clasificación Glaser junto con todo lo que deriva de ella.

    Bajo la escalera classify-first la clasificación precede a la segmentación:
    cada segmento nace con la etiqueta que el clasificador le dio al texto.
    Borrar sólo los metadatos dejaría segmentos con categorías que ya no
    existen en el documento y que ninguna etapa posterior volvería a etiquetar,
    así que se borran juntos los segmentos, sus códigos y los incidentes que
    salieron de ellos. El estado vuelve a 'preprocesado' —o 'crudo' si el texto
    tampoco está preprocesado—, nunca a 'segmentado': ya no quedan segmentos.
    """
    from sqlalchemy import text

    # FK hijas primero: las comparaciones referencian incidentes con dos FK
    # NO ACTION y los incidentes a los segmentos, que también se borran.
    await db.execute(
        text(
            "DELETE FROM incident_comparisons "
            "WHERE incident_a_id IN "
            "(SELECT id FROM extracted_incidents WHERE documento_id = :did) "
            "OR incident_b_id IN "
            "(SELECT id FROM extracted_incidents WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("DELETE FROM extracted_incidents WHERE documento_id = :did"),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id = :did)"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("DELETE FROM segmentos WHERE documento_id = :did"),
        {"did": document_id},
    )
    await db.execute(
        text(
            "UPDATE documentos SET estado = CASE "
            " WHEN metadatos ? 'texto_preprocesado' THEN 'preprocesado' "
            " ELSE 'crudo' END, "
            "metadatos = metadatos - 'texto_clasificado' - 'baseline_tags' "
            "- 'glaser_blocks' - 'glaser_used_fallback' "
            "WHERE id = :did"
        ),
        {"did": document_id},
    )
    # El clasificador, el segmentador y el extractor leyeron datos que ya no
    # existen: sus filas de progreso dejan de ser válidas.
    await db.execute(
        text(
            "DELETE FROM document_stage_progress "
            "WHERE documento_id = :did AND agent_id IN "
            "('fa_glaser_data_classifier', 'segmentar_documento', "
            "'fa_document_pattern_extractor')"
        ),
        {"did": document_id},
    )
    await db.commit()
    return {"status": "ok", "message": f"Classified text cleared for doc {document_id}"}
