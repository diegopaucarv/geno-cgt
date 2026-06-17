"""F5.3 — Redacción Natural (Fase 6a): natural_writer, writing_critic, gap_feeler.

Triada de agentes para redacción teórica en Classic Grounded Theory:
  1. write_section (PRO): Redacta secciones desde pilas de memos ordenados
  2. critique_section (PRO): Evalúa borradores contra reglas CGT
  3. feel_gaps (FLASH): Monitorea escritura en background, detecta huecos

Refs: 3-memomaker.md §5, kb.md §9, AGENTES.md Fase 6a.
"""

from __future__ import annotations

import logging
import os

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


# ═══════════════════════════════════════════════════════════════════════
# Public API — Fase 6a Writing Engine
# ═══════════════════════════════════════════════════════════════════════


def write_section(sorting_group_id: str, proyecto_id: str) -> dict:
    """Redacta una sección teórica a partir de una pila de memos ordenados (PRO).

    Lee los memos del sorting group (F0.2), los envía al natural_writer
    y retorna un borrador con citas, conceptos y memos huérfanos.

    Returns:
        dict con {draft, citations[], concepts[], orphan_memos[]}
    """
    session = SessionLocal()
    try:
        # ── Load sorting group ──
        group = session.execute(
            text(
                "SELECT msg.memos_json, msg.attempt_id, msa.proyecto_id "
                "FROM memo_sorting_groups msg "
                "JOIN memo_sorting_attempts msa ON msg.attempt_id = msa.id "
                "WHERE msg.id = :gid"
            ),
            {"gid": sorting_group_id},
        ).fetchone()

        if not group:
            return {
                "error": "Sorting group not found",
                "sorting_group_id": sorting_group_id,
            }

        memo_ids = group[0]  # memos_json: list[str] of UUIDs
        if not memo_ids:
            return {
                "error": "Sorting group has no memos",
                "sorting_group_id": sorting_group_id,
            }

        # ── Load memo contents ──
        memos_ordered = _load_memos_for_writing(session, memo_ids)

        # ── Load researcher instructions from proyecto ──
        instructions = _load_project_instructions(session, proyecto_id)

        # ── Call natural_writer (PRO) ──
        logger.info(
            "Writer: drafting section for group %s (%d memos)",
            sorting_group_id[:8],
            len(memo_ids),
        )

        variables = {
            "memos_ordered": memos_ordered,
            "researcher_instructions": instructions,
            "section_structure": (
                "1. Concepto central (gerundio)\n"
                "2. Propiedades y dimensiones\n"
                "3. Condiciones causales\n"
                "4. Estrategias y consecuencias\n"
                "5. Relaciones con otras categorías"
            ),
        }

        response = llm.run_agent(
            agent_id="natural_writer",
            variables=variables,
            max_tokens=4000,
            temperature=0.3,
        )

        # ── Parse response ──
        draft = response.get("draft", "")
        citations = response.get("citations", [])
        concepts = response.get("concepts", [])
        orphan_memos = response.get("orphan_memos", [])

        logger.info(
            "Writer: section drafted — %d chars, %d citations, %d concepts, %d orphans",
            len(draft),
            len(citations),
            len(concepts),
            len(orphan_memos),
        )

        return {
            "draft": draft,
            "citations": citations,
            "concepts": concepts,
            "orphan_memos": orphan_memos,
        }

    except Exception:
        logger.exception("write_section failed for group %s", sorting_group_id)
        return {"error": "write_section failed", "sorting_group_id": sorting_group_id}
    finally:
        session.close()


def critique_section(draft: str, memo_ids: list[str], proyecto_id: str) -> dict:
    """Evalúa un borrador contra reglas CGT (PRO).

    Verifica: tiempo verbal, conceptos vs personas, dosis de citas,
    fidelidad a memos fuente, y progresión de abstracción.

    Returns:
        dict con {verdict: SAT|MOD|FORCED, issues[{type, location, suggestion, severity}]}
    """
    session = SessionLocal()
    try:
        # ── Load source memos for fidelity verification ──
        source_memos = _load_memos_for_writing(session, memo_ids)

        # ── Call writing_critic (PRO) ──
        logger.info(
            "Critic: evaluating draft (%d chars) against %d source memos",
            len(draft),
            len(memo_ids),
        )

        variables = {
            "draft": draft,
            "source_memos": source_memos,
        }

        response = llm.run_agent(
            agent_id="writing_critic",
            variables=variables,
            max_tokens=3000,
            temperature=0.2,
        )

        verdict = response.get("verdict", "MOD")
        issues = response.get("issues", [])
        summary = response.get("summary", "")

        logger.info(
            "Critic: verdict=%s, %d issues found",
            verdict,
            len(issues),
        )

        return {
            "verdict": verdict,
            "issues": issues,
            "summary": summary,
        }

    except Exception:
        logger.exception("critique_section failed for project %s", proyecto_id)
        return {"error": "critique_section failed", "proyecto_id": proyecto_id}
    finally:
        session.close()


