from app.core.celery_app import celery_app
from app.core.tei_client import TEIClient


@celery_app.task(queue="nlp", bind=True)
def generate_embeddings_for_document(self, document_id: int, chunks: list[str]):
    cliente = TEIClient()

    # Procesa en lote para eficiencia (el servidor aplica el prefijo de documento)
    embeddings = cliente.embed_documents_sync(chunks)

    return {"document_id": document_id, "num_chunks": len(embeddings)}
