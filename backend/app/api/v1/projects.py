import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.database import get_db
from app.models.domain.category import Categoria
from app.models.domain.document import Documento
from app.models.domain.project import Proyecto
from app.models.domain.project_config_history import ProjectConfigHistory
from app.models.domain.user import Usuario
from app.schemas import ProjectCreate, ProjectResponse
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

# ── Política de mutación por defecto ──────────────────────────────────

DEFAULT_MUTATION_POLICY: dict[str, str] = {
    "population_description": "suggest",
    "temporal_frame": "suggest",
    "spatial_frame": "suggest",
    "object_of_study": "require_approval",
    "pattern_of_interest": "require_approval",
    "coding_styles": "suggest",
    "gerundio_esperado": "suggest",
    "segmentation_config": "auto",
}

VALID_MUTATION_LEVELS = {"auto", "suggest", "require_approval", "locked"}


# ── Helpers ───────────────────────────────────────────────────────────


async def _record_config_change(
    db: AsyncSession,
    project_id: UUID,
    *,
    field: str,
    old_value: str | None,
    new_value: str,
    triggered_by: str = "user",
    agent_run_id: str | None = None,
    mutation_level: str | None = None,
    rationale: str | None = None,
    confidence: float | None = None,
    context: dict | None = None,
) -> ProjectConfigHistory:
    """Registra un cambio de configuración en el historial inmutable."""
    entry = ProjectConfigHistory(
        proyecto_id=project_id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        triggered_by=triggered_by,
        agent_run_id=agent_run_id,
        mutation_level=mutation_level,
        rationale=rationale,
        confidence=confidence,
        context=context,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Proyecto).where(Proyecto.creador_id == current_user.id)
    )
    return result.scalars().all()


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    proyecto = Proyecto(**body.model_dump(), creador_id=current_user.id)
    db.add(proyecto)
    await db.commit()
    await db.refresh(proyecto)

    # ── F1.2: population_generalizer (FLASH, single-shot) ──
    raw_pop = body.supuesto_poblacional
    if raw_pop and raw_pop.strip():
        try:
            from app.core.llm_config import get_model_for_prompt
            from app.core.together_client import TogetherLLM
            from app.prompts import PROMPT_REGISTRY

            template = PROMPT_REGISTRY["population_generalizer"]
            messages = template.build_messages(raw_population_description=raw_pop)
            model = get_model_for_prompt("population_generalizer")

            llm = TogetherLLM()
            response = await asyncio.to_thread(
                llm.chat,
                model=model,
                messages=messages,
                response_format=template.output_schema,
            )

            content = json.loads(response.get("content", "{}"))

            # Merge with any existing population_assumption
            current = proyecto.population_assumption or {}
            current["population_description"] = raw_pop
            current["generalized_population"] = content.get(
                "generalized_population", ""
            )
            current["spatial_frame"] = content.get("spatial_frame", "sparse")
            current["temporal_frame"] = content.get(
                "temporal_frame", "present_continuous"
            )
            current["generalizer_confidence"] = content.get("confidence", 0.5)
            current["generalizer_rationale"] = content.get("rationale", "")
            proyecto.population_assumption = current

            await db.commit()
            await db.refresh(proyecto)
            logger.info(
                "population_generalizer: project=%s spatial=%s temporal=%s",
                proyecto.id,
                current.get("spatial_frame"),
                current.get("temporal_frame"),
            )
        except Exception as e:
            logger.warning(
                "population_generalizer failed for project=%s: %s",
                proyecto.id,
                e,
            )
            # Non-blocking: project is created even if generalizer fails

    return proyecto


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    # Conteos para el dashboard
    doc_count = await db.scalar(
        select(func.count(Documento.id)).where(Documento.proyecto_id == project_id)
    )
    cat_count = await db.scalar(
        select(func.count(Categoria.id)).where(Categoria.proyecto_id == project_id)
    )

    # Devolvemos el proyecto + metadata extra
    return {
        **proyecto.__dict__,
        "num_documentos": doc_count,
        "num_categorias": cat_count,
    }


