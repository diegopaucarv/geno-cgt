"""Endpoints de memos — creación manual por el investigador y tipos disponibles."""

from __future__ import annotations

import logging
import uuid
from uuid import UUID

from app.core.memo_types import (
    family_to_entity_type,
    get_all_types,
    get_types_for_stage,
)
from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["memos"])


# ── Schemas ──────────────────────────────────────────────────────────────


class CreateMemoRequest(BaseModel):
    tipo: str = Field(..., description="Tipo de entidad: HIPOTESIS, CATEGORIA, etc.")
    contenido: str = Field(..., min_length=1, description="Contenido del memo")
    es_confidencial: bool = Field(False)


# ── GET /available-memo-types ────────────────────────────────────────────


@router.get("/projects/{project_id}/available-memo-types")
async def get_available_memo_types(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Tipos de memo disponibles según la etapa actual del proyecto."""
    row = await db.execute(
        text("SELECT estado FROM proyectos WHERE id = :pid"),
        {"pid": project_id},
    )
    proyecto = row.fetchone()
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    stage = proyecto[0]

    active_run = await db.execute(
        text(
            "SELECT id FROM pipeline_runs "
            "WHERE project_id = :pid AND status = 'running' LIMIT 1"
        ),
        {"pid": project_id},
    )
    is_running = active_run.fetchone() is not None

    available = get_types_for_stage(stage)
    all_types = get_all_types()

    return {
        "stage": stage,
        "pipeline_running": is_running,
        "can_add_memo": not is_running,
        "available_types": available,
        "all_types": all_types,
    }


# ── POST /memos ──────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/memos")
async def create_user_memo(
    project_id: UUID,
    body: CreateMemoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Crea un memo manual. Solo si el pipeline NO está corriendo."""

    # ── 1. Bloquear proyecto y verificar pipeline ──
    async with db.begin():
        row = await db.execute(
            text("SELECT estado FROM proyectos WHERE id = :pid FOR UPDATE"),
            {"pid": project_id},
        )
        proyecto = row.fetchone()
        if not proyecto:
            raise HTTPException(404, "Proyecto no encontrado")

        stage = proyecto[0]

        active_run = await db.execute(
            text(
                "SELECT id FROM pipeline_runs "
                "WHERE project_id = :pid AND status = 'running' "
                "FOR UPDATE LIMIT 1"
            ),
            {"pid": project_id},
        )
        if active_run.fetchone():
            raise HTTPException(
                409,
                "No se pueden añadir entidades mientras el pipeline está ejecutándose. Pausalo primero.",
            )

        # ── 2. Validar tipo permitido en esta etapa ──
        available = get_types_for_stage(stage)
        allowed_keys = [t["key"] for t in available]
        if body.tipo not in allowed_keys:
            raise HTTPException(
                400,
                f"Tipo '{body.tipo}' no disponible en etapa '{stage}'. "
                f"Disponibles: {allowed_keys}",
            )

        # ── 3. Insertar memo ──
        memo_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO memos "
                "(id, proyecto_id, autor_id, tipo, estado, contenido, "
                " es_confidencial, user_created, stage_at_creation) "
                "VALUES (:id, :pid, :uid, :tipo, 'ABIERTO', :contenido, "
                " :conf, true, :stage)"
            ),
            {
                "id": memo_id,
                "pid": project_id,
                "uid": current_user.id,
                "tipo": body.tipo,
                "contenido": body.contenido,
                "conf": body.es_confidencial,
                "stage": stage,
            },
        )

        # ── 4. Efectos secundarios por tipo ──
        if body.tipo == "CATEGORIA":
            nombre = f"[Manual] {body.contenido[:100]}"
            await db.execute(
                text(
                    "INSERT INTO categorias "
                    "(id, proyecto_id, nombre, definicion, estado_saturacion, "
                    " puntaje_relevancia, version, source_memo_id) "
                    "VALUES (gen_random_uuid(), :pid, :nombre, :def, "
                    " 'ABIERTO', 1, 1, :mid)"
                ),
                {
                    "pid": project_id,
                    "nombre": nombre,
                    "def": body.contenido,
                    "mid": memo_id,
                },
            )
            logger.info("Created manual category '%s' from memo %s", nombre, memo_id)

        elif body.tipo == "TEORICO":
            nombre = f"[User] {body.contenido[:100]}"
            await db.execute(
                text(
                    "INSERT INTO theoretical_codes "
                    "(id, project_id, name, family, description, glaserian, "
                    " user_defined, layer) "
                    "VALUES (gen_random_uuid(), :pid, :name, 'custom', :desc, "
                    " false, true, 'custom')"
                ),
                {"pid": project_id, "name": nombre, "desc": body.contenido},
            )
            logger.info(
                "Created user theoretical code '%s' from memo %s", nombre, memo_id
            )

    return {
        "id": str(memo_id),
        "tipo": body.tipo,
        "stage": stage,
        "user_created": True,
    }


