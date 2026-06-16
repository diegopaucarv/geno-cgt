"""Agentic Architecture Layer for GT System.

Proporciona:
- BaseAgent: clase base abstracta para todos los bucles agenciales
- ToolRegistry: registro centralizado de herramientas para agentes
- AgentResult: resultado unificado de cualquier agente
- AgentLoopLog: log de traceabilidad para DB

Patrones implementados:
- SelfRefinementLoop: Generate → Critic → Refine → Converge
- ReactRunner: Thought → Action → Observation → ... → FinalAnswer
- PlanExecutor: Plan → Execute → Evaluate → Replan
"""

from app.agents.base import AgentLoopLog, AgentResult, BaseAgent
from app.agents.exceptions import AgentAbortedError, TaskCancelledError
from app.agents.orchestrator import OrchestratorRuleEngine
from app.agents.plan_executor import PlanExecutor
from app.agents.react_runner import ReactRunner
from app.agents.self_refiner import SelfRefinementLoop
from app.agents.tool_registry import ToolRegistry, tool

__all__ = [
    "AgentAbortedError",
    "AgentLoopLog",
    "AgentResult",
    "BaseAgent",
    "OrchestratorRuleEngine",
    "PlanExecutor",
    "ReactRunner",
    "SelfRefinementLoop",
    "TaskCancelledError",
    "ToolRegistry",
    "tool",
]
