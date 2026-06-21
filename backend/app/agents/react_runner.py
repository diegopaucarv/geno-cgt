"""ReactRunner: motor genérico de bucle ReAct.

Thought → Action → Observation → Thought → ... → FinalAnswer

El LLM razona, decide qué herramienta llamar, el sistema la ejecuta,
y el resultado se devuelve como Observation. El bucle continúa hasta
que el LLM emite FinalAnswer.

Soporta dos modos:
- Text parsing (Thought:/Action:/Action Input:) — default
- Native function calling (tools parameter) — con AGENTIC_NATIVE_FC=true
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ReactRunner(BaseAgent):
    """Motor ReAct genérico con preservación de reasoning_content."""

    def __init__(
        self,
        agent_id: str,
        llm_client: Any,
        tool_registry: ToolRegistry,
        max_iterations: int = 5,
        timeout_seconds: float = 300.0,
        use_native_fc: bool = False,
    ):
        super().__init__(agent_id, llm_client, max_iterations, timeout_seconds)
        self.tools = tool_registry
        self.use_native_fc = use_native_fc
        self._conversation: list[dict[str, Any]] = []

    def _build_system_prompt(self, **kwargs) -> str:
        tools_schema = self.tools.get_schema_for_prompt()
        return f"""[ROL]
{kwargs.get("role_description", "Eres un agente ReAct. Pensá paso a paso y usá herramientas cuando necesites información adicional.")}

[FORMATO DE RESPUESTA]
Respondé SIEMPRE en este formato exacto:

Thought: [Tu razonamiento sobre qué hacer ahora]
Action: [Nombre de la herramienta, o "FinalAnswer"]
Action Input: [Input JSON para la herramienta]

Cuando tengas la respuesta final:
Thought: [Por qué es la respuesta correcta]
FinalAnswer: {{...}}

[HERRAMIENTAS DISPONIBLES]
{tools_schema}

