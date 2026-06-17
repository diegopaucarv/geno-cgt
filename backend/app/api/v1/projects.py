import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import spacy
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

# ── spaCy model (lazy-loaded) ──────────────────────────────────────────

_nlp: "spacy.Language | None" = None


def _get_nlp() -> "spacy.Language":
    """Lazy-load the Spanish spaCy model."""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("es_core_news_lg")
    return _nlp


# ── Spanish equivalents for canonical object_of_study types ──

_OOS_SPANISH_MAP: dict[str, str] = {
    "concern": "preocupación",
    "emotion": "emoción",
    "behavior": "comportamiento",
    "discourse": "discurso",
    "identity": "identidad",
}

# ── Similarity thresholds ──

_SUGGEST_THRESHOLD = 0.5  # if similarity > this, suggest the canonical type
_ACCEPT_THRESHOLD = 0.3  # if similarity < this to ALL types, accept as custom


def _validate_custom_label_with_spacy(
    custom_label: str,
) -> dict:
    """
    Run spaCy semantic similarity between custom_label and the 5 canonical types
    (using their Spanish equivalents).

    Returns a dict with:
        - suggestion: canonical type to suggest (or None)
        - similarities: {canonical_type: similarity_score}
        - accepted: bool (True if custom label is distinct enough)
    """
    if not custom_label or not custom_label.strip():
        return {"suggestion": None, "similarities": {}, "accepted": True}

    nlp = _get_nlp()
    label_doc = nlp(custom_label.strip())

    similarities: dict[str, float] = {}
    for canonical, spanish in _OOS_SPANISH_MAP.items():
        canonical_doc = nlp(spanish)
        sim = label_doc.similarity(canonical_doc)
        similarities[canonical] = round(float(sim), 4)

    # Check for suggestion: is custom_label similar to any canonical type?
    max_sim = max(similarities.values()) if similarities else 0.0
    suggestion: str | None = None
    if max_sim > _SUGGEST_THRESHOLD:
        # Find the canonical type with highest similarity
        suggestion = max(similarities, key=lambda k: similarities[k])

    # Accept if below threshold to ALL types (truly distinct)
    accepted = max_sim < _ACCEPT_THRESHOLD

    return {
        "suggestion": suggestion,
        "similarities": similarities,
        "accepted": accepted,
        "max_similarity": round(max_sim, 4),
    }


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

