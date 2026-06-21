"""Endpoints de memos — creación manual por el investigador y tipos disponibles."""

from __future__ import annotations

import json
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


def _to_jsonb(value: dict | None) -> str | None:
    """Serializa un dict a cadena JSON para columnas JSONB de PostgreSQL."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


# ── Schemas ──────────────────────────────────────────────────────────────


class CreateMemoRequest(BaseModel):
    tipo: str = Field(..., description="Tipo de entidad: HIPOTESIS, CATEGORIA, etc.")
    contenido: str = Field(..., min_length=1, description="Contenido del memo")
    es_confidencial: bool = Field(False)
    structured_fields: dict | None = Field(
        None, description="Campos estructurados según el tipo de memo"
    )


class PatchMemoRequest(BaseModel):
    contenido: str | None = Field(
        None, min_length=1, description="Nuevo contenido del memo"
    )
    es_confidencial: bool | None = Field(None)
    tipo: str | None = Field(
        None, description="Cambiar tipo de entidad (no propaga a entidades derivadas)"
    )


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

    # ── FIX 5: Two-level gating — check which required agents have run ──
    required_agents = list(
        {t["requires_agent"] for t in available if t.get("requires_agent")}
    )
    if required_agents:
        agent_rows = await db.execute(
            text(
                "SELECT DISTINCT agent_id FROM agent_loop_logs "
                "WHERE proyecto_id = :pid AND agent_id = ANY(:agent_ids::text[])"
            ),
            {"pid": project_id, "agent_ids": required_agents},
        )
        completed = {row[0] for row in agent_rows.fetchall()}

        for t in available:
            ra = t.get("requires_agent")
            if ra:
                t["agent_status"] = "completed" if ra in completed else "not_run"

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
                " es_confidencial, user_created, stage_at_creation, structured_fields) "
                "VALUES (:id, :pid, :uid, :tipo, 'ABIERTO', :contenido, "
                " :conf, true, :stage, :sf)"
            ),
            {
                "id": memo_id,
                "pid": project_id,
                "uid": current_user.id,
                "tipo": body.tipo,
                "contenido": body.contenido,
                "conf": body.es_confidencial,
                "stage": stage,
                "sf": _to_jsonb(body.structured_fields),
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
            sf = body.structured_fields or {}
            family = sf.get("family", "custom")
            layer = sf.get("layer", "custom")
            viz_hint = sf.get("visualization_hint", "")
            await db.execute(
                text(
                    "INSERT INTO theoretical_codes "
                    "(id, project_id, name, family, description, glaserian, "
                    " user_defined, layer, visualization_hint, source_memo_id) "
                    "VALUES (gen_random_uuid(), :pid, :name, :family, :desc, "
                    " false, true, :layer, :viz, :mid)"
                ),
                {
                    "pid": project_id,
                    "name": nombre,
                    "family": family,
                    "desc": body.contenido,
                    "layer": layer,
                    "viz": viz_hint,
                    "mid": memo_id,
                },
            )
            logger.info(
                "Created user theoretical code '%s' (family=%s, layer=%s) from memo %s",
                nombre,
                family,
                layer,
                memo_id,
            )

    return {
        "id": str(memo_id),
        "tipo": body.tipo,
        "stage": stage,
        "user_created": True,
    }


# ── PATCH /memos/{memo_id} ───────────────────────────────────────────────


@router.patch("/projects/{project_id}/memos/{memo_id}")
async def patch_user_memo(
    project_id: UUID,
    memo_id: UUID,
    body: PatchMemoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza un memo manual y sincroniza las entidades vinculadas.

    Si el memo es fuente de una categoría (vía source_memo_id),
    propaga cambios de contenido a nombre/definición de la categoría.
    Si el memo es fuente de un código teórico, propaga a name/description.
    """

    async with db.begin():
        # ── 1. Verificar que el memo existe y pertenece al proyecto ──
        memo_row = await db.execute(
            text(
                "SELECT id, tipo, contenido, user_created FROM memos "
                "WHERE id = :mid AND proyecto_id = :pid FOR UPDATE"
            ),
            {"mid": memo_id, "pid": project_id},
        )
        memo = memo_row.fetchone()
        if not memo:
            raise HTTPException(404, "Memo no encontrado en este proyecto")

        if not memo[3]:  # user_created
            raise HTTPException(
                400,
                "Solo se pueden editar memos creados manualmente. "
                "Los memos generados por agentes no son editables directamente.",
            )

        # ── 2. Construir SET clauses ──
        sets: list[str] = []
        params: dict = {"mid": memo_id, "pid": project_id}

        if body.contenido is not None:
            sets.append("contenido = :contenido")
            params["contenido"] = body.contenido
        if body.es_confidencial is not None:
            sets.append("es_confidencial = :conf")
            params["conf"] = body.es_confidencial
        if body.tipo is not None:
            proyecto_row = await db.execute(
                text("SELECT estado FROM proyectos WHERE id = :pid"),
                {"pid": project_id},
            )
            stage = proyecto_row.scalar()
            if not stage:
                raise HTTPException(404, "Proyecto no encontrado")
            available = get_types_for_stage(stage)
            allowed_keys = [t["key"] for t in available]
            if body.tipo not in allowed_keys:
                raise HTTPException(
                    400,
                    f"Tipo '{body.tipo}' no disponible en etapa '{stage}'.",
                )
            sets.append("tipo = :tipo")
            params["tipo"] = body.tipo

        if not sets:
            raise HTTPException(400, "No fields to update")

        sets.append("version = version + 1")

        await db.execute(
            text(
                f"UPDATE memos SET {', '.join(sets)} WHERE id = :mid AND proyecto_id = :pid"
            ),
            params,
        )

        new_content = body.contenido if body.contenido is not None else memo[2]
        memo_tipo = body.tipo if body.tipo is not None else memo[1]

        # ── 3. Sincronizar categorías vinculadas vía source_memo_id ──
        linked_cats = await db.execute(
            text("SELECT id FROM categorias WHERE source_memo_id = :mid"),
            {"mid": memo_id},
        )
        for (cat_id,) in linked_cats.fetchall():
            nombre = f"[Manual] {new_content[:100]}"
            await db.execute(
                text(
                    "UPDATE categorias SET nombre = :nombre, definicion = :def "
                    "WHERE id = :cid"
                ),
                {"nombre": nombre, "def": new_content, "cid": cat_id},
            )
            logger.info("Synced category %s from memo %s update", cat_id, memo_id)

        # ── 4. Sincronizar theoretical_codes vinculados vía source_memo_id ──
        if memo_tipo == "TEORICO":
            linked_tcs = await db.execute(
                text(
                    "SELECT id FROM theoretical_codes "
                    "WHERE source_memo_id = :mid AND user_defined = true"
                ),
                {"mid": memo_id},
            )
            for (tc_id,) in linked_tcs.fetchall():
                tc_name = f"[User] {new_content[:100]}"
                await db.execute(
                    text(
                        "UPDATE theoretical_codes SET name = :name, description = :desc "
                        "WHERE id = :tid"
                    ),
                    {"name": tc_name, "desc": new_content, "tid": tc_id},
                )
                logger.info(
                    "Synced theoretical_code %s from memo %s update", tc_id, memo_id
                )

    return {"status": "updated", "id": str(memo_id)}


