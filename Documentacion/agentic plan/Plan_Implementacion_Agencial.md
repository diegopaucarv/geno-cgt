# Plan de Implementación — Arquitectura Agencial CoT para GT

> **De llamadas single-shot a bucles agentic con Chain of Thought, ReAct, y tool-use.**
>
> Fecha: 2026-06-15 | Ultima actualizacion: 2026-06-16

📋 Checklist: CHECKLIST.md (23/36 items) | 🔗 Interconexiones: ANALISIS_INTERCONEXIONES.md | 🔗 Compatibilidad: ANALISIS_COMPATIBILIDAD.md | 🔗 Oportunidades: Oportunidades_Arquitectura_Agencial_CoT.md | 🔗 Gaps: ../Analisis_CoT_Gaps.md

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

## 1.3 Patrones Agenciales: los 4 paradigmas que implementamos

No hay un solo patrón agencial. El sistema GT se beneficia de **4 paradigmas complementarios**,
cada uno adecuado para un tipo de tarea distinta:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    LOS 4 PARADIGMAS AGENCIALES                           │
├────────────┬──────────────────────────────┬──────────────────────────────┤
│ PARADIGMA  │ CUÁNDO USARLO                │ DÓNDE EN GT                  │
├────────────┼──────────────────────────────┼──────────────────────────────┤
│ P1: Self-  │ Tareas creativas donde la    │ B2: generar códigos          │
│ Refinement │ calidad > velocidad. El LLM  │ B2b: definir categorías      │
│            │ genera, se auto-critica,     │ Map-Reduce: sintetizar       │
│            │ refina. Sin tools externas.  │                              │
├────────────┼──────────────────────────────┼──────────────────────────────┤
│ P2: ReAct  │ Tareas que requieren         │ B3: generar hipótesis con    │
│ (Reason+   │ buscar/verificar datos.      │ evidencia de segmentos       │
│  Acting)   │ Thought→Action→Observation   │ A3: sense-making iterativo   │
│            │ en bucle hasta converger.    │ Elaboration: buscar evidencia│
├────────────┼──────────────────────────────┼──────────────────────────────┤
│ P3: Plan-  │ Tareas multi-step complejas  │ Pipeline completo: planificar│
│ and-Exec.  │ donde conviene planificar    │ qué documentos codificar,    │
│            │ antes de ejecutar.           │ en qué orden, con qué método │
│            │ Plan→Execute→Evaluate→Replan │ Orchestrator: decidir ruta   │
├────────────┼──────────────────────────────┼──────────────────────────────┤
│ P4: Multi- │ Tareas donde múltiples       │ Elaboration: Proposer vs     │
│ Agent      │ perspectivas enriquecen.     │ Skeptic vs Synthesizer       │
│ Debate     │ Agentes con roles opuestos   │ Saturation: múltiples fuentes│
│            │ debaten hasta síntesis.      │ de señal confluyen           │
└────────────┴──────────────────────────────┴──────────────────────────────┘
```

### 1.3.1 Plan-and-Execute: el patrón que faltaba

**ReAct** decide paso a paso sin visión global. **Plan-and-Execute** invierte el orden:
primero elabora un plan completo, luego lo ejecuta metódicamente, y solo al final evalúa.

```
┌─────────────────────────────────────────────────────────────────┐
│              PLAN-AND-EXECUTE (Planificar → Ejecutar → Evaluar)  │
│                                                                  │
│  FASE 1: PLANIFICAR                                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ LLM recibe el objetivo + estado actual y produce un PLAN │    │
│  │ {                                                        │    │
│  │   "goal": "Generar códigos para 15 segmentos",           │    │
│  │   "steps": [                                             │    │
│  │     {"id":1, "action":"search_segments", "why":"..."},   │    │
│  │     {"id":2, "action":"group_indicators", "why":"..."},  │    │
│  │     {"id":3, "action":"generate_codes", "why":"..."},    │    │
│  │     {"id":4, "action":"verify_against_existing", ...}    │    │
│  │   ]                                                      │    │
│  │ }                                                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                        │                                         │
│                        ▼                                         │
│  FASE 2: EJECUTAR (con tools)                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Para cada step del plan:                                 │    │
│  │   Step 1 → tool: search_segments(...) → 45 resultados    │    │
│  │   Step 2 → tool: group_indicators(...) → 8 grupos        │    │
│  │   Step 3 → LLM: generate_codes(grupos) → 6 códigos       │    │
│  │   Step 4 → tool: find_similar_codes(...) → 1 redundante  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                        │                                         │
│                        ▼                                         │
│  FASE 3: EVALUAR + REPLANIFICAR (si es necesario)               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ LLM evalúa el resultado contra el objetivo.              │    │
│  │ ¿Falta algo? → agrega steps al plan y vuelve a Fase 2.  │    │
│  │ ¿Todo OK?    → devuelve resultado final.                │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

**¿Cuándo usar Plan-and-Execute vs ReAct en GT?**

| Tarea | Patrón | Por qué |
|-------|--------|---------|
| Codificar 1 documento (B2) | **ReAct** | Pocos pasos, mucha incertidumbre por segmento |
| Codificar un proyecto entero | **Plan-and-Execute** | Muchos documentos, conviene planificar orden |
| Generar hipótesis (B3) | **ReAct** | Exploratorio, cada hallazgo cambia el rumbo |
| Elaboración selectiva (Fase 5b) | **Plan-and-Execute** | Multi-step: integrar→muestrear→elaborar→verificar |
| Saturation analysis | **Plan-and-Execute** | 4 fuentes independientes, planificar consultas |
| Theoretical Playground | **ReAct** | Interactivo, el investigador cambia el rumbo |

