"""
B3 — Label Critic (FLASH, structured evaluation).

Evalúa etiquetas propuestas por el pattern_labeler (B2).
Emite veredictos SAT | MOD | FORCED para cada etiqueta.

FLASH: 10x más barato que PRO. Solo evalúa, no genera.

Usado tanto en el SelfRefinement loop de B2 como standalone
para evaluación post-hoc.

See AGENTES.md §label_critic for I/O spec.
"""

from __future__ import annotations

import logging

from llm_client import LLMClient

logger = logging.getLogger(__name__)
llm = LLMClient()


def b3_critique_labels(groups_json: str, labels_json: str) -> dict:
    """Evalúa etiquetas propuestas contra los incidentes fuente.

    FLASH — structured evaluation. No generation.

    Args:
        groups_json: JSON string con los grupos de incidentes fuente.
        labels_json: JSON string con las etiquetas propuestas a evaluar.

    Returns:
        dict con:
          - all_valid: bool — true si TODAS las etiquetas son SAT.
          - issues: list[dict] — [{label, verdict: SAT|MOD|FORCED, type, description}]
          - summary: dict — {total, sat, mod, forced}
    """
    try:
        response = llm.run_agent(
            agent_id="label_critic",
            variables={
                "output_to_evaluate": labels_json,
                "source_incidents": groups_json,
            },
            temperature=0.1,
        )

        all_valid = response.get("all_valid", False)
        issues = response.get("issues", [])

        # ── Calcular summary ───────────────────────────────────────
        sat_count = sum(1 for i in issues if i.get("verdict") == "SAT")
        mod_count = sum(1 for i in issues if i.get("verdict") == "MOD")
        forced_count = sum(1 for i in issues if i.get("verdict") == "FORCED")
        total = len(issues)

        logger.info(
            "B3 critique: %d labels — %d SAT, %d MOD, %d FORCED, all_valid=%s",
            total,
            sat_count,
            mod_count,
            forced_count,
            all_valid,
        )

        return {
            "all_valid": all_valid,
            "issues": issues,
            "summary": {
                "total": total,
                "sat": sat_count,
                "mod": mod_count,
                "forced": forced_count,
            },
        }

    except Exception:
        logger.exception("B3 critique_labels failed")
        raise
