"""F5.4 — Literature Dialogue: Compare + Critique literature vs grounded theory.

Two PRO agents:
  1. literature_comparer: Codes lit fragments as incidents, evaluates emergent fit
  2. literature_critic: Detects forcing, authority bias, name-dropping

Refs: 3-memomaker.md §F5.4, AGENTES.md LiteratureDialogue.
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


def compare_literature(
    proyecto_id: str,
    literature_fragments: list[str],
) -> dict:
    """Compare literature fragments against the grounded theory.

    Reads full theory (categories + properties + hypotheses) from DB,
    codes literature fragments as incidents, and evaluates emergent fit.

    Args:
        proyecto_id: UUID of the project
        literature_fragments: List of literature text fragments to compare

    Returns:
        dict with {comparison_table: [{category, extends, modifies, integrates,
                   transcends}], global_assessment: str}
    """
    session = SessionLocal()
    try:
        # ── 1. Read full theory from DB ──
        logger.info(
            "LiteratureComparer: reading full theory for proyecto %s",
            proyecto_id[:8],
        )
        theory = _read_full_theory(session, proyecto_id)

        # ── 1.5 Fetch research context ──
        ctx = session.execute(
            text(
                "SELECT object_of_study, population_assumption "
                "FROM proyectos WHERE id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = ctx[0] if ctx and ctx[0] else "concern"
        pa = ctx[1] if ctx and ctx[1] else {}
        rq_data = pa.get("research_question", {}) if isinstance(pa, dict) else {}
        research_question = rq_data.get("research_question", "(not generated)")

        # ── 2. Call literature_comparer PRO agent ──
        logger.info(
            "LiteratureComparer: comparing %d fragments against theory",
            len(literature_fragments),
        )
        result = llm.run_agent(
            "f6c_literature_comparer",
            variables={
                "theory": theory,
                "literature_fragments": json.dumps(
                    literature_fragments, ensure_ascii=False
                ),
                "object_of_study": object_of_study,
                "research_question": research_question,
            },
        )
        logger.info("LiteratureComparer: completed for proyecto %s", proyecto_id[:8])
        return result

    except Exception:
        logger.exception("compare_literature failed for proyecto %s", proyecto_id)
        return {"error": "compare_literature failed", "proyecto_id": proyecto_id}
    finally:
        session.close()


def critique_literature_dialogue(
    comparison_table: dict, proyecto_id: str = None
) -> dict:
    """Critique the literature comparison for forcing, authority bias, name-dropping.

    Detects:
      - Forcing matches (extending literature without data evidence)
      - Treating literature as authority
      - Name-dropping (citing authors without substantive engagement)
      - Absence of transcendence (all cells are "extends" or "modifies")
      - Unidirectional dialogue (only literature corrects theory)

    Args:
        comparison_table: Output from compare_literature (must include comparison_table key)
        proyecto_id: Optional. If provided, fetches theory, literature_fragments,
                     object_of_study, and research_question from DB for deeper evaluation.

    Returns:
        dict with {verdict: SAT|MOD|FORCED,
                   issues: [{type, detail, suggestion}]}
    """
    session = SessionLocal() if proyecto_id else None
    try:
        logger.info("LiteratureCritic: evaluating comparison table")

        # ── Fetch full context from DB if proyecto_id provided ──
        theory = ""
        literature_fragments = ""
        object_of_study = ""
        research_question = ""

        if proyecto_id and session:
            theory = _read_full_theory(session, proyecto_id)
            ctx = session.execute(
                text(
                    "SELECT object_of_study, population_assumption "
                    "FROM proyectos WHERE id = :pid"
                ),
                {"pid": proyecto_id},
            ).fetchone()
            if ctx:
                object_of_study = ctx[0] if ctx[0] else "concern"
                pa = ctx[1] if ctx[1] else {}
                rq_data = (
                    pa.get("research_question", {}) if isinstance(pa, dict) else {}
                )
                research_question = rq_data.get("research_question", "(not generated)")
            logger.info(
                "LiteratureCritic: loaded context — OOS=%s, theory=%d chars",
                object_of_study,
                len(theory),
            )

        result = llm.run_agent(
            "f6c_literature_critic",
            variables={
                "comparison_table": json.dumps(comparison_table, ensure_ascii=False),
                "theory": theory[:8000] if theory else "(not available)",
                "literature_fragments": literature_fragments[:3000]
                if literature_fragments
                else "(not available)",
                "object_of_study": object_of_study or "(not provided)",
                "research_question": research_question or "(not generated)",
            },
        )
        logger.info(
            "LiteratureCritic: verdict=%s, issues=%d",
            result.get("verdict", "?"),
            len(result.get("issues", [])),
        )
        return result

    except Exception:
        logger.exception("critique_literature_dialogue failed")
        return {"error": "critique_literature_dialogue failed"}
    finally:
        if session:
            session.close()


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


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
                continue  # only latest iteration per category
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