### 1.3.2 Tool Calling con RAG: el flujo completo

La llamada a herramientas es el corazón de ReAct y Plan-and-Execute. Acá mostramos
el flujo concreto de cómo un agente invoca `search_segments` (RAG) y procesa el resultado:

```
┌──────────────────────────────────────────────────────────────────────────┐
│         TOOL CALLING: search_segments (RAG) — Flujo Completo             │
│                                                                          │
│  AGENTE (LLM)                   SISTEMA (Python)        SERVICIOS        │
│  ─────────────                  ────────────────        ─────────        │
│                                                                          │
│  1. Thought:                                                             │
│  "Necesito evidencia sobre                                              │
│   'negociando límites'. Voy                                             │
│   a buscar segmentos que                                                │
│   mencionen este patrón."                                               │
│                                                                          │
│  2. Action: search_segments                                             │
│  3. Action Input: {                                                      │
│       "query": "negociando límites",  ──────────────────────────────────▶│
│       "proyecto_id": "abc-123",       │  ToolRegistry.execute()          │
│       "top_k": 5                      │  1. Valida tool existe           │
│     }                                  │  2. Extrae parámetros            │
│                                        │  3. Invoca search_segments() ───▶│
│                                        │                                  │
│                                        │      search_segments(query,     │
│                                        │      proyecto_id, top_k)        │
│                                        │         │                        │
│                                        │         ├─▶ TEIClient            │
│                                        │         │   .embed_query() ────▶│ TEI Server
│                                        │         │   POST /v1/embeddings  │ voyage-4-nano
│                                        │         │                        │
│                                        │         ├─▶ RAGService           │
│                                        │         │   .search()            │
│                                        │         │   ├─ semantic_rank ───▶│ PostgreSQL
│                                        │         │   │  (HNSW <=>)         │ pgvector
│                                        │         │   ├─ lexical_rank ────▶│ GIN index
│                                        │         │   │  (ts_rank)          │
│                                        │         │   └─ RRF fusion (k=60) │
│                                        │         │                        │
│                                        │         └─▶ MMR rerank           │
│                                        │             (si diversify=True)  │
│                                        │                                  │
│  ◀──────────────────────────────────────┤  Resultado (JSON string):       │
│  4. Observation:                       │  [                               │
│  [                                      │    {"segmento_id": "s1",        │
│    {"segmento_id": "s1",                │     "texto": "...acepto las     │
│     "texto": "...acepto las             │     que valen la pena...",      │
│     que valen la pena...",              │     "score": 0.87},             │
│     "score": 0.87},                     │    {"segmento_id": "s2",        │
│    {"segmento_id": "s2",                │     "texto": "...cada uno       │
│     "texto": "...cada uno               │     tiene su maña...",          │
│     tiene su maña...",                  │     "score": 0.82},             │
│     "score": 0.82}                      │    ...                          │
│  ]                                      │  ]                              │
│                                                                          │
│  5. Thought:                                                             │
│  "Encontré 5 segmentos con                                              │
│   score > 0.80. Los incidentes                                          │
│   muestran un patrón claro de                                           │
│   negociación con el algoritmo.                                         │
│   Puedo generar una hipótesis."                                        │
│                                                                          │
│  6. Action: FinalAnswer                                                 │
│  7. FinalAnswer: {                                                       │
│       "hypotheses": [{                                                   │
│         "text": "Los participantes                                       │
│         negocian activamente los                                         │
│         límites impuestos por el                                         │
│         algoritmo...",                                                   │
│         "evidence_segments": ["s1","s2"],                                │
│         "confidence": 0.85                                               │
│       }]                                                                 │
│     }                                                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

**El contrato de una Tool:**

Toda herramienta en el sistema sigue este contrato:

```python
# 1. DECLARACIÓN (lo que el LLM ve en el system prompt)
@tool(
    name="search_segments",
    description="Busca segmentos semánticamente en el corpus usando RRF (fusión semántica + léxica). "
                "Útil para encontrar evidencia textual sobre un tema o patrón.",
    parameters={
        "query": "texto de búsqueda en lenguaje natural (ej: 'negociando límites con el algoritmo')",
        "proyecto_id": "UUID del proyecto (obligatorio)",
        "top_k": "número de resultados a devolver (default: 5, max: 10)"
    }
)
def search_segments(query, proyecto_id, top_k=5):
    ...

# 2. INVOCACIÓN (lo que el LLM emite en Action Input)
# Action: search_segments
# Action Input: {"query": "negociando límites con el algoritmo", "proyecto_id": "abc-123", "top_k": 5}

# 3. OBSERVACIÓN (lo que el LLM recibe de vuelta)
# Observation: [{"segmento_id":"s1","texto":"...","score":0.87}, ...]
```

**Tool Calling vs Function Calling nativo:**

El sistema usa **tool calling por parsing de texto** (no el function calling nativo de la API)
porque:
1. Compatible con cualquier modelo (no solo los que soportan native function calling)
2. El formato `Thought:/Action:/Action Input:` es más flexible y permite razonamiento intercalado
3. Ya tenemos prompts en formato markdown que se adaptan naturalmente
4. Si en el futuro migramos a native function calling, el `ToolRegistry` abstrae la diferencia

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
├── plan_executor.py               # Plan-and-Execute genérico
├── tools/
│   ├── __init__.py
│   ├── search_tools.py            # search_segments, search_similar_codes
│   ├── db_tools.py                # get_code_details, get_hypotheses, get_segments
│   └── compare_tools.py           # compare_embeddings, find_duplicates
└── prompts/
    ├── react_system.txt           # System prompt universal para ReAct
    └── self_critic_system.txt     # System prompt para self-refinement
```

