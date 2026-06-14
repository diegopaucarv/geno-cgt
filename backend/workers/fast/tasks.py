from app.core.celery_app import celery_app


@celery_app.task(queue="fast")
def validate_document_structure(document_id: int, file_path: str):
    # Lógica rápida: verificar extensión, tamaño, etc.
    return {"status": "validated", "document_id": document_id}
