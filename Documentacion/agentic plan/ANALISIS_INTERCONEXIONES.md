# Análisis de Interconexiones — Capa Agencial GT

> **Fecha:** 2026-06-16
> **Componentes analizados:** 11 archivos en `backend/app/agents/` + 5 prompts + 3 servicios existentes

---

## 1. Grafo de dependencias

```
                        ┌──────────────────────┐
                        │   __init__.py         │
                        │   (exports públicos)  │
                        └──────┬───────────────┘
                               │ re-exporta
          ┌────────────────────┼────────────────────────┐
          │                    │                        │
          ▼                    ▼                        ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐
│   base.py       │  │ tool_registry.py│  │  orchestrator.py        │
│                 │  │                 │  │                         │
│ AgentResult     │  │ ToolRegistry    │  │ OrchestratorRuleEngine  │
│ AgentLoopLog    │  │ @tool           │  │   RULES dict (11 reglas)│
│ BaseAgent       │  │                 │  │   _resolve_after_* (2)  │
│  └─_build_      │  │                 │  │   _llm_fallback         │
│    assistant_   │  │                 │  │                         │
│    msg()        │  │                 │  │ depende de:             │
│                 │  │                 │  │   llm_client (opcional) │
│ depende de:     │  │                 │  └──────────┬──────────────┘
│   (nada externo)│  │                 │             │ usado por
└────────┬────────┘  └────────┬────────┘             │ workflow.py
         │                    │                      │ (Fase 3)
         │ hereda             │ compone              │
         │                    │                      │
    ┌────┴────────────┬───────┴──────────┐           │
    │                 │                  │           │
    ▼                 ▼                  ▼           │
┌───────────┐  ┌────────────┐  ┌──────────────┐     │
│self_refiner│ │react_runner│  │plan_executor │     │
│           │  │            │  │              │     │
│SelfRefine│  │ReactRunner │  │PlanExecutor  │     │
│mentLoop  │  │            │  │              │     │
│          │  │  contiene: │  │  contiene:   │     │
│PRO: gen  │  │ ToolReg.   │  │  ToolReg.    │     │
│FLASH:crit│  │ _parse_    │  │  _parse_json │     │
│          │  │   react()  │  │              │     │
│          │  │ _extract_  │  │              │     │
│          │  │   balanced │  │              │     │
│          │  │   _json()  │  │              │     │
└──────────┘  └──────┬─────┘  └──────────────┘
                     │
                     │ usa
                     ▼
            ┌────────────────┐
            │  tools/        │
            │  ├─db_tools.py │──────▶ PostgreSQL (sync session)
            │  ├─compare_    │──────▶ TEIClient → TEI Server
            │  │  tools.py   │
            │  └─search_     │──────▶ RAGService → pgvector + TEI
            │     tools.py   │
            └────────────────┘
```

---

## 2. Flujo de datos completo — Self-Refinement Loop

```
ENTRADA: proyecto_id, indicadores, population_assumption

Worker llama a: SelfRefinementLoop.run(project_id, generate_vars={...}, critic_vars={...})
                            │
                            ▼
                 ┌─── BaseAgent.run() ───┐
                 │  history = [system]   │
                 │  for i in max_iter:   │
                 │    step = _step()     │
                 │    if _should_stop(): │
                 │      return result    │
                 └───────────────────────┘
                            │
                            ▼ iteración 1
                 ┌─── SelfRefinementLoop._step() ───┐
                 │                                    │
                 │  1. llm.run_agent("b2b", vars)     │────▶ Workers/heavy/llm_client.py
                 │     → DeepSeek V4 Pro              │      carga prompt: b2b_generate_codes.md
                 │     → genera códigos + razona      │      ┌─────────────────────────┐
                 │     → response = {                 │      │ Together.ai API         │
                 │         "codes": [...],            │      │ POST /chat/completions  │
                 │         "_reasoning_content":"..." │      │ model: deepseek-pro     │
                 │       }                            │      │ response_format: json   │
                 │                                    │      └─────────────────────────┘
                 │  2. _build_assistant_message()     │
                 │     → inyecta reasoning_content    │
                 │     → history.append(msg)          │
                 │                                    │
                 │  3. llm.run_agent("code_critic")   │────▶ Workers/heavy/llm_client.py
                 │     → Gemma/Nemotron FLASH         │      carga: code_critic.md
                 │     → evalúa calidad               │
                 │     → response = {                 │
                 │         "all_valid": true|false,   │
                 │         "issues": [...]            │
                 │       }                            │
                 │                                    │
                 │  return {                          │
                 │    "is_valid": ...,                │
                 │    "output": ...,                  │────▶ BaseAgent.run()
                 │    "had_reasoning": true           │      evalúa _should_stop()
                 │  }                                 │
                 └────────────────────────────────────┘

SALIDA: AgentResult(success=True, data={codes: [...]}, iterations=N, had_reasoning=True)
```

---

## 3. Flujo de datos completo — ReAct Loop

