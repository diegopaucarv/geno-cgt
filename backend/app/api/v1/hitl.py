"""HITL decision endpoint — gates del pipeline selectivo.

Los workers del pipeline selectivo insertan filas en hitl_decisions
cuando llegan a un gate HITL. El frontend consulta las pendientes
y el investigador decide ACCEPT/MODIFY/REJECT.

También contiene el HITL gate unificado de open coding:
  GET  /projects/{pid}/hitl/open-coding/status
  POST /projects/{pid}/hitl/open-coding/decide
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.schemas.hitl import (
    HitlDecisionBulkDelete,
    HitlDecisionCreate,
    HitlDecisionFull,
    HitlDecisionListResponse,
    HitlDecisionRequest,
    HitlDecisionResponse,
    HitlDecisionUpdate,
    HitlPendingItem,
    OpenCodingHITLDecision,
    OpenCodingHITLDecisionResponse,
    OpenCodingHITLStatusResponse,
)
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["hitl"])

# Columnas del CRUD completo; el orden casa 1:1 con _decision_full().
_FULL_COLS = (
    "id, project_id, gate_name, status, proposal, critic_verdict, "
    "researcher_decision, researcher_note, researcher_feedback, decided_at, "
    "creado_en, actualizado_en"
)

# Estado terminal → researcher_decision que espera el resto del pipeline.
_STATUS_TO_DECISION = {
    "accepted": "accept",
    "modified": "modify",
    "rejected": "reject",
}


def _utcnow() -> datetime:
    """UTC naive para columnas ``timestamp without time zone``.

    asyncpg rechaza datetimes con tzinfo contra ``timestamp`` (el modelo usa
    ``DateTime`` naive), así que se normaliza antes de escribir.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_json_obj(value) -> dict:
    """Normaliza un valor jsonb leído por ``text()``.

    asyncpg entrega las columnas ``jsonb`` como texto salvo que se registre un
    codec, así que hay que deserializar. También se acepta ya-deserializado por
    si en el futuro se registra el codec y para los tests con dobles.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _decision_full(row) -> HitlDecisionFull:
    """Mapea una fila cruda de ``text()`` al schema completo.

    proposal/critic_verdict pueden venir NULL cuando la fila la escribió un
    worker por SQL directo; se normalizan a ``{}`` para no romper el contrato.
    """
    return HitlDecisionFull(
        id=row[0],
        project_id=row[1],
        gate_name=row[2],
        status=row[3],
        proposal=_as_json_obj(row[4]),
        critic_verdict=_as_json_obj(row[5]),
        researcher_decision=row[6],
        researcher_note=row[7],
        researcher_feedback=row[8],
        decided_at=row[9],
        created_at=row[10],
        updated_at=row[11],
    )


# ═══════════════════════════════════════════════════════════════════════
# CRUD completo de hitl_decisions
#
# ═══════════════════════════════════════════════════════════════════════
# Open Coding HITL Gate — unified concern / population / categories gate
# ═══════════════════════════════════════════════════════════════════════


@router.get(
    "/projects/{project_id}/hitl/open-coding/status",
    response_model=OpenCodingHITLStatusResponse,
)
async def get_open_coding_hitl_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna el estado actual del HITL gate de open coding.

    El frontend usa esta data para poblar el panel de decisiones donde
    el investigador elige el concern principal, la población, y confirma
    las categorías centrales antes de avanzar a codificación selectiva.
    """
    # ── 1. Docs processed vs total ──────────────────────────────────
    docs_total = await db.execute(
        text("SELECT COUNT(*) FROM documentos WHERE proyecto_id = :pid"),
        {"pid": project_id},
    )
    total_docs = docs_total.scalar() or 0

    docs_proc = await db.execute(
        text(
            "SELECT COUNT(*) FROM documentos "
            "WHERE proyecto_id = :pid AND TRIM(estado) IN "
            "('listo', 'resumiendo', 'resumido', 'sintetizado', "
            " 'procesado', 'incidentes_extraidos', 'codificando', 'codificado')"
        ),
        {"pid": project_id},
    )
    docs_processed = docs_proc.scalar() or 0

    # ── 2. Batch number ─────────────────────────────────────────────
    proj_row = await db.execute(
        text(
            "SELECT batch_number, chosen_concern, chosen_population "
            "FROM proyectos WHERE id = :pid"
        ),
        {"pid": project_id},
    )
    proj = proj_row.fetchone()
    if not proj:
        raise HTTPException(404, "Proyecto no encontrado")

    batch_number = proj[0] or 0
    chosen_concern = proj[1]
    chosen_population = proj[2]

    # ── 3. Concern candidates (from concerns table) ─────────────────
    concern_rows = await db.execute(
        text(
            "SELECT label, description, identified_at_batch "
            "FROM concerns "
            "WHERE project_id = :pid AND status != 'rejected' "
            "ORDER BY identified_at_batch DESC, label ASC"
        ),
        {"pid": project_id},
    )
    concern_candidates = []
    for row in concern_rows:
        # Resolve supporting codes: categories whose concern_label matches
        codes_result = await db.execute(
            text(
                "SELECT nombre FROM categorias "
                "WHERE proyecto_id = :pid AND concern_label = :clabel"
            ),
            {"pid": project_id, "clabel": row[0]},
        )
        supporting = [r[0] for r in codes_result]
        concern_candidates.append(
            {
                "label": row[0],
                "supporting_codes": supporting,
                "rationale": row[1] or "",
            }
        )

    # ── 4. Population proposals (latest population_context) ─────────
    pop_row = await db.execute(
        text(
            "SELECT surprising_details, language_patterns, "
            "data_production_context, version "
            "FROM population_contexts "
            "WHERE proyecto_id = :pid "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"pid": project_id},
    )
    pop = pop_row.fetchone()
    population_proposals = []
    if pop:
        # Build description from the three context dimensions
        parts = [p for p in [pop[0], pop[1], pop[2]] if p]
        description = " ".join(parts) if parts else "(sin descripción)"
        population_proposals.append(
            {"description": description, "source_batch": pop[3] or 1}
        )

    # ── 5. Unified categories ───────────────────────────────────────
    cat_rows = await db.execute(
        text(
            "SELECT id, nombre, definicion, es_central "
            "FROM categorias WHERE proyecto_id = :pid "
            "ORDER BY es_central DESC, nombre ASC"
        ),
        {"pid": project_id},
    )
    unified_categories = [
        {
            "id": str(r[0]),
            "label": r[1],
            "definition": r[2] or "",
            "is_core_candidate": bool(r[3]),
        }
        for r in cat_rows
    ]

    # ── 6. Unified hypotheses ───────────────────────────────────────
    hyp_rows = await db.execute(
        text(
            "SELECT h.id, h.text, h.concern_labels, "
            "COALESCE(c.es_central, false) AS is_core "
            "FROM hypotheses h "
            "LEFT JOIN categorias c ON c.id = h.code_id "
            "WHERE h.project_id = :pid "
            "ORDER BY h.confidence DESC"
        ),
        {"pid": project_id},
    )
    # Gather all concern labels for relevance check
    all_concern_labels = {cc["label"] for cc in concern_candidates}
    unified_hypotheses = []
    for r in hyp_rows:
        hyp_labels = r[2] if isinstance(r[2], list) else []
        relevance = (
            "DIRECT"
            if any(lbl in all_concern_labels for lbl in hyp_labels)
            else "INDIRECT"
        )
        unified_hypotheses.append(
            {
                "id": str(r[0]),
                "text": r[1] or "",
                "concern_relevance": relevance,
                "is_core_candidate": bool(r[3]),
            }
        )

    # ── 7. can_proceed ──────────────────────────────────────────────
    can_proceed = bool(chosen_concern and chosen_population)

    return {
        "docs_processed": docs_processed,
        "total_docs": total_docs,
        "batch_number": batch_number,
        "concern_candidates": concern_candidates,
        "population_proposals": population_proposals,
        "unified_categories": unified_categories,
        "unified_hypotheses": unified_hypotheses,
        "chosen_concern": chosen_concern,
        "chosen_population": chosen_population,
        "can_proceed": can_proceed,
    }


