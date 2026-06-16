"""T15–T17 — API de elaboración: relaciones, ghosts, renombres, ecosistema, recomendaciones."""

from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["elaboration"])

# ═══════════════════════════════════════════════════════════════════
# T15 — Elaboration API: relaciones y ghosts
# ═══════════════════════════════════════════════════════════════════


@router.post("/projects/{project_id}/elaboration/relationships")
async def elaborate_relationship(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Iniciar elaboración de una relación conceptual.
    Body: {category_ids, theoretical_code_id, researcher_question}
    """
    # La lógica pesada la ejecuta Celery; este endpoint lanza la tarea.
    from workers.heavy.tasks import app as celery_app

    task = celery_app.send_task(
        "elaborate_relationship",
        args=[
            str(project_id),
            body.get("category_ids", []),
            body.get("theoretical_code_id", ""),
            body.get("researcher_question", ""),
        ],
    )
    return {"status": "processing", "task_id": task.id}


@router.get("/projects/{project_id}/elaboration/relationships")
async def list_relationships(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Listar todas las relaciones elaboradas."""
    rows = await db.execute(
        text(
            "SELECT cr.id, cr.category_ids, cr.theoretical_code_id, "
            "cr.elaboration_status, cr.direction, cr.converging_doc_count, "
            "cr.diverging_doc_count, cr.conceptual_fit, cr.layer, "
            "cr.position_tension, cr.researcher_question, "
            "tc.name as code_name "
            "FROM conceptual_relationships cr "
            "JOIN theoretical_codes tc ON cr.theoretical_code_id = tc.id "
            "WHERE cr.project_id = :pid ORDER BY cr.creado_en DESC"
        ),
        {"pid": project_id},
    )
    return [
        {
            "id": str(r[0]),
            "category_ids": r[1],
            "theoretical_code_id": str(r[2]),
            "elaboration_status": r[3],
            "direction": r[4],
            "converging_docs": r[5],
            "diverging_docs": r[6],
            "conceptual_fit": r[7],
            "layer": r[8],
            "position_tension": r[9],
            "question": r[10],
            "code_name": r[11],
        }
        for r in rows.fetchall()
    ]


@router.get("/projects/{project_id}/elaboration/relationships/{rel_id}")
async def get_relationship(
    project_id: UUID,
    rel_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Ver relación con trazabilidad completa."""
    row = await db.execute(
        text(
            "SELECT cr.*, tc.name as code_name "
            "FROM conceptual_relationships cr "
            "JOIN theoretical_codes tc ON cr.theoretical_code_id = tc.id "
            "WHERE cr.id = :rid AND cr.project_id = :pid"
        ),
        {"rid": rel_id, "pid": project_id},
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(404, "Relación no encontrada")
    return {
        "id": str(r[0]),
        "category_ids": r[2],
        "theoretical_code_name": r[18],
        "elaboration_status": r[4],
        "direction": r[5],
        "converging_docs": r[7],
        "diverging_docs": r[9],
        "conceptual_fit": r[12],
        "layer": r[13],
        "position_tension": r[14],
        "question": r[3],
        "divergence_resolution": r[10],
    }


@router.put("/projects/{project_id}/elaboration/relationships/{rel_id}/diverge")
async def resolve_divergence(
    project_id: UUID,
    rel_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Expandir relación con dato divergente."""
    resolution = body.get("divergence_resolution", "")
    await db.execute(
        text(
            "UPDATE conceptual_relationships SET "
            "divergence_resolution = :res, elaboration_status = 'expanded', "
            "position_tension = 0.0 WHERE id = :rid AND project_id = :pid"
        ),
        {"res": resolution, "rid": rel_id, "pid": project_id},
    )
    await db.commit()
    return {"status": "expanded"}


@router.get("/projects/{project_id}/elaboration/ghosts")
async def list_ghosts(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Listar ghost-blobs pendientes (hipótesis no conectadas)."""
    rows = await db.execute(
        text(
            "SELECT m.id, m.contenido, m.tipo FROM memos m "
            "WHERE m.proyecto_id = :pid AND m.tipo = 'HIPOTESIS' "
            "AND m.id NOT IN ("
            "  SELECT memo_id FROM elaboration_memos "
            "  WHERE memo_id IS NOT NULL AND project_id = :pid2"
            ") LIMIT 20"
        ),
        {"pid": project_id, "pid2": project_id},
    )
    return [
        {"id": str(r[0]), "content": r[1][:300], "type": r[2]} for r in rows.fetchall()
    ]


@router.post("/projects/{project_id}/elaboration/ghosts/{memo_id}/absorb")
async def absorb_ghost(
    project_id: UUID,
    memo_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Absorber ghost-blob en categoría. Body: {target_category_id}"""
    from workers.heavy.tasks import app as celery_app

    task = celery_app.send_task(
        "absorb_ghost",
        args=[str(project_id), str(memo_id), body.get("target_category_id", "")],
    )
    return {"status": "processing", "task_id": task.id}


# ═══════════════════════════════════════════════════════════════════
# T16 — Rename API
# ═══════════════════════════════════════════════════════════════════


@router.get("/projects/{project_id}/elaboration/rename-suggestions/{category_id}")
async def get_rename_suggestions(
    project_id: UUID,
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Sugerencias de renombre para una categoría."""
    from app.services.rename_detector import (
        get_rename_candidates,
        should_suggest_rename,
    )

    needs_rename = should_suggest_rename(category_id, db)
    if not needs_rename:
        return {"needs_rename": False, "suggestions": []}

    # Para invocar el LLM necesitamos llm_client — delegamos a Celery
    from workers.heavy.tasks import app as celery_app

    task = celery_app.send_task(
        "suggest_rename", args=[str(project_id), str(category_id)]
    )
    return {"needs_rename": True, "status": "processing", "task_id": task.id}


@router.post("/projects/{project_id}/elaboration/rename")
async def apply_rename(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Aplicar renombre. Body: {category_id, new_name, rationale}"""
    from app.services.rename_detector import apply_rename as do_rename

    category_id = UUID(body.get("category_id", ""))
    new_name = body.get("new_name", "")
    rationale = body.get("rationale", "")

    if not new_name:
        raise HTTPException(400, "new_name es requerido")

    do_rename(category_id, new_name, rationale, db)
    await db.commit()
    return {"status": "renamed", "category_id": str(category_id), "new_name": new_name}


@router.get(
    "/projects/{project_id}/elaboration/categories/{category_id}/definition-history"
)
async def get_definition_history(
    project_id: UUID,
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Historial completo de definiciones (timeline de evolución)."""
    rows = await db.execute(
        text(
            "SELECT version, name_at_version, definition_at_version, "
            "trigger, trigger_detail, creado_en "
            "FROM category_definition_versions "
            "WHERE category_id = :cid AND project_id = :pid "
            "ORDER BY version"
        ),
        {"cid": category_id, "pid": project_id},
    )
    return [
        {
            "version": r[0],
            "name": r[1],
            "definition": r[2],
            "trigger": r[3],
            "detail": r[4],
            "created_at": str(r[5]),
        }
        for r in rows.fetchall()
    ]


# ═══════════════════════════════════════════════════════════════════
# T17 — Ecosystem & Recommendations API
# ═══════════════════════════════════════════════════════════════════


@router.get("/projects/{project_id}/elaboration/ecosystem")
async def get_ecosystem(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Estado completo del ecosistema (blobs, tendriles, ghosts, layout)."""
    layout = await db.execute(
        text("SELECT * FROM ecosystem_layouts WHERE project_id = :pid"),
        {"pid": project_id},
    )
    lay = layout.fetchone()

    return {
        "blobs": await _get_blobs(db, project_id),
        "tendrils": await _get_tendrils(db, project_id),
        "layout": {
            "blob_positions": lay[3] if lay else {},
            "ghost_positions": lay[4] if lay else {},
            "fog_zones": lay[5] if lay else {},
            "physics_params": lay[6] if lay else {},
        }
        if lay
        else None,
    }


@router.put("/projects/{project_id}/elaboration/ecosystem/layout")
async def save_ecosystem_layout(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Guardar posiciones del ecosistema (persiste tras drag)."""
    existing = await db.execute(
        text("SELECT id, version FROM ecosystem_layouts WHERE project_id = :pid"),
        {"pid": project_id},
    )
    row = existing.fetchone()

    if row:
        new_version = (row[1] or 0) + 1
        await db.execute(
            text(
                "UPDATE ecosystem_layouts SET version = :v, "
                "blob_positions = :bp, ghost_positions = :gp, "
                "fog_zones = :fz, physics_params = :pp "
                "WHERE id = :eid"
            ),
            {
                "v": new_version,
                "bp": body.get("blob_positions", {}),
                "gp": body.get("ghost_positions", {}),
                "fz": body.get("fog_zones", {}),
                "pp": body.get("physics_params", {}),
                "eid": row[0],
            },
        )
    else:
        await db.execute(
            text(
                "INSERT INTO ecosystem_layouts "
                "(id, project_id, version, blob_positions, ghost_positions, "
                "fog_zones, physics_params) "
                "VALUES (gen_random_uuid(), :pid, 1, :bp, :gp, :fz, :pp)"
            ),
            {
                "pid": project_id,
                "bp": body.get("blob_positions", {}),
                "gp": body.get("ghost_positions", {}),
                "fz": body.get("fog_zones", {}),
                "pp": body.get("physics_params", {}),
            },
        )
    await db.commit()
    return {"status": "saved"}


@router.get("/projects/{project_id}/elaboration/recommendations")
async def get_recommendations(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Guía de elaboración (sugerencias rankeadas)."""
    from app.services.recommendation_engine import RecommendationEngine

    engine = RecommendationEngine(db)
    recs = engine.generate_recommendations(project_id)
    return [
        {
            "category": r.category,
            "title": r.title,
            "description": r.description,
            "action_type": r.action_type,
            "category_ids": r.category_ids,
            "suggested_code": r.suggested_code,
            "impact_score": r.impact_score,
        }
        for r in recs
    ]


@router.get("/projects/{project_id}/elaboration/model")
async def get_theoretical_model(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Grafo completo de relaciones + gaps + cobertura de capas."""
    return {
        "relationships": await _get_tendrils(db, project_id),
        "orphan_categories": await _get_orphans(db, project_id),
        "layers_coverage": await _get_layer_coverage(db, project_id),
    }


# ── Helpers ─────────────────────────────────────────────────────────


async def _get_blobs(db, project_id: UUID) -> list[dict]:
    rows = await db.execute(
        text(
            "SELECT id, nombre, definicion, version, "
            "puntaje_relevancia, estado_saturacion, es_central "
            "FROM categorias WHERE proyecto_id = :pid ORDER BY puntaje_relevancia DESC"
        ),
        {"pid": project_id},
    )
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "definition": r[2],
            "version": r[3],
            "relevance": r[4],
            "saturation": r[5],
            "is_core": r[6],
        }
        for r in rows.fetchall()
    ]


async def _get_tendrils(db, project_id: UUID) -> list[dict]:
    rows = await db.execute(
        text(
            "SELECT id, category_ids, theoretical_code_id, elaboration_status, "
            "converging_doc_count, diverging_doc_count, conceptual_fit, "
            "layer, position_tension "
            "FROM conceptual_relationships WHERE project_id = :pid"
        ),
        {"pid": project_id},
    )
    return [
        {
            "id": str(r[0]),
            "category_ids": r[1],
            "code_id": str(r[2]),
            "status": r[3],
            "converging": r[4],
            "diverging": r[5],
            "fit": r[6],
            "layer": r[7],
            "tension": r[8],
        }
        for r in rows.fetchall()
    ]


async def _get_orphans(db, project_id: UUID) -> list[dict]:
    rows = await db.execute(
        text(
            "SELECT c.id, c.nombre FROM categorias c "
            "WHERE c.proyecto_id = :pid AND c.id NOT IN ("
            "  SELECT DISTINCT jsonb_array_elements_text(cr.category_ids)::uuid "
            "  FROM conceptual_relationships cr WHERE cr.project_id = :pid2"
            ")"
        ),
        {"pid": project_id, "pid2": project_id},
    )
    return [{"id": str(r[0]), "name": r[1]} for r in rows.fetchall()]


async def _get_layer_coverage(db, project_id: UUID) -> dict:
    rows = await db.execute(
        text(
            "SELECT DISTINCT layer FROM conceptual_relationships "
            "WHERE project_id = :pid AND layer IS NOT NULL"
        ),
        {"pid": project_id},
    )
    covered = {r[0] for r in rows.fetchall()}
    return {
        "covered": list(covered),
        "missing": list(
            {
                "process",
                "conditions",
                "variation",
                "structure",
                "consequences",
                "action",
                "fusion",
            }
            - covered
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# T20 — P5: HITL Modification Agent
# ═══════════════════════════════════════════════════════════════════


@router.post("/projects/{project_id}/modification/request")
async def request_modification(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """P5 Fases 1-4: Solicitar modificacion de un memo con verificacion agencial.

    Body esperado:
    {
        "agent_id": "b2b_generate_codes",
        "user_request": "Creo que el gerundio no captura bien el patron...",
        "current_memo": {"code_name": "...", "definition": "..."},
        "memo_id": "uuid-del-output",
        "original_prompt": "b2b_generate_codes.md"  (opcional)
    }

    Retorna:
    {
        "valid_request": true/false,
        "filter_reason": "...",
        "suggested_questions": [...],
        "recommended": true/false/null,
        "recommendation_reason": "...",
        "recommendation_confidence": 0.85,
        "evidence_sufficient": true/false,
        "modified_memo": {...},
        "impact_summary": "...",
        "missing_evidence": "..."
    }
    """
    import sys as _sys

    _sys.path.insert(0, "/app")
    from workers.heavy.llm_client import LLMClient

    _llm = LLMClient()

    from app.agents.hitl_modifier import HITLModificationAgent

    agent = HITLModificationAgent(_llm)

    result = agent.process_request(
        agent_id=body.get("agent_id", ""),
        user_request=body.get("user_request", ""),
        current_memo=body.get("current_memo", {}),
        proyecto_id=str(project_id),
        original_prompt=body.get("original_prompt", ""),
    )

    return result.to_response()


@router.post("/projects/{project_id}/modification/apply")
async def apply_modification(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """P5 Fase 5: Aplicar una modificacion confirmada por el usuario.

    Body esperado:
    {
        "agent_id": "b2b_generate_codes",
        "memo_id": "uuid-del-output-a-modificar",
        "new_content": {"code_name": "...", "definition": "..."},
        "agent_output_id": "uuid-del-agent-output"  (opcional, para log)
    }

    Retorna:
    {
        "status": "applied",
        "wiped_tables": ["codigos_segmento", "code_document_summaries"],
        "restart_from": "batch_code",
        "invalidated_outputs": ["B2.5 grounding", "B3 hypotheses"]
    }
    """
    import sys as _sys

    _sys.path.insert(0, "/app")
    from workers.heavy.llm_client import LLMClient

    _llm = LLMClient()

    from app.agents.hitl_modifier import HITLModificationAgent

    agent = HITLModificationAgent(_llm)

    result = agent.apply_modification(
        agent_id=body.get("agent_id", ""),
        memo_id=body.get("memo_id", ""),
        new_content=body.get("new_content", {}),
        proyecto_id=str(project_id),
    )

    # Si se aplico, registrar en output_modifications
    if result.get("status") == "applied":
        try:
            from app.models.domain.agent_outputs import OutputModification
            from database import SessionLocal
            import json as _json
            from datetime import datetime, timezone

            s = SessionLocal()
            try:
                mod = OutputModification(
                    proyecto_id=project_id,
                    modified_by=current_user.id,
                    agent_output_id=body.get("agent_output_id"),
                    user_request=body.get("user_request", ""),
                    recommended=body.get("recommended"),
                    recommendation_reason=body.get("recommendation_reason", ""),
                    recommendation_confidence=body.get("recommendation_confidence"),
                    original_content=body.get("current_memo", {}),
                    modified_content=body.get("new_content", {}),
                    evidence_collected=body.get("evidence_collected", []),
                    verification_plan=body.get("verification_plan"),
                    applied=True,
                    applied_at=datetime.now(timezone.utc).isoformat(),
                    wiped_tables=result.get("wiped_tables", []),
                    pipeline_restarted_from=result.get("restart_from", ""),
                )
                s.add(mod)
                s.commit()
            finally:
                s.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to log OutputModification: %s", e
            )

    return result
