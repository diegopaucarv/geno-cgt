"""Endpoints HITL (Human In The Loop) para revisión de hipótesis.

Plan §Fase 10: el Coordinator pausa el grafo LangGraph en nodos
de revisión humana. Estos endpoints permiten aceptar, rechazar o
modificar hipótesis candidatas antes de que el pipeline continúe.

Flujo:
  1. GET  /candidates     → listar hipótesis en estado 'candidate'
  2. POST /{id}/accept    → aceptar (status='accepted', confidence=1.0)
  3. POST /{id}/modify    → modificar texto y/o nivel
  4. POST /{id}/reject    → rechazar (status='rejected')
  5. POST /{id}/split     → dividir en hipótesis hijas (Tree of Thoughts)
"""

from __future__ import annotations

import re
from uuid import UUID

from app.db.database import get_db
from app.models.domain.project import Proyecto
from app.models.domain.synthesis import Hypothesis
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/hypotheses", tags=["hypotheses"])


# ═══════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════


class HypothesisCandidate(BaseModel):
    id: UUID
    text: str
    level: str  # 'general', 'specific', 'emergent'
    confidence: float
    status: str
    code_id: UUID | None = None
    parent_hypothesis_id: UUID | None = None

    model_config = {"from_attributes": True}


class AcceptRequest(BaseModel):
    justification: str = Field(
        default="", max_length=500, description="Justificación de la decisión"
    )


class ModifyRequest(BaseModel):
    new_text: str = Field(..., min_length=10, max_length=2000)
    new_level: str | None = Field(None, pattern="^(general|specific|emergent)$")
    justification: str = Field(default="", max_length=500)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class SplitRequest(BaseModel):
    children: list[str] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Textos de las hipótesis hijas (2-5)",
    )
    justification: str = Field(default="", max_length=500)


class HypothesisOut(BaseModel):
    """Representación plana usada por el panel de hipótesis (CRUD + duplicados)."""

    id: str
    text: str
    level: str
    confidence: float
    status: str
    code_id: str | None = None
    parent_hypothesis_id: str | None = None
    concern_labels: list = Field(default_factory=list)
    batch_number: int | None = None


class HypothesisCreate(BaseModel):
    project_id: UUID
    text: str = Field(..., min_length=1, max_length=4000)
    level: str = Field(default="emergent", pattern="^(general|specific|emergent)$")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: str = Field(default="candidate", max_length=50)
    code_id: UUID | None = None
    concern_labels: list[str] = Field(default_factory=list)


class HypothesisPatch(BaseModel):
    """Actualización parcial: todos los campos son opcionales."""

    text: str | None = Field(default=None, min_length=1, max_length=4000)
    level: str | None = Field(default=None, pattern="^(general|specific|emergent)$")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str | None = Field(default=None, max_length=50)
    concern_labels: list[str] | None = None


class BulkDeleteRequest(BaseModel):
    ids: list[UUID] = Field(..., min_length=1, max_length=500)


def _to_out(hyp: Hypothesis) -> HypothesisOut:
    """Serializa la fila ORM sin dejar escapar UUID ni tipos no JSON."""
    return HypothesisOut(
        id=str(hyp.id),
        text=hyp.text,
        level=hyp.level,
        confidence=float(hyp.confidence),
        status=hyp.status,
        code_id=str(hyp.code_id) if hyp.code_id else None,
        parent_hypothesis_id=(
            str(hyp.parent_hypothesis_id) if hyp.parent_hypothesis_id else None
        ),
        concern_labels=hyp.concern_labels or [],
        batch_number=hyp.batch_number,
    )


# Stopwords mínimas: artículos, preposiciones y conectores frecuentes (ES + EN).
_STOPWORDS = {
    "de",
    "la",
    "el",
    "los",
    "las",
    "que",
    "y",
    "en",
    "a",
    "un",
    "una",
    "del",
    "se",
    "por",
    "con",
    "para",
    "al",
    "es",
    "su",
    "lo",
    "como",
    "mas",
    "o",
    "sus",
    "no",
    "si",
    "the",
    "of",
    "to",
}

# Conserva letras acentuadas del español: son discriminativas en las hipótesis.
_TOKEN_RE = re.compile(r"[^0-9a-záéíóúñü ]")