VALID_OBJECTS_OF_STUDY = {
    "concern",
    "emotion",
    "behavior",
    "discourse",
    "identity",
    "custom",
}


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
    data = body.model_dump()
    oos = data.get("object_of_study", "concern")
    if oos and oos not in VALID_OBJECTS_OF_STUDY:
        raise HTTPException(
            400,
            f"object_of_study invalido: '{oos}'. "
            f"Valores permitidos: {', '.join(sorted(VALID_OBJECTS_OF_STUDY))}",
        )
    data["object_of_study"] = oos or "concern"

    # ── spaCy validation for custom object_of_study ──
    custom_label = body.custom_label
    spacy_result: dict | None = None
    if oos == "custom" and custom_label and custom_label.strip():
        try:
            spacy_result = _validate_custom_label_with_spacy(custom_label)
            logger.info(
                "spaCy custom_label validation: label=%r suggestion=%s max_sim=%.4f",
                custom_label,
                spacy_result.get("suggestion"),
                spacy_result.get("max_similarity", 0),
            )
        except Exception as e:
            logger.warning("spaCy validation failed for custom_label: %s", e)
            spacy_result = {
                "suggestion": None,
                "similarities": {},
                "accepted": True,
                "max_similarity": 0.0,
            }

    proyecto = Proyecto(**data, creador_id=current_user.id)
    db.add(proyecto)
    await db.commit()
    await db.refresh(proyecto)

    # ── Store custom_label + spaCy result in population_assumption ──
    if oos == "custom" and custom_label and custom_label.strip():
        pop = proyecto.population_assumption or {}
        pop["custom_label"] = custom_label.strip()
        if spacy_result:
            pop["custom_label_spacy"] = spacy_result
        proyecto.population_assumption = pop
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
            # Forzar JSON: Gemma Flash no respeta response_format, necesita instruccion explicita
            messages.append(
                {
                    "role": "user",
                    "content": "Responde EXCLUSIVAMENTE en formato JSON, sin markdown, sin explicacion adicional.",
                }
            )
            model = get_model_for_prompt("population_generalizer")

            llm = TogetherLLM()
            response = await asyncio.to_thread(
                llm.chat,
                model=model,
                messages=messages,
            )

            # Parse JSON from text (gemma flash no soporta response_format JSON schema)
            raw_content = response.get("content", "{}")
            content = {}
            try:
                content = json.loads(raw_content)
            except json.JSONDecodeError:
                import re

                matches = list(
                    re.finditer(
                        r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_content, re.DOTALL
                    )
                )
                for m in matches:
                    try:
                        content = json.loads(m.group(0))
                        break
                    except json.JSONDecodeError:
                        continue

            # Mapear keys en espanol → ingles (Gemma a veces responde en espanol)
            KEY_MAP = {
                "population_generalizada": "generalized_population",
                "poblacion_generalizada": "generalized_population",
                "marco_espacial": "spatial_frame",
                "marco_temporal": "temporal_frame",
                "confianza": "confidence",
                "justificacion": "rationale",
            }
            content = {KEY_MAP.get(k, k): v for k, v in content.items()}

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
        "custom_label",
    }
    update_data = {k: v for k, v in body.items() if k in allowed_keys}

    if not update_data:
        raise HTTPException(
            400, "No se recibieron campos válidos para population_assumption"
        )

    # ── spaCy validation for custom_label ──
    if "custom_label" in update_data:
        cl = update_data["custom_label"]
        resolved_oos = update_data.get(
            "object_of_study",
            proyecto.population_assumption.get(
                "object_of_study", proyecto.object_of_study
            )
            if proyecto.population_assumption
            else proyecto.object_of_study,
        )
        if resolved_oos == "custom" and cl and str(cl).strip():
            try:
                spacy_result = _validate_custom_label_with_spacy(str(cl))
                logger.info(
                    "spaCy custom_label validation (pop-assumption): label=%r suggestion=%s",
                    cl,
                    spacy_result.get("suggestion"),
                )
                update_data["custom_label_spacy"] = spacy_result
            except Exception as e:
                logger.warning(
                    "spaCy validation failed for custom_label (pop-assumption): %s", e
                )
        elif resolved_oos != "custom":
            # Clear spacy data if not custom
            update_data.pop("custom_label_spacy", None)
            current_extra = proyecto.population_assumption or {}
            current_extra.pop("custom_label_spacy", None)

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

    # ── F0.3.5: Sync object_of_study to dedicated column ──
    if "object_of_study" in update_data:
        oos = update_data["object_of_study"]
        if oos not in VALID_OBJECTS_OF_STUDY:
            raise HTTPException(
                400,
                f"object_of_study invalido: '{oos}'. "
                f"Valores permitidos: {', '.join(sorted(VALID_OBJECTS_OF_STUDY))}",
            )
        if oos != proyecto.object_of_study:
            proyecto.object_of_study = oos
            # Reset pipeline state if pattern type changes
            if proyecto.estado not in ("collecting", "coding"):
                proyecto.estado = "coding"
                logger.info(
                    "Project %s: object_of_study changed via pop-assumption, resetting to 'coding'",
                    proyecto.id,
                )

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