```
ENTRADA: proyecto_id, role_description

Worker llama a: ReactRunner.run(project_id)
                            │
                            ▼
                 ┌─── BaseAgent.run() ───┐
                 │  history = [system]   │
                 │  for i in max_iter:   │
                 │    step = _step()     │
                 └───────────────────────┘
                            │
                            ▼ iteración N
                 ┌─── ReactRunner._step() ───────────────┐
                 │                                        │
                 │  1. llm.chat(history + ["Next step?"]) │────▶ TogetherLLM.chat()
                 │     → DeepSeek V4 Pro                  │      ┌──────────────────┐
                 │     → response = {                     │      │ Together.ai API  │
                 │         "content": "Thought:...\n      │      │ model: deepseek  │
                 │           Action: search_segments\n    │      │   -pro           │
                 │           Action Input: {...}",        │      └──────────────────┘
                 │         "reasoning_content": "..."     │
                 │       }                                │
                 │                                        │
                 │  2. _parse_react(content)              │
                 │     → balanced bracket matching        │
                 │     → extrae Action + Action Input     │
                 │                                        │
                 │  3. tools.execute(action, input)       │────▶ ToolRegistry.execute()
                 │     → search_segments(query, pid, k)   │      ┌──────────────────┐
                 │     → TEIClient.embed_query()          │─────▶│ TEI Server :8080 │
                 │     → RAGService.search()              │─────▶│ PostgreSQL       │
                 │     → observation = JSON string        │      │  pgvector HNSW   │
                 │                                        │      │  GIN ts_rank     │
                 │  4. _build_assistant_message()         │      └──────────────────┘
                 │     → inyecta reasoning_content        │
                 │     → history.append(assistant_msg)    │
                 │     → history.append(observation)      │
                 │                                        │
                 │  return {                              │
                 │    "type": "tool_call",                │────▶ BaseAgent.run()
                 │    "had_reasoning": true               │      NO es final →
                 │  }                                     │      siguiente iteración
                 └────────────────────────────────────────┘

         ... se repite hasta que el LLM emite FinalAnswer ...

SALIDA: AgentResult(success=True, data={hypotheses: [...]}, iterations=N, had_reasoning=True)
```

---

## 4. Tabla de acoplamiento entre componentes

```
┌──────────────────────┬──────────────────────────────────────────────────────┐
│ COMPONENTE           │  DEPENDE DE                                          │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ base.py              │  (stdlib only: logging, time, dataclasses)           │
│ BaseAgent            │  NINGUNA dependencia externa                         │
│ AgentResult          │  NINGUNA                                             │
│ AgentLoopLog         │  NINGUNA                                             │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ tool_registry.py     │  (stdlib: json, logging, typing)                     │
│ ToolRegistry         │  NINGUNA dependencia externa                         │
│ @tool                │  NINGUNA                                             │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ orchestrator.py      │  (stdlib: logging, typing)                           │
│ OrchestratorRuleEng. │  llm_client (OPCIONAL — solo para fallback)          │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ self_refiner.py      │  BaseAgent (herencia)                                │
│ SelfRefinementLoop   │  llm_client (inyectado en __init__)                  │
│                      │  prompts: b2b_generate_codes.md (PRO)                │
│                      │  prompts: code_critic.md (FLASH)                     │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ react_runner.py      │  BaseAgent (herencia)                                │
│ ReactRunner          │  ToolRegistry (inyectado en __init__)                │
│                      │  llm_client (inyectado en __init__)                  │
│                      │  prompts: react_hypothesis.md (PRO)                  │
│ _parse_react()       │  _extract_balanced_json() (static, interno)          │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ plan_executor.py     │  BaseAgent (herencia)                                │
│ PlanExecutor         │  ToolRegistry (inyectado en __init__)                │
│                      │  llm_client (inyectado en __init__)                  │
│ _parse_json()        │  (interno, static)                                   │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ tools/db_tools.py    │  SQLAlchemy (sync session → PostgreSQL)              │
│ get_all_codes        │  NINGUNA dependencia de LLM                          │
│ get_code_details     │  NINGUNA dependencia de LLM                          │
│ get_existing_hyps    │  NINGUNA dependencia de LLM                          │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ tools/compare_tools  │  TEIClient → TEI Server :8080 (voyage-4-nano ONNX)  │
│ compare_embeddings   │  NINGUNA dependencia de LLM                          │
│ find_similar_codes   │  RAGService → pgvector (HNSW)                        │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ tools/search_tools   │  TEIClient → TEI Server :8080                        │
│ search_segments      │  RAGService → RRF (semantic + lexical)               │
│ search_similar_codes │  NINGUNA dependencia de LLM                          │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ prompts/deepseek_pro │  Ninguno (son archivos .md cargados por llm_client)  │
│ prompts/deepseek_flash│ Ninguno                                             │
└──────────────────────┴──────────────────────────────────────────────────────┘
```

---

## 5. Puntos de integración con el sistema existente