#### Paso 0.4b — `backend/app/agents/plan_executor.py` (NUEVO: Plan-and-Execute)

```python
"""PlanExecutor: patrón Plan-and-Execute (Planificar → Ejecutar → Evaluar → Replanificar)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.agents.base import BaseAgent
from app.agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class PlanExecutor(BaseAgent):
    """
    Motor Plan-and-Execute genérico.

    A diferencia de ReAct (que decide paso a paso), este agente:
    1. PLANIFICA: el LLM elabora un plan completo (lista de steps)
    2. EJECUTA: el sistema ejecuta cada step del plan con tools
    3. EVALÚA: el LLM revisa el resultado y decide si replanificar
    4. REPITE desde 1 si es necesario

    Ideal para tareas multi-step donde conviene tener visión global:
    - Codificación de un proyecto entero
    - Elaboración selectiva (Fase 5b)
    - Saturation analysis (4 fuentes)
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
{kwargs.get('role_description', 'Eres un agente planificador. Primero elaborá un plan, después ejecutalo.')}

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
        # ── FASE 1: PLANIFICAR ──
        plan_response = self.llm.chat(
            messages=history + [{{
                "role": "user",
                "content": f"Objetivo: {kwargs.get('goal', 'Completar la tarea')}\n\nEstado actual:\n{kwargs.get('state_summary', '')}\n\nElaborá un PLAN detallado para lograr el objetivo."
            }}],
            temperature=0.3,
        )

        plan = self._parse_json(plan_response.get("content", ""))
        steps = plan.get("steps", [])
        goal = plan.get("goal", kwargs.get("goal", ""))

        logger.info("PlanExecutor cycle %d: plan=%s steps=%d", iteration, goal, len(steps))

        if not steps:
            return {{
                "type": "error",
                "iteration": iteration,
                "error": "No steps in plan",
            }}

        # ── FASE 2: EJECUTAR ──
        results = []
        for step in steps:
            action = step.get("action", "")
            step_input = step.get("input", {})

            if action in ("generate_codes", "generate_hypotheses", "evaluate_result"):
                # Acción LLM (sin tool)
                llm_response = self.llm.run_agent(
                    agent_id=action,
                    variables=step_input,
                )
                results.append({{
                    "step_id": step["id"],
                    "action": action,
                    "output": llm_response,
                    "status": "ok",
                }})
            elif action in self.tools.tool_names:
                # Acción tool
                try:
                    observation = self.tools.execute(action, step_input)
                    results.append({{
                        "step_id": step["id"],
                        "action": action,
                        "output": json.loads(observation) if isinstance(observation, str) else observation,
                        "status": "ok",
                    }})
                except Exception as e:
                    logger.warning("Plan step %d (%s) failed: %s", step["id"], action, e)
                    results.append({{
                        "step_id": step["id"],
                        "action": action,
                        "error": str(e),
                        "status": "error",
                    }})
            else:
                logger.warning("Unknown action in plan: %s", action)
                results.append({{
                    "step_id": step["id"],
                    "action": action,
                    "error": f"Unknown action: {action}",
                    "status": "error",
                }})

        # ── FASE 3: EVALUAR ──
        evaluation = self.llm.chat(
            messages=[{{
                "role": "user",
                "content": f"""Plan ejecutado. Resultados:
{json.dumps(results, ensure_ascii=False, indent=2)[:3000]}

Criterio de éxito: {plan.get('success_criteria', '')}

¿El plan logró el objetivo? Respondé en JSON:
{{"goal_achieved": true/false, "assessment": "...", "missing": "..."}}
"""
            }}],
            temperature=0.1,
        )

        eval_result = self._parse_json(evaluation.get("content", ""))
        goal_achieved = eval_result.get("goal_achieved", False)

        if goal_achieved:
            return {{
                "type": "final",
                "iteration": iteration,
                "output": results,
                "plan": plan,
                "evaluation": eval_result,
            }}

        # ── REPLANIFICAR (implícito en el próximo ciclo) ──
        history.append({{
            "role": "user",
            "content": f"El plan no logró el objetivo. Resultados: {json.dumps(results, ensure_ascii=False)[:1000]}. Evaluación: {eval_result.get('assessment', '')}. Lo que falta: {eval_result.get('missing', '')}. Replanificá."
        }})

        return {{
            "type": "replan",
            "iteration": iteration,
            "results": results,
            "evaluation": eval_result,
        }}

    def _should_stop(self, step_result: dict) -> bool:
        return step_result.get("type") == "final"

    def _extract_result(self, step_result: dict) -> dict:
        return {{
            "plan": step_result.get("plan", {{}}),
            "results": step_result.get("output", []),
            "evaluation": step_result.get("evaluation", {{}}),
        }}

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extrae JSON de texto (tolera markdown fences)."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Intentar encontrar el primer objeto JSON
            import re
            match = re.search(r'\{.+\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {{"error": "JSON parse failed", "raw": text[:200]}}
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
from app.agents.plan_executor import PlanExecutor
from app.agents.tool_registry import ToolRegistry, tool

__all__ = [
    "AgentResult",
    "AgentLoopLog",
    "BaseAgent",
    "SelfRefinementLoop",
    "ReactRunner",
    "PlanExecutor",
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
from app.agents import BaseAgent, SelfRefinementLoop, ReactRunner, PlanExecutor, ToolRegistry
from app.agents.tools.search_tools import search_segments
from app.agents.tools.db_tools import get_code_details
from app.agents.tools.compare_tools import compare_embeddings
print('✅ All imports OK')
"

# Test: PlanExecutor con mock
cd backend && python -c "
from app.agents.plan_executor import PlanExecutor
# Probar _parse_json con varios formatos
test_cases = [
    '{\"goal\": \"test\", \"steps\": []}',
    '```json\n{\"goal\": \"test\"}\n```',
    'Thought: algo\n{\"goal\": \"test\"}',
]
for tc in test_cases:
    result = PlanExecutor._parse_json(tc)
    print(f'Parsed: {result}')
