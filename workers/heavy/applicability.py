"""F5.5 — Applicability: Generate + Critique intervention guidelines from theory.

Two PRO agents:
  1. applicability_engine: Identifies control/access variables, drafts guidelines
  2. applicability_critic: Evaluates genuineness, limits, accessibility, modifiability

Refs: 3-memomaker.md §F5.5, AGENTES.md Applicability.
"""

from __future__ import annotations

import json
import logging

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════


def generate_applicability(proyecto_id: str) -> dict:
    """Generate intervention guidelines from the grounded theory.

    Reads complete theory from DB, identifies control variables (modifiable)
    and access variables (conditional), and drafts intervention guidelines
    with causal mechanisms traced to theory properties.

    Args:
        proyecto_id: UUID of the project

    Returns:
        dict with {control_variables: [{name, description, modifiable_by,
                   theory_basis}], access_variables: [{name, description,
                   conditions_access}], guidelines: [{guideline, target,
                   mechanism, evidence_from_theory}], implications: [str],
                   future_agenda: [str]}
    """
    session = SessionLocal()
    try:
        # ── 1. Read full theory from DB ──
        logger.info(
            "ApplicabilityEngine: reading theory for proyecto %s",
            proyecto_id[:8],
        )
        theory = _read_full_theory(session, proyecto_id)

        # ── 2. Derive application context from project metadata ──
        app_context = _get_application_context(session, proyecto_id)

        # ── 2.5 Fetch object_of_study ──
        oos_row = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # ── 3. Call applicability_engine PRO agent ──
        logger.info("ApplicabilityEngine: generating guidelines")
        result = llm.run_agent(
            "f6d_applicability_engine",
            variables={
                "theory": theory,
                "application_context": app_context,
                "object_of_study": object_of_study,
            },
        )
        logger.info(
            "ApplicabilityEngine: %d control vars, %d access vars, %d guidelines",
            len(result.get("control_variables", [])),
            len(result.get("access_variables", [])),
            len(result.get("guidelines", [])),
        )
        return result

    except Exception:
        logger.exception("generate_applicability failed for proyecto %s", proyecto_id)
        return {"error": "generate_applicability failed", "proyecto_id": proyecto_id}
    finally:
        session.close()