```
NUEVO (agents/)                    EXISTENTE (sin modificar)
─────────────────────────────────  ─────────────────────────────
                                   backend/app/core/
                                   ├── together_client.py    ← LLM calls (PRO/FLASH)
                                   ├── tei_client.py         ← embeddings (voyage-4-nano)
                                   ├── config.py             ← env vars
                                   └── llm_config.py         ← model registry

                                   backend/app/services/
                                   └── rag.py                ← RAGService.search()

                                   backend/app/db/
                                   └── database.py           ← AsyncSessionLocal

                                   workers/heavy/
                                   ├── llm_client.py         ← LLMClient (Celery)
                                   └── agents_b.py           ← b2_open_code, b3_generate

                                   workers/fast/
                                   └── llm_client.py         ← LLMClient (HTTP directo)

                                   workers/nlp/
                                   └── segmentador.py        ← ProgressiveSegmenter
```

---

## 6. Flujo de feature flags

```
AGENTIC_MODE=true
    │
    ├──▶ workers/heavy/agents_b.py
    │      if AGENTIC_MODE:
    │          b2b_response = llm.run_self_refinement(...)  ← SelfRefinementLoop
    │      else:
    │          b2b_response = _b2b_generate_codes(...)      ← single-shot actual
    │
    ├──▶ workers/heavy/agents_b.py
    │      if AGENTIC_MODE:
    │          raw_hyps = b3_generate_hypotheses_agentic()  ← ReactRunner
    │      else:
    │          raw_hyps = response.get("hypotheses", [])    ← single-shot actual
    │
    └──▶ backend/app/core/workflow.py
           if AGENTIC_MODE:
               orch = OrchestratorRuleEngine(llm)
               next_node = orch.decide(current_step, state)
           else:
               next_node = DEFAULT_ORDER[current_step]       ← determinístico

AGENTIC_NATIVE_FC=true  (futuro)
    └──▶ ReactRunner(use_native_fc=True)
           → _step_native_fc() usa tools parameter de la API
           → en vez de text parsing Thought:/Action:
```

---

## 7. Ciclo de vida de reasoning_content

```
┌─────────────────────────────────────────────────────────────────┐
│              FLUJO DE reasoning_content (DeepSeek V4 Pro)        │
│                                                                  │
│  1. GENERACIÓN                                                   │
│     DeepSeek V4 Pro recibe prompt                               │
│     → razona internamente (RLVR)                                │
│     → genera reasoning_content + content                        │
│                                                                  │
│  2. CAPTURA (together_client.py / llm_client.py)                │
│     message = response.choices[0].message                       │
│     reasoning = getattr(message, "reasoning_content", None)     │
│     return {"content": ..., "reasoning_content": reasoning}     │
│                                                                  │
│  3. INYECCIÓN EN HISTORIAL (BaseAgent._build_assistant_message) │
│     assistant_msg = {"role":"assistant", "content": content}    │
│     if reasoning:                                                │
│         assistant_msg["reasoning_content"] = reasoning          │
│     history.append(assistant_msg)                               │
│                                                                  │
│  4. REINYECCIÓN EN SIGUIENTE LLAMADA                            │
│     El history incluye todos los assistant_msg previos          │
│     → cada uno con su reasoning_content                         │
│     → el modelo ve su propio razonamiento anterior              │
│     → NO tiene que re-razonar desde cero                        │
│     → no divaga, no repite acciones, no alucina                 │
│                                                                  │
│  5. TRAZABILIDAD                                                │
│     AgentResult.had_reasoning = True                            │
│     AgentLoopLog.had_reasoning = True                           │
│     → visible en logs y métricas                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Riesgos de interconexión

| Riesgo | Componentes afectados | Mitigación |
|--------|----------------------|------------|
| **ToolRegistry.execute() falla** | ReactRunner, PlanExecutor → bucle se rompe | `execute()` captura TypeError y Exception, devuelve `{"error": ...}` como JSON string. El LLM lee el error y decide reintentar con otra tool. |
| **llm_client no disponible** | SelfRefinementLoop, ReactRunner, PlanExecutor → no pueden llamar al LLM | `BaseAgent.run()` captura excepciones en `_step()` y devuelve `AgentResult(success=False, error=...)`. El caller puede hacer fallback al single-shot. |
| **reasoning_content perdido** | Todos los runners → el agente divaga | `_build_assistant_message()` es el ÚNICO punto donde se inyecta. Si `llm_client` no retorna `reasoning_content`, el `if reasoning:` simplemente no lo agrega — no rompe nada. |
| **Prompt no encontrado** | llm_client.run_agent() → error | El `PromptLoader` tiene fallback: prueba .md → .txt → error claro. El caller recibe el error y puede reintentar con otro agent_id. |
| **JSON parse falla en ReAct** | ReactRunner._parse_react() → bucle no avanza | `_extract_balanced_json()` retorna None si el JSON está malformado. `_parse_react()` devuelve dict vacío → `_step()` intenta ejecutar tool con action="" → ToolRegistry.execute() devuelve error → el LLM ve el error y corrige. |
| **Orchestrator decide mal** | workflow.py → pipeline va por camino incorrecto | El `OrchestratorRuleEngine` tiene 11 reglas duras + 2 heurísticas + fallback a `final_report`. La decisión incorrecta solo ocurre si el LLM fallback decide mal → el pipeline eventualmente llega a `final_report` por timeout. |