@router.post(
    "/projects/{project_id}/hitl/open-coding/decide",
    response_model=OpenCodingHITLDecisionResponse,
)
async def decide_open_coding_hitl(
    project_id: UUID,
    decision: OpenCodingHITLDecision,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """El investigador decide sobre concern, población y categorías centrales.

    Acciones:
    1. UPDATE proyectos.chosen_concern y chosen_population
    2. UPDATE categorias.es_central = true para core_category_ids
    3. INSERT en hitl_decisions con gate_name="open_coding_batch_{n}"
    4. Si confirmed=true, disparar coordinator de codificación selectiva
    5. Publicar evento Redis: project:{id}:events con type="hitl_resolved"
    """
    # ── 1. Obtener batch_number actual ──────────────────────────────
    proj_row = await db.execute(
        text("SELECT batch_number FROM proyectos WHERE id = :pid"),
        {"pid": project_id},
    )
    proj = proj_row.fetchone()
    if not proj:
        raise HTTPException(404, "Proyecto no encontrado")
    batch_number = proj[0] or 0

    now = _utcnow()

    # ── 2. Update proyectos ─────────────────────────────────────────
    await db.execute(
        text(
            "UPDATE proyectos SET "
            "chosen_concern = :concern, "
            "chosen_population = :pop "
            "WHERE id = :pid"
        ),
        {
            "concern": decision.chosen_concern,
            "pop": decision.chosen_population,
            "pid": project_id,
        },
    )

    # ── 3. Update categorias.es_central for core_category_ids ────────
    core_updated = 0
    if decision.core_category_ids:
        # Verify which categories exist before updating
        cids_str = [str(cid) for cid in decision.core_category_ids]
        count_result = await db.execute(
            text(
                "SELECT COUNT(*) FROM categorias "
                "WHERE proyecto_id = :pid AND id = ANY(:cids)"
            ),
            {"pid": project_id, "cids": cids_str},
        )
        existing = count_result.scalar() or 0

        await db.execute(
            text(
                "UPDATE categorias SET es_central = true "
                "WHERE proyecto_id = :pid AND id = ANY(:cids)"
            ),
            {"pid": project_id, "cids": cids_str},
        )
        core_updated = existing

    # ── 4. Insert hitl_decision record ──────────────────────────────
    gate_name = f"open_coding_batch_{batch_number}"
    proposal_payload = {
        "chosen_concern": decision.chosen_concern,
        "chosen_population": decision.chosen_population,
        "core_category_ids": [str(cid) for cid in decision.core_category_ids],
        "confirmed": decision.confirmed,
    }
    await db.execute(
        text(
            "INSERT INTO hitl_decisions "
            "(id, project_id, gate_name, proposal, critic_verdict, "
            "status, researcher_decision, researcher_note, decided_at) "
            "VALUES (gen_random_uuid(), :pid, :gate, :proposal, "
            "'{}'::jsonb, :status, :dec, :note, :now)"
        ),
        {
            "pid": project_id,
            "gate": gate_name,
            "proposal": json.dumps(proposal_payload, ensure_ascii=False),
            "status": "accepted" if decision.confirmed else "modified",
            "dec": "accept" if decision.confirmed else "modify",
            "note": decision.researcher_note or "",
            "now": now,
        },
    )

    await db.commit()

    # ── Poblar concern_label y population_label en categorias ────────
    if decision.chosen_concern:
        await db.execute(
            text(
                "UPDATE categorias SET concern_label = :concern "
                "WHERE proyecto_id = :pid AND es_central = true"
            ),
            {"concern": decision.chosen_concern, "pid": project_id},
        )
    if decision.chosen_population:
        await db.execute(
            text(
                "UPDATE categorias SET population_label = :pop WHERE proyecto_id = :pid"
            ),
            {"pop": decision.chosen_population, "pid": project_id},
        )
    await db.commit()

    # ── 5. Disparar generalización de población ──────────────────────
    if decision.chosen_population:
        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "generalize_population",
                args=[str(project_id)],
                queue="fast",
            )
            logger.info(
                "Population generalization dispatched for project=%s "
                "after open-coding HITL decision (gate=%s)",
                project_id,
                gate_name,
            )
        except Exception as e:
            logger.warning("Failed to dispatch population generalization: %s", e)

    # ── 6. Si confirmed, disparar coordinator ───────────────────────
    if decision.confirmed:
        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "selective_coding_coordinator",
                args=[str(project_id)],
                queue="heavy",
            )
            logger.info(
                "Selective coding coordinator dispatched for project=%s "
                "after open-coding HITL confirmation (gate=%s)",
                project_id,
                gate_name,
            )
        except Exception as e:
            logger.warning("Failed to dispatch selective coding coordinator: %s", e)

    # ── 7. Publicar evento Redis ────────────────────────────────────
    try:
        from app.api.v1.events import publish_event

        publish_event(
            str(project_id),
            "hitl_resolved",
            {
                "gate": gate_name,
                "chosen_concern": decision.chosen_concern,
                "chosen_population": decision.chosen_population,
                "confirmed": decision.confirmed,
            },
        )
    except Exception as e:
        logger.warning("Failed to publish hitl_resolved event: %s", e)

    logger.info(
        "Open-coding HITL decision: project=%s gate=%s confirmed=%s user=%s",
        project_id,
        gate_name,
        decision.confirmed,
        current_user.id,
    )

    return {
        "status": "confirmed" if decision.confirmed else "saved",
        "chosen_concern": decision.chosen_concern,
        "chosen_population": decision.chosen_population,
        "core_categories_set": core_updated,
        "confirmed": decision.confirmed,
    }