def critique_applicability(directrices: dict) -> dict:
    """Critique the applicability guidelines for genuineness, limits, accessibility.

    Evaluates:
      - Genuineness: each guideline derived from a specific theory property?
      - Limits: does it acknowledge when it does NOT apply?
      - Accessibility: language understandable by non-academic practitioners?
      - Modifiability: are control variables actually modifiable in practice?
      - Mechanism: does each guideline explain the causal mechanism?

    Args:
        directrices: Full output from generate_applicability (includes
                     control_variables, access_variables, guidelines, etc.)

    Returns:
        dict with {verdict: SAT|MOD|FORCED,
                   issues: [{type, guideline_index, detail, suggestion}]}
    """
    try:
        logger.info("ApplicabilityCritic: evaluating guidelines")
        guidelines_str = json.dumps(
            directrices.get("guidelines", []), ensure_ascii=False
        )
        variables_str = json.dumps(
            {
                "control_variables": directrices.get("control_variables", []),
                "access_variables": directrices.get("access_variables", []),
            },
            ensure_ascii=False,
        )

        result = llm.run_agent(
            "f6d_applicability_critic",
            variables={
                "guidelines": guidelines_str,
                "variables": variables_str,
            },
        )
        logger.info(
            "ApplicabilityCritic: verdict=%s, issues=%d",
            result.get("verdict", "?"),
            len(result.get("issues", [])),
        )
        return result

    except Exception:
        logger.exception("critique_applicability failed")
        return {"error": "critique_applicability failed"}


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _get_application_context(session, proyecto_id: str) -> str:
    """Derive a natural-language application context from project metadata."""
    row = session.execute(
        text("SELECT supuesto_poblacional, nombre FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()

    if row and row[0]:
        return (
            f"Proyecto: {row[1] or 'Sin nombre'}. "
            f"Supuesto poblacional: {row[0]}. "
            "El contexto de aplicación es el mismo dominio sustantivo "
            "del cual emergió la teoría."
        )

    return (
        "Contexto de aplicación genérico: intervención profesional "
        "basada en la teoría fundamentada. El dominio es el mismo "
        "del cual emergió la teoría."
    )


def _read_full_theory(session, proyecto_id: str) -> str:
    """Read the complete grounded theory for a project from the DB.

    Gathers: categories, hypotheses, memos (PROPIEDAD/HIPOTESIS),
    paradigm states, and the Database A/B theoretical model.
    """
    # ── Categories ──
    cats = session.execute(
        text(
            "SELECT id, nombre, definicion, limites, estado_saturacion, "
            "saturation_panel_json, gerundio_label, es_central "
            "FROM categorias WHERE proyecto_id = :pid"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    # ── Hypotheses ──
    hyps = session.execute(
        text(
            "SELECT h.text, h.level, h.confidence, h.status, "
            "COALESCE(c.nombre, 'sin categoria') AS category_name "
            "FROM hypotheses h "
            "LEFT JOIN categorias c ON h.code_id = c.id "
            "WHERE h.project_id = :pid"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    # ── Memos (theoretical: PROPIEDAD, HIPOTESIS) ──
    memos = session.execute(
        text(
            "SELECT contenido, tipo, estado, structured_fields "
            "FROM memos WHERE proyecto_id = :pid "
            "AND tipo IN ('PROPIEDAD', 'HIPOTESIS') "
            "ORDER BY tipo"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    # ── Paradigm states (latest per category) ──
    paradigms = session.execute(
        text(
            "SELECT ps.paradigm_snapshot, ps.integration_memo, ps.iteration, "
            "c.nombre AS category_name "
            "FROM paradigm_states ps "
            "JOIN categorias c ON ps.code_id = c.id "
            "WHERE c.proyecto_id = :pid "
            "ORDER BY c.nombre, ps.iteration DESC"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    # ── Database A: nodes ──
    nodes = session.execute(
        text(
            "SELECT dn.label, COALESCE(c.nombre, 'sin categoria') AS category_name "
            "FROM database_nodes dn "
            "LEFT JOIN categorias c ON dn.category_id = c.id "
            "WHERE dn.project_id = :pid"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    # ── Database B: edges/relationships ──
    edges = session.execute(
        text(
            "SELECT de.relationship_type, "
            "src.label AS source_label, tgt.label AS target_label "
            "FROM database_edges de "
            "JOIN database_nodes src ON de.source_node_id = src.id "
            "JOIN database_nodes tgt ON de.target_node_id = tgt.id "
            "WHERE de.project_id = :pid"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    parts: list[str] = []

    # ── 1. Categories ──
    parts.append("=== CATEGORÍAS ===")
    for c in cats:
        parts.append(
            f"Categoría: {c[1]}\n"
            f"  Definición: {c[2]}\n"
            f"  Límites: {c[3] or 'No definidos'}\n"
            f"  Estado saturación: {c[4]}\n"
            f"  Gerundio: {c[6] or 'N/A'}\n"
            f"  Es central: {'Sí' if c[7] else 'No'}"
        )

    # ── 2. Hypotheses ──
    if hyps:
        parts.append("\n=== HIPÓTESIS ===")
        for h in hyps:
            parts.append(f"[{h[1]}, confianza={h[2]:.2f}] {h[0]}\n  Categoría: {h[4]}")

    # ── 3. Memos ──
    if memos:
        parts.append("\n=== MEMOS TEÓRICOS ===")
        for m in memos:
            content = (m[0] or "")[:500]
            parts.append(f"[{m[1]}] {content}")

    # ── 4. Paradigm states ──
    if paradigms:
        parts.append("\n=== ESTADOS PARADIGMÁTICOS ===")
        seen_cats: set[str] = set()
        for p in paradigms:
            cat_name = p[3]
            if cat_name in seen_cats:
                continue
            seen_cats.add(cat_name)
            snap = (
                p[0] if isinstance(p[0], str) else json.dumps(p[0], ensure_ascii=False)
            )
            parts.append(
                f"Categoría: {cat_name} (iteración {p[2]})\n"
                f"  Paradigma: {snap[:800]}\n"
                f"  Integración: {(p[1] or '')[:400]}"
            )

    # ── 5. Database A/B model ──
    if nodes:
        parts.append("\n=== MODELO TEÓRICO — NODOS ===")
        for n in nodes:
            parts.append(f"- {n[0]} (categoría: {n[1]})")
    if edges:
        parts.append("\n=== MODELO TEÓRICO — RELACIONES ===")
        for e in edges:
            parts.append(f"- {e[1]} --[{e[0]}]--> {e[2]}")

    return "\n".join(parts)