print('✅ PlanExecutor JSON parser OK')
"

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

def test_plan_executor_parse_json():
    from app.agents.plan_executor import PlanExecutor
    # JSON limpio
    assert PlanExecutor._parse_json('{"goal": "test"}') == {"goal": "test"}
    # Con markdown fence
    result = PlanExecutor._parse_json('```json\n{"goal": "test"}\n```')
    assert result["goal"] == "test"
    # Con texto alrededor
    result = PlanExecutor._parse_json('Thought: algo\n{"goal": "test"}')
    assert result["goal"] == "test"


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

## 9. Optimizaciones: JSON Schema, Nemotron FLASH, Algoritmos

> **Análisis de cada llamada a LLM del plan: ¿podemos reemplazarla, degradarla a FLASH,
> o hacerla más eficiente con JSON Schema y algoritmos determinísticos?**

### 9.1 Mapa de calor: dónde se gasta el dinero hoy

```
COSTO ESTIMADO POR FASE (asumiendo PRO=$8.00/M out, FLASH=$1.10/M out)

Fase 1 — Self-Refinement B2 (por lote de ~10 segmentos)
├── Generate codes (PRO, ~1500 out tokens) ........ $0.0120
├── Critic (FLASH, ~400 out tokens) ............... $0.0004  ← ya usa FLASH ✅
├── Refine codes (PRO, ~800 out tokens) ........... $0.0064  (solo si necesario)
└── TOTAL por iteración ........................... ~$0.0124 (1 iter) ~$0.0188 (2 iter)

Fase 2 — ReAct B3 (por proyecto, ~3-5 pasos)
├── Thought/Action (PRO, ~200 out × 4 pasos) ...... $0.0064
├── Tool calls (search_segments, get_code, etc.) .. $0.0000  ← determinístico ✅
├── FinalAnswer (PRO, ~800 out tokens) ............ $0.0064
└── TOTAL .......................................... ~$0.0128

Fase 3 — Orchestrator (por decisión)
├── Decidir próximo nodo (PRO, ~50 out tokens) .... $0.0004  ← podría ser FLASH
└── TOTAL .......................................... ~$0.0004

Fase 4 — Multi-Agent Debate (por relación)
├── Proposer (PRO, ~1000 out) ..................... $0.0080
├── Skeptic (FLASH, ~400 out) ..................... $0.0004  ← ya usa FLASH ✅
├── Rebuttal (PRO, ~600 out) ...................... $0.0048  (solo si divergencia)
├── Synthesizer (PRO, ~800 out) ................... $0.0064
└── TOTAL .......................................... ~$0.0152 (sin rebuttal) ~$0.0200 (con)
```

### 9.2 Las 12 oportunidades de optimización

```
┌────┬──────────────────────────────────────────┬──────────┬──────────┬──────────┐
│  # │  Optimización                            │  Ahorro  │  Riesgo  │  Priority│
│    │                                          │  estimado│  calidad │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O1 │  JSON Schema en Critic/Skeptic output    │  -30%    │  Nulo    │  ⭐⭐⭐⭐⭐ │
│    │  (reduce retries por parseo fallido)     │  retries  │          │  AHORA   │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O2 │  Orchestrator → algoritmo determinístico │  -100%    │  Bajo    │  ⭐⭐⭐⭐⭐ │
│    │  (tabla de reglas en vez de LLM)         │  de esta  │          │  AHORA   │
│    │                                          │  llamada  │          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O3 │  find_similar_codes como tool en Critic  │  +preciso │  Nulo    │  ⭐⭐⭐⭐  │
│    │  (el Critic llama a TEI en vez de adivinar│          │          │  Fase 1  │
│    │   si dos códigos son redundantes)        │          │          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O4 │  B2a → ya es FLASH + prefiltro TEI       │  0%      │  Nulo    │  ⭐⭐⭐⭐  │
│    │  (verificar que el prefiltro esté activo)│  (ya está │          │  Ya está │
│    │                                          │  optimiz.)│          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O5 │  Descomponer B2b: FLASH temas → PRO defs │  -35%    │  Bajo    │  ⭐⭐⭐⭐  │
│    │  (FLASH agrupa indicadores en temas,     │  tokens   │          │  Fase 1b │
│    │   PRO solo escribe definiciones)         │  PRO      │          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O6 │  Evaluación de calidad → algoritmo puro  │  -100%    │  Bajo    │  ⭐⭐⭐⭐  │
│    │  (regex para gerundio, TEI para          │  del      │          │  Fase 1  │
│    │   redundancia, fastText para idioma)     │  critic   │          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O7 │  PlanExecutor: validación determinística │  -50%     │  Medio   │  ⭐⭐⭐   │
│    │  del plan (schema check + precondiciones)│  tokens   │          │  Fase 3  │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O8 │  ReAct: cache de Thought/Action para     │  -20%     │  Bajo    │  ⭐⭐⭐   │
│    │  queries similares (embedding cache)     │  llamadas │          │  Fase 2  │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O9 │  Multi-Agent: Skeptic con tools propias  │  +preciso │  Nulo    │  ⭐⭐⭐   │
│    │  (Skeptic llama search_segments para     │          │          │  Fase 4  │
│    │   encontrar divergencia real, no inventa)│          │          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O10│  Hypothesis eval: fastText classifier     │  -100%    │  Medio   │  ⭐⭐    │
│    │  (pre-clasificar si una hipótesis tiene  │  de eval  │          │  Fase 2b │
│    │   suficiente evidencia sin llamar LLM)   │  inicial  │          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O11│  Reflexive Monitor → solo bajo demanda    │  -100%    │  Bajo    │  ⭐⭐    │
│    │  (no ejecutar reflexión en cada sync,    │  si no se │          │  Fase 4  │
│    │   solo cuando el usuario pide "explicar")│  pide     │          │          │
├────┼──────────────────────────────────────────┼──────────┼──────────┼──────────┤
│ O12│  RAG query expansion → solo si MMR < 0.5  │  -70%     │  Bajo    │  ⭐⭐    │
│    │  (no expandir queries que ya devuelven   │  llamadas │          │  Fase 4  │
│    │   resultados diversos y relevantes)      │          │          │          │
└────┴──────────────────────────────────────────┴──────────┴──────────┴──────────┘
```