# ═══════════════════════════════════════════════════════════════════════
# F0.6: Nemotrón — Research Question endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research-question")
async def get_research_question(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Returns the stored research question for a project.

    The research question is stored in population_assumption.research_question
    after the Nemotrón agent generates it.
    """
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    pa = proyecto.population_assumption or {}
    rq_data = pa.get("research_question")

    if not rq_data:
        return {
            "project_id": str(project_id),
            "research_question": None,
            "operational_question": None,
            "rationale": None,
            "key_dimensions": None,
            "generated_at": None,
            "message": "No research question generated yet. Use POST .../generate to create one.",
        }

    return {
        "project_id": str(project_id),
        **rq_data,
    }


@router.post("/{project_id}/research-question/generate")
async def generate_research_question(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Triggers the Nemotrón agent to generate a formal CGT research question.

    Dispatches the research_question_builder Celery task to the heavy queue.
    Returns the task_id for polling.
    """
    from app.core.celery_app import celery_app

    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    # Verify project has population assumption data
    pa = proyecto.population_assumption or {}
    pop_desc = pa.get("population_description", "")
    if not pop_desc or not pop_desc.strip():
        # Fallback: use supuesto_poblacional
        if not proyecto.supuesto_poblacional:
            raise HTTPException(
                400,
                "El proyecto no tiene population_description ni supuesto_poblacional. "
                "Configure la población antes de generar la pregunta de investigación.",
            )

    task = celery_app.send_task(
        "research_question_builder",
        args=[str(project_id)],
        queue="heavy",
    )

    return {
        "status": "dispatched",
        "project_id": str(project_id),
        "task_id": task.id,
        "message": "Research question generation dispatched. Use GET .../research-question to check results.",
    }


# ═══════════════════════════════════════════════════════════════════════
# Config endpoints — lectura y política de mutaciones (continuación)
# ═══════════════════════════════════════════════════════════════════════


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
    pattern_changed = False
    new_oos = body.get("object_of_study")
    for key, value in body.items():
        if key in updatable and value is not None:
            if key == "object_of_study" and value not in VALID_OBJECTS_OF_STUDY:
                raise HTTPException(
                    400,
                    detail=f"object_of_study invalido: '{value}'. "
                    f"Valores permitidos: {', '.join(sorted(VALID_OBJECTS_OF_STUDY))}",
                )
            if key == "object_of_study" and value != proyecto.object_of_study:
                pattern_changed = True
            setattr(proyecto, key, value)

    # ── Handle custom_label: spaCy validation + JSONB sync ──
    custom_label = body.get("custom_label")
    if custom_label is not None:
        resolved_oos = new_oos if new_oos is not None else proyecto.object_of_study
        if resolved_oos == "custom" and custom_label and str(custom_label).strip():
            # Run spaCy validation
            try:
                spacy_result = _validate_custom_label_with_spacy(str(custom_label))
                logger.info(
                    "spaCy custom_label validation (update): label=%r suggestion=%s max_sim=%.4f",
                    custom_label,
                    spacy_result.get("suggestion"),
                    spacy_result.get("max_similarity", 0),
                )
            except Exception as e:
                logger.warning(
                    "spaCy validation failed for custom_label (update): %s", e
                )
                spacy_result = {
                    "suggestion": None,
                    "similarities": {},
                    "accepted": True,
                    "max_similarity": 0.0,
                }
            # Store in population_assumption
            pop = proyecto.population_assumption or {}
            pop["custom_label"] = str(custom_label).strip()
            pop["custom_label_spacy"] = spacy_result
            proyecto.population_assumption = pop
        elif resolved_oos != "custom":
            # Clear custom_label if object_of_study is no longer "custom"
            pop = proyecto.population_assumption or {}
            pop.pop("custom_label", None)
            pop.pop("custom_label_spacy", None)
            proyecto.population_assumption = pop

    # ── F0.3.5: Si cambia el tipo de patron, reiniciar pipeline ──
    if pattern_changed and proyecto.estado not in ("collecting", "coding"):
        proyecto.estado = "coding"
        logger.info(
            "Project %s: object_of_study changed, resetting state to 'coding'",
            proyecto.id,
        )

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
