import asyncio
import json
import logging
from uuid import UUID

from app.db.database import get_db
from app.models.domain.category import Categoria
from app.models.domain.document import Documento
from app.models.domain.project import Proyecto
from app.models.domain.user import Usuario
from app.schemas import ProjectCreate, ProjectResponse
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


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

    current = proyecto.population_assumption or {}
    current.update(update_data)
    proyecto.population_assumption = current
    await db.commit()
    await db.refresh(proyecto)
    return {
        "status": "updated",
        "population_assumption": proyecto.population_assumption,
        "supuesto_poblacional": proyecto.supuesto_poblacional,
    }
