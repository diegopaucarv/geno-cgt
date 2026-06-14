import magic
from app.core.minio_client import minio_client
from app.db.database import get_db
from app.models.domain.document import Document
from app.models.domain.user import User
from app.services.auth import get_current_user
from app.services.storage import generar_storage_key  # función auxiliar
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_MIME_TYPES = [
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload/{project_id}")
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Validar tipo MIME (con python-magic)
    content = await file.read(1024)  # leemos primeros bytes
    await file.seek(0)  # reiniciamos el puntero
    mime = magic.from_buffer(content, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Tipo de archivo no permitido: {mime}")

    # 2. Validar tamaño (FastAPI ya tiene límites, pero verificamos)
    file_size = 0
    chunk = await file.read(8192)
    while chunk:
        file_size += len(chunk)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(413, "Archivo demasiado grande")
        chunk = await file.read(8192)
    await file.seek(0)

    # 3. Generar storage_key única
    storage_key = f"projects/{project_id}/{current_user.id}_{file.filename}"

    # 4. Subir a MinIO
    await minio_client.upload_file(file, storage_key, content_type=mime)

    # 5. Guardar metadatos en DB
    new_doc = Document(
        project_id=project_id,
        original_filename=file.filename,
        storage_key=storage_key,
        mime_type=mime,
        size_bytes=file_size,
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    return {"id": new_doc.id, "storage_key": storage_key, "filename": file.filename}


@router.get("/download/{document_id}")
async def download_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Obtener el documento de la BD
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # Verificar que el usuario tenga acceso al proyecto (pendiente RLS)

    # Opción 1: descargar y devolver el archivo directamente
    file_bytes = await minio_client.download_file(doc.storage_key)
    headers = {"Content-Disposition": f'attachment; filename="{doc.original_filename}"'}
    return Response(content=file_bytes, media_type=doc.mime_type, headers=headers)


@router.get("/presigned/{document_id}")
async def get_presigned_url(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve una URL temporal para descarga directa desde MinIO"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    url = await minio_client.generate_presigned_url(
        doc.storage_key, expiration=600
    )  # 10 min
    return {"url": url}