@router.put("/{project_id}/config/population-assumption")
async def update_population_assumption(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """C04: Configurar population_assumption en Fase 0."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    allowed_keys = {
        "object_of_study",
        "temporal_frame",
        "spatial_frame",
        "population_description",
        "gerundio_esperado",
    }
    update_data = {k: v for k, v in body.items() if k in allowed_keys}

    if not update_data:
        raise HTTPException(
            400, "No se recibieron campos válidos para population_assumption"
        )

    # Record history for each changed key
    current = proyecto.population_assumption or {}
    for key, value in update_data.items():
        old_val = current.get(key)
        await _record_config_change(
            db,
            project_id,
            field=f"population_assumption.{key}",
            old_value=json.dumps(old_val) if old_val is not None else None,
            new_value=json.dumps(value),
            triggered_by="user",
        )

    current.update(update_data)
    proyecto.population_assumption = current
    await db.commit()
    await db.refresh(proyecto)
    return {
        "status": "updated",
        "population_assumption": proyecto.population_assumption,
        "supuesto_poblacional": proyecto.supuesto_poblacional,
    }


# ═══════════════════════════════════════════════════════════════════════
# Config endpoints — lectura y política de mutaciones
# ═══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/config")
async def get_project_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve toda la configuración actual del proyecto."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    policy = proyecto.config_mutation_policy or DEFAULT_MUTATION_POLICY

    return {
        "project_id": str(proyecto.id),
        "nombre": proyecto.nombre,
        "estado": proyecto.estado,
        "ruta_de_codificacion": proyecto.ruta_de_codificacion,
        # ── Configuración epistemológica ──
        "supuesto_poblacional": proyecto.supuesto_poblacional,
        "object_of_study": proyecto.object_of_study,
        "population_assumption": proyecto.population_assumption or {},
        # ── Estilos de codificación ──
        "coding_style_instruction": proyecto.coding_style_instruction,
        # ── Segmentación ──
        "config_segmentacion": proyecto.config_segmentacion or {},
        # ── Política de mutaciones ──
        "mutation_policy": policy,
        # ── Sugerencias pendientes (cambios propuestos por agentes, nivel "suggest") ──
        "pending_suggestions": await _get_pending_suggestions(db, project_id),
    }


@router.get("/{project_id}/config/history")
async def get_project_config_history(
    project_id: UUID,
    field: str | None = Query(None, description="Filtrar por campo específico"),
    limit: int = Query(50, ge=1, le=200, description="Máximo de entradas"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve el historial de cambios de configuración del proyecto (tipo git log)."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    query = (
        select(ProjectConfigHistory)
        .where(ProjectConfigHistory.proyecto_id == project_id)
        .order_by(ProjectConfigHistory.creado_en.desc())
    )
    if field:
        query = query.where(ProjectConfigHistory.field == field)
    query = query.limit(limit)

    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "project_id": str(project_id),
        "total": len(entries),
        "entries": [
            {
                "id": str(e.id),
                "field": e.field,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "triggered_by": e.triggered_by,
                "agent_run_id": e.agent_run_id,
                "mutation_level": e.mutation_level,
                "rationale": e.rationale,
                "confidence": e.confidence,
                "context": e.context,
                "timestamp": e.creado_en.isoformat() if e.creado_en else None,
            }
            for e in entries
        ],
    }


@router.put("/{project_id}/config/mutation-policy")
async def update_mutation_policy(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza la política de mutaciones automáticas del proyecto.

    Body: {"population_description": "auto", "object_of_study": "require_approval", ...}
    Solo se aceptan claves válidas con niveles válidos.
    """
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    current_policy = proyecto.config_mutation_policy or dict(DEFAULT_MUTATION_POLICY)

    updated = False
    for key, level in body.items():
        if key not in DEFAULT_MUTATION_POLICY:
            continue  # Ignorar claves desconocidas
        if level not in VALID_MUTATION_LEVELS:
            continue  # Ignorar niveles inválidos
        if current_policy.get(key) != level:
            await _record_config_change(
                db,
                project_id,
                field=f"mutation_policy.{key}",
                old_value=current_policy.get(key, "suggest"),
                new_value=level,
                triggered_by="user",
            )
            current_policy[key] = level
            updated = True

    if not updated:
        return {
            "status": "no_changes",
            "message": "No se detectaron cambios en la política",
            "mutation_policy": current_policy,
        }

    proyecto.config_mutation_policy = current_policy
    await db.commit()
    await db.refresh(proyecto)

    return {
        "status": "updated",
        "message": f"Política de mutaciones actualizada",
        "mutation_policy": proyecto.config_mutation_policy,
    }


async def _get_pending_suggestions(db: AsyncSession, project_id: UUID) -> list[dict]:
    """Devuelve sugerencias pendientes de agentes (nivel 'suggest')
    que el investigador aún no ha aceptado/rechazado.

    Por ahora recuperamos las entradas de historial con mutation_level='suggest'
    más recientes para cada campo.
    """
    from sqlalchemy import text as sa_text

    # Obtener la sugerencia más reciente por campo con nivel 'suggest'
    rows = await db.execute(
        sa_text(
            """
            SELECT DISTINCT ON (field)
                id, field, old_value, new_value, triggered_by,
                rationale, confidence, context, creado_en
            FROM project_config_history
            WHERE proyecto_id = :pid
              AND mutation_level = 'suggest'
            ORDER BY field, creado_en DESC
            """
        ),
        {"pid": project_id},
    )

    return [
        {
            "id": str(row[0]),
            "field": row[1],
            "old_value": row[2],
            "new_value": row[3],
            "triggered_by": row[4],
            "rationale": row[5],
            "confidence": row[6],
            "context": row[7],
            "timestamp": row[8].isoformat() if row[8] else None,
        }
        for row in rows
    ]


@router.put("/{project_id}")
async def update_project(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Editar nombre, descripcion poblacional, y config del proyecto."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    updatable = {"nombre", "supuesto_poblacional", "object_of_study"}
    for key, value in body.items():
        if key in updatable and value is not None:
            setattr(proyecto, key, value)

    await db.commit()
    await db.refresh(proyecto)
    return {
        "status": "updated",
        "id": str(proyecto.id),
        "nombre": proyecto.nombre,
        "estado": proyecto.estado,
        "object_of_study": proyecto.object_of_study,
        "supuesto_poblacional": proyecto.supuesto_poblacional,
        "population_assumption": proyecto.population_assumption,
    }


@router.delete("/{project_id}", status_code=200)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina un proyecto y todos sus datos asociados (cascada)."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")
    if str(proyecto.creador_id) != str(current_user.id):
        raise HTTPException(403, "No autorizado")

    nombre = proyecto.nombre
    await db.delete(proyecto)
    await db.commit()
    return {"status": "deleted", "nombre": nombre, "id": str(project_id)}


@router.delete("/{project_id}/documents", status_code=200)
async def delete_all_documents(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina todos los documentos de un proyecto y resetea su estado."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    from sqlalchemy import text as sa_text

    # Contar docs antes de borrar
    count = await db.scalar(
        select(func.count(Documento.id)).where(Documento.proyecto_id == project_id)
    )

    # Borrar en orden: codigos → segmentos → documentos
    await db.execute(
        sa_text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid))"
        ),
        {"pid": project_id},
    )
    await db.execute(
        sa_text(
            "DELETE FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid)"
        ),
        {"pid": project_id},
    )
    await db.execute(
        sa_text("DELETE FROM documentos WHERE proyecto_id = :pid"),
        {"pid": project_id},
    )

    # Resetear estado del proyecto
    proyecto.estado = "collecting"
    await db.commit()

    return {"status": "deleted", "count": count, "project_id": str(project_id)}
