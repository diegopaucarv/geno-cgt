"""PlanExecutor: patrón Plan-and-Execute.

Planificar → Ejecutar → Evaluar → Replanificar (si es necesario)

A diferencia de ReAct (paso a paso), este agente primero elabora
un plan completo, luego ejecuta cada paso, y evalúa el resultado.
Ideal para tareas multi-step con visión global:
- Codificación de un proyecto entero
- Elaboración selectiva (Fase 5b)
- Saturation analysis (4 fuentes)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class PlanExecutor(BaseAgent):
    """Motor Plan-and-Execute genérico.

    1. PLANIFICA: el LLM elabora un plan completo (lista de steps)
    2. EJECUTA: el sistema ejecuta cada step con tools
    3. EVALÚA: el LLM revisa el resultado y decide si replanificar
    4. REPITE desde 1 si es necesario
    """

    def __init__(
        self,
        agent_id: str,
        llm_client: Any,
        tool_registry: ToolRegistry,
        max_plan_cycles: int = 3,
        timeout_seconds: float = 600.0,
    ):
        super().__init__(agent_id, llm_client, max_plan_cycles, timeout_seconds)
        self.tools = tool_registry
        self.max_plan_cycles = max_plan_cycles

    def _build_system_prompt(self, **kwargs) -> str:
        tools_schema = self.tools.get_schema_for_prompt()
        return f"""[ROL]
{kwargs.get("role_description", "Eres un agente planificador. Primero elaborá un plan, después ejecutalo.")}

[FORMATO DEL PLAN]
Cuando te pida que planifiques, respondé en JSON:
{{
  "goal": "objetivo en una frase",
  "steps": [
    {{"id": 1, "action": "nombre_de_tool_o_LLM", "description": "qué hace este paso", "input": {{...}} }},
    ...
  ],
  "success_criteria": "cómo sabré que el plan funcionó"
}}

[HERRAMIENTAS DISPONIBLES]
{tools_schema}

[ACCIONES SIN TOOL]
Además de las herramientas, podés usar estas acciones:
- "generate_codes": el LLM genera códigos (sin tool)
- "generate_hypotheses": el LLM genera hipótesis (sin tool)
- "evaluate_result": el LLM evalúa el resultado (sin tool)

[REGLAS]
- Planificá ANTES de ejecutar.
- Cada step debe usar una herramienta o ser una acción LLM.
- Si un step falla, ajustá el plan y reintentá.
- No uses más de {self.max_plan_cycles} ciclos de planificación.
"""

    def _step(self, history: list[dict], iteration: int, **kwargs) -> dict:
        # ── FASE 1: PLANIFICAR ───────────────────────────────────
        plan_response = self.llm.chat(
            messages=history
            + [
                {
                    "role": "user",
                    "content": (
                        f"Objetivo: {kwargs.get('goal', 'Completar la tarea')}\n\n"
                        f"Estado actual:\n{kwargs.get('state_summary', '')}\n\n"
                        "Elaborá un PLAN detallado para lograr el objetivo."
                    ),
                }
            ],
            temperature=0.3,
        )

        plan = self._parse_json(plan_response.get("content", ""))
        steps = plan.get("steps", [])
        goal = plan.get("goal", kwargs.get("goal", ""))

        logger.info(
            "PlanExecutor cycle %d: goal=%s steps=%d", iteration, goal, len(steps)
        )

        if not steps:
            return {
                "type": "error",
                "iteration": iteration,
                "error": "No steps in plan",
            }

        # Guardar plan en historial preservando reasoning
        plan_msg = self._build_assistant_message(
            json.dumps(plan, ensure_ascii=False), plan_response
        )
        history.append(plan_msg)

        # ── FASE 2: EJECUTAR ─────────────────────────────────────
        results: list[dict[str, Any]] = []
        for step in steps:
            action = step.get("action", "")
            step_input = step.get("input", {})

            if action in ("generate_codes", "generate_hypotheses", "evaluate_result"):
                # Acción LLM (sin tool)
                llm_response = self.llm.run_agent(
                    agent_id=action,
                    variables=step_input,
                )
                results.append(
                    {
                        "step_id": step["id"],
                        "action": action,
                        "output": llm_response,
                        "status": "ok",
                    }
                )
            elif action in self.tools:
                # Acción tool
                try:
                    observation = self.tools.execute(action, step_input)
                    parsed_obs = (
                        json.loads(observation)
                        if isinstance(observation, str)
                        else observation
                    )
                    results.append(
                        {
                            "step_id": step["id"],
                            "action": action,
                            "output": parsed_obs,
                            "status": "ok",
                        }
                    )
                except Exception as e:
                    logger.warning(
                        "Plan step %s (%s) failed: %s", step["id"], action, e
                    )
                    results.append(
                        {
                            "step_id": step["id"],
                            "action": action,
                            "error": str(e),
                            "status": "error",
                        }
                    )
            else:
                results.append(
                    {
                        "step_id": step["id"],
                        "action": action,
                        "error": f"Unknown action: {action}",
                        "status": "error",
                    }
                )

        # ── FASE 3: EVALUAR ──────────────────────────────────────
        eval_response = self.llm.chat(
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Plan ejecutado. Resultados:\n"
                        f"{json.dumps(results, ensure_ascii=False, indent=2)[:3000]}\n\n"
                        f"Criterio de éxito: {plan.get('success_criteria', '')}\n\n"
                        "¿El plan logró el objetivo? Respondé en JSON:\n"
                        '{"goal_achieved": true/false, "assessment": "...", "missing": "..."}'
                    ),
                }
            ],
            temperature=0.1,
        )

        eval_result = self._parse_json(eval_response.get("content", ""))
        goal_achieved = eval_result.get("goal_achieved", False)

        if goal_achieved:
            return {
                "type": "final",
                "iteration": iteration,
                "output": results,
                "plan": plan,
                "evaluation": eval_result,
            }

        # ── REPLANIFICAR (el próximo ciclo lo hará) ──────────────
        history.append(
            {
                "role": "user",
                "content": (
                    f"El plan no logró el objetivo. "
                    f"Resultados: {json.dumps(results, ensure_ascii=False)[:1000]}. "
                    f"Evaluación: {eval_result.get('assessment', '')}. "
                    f"Lo que falta: {eval_result.get('missing', '')}. "
                    f"Replanificá."
                ),
            }
        )

        return {
            "type": "replan",
            "iteration": iteration,
            "results": results,
            "evaluation": eval_result,
        }

    def _should_stop(self, step_result: dict) -> bool:
        return step_result.get("type") == "final"

    def _extract_result(self, step_result: dict) -> dict:
        return {
            "plan": step_result.get("plan", {}),
            "results": step_result.get("output", []),
            "evaluation": step_result.get("evaluation", {}),
        }

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Extrae JSON de texto, tolerando markdown fences y texto alrededor."""
        text = text.strip()
        # Quitar markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Buscar primer objeto JSON en el texto
            match = re.search(r"\{.+\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {"error": "JSON parse failed", "raw": text[:200]}
