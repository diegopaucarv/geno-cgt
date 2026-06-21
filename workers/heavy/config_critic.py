"""
Configuration Critic — Reviews emerging theoretical configuration after every 3-doc batch.

Runs AFTER the category synthesizer and hypothesis synthesizer complete.
Evaluates:
  1. Possible underlying concerns (gerunds) — what the population seems to be
     continuously trying to resolve
  2. Possible population reconfigurations — different ways to segment the population
     based on emerging conceptual patterns
  3. Coding style recommendation — whether the current coding style adequately
     captures what's important

La CGT compara unidades conceptuales y no unidades demográficas estrictas.
Looks for TENSIONS and UNDERLYING PROCESSES, not surface themes.
"""

from __future__ import annotations

import logging

from context_utils import inject_chosen_context
from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def _get_operational_question(session, proyecto_id: str) -> str:
    """Extract operational question from project's population_assumption JSONB."""
    pa = session.execute(
        text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if pa and pa[0] and isinstance(pa[0], dict):
        rq = pa[0].get("research_question", {})
        if isinstance(rq, dict):
            return rq.get("operational_question", "")
    return ""


def _get_object_of_study(session, proyecto_id: str) -> str:
    """Get the declared object of study for the project."""
    row = session.execute(
        text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    return row[0] if row and row[0] else "concern"


def _get_population_description(session, proyecto_id: str) -> str:
    """Get the population description from proyecto."""
    # Try from supuesto_poblacional first (legacy text field)
    row = session.execute(
        text(
            "SELECT supuesto_poblacional, population_assumption FROM proyectos WHERE id = :pid"
        ),
        {"pid": proyecto_id},
    ).fetchone()
    if not row:
        return "(sin supuesto poblacional)"

    # Prefer population_assumption.population_description if available
    if row[1] and isinstance(row[1], dict):
        pop_desc = row[1].get("population_description", "")
        if pop_desc:
            return pop_desc

    # Fallback to supuesto_poblacional text field
    if row[0]:
        return row[0]

    return "(sin supuesto poblacional)"


def _get_current_concerns(session, proyecto_id: str) -> str:
    """Get currently identified concerns from the concerns table."""
    rows = session.execute(
        text(
            "SELECT label, description, status "
            "FROM concerns "
            "WHERE project_id = :pid "
            "ORDER BY created_at"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    if not rows:
        return "(no hay concerns identificadas aún — primera iteración)"

    lines = []
    for r in rows:
        label = r[0] or ""
        desc = r[1] or ""
        status = r[2] or "candidate"
        # Truncate descriptions to save tokens
        if len(desc) > 150:
            desc = desc[:147] + "..."
        lines.append(f"- [{status}] {label}: {desc}")

    return "\n".join(lines)


def _get_coding_style(session, proyecto_id: str) -> str:
    """Get the current coding style instruction."""
    row = session.execute(
        text("SELECT coding_style_instruction FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if row and row[0]:
        return row[0]

    # Try population_assumption.coding_styles
    pa = session.execute(
        text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if pa and pa[0] and isinstance(pa[0], dict):
        styles = pa[0].get("coding_styles", [])
        if styles:
            return "gerundio"

    return "gerundio"


def _get_baseline_segments(
    session, proyecto_id: str, batch_start: int, batch_size: int = 3
) -> str:
    """Get baseline segments for documents in the current batch.

    Documents are ordered by creation. batch_start is 1-based doc index.
    Returns compact text with segment content for the batch window.
    """
    # Get ordered documents
    docs = session.execute(
        text(
            "SELECT id, original_filename "
            "FROM documentos "
            "WHERE proyecto_id = :pid "
            "ORDER BY creado_en"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    if not docs:
        return "(no hay documentos)"

    # Compute batch range (0-based)
    batch_start_idx = batch_start - 1  # Convert to 0-based
    batch_end_idx = min(batch_start_idx + batch_size, len(docs))

    if batch_start_idx >= len(docs):
        return "(batch fuera de rango)"

    batch_docs = docs[batch_start_idx:batch_end_idx]
    batch_doc_ids = [str(d[0]) for d in batch_docs]

    if not batch_doc_ids:
        return "(sin documentos en el lote)"

    # Get baseline segments for batch documents
    segments = session.execute(
        text(
            "SELECT s.texto, d.original_filename "
            "FROM segmentos s "
            "JOIN documentos d ON s.documento_id = d.id "
            "WHERE s.documento_id IN :doc_ids "
            "AND s.tipo_dato_glaser = 'baseline_data' "
            "ORDER BY d.creado_en, s.posicion"
        ),
        {
            "doc_ids": tuple(batch_doc_ids),
        },
    ).fetchall()

    if not segments:
        return "(sin segmentos baseline en este lote)"

    lines = []
    current_doc = None
    for seg in segments:
        texto = (seg[0] or "").strip()
        doc_name = seg[1] or "desconocido"
        if not texto:
            continue

        # Add doc header when switching documents
        if doc_name != current_doc:
            current_doc = doc_name
            lines.append(f"\n── {doc_name} ──")

        # Truncate long segments to save tokens
        if len(texto) > 300:
            texto = texto[:297] + "..."
        lines.append(f"• {texto}")

    return "\n".join(lines)


def _format_categories_compact(categories: list[dict]) -> str:
    """Format categories in compact token-saving format.

    Example:
    [cat_1] Label: "Sobreviviendo" | Docs: 1,2,3 | Incidents: 13 | Def: "proceso de..."
    """
    lines = []
    for idx, cat in enumerate(categories, start=1):
        label = cat.get("label", "")
        definition = cat.get("definition", "")
        doc_count = (
            cat.get("doc_count", 0)
            if "doc_count" in cat
            else len(cat.get("doc_ids", []))
        )
        incident_count = cat.get("incident_count", 0)

        # Truncate definition to ~200 chars
        if len(definition) > 200:
            definition = definition[:197] + "..."

        lines.append(
            f'[cat_{idx}] Label: "{label}" | Docs: {doc_count} '
            f'| Incidents: {incident_count} | Def: "{definition}"'
        )

    return "\n".join(lines) if lines else "(no hay categorías)"


def _format_hypotheses_compact(hypotheses: list[dict]) -> str:
    """Format hypotheses in compact token-saving format.

    Example:
    [H1] "Cuando X, entonces Y" (relational, confidence: 0.7)
    """
    if not hypotheses:
        return "(no hay hipótesis)"

    lines = []
    for idx, h in enumerate(hypotheses, start=1):
        text_val = h.get("text", "") or str(h)
        level = h.get("level", "general")
        htype = h.get("type", "descriptive")
        confidence = h.get("confidence", 0.0)

        # Truncate long hypothesis text
        if len(text_val) > 200:
            text_val = text_val[:197] + "..."

        lines.append(f'[H{idx}] "{text_val}" ({htype}, {level}, conf: {confidence})')

    return "\n".join(lines)


def critique_configuration(
    proyecto_id: str,
    batch_start: int,
    categories: list[dict],
    hypotheses: list[dict],
) -> dict:
    """Review emerging theoretical configuration after a 3-doc synthesis batch.

    Args:
        proyecto_id: Project UUID.
        batch_start: 1-based index of the first document in the current batch.
        categories: Current unified categories (after synthesizer) as list of dicts.
        hypotheses: Current hypotheses as list of dicts.

    Returns:
        dict with:
          - concerns: list[dict] — identified gerund concerns
          - population_variants: list[dict] — proposed population reconfigurations
          - coding_style_recommendation: dict — style evaluation
          - rationale: str — overall narrative
    """
    session = SessionLocal()
    try:
        logger.info(
            "ConfigCritic: project=%s batch_start=%d categories=%d hypotheses=%d",
            proyecto_id[:8],
            batch_start,
            len(categories),
            len(hypotheses),
        )

        # ── 1. Load project config ──
        operational_question = _get_operational_question(session, proyecto_id)
        object_of_study = _get_object_of_study(session, proyecto_id)
        current_population = _get_population_description(session, proyecto_id)
        current_concerns = _get_current_concerns(session, proyecto_id)
        current_coding_style = _get_coding_style(session, proyecto_id)

        # ── 2. Load baseline segments for the current batch ──
        baseline_segments = _get_baseline_segments(session, proyecto_id, batch_start)

        # ── 3. Format compact summaries ──
        categories_summary = _format_categories_compact(categories)
        hypotheses_summary = _format_hypotheses_compact(hypotheses)

        # ── 4. Call AI critic ──
        logger.info(
            "ConfigCritic: calling fd_config_critic | cats=%d chars | hyps=%d chars | segments=%d chars",
            len(categories_summary),
            len(hypotheses_summary),
            len(baseline_segments),
        )

        response = llm.run_agent(
            "fd_config_critic",
            variables=inject_chosen_context(
                proyecto_id,
                session,
                {
                    "categories_summary": categories_summary,
                    "hypotheses_summary": hypotheses_summary,
                    "baseline_segments": baseline_segments,
                    "current_population": current_population,
                    "current_concerns": current_concerns,
                    "current_coding_style": current_coding_style,
                    "operational_question": operational_question
                    or "(not yet generated)",
                    "object_of_study": object_of_study,
                },
            ),
            temperature=0.3,
        )

        # ── 5. Extract results ──
        concerns = response.get("concerns", [])
        population_variants = response.get("population_variants", [])
        coding_style_rec = response.get("coding_style_recommendation", {})
        rationale = response.get("rationale", "")

        concern_count = len(concerns) if isinstance(concerns, list) else 0
        variant_count = (
            len(population_variants) if isinstance(population_variants, list) else 0
        )

        logger.info(
            "ConfigCritic complete: %d concerns, %d population variants, style=%s",
            concern_count,
            variant_count,
            coding_style_rec.get("recommendation", "unknown")
            if isinstance(coding_style_rec, dict)
            else "unknown",
        )

        # ── 6. Persist concerns to DB ──
        if isinstance(concerns, list):
            for concern in concerns:
                if not isinstance(concern, dict):
                    continue
                label = concern.get("label", "").strip()
                description = concern.get("description", "").strip()
                confidence = concern.get("confidence", "MEDIUM")

                if not label:
                    continue

                # Check if concern already exists (by label)
                existing = session.execute(
                    text(
                        "SELECT id FROM concerns "
                        "WHERE project_id = :pid AND label = :label"
                    ),
                    {"pid": proyecto_id, "label": label},
                ).fetchone()

                if existing:
                    # Update existing concern
                    session.execute(
                        text(
                            "UPDATE concerns SET description = :desc, "
                            "status = CASE WHEN :conf = 'HIGH' THEN 'confirmed' ELSE status END, "
                            "updated_at = NOW() "
                            "WHERE id = :cid"
                        ),
                        {
                            "desc": description,
                            "conf": confidence,
                            "cid": str(existing[0]),
                        },
                    )
                    logger.debug("ConfigCritic: updated concern '%s'", label)
                else:
                    # Insert new concern
                    status = "confirmed" if confidence == "HIGH" else "candidate"
                    session.execute(
                        text(
                            "INSERT INTO concerns (id, project_id, label, description, status, identified_at_batch) "
                            "VALUES (gen_random_uuid(), :pid, :label, :desc, :status, :batch)"
                        ),
                        {
                            "pid": proyecto_id,
                            "label": label,
                            "desc": description,
                            "status": status,
                            "batch": batch_start,
                        },
                    )
                    logger.info(
                        "ConfigCritic: new concern '%s' (%s)", label, confidence
                    )

        session.commit()

        # ── 7. HITL gate ──
        from agents.transitions import hitl_gate
        from database import SessionLocal as _SL

        _s = _SL()
        try:
            proposal = {
                "concerns": concerns,
                "population_variants": population_variants,
                "coding_style": coding_style_rec,
                "rationale": rationale,
            }
            critic_verdict = {
                "verdict": "SAT",
                "note": "Review the proposed configuration before continuing.",
            }
            hitl_gate(_s, proyecto_id, "config_review", proposal, critic_verdict)
            logger.info(
                "ConfigCritic HITL gate created for project %s",
                proyecto_id[:8],
            )
        finally:
            _s.close()

        return {
            "concerns": concerns,
            "population_variants": population_variants,
            "coding_style_recommendation": coding_style_rec,
            "rationale": rationale,
            "status": "ok",
        }

    except Exception:
        session.rollback()
        logger.exception(
            "ConfigCritic failed for project %s batch_start=%d",
            proyecto_id,
            batch_start,
        )
        return {
            "status": "error",
            "proyecto_id": proyecto_id,
            "batch_start": batch_start,
            "concerns": [],
            "population_variants": [],
            "coding_style_recommendation": {},
            "rationale": "",
        }
    finally:
        session.close()
