"""
Core Category Proposer — Evalúa categorías existentes contra criterios CGT de categoría central.

Se ejecuta DESPUÉS de que todas las pausas every-3-doc están resueltas,
el usuario ha seleccionado exactamente UNA concern y UNA población.
Propone cuál categoría existente debe ser la CORE CATEGORY.

La categoría central NO se detecta con un algoritmo. Emerge de las hipótesis acumuladas.
Las hipótesis documentan relaciones entre categorías → son el input CLAVE.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


# ── Helpers for loading project configuration ──────────────────────────


def _get_object_of_study(session, proyecto_id: str) -> str:
    """Obtiene el object_of_study declarado para el proyecto."""
    row = session.execute(
        text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    return row[0] if row and row[0] else "concern"


def _get_operational_question(session, proyecto_id: str) -> str:
    """Extrae la pregunta operacional del population_assumption JSONB del proyecto."""
    pa = session.execute(
        text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if pa and pa[0] and isinstance(pa[0], dict):
        rq = pa[0].get("research_question", {})
        if isinstance(rq, dict):
            return rq.get("operational_question", "")
    return ""


# ── Guardrail enforcement ──────────────────────────────────────────────


def _enforce_guardrails(session, proyecto_id: str) -> dict | None:
    """Enforces guardrails 1 and 2. Returns an error dict if violated, None if OK.

    Guardrail 1: Exactly ONE confirmed concern.
    Guardrail 2: All categories must have a concern_label assigned.
    """
    # ── Guardrail 1: Exactly ONE confirmed concern ──
    concerns = session.execute(
        text(
            "SELECT id, label, description, status "
            "FROM concerns "
            "WHERE project_id = :pid AND status = 'confirmed'"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    if len(concerns) == 0:
        return {
            "error": "no_confirmed_concern",
            "message": (
                "No hay ninguna concern confirmada. "
                "El usuario debe confirmar exactamente UNA concern antes de proponer "
                "la categoría central."
            ),
        }
    if len(concerns) > 1:
        labels = [c[1] for c in concerns]
        return {
            "error": "multiple_confirmed_concerns",
            "message": (
                f"Hay {len(concerns)} concerns confirmadas: {labels}. "
                "El usuario debe seleccionar exactamente UNA concern. "
                "Rechace o des-confirme las demás antes de continuar."
            ),
            "confirmed_labels": labels,
        }

    # ── Guardrail 2: All categories have concern_label ──
    uncategorized = session.execute(
        text(
            "SELECT COUNT(*) FROM categorias "
            "WHERE proyecto_id = :pid AND (concern_label IS NULL OR concern_label = '')"
        ),
        {"pid": proyecto_id},
    ).fetchone()

    if uncategorized and uncategorized[0] > 0:
        return {
            "error": "categories_without_concern_label",
            "message": (
                f"Hay {uncategorized[0]} categorías sin concern_label asignado. "
                "Todas las categorías deben tener un concern_label antes de proponer "
                "la categoría central. Ejecute el concern labeler (A14) primero."
            ),
            "uncategorized_count": uncategorized[0],
        }

    return None


# ── Data loading ────────────────────────────────────────────────────────


def _load_confirmed_concern(session, proyecto_id: str) -> dict:
    """Carga la única concern confirmada."""
    row = session.execute(
        text(
            "SELECT label, description "
            "FROM concerns "
            "WHERE project_id = :pid AND status = 'confirmed'"
        ),
        {"pid": proyecto_id},
    ).fetchone()

    return {
        "label": row[0] or "",
        "description": row[1] or "",
    }


def _load_categories(session, proyecto_id: str) -> list[dict]:
    """Carga todas las categorías con sus indicadores: label, definicion, doc_count,
    incident_count, concern_label."""
    rows = session.execute(
        text(
            "SELECT c.id, c.nombre, c.definicion, c.concern_label, "
            "c.parent_category_id "
            "FROM categorias c "
            "WHERE c.proyecto_id = :pid "
            "ORDER BY c.creado_en"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    categories = []
    for r in rows:
        cat_id = str(r[0])

        # Doc count via codigos_segmento → segmentos → documentos
        doc_count_row = session.execute(
            text(
                "SELECT COUNT(DISTINCT s.documento_id) "
                "FROM codigos_segmento cs "
                "JOIN segmentos s ON cs.segmento_id = s.id "
                "WHERE cs.categoria_id = :cid"
            ),
            {"cid": cat_id},
        ).fetchone()
        doc_count = doc_count_row[0] if doc_count_row else 0

        # Incident count via incident_groups matching the category label
        inc_count_row = session.execute(
            text(
                "SELECT COUNT(*) FROM incident_groups "
                "WHERE proyecto_id = :pid AND label = :name"
            ),
            {"pid": proyecto_id, "name": r[1]},
        ).fetchone()
        incident_count = inc_count_row[0] if inc_count_row else 0

        categories.append(
            {
                "id": cat_id,
                "label": r[1] or "",
                "definition": r[2] or "",
                "concern_label": r[3] or "",
                "doc_count": doc_count,
                "incident_count": incident_count,
                "parent_category_id": str(r[4]) if r[4] else None,
            }
        )

    return categories


def _load_hypotheses(session, proyecto_id: str) -> list[dict]:
    """Carga todas las hipótesis del proyecto con sus concern_labels."""
    rows = session.execute(
        text(
            "SELECT id, text, level, confidence, status, concern_labels, "
            "code_id, batch_number "
            "FROM hypotheses "
            "WHERE project_id = :pid "
            "ORDER BY created_at"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    hypotheses = []
    for r in rows:
        hypotheses.append(
            {
                "id": str(r[0]),
                "text": r[1] or "",
                "level": r[2] or "general",
                "confidence": float(r[3]) if r[3] else 0.0,
                "status": r[4] or "candidate",
                "concern_labels": list(r[5]) if isinstance(r[5], list) else [],
                "code_id": str(r[6]) if r[6] else None,
                "batch_number": r[7],
            }
        )

    return hypotheses


# ── Compact formatters ─────────────────────────────────────────────────


def _format_categories_compact(categories: list[dict]) -> str:
    """Formatea categorías en formato compacto para ahorrar tokens.

    Example:
    [cat_1] Label: "Sobreviviendo a la avalancha" | Docs: 3 | Incidents: 13 | Concern: "Negotiating permanence" | Def: "proceso de adaptación continua..."
    """
    if not categories:
        return "(no hay categorías)"

    lines = []
    for idx, cat in enumerate(categories, start=1):
        label = cat.get("label", "")
        definition = cat.get("definition", "")
        doc_count = cat.get("doc_count", 0)
        incident_count = cat.get("incident_count", 0)
        concern_label = cat.get("concern_label", "")

        # Truncate definition to ~200 chars to save tokens
        if len(definition) > 200:
            definition = definition[:197] + "..."

        concern_part = f' | Concern: "{concern_label}"' if concern_label else ""

        lines.append(
            f'[cat_{idx}] Label: "{label}" | Docs: {doc_count} '
            f'| Incidents: {incident_count}{concern_part} | Def: "{definition}"'
        )

    return "\n".join(lines)


def _format_hypotheses_compact(hypotheses: list[dict]) -> str:
    """Formatea hipótesis en formato compacto para ahorrar tokens.

    Example:
    [H1] "Cuando X aumenta, Y disminuye" (relational, conf: 0.85) | Concerns: ["Negotiating permanence"] | Code: cat_uuid
    """
    if not hypotheses:
        return "(no hay hipótesis aún)"

    lines = []
    for idx, h in enumerate(hypotheses, start=1):
        text_val = h.get("text", "")
        level = h.get("level", "general")
        confidence = h.get("confidence", 0.0)
        concern_labels = h.get("concern_labels", [])
        code_id = h.get("code_id", "")

        # Truncate long texts
        if len(text_val) > 250:
            text_val = text_val[:247] + "..."

        concern_part = ""
        if concern_labels:
            concern_part = f" | Concerns: {json.dumps(concern_labels)}"

        code_part = f" | Code: {code_id[:8]}..." if code_id else ""

        lines.append(
            f'[H{idx}] "{text_val}" ({level}, conf: {confidence:.2f})'
            f"{concern_part}{code_part}"
        )

    return "\n".join(lines)


# ── Main function ──────────────────────────────────────────────────────


def propose_core_categories(proyecto_id: str) -> dict[str, Any]:
    """Evalúa todas las categorías contra los criterios CGT y propone candidatas
    a categoría central.

    Args:
        proyecto_id: UUID del proyecto.

    Returns:
        dict con:
          - core_category_candidates: list[dict] — candidatas rankeadas
          - recommendation: str — narrativa de recomendación
          - confirmed_concern: dict — la concern confirmada usada
          - no_suitable_core: bool
          - no_suitable_rationale: str | None

    Guardrails enforced:
        1. Exactly ONE confirmed concern must exist.
        2. All categories must have a concern_label assigned.
    """
    session = SessionLocal()
    try:
        logger.info(
            "CoreCategoryProposer: project=%s — starting evaluation",
            proyecto_id[:8],
        )

        # ── Guardrails ──
        guard_error = _enforce_guardrails(session, proyecto_id)
        if guard_error:
            logger.warning(
                "CoreCategoryProposer: guardrail failed — %s",
                guard_error.get("error"),
            )
            return guard_error

        # ── 1. Load confirmed concern ──
        confirmed_concern = _load_confirmed_concern(session, proyecto_id)
        logger.info(
            "CoreCategoryProposer: confirmed concern = '%s'",
            confirmed_concern["label"],
        )

        # ── 2. Load all categories ──
        categories = _load_categories(session, proyecto_id)
        logger.info(
            "CoreCategoryProposer: loaded %d categories",
            len(categories),
        )

        if not categories:
            return {
                "error": "no_categories",
                "message": "No hay categorías en el proyecto. Ejecute la codificación abierta primero.",
            }

        # ── 3. Load all hypotheses ──
        hypotheses = _load_hypotheses(session, proyecto_id)
        logger.info(
            "CoreCategoryProposer: loaded %d hypotheses",
            len(hypotheses),
        )

        # ── 4. Load project config ──
        object_of_study = _get_object_of_study(session, proyecto_id)
        operational_question = _get_operational_question(session, proyecto_id)

        # ── 5. Format compact summaries ──
        categories_summary = _format_categories_compact(categories)
        hypotheses_summary = _format_hypotheses_compact(hypotheses)

        confirmed_concern_text = (
            f'Label: "{confirmed_concern["label"]}"\n'
            f'Description: "{confirmed_concern["description"]}"'
        )

        logger.info(
            "CoreCategoryProposer: calling LLM | cats=%d chars | hyps=%d chars",
            len(categories_summary),
            len(hypotheses_summary),
        )

        # ── 6. Call LLM ──
        response = llm.run_agent(
            "fc_core_category_proposer",
            variables={
                "confirmed_concern": confirmed_concern_text,
                "categories_summary": categories_summary,
                "hypotheses_summary": hypotheses_summary,
                "object_of_study": object_of_study,
                "operational_question": operational_question or "(not yet generated)",
            },
        )

        candidates = response.get("core_category_candidates", [])
        recommendation = response.get("recommendation", "")
        no_suitable_core = response.get("no_suitable_core", False)
        no_suitable_rationale = response.get("no_suitable_rationale", None)

        logger.info(
            "CoreCategoryProposer: %d candidates proposed | no_suitable=%s",
            len(candidates),
            no_suitable_core,
        )

        # ── 7. Validate candidates exist in system ──
        category_labels = {c["label"] for c in categories}
        validated_candidates = []
        for candidate in candidates:
            label = candidate.get("category_label", "")
            if label not in category_labels:
                logger.warning(
                    "CoreCategoryProposer: candidate '%s' not found in categories — skipping",
                    label,
                )
                continue
            validated_candidates.append(candidate)

        if validated_candidates != candidates:
            logger.warning(
                "CoreCategoryProposer: filtered %d invalid candidates (labels not in system)",
                len(candidates) - len(validated_candidates),
            )

        return {
            "core_category_candidates": validated_candidates,
            "recommendation": recommendation,
            "confirmed_concern": confirmed_concern,
            "no_suitable_core": no_suitable_core,
            "no_suitable_rationale": no_suitable_rationale,
        }

    except Exception:
        session.rollback()
        logger.exception("CoreCategoryProposer failed for project %s", proyecto_id)
        raise
    finally:
        session.close()
