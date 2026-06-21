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
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    # Menos de 1 signo de puntuación cada ~8 tokens → necesita mejora
    return ratio < (1 / 20)


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
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    meta = doc.metadatos or {}
    # Priority: classified (baseline_data tags) → preprocessed → extracted
    texto = (
        meta.get("texto_clasificado")
        or meta.get("texto_preprocesado")
        or doc.texto_extraido
    )
    if not texto:
        raise HTTPException(400, "No hay texto extraído para segmentar")

    if SEGMENTATION_MODE == "progressive":
        from app.core.celery_app import celery_app
        from celery.result import AsyncResult

        task = celery_app.send_task(
            "segmentar_documento",
            args=[texto, 1024],
            kwargs={"documento_id": str(document_id)},
            queue="nlp",
        )
        # Mark as segmenting
        doc.estado = "segmentando"
        await db.commit()
        return {"status": "dispatched", "task_id": task.id}

    # Default: spaCy (via model manager)

    # Eliminar segmentos previos
    existing = (
        (await db.execute(select(Segmento).where(Segmento.documento_id == document_id)))
        .scalars()
        .all()
    )
    for s in existing:
        await db.delete(s)

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

    await db.commit()
    return {"status": "done", "num_segmentos": len(list(doc_nlp.sents))}


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
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina todos los segmentos de un proyecto y resetea docs a crudo."""
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
    await db.execute(
        text("UPDATE documentos SET estado = 'crudo' WHERE proyecto_id = :pid"),
        {"pid": project_id},
    )
    await db.commit()
    return {"status": "ok", "message": "Segmentos eliminados, docs reseteados a crudo"}


@router.delete("/{document_id}/segments", status_code=200)
async def delete_document_segments(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina los segmentos de UN documento y lo devuelve a estado 'clasificado'."""
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM segmentos WHERE documento_id = :did"),
        {"did": document_id},
    )
    # Clear stage progress for segmenter
    await db.execute(
        text(
            "DELETE FROM document_stage_progress "
            "WHERE documento_id = :did AND agent_id = 'segmentar_documento'"
        ),
        {"did": document_id},
    )
    await db.execute(
        text("UPDATE documentos SET estado = 'clasificado' WHERE id = :did"),
        {"did": document_id},
    )
    await db.commit()
    return {"status": "ok", "message": f"Segmentos del doc {document_id} eliminados"}


@router.post("/{document_id}/restore-original", status_code=200)
async def restore_document_original(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra texto_preprocesado, warning, y resetea el doc a crudo."""
    from sqlalchemy import text

    await db.execute(
        text(
            "UPDATE documentos SET estado = 'crudo', "
            "metadatos = metadatos - 'texto_preprocesado' - 'preprocess_warning' - 'texto_puntuado' "
            "WHERE id = :did"
        ),
        {"did": document_id},
    )
    # Clear stage progress for this agent
    await db.execute(
        text(
            "DELETE FROM document_stage_progress "
            "WHERE documento_id = :did AND agent_id = 'util_punctuator'"
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
    Borra: preprocesado, clasificado, segmentos, y stage_progress."""
    from sqlalchemy import text

    # Delete FK-dependent data first
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
    """Triggers the 3-step Glaser classification for a single document.

    Dispatches task_run_glaser_classifier to the Celery 'heavy' queue.
    The task executes:
      Step 1 (PRO): XML tag classification of the full document text.
      Step 2 (FLASH): Structure validator with algorithmic fallback.
      Step 3: Baseline selection.

    With validator loop: validate -> feedback -> re-classify -> ... (max 3 rounds).
    """
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # Verify document belongs to user's project
    # (get_current_user already ensures auth; cross-project access is handled by
    #  the Celery task which validates internally)

    # Check document has text to classify
    meta = doc.metadatos or {}
    texto = meta.get("texto_preprocesado") or meta.get("texto_extraido", "")
    if not texto:
        raise HTTPException(400, "El documento no tiene texto extraído para clasificar")

    from app.core.celery_app import celery_app

    task = celery_app.send_task(
        "run_glaser_classifier",
        args=[str(document_id), str(doc.proyecto_id)],
        queue="heavy",
    )

    return {
        "status": "dispatched",
        "task_id": task.id,
        "document_id": str(document_id),
    }


@router.delete("/{document_id}/classify-glaser")
async def delete_classified_text(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra texto_clasificado, baseline_tags, y devuelve el doc a preprocesado."""
    from sqlalchemy import text

    await db.execute(
        text(
            "UPDATE documentos SET estado = 'preprocesado', "
            "metadatos = metadatos - 'texto_clasificado' - 'baseline_tags' "
            "WHERE id = :did"
        ),
        {"did": document_id},
    )
    await db.execute(
        text(
            "DELETE FROM document_stage_progress "
            "WHERE documento_id = :did AND agent_id = 'fa_glaser_data_classifier'"
        ),
        {"did": document_id},
    )
    await db.commit()
    return {"status": "ok", "message": f"Classified text cleared for doc {document_id}"}