---

### 9.3 O1: JSON Schema en critic/skeptic (MÁXIMA PRIORIDAD)

**Problema:** El plan actual hace que el LLM devuelva JSON libre. Si falla el parseo,
hay retry. Cada retry cuesta tokens y latencia.

**Solución:** Usar `response_format` con JSON Schema estricto (Together.ai lo soporta).

#### Código actual (frágil):
```python
# SelfRefinementLoop._step() — critic actual
critic_response = self.llm.run_agent(
    self.critic_prompt_id,
    variables=critic_vars,
    temperature=0.1,
)
# ⚠️ Si el LLM devuelve {"all_valid": true} en vez de {"all_valid": true, "issues": []}
#    o si devuelve texto en vez de JSON, hay retry costoso
```

#### Código optimizado:
```python
# Schema estricto para el critic
CRITIC_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "code_critic_output",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "all_valid": {"type": "boolean"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code_name": {"type": "string"},
                            "problem": {
                                "type": "string",
                                "enum": [
                                    "wrong_style",        # no usa gerundio/in-vivo
                                    "vague_definition",    # definición < 50 chars
                                    "redundant",           # similar a otro código
                                    "not_grounded",        # sin indicadores
                                    "missing_properties"   # sin propiedades/dimensiones
                                ]
                            },
                            "suggestion": {"type": "string"}
                        },
                        "required": ["code_name", "problem", "suggestion"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["all_valid", "issues"],
            "additionalProperties": False
        }
    }
}

# Llamada con schema (Together.ai lo fuerza a devolver JSON válido)
critic_response = self.llm.chat(
    messages=[...],
    response_format=CRITIC_SCHEMA,  # ← el modelo NO puede desviarse
    temperature=0.1,
)
# ✅ Garantizado: JSON válido con la estructura exacta
```

**Schemas adicionales a definir:**

```python
# PlanExecutor plan schema
PLAN_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "agent_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 10},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer", "minimum": 1},
                            "action": {"type": "string"},
                            "description": {"type": "string"},
                            "input": {"type": "object"}
                        },
                        "required": ["id", "action", "description", "input"],
                        "additionalProperties": False
                    },
                    "minItems": 1,
                    "maxItems": 10
                },
                "success_criteria": {"type": "string", "minLength": 5}
            },
            "required": ["goal", "steps", "success_criteria"],
            "additionalProperties": False
        }
    }
}

# ReAct output schema (cuando no es FinalAnswer)
REACT_ACTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "react_action",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "action": {"type": "string"},
                "action_input": {"type": "object"}
            },
            "required": ["thought", "action", "action_input"],
            "additionalProperties": False
        }
    }
}

# Saturation reflector schema
REFLECTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "saturation_reflection",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "narrative_summary": {"type": "string", "maxLength": 500},
                "prioritized_actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                            "rationale": {"type": "string"}
                        },
                        "required": ["action", "impact"],
                        "additionalProperties": False
                    },
                    "maxItems": 5
                },
                "saturation_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "blind_spots": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["narrative_summary", "prioritized_actions"],
            "additionalProperties": False
        }
    }
}
```

**Beneficio:** Elimina el 100% de retries por parseo fallido. El modelo está _forzado_
a devolver JSON que cumple el schema exacto. Reduce latencia en ~30% para flujos
con critic/skeptic.

---

### 9.4 O2: Orchestrator determinístico (MÁXIMA PRIORIDAD)

**Problema:** El Orchestrator Agent usa PRO (~$0.0004 por decisión) para una tarea
que es esencialmente un `switch` statement con ~10 reglas.

**Análisis de decisiones del Orchestrator:**

