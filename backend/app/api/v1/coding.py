from uuid import UUID

from app.core.tei_client import TEIClient
from app.db.database import get_db
from app.models.domain.category import Categoria, CodigoSegmento
from app.models.domain.document import Documento
from app.models.domain.segment import Segmento
from app.models.domain.user import Usuario
from app.schemas import (
    CategoryCreate,
    CategoryResponse,
    CodeAssignRequest,
    CodeAssignResponse,
    RecommendationItem,
    SegmentResponse,
)
from app.services.auth import get_current_user
from app.services.rag import RAGService
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["coding"])
tei = TEIClient()


# ── GET /documents/{document_id}/segments ────────────────────────────


@router.get(
    "/documents/{document_id}/segments",
    response_model=list[SegmentResponse],
)
async def list_segments(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    result = await db.execute(
        select(Segmento)
        .where(Segmento.documento_id == document_id)
        .order_by(Segmento.posicion)
    )
    return result.scalars().all()


# ── POST /categories ─────────────────────────────────────────────────


@router.post(
    "/categories",
    status_code=201,
    response_model=CategoryResponse,
)
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    categoria = Categoria(**body.model_dump())
    db.add(categoria)
    await db.commit()
    await db.refresh(categoria)
    return categoria


# ── GET /categories ──────────────────────────────────────────────────


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
)
async def list_categories(
    proyecto_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Categoria).where(Categoria.proyecto_id == proyecto_id)
    )
    return result.scalars().all()


# ── POST /code-assignments ───────────────────────────────────────────


@router.post(
    "/code-assignments",
    status_code=201,
    response_model=CodeAssignResponse,
)
async def assign_code(
    body: CodeAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    segmento = await db.get(Segmento, body.segmento_id)
    if not segmento:
        raise HTTPException(404, "Segmento no encontrado")
    categoria = await db.get(Categoria, body.categoria_id)
    if not categoria:
        raise HTTPException(404, "Categoría no encontrada")

    asignacion = CodigoSegmento(**body.model_dump())
    db.add(asignacion)
    await db.commit()
    await db.refresh(asignacion)
    return asignacion


# ── GET /segments/{segment_id}/recommendations ───────────────────────


@router.get(
    "/segments/{segment_id}/recommendations",
    response_model=list[RecommendationItem],
)
async def recommend_codes(
    segment_id: UUID,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Recomienda códigos existentes para un segmento.

    Usa RAGService.search_similar_codes() que compara el embedding del
    segmento contra los centroides de las categorías (índice HNSW).
    Más rápido y semánticamente preciso que la versión anterior basada
    en frecuencia de co-ocurrencia en segmentos vecinos.
    """
    segmento = await db.get(Segmento, segment_id)
    if not segmento:
        raise HTTPException(404, "Segmento no encontrado")

    if segmento.embedding is None:
        return []

    doc = await db.get(Documento, segmento.documento_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # ── Buscar códigos similares vía RAG ──────────────────
    rag = RAGService(db, tei)
    candidates = await rag.search_similar_codes(
        segment_embedding=segmento.embedding,
        proyecto_id=doc.proyecto_id,
        top_k=limit,
    )

    if not candidates:
        return []

    # ── Resolver las categorías completas ─────────────────
    cat_ids = [UUID(c.id) for c in candidates]
    cats_stmt = select(Categoria).where(Categoria.id.in_(cat_ids))
    result = await db.execute(cats_stmt)
    categorias = {c.id: c for c in result.scalars().all()}

    return [
        RecommendationItem(
            categoria=categorias.get(UUID(c.id)),
            score=c.score,
            definicion=c.definicion[:200] if c.definicion else "",
        )
        for c in candidates
        if UUID(c.id) in categorias
    ]
