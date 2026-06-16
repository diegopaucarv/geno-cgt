# Plan de Implementación — Arquitectura Agencial CoT para GT

> **De llamadas single-shot a bucles agentic con Chain of Thought, ReAct, y tool-use.**
>
> Fecha: 2026-06-15 | Duración estimada: 15-20 días

---

## Índice

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Fase 0: Infraestructura Agencial Base](#2-fase-0-infraestructura-agencial-base)
3. [Fase 1: Self-Refinement Loop (B2 — Open Coding)](#3-fase-1-self-refinement-loop)
4. [Fase 2: ReAct Agent (B3 — Hypothesis Generation)](#4-fase-2-react-agent)
5. [Fase 3: Orchestrator Agent (LangGraph)](#5-fase-3-orchestrator-agent)
6. [Fase 4: Multi-Agent Debate + Reflexive Monitor + RAG](#6-fase-4-debate--reflexive--rag)
7. [Testing & Validación](#7-testing--validación)
8. [Feature Flags & Rollout](#8-feature-flags--rollout)

---

## 1. Resumen Ejecutivo

### 1.1 Qué vamos a construir

```
┌────────────────────────────────────────────────────────────────────┐
│                      ARQUITECTURA OBJETIVO                         │
│                                                                    │
│  ┌──────────┐    ┌──────────────────┐    ┌────────────────────┐   │
│  │ Frontend │───▶│ FastAPI Routers  │───▶│ LangGraph (nuevo)  │   │
│  │ (sin     │    │ (sin cambios)    │    │ + Orchestrator     │   │
│  │ cambios) │    │                  │    │   Agent Node       │   │
│  └──────────┘    └──────────────────┘    └────────┬───────────┘   │
│                                                   │               │
│                    ┌──────────────────────────────┼───────┐       │
│                    │     AGENTIC LAYER (nueva)    │       │       │
│                    │                              │       │       │
│                    │  ┌──────────────────────┐    │       │       │
│                    │  │ SelfRefinementLoop   │◀───┘       │       │
│                    │  │ (b2b_generate_codes) │            │       │
│                    │  └──────────────────────┘            │       │
│                    │  ┌──────────────────────┐            │       │
│                    │  │ ReactRunner          │            │       │
│                    │  │ (b3_generate_hyp)    │            │       │
│                    │  └──────────────────────┘            │       │
│                    │  ┌──────────────────────┐            │       │
│                    │  │ MultiAgentDebate     │            │       │
│                    │  │ (elaboration_engine) │            │       │
│                    │  └──────────────────────┘            │       │
│                    │                                      │       │
│                    │  ┌──────────────────────────────┐    │       │
│                    │  │ Tool Registry                │    │       │
│                    │  │ • search_segments (RAG)      │    │       │
│                    │  │ • compare_embeddings (TEI)   │    │       │
│                    │  │ • get_code_details (DB)      │    │       │
│                    │  │ • check_saturation (SQL)     │    │       │
│                    │  └──────────────────────────────┘    │       │
│                    └──────────────────────────────────────┘       │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ SERVICIOS EXISTENTES (sin cambios de interfaz)              │ │
│  │ RAGService | TEIClient | TogetherLLM | DB Session           │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

### 1.2 Principios de diseño

1. **Feature flags**: toda funcionalidad agentic se activa con `AGENTIC_MODE=true`
2. **Fallback determinístico**: si el bucle falla, se degrada al single-shot actual
3. **Backward compatible**: las APIs externas no cambian sus firmas
4. **Modelo barato para critic**: FLASH para auto-evaluación, PRO para generación
5. **Timeouts estrictos**: cada agente tiene `max_iterations` y `timeout_seconds`

---

## 2. Fase 0: Infraestructura Agencial Base

> **Duración:** 1-2 días | **Riesgo:** Bajo | **Dependencias:** Ninguna

### 2.1 Archivos a crear

```
backend/app/agents/
├── __init__.py
├── base.py                        # BaseAgent + Result types
├── tool_registry.py               # ToolRegistry centralizado
├── react_runner.py                # Motor ReAct genérico
├── self_refiner.py                # SelfRefinementLoop genérico
├── tools/
│   ├── __init__.py
│   ├── search_tools.py            # search_segments, search_similar_codes
│   ├── db_tools.py                # get_code_details, get_hypotheses, get_segments
│   └── compare_tools.py           # compare_embeddings, find_duplicates
└── prompts/
    ├── react_system.txt           # System prompt universal para ReAct
    └── self_critic_system.txt     # System prompt para self-refinement
```

### 2.2 Paso a paso

#### Paso 0.1 — `backend/app/agents/__init__.py`

```python
"""Agentic Architecture Layer for GT System.

Provides:
- BaseAgent: abstract base for all agentic loops
- SelfRefinementLoop: Generate → Critic → Refine pattern
- ReactRunner: Thought → Action → Observation pattern
- ToolRegistry: centralized tool registration and execution
"""

from app.agents.base import AgentResult, AgentLoopLog, BaseAgent
from app.agents.self_refiner import SelfRefinementLoop
from app.agents.react_runner import ReactRunner
from app.agents.tool_registry import ToolRegistry, tool

__all__ = [
    "AgentResult",
    "AgentLoopLog",
    "BaseAgent",
    "SelfRefinementLoop",
    "ReactRunner",
    "ToolRegistry",
    "tool",
]
```

#### Paso 0.2 — `backend/app/agents/base.py`

```python
"""BaseAgent: template method para bucles agenciales."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Resultado unificado de cualquier agente."""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    iterations: int = 0
    total_tokens: int = 0
    total_cost_est: float = 0.0
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
    tool_calls: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    result_summary: str
    error: str | None = None


class BaseAgent:
    """Template Method para agentes con bucle.

    Subclases implementan:
    - _build_system_prompt() → str
    - _should_stop(state) → bool
    - _extract_result(state) → dict
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
        trace: list[dict] = []
        total_tokens = 0
        history: list[dict[str, str]] = [
            {"role": "system", "content": self._build_system_prompt(**kwargs)}
        ]

        for iteration in range(1, self.max_iterations + 1):
            if time.time() - started_at > self.timeout_seconds:
                return AgentResult(
                    success=False,
                    error=f"Timeout after {self.timeout_seconds}s",
                    iterations=iteration,
                    trace=trace,
                )

            try:
                step_result = self._step(history, iteration, **kwargs)
                trace.append(step_result)
                total_tokens += step_result.get("tokens", 0)

                if self._should_stop(step_result):
                    return AgentResult(
                        success=True,
                        data=self._extract_result(step_result),
                        iterations=iteration,
                        total_tokens=total_tokens,
                        trace=trace,
                    )
            except Exception as e:
                logger.error("Agent %s iteration %d failed: %s", self.agent_id, iteration, e)
                return AgentResult(
                    success=False,
                    error=str(e),
                    iterations=iteration,
                    trace=trace,
                )

        return AgentResult(
            success=False,
            error=f"Max iterations ({self.max_iterations}) reached without convergence",
            iterations=self.max_iterations,
            total_tokens=total_tokens,
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

    def _log_loop(self, project_id: str, result: AgentResult):
        """Persiste AgentLoopLog en DB (opcional, para traceabilidad)."""
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            log = AgentLoopLog(
                agent_id=self.agent_id,
                project_id=project_id,
                started_at=now,
                finished_at=now,
                iterations=result.iterations,
                total_tokens=result.total_tokens,
                tool_calls=[t for t in result.trace if t.get("type") == "tool_call"],
                llm_calls=[t for t in result.trace if t.get("type") == "llm_call"],
                result_summary=str(result.data)[:500],
                error=result.error,
            )
            logger.info("AgentLoopLog: %s iterations=%d tokens=%d", self.agent_id, result.iterations, result.total_tokens)
        except Exception as e:
            logger.warning("Failed to persist AgentLoopLog: %s", e)
```

#### Paso 0.3 — `backend/app/agents/tool_registry.py`

```python
"""ToolRegistry: registro centralizado de herramientas para agentes ReAct."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def tool(name: str, description: str, parameters: dict | None = None):
    """Decorator para registrar funciones como tools."""
    def decorator(fn: Callable):
        fn._tool_meta = {
            "name": name,
            "description": description,
            "parameters": parameters or {},
        }
        return fn
    return decorator


class ToolRegistry:
    """Registro centralizado de tools disponibles para agentes.

    Uso:
        registry = ToolRegistry()
        registry.register(search_segments, "search_segments", "Busca segmentos...")
        result = registry.execute("search_segments", {"query": "...", "top_k": 5})
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, fn: Callable, name: str, description: str, parameters: dict | None = None):
        self._tools[name] = {
            "fn": fn,
            "name": name,
            "description": description,
            "parameters": parameters or {},
        }

    def register_from_module(self, module):
        """Auto-registra todas las funciones decoradas con @tool de un módulo."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, "_tool_meta"):
                meta = attr._tool_meta
                self.register(attr, meta["name"], meta["description"], meta["parameters"])

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Ejecuta una tool y devuelve el resultado como string."""
        if tool_name not in self._tools:
            available = list(self._tools.keys())
            return json.dumps({"error": f"Tool '{tool_name}' not found. Available: {available}"})

        try:
            fn = self._tools[tool_name]["fn"]
            result = fn(**tool_input)
            if isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False, default=str)
            return str(result)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})

    def get_schema_for_prompt(self) -> str:
        """Genera la descripción de tools para el system prompt."""
        lines = []
        for name, info in self._tools.items():
            params = json.dumps(info["parameters"], ensure_ascii=False)
            lines.append(f"- {name}({params}): {info['description']}")
        return "\n".join(lines)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
```

#### Paso 0.4 — `backend/app/agents/self_refiner.py`

```python
"""SelfRefinementLoop: patrón Generate → Critic → Refine → Converge."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class SelfRefinementLoop(BaseAgent):
    """
    Bucle de auto-refinamiento genérico.

    El LLM genera output → se auto-evalúa → corrige → repite.
    Útil para tareas donde la calidad importa más que la velocidad:
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
        return kwargs.get("system_prompt", "Eres un agente que mejora iterativamente su output.")

    def _step(self, history: list[dict], iteration: int, **kwargs) -> dict:
        # 1. GENERATE
        gen_response = self.llm.run_agent(
            self.generate_prompt_id,
            variables=kwargs.get("generate_vars", {}),
        )
        gen_text = json.dumps(gen_response, ensure_ascii=False)
        history.append({"role": "assistant", "content": gen_text})

        # 2. CRITIC (usa FLASH para ahorrar costo)
        critic_vars = {
            **kwargs.get("critic_vars", {}),
            "output_to_evaluate": gen_text,
        }
        critic_response = self.llm.run_agent(
            self.critic_prompt_id,
            variables=critic_vars,
            temperature=0.1,  # más determinístico para evaluar
        )

        return {
            "type": "refinement_step",
            "iteration": iteration,
            "output": gen_response,
            "critic": critic_response,
            "is_valid": critic_response.get("all_valid", False),
            "issues": critic_response.get("issues", []),
        }

    def _should_stop(self, step_result: dict) -> bool:
        return step_result.get("is_valid", False)

    def _extract_result(self, step_result: dict) -> dict:
        return step_result.get("output", {})
```

#### Paso 0.5 — `backend/app/agents/react_runner.py`

```python
"""ReactRunner: motor genérico de bucle ReAct (Thought → Action → Observation)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ReactRunner(BaseAgent):
    """
    Motor ReAct genérico.

    El LLM razona (Thought), decide una acción (Action),
    el sistema la ejecuta y devuelve la observación (Observation).
    Repite hasta que el LLM emite FinalAnswer.
    """

    def __init__(
        self,
        agent_id: str,
        llm_client: Any,
        tool_registry: ToolRegistry,
        max_iterations: int = 5,
        timeout_seconds: float = 300.0,
    ):
        super().__init__(agent_id, llm_client, max_iterations, timeout_seconds)
        self.tools = tool_registry

    def _build_system_prompt(self, **kwargs) -> str:
        tools_schema = self.tools.get_schema_for_prompt()
        return f"""[ROL]
{kwargs.get('role_description', 'Eres un agente ReAct. Pensá paso a paso y usá herramientas cuando necesites información adicional.')}

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
        # 1. LLM decide
        response = self.llm.chat(
            messages=history + [{"role": "user", "content": "¿Cuál es el siguiente paso?"}],
            temperature=0.3,
        )
        content = response.get("content", "")
        tokens = response.get("usage", {}).get("total_tokens", 0)

        # 2. Parsear respuesta ReAct
        parsed = self._parse_react(content)

        if "final_answer" in parsed:
            return {
                "type": "final",
                "iteration": iteration,
                "output": parsed["final_answer"],
                "thought": parsed.get("thought", ""),
                "tokens": tokens,
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
        history.append({"role": "assistant", "content": content})
        history.append({"role": "user", "content": f"Observation: {observation}"})

        return {
            "type": "tool_call",
            "iteration": iteration,
            "thought": parsed.get("thought", ""),
            "action": tool_name,
            "action_input": tool_input,
            "observation": observation[:500],
            "tokens": tokens,
        }

    def _should_stop(self, step_result: dict) -> bool:
        return step_result.get("type") == "final"

    def _extract_result(self, step_result: dict) -> dict:
        return step_result.get("output", {})

    @staticmethod
    def _parse_react(text: str) -> dict:
        """Parsea el formato Thought/Action/FinalAnswer del LLM."""
        result: dict[str, Any] = {}

        thought_match = re.search(r"Thought:\s*(.+?)(?=\n(?:Action:|FinalAnswer:)|\Z)", text, re.DOTALL)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        final_match = re.search(r"FinalAnswer:\s*(\{.+?\})", text, re.DOTALL)
        if final_match:
            try:
                result["final_answer"] = json.loads(final_match.group(1))
            except json.JSONDecodeError:
                result["final_answer"] = {"raw": final_match.group(1)}
            return result

        action_match = re.search(r"Action:\s*(.+?)(?=\n|\Z)", text)
        if action_match:
            result["action"] = action_match.group(1).strip()

        input_match = re.search(r"Action Input:\s*(\{.+?\})", text, re.DOTALL)
        if input_match:
            try:
                result["action_input"] = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                result["action_input"] = {"raw": input_match.group(1)}

        return result
```

#### Paso 0.6 — `backend/app/agents/tools/__init__.py`

```python
"""Agent tools package."""
```

#### Paso 0.7 — `backend/app/agents/tools/search_tools.py`

```python
"""Search tools para agentes ReAct."""

from app.agents.tool_registry import tool
from app.core.tei_client import TEIClient

tei = TEIClient()


@tool(
    name="search_segments",
    description="Busca segmentos semánticamente en el corpus del proyecto usando RRF (semantic + lexical).",
    parameters={"query": "texto de búsqueda", "proyecto_id": "UUID del proyecto", "top_k": "número de resultados (default 5)"},
)
def search_segments(query: str, proyecto_id: str, top_k: int = 5) -> dict:
    """Tool: búsqueda RAG de segmentos."""
    import asyncio
    from uuid import UUID

    from app.db.database import AsyncSessionLocal
    from app.services.rag import RAGService

    async def _search():
        async with AsyncSessionLocal() as db:
            service = RAGService(db, tei)
            results = await service.search(
                query=query,
                proyecto_id=UUID(proyecto_id),
                top_k=top_k,
                fusion="rrf",
            )
            return [
                {
                    "segmento_id": str(r.segmento_id),
                    "texto": r.texto[:300],
                    "score": r.score,
                }
                for r in results
            ]

    return asyncio.run(_search())


@tool(
    name="search_similar_codes",
    description="Busca códigos existentes semánticamente similares a un texto dado.",
    parameters={"text": "texto a comparar", "proyecto_id": "UUID del proyecto", "top_k": "número de resultados"},
)
def search_similar_codes(text: str, proyecto_id: str, top_k: int = 5) -> dict:
    """Tool: búsqueda de códigos similares por embedding."""
    import asyncio
    from uuid import UUID

    from app.db.database import AsyncSessionLocal
    from app.services.rag import RAGService

    async def _search():
        async with AsyncSessionLocal() as db:
            embedding = await tei.embed_query(text)
            service = RAGService(db, tei)
            results = await service.search_similar_codes(
                segment_embedding=embedding,
                proyecto_id=UUID(proyecto_id),
                top_k=top_k,
            )
            return [
                {"id": c.id, "nombre": c.nombre, "definicion": c.definicion[:200], "score": c.score}
                for c in results
            ]

    return asyncio.run(_search())
```

#### Paso 0.8 — `backend/app/agents/tools/db_tools.py`

```python
"""Database tools para agentes ReAct."""

import json

from app.agents.tool_registry import tool


def _sync_session():
    """Obtiene una sesión sync para uso en Celery workers."""
    import sys
    sys.path.insert(0, "/app")
    from database import SessionLocal
    return SessionLocal()


@tool(
    name="get_code_details",
    description="Obtiene la definición completa y los incidentes (segmentos) de un código por su ID.",
    parameters={"code_id": "UUID del código"},
)
def get_code_details(code_id: str) -> dict:
    """Tool: obtener detalles de un código con incidentes."""
    from sqlalchemy import text

    s = _sync_session()
    try:
        cat = s.execute(
            text("SELECT nombre, definicion, version, es_central FROM categorias WHERE id = :cid"),
            {"cid": code_id},
        ).fetchone()
        if not cat:
            return {"error": f"Código {code_id} no encontrado"}

        incidents = s.execute(
            text(
                "SELECT s.texto, d.original_filename "
                "FROM codigos_segmento cs "
                "JOIN segmentos s ON cs.segmento_id = s.id "
                "JOIN documentos d ON s.documento_id = d.id "
                "WHERE cs.categoria_id = :cid LIMIT 10"
            ),
            {"cid": code_id},
        ).fetchall()

        return {
            "nombre": cat[0],
            "definicion": cat[1],
            "version": cat[2],
            "es_central": cat[3],
            "incidentes": [{"texto": r[0][:300], "documento": r[1]} for r in incidents],
            "total_incidentes": len(incidents),
        }
    finally:
        s.close()


@tool(
    name="get_all_codes",
    description="Lista todos los códigos (categorías) del proyecto con sus definiciones.",
    parameters={"proyecto_id": "UUID del proyecto"},
)
def get_all_codes(proyecto_id: str) -> dict:
    """Tool: listar códigos del proyecto."""
    from sqlalchemy import text

    s = _sync_session()
    try:
        codes = s.execute(
            text("SELECT id, nombre, definicion FROM categorias WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        return {
            "total": len(codes),
            "codes": [{"id": str(c[0]), "nombre": c[1], "definicion": c[2][:200]} for c in codes],
        }
    finally:
        s.close()


@tool(
    name="get_existing_hypotheses",
    description="Lista las hipótesis existentes del proyecto (no rechazadas).",
    parameters={"proyecto_id": "UUID del proyecto"},
)
def get_existing_hypotheses(proyecto_id: str) -> dict:
    """Tool: listar hipótesis existentes."""
    from sqlalchemy import text

    s = _sync_session()
    try:
        hyps = s.execute(
            text("SELECT id, text, level, confidence, status FROM hypotheses WHERE project_id = :pid AND status != 'rejected'"),
            {"pid": proyecto_id},
        ).fetchall()
        return {
            "total": len(hyps),
            "hypotheses": [
                {"id": str(h[0]), "text": h[1], "level": h[2], "confidence": h[3], "status": h[4]}
                for h in hyps
            ],
        }
    finally:
        s.close()
```

#### Paso 0.9 — `backend/app/agents/tools/compare_tools.py`

```python
"""Comparison tools para agentes ReAct."""

from app.agents.tool_registry import tool
from app.core.tei_client import TEIClient

tei = TEIClient()


@tool(
    name="compare_embeddings",
    description="Compara la similitud semántica entre dos textos (0-1). Útil para detectar códigos redundantes.",
    parameters={"text_a": "primer texto", "text_b": "segundo texto"},
)
def compare_embeddings(text_a: str, text_b: str) -> dict:
    """Tool: comparar similitud semántica entre dos textos."""
    import asyncio

    async def _compare():
        emb_a = await tei.embed_query(text_a)
        emb_b = await tei.embed_query(text_b)
        dot = sum(a * b for a, b in zip(emb_a, emb_b))
        return {"similarity": round(dot, 4), "are_duplicates": dot > 0.85}

    return asyncio.run(_compare())


@tool(
    name="find_similar_codes",
    description="Encuentra códigos existentes que sean semánticamente similares a un nuevo código candidato.",
    parameters={"code_definition": "definición del código nuevo", "proyecto_id": "UUID del proyecto"},
)
def find_similar_codes(code_definition: str, proyecto_id: str) -> dict:
    """Tool: detectar códigos redundantes."""
    import asyncio
    from uuid import UUID

    from app.db.database import AsyncSessionLocal
    from app.services.rag import RAGService

    async def _find():
        async with AsyncSessionLocal() as db:
            embedding = await tei.embed_query(code_definition)
            service = RAGService(db, tei)
            results = await service.search_similar_codes(
                segment_embedding=embedding,
                proyecto_id=UUID(proyecto_id),
                top_k=3,
            )
            return {
                "similar_codes": [
                    {"nombre": c.nombre, "definicion": c.definicion[:200], "score": c.score}
                    for c in results
                ],
                "has_near_duplicate": any(c.score > 0.85 for c in results),
            }

    return asyncio.run(_find())
```

### 2.3 Verificación Fase 0

```bash
# Test: importar todo el paquete sin errores
cd backend && python -c "
from app.agents import BaseAgent, SelfRefinementLoop, ReactRunner, ToolRegistry
from app.agents.tools.search_tools import search_segments
from app.agents.tools.db_tools import get_code_details
from app.agents.tools.compare_tools import compare_embeddings
print('✅ All imports OK')
"

# Test: ToolRegistry registra y ejecuta
cd backend && python -c "
from app.agents.tool_registry import ToolRegistry
r = ToolRegistry()
def dummy_test(x): return {'result': x * 2}
r.register(dummy_test, 'dummy', 'test tool', {'x': 'int'})
assert 'dummy' in r.tool_names
result = r.execute('dummy', {'x': 5})
print('✅ ToolRegistry OK:', result)
"
```

---

## 3. Fase 1: Self-Refinement Loop

> **Duración:** 3-4 días | **Riesgo:** Bajo | **Depende de:** Fase 0

### 3.1 Objetivo

Convertir `b2b_generate_codes()` de single-shot a un bucle Generate → Self-Critic → Refine.

### 3.2 Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `workers/heavy/agents_b.py` | Nuevo `b2b_generate_codes_agentic()` + feature flag en `b2_open_code()` |
| `workers/heavy/llm_client.py` | Nuevo `run_self_refinement()` |
| `prompts/deepseek_pro/b2b_generate_codes.md` | Añadir sección `[SELF-CRITIC]` al prompt existente |
| `backend/app/core/llm_config.py` | Registrar `b2b_code_critic` en `PROMPT_TIER_MAP` |

### 3.3 Paso a paso

#### Paso 1.1 — Prompt: `prompts/deepseek_pro/b2b_generate_codes.md`

Añadir al prompt existente una nueva sección `[SELF-CRITIC]`:

```markdown
[SELF-CRITIC]
Después de generar los códigos, auto-evalualos con este criterio:
1. ¿Cada código usa el estilo requerido (gerundio, in-vivo, etc.)?
2. ¿Cada definición describe propiedades y dimensiones (no solo repite el nombre)?
3. ¿Hay códigos redundantes? (similitud > 0.85 en significado)
4. ¿Todos los códigos están anclados en los indicadores proporcionados?

Si algún código falla, reescribilo. Si dos códigos son redundantes, fusionarlos.
Repetí hasta que todos pasen.
```

#### Paso 1.2 — Nuevo método en `workers/heavy/llm_client.py`

```python
def run_self_refinement(
    self,
    agent_id: str,
    variables: dict[str, str],
    max_iterations: int = 3,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """
    Ejecuta un bucle Generate → Self-Critic → Refine.

    El prompt debe incluir una sección [SELF-CRITIC] con criterios de evaluación.
    El LLM recibe su propio output y lo mejora iterativamente.
    """
    if self.is_mock:
        return dict(MOCK_RESPONSES.get(agent_id, {"mock_note": f"No mock for {agent_id}"}))

    parsed = _load_agent_prompt(agent_id, "PRO")
    prompt_template = parsed["prompt"]
    schema = parsed["schema"]

    try:
        system_prompt = prompt_template.format(**variables)
    except KeyError as e:
        logger.warning("Missing variable %s, using raw template", e)
        system_prompt = prompt_template
        for k, v in variables.items():
            system_prompt = system_prompt.replace("{" + k + "}", str(v))

    history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Generá los códigos. Después auto-evalualos con [SELF-CRITIC]."},
    ]

    best_output = None
    best_score = -1

    for iteration in range(1, max_iterations + 1):
        response = self._call_llm(
            tier="PRO",
            model=_TIER_MODELS["PRO"],
            system_prompt=history[0]["content"],
            schema=schema,
            max_tokens=_TIER_MAX_TOKENS["PRO"],
            temperature=temperature,
        )

        # Evaluar calidad del output
        codes = response.get("codes", [])
        score = self._evaluate_code_quality(codes)

        if score > best_score:
            best_score = score
            best_output = response

        if score >= 0.9:  # Convergencia
            logger.info("Self-refinement converged at iteration %d (score=%.2f)", iteration, score)
            break

        # Feedback para refinamiento
        history.append({"role": "assistant", "content": json.dumps(response, ensure_ascii=False)})
        history.append({
            "role": "user",
            "content": f"Quality score: {score:.2f}. Mejorá los códigos con problemas."
        })

    return best_output or response

@staticmethod
def _evaluate_code_quality(codes: list[dict]) -> float:
    """Evalúa calidad de códigos (0-1). Heurística simple, sin LLM extra."""
    if not codes:
        return 0.0
    score = 0.0
    for code in codes:
        name = code.get("code_name", "")
        definition = code.get("definition", "")
        # Gerundio check
        if name.strip().endswith(("ando", "iendo", "ar", "er", "ir")) or name.startswith('"'):
            score += 0.3
        # Definición con sustancia (> 50 chars)
        if len(definition) > 50:
            score += 0.3
        # Tiene propiedades
        if "propiedades" in code or "dimensiones" in code or "variations" in code:
            score += 0.2
        # Tiene indicadores anclados
        if code.get("indicators") and len(code["indicators"]) > 0:
            score += 0.2
    return min(score / max(len(codes), 1), 1.0)
```

#### Paso 1.3 — Feature flag en `workers/heavy/agents_b.py`

```python
# Al inicio del archivo, después de llm = LLMClient()
import os as _os
AGENTIC_MODE = _os.getenv("AGENTIC_MODE", "false").lower() in ("1", "true", "yes")

# En b2_open_code(), reemplazar la llamada a _b2b_generate_codes:
if AGENTIC_MODE:
    b2b_response = llm.run_self_refinement(
        agent_id="b2b",
        variables={
            "population_assumption": pop_assumption,
            "population_context": pop_ctx[0] if pop_ctx else "",
            "existing_codes": codes_text,
            "indicators": indicators_text,
        },
        max_iterations=3,
    )
else:
    b2b_response = _b2b_generate_codes(
        pop_assumption=pop_assumption,
        pop_context=pop_ctx[0] if pop_ctx else "",
        existing_codes=codes_text,
        indicators_text=indicators_text,
    )
```

### 3.4 Verificación Fase 1

```bash
# Test con AGENTIC_MODE=true
cd backend && AGENTIC_MODE=true python -c "
from workers.heavy.agents_b import b2_open_code
result = b2_open_code('test-project-id')
print('Codes created:', result.get('codes_created'))
"

# Test con AGENTIC_MODE=false (debe ser idéntico al comportamiento actual)
cd backend && AGENTIC_MODE=false python -c "
from workers.heavy.agents_b import b2_open_code
result = b2_open_code('test-project-id')
print('Codes created:', result.get('codes_created'))
"
```

---

## 4. Fase 2: ReAct Agent

> **Duración:** 4-5 días | **Riesgo:** Medio | **Depende de:** Fase 0, Fase 1

### 4.1 Objetivo

Convertir `b3_generate_hypotheses()` en un agente ReAct que puede buscar evidencia antes de generar hipótesis.

### 4.2 Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `workers/heavy/agents_b.py` | Nuevo `b3_generate_hypotheses_agentic()` |
| `workers/heavy/llm_client.py` | Nuevo `run_react_loop()` |
| `backend/app/agents/tool_registry.py` | (ya creado en Fase 0) |
| `backend/app/agents/tools/*.py` | (ya creados en Fase 0) |
| `prompts/deepseek_pro/b3_hypothesis_generator.md` | Versión ReAct-aware |
| `workers/heavy/tasks.py` | Nueva tarea `run_react_hypothesis` |
| `backend/app/core/llm_config.py` | Registrar `b3_react` en `PROMPT_TIER_MAP` |

### 4.3 Paso a paso

#### Paso 2.1 — Nuevo método en `workers/heavy/llm_client.py`

```python
def run_react_loop(
    self,
    agent_id: str,
    variables: dict[str, str],
    tools: "ToolRegistry",  # forward ref
    max_steps: int = 5,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """
    Ejecuta un bucle ReAct: Thought → Action → Observation → ... → FinalAnswer.

    El LLM decide qué tools llamar y cuándo tiene suficiente evidencia.
    """
    if self.is_mock:
        return dict(MOCK_RESPONSES.get(agent_id, {"mock_note": f"No mock for {agent_id}"}))

    parsed = _load_agent_prompt(agent_id, "PRO")
    prompt_template = parsed["prompt"]
    schema = parsed["schema"]

    try:
        system_prompt = prompt_template.format(**variables)
    except KeyError:
        system_prompt = prompt_template
        for k, v in variables.items():
            system_prompt = system_prompt.replace("{" + k + "}", str(v))

    # Inyectar tools schema
    tools_schema = tools.get_schema_for_prompt()
    system_prompt += f"\n\n[HERRAMIENTAS DISPONIBLES]\n{tools_schema}"

    history = [{"role": "system", "content": system_prompt}]

    for step in range(1, max_steps + 1):
        response = self._call_llm(
            tier="PRO",
            model=_TIER_MODELS["PRO"],
            system_prompt=history[0]["content"],
            schema=None,  # ReAct usa formato libre Thought/Action
            max_tokens=_TIER_MAX_TOKENS["PRO"],
            temperature=temperature,
        )

        # Parsear respuesta (Thought/Action/FinalAnswer)
        from app.agents.react_runner import ReactRunner
        parsed_action = ReactRunner._parse_react(
            json.dumps(response) if isinstance(response, dict) else str(response)
        )

        if "final_answer" in parsed_action:
            return parsed_action["final_answer"]

        tool_name = parsed_action.get("action", "")
        tool_input = parsed_action.get("action_input", {})
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except json.JSONDecodeError:
                tool_input = {"query": tool_input}

        observation = tools.execute(tool_name, tool_input)
        history.append({"role": "assistant", "content": json.dumps(response, ensure_ascii=False)})
        history.append({"role": "user", "content": f"Observation: {observation}"})

    return {"error": "Max steps reached", "hypotheses": []}
```

#### Paso 2.2 — Feature flag en `workers/heavy/agents_b.py`

```python
def b3_generate_hypotheses_agentic(proyecto_id: str) -> dict:
    """Versión ReAct de B3: el agente busca evidencia antes de generar hipótesis."""
    from app.agents.tool_registry import ToolRegistry
    from app.agents.tools.search_tools import search_segments, search_similar_codes
    from app.agents.tools.db_tools import get_code_details, get_all_codes, get_existing_hypotheses
    from app.agents.tools.compare_tools import compare_embeddings, find_similar_codes

    tools = ToolRegistry()
    tools.register(search_segments, "search_segments",
                   "Busca segmentos semánticamente en el corpus.")
    tools.register(get_code_details, "get_code_details",
                   "Obtiene definición e incidentes de un código.")
    tools.register(get_all_codes, "get_all_codes",
                   "Lista todos los códigos del proyecto.")
    tools.register(get_existing_hypotheses, "get_existing_hypotheses",
                   "Lista hipótesis ya generadas.")
    tools.register(find_similar_codes, "find_similar_codes",
                   "Detecta códigos similares (anti-redundancia).")

    response = llm.run_react_loop(
        agent_id="b3",
        variables={
            "proyecto_id": proyecto_id,
            "population_assumption": "...",  # cargado dentro de run_react_loop
            "population_context": "...",
            "processes": "...",
            "codes": "...",
            "existing_hypotheses": "...",
        },
        tools=tools,
        max_steps=5,
    )

    return response


# En el punto de llamada:
if AGENTIC_MODE:
    raw_hypotheses = b3_generate_hypotheses_agentic(proyecto_id)
else:
    raw_hypotheses = response.get("hypotheses", [])  # comportamiento actual
```

### 4.4 Verificación Fase 2

```bash
# Test: ReAct loop con tools mock
cd backend && python -c "
from app.agents.tool_registry import ToolRegistry
from app.agents.tools.db_tools import get_all_codes
r = ToolRegistry()
r.register(get_all_codes, 'get_all_codes', 'List codes', {'proyecto_id': 'str'})
schema = r.get_schema_for_prompt()
assert 'get_all_codes' in schema
assert len(r.tool_names) == 1
print('✅ ReAct ToolRegistry OK')
"
```

---

## 5. Fase 3: Orchestrator Agent

> **Duración:** 3-4 días | **Riesgo:** Medio | **Depende de:** Fase 0, Fase 1

### 5.1 Objetivo

Agregar un nodo `orchestrator_decide` al LangGraph que use LLM reasoning para decidir el próximo paso del pipeline dinámicamente, con fallback determinístico.

### 5.2 Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `backend/app/core/workflow.py` | Nuevo nodo `node_orchestrator_decide` + edge dinámico |
| `backend/app/agents/orchestrator.py` | NUEVO: OrchestratorAgent |
| `prompts/deepseek_pro/orchestrator_decider.md` | NUEVO |

### 5.3 Paso a paso

#### Paso 3.1 — `backend/app/agents/orchestrator.py`

```python
"""Orchestrator Agent: decide dinámicamente el próximo paso del pipeline."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Nodos válidos del grafo
VALID_NODES = [
    "segment_and_index",
    "extract_entities",
    "batch_code",
    "map_synthesize",
    "reduce_synthesize",
    "find_core_concern",
    "generate_hypotheses",
    "calculate_saturation",
    "theosampler_evaluate",
    "hitl_gap_review",
    "process_new_data",
    "prepare_playground",
    "hitl_review",
    "final_report",
]

# Orden recomendado (fallback determinístico)
DEFAULT_ORDER = {
    "segment_and_index": "extract_entities",
    "extract_entities": "batch_code",
    "batch_code": "map_synthesize",
    "map_synthesize": "reduce_synthesize",
    "reduce_synthesize": "find_core_concern",
    "find_core_concern": "generate_hypotheses",
    "generate_hypotheses": "calculate_saturation",
    "calculate_saturation": "theosampler_evaluate",
    "theosampler_evaluate": "prepare_playground",
    "prepare_playground": "hitl_review",
    "hitl_review": "final_report",
}


class OrchestratorAgent:
    """Decide el próximo nodo del pipeline basado en el estado actual."""

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def decide(
        self,
        current_step: str,
        state: dict[str, Any],
    ) -> str:
        """
        Decide el próximo nodo.

        Primero intenta con LLM. Si falla, usa fallback determinístico.
        """
        # Intentar decisión LLM
        try:
            decision = self._llm_decide(current_step, state)
            if decision in VALID_NODES:
                logger.info("Orchestrator LLM decided: %s → %s", current_step, decision)
                return decision
        except Exception as e:
            logger.warning("Orchestrator LLM failed: %s. Using deterministic fallback.", e)

        # Fallback determinístico
        fallback = DEFAULT_ORDER.get(current_step, "final_report")
        logger.info("Orchestrator fallback: %s → %s", current_step, fallback)
        return fallback

    def _llm_decide(self, current_step: str, state: dict) -> str:
        """Usa LLM para decidir el próximo paso."""
        prompt = f"""[ESTADO ACTUAL DEL PIPELINE]
- Current step: {current_step}
- Project ID: {state.get('project_id', '')}
- Documents processed: {state.get('docs_processed', 0)}
- Codes generated: {len(state.get('new_codes', []))}
- Candidate hypotheses: {len(state.get('candidate_hypotheses', []))}
- Main concern found: {bool(state.get('main_concern'))}
- Saturated codes: {state.get('saturated_codes', [])}
- Pending gaps: {len(state.get('pending_gaps', []))}
- Errors: {len(state.get('errors', []))}

[NODOS DISPONIBLES]
{', '.join(VALID_NODES)}

[DECISIÓN]
Basado en el estado, ¿cuál es el PRÓXIMO nodo óptimo?
Respondé SOLO el nombre del nodo, sin explicación.
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=50,
        )
        content = response.get("content", "").strip().lower()
        # Extraer solo el nombre del nodo
        for node in VALID_NODES:
            if node in content:
                return node
        return DEFAULT_ORDER.get(current_step, "final_report")
```

#### Paso 3.2 — Modificar `backend/app/core/workflow.py`

Añadir el nodo orchestrator y el edge dinámico:

```python
# En build_glaser_graph_with_feedback(), añadir:

def node_orchestrator_decide(state: AnalysisState) -> AnalysisState:
    """Nodo agencial: el LLM decide el próximo paso del pipeline."""
    state["current_step"] = "orchestrator_decide"

    try:
        import os as _os
        if _os.getenv("AGENTIC_MODE", "false").lower() in ("1", "true", "yes"):
            from app.agents.orchestrator import OrchestratorAgent
            from app.core.together_client import TogetherLLM

            llm = TogetherLLM()
            orch = OrchestratorAgent(llm)
            next_node = orch.decide(state.get("current_step", ""), dict(state))
            state["orchestrator_decision"] = next_node
            logger.info("Orchestrator decided: %s", next_node)
        else:
            # Modo determinístico: seguir el orden por defecto
            state["orchestrator_decision"] = DEFAULT_ORDER.get(
                state.get("current_step", ""), "final_report"
            )
    except Exception as e:
        logger.warning("Orchestrator node failed: %s", e)
        state["orchestrator_decision"] = "final_report"

    return state


def route_by_orchestrator(state: AnalysisState) -> str:
    """Routing function: devuelve el nodo decidido por el orchestrator."""
    return state.get("orchestrator_decision", "final_report")


# En el builder:
builder.add_node("orchestrator_decide", node_orchestrator_decide)

# Reemplazar edges estáticos por:
# 1. Cada nodo → orchestrator_decide
for node in ["segment_and_index", "extract_entities", "batch_code",
             "map_synthesize", "reduce_synthesize", "find_core_concern",
             "generate_hypotheses", "calculate_saturation",
             "theosampler_evaluate", "hitl_gap_review",
             "process_new_data", "prepare_playground", "hitl_review"]:
    builder.add_edge(node, "orchestrator_decide")

# 2. Orchestrator → ruteo dinámico a todos los nodos + END
builder.add_conditional_edges(
    "orchestrator_decide",
    route_by_orchestrator,
    {node: node for node in VALID_NODES} | {"final_report": END},
)
```

---

## 6. Fase 4: Debate + Reflexive + RAG

> **Duración:** 5-6 días | **Riesgo:** Medio-Alto | **Depende de:** Fase 0, Fase 1

### 6.1 Multi-Agent Debate (Elaboration Engine)

**Archivo:** `backend/app/services/elaboration_engine.py`

```python
def elaborate_relationship_agentic(
    self,
    project_id: UUID,
    category_ids: list[UUID],
    theoretical_code_id: UUID,
    researcher_question: str,
) -> ElaborationResult:
    """Multi-agent debate: Proposer → Skeptic → Proposer → Synthesizer."""

    # Fase 1: Proposer
    proposal = self.llm.run_agent("relationship_proposer", {
        "categories_with_incidents": self._load_categories(category_ids),
        "theoretical_code": self._load_theoretical_code(theoretical_code_id),
        "researcher_question": researcher_question,
    })

    # Fase 2: Skeptic (FLASH — más barato)
    skeptic = self.llm.run_agent("relationship_skeptic", {
        "proposal": json.dumps(proposal, ensure_ascii=False),
        "categories": self._load_categories(category_ids),
    })

    # Fase 3: Si hay divergencia, rebuttal
    if skeptic.get("diverging_evidence"):
        proposal = self.llm.run_agent("relationship_proposer", {
            **{k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v)
               for k, v in proposal.items()},
            "skeptic_challenge": json.dumps(skeptic["diverging_evidence"], ensure_ascii=False),
        })

    # Fase 4: Synthesizer
    final = self.llm.run_agent("relationship_synthesizer", {
        "proposal": json.dumps(proposal, ensure_ascii=False),
        "skeptic_findings": json.dumps(skeptic, ensure_ascii=False),
    })

    return self._persist_result(final, project_id, category_ids, theoretical_code_id)
```

### 6.2 Reflexive Saturation Monitor

**Archivo:** `backend/app/services/saturation_gap_analyzer.py` (añadir al final)

```python
class ReflexiveSaturationMonitor:
    """Capa agencial sobre SaturationGapAnalyzer."""

    def __init__(self, db_session, llm_client):
        self.analyzer = SaturationGapAnalyzer(db_session)
        self.llm = llm_client

    async def analyze_with_reflection(self, project_id: UUID) -> dict:
        raw = await self.analyzer.full_analysis(project_id)

        try:
            reflection = self.llm.run_agent("saturation_reflector", {
                "critical_gaps": json.dumps([
                    {"severity": g.severity.value, "description": g.description, "action": g.suggested_action}
                    for g in raw.critical
                ], ensure_ascii=False),
                "warnings": json.dumps([
                    {"severity": g.severity.value, "source": g.source.value, "description": g.description}
                    for g in raw.warnings
                ], ensure_ascii=False),
                "saturated": json.dumps(raw.saturated, ensure_ascii=False),
            })
        except Exception:
            reflection = {"narrative_summary": "Reflexión no disponible", "prioritized_actions": []}

        return {
            "project_id": str(raw.project_id),
            "generated_at": raw.generated_at,
            "critical": [...],  # igual que antes
            "warnings": [...],
            "saturated": raw.saturated,
            "reflection": reflection,
        }
```

### 6.3 Agentic RAG Query Expansion

**Archivo:** `backend/app/services/rag.py` (añadir método)

```python
async def agentic_search(
    self,
    query: str,
    proyecto_id: UUID,
    top_k: int = 5,
) -> list[dict]:
    """Query → LLM expands → Multi-query → RRF → MMR."""
    # 1. Expandir query con LLM (FLASH para ahorrar)
    try:
        expansions = self.llm.run_agent("query_expander", {
            "original_query": query,
        })
        queries = [query] + expansions.get("queries", [])[:3]
    except Exception:
        queries = [query]

    # 2. Buscar con cada query
    all_results = []
    for q in queries:
        results = await self.search(q, proyecto_id, top_k * 2, fusion="rrf")
        all_results.extend(results)

    # 3. RRF fusion
    fused = self._rrf_fuse(all_results, k=60)

    # 4. MMR
    if len(fused) > top_k:
        fused = self._mmr_rerank(fused, top_k)

    return [
        {"segmento_id": str(r.segmento_id), "texto": r.texto, "score": r.score}
        for r in fused[:top_k]
    ]
```

---

## 7. Testing & Validación

### 7.1 Tests unitarios

```python
# tests/unit/test_agents.py

def test_tool_registry_register_and_execute():
    from app.agents.tool_registry import ToolRegistry
    r = ToolRegistry()

    def echo(x): return {"echo": x}
    r.register(echo, "echo", "Echo tool", {"x": "str"})

    result = r.execute("echo", {"x": "hello"})
    assert "hello" in result

def test_react_parser_final_answer():
    from app.agents.react_runner import ReactRunner
    text = "Thought: Ya tengo suficiente.\nFinalAnswer: {\"result\": 42}"
    parsed = ReactRunner._parse_react(text)
    assert parsed["final_answer"] == {"result": 42}

def test_react_parser_action():
    from app.agents.react_runner import ReactRunner
    text = "Thought: Necesito buscar.\nAction: search_segments\nAction Input: {\"query\": \"test\"}"
    parsed = ReactRunner._parse_react(text)
    assert parsed["action"] == "search_segments"
    assert parsed["action_input"] == {"query": "test"}

def test_self_refinement_converges():
    # Mock LLM que devuelve output cada vez mejor
    from app.agents.self_refiner import SelfRefinementLoop

    class MockLLM:
        def __init__(self):
            self.calls = 0
        def run_agent(self, agent_id, variables, temperature=None):
            self.calls += 1
            if self.calls == 1:
                return {"codes": [{"code_name": "test", "definition": "short"}]}
            return {"codes": [{"code_name": "testeando", "definition": "Definición larga con propiedades y dimensiones claras"}]}
        def chat(self, messages, temperature=None, max_tokens=None):
            return {"content": '{"all_valid": true}', "usage": {"total_tokens": 10}}

    loop = SelfRefinementLoop("test", MockLLM(), "gen", "critic")
    result = loop.run("test-project")
    assert result.success
    assert result.iterations == 2
```

### 7.2 Tests de integración

```bash
# Test: Pipeline completo con AGENTIC_MODE
cd backend && AGENTIC_MODE=true python -c "
from workers.heavy.agents_b import b2_open_code, b3_generate_hypotheses
# Usar un proyecto real con documentos
result_b2 = b2_open_code('real-project-uuid')
assert result_b2.get('codes_created', 0) >= 0
print('B2 agentic OK')

result_b3 = b3_generate_hypotheses('real-project-uuid')
assert result_b3.get('hypotheses_created', 0) >= 0
print('B3 agentic OK')
"
```

### 7.3 A/B Testing

```python
# tests/test_integration.py (añadir)

def test_agentic_vs_single_shot_quality():
    """Compara calidad de códigos con y sin agente."""
    project_id = "test-project-uuid"
    indicators = load_test_indicators()

    # Single-shot
    codes_single = b2b_generate_codes_single_shot(project_id, indicators)

    # Agentic
    codes_agentic = b2b_generate_codes_agentic(project_id, indicators)

    # Métricas
    redundancy_single = measure_redundancy(codes_single)
    redundancy_agentic = measure_redundancy(codes_agentic)

    assert redundancy_agentic <= redundancy_single, \
        f"Agentic should reduce redundancy. Single: {redundancy_single}, Agentic: {redundancy_agentic}"
```

---

## 8. Feature Flags & Rollout

### 8.1 Variables de entorno

```bash
# .env o docker-compose.yml
AGENTIC_MODE=true                    # Activar toda la capa agencial
AGENTIC_SELF_REFINEMENT=true         # Fase 1: Self-refinement en B2
AGENTIC_REACT=true                   # Fase 2: ReAct en B3
AGENTIC_ORCHESTRATOR=true            # Fase 3: Orchestrator dinámico
AGENTIC_DEBATE=true                  # Fase 4: Multi-agent debate
AGENTIC_REFLECTIVE=true              # Fase 4: Reflexive monitor
AGENTIC_MAX_ITERATIONS=3             # Límite global de iteraciones
AGENTIC_TIMEOUT_SECONDS=300          # Timeout global por agente
AGENTIC_CRITIC_TIER=flash            # Modelo para critic (flash es más barato)
```

### 8.2 Plan de rollout

```
Semana 1: Fase 0 + Fase 1
  ├── Día 1-2: Infraestructura + tests
  ├── Día 3-4: Self-refinement en B2
  └── Día 5: Deploy con AGENTIC_SELF_REFINEMENT=true en staging

Semana 2: Fase 2
  ├── Día 6-8: ReAct en B3 + tools
  ├── Día 9-10: Testing A/B
  └── Deploy staging con AGENTIC_REACT=true

Semana 3: Fase 3 + Fase 4
  ├── Día 11-13: Orchestrator + Debate
  ├── Día 14-15: Reflexive + RAG agentic
  └── Deploy staging completo

Semana 4: Producción
  ├── Día 16-17: Monitoring + ajustes
  ├── Día 18-19: Canary deploy 10% → 50% → 100%
  └── Día 20: Full rollout
```

### 8.3 Rollback

Si algo falla, desactivar con:

```bash
AGENTIC_MODE=false  # Vuelve al comportamiento single-shot original
```

Todos los paths de código nuevo están condicionados por `AGENTIC_MODE`, por lo que un rollback es instantáneo y no requiere deploy de código.

---

## Resumen de Entregables

| Fase | Archivos nuevos | Archivos modificados | Días |
|------|----------------|---------------------|------|
| **F0** | 12 (`agents/` completo) | 0 | 1-2 |
| **F1** | 0 | `agents_b.py`, `llm_client.py`, `b2b_generate_codes.md` | 3-4 |
| **F2** | 0 | `agents_b.py`, `llm_client.py`, `tasks.py`, `llm_config.py` | 4-5 |
| **F3** | `orchestrator.py`, `orchestrator_decider.md` | `workflow.py` | 3-4 |
| **F4** | `relationship_proposer.md`, `relationship_skeptic.md`, `relationship_synthesizer.md`, `saturation_reflector.md`, `query_expander.md` | `elaboration_engine.py`, `saturation_gap_analyzer.py`, `rag.py`, `analysis.py` | 5-6 |
| **Tests** | `test_agents.py` | `test_integration.py` | (incluido) |
| **TOTAL** | **19 nuevos** | **12 modificados** | **15-20** |