def _tokens(texto: str) -> set[str]:
    clean = _TOKEN_RE.sub(" ", (texto or "").lower())
    return {t for t in clean.split() if len(t) > 2 and t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ═══════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════


@router.get("/candidates", response_model=list[HypothesisCandidate])
async def list_candidates(
    proyecto_id: UUID = Query(..., description="ID del proyecto"),
    status: str = Query("candidate", description="Filtrar por estado"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Lista hipótesis pendientes de revisión humana.

    El Coordinator (LangGraph) pausa el pipeline cuando hay hipótesis
    en estado 'candidate'. Este endpoint alimenta el Hypothesis Panel
    del frontend.
    """
    result = await db.execute(
        select(Hypothesis)
        .where(Hypothesis.project_id == proyecto_id)
        .where(Hypothesis.status == status)
        .order_by(Hypothesis.confidence.desc())
    )
    return result.scalars().all()


# ───────────────────────────────────────────────────────────────
# CRUD / panel de hipótesis
# Rutas literales declaradas antes que las dinámicas para evitar shadowing.
# ───────────────────────────────────────────────────────────────


@router.post("", response_model=HypothesisOut, status_code=201)
async def create_hypothesis(
    body: HypothesisCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Crea una hipótesis suelta (sin penalización de confianza ni HITL)."""
    if not await db.get(Proyecto, body.project_id):
        raise HTTPException(404, "Proyecto no encontrado")

    hyp = Hypothesis(
        project_id=body.project_id,
        code_id=body.code_id,
        text=body.text,
        level=body.level,
        confidence=body.confidence,
        status=body.status,
        concern_labels=list(body.concern_labels),
    )
    db.add(hyp)
    await db.commit()
    await db.refresh(hyp)
    return _to_out(hyp)


@router.get("/by-project/{project_id}")
async def list_by_project(
    project_id: UUID,
    status: str | None = Query(None, description="Filtrar por estado"),
    level: str | None = Query(None, description="general|specific|emergent"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Lista todas las hipótesis del proyecto con filtros opcionales.

    `by_status` cuenta por estado sobre el proyecto (respetando `level` pero
    ignorando `status`) para que el frontend pueda pintar contadores de tabs.
    La tabla no tiene timestamp: se ordena por confianza y luego texto.
    """
    stmt = select(Hypothesis).where(Hypothesis.project_id == project_id)
    if status:
        stmt = stmt.where(Hypothesis.status == status)
    if level:
        stmt = stmt.where(Hypothesis.level == level)
    stmt = stmt.order_by(Hypothesis.confidence.desc(), Hypothesis.text.asc())
    rows = (await db.execute(stmt)).scalars().all()

    count_stmt = select(Hypothesis.status, func.count()).where(
        Hypothesis.project_id == project_id
    )
    if level:
        count_stmt = count_stmt.where(Hypothesis.level == level)
    count_stmt = count_stmt.group_by(Hypothesis.status)
    by_status = {st: int(n) for st, n in (await db.execute(count_stmt)).all()}

    return {
        "items": [_to_out(h) for h in rows],
        "total": len(rows),
        "by_status": by_status,
    }


@router.get("/duplicates/{project_id}")
async def get_hypothesis_duplicates(
    project_id: UUID,
    threshold: float = Query(0.8, description="Umbral Jaccard; se acota a [0.5, 1.0]"),
    max_items: int = Query(2000, description="Máximo de hipótesis a comparar"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Detecta hipótesis casi duplicadas con Jaccard de tokens (sin pg_trgm).

    Se agrupan por clausura transitiva (union-find): A~B y B~C implican un solo
    clúster A,B,C. Solo se devuelven clústeres de tamaño >= 2.
    """
    thr = max(0.5, min(1.0, float(threshold)))
    limit = max(1, min(int(max_items), 5000))

    result = await db.execute(
        select(Hypothesis)
        .where(Hypothesis.project_id == project_id)
        .where(Hypothesis.status.not_in(["rejected", "split"]))
        .order_by(Hypothesis.confidence.desc(), Hypothesis.text.asc())
        .limit(limit)
    )
    rows = list(result.scalars().all())

    token_sets = [_tokens(h.text) for h in rows]
    n = len(rows)

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        if not token_sets[i]:
            continue
        for j in range(i + 1, n):
            if _jaccard(token_sets[i], token_sets[j]) >= thr:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    # dict conserva el orden de inserción (i ascendente) → clústeres deterministas
    grouped: dict[int, list[int]] = {}
    for i in range(n):
        grouped.setdefault(find(i), []).append(i)

    clusters = []
    for idxs in grouped.values():
        if len(idxs) < 2:
            continue
        base_tokens = token_sets[idxs[0]]
        items = []
        for pos, idx in enumerate(idxs):
            h = rows[idx]
            sim = 1.0 if pos == 0 else _jaccard(base_tokens, token_sets[idx])
            items.append(
                {
                    "id": str(h.id),
                    "text": h.text,
                    "level": h.level,
                    "status": h.status,
                    "confidence": float(h.confidence),
                    "similarity": round(sim, 4),
                    "is_suggested_keep": pos == 0,
                }
            )
        clusters.append(
            {"cluster_id": len(clusters) + 1, "size": len(items), "items": items}
        )

    return {
        "threshold": thr,
        "total_hypotheses": n,
        "clusters": clusters,
        "redundant_count": sum(c["size"] for c in clusters) - len(clusters),
    }


@router.post("/bulk-delete")
async def bulk_delete_hypotheses(
    body: BulkDeleteRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra en lote; antes desengancha las hijas para no violar el self-FK."""
    await db.execute(
        update(Hypothesis)
        .where(Hypothesis.parent_hypothesis_id.in_(body.ids))
        .values(parent_hypothesis_id=None)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(
        delete(Hypothesis)
        .where(Hypothesis.id.in_(body.ids))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {"deleted": int(result.rowcount or 0)}


@router.patch("/{hypothesis_id}", response_model=HypothesisOut)
async def update_hypothesis(
    hypothesis_id: UUID,
    body: HypothesisPatch = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualización parcial sin penalización de confianza ni cambio de estado."""
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    for campo, valor in body.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(hyp, campo, valor)

    await db.commit()
    await db.refresh(hyp)
    return _to_out(hyp)


@router.delete("/{hypothesis_id}")
async def delete_hypothesis(
    hypothesis_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borrado físico; las hijas quedan huérfanas en la raíz del árbol."""
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    await db.execute(
        update(Hypothesis)
        .where(Hypothesis.parent_hypothesis_id == hypothesis_id)
        .values(parent_hypothesis_id=None)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        delete(Hypothesis)
        .where(Hypothesis.id == hypothesis_id)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {"deleted": True, "id": str(hypothesis_id)}


@router.post("/{hypothesis_id}/accept")
async def accept_hypothesis(
    hypothesis_id: UUID,
    body: AcceptRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Aceptar una hipótesis candidata.

    Cambia status='accepted', confidence=1.0.
    El Coordinator puede continuar el pipeline al recibir esta señal.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    if hyp.status != "candidate":
        raise HTTPException(
            400, f"Solo se pueden aceptar hipótesis candidatas (actual: {hyp.status})"
        )

    hyp.status = "accepted"
    hyp.confidence = 1.0
    await db.commit()
    await db.refresh(hyp)
    return {"id": str(hyp.id), "status": hyp.status, "confidence": hyp.confidence}


@router.post("/{hypothesis_id}/modify")
async def modify_hypothesis(
    hypothesis_id: UUID,
    body: ModifyRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Modificar una hipótesis candidata (texto y/o nivel).

    La hipótesis modificada vuelve a 'candidate' para que el Testeador
    de memos (A06) la re-evalúe en el siguiente ciclo.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    if hyp.status not in ("candidate", "accepted"):
        raise HTTPException(
            400,
            f"Solo se pueden modificar hipótesis candidatas o aceptadas (actual: {hyp.status})",
        )

    hyp.text = body.new_text
    if body.new_level:
        hyp.level = body.new_level
    hyp.status = "candidate"  # vuelve a cola de revisión
    hyp.confidence = max(
        0.0, hyp.confidence - 0.2
    )  # leve penalización por modificación
    await db.commit()
    await db.refresh(hyp)
    return {"id": str(hyp.id), "status": hyp.status, "text": hyp.text[:100] + "..."}


@router.post("/{hypothesis_id}/reject")
async def reject_hypothesis(
    hypothesis_id: UUID,
    body: RejectRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Rechazar una hipótesis.

    Cambia status='rejected'. El Coordinator excluye hipótesis
    rechazadas de ciclos futuros de B3 y A3.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    hyp.status = "rejected"
    hyp.confidence = 0.0
    await db.commit()
    return {"id": str(hyp.id), "status": hyp.status, "reason": body.reason[:100]}


@router.post("/{hypothesis_id}/split", status_code=201)
async def split_hypothesis(
    hypothesis_id: UUID,
    body: SplitRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Dividir una hipótesis en hipótesis hijas (Tree of Thoughts).

    La hipótesis original se marca como 'split'. Las hijas heredan
    el project_id, code_id y parent_hypothesis_id.

    Útil cuando una hipótesis es demasiado amplia y el investigador
    identifica sub-hipótesis más precisas.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    if hyp.status == "rejected":
        raise HTTPException(400, "No se puede dividir una hipótesis rechazada")

    # Marcar original como dividida
    hyp.status = "split"

    # Crear hijas
    children = []
    for child_text in body.children:
        child = Hypothesis(
            project_id=hyp.project_id,
            code_id=hyp.code_id,
            text=child_text,
            level=hyp.level,
            confidence=0.5,
            status="candidate",
            parent_hypothesis_id=hypothesis_id,
        )
        db.add(child)
        children.append(child)

    await db.commit()
    return {
        "parent_id": str(hyp.id),
        "parent_status": hyp.status,
        "children_created": len(children),
    }
