"""Endpoints de búsqueda RAG: RRF, semántica, léxica + MMR opcional."""

from typing import Literal
from uuid import UUID

from app.core.tei_client import TEIClient
from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from app.services.rag import RAGService
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

tei = TEIClient()


@router.get("/search")
async def search_segments(
    q: str = Query(..., min_length=2, description="Texto de búsqueda"),
    proyecto_id: UUID = Query(..., description="ID del proyecto"),
    top_k: int = Query(5, ge=1, le=20, description="Nº de resultados"),
    fusion: Literal["rrf", "semantic", "lexical"] = Query(
        "rrf", description="Modo de fusión: rrf, semantic, lexical"
    ),
    diversify: bool = Query(False, description="Activar MMR para diversificar"),
    lambda_mmr: float = Query(
        0.7, ge=0.0, le=1.0, description="Peso relevancia vs diversidad (MMR)"
    ),
    documento_id: UUID | None = Query(None, description="Filtrar por documento"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Búsqueda de segmentos con fusión configurable y MMR opcional.

    Modos de fusión:
    - **rrf**: Reciprocal Rank Fusion — rankings semántico + léxico (recomendado)
    - **semantic**: solo similitud coseno (índice HNSW)
    - **lexical**: solo BM25 (búsqueda de términos exactos)

    Si `diversify=true`, aplica MMR para evitar near-duplicates y maximizar
    diversidad de facetas. Útil cuando los resultados son muy similares.
    """
    service = RAGService(db, tei)
    results = await service.search(
        query=q,
        proyecto_id=proyecto_id,
        top_k=top_k,
        fusion=fusion,
        diversify=diversify,
        lambda_mmr=lambda_mmr,
        documento_id=documento_id,
    )
    return [
        {
            "segmento_id": str(r.segmento_id),
            "texto": r.texto,
            "documento_id": str(r.documento_id),
            "score": r.score,
            "mmr_score": r.mmr_score,
        }
        for r in results
    ]


@router.get("/context/{code_id}")
async def get_code_context(
    code_id: UUID,
    proyecto_id: UUID = Query(..., description="ID del proyecto"),
    top_k: int = Query(10, ge=1, le=30, description="Nº de segmentos de contexto"),
    lambda_mmr: float = Query(0.6, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Recupera segmentos de contexto para un código (Map-Reduce synthesis).
    Usa el centroide del código como query. RRF + MMR con lambda bajo
    para privilegiar diversidad de facetas.
    """
    service = RAGService(db, tei)
    results = await service.search_context_for_code(
        code_id=code_id,
        proyecto_id=proyecto_id,
        top_k=top_k,
        lambda_mmr=lambda_mmr,
    )
    return [
        {
            "segmento_id": str(r.segmento_id),
            "texto": r.texto,
            "documento_id": str(r.documento_id),
            "score": r.score,
            "mmr_score": r.mmr_score,
        }
        for r in results
    ]