[REGLAS]
- Usá las herramientas para obtener datos, no inventes.
- Si una herramienta falla, intentá otra aproximación.
- No uses más de {self.max_iterations} pasos.
"""

    def _step(self, history: list[dict], iteration: int, **kwargs) -> dict:
        # 1. LLM decide el siguiente paso
        response = self.llm.chat(
            messages=history
            + [{"role": "user", "content": "¿Cuál es el siguiente paso?"}],
            temperature=0.3,
        )

        content = response.get("content", "")
        reasoning = response.get("reasoning_content", "")
        tokens = response.get("usage", {}).get("total_tokens", 0)

        # 2. Parsear respuesta
        parsed = self._parse_react(content)

        if "final_answer" in parsed:
            return {
                "type": "final",
                "iteration": iteration,
                "output": parsed["final_answer"],
                "thought": parsed.get("thought", ""),
                "tokens": tokens,
                "had_reasoning": bool(reasoning),
            }

        # 3. Ejecutar tool
        tool_name = parsed.get("action", "")
        tool_input = parsed.get("action_input", {})
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except json.JSONDecodeError:
                tool_input = {"query": tool_input}

        observation = self.tools.execute(tool_name, tool_input)

        # 4. Guardar en historial preservando reasoning
        assistant_msg = self._build_assistant_message(content, response)
        history.append(assistant_msg)
        history.append(
            {
                "role": "user",
                "content": f"Observation: {observation}",
            }
        )

        return {
            "type": "tool_call",
            "iteration": iteration,
            "thought": parsed.get("thought", ""),
            "action": tool_name,
            "action_input": tool_input,
            "observation": observation[:500],
            "tokens": tokens,
            "had_reasoning": bool(reasoning),
        }

    def _should_stop(self, step_result: dict) -> bool:
        return step_result.get("type") == "final"

    def _extract_result(self, step_result: dict) -> dict:
        return step_result.get("output", {})

    # ── Override run() to capture conversation history ─────────────

    def run(self, project_id: str, **kwargs) -> AgentResult:
        """Override BaseAgent.run() to capture full conversation history.

        Returns:
            AgentResult with data._conversation containing all messages.
        """
        import time as _time

        started_at = _time.time()
        self._conversation = []
        trace: list[dict[str, Any]] = []
        total_tokens = 0
        had_reasoning = False

        # Build system prompt
        system_content = self._build_system_prompt(**kwargs)
        history: list[dict[str, Any]] = [
            {"role": "system", "content": system_content}
        ]
        self._conversation.append({"role": "system", "content": system_content})

        for iteration in range(1, self.max_iterations + 1):
            if _time.time() - started_at > self.timeout_seconds:
                return AgentResult(
                    success=False,
                    error=f"Timeout after {self.timeout_seconds}s",
                    iterations=iteration,
                    total_tokens=total_tokens,
                    had_reasoning=had_reasoning,
                    trace=trace,
                )

            try:
                # Track user prompt (passed inline by _step to LLM)
                user_prompt = {"role": "user", "content": "Cual es el siguiente paso?"}
                self._conversation.append(user_prompt)

                # Remember history length before step
                hist_len_before = len(history)

                step_result = self._step(history, iteration, **kwargs)
                trace.append(step_result)
                total_tokens += step_result.get("tokens", 0)
                if step_result.get("had_reasoning"):
                    had_reasoning = True

                # Capture new messages added to history by _step
                new_messages = history[hist_len_before:]
                self._conversation.extend(new_messages)

                if self._should_stop(step_result):
                    result = AgentResult(
                        success=True,
                        data=self._extract_result(step_result),
                        iterations=iteration,
                        total_tokens=total_tokens,
                        had_reasoning=had_reasoning,
                        trace=trace,
                    )
                    # Attach conversation to result data
                    result.data["_conversation"] = list(self._conversation)
                    return result
            except Exception as e:
                logger.error(
                    "Agent %s iteration %d failed: %s", self.agent_id, iteration, e
                )
                return AgentResult(
                    success=False,
                    error=str(e),
                    iterations=iteration,
                    total_tokens=total_tokens,
                    had_reasoning=had_reasoning,
                    trace=trace,
                )

        return AgentResult(
            success=False,
            error=f"Max iterations ({self.max_iterations}) reached without convergence",
            iterations=self.max_iterations,
            total_tokens=total_tokens,
            had_reasoning=had_reasoning,
            trace=trace,
        )

    # ── Parsing ──────────────────────────────────────────────────

    @staticmethod
    def _parse_react(text: str) -> dict[str, Any]:
        """Parsea el formato Thought/Action/FinalAnswer del LLM.

        Tolera variaciones de formato comunes en modelos de razonamiento.
        """
        result: dict[str, Any] = {}

        # Thought
        thought_match = re.search(
            r"Thought:\s*(.+?)(?=\n(?:Action:|FinalAnswer:)|\Z)",
            text,
            re.DOTALL,
        )
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        # FinalAnswer (termina el bucle, balanced brackets)
        final_start = text.find("FinalAnswer:")
        if final_start >= 0:
            brace_pos = text.find("{", final_start)
            if brace_pos >= 0:
                json_str = ReactRunner._extract_balanced_json(text, brace_pos)
                if json_str:
                    try:
                        result["final_answer"] = json.loads(json_str)
                    except json.JSONDecodeError:
                        result["final_answer"] = {"raw": json_str}
                    return result

        # Action
        action_match = re.search(r"Action:\s*(.+?)(?=\n|\Z)", text)
        if action_match:
            result["action"] = action_match.group(1).strip()

        # Action Input (JSON, balanced brackets)
        input_start = text.find("Action Input:")
        if input_start >= 0:
            brace_pos = text.find("{", input_start)
            if brace_pos >= 0:
                json_str = ReactRunner._extract_balanced_json(text, brace_pos)
                if json_str:
                    try:
                        result["action_input"] = json.loads(json_str)
                    except json.JSONDecodeError:
                        result["action_input"] = {"raw": json_str}

        return result

    @staticmethod
    def _extract_balanced_json(text: str, start: int) -> str | None:
        """Extrae un objeto JSON usando balanced bracket matching.

        Soporta JSON anidado, strings con backslashes, etc.
        Mucho mas robusto que regex lazy para JSON complejo.
        """
        if start >= len(text) or text[start] != "{":
            return None

        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            ch = text[i]

            if escape:
                escape = False
                continue

            if ch == "\\":
                escape = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None