# Se declaran antes de /hitl/{gate_name}/detail: GET /hitl/decisions/{id}
# comparte forma con esa ruta paramétrica y así el literal "decisions" gana
# el matching en lugar de interpretarse como un gate_name.
# ═══════════════════════════════════════════════════════════════════════


@router.get(
    "/projects/{project_id}/hitl/decisions",
    response_model=HitlDecisionListResponse,
)
async def list_hitl_decisions(
    project_id: UUID,
    status: str | None = Query(None, description="Filtra por estado"),
    gate_name: str | None = Query(None, description="Filtra por gate"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Lista las decisiones HITL del proyecto, las más recientes primero.

    ``counts`` se calcula sin aplicar el filtro: son las pastillas del filtro y
    deben reflejar todo el proyecto, no solo la página visible.
    """
    where = ["project_id = :pid"]
    params: dict = {"pid": project_id}
    if status:
        where.append("status = :status")
        params["status"] = status
    if gate_name:
        where.append("gate_name = :gate_name")
        params["gate_name"] = gate_name
    where_sql = " AND ".join(where)

    total = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM hitl_decisions WHERE {where_sql}"), params
        )
    ).scalar() or 0

    counts = {"pending": 0, "accepted": 0, "modified": 0, "rejected": 0}
    counts_rows = await db.execute(
        text(
            "SELECT status, COUNT(*) FROM hitl_decisions "
            "WHERE project_id = :pid GROUP BY status"
        ),
        {"pid": project_id},
    )
    for row_status, row_count in counts_rows:
        # Estados fuera del contrato se ignoran para no añadir claves extra.
        if row_status in counts:
            counts[row_status] = row_count

    rows = await db.execute(
        text(
            f"SELECT {_FULL_COLS} FROM hitl_decisions "
            f"WHERE {where_sql} ORDER BY creado_en DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    )
    return {
        "items": [_decision_full(row) for row in rows],
        "total": total,
        "counts": counts,
    }


@router.post(
    "/projects/{project_id}/hitl/decisions",
    response_model=HitlDecisionFull,
    status_code=201,
)
async def create_hitl_decision(
    project_id: UUID,
    body: HitlDecisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Crea una decisión HITL desde cero (siembra manual o importación).

    Si nace ya resuelta se marca ``decided_at`` y se rellena
    ``researcher_decision`` para que el resto del pipeline la trate como tal.
    """
    decided_at = _utcnow() if body.status != "pending" else None
    researcher_decision = _STATUS_TO_DECISION.get(body.status)

    row = (
        await db.execute(
            text(
                "INSERT INTO hitl_decisions "
                "(id, project_id, gate_name, proposal, critic_verdict, status, "
                "researcher_decision, researcher_note, decided_at) "
                "VALUES (gen_random_uuid(), :pid, :gate_name, :proposal, "
                ":critic_verdict, :status, :dec, :note, :decided_at) "
                f"RETURNING {_FULL_COLS}"
            ),
            {
                "pid": project_id,
                "gate_name": body.gate_name,
                "proposal": json.dumps(body.proposal, ensure_ascii=False),
                "critic_verdict": json.dumps(body.critic_verdict, ensure_ascii=False),
                "status": body.status,
                "dec": researcher_decision,
                "note": body.note,
                "decided_at": decided_at,
            },
        )
    ).fetchone()
    await db.commit()
    return _decision_full(row)


@router.get(
    "/projects/{project_id}/hitl/decisions/{decision_id}",
    response_model=HitlDecisionFull,
)
async def get_hitl_decision(
    project_id: UUID,
    decision_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve una decisión completa; 404 si no existe o es de otro proyecto."""
    row = (
        await db.execute(
            text(
                f"SELECT {_FULL_COLS} FROM hitl_decisions "
                "WHERE project_id = :pid AND id = :did"
            ),
            {"pid": project_id, "did": decision_id},
        )
    ).fetchone()
    if not row:
        raise HTTPException(404, "Decisión HITL no encontrada")
    return _decision_full(row)


@router.patch(
    "/projects/{project_id}/hitl/decisions/{decision_id}",
    response_model=HitlDecisionFull,
)
async def update_hitl_decision(
    project_id: UUID,
    decision_id: UUID,
    body: HitlDecisionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza campos sueltos de una decisión HITL.

    Solo se escriben los campos presentes en el body. Resolver la decisión
    (accepted/modified) re-despacha el coordinator igual que
    ``.../hitl/{gate}/decide``, pero solo la primera vez que se resuelve para
    no duplicar el trabajo si el investigador vuelve a guardar el mismo estado.
    """
    current = (
        await db.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND id = :did"
            ),
            {"pid": project_id, "did": decision_id},
        )
    ).fetchone()
    if not current:
        raise HTTPException(404, "Decisión HITL no encontrada")
    previous_status = current[0]

    sets: list[str] = []
    params: dict = {"pid": project_id, "did": decision_id}
    if body.gate_name is not None:
        sets.append("gate_name = :gate_name")
        params["gate_name"] = body.gate_name
    if body.note is not None:
        sets.append("researcher_note = :note")
        params["note"] = body.note
    if body.feedback is not None:
        sets.append("researcher_feedback = :feedback")
        params["feedback"] = body.feedback

    new_status = body.status
    if new_status is not None:
        sets.append("status = :status")
        params["status"] = new_status
        resolved = _STATUS_TO_DECISION.get(new_status)
        if resolved is not None:
            sets.append("researcher_decision = :dec")
            params["dec"] = resolved
            sets.append("decided_at = :now")
            params["now"] = _utcnow()

    if sets:
        # El UPDATE por SQL crudo no dispara el onupdate del TimestampMixin.
        sets.append("actualizado_en = now()")
        await db.execute(
            text(
                f"UPDATE hitl_decisions SET {', '.join(sets)} "
                "WHERE project_id = :pid AND id = :did"
            ),
            params,
        )
        await db.commit()

    if new_status in ("accepted", "modified") and previous_status not in (
        "accepted",
        "modified",
    ):
        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "selective_coding_coordinator",
                args=[str(project_id)],
                queue="heavy",
            )
            logger.info(
                "Coordinator re-dispatched for project=%s after PATCH status=%s",
                project_id,
                new_status,
            )
        except Exception as e:
            logger.warning("Failed to re-dispatch coordinator: %s", e)

    row = (
        await db.execute(
            text(
                f"SELECT {_FULL_COLS} FROM hitl_decisions "
                "WHERE project_id = :pid AND id = :did"
            ),
            {"pid": project_id, "did": decision_id},
        )
    ).fetchone()
    if not row:
        raise HTTPException(404, "Decisión HITL no encontrada")
    return _decision_full(row)