def feel_gaps(draft: str, project_id: str) -> list[dict]:
    """Monitorea la escritura en background detectando huecos (FLASH).

    Detecta tres tipos de gaps:
      1. Claims sin respaldo en memos (afirmaciones sin evidencia)
      2. Transiciones débiles (saltos abruptos entre conceptos)
      3. Propiedades unipolares (dimensiones sin contraparte)

    Returns:
        [{type, description, severity}]
    """
    try:
        logger.info("GapFeeler: scanning draft (%d chars) for gaps", len(draft))

        flash_model = os.getenv("MODEL_FLASH", "google/gemma-4-31B-it")

        response = llm._call_llm(
            tier="FLASH",
            model=flash_model,
            system_prompt=(
                "Eres un detector de huecos teóricos para Classic Grounded Theory. "
                "Escaneas borradores de secciones teóricas en busca de:\n\n"
                "1. **Claims sin backing**: Afirmaciones que no tienen evidencia "
                "en memos o incidentes. Indica qué se afirma sin respaldo.\n"
                "2. **Transiciones débiles**: Saltos abruptos entre conceptos "
                "sin conectores lógicos. Indica la ubicación del salto.\n"
                "3. **Propiedades unipolares**: Dimensiones mencionadas solo "
                "en un extremo (ej: 'alto' sin 'bajo'). Indica la propiedad.\n\n"
                "Responde SOLO en JSON."
            ),
            schema={
                "type": "object",
                "properties": {
                    "gaps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "claim_without_backing",
                                        "weak_transition",
                                        "unipolar_property",
                                    ],
                                },
                                "description": {"type": "string"},
                                "severity": {
                                    "type": "string",
                                    "enum": ["critical", "major", "minor"],
                                },
                            },
                            "required": ["type", "description", "severity"],
                        },
                    }
                },
                "required": ["gaps"],
            },
            max_tokens=2048,
            temperature=0.1,
        )

        gaps = response.get("gaps", [])
        logger.info("GapFeeler: %d gaps detected in background scan", len(gaps))
        return gaps

    except Exception:
        logger.exception("feel_gaps failed (non-blocking, swallowing)")
        return []


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _load_memos_for_writing(session, memo_ids: list[str]) -> str:
    """Load memo contents as a formatted string for the writer/critic prompts."""
    if not memo_ids:
        return "(no memos provided)"

    placeholders = ", ".join(f":m{i}" for i in range(len(memo_ids)))
    params = {f"m{i}": mid for i, mid in enumerate(memo_ids)}

    rows = session.execute(
        text(
            f"SELECT id, contenido, tipo, version FROM memos "
            f"WHERE id IN ({placeholders})"
        ),
        params,
    ).fetchall()

    if not rows:
        return "(no memos found)"

    parts = []
    for i, row in enumerate(rows):
        memo_id = str(row[0])
        content = (row[1] or "")[:2000]  # Truncate para no saturar el prompt
        tipo = row[2] or "MEMO"
        version = row[3] or 1
        parts.append(
            f"--- Memo {i + 1} [{tipo} v{version}] (id: {memo_id[:8]}) ---\n{content}\n"
        )

    return "\n".join(parts)


def _load_project_instructions(session, proyecto_id: str) -> str:
    """Load researcher instructions from the project record.

    Falls back to default CGT instructions if none configured.
    """
    # Intentar cargar instrucciones específicas del proyecto si existen
    row = session.execute(
        text(
            "SELECT COALESCE(supuesto_poblacional, '') FROM proyectos WHERE id = :pid"
        ),
        {"pid": proyecto_id},
    ).fetchone()

    poblacional = (row[0] or "").strip() if row else ""

    base = (
        "Redacta en presente conceptual. Usa gerundios. "
        "Cada afirmación debe rastrearse a un memo fuente. "
        "El sujeto de cada oración es un concepto, no una persona."
    )

    if poblacional:
        return f"{base}\nContexto poblacional: {poblacional}"
    return base
