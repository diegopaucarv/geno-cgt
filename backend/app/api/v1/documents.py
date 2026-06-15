import uuid
from uuid import UUID

import magic
from app.core.config import ORCHESTRATION_MODE, SEGMENTATION_MODE
from app.core.minio_client import minio_client
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
        elif mime == "text/plain":
            texto_extraido = file_bytes.decode("utf-8", errors="replace")
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
            "texto_extraido": texto_extraido,
            "needs_punctuation": needs_punct,
        }
        if texto_extraido
        else {},
    )
    db.add(new_doc)
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

    texto = doc.metadatos.get("texto_extraido", "") if doc.metadatos else ""
    if not texto:
        raise HTTPException(400, "No hay texto extraído para segmentar")

    if SEGMENTATION_MODE == "progressive":
        from app.core.celery_app import celery_app
        from celery.result import AsyncResult

        task = celery_app.send_task(
            "segmentar_documento",
            args=[texto, 1024],
            queue="nlp",
        )
        return {"status": "dispatched", "task_id": task.id}

    # Default: spaCy
    import spacy

    # Eliminar segmentos previos
    existing = (
        (await db.execute(select(Segmento).where(Segmento.documento_id == document_id)))
        .scalars()
        .all()
    )
    for s in existing:
        await db.delete(s)

    nlp = spacy.load("es_core_news_lg")
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
        select(Documento).where(Documento.proyecto_id == proyecto_id)
    )
    docs = result.scalars().all()
    return [
        {
            **DocumentResponse.model_validate(doc).model_dump(),
            "texto_extraido": doc.texto_extraido,
        }
        for doc in docs
    ]


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

    texto = doc.metadatos.get("texto_extraido", "") if doc.metadatos else ""
    if not texto:
        raise HTTPException(400, "No hay texto extraído para puntuar")

    needs_punct = _needs_punctuation(texto)
    if not needs_punct:
        return {
            "status": "ok",
            "punctuation_fix": False,
            "message": "El texto ya tiene buena puntuación",
        }

    from app.core.celery_app import celery_app
    from celery.result import AsyncResult

    task = celery_app.send_task(
        "punctuate_text",
        kwargs={
            "texto": texto,
            "max_chars": 8000,
            "documento_id": str(document_id),
        },
        queue="fast",
    )

    # Esperar resultado (hasta 3 min, sin bloquear event loop)
    import asyncio

    result = AsyncResult(task.id, app=celery_app)
    try:
        output = await asyncio.to_thread(result.get, timeout=600)
    except Exception:
        return {"status": "error", "message": "Timeout o error en el procesamiento"}

    # Refrescar documento
    await db.refresh(doc)

    return {
        "status": "ok",
        "punctuation_fix": True,
        "punctuated_text": output.get("punctuated_text", texto)[:500],
        "changes_made": output.get("changes_made", False),
        "full_text": doc.texto_extraido[:500],
    }


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

    texto = doc.metadatos.get("texto_extraido", "") if doc.metadatos else ""
    if not texto:
        raise HTTPException(400, "No hay texto extraído para procesar")

    steps = (body or {}).get("steps", ["punctuate", "segment", "agents"])

    from app.core.celery_app import celery_app
    from celery.result import AsyncResult

    result: dict = {"document_id": str(document_id), "steps": {}}

    if "punctuate" in steps:
        needs = _needs_punctuation(texto)
        if needs:
            task = celery_app.send_task(
                "punctuate_text",
                kwargs={
                    "texto": texto,
                    "max_chars": 8000,
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
            args=[texto, 1024, doc.original_filename, "TEXTO", "", str(document_id)],
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
        except Exception:
            result["steps"]["agents"] = {"status": "error", "message": "Timeout"}

    # Actualizar estado del documento
    doc.estado = "listo"
    await db.commit()

    return result


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    await minio_client.delete_file(doc.storage_key)
    await db.delete(doc)
    await db.commit()
