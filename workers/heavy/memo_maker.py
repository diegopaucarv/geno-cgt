"""F4.3 — MemoMaker: Generate, Simplify, Correlate memos at category saturation.

Triggered by task_core_saturation_loop when a category reaches saturation.
3 PRO agents: Generate (4 analyses) → Simplify (double-entry tables) → Correlate (2x2 matrices).

Refs: 3-memomaker.md, kb.md 6.3, AGENTES.md MemoMaker.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


# ═══════════════════════════════════════════════════════════════════════
# Public API — called from task_core_saturation_loop
# ═══════════════════════════════════════════════════════════════════════


def generate_saturation_memo(
    category_id: str,
    proyecto_id: str,
    author_id: str | None = None,
) -> dict:
    """Generate a saturation memo for a category via 3-step MemoMaker.

    Steps:
      1. Generate (PRO): Integrates 4 analyses (paradigm, incidents, gaps, properties)
      2. Simplify (PRO): Double-entry tables for each analysis dimension
      3. Correlate (PRO): 2x2 matrix + typology from the simplified tables

    Returns:
        dict with {memo_id, structured_fields, version, status}
    """
    session = SessionLocal()
    try:
        # ── Load category data ──
        cat = session.execute(
            text(
                "SELECT nombre, definicion, saturation_panel_json, "
                "gerundio_label FROM categorias WHERE id = :cid"
            ),
            {"cid": category_id},
        ).fetchone()
        if not cat:
            return {"error": "Category not found", "category_id": category_id}

        cat_name = cat[0]

        # ── Step 1: Generate (PRO) ──
        logger.info("MemoMaker: generating memo for '%s'", cat_name)
        memo_content = _step_generate(session, category_id, proyecto_id, cat_name)

        # ── Step 2: Simplify (PRO) ──
        simplified = _step_simplify(memo_content, cat_name)

        # ── Step 3: Correlate (PRO) ──
        correlated = _step_correlate(simplified, cat_name, proyecto_id)

        # ── Persist memo ──
        memo_id = str(uuid4())
        structured = {
            "generated_content": memo_content,
            "simplified_tables": simplified,
            "correlated_matrices": correlated,
            "memo_maker_version": 1,
        }

        session.execute(
            text(
                "INSERT INTO memos (id, proyecto_id, autor_id, tipo, estado, "
                "contenido, version, structured_fields) "
                "VALUES (:id, :pid, :aid, 'PROPIEDAD', 'ABIERTO', :content, 1, :fields)"
            ),
            {
                "id": memo_id,
                "pid": proyecto_id,
                "aid": author_id,
                "content": memo_content[:5000],
                "fields": json.dumps(structured, ensure_ascii=False),
            },
        )
        session.commit()

        logger.info("MemoMaker: memo %s created for '%s'", memo_id[:8], cat_name)
        return {
            "memo_id": memo_id,
            "structured_fields": structured,
            "version": 1,
            "status": "created",
        }

    except Exception:
        logger.exception("MemoMaker failed for category %s", category_id)
        return {"error": "MemoMaker failed", "category_id": category_id}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Step 1: Generate — integrate 4 analyses into a narrative memo
# ═══════════════════════════════════════════════════════════════════════


def _step_generate(session, category_id: str, proyecto_id: str, cat_name: str) -> str:
    """PRO: Integrate paradigm, incidents, gaps, and properties into a memo."""

    paradigm_rows = session.execute(
        text(
            "SELECT paradigm_snapshot, integration_memo FROM paradigm_states "
            "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 5"
        ),
        {"cid": category_id},
    ).fetchall()

    incidents = session.execute(
        text(
            "SELECT s.texto, d.original_filename "
            "FROM codigos_segmento cs "
            "JOIN segmentos s ON cs.segmento_id = s.id "
            "JOIN documentos d ON s.documento_id = d.id "
            "WHERE cs.categoria_id = :cid LIMIT 15"
        ),
        {"cid": category_id},
    ).fetchall()

    saturation = session.execute(
        text("SELECT saturation_panel_json FROM categorias WHERE id = :cid"),
        {"cid": category_id},
    ).fetchone()

    variables = {
        "category_name": cat_name,
        "paradigm_snapshots": json.dumps(
            [
                json.loads(r[0]) if isinstance(r[0], str) else r[0]
                for r in paradigm_rows
                if r[0]
            ],
            ensure_ascii=False,
        ),
        "incident_samples": json.dumps(
            [{"text": r[0][:300], "doc": r[1]} for r in incidents],
            ensure_ascii=False,
        ),
        "saturation_panel": json.dumps(
            saturation[0] if saturation and saturation[0] else {},
            ensure_ascii=False,
        ),
    }

    response = llm._call_llm(
        tier="PRO",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un generador de memos teoricos para Classic Grounded Theory. "
                    "Integra 4 fuentes de analisis en un memo narrativo:\n"
                    "1. Paradigma: dimensiones, condiciones, consecuencias, estrategias\n"
                    "2. Incidentes: evidencia textual que respalda la categoria\n"
                    "3. Gaps: que propiedades faltan documentar\n"
                    "4. Relaciones: con que otras categorias se vincula\n\n"
                    "Escribe en presente conceptual. Usa gerundios. "
                    "Cada afirmacion debe rastrearse a un incidente fuente. "
                    "Maximo 500 palabras."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Categoria: {cat_name}\n\n"
                    f"Paradigma (ultimas 5 iteraciones):\n{variables['paradigm_snapshots']}\n\n"
                    f"Incidentes de evidencia:\n{variables['incident_samples']}\n\n"
                    f"Panel de saturacion:\n{variables['saturation_panel']}\n\n"
                    "Redacta un memo teorico que integre estos 4 analisis."
                ),
            },
        ],
        temperature=0.3,
        max_tokens=1500,
    )

    return response.get("content", "") if isinstance(response, dict) else str(response)


# ═══════════════════════════════════════════════════════════════════════
# Step 2: Simplify — double-entry tables
# ═══════════════════════════════════════════════════════════════════════


def _step_simplify(memo_content: str, cat_name: str) -> dict:
    """PRO: Transform the narrative memo into double-entry analysis tables."""

    response = llm._call_llm(
        tier="PRO",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un simplificador de memos para Classic Grounded Theory. "
                    "Transforma un memo narrativo en tablas de doble entrada. "
                    "Para cada dimension del paradigma, crea una tabla:\n"
                    "Filas = propiedades, Columnas = documentos/incidentes.\n"
                    "Responde SOLO en JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Memo de la categoria '{cat_name}':\n\n{memo_content}\n\n"
                    "Produce tablas de doble entrada en formato JSON:\n"
                    '{{"tables": [{{"dimension": "...", "rows": [{{"property": "...", '
                    '"documents": {{"doc1": "evidencia", "doc2": "..."}}}}]}}]}}'
                ),
            },
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    content = (
        response.get("content", "{}") if isinstance(response, dict) else str(response)
    )
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"tables": [], "raw": content}


# ═══════════════════════════════════════════════════════════════════════
# Step 3: Correlate — 2x2 matrices with the 12 theoretical families
# ═══════════════════════════════════════════════════════════════════════


def _step_correlate(simplified: dict, cat_name: str, proyecto_id: str) -> dict:
    """PRO: Generate 2x2 matrices + typologies from simplified tables.

    Uses the 12 Glaserian theoretical families as correlation lenses.
    """
    # Load theoretical families for correlation prompts
    session = SessionLocal()
    try:
        families = session.execute(
            text(
                "SELECT name, family, layer, description FROM theoretical_codes "
                "WHERE project_id IS NULL AND glaserian = true"
            )
        ).fetchall()
    finally:
        session.close()

    family_lenses = (
        "\n".join(f"- {r[0]} ({r[1]}): {r[3][:100]}" for r in families)
        if families
        else "(12 familias built-in)"
    )

    response = llm._call_llm(
        tier="PRO",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un correlador de memos para Classic Grounded Theory. "
                    "A partir de tablas de doble entrada, identifica patrones "
                    "transversales usando las 12 familias de codigos teoricos de Glaser. "
                    "Produce:\n"
                    "1. Matrices 2x2: cruza dos dimensiones → 4 cuadrantes con tipologias\n"
                    "2. Correlaciones: que familias teoricas aplican a este memo\n\n"
                    "Responde SOLO en JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Categoria: {cat_name}\n\n"
                    f"Tablas simplificadas:\n{json.dumps(simplified, ensure_ascii=False)}\n\n"
                    f"Familias teoricas disponibles:\n{family_lenses}\n\n"
                    "Produce matrices 2x2 y correlaciones teoricas en JSON:\n"
                    '{{"matrices": [{{"dimension_a": "...", "dimension_b": "...", '
                    '"quadrants": [{{"label": "...", "properties": [...]}}]}}], '
                    '"family_correlations": [{{"family": "...", "relevance": 0.8, '
                    '"rationale": "..."}}]}}'
                ),
            },
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    content = (
        response.get("content", "{}") if isinstance(response, dict) else str(response)
    )
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"matrices": [], "family_correlations": [], "raw": content}
