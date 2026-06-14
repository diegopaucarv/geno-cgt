from collections import Counter
from uuid import UUID

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
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["coding"])


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
    segmento = await db.get(Segmento, segment_id)
    if not segmento:
        raise HTTPException(404, "Segmento no encontrado")

    if segmento.embedding is None:
        raise HTTPException(400, "El segmento no tiene embedding")

    doc = await db.get(Documento, segmento.documento_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # Buscar segmentos similares dentro del mismo proyecto
    similar_stmt = (
        select(Segmento.id)
        .join(Documento, Segmento.documento_id == Documento.id)
        .where(Documento.proyecto_id == doc.proyecto_id)
        .where(Segmento.id != segment_id)
        .where(Segmento.embedding.is_not(None))
        .order_by(func.cosine_distance(Segmento.embedding, segmento.embedding))
        .limit(20)
    )
    result = await db.execute(similar_stmt)
    similares = result.all()

    if not similares:
        return []

    # Categorías asignadas a esos segmentos similares
    seg_ids = [s.id for s in similares]
    assignments_stmt = select(CodigoSegmento.categoria_id).where(
        CodigoSegmento.segmento_id.in_(seg_ids)
    )
    result = await db.execute(assignments_stmt)
    cat_ids = [row[0] for row in result.all()]

    if not cat_ids:
        return []

    # Top N por frecuencia
    freq = Counter(cat_ids)
    top_cat_ids = [cid for cid, _ in freq.most_common(limit)]

    cats_stmt = select(Categoria).where(Categoria.id.in_(top_cat_ids))
    result = await db.execute(cats_stmt)
    categorias = result.scalars().all()

    cat_map = {c.id: c for c in categorias}
    ordered = [cat_map[cid] for cid in top_cat_ids if cid in cat_map]

    return [
        RecommendationItem(categoria=cat, frecuencia=freq[cat.id]) for cat in ordered
    ]