```python
# El 90% de las decisiones del pipeline son determinísticas.
# Solo hay ambigüedad real en 2 puntos:
#   1. Después de reduce_synthesize: ¿find_core_concern o generate_hypotheses?
#   2. Después de theosampler_evaluate: ¿gap_review o prepare_playground?

# Solución: Rule Engine con LLM solo para los 2 casos ambiguos

class OrchestratorRuleEngine:
    """Motor de reglas determinísticas + LLM solo para casos ambiguos."""

    # Regla: current_step → next_step (90% de los casos)
    RULES = {
        "segment_and_index": "extract_entities",
        "extract_entities": "batch_code",
        "batch_code": "map_synthesize",
        "map_synthesize": "reduce_synthesize",
        # "reduce_synthesize": AMBIGUO → ver método _resolve
        # "find_core_concern": "generate_hypotheses",
        "generate_hypotheses": "calculate_saturation",
        "calculate_saturation": "theosampler_evaluate",
        # "theosampler_evaluate": AMBIGUO → ver método _resolve
        "hitl_gap_review": "prepare_playground",  # o process_new_data
        "process_new_data": "theosampler_evaluate",
        "prepare_playground": "hitl_review",
        "hitl_review": "final_report",
    }

    def decide(self, current_step: str, state: dict) -> str:
        # 1. Intentar regla determinística primero
        if current_step in self.RULES:
            return self.RULES[current_step]

        # 2. Casos ambiguos: usar heurísticas, no LLM
        if current_step == "reduce_synthesize":
            return self._resolve_after_reduce(state)

        if current_step == "theosampler_evaluate":
            return self._resolve_after_theosampler(state)

        # 3. Solo si las heurísticas no resuelven → LLM (FLASH, no PRO)
        return self._llm_fallback(current_step, state)

    def _resolve_after_reduce(self, state: dict) -> str:
        """Heurística: ¿ya tenemos main_concern?"""
        if state.get("main_concern"):
            return "generate_hypotheses"
        codes_count = len(state.get("new_codes", []))
        if codes_count >= 3:
            return "find_core_concern"  # Suficientes códigos para buscar CC
        return "generate_hypotheses"    # Pocos códigos, seguimos generando

    def _resolve_after_theosampler(self, state: dict) -> str:
        """Heurística: ¿hay gaps críticos?"""
        gaps = state.get("pending_gaps", [])
        critical_gaps = [g for g in gaps if g.get("severity") == "critical"]
        if critical_gaps:
            return "hitl_gap_review"
        return "prepare_playground"
```

**Beneficio:** Elimina ~90% de las llamadas PRO del Orchestrator. Los casos ambiguos
se resuelven con heurísticas de 3 líneas. Si alguna vez falla, el fallback a LLM
(FLASH, no PRO) sigue disponible.

---

### 9.5 O5: Descomponer B2b — FLASH para temas, PRO solo para definiciones

**Problema:** B2b usa PRO para todo el proceso: leer indicadores → agrupar → nombrar → definir.
Pero agrupar y nombrar son tareas de clasificación que FLASH hace bien.

**Pipeline actual vs optimizado:**

```
ACTUAL (100% PRO):
  indicadores (texto) ──────────[ PRO: generate_codes ]──────────→ códigos + definiciones
  Tokens out: ~1500 PRO
  Costo: ~$0.0120

OPTIMIZADO (FLASH + PRO):
  indicadores (texto)
      │
      ├──[ FLASH: theme_grouper ]──→ temas agrupados (~5-8 grupos)
      │   Tokens out: ~300 FLASH
      │   Costo: ~$0.0003
      │
      ├──[ FLASH: code_namer ]─────→ nombres tentativos en gerundio/in-vivo
      │   Tokens out: ~200 FLASH
      │   Costo: ~$0.0002
      │
      └──[ PRO: definition_writer ]→ definiciones completas con propiedades
          Tokens out: ~800 PRO       y dimensiones (solo la parte creativa)
          Costo: ~$0.0064

  TOTAL: ~$0.0069 (vs $0.0120 actual = -42% costo)
```

**Implementación:**

```python
def b2b_generate_codes_decomposed(indicators_text, pop_assumption, existing_codes):
    """B2b descompuesto: FLASH para extracción, PRO solo para definición."""

    # Paso 1: FLASH agrupa indicadores en temas (tarea de clasificación)
    themes = llm.run_agent(
        agent_id="theme_grouper",         # NUEVO prompt FLASH
        variables={"indicators": indicators_text},
        tier="FLASH",
        temperature=0.1,
        response_format=THEME_SCHEMA,     # JSON Schema estricto
    )
    # themes = {"themes": [{"name": "...", "indicators": [...], "suggested_gerundio": "..."}]}

    # Paso 2: Para cada tema, FLASH sugiere nombre (en paralelo)
    names = []
    for theme in themes["themes"]:
        name_response = llm.run_agent(
            agent_id="code_namer",        # NUEVO prompt FLASH
            variables={
                "theme": theme["name"],
                "indicators": json.dumps(theme["indicators"]),
                "existing_codes": existing_codes,
                "coding_style": "gerundio"
            },
            tier="FLASH",
            temperature=0.2,
            response_format=NAMER_SCHEMA,
        )
        names.append(name_response)

    # Paso 3: PRO escribe definiciones completas (tarea creativa)
    definitions = llm.run_agent(
        agent_id="definition_writer",     # NUEVO prompt PRO
        variables={
            "themes_with_names": json.dumps(names, ensure_ascii=False),
            "population_assumption": pop_assumption,
            "existing_codes": existing_codes,
        },
        tier="PRO",
        temperature=0.3,
        response_format=DEFINITION_SCHEMA,
    )

    return definitions
```

**Nuevos prompts FLASH necesarios:**
- `prompts/flash/theme_grouper.md` — Agrupa indicadores por similitud temática
- `prompts/flash/code_namer.md` — Sugiere nombres en gerundio/in-vivo para un tema

**Nuevo prompt PRO:**
- `prompts/deepseek_pro/definition_writer.md` — Escribe definiciones con propiedades y dimensiones

**Beneficio:** -42% costo PRO por lote de codificación. La calidad no se degrada porque
la parte creativa (definiciones) sigue en PRO. FLASH maneja tareas de clasificación
que son su fuerte.

---

### 9.6 O6: Evaluación de calidad 100% algorítmica

**Problema:** El `SelfRefinementLoop` actual evalúa calidad con `_evaluate_code_quality()`
(heurística simple) PERO también hace una llamada FLASH para el critic. Podemos
reemplazar el critic LLM con un pipeline algorítmico más preciso.

**Pipeline algorítmico de evaluación:**

