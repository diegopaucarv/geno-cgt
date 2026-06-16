"""BaseAgent: template method para bucles agenciales.

Proporciona la infraestructura común para todos los patrones:
- SelfRefinementLoop (Generate → Critic → Refine)
- ReactRunner (Thought → Action → Observation)
- PlanExecutor (Plan → Execute → Evaluate)

Cada subclase solo implementa _build_system_prompt(), _step(),
_should_stop(), y _extract_result().
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Resultado unificado de cualquier agente."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    iterations: int = 0
    total_tokens: int = 0
    total_cost_est: float = 0.0
    had_reasoning: bool = False
    trace: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class AgentLoopLog:
    """Log de traceabilidad de un bucle agencial (para DB)."""

    agent_id: str
    project_id: str
    started_at: str
    finished_at: str
    iterations: int
    total_tokens: int
    had_reasoning: bool
    tool_calls: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    result_summary: str
    error: str | None = None


class BaseAgent:
    """Template Method para agentes con bucle.

    Subclases implementan:
    - _build_system_prompt(**kwargs) → str
    - _step(history, iteration, **kwargs) → dict
    - _should_stop(step_result) → bool
    - _extract_result(step_result) → dict
    """

    def __init__(
        self,
        agent_id: str,
        llm_client: Any,
        max_iterations: int = 5,
        timeout_seconds: float = 300.0,
    ):
        self.agent_id = agent_id
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds

    def run(self, project_id: str, **kwargs) -> AgentResult:
        """Template method: ejecuta el bucle agencial."""
        started_at = time.time()
        trace: list[dict[str, Any]] = []
        total_tokens = 0
        had_reasoning = False
        history: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt(**kwargs)}
        ]

        for iteration in range(1, self.max_iterations + 1):
            if time.time() - started_at > self.timeout_seconds:
                return AgentResult(
                    success=False,
                    error=f"Timeout after {self.timeout_seconds}s",
                    iterations=iteration,
                    total_tokens=total_tokens,
                    had_reasoning=had_reasoning,
                    trace=trace,
                )

            try:
                step_result = self._step(history, iteration, **kwargs)
                trace.append(step_result)
                total_tokens += step_result.get("tokens", 0)
                if step_result.get("had_reasoning"):
                    had_reasoning = True

                if self._should_stop(step_result):
                    return AgentResult(
                        success=True,
                        data=self._extract_result(step_result),
                        iterations=iteration,
                        total_tokens=total_tokens,
                        had_reasoning=had_reasoning,
                        trace=trace,
                    )
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

    # ── Abstract methods ──────────────────────────────────────────

    def _build_system_prompt(self, **kwargs) -> str:
        raise NotImplementedError

    def _step(self, history: list[dict], iteration: int, **kwargs) -> dict:
        raise NotImplementedError

    def _should_stop(self, step_result: dict) -> bool:
        raise NotImplementedError

    def _extract_result(self, step_result: dict) -> dict:
        raise NotImplementedError

    # ── Helpers ───────────────────────────────────────────────────

    def _log_loop(self, project_id: str, result: AgentResult) -> None:
        """Persiste AgentLoopLog en DB (opcional, para traceabilidad)."""
        try:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).isoformat()
            self._loop_log = AgentLoopLog(
                agent_id=self.agent_id,
                project_id=project_id,
                started_at=now,
                finished_at=now,
                iterations=result.iterations,
                total_tokens=result.total_tokens,
                had_reasoning=result.had_reasoning,
                tool_calls=[t for t in result.trace if t.get("type") == "tool_call"],
                llm_calls=[t for t in result.trace if t.get("type") == "llm_call"],
                result_summary=str(result.data)[:500],
                error=result.error,
            )
            logger.info(
                "AgentLoopLog: %s iterations=%d tokens=%d reasoning=%s",
                self.agent_id,
                result.iterations,
                result.total_tokens,
                result.had_reasoning,
            )
        except Exception as e:
            logger.warning("Failed to persist AgentLoopLog: %s", e)

    @staticmethod
    def _build_assistant_message(
        content: str, response: dict[str, Any]
    ) -> dict[str, Any]:
        """Construye un mensaje assistant preservando reasoning_content.

        CRÍTICO para DeepSeek V4 Pro: si el modelo generó razonamiento
        interno (reasoning_content), DEBE incluirse en el historial
        para que el agente no pierda el contexto de su reflexión.
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        reasoning = response.get("reasoning_content")
        if reasoning:
            msg["reasoning_content"] = reasoning
        return msg
