"""Comparison tools — basadas en TEI embeddings, sin LLM.

Usan el servidor TEI local (voyage-4-nano ONNX) para comparar
similitud semántica entre textos. No requieren llamadas a Together.ai.
"""

from __future__ import annotations

import asyncio
import logging

from app.agents.tool_registry import tool
from app.core.tei_client import TEIClient

logger = logging.getLogger(__name__)

# Instancia compartida (TEIClient ya tiene cache en Redis)
tei = TEIClient()


def _run_async(coro):
    """Helper: ejecuta coroutine en event loop. Seguro desde sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Ya hay un loop corriendo (ej. dentro de FastAPI)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════
# Tools
# ═══════════════════════════════════════════════════════════════════


@tool(
    name="compare_embeddings",
    description="Compara la similitud semántica entre dos textos (0-1). "
    "Útil para detectar códigos redundantes: si similarity > 0.85, "
    "los códigos probablemente describen el mismo fenómeno.",
    parameters={
        "text_a": "primer texto a comparar",
        "text_b": "segundo texto a comparar",
    },
)
def compare_embeddings(text_a: str, text_b: str) -> dict:
    """Tool: similitud coseno entre dos textos vía TEI."""

    async def _compare():
        emb_a = await tei.embed_query(text_a)
        emb_b = await tei.embed_query(text_b)
        dot = sum(a * b for a, b in zip(emb_a, emb_b))
        return {
            "similarity": round(dot, 4),
            "are_duplicates": dot > 0.85,
        }

    try:
        return _run_async(_compare())
    except Exception as e:
        logger.error("compare_embeddings failed: %s", e)
        return {"error": str(e)}


@tool(
    name="find_similar_codes",
    description="Busca códigos existentes semánticamente similares a un "
    "nuevo código candidato (por su definición). Devuelve los "
    "top-3 más similares. Útil para anti-redundancia antes de "
    "crear un código nuevo.",
    parameters={
        "code_definition": "definición del código candidato a verificar",
        "proyecto_id": "UUID del proyecto donde buscar",
    },
)
def find_similar_codes(code_definition: str, proyecto_id: str) -> dict:
    """Tool: detectar códigos redundantes vía TEI + pgvector."""
    import asyncio as _asyncio
    from uuid import UUID

    from app.db.database import AsyncSessionLocal
    from app.services.rag import RAGService

    async def _find():
        async with AsyncSessionLocal() as db:
            embedding = await tei.embed_query(code_definition)
            service = RAGService(db, tei)
            results = await service.search_similar_codes(
                segment_embedding=embedding,
                proyecto_id=UUID(proyecto_id),
                top_k=3,
            )
            return {
                "similar_codes": [
                    {
                        "id": c.id,
                        "nombre": c.nombre,
                        "definicion": (c.definicion or "")[:200],
                        "score": c.score,
                    }
                    for c in results
                ],
                "has_near_duplicate": any(c.score > 0.85 for c in results),
            }

    try:
        return _asyncio.run(_find())
    except Exception as e:
        logger.error("find_similar_codes failed: %s", e)
        return {"error": str(e)}
