"""
B3 — Label Critic (FLASH, structured evaluation).

Evalúa UNA etiqueta propuesta por el pattern_labeler (B2) contra sus
incidentes fuente. FLASH — solo evalúa, no genera.

Retorna issues si la etiqueta tiene problemas; array vacío si es correcta.

Usado tanto en el SelfRefinement loop de B2 (concepto por concepto)
como standalone para evaluación post-hoc.

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
        groups_json: JSON string con los incidentes fuente del grupo.
        labels_json: JSON string con la(s) etiqueta(s) a evaluar.

    Returns:
        dict con:
          - issues: list[dict] — [{label, description, suggestion}]
            Empty issues array = labels are good.
    """
    try:
        response = llm.run_agent(
            agent_id="fb_label_critic",
            variables={
                "output_to_evaluate": labels_json,
                "source_incidents": groups_json,
            },
            temperature=0.1,
        )

        issues = response.get("issues", [])

        logger.info(
            "B3 critique: %d issues found",
            len(issues),
        )

        return {
            "issues": issues,
        }

    except Exception:
        logger.exception("B3 critique_labels failed")
        raise
