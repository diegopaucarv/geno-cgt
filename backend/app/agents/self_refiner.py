"""SelfRefinementLoop: patrón Generate → Critic → Refine → Converge.

El LLM genera output, se auto-evalúa, corrige, y repite hasta
que todos los criterios de calidad se cumplen.

Usa PRO para generar y FLASH para el critic (más barato).
Incluye preservación de reasoning_content para DeepSeek V4 Pro.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class SelfRefinementLoop(BaseAgent):
    """
    Bucle de auto-refinamiento genérico.

    Ideal para tareas donde calidad > velocidad:
    - Generación de códigos (B2b)
    - Síntesis de map-reduce
    - Redacción de definiciones
    """

    def __init__(
        self,
        agent_id: str,
        llm_client: Any,
        generate_prompt_id: str,
        critic_prompt_id: str,
        max_iterations: int = 3,
        timeout_seconds: float = 300.0,
    ):
        super().__init__(agent_id, llm_client, max_iterations, timeout_seconds)
        self.generate_prompt_id = generate_prompt_id
        self.critic_prompt_id = critic_prompt_id

    def _build_system_prompt(self, **kwargs) -> str:
        return kwargs.get(
            "system_prompt",
            "Eres un agente que mejora iterativamente su output.",
        )

    def _step(self, history: list[dict], iteration: int, **kwargs) -> dict:
        # ── 1. GENERATE (PRO — razona internamente) ──────────────
        gen_response = self.llm.run_agent(
            self.generate_prompt_id,
            variables=kwargs.get("generate_vars", {}),
        )

        # ⚠️ CLAVE: Preservar reasoning_content para que el modelo
        # no pierda el contexto de su reflexión entre iteraciones.
        gen_text = json.dumps(gen_response, ensure_ascii=False)
        assistant_msg = self._build_assistant_message(gen_text, gen_response)
        history.append(assistant_msg)

        had_reasoning = bool(gen_response.get("_reasoning_content"))

        # ── 2. ALGORITHMIC CHECK (O6: regex + heuristics, no LLM) ──
        codes = gen_response.get("codes", [])
        coding_style = kwargs.get("coding_style", "gerundio")

        from app.agents.quality.scorer import (
            compare_codes_for_redundancy,
            evaluate_codes_algorithmic,
        )

        algo_eval = evaluate_codes_algorithmic(codes, coding_style)
        redundancy_issues = compare_codes_for_redundancy(codes)
        algo_eval["issues"].extend(redundancy_issues)
        if redundancy_issues:
            algo_eval["all_valid"] = False

        # If algorithmic check passes, skip LLM critic entirely
        if algo_eval["all_valid"]:
            return {
                "type": "refinement_step",
                "iteration": iteration,
                "output": gen_response,
                "critic": algo_eval,
                "is_valid": True,
                "issues": [],
                "had_reasoning": had_reasoning,
                "critic_source": "algorithmic",
            }

        # ── 3. LLM CRITIC (FLASH) — only for qualitative issues ────
        critic_vars = {
            **kwargs.get("critic_vars", {}),
            "output_to_evaluate": gen_text,
            "algorithmic_issues": json.dumps(algo_eval["issues"], ensure_ascii=False),
        }
        critic_response = self.llm.run_agent(
            self.critic_prompt_id,
            variables=critic_vars,
            temperature=0.1,
        )

        is_valid = critic_response.get("all_valid", False)
        issues = critic_response.get("issues", [])

        if not is_valid and issues:
            # Feedback para la próxima iteración
            history.append(
                {
                    "role": "user",
                    "content": (
                        f"Iteration {iteration} issues: "
                        f"{json.dumps(issues, ensure_ascii=False)[:500]}\n"
                        "Refiná los códigos con problemas."
                    ),
                }
            )

        return {
            "type": "refinement_step",
            "iteration": iteration,
            "output": gen_response,
            "critic": critic_response,
            "is_valid": is_valid,
            "issues": issues,
            "had_reasoning": had_reasoning,
        }

    def _should_stop(self, step_result: dict) -> bool:
        return step_result.get("is_valid", False)

    def _extract_result(self, step_result: dict) -> dict:
        return step_result.get("output", {})