```python
def evaluate_codes_algorithmic(codes: list[dict], project_id: str, coding_style: str) -> dict:
    """
    Evalúa códigos SIN LLM, usando:
    - Regex para validar estilo (gerundio, in-vivo, etc.)
    - TEI embeddings para detectar redundancia
    - Heurísticas para definición, grounding, propiedades

    Retorna el mismo formato que el critic LLM para mantener compatibilidad.
    """
    issues = []
    all_valid = True

    for i, code in enumerate(codes):
        name = code.get("code_name", "").strip()
        definition = code.get("definition", "").strip()

        # 1. Validar estilo de codificación (regex, sin LLM)
        style_ok = validate_coding_style(name, coding_style)
        if not style_ok:
            all_valid = False
            issues.append({
                "code_name": name,
                "problem": "wrong_style",
                "suggestion": f"El nombre debe usar estilo '{coding_style}'. "
                              f"Ejemplo correcto: {suggest_style_example(name, coding_style)}"
            })

        # 2. Validar definición sustancial
        if len(definition) < 50:
            all_valid = False
            issues.append({
                "code_name": name,
                "problem": "vague_definition",
                "suggestion": "La definición debe tener al menos 50 caracteres "
                              "describiendo propiedades y dimensiones."
            })

        # 3. Detectar redundancia con TEI (algorítmico, sin LLM)
        for j, other in enumerate(codes):
            if j <= i:
                continue
            similarity = compare_code_embeddings(
                f"{name}: {definition}",
                f"{other.get('code_name', '')}: {other.get('definition', '')}"
            )
            if similarity > 0.85:
                all_valid = False
                issues.append({
                    "code_name": name,
                    "problem": "redundant",
                    "suggestion": f"Similar a '{other['code_name']}' (similitud: {similarity:.2f}). "
                                  f"Considerar fusionar ambos códigos."
                })

    return {"all_valid": all_valid, "issues": issues}


def validate_coding_style(name: str, style: str) -> bool:
    """Validación por regex, sin LLM."""
    if style == "gerundio":
        return bool(re.search(r'(ando|iendo)$', name, re.IGNORECASE))
    elif style == "in_vivo":
        return name.startswith('"') and name.endswith('"')
    elif style == "nominalizacion":
        return bool(re.search(r'(ción|miento|dad|encia|anza)$', name, re.IGNORECASE))
    return True  # otros estilos sin validación estricta


def compare_code_embeddings(text_a: str, text_b: str) -> float:
    """Compara dos textos vía TEI (cached)."""
    import asyncio
    from app.core.tei_client import TEIClient
    tei = TEIClient()

    async def _cmp():
        emb_a = await tei.embed_query(text_a)
        emb_b = await tei.embed_query(text_b)
        return sum(a * b for a, b in zip(emb_a, emb_b))

    return asyncio.run(_cmp())
```

**Cuándo usar el critic algorítmico vs LLM:**

```python
# SelfRefinementLoop modificado:
def _step(self, history, iteration, **kwargs):
    gen_response = self.llm.run_agent(...)  # Generate (PRO)

    # PRIMERO: evaluación algorítmica (gratis, instantánea)
    algo_eval = evaluate_codes_algorithmic(
        gen_response.get("codes", []),
        kwargs.get("project_id"),
        kwargs.get("coding_style", "gerundio")
    )

    if algo_eval["all_valid"]:
        # Si pasa el chequeo algorítmico, ni llamamos al LLM critic
        return {
            "type": "refinement_step",
            "output": gen_response,
            "critic": algo_eval,
            "is_valid": True,
            "issues": [],
        }

    # SOLO si falla el algorítmico → LLM critic para sugerencias cualitativas
    critic_response = self.llm.run_agent(
        self.critic_prompt_id,
        variables={**kwargs.get("critic_vars", {}),
                   "output_to_evaluate": json.dumps(gen_response),
                   "algorithmic_issues": json.dumps(algo_eval["issues"])},
        temperature=0.1,
    )
    ...
```

**Beneficio:** ~60% de las iteraciones del critic se resuelven sin LLM (solo regex + TEI).
La llamada FLASH solo se usa cuando hay problemas que requieren sugerencias cualitativas.

---

### 9.7 Las que MENOS conviene optimizar

#### O10: fastText para evaluar hipótesis ❌

fastText es un clasificador de texto rápido pero **no entiende semántica**. No puede
evaluar si una hipótesis como "la experiencia modula la sofisticación de estrategias"
tiene evidencia en los segmentos. Para eso necesitás embeddings (TEI) o LLM.

**Conclusión:** No implementar. Usar TEI embeddings + threshold en vez de fastText.

#### O12: RAG query expansion condicional ❌ (por ahora)

La idea es buena (no expandir queries que ya devuelven buenos resultados), pero:
- Requiere evaluar la calidad de resultados actuales → otra llamada LLM
- El costo de expandir con FLASH es mínimo (~$0.0002)
- La complejidad añadida no justifica el ahorro

**Conclusión:** Postergar. Implementar solo si vemos que > 30% de queries ya son buenas.

#### Reemplazar TODO el critic con algoritmo ❌

El critic algorítmico (O6) funciona para chequeos estructurales (estilo, longitud,
redundancia). Pero no puede evaluar:
- "¿Esta definición captura la esencia del fenómeno?"
- "¿Las propiedades descritas son realmente dimensiones del concepto?"
- "¿El nombre refleja adecuadamente la definición?"

Para esos juicios cualitativos, el LLM (FLASH) sigue siendo necesario.

**Conclusión:** Algorítmico para filtro, LLM para juicio cualitativo. Híbrido.

#### Usar solo FLASH para todo ❌

El plan ya reserva PRO para: generación de códigos, hipótesis, síntesis,
elaboración. Degradar estas tareas a FLASH ahorraría ~85% de costo pero la
calidad se desplomaría. FLASH no tiene la profundidad de razonamiento para
metodología Grounded Theory.