@router.delete("/projects/{project_id}/hitl/decisions/{decision_id}")
async def delete_hitl_decision(
    project_id: UUID,
    decision_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra una decisión HITL; 404 si no existe en este proyecto."""
    result = await db.execute(
        text("DELETE FROM hitl_decisions WHERE project_id = :pid AND id = :did"),
        {"pid": project_id, "did": decision_id},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Decisión HITL no encontrada")
    return {"status": "ok", "deleted": 1}


@router.delete("/projects/{project_id}/hitl/decisions")
async def bulk_delete_hitl_decisions(
    project_id: UUID,
    body: HitlDecisionBulkDelete,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra en bloque por ids y/o filtros.

    Exigimos ids o algún filtro porque un body vacío borraría todo el proyecto,
    demasiado destructivo para una acción por defecto.
    """
    if not body.ids and not body.status and not body.gate_name:
        raise HTTPException(400, "Indica ids o al menos un filtro (status/gate_name)")

    where = ["project_id = :pid"]
    params: dict = {"pid": project_id}
    if body.ids:
        where.append("id = ANY(:ids)")
        params["ids"] = [str(decision_id) for decision_id in body.ids]
    if body.status:
        where.append("status = :status")
        params["status"] = body.status
    if body.gate_name:
        where.append("gate_name = :gate_name")
        params["gate_name"] = body.gate_name

    result = await db.execute(
        text(f"DELETE FROM hitl_decisions WHERE {' AND '.join(where)}"), params
    )
    await db.commit()
    return {"deleted": result.rowcount or 0}


@router.get("/projects/{project_id}/hitl/{gate_name}/detail")
async def get_hitl_detail(
    project_id: UUID,
    gate_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Obtiene la decisión HITL completa (proposal + critic_verdict) para mostrar en el modal."""
    row = await db.execute(
        text(
            "SELECT id, gate_name, proposal, critic_verdict, status, creado_en "
            "FROM hitl_decisions "
            "WHERE project_id = :pid AND gate_name = :gate "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"pid": project_id, "gate": gate_name},
    )
    decision_row = row.fetchone()
    if not decision_row:
        raise HTTPException(404, f"No decision found for gate '{gate_name}'")

    return {
        "id": str(decision_row[0]),
        "gate_name": decision_row[1],
        "proposal": decision_row[2] if isinstance(decision_row[2], dict) else {},
        "critic_verdict": decision_row[3] if isinstance(decision_row[3], dict) else {},
        "status": decision_row[4],
        "created_at": str(decision_row[5]),
    }


@router.get("/projects/{project_id}/hitl/pending")
async def get_pending_decisions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[HitlPendingItem]:
    """Devuelve las decisiones HITL pendientes para un proyecto."""
    rows = await db.execute(
        text(
            "SELECT id, gate_name, proposal, critic_verdict, creado_en "
            "FROM hitl_decisions "
            "WHERE project_id = :pid AND status = 'pending' "
            "ORDER BY creado_en ASC"
        ),
        {"pid": project_id},
    )
    results = []
    for row in rows:
        proposal = row[2] if isinstance(row[2], dict) else {}
        critic = row[3] if isinstance(row[3], dict) else {}
        # Extract summary from first candidate's statement or overall rationale
        candidates = proposal.get("candidates", [])
        if candidates and isinstance(candidates, list):
            proposal_summary = (
                candidates[0].get("statement", "")
                if isinstance(candidates[0], dict)
                else str(candidates[0])
            )
        elif (
            proposal.get("convergence_assessment")
            or proposal.get("converging") is not None
        ):
            # Gate de convergencia (lote de extracción): no trae `candidates`,
            # así que sin esta rama el resumen quedaba en "(no candidates)".
            docs_processed = proposal.get("docs_processed")
            total_docs = proposal.get("total_docs")
            parts = [str(proposal.get("convergence_assessment") or "")]
            if proposal.get("recommendation"):
                parts.append(str(proposal["recommendation"]))
            if docs_processed is not None and total_docs is not None:
                parts.append(f"{docs_processed}/{total_docs} docs")
            proposal_summary = " · ".join(p for p in parts if p)
        else:
            # `rationale: null` en el JSONB hacía `None[:200]` → 500 en TODO el
            # listado, que ahora se pollea cada segundo durante el lote.
            proposal_summary = str(proposal.get("rationale") or "")[:200]
        # Derive verdict from observations: count strong/weak observations
        observations = critic.get("observations", [])
        if not observations:
            critic_verdict = "NO_FEEDBACK"
        else:
            strong = sum(1 for o in observations if o.get("is_strong"))
            critic_verdict = f"{strong}/{len(observations)} strong"
        results.append(
            HitlPendingItem(
                id=row[0],
                gate_name=row[1],
                proposal_summary=proposal_summary[:200]
                if proposal_summary
                else "(no candidates)",
                critic_verdict=critic_verdict,
                created_at=row[4],
            )
        )
    return results


@router.post(
    "/projects/{project_id}/hitl/{gate_name}/decide",
    response_model=HitlDecisionResponse,
)
async def decide_hitl(
    project_id: UUID,
    gate_name: str,
    body: HitlDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    El investigador decide sobre una propuesta en un gate HITL.

    - ACCEPT → la decisión se marca como aceptada. El coordinator
      (cuando exista) detectará el cambio y avanzará el pipeline.
    - MODIFY → se guarda el feedback. El coordinator re-ejecutará
      el proposer con las instrucciones del investigador.
    - REJECT → se archiva la decisión con nota metodológica.
    """
    # 1. Buscar la decisión pendiente más reciente para este gate
    row = await db.execute(
        text(
            "SELECT id FROM hitl_decisions "
            "WHERE project_id = :pid AND gate_name = :gate AND status = 'pending' "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"pid": project_id, "gate": gate_name},
    )
    decision_row = row.fetchone()
    if not decision_row:
        raise HTTPException(404, f"No pending decision for gate '{gate_name}'")

    decision_id = decision_row[0]

    # 2. Actualizar la decisión
    new_status = (
        "accepted"
        if body.decision == "accept"
        else "modified"
        if body.decision == "modify"
        else "rejected"
    )
    now = _utcnow()

    await db.execute(
        text(
            "UPDATE hitl_decisions SET "
            "status = :status, "
            "researcher_decision = :dec, "
            "researcher_note = :note, "
            "researcher_feedback = :fb, "
            "decided_at = :now "
            "WHERE id = :did"
        ),
        {
            "status": new_status,
            "dec": body.decision,
            "note": body.note,
            "fb": body.feedback,
            "now": now,
            "did": decision_id,
        },
    )
    await db.commit()

    # 3. Re-disparar coordinator para continuar el pipeline
    # Los gates de convergencia son informativos: no gobiernan la fase
    # selectiva, así que decidir sobre ellos no debe arrancar el coordinator.
    _ADVISORY_GATES = {"pattern_convergence"}
    if body.decision in ("accept", "modify") and gate_name not in _ADVISORY_GATES:
        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "selective_coding_coordinator",
                args=[str(project_id)],
                queue="heavy",
            )
            logger.info(
                "Coordinator re-dispatched for project=%s after %s decision",
                project_id,
                body.decision,
            )
        except Exception as e:
            logger.warning("Failed to re-dispatch coordinator: %s", e)

    logger.info(
        "HITL decision: gate=%s decision=%s by user=%s",
        gate_name,
        body.decision,
        current_user.id,
    )

    return HitlDecisionResponse(
        id=decision_id,
        project_id=project_id,
        gate_name=gate_name,
        status=new_status,
        researcher_decision=body.decision,
        researcher_note=body.note,
        decided_at=now,
    )


@router.post("/projects/{project_id}/hitl/reset")
async def reset_hitl_decisions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Limpia todas las decisiones HITL pendientes de un proyecto."""
    from sqlalchemy import text

    await db.execute(
        text(
            "DELETE FROM hitl_decisions WHERE project_id = :pid AND status = 'pending'"
        ),
        {"pid": project_id},
    )
    await db.commit()
    return {"status": "ok"}
