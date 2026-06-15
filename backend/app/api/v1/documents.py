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


def _needs_punctuation(text: str) -> bool:
    """Heurística: +60% de oraciones empiezan con minúscula → necesita puntuación."""
    import re

    sentences = re.split(r"[.!?]+", text)
    if len(sentences) < 3:
        return False
    lower_starts = sum(1 for s in sentences if s.strip() and s.strip()[0].islower())
    return lower_starts / max(len(sentences), 1) > 0.6


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
    if texto_extraido and _needs_punctuation(texto_extraido):
        from app.core.celery_app import celery_app

        celery_app.send_task(
            "punctuate_text",
            args=[texto_extraido[:50000], 3000, str(new_doc.id)],
            queue="fast",
        )

    # 6. Guardar metadatos en DB (texto_extraido en metadatos)
    new_doc = Documento(
        proyecto_id=project_id,
        original_filename=file.filename,
        storage_key=storage_key,
        mime_type=mime,
        size_bytes=file_size,
        tipo_de_fuente="TEXTO",
        estado="crudo",
        metadatos={"texto_extraido": texto_extraido[:10000]} if texto_extraido else {},
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    # 7. Disparar pipeline CGT asíncrono
    from app.core.celery_app import celery_app

    # Paso 0: segmentar en worker-nlp (tiene spaCy)
    celery_app.send_task(
        "segmentar_documento",
        args=[
            texto_extraido[:50000],
            1024,
            file.filename,
            "TEXTO",
            "",
            str(new_doc.id),
        ],
        queue="nlp",
    )

    # Paso 1: pipeline de agentes en worker-heavy
    if ORCHESTRATION_MODE == "graph":
        task = celery_app.send_task(
            "invoke_graph",
            args=[str(project_id), str(new_doc.id)],
            queue="heavy",
        )
    else:
        task = celery_app.send_task(
            "process_document_agents_a",
            args=[str(new_doc.id), str(project_id)],
            queue="heavy",
        )

    return {
        "id": new_doc.id,
        "storage_key": storage_key,
        "filename": file.filename,
        "estado": "segmentando",
        "pipeline_task_id": task.id,
        "orchestration": ORCHESTRATION_MODE,
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
    doc_nlp = nlp(texto[:100000])

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