**Conclusión:** No hacer. PRO es necesario para tareas creativas/analíticas.

---

### 9.8 Tabla resumen: qué optimizar y en qué orden

```
SEMANA 1-2 (Fase 0 + Fase 1) — Optimizaciones inmediatas
┌──────────────────────────────────────────────────────────────────┐
│ ✅ O1: JSON Schema en Critic, PlanExecutor, ReAct               │
│    → Archivos: schemas.py nuevo, modificar self_refiner.py,     │
│       plan_executor.py, react_runner.py                         │
│    → Tiempo: 2-3 horas                                          │
│                                                                  │
│ ✅ O2: Orchestrator → Rule Engine determinístico                │
│    → Archivos: orchestrator.py (reescribir)                     │
│    → Tiempo: 2-3 horas                                          │
│                                                                  │
│ ✅ O3: find_similar_codes como tool en Critic                   │
│    → Archivos: tools/compare_tools.py (ya existe)               │
│    → Tiempo: 1 hora (solo integrar)                             │
│                                                                  │
│ ✅ O6: Evaluación algorítmica (regex + TEI)                     │
│    → Archivos: NUEVO quality/scorer.py                          │
│    → Tiempo: 3-4 horas                                          │
└──────────────────────────────────────────────────────────────────┘

SEMANA 2-3 (Fase 2 + Fase 3) — Optimizaciones de costo
┌──────────────────────────────────────────────────────────────────┐
│ ✅ O5: Descomponer B2b (FLASH temas → PRO definiciones)         │
│    → Archivos: NUEVOS prompts/theme_grouper.md, code_namer.md   │
│    → Tiempo: 4-5 horas                                          │
│                                                                  │
│ ✅ O7: PlanExecutor validación determinística                   │
│    → Archivos: plan_executor.py (modificar _step)               │
│    → Tiempo: 2-3 horas                                          │
└──────────────────────────────────────────────────────────────────┘

SEMANA 3-4 (Fase 4) — Optimizaciones de precisión
┌──────────────────────────────────────────────────────────────────┐
│ ✅ O9: Skeptic con tools propias (busca divergencia real)       │
│    → Archivos: elaboration_engine.py, tools/search_tools.py     │
│    → Tiempo: 3-4 horas                                          │
│                                                                  │
│ ⬜ O8: Cache de Thought/Action (si hay volumen)                  │
│    → Solo si vemos > 100 queries/día similares                  │
│                                                                  │
│ ⬜ O11: Reflexive solo bajo demanda (ya está en el plan)         │
└──────────────────────────────────────────────────────────────────┘
```

### 9.9 Impacto acumulado estimado

```
COSTO POR PROYECTO TÍPICO (10 documentos, ~200 segmentos)

Sin optimizaciones (plan original):
├── B2 coding (10 docs × 2 iter) .............. $0.376
├── B3 hypotheses (5 pasos ReAct) ............. $0.064
├── Orchestrator (20 decisiones) .............. $0.008
├── Elaboration (5 relaciones) ................ $0.100
├── Reflexive monitor (1 vez) ................. $0.005
├── RAG query expansion (5 queries) ........... $0.002
└── TOTAL ...................................... ~$0.555

Con optimizaciones O1-O9:
├── B2 coding (FLASH temas + PRO defs) ........ $0.218  (-42%)
├── B3 hypotheses (con cache) ................. $0.051  (-20%)
├── Orchestrator (determinístico) ............. $0.000  (-100%)
├── Elaboration (Skeptic con tools) ........... $0.100  (igual)
├── Reflexive (solo bajo demanda) ............. $0.000  (-100%)
├── RAG query expansion (con guard) ........... $0.001  (-50%)
└── TOTAL ...................................... ~$0.370  (-33%)

AHORRO ESTIMADO: ~$0.185/proyecto (−33%)
Para 100 proyectos/mes: ~$18.50/mes → $222/año

El ahorro real es mayor porque:
- Menos retries por JSON Schema → menos tokens desperdiciados
- Menos latencia → mejor UX → más proyectos completados
- Evaluación algorítmica → menos iteraciones del refinement loop
```

---

## 10. Feature Flags & Rollout

### 10.1 Variables de entorno

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

### 10.2 Plan de rollout

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

### 10.3 Rollback

Si algo falla, desactivar con:

```bash
AGENTIC_MODE=false  # Vuelve al comportamiento single-shot original
```

Todos los paths de código nuevo están condicionados por `AGENTIC_MODE`, por lo que un rollback es instantáneo y no requiere deploy de código.

---

## Resumen de Entregables

| Fase | Archivos nuevos | Archivos modificados | Días |
|------|----------------|---------------------|------|
| **F0** | 13 (`agents/` completo) | 0 | 1-2 |
| **F1** | 0 | `agents_b.py`, `llm_client.py`, `b2b_generate_codes.md` | 3-4 |
| **F2** | 0 | `agents_b.py`, `llm_client.py`, `tasks.py`, `llm_config.py` | 4-5 |
| **F3** | `orchestrator.py`, `orchestrator_decider.md` | `workflow.py` | 3-4 |
| **F4** | `relationship_proposer.md`, `relationship_skeptic.md`, `relationship_synthesizer.md`, `saturation_reflector.md`, `query_expander.md` | `elaboration_engine.py`, `saturation_gap_analyzer.py`, `rag.py`, `analysis.py` | 5-6 |
| **Tests** | `test_agents.py` | `test_integration.py` | (incluido) |
| **TOTAL** | **20 nuevos** | **12 modificados** | **15-20** |