# ── GET /stale-user-entities ─────────────────────────────────────────────


@router.get("/projects/{project_id}/stale-user-entities")
async def get_stale_user_entities(
    project_id: UUID,
    current_stage: str = Query(..., description="Etapa actual del proyecto"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Detecta memos de usuario creados en etapas anteriores a current_stage."""
    from app.core.memo_types import STAGE_ORDER

    try:
        current_idx = STAGE_ORDER.index(current_stage)
    except ValueError:
        current_idx = 0

    stale = await db.execute(
        text(
            "SELECT stage_at_creation, COUNT(*) FROM memos "
            "WHERE proyecto_id = :pid AND user_created = true "
            "AND stage_at_creation != :stage "
            "GROUP BY stage_at_creation"
        ),
        {"pid": project_id, "stage": current_stage},
    )

    affected_stages: list[str] = []
    total = 0
    for row in stale.fetchall():
        s = row[0]
        c = row[1]
        try:
            if STAGE_ORDER.index(s) < current_idx:
                affected_stages.append(s)
                total += c
        except ValueError:
            pass

    return {
        "count": total,
        "affected_stages": affected_stages,
        "earliest_stage": affected_stages[0] if affected_stages else None,
    }


# ── GET /entity-type-colors (para el frontend) ────────────────────────────


@router.get("/entity-type-colors")
async def get_entity_type_colors():
    """Devuelve colores y metadata de todos los tipos de entidad para los filtros/badges del frontend."""
    from app.core.memo_types import get_all_types

    return {"types": get_all_types()}


# ── DELETE /memos ────────────────────────────────────────────────────────


@router.delete("/projects/{project_id}/memos")
async def delete_memos_by_type(
    project_id: UUID,
    tipo: str = Query(
        "all", description="Tipo de entidad a eliminar. 'all' = todos los user_created."
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina todos los memos user_created de un tipo especifico, o todos si tipo='all'."""
    active_run = await db.execute(
        text(
            "SELECT id FROM pipeline_runs WHERE project_id = :pid AND status = 'running' LIMIT 1"
        ),
        {"pid": project_id},
    )
    if active_run.fetchone():
        raise HTTPException(409, "Pausa el pipeline antes de eliminar entidades.")

    tipo_filter = "" if tipo == "all" else "AND tipo = :tipo"
    params: dict = {"pid": project_id}
    if tipo != "all":
        params["tipo"] = tipo

    count_row = await db.execute(
        text(
            f"SELECT COUNT(*) FROM memos "
            f"WHERE proyecto_id = :pid {tipo_filter} AND user_created = true"
        ),
        params,
    )
    count = count_row.scalar() or 0

    label = "todos los tipos" if tipo == "all" else f"tipo '{tipo}'"
    if count == 0:
        return {"deleted": 0, "message": f"No hay memos de {label}"}

    # Eliminar entidades derivadas
    if tipo == "all" or tipo == "CATEGORIA":
        cat_filter = "" if tipo == "all" else "AND m.tipo = :tipo"
        await db.execute(
            text(
                f"DELETE FROM categorias WHERE proyecto_id = :pid "
                f"AND source_memo_id IN (SELECT m.id FROM memos m WHERE m.proyecto_id = :pid2 {cat_filter} AND m.user_created = true)"
            ),
            params | {"pid2": project_id},
        )
    if tipo == "all" or tipo == "TEORICO":
        await db.execute(
            text(
                "DELETE FROM theoretical_codes WHERE proyecto_id = :pid "
                "AND user_defined = true AND name LIKE '[User]%'"
            ),
            {"pid": project_id},
        )

    await db.execute(
        text(
            f"DELETE FROM memos "
            f"WHERE proyecto_id = :pid {tipo_filter} AND user_created = true"
        ),
        params,
    )
    await db.commit()

    logger.info("Deleted %d user memos of %s from project %s", count, label, project_id)
    return {"deleted": count, "tipo": tipo}
