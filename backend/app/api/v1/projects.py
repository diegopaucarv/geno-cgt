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