# ── DELETE /memos/{memo_id} ──────────────────────────────────────────────


@router.delete("/projects/{project_id}/memos/{memo_id}")
async def delete_user_memo(
    project_id: UUID,
    memo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina un memo manual y maneja las entidades vinculadas.

    Las categorías vinculadas se marcan como huérfanas (source_memo_id = NULL)
    en vez de eliminarlas, preservando el trabajo de codificación.
    Los códigos teóricos vinculados se marcan como huérfanos igualmente.
    """

    async with db.begin():
        # ── 1. Verificar que el memo existe y es editable ──
        memo_row = await db.execute(
            text(
                "SELECT id, tipo FROM memos "
                "WHERE id = :mid AND proyecto_id = :pid AND user_created = true "
                "FOR UPDATE"
            ),
            {"mid": memo_id, "pid": project_id},
        )
        memo = memo_row.fetchone()
        if not memo:
            raise HTTPException(
                404,
                "Memo no encontrado o no es un memo manual editable",
            )

        memo_tipo = memo[1]

        orphaned_cat_ids: list[str] = []
        orphaned_tc_ids: list[str] = []

        # ── 2. Marcar categorías huérfanas (no eliminarlas) ──
        orphaned_cats = await db.execute(
            text(
                "UPDATE categorias SET source_memo_id = NULL "
                "WHERE source_memo_id = :mid "
                "RETURNING id"
            ),
            {"mid": memo_id},
        )
        orphaned_cat_ids = [row[0] for row in orphaned_cats.fetchall()]
        if orphaned_cat_ids:
            logger.info(
                "Orphaned %d categorias from memo %s: %s",
                len(orphaned_cat_ids),
                memo_id,
                orphaned_cat_ids,
            )

        # ── 3. Marcar theoretical_codes huérfanos ──
        if memo_tipo == "TEORICO":
            orphaned_tcs = await db.execute(
                text(
                    "UPDATE theoretical_codes SET source_memo_id = NULL "
                    "WHERE source_memo_id = :mid AND user_defined = true "
                    "RETURNING id"
                ),
                {"mid": memo_id},
            )
            orphaned_tc_ids = [row[0] for row in orphaned_tcs.fetchall()]
            if orphaned_tc_ids:
                logger.info(
                    "Orphaned %d theoretical_codes from memo %s: %s",
                    len(orphaned_tc_ids),
                    memo_id,
                    orphaned_tc_ids,
                )

        # ── 4. Eliminar el memo ──
        await db.execute(
            text("DELETE FROM memos WHERE id = :mid AND proyecto_id = :pid"),
            {"mid": memo_id, "pid": project_id},
        )

    return {
        "status": "deleted",
        "id": str(memo_id),
        "orphaned_categorias": len(orphaned_cat_ids) if memo_tipo == "CATEGORIA" else 0,
        "orphaned_theoretical_codes": len(orphaned_tc_ids)
        if memo_tipo == "TEORICO"
        else 0,
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
        # Eliminar por source_memo_id (nuevos, desde P4)
        tc_filter_in = "" if tipo == "all" else "AND m.tipo = :tipo"
        await db.execute(
            text(
                f"DELETE FROM theoretical_codes WHERE proyecto_id = :pid "
                f"AND source_memo_id IN (SELECT m.id FROM memos m WHERE m.proyecto_id = :pid2 {tc_filter_in} AND m.user_created = true)"
            ),
            params | {"pid2": project_id},
        )
        # Fallback: eliminar por patrón de nombre (legacy, sin source_memo_id)
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
