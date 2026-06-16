# 🏗️ Checklist de Progreso — Arquitectura Agencial CoT

> **Actualizado:** 2026-06-16  
> **Plan de referencia:** `Documentacion/agentic plan/Plan_Implementacion_Agencial.md`

---

## Fase 0 — Infraestructura Agencial Base

- [x] `backend/app/agents/__init__.py` — exports: BaseAgent, ToolRegistry, 3 runners, tool
- [x] `backend/app/agents/base.py` — AgentResult, AgentLoopLog, BaseAgent + `_build_assistant_message()` (reasoning preservation)
- [x] `backend/app/agents/tool_registry.py` — ToolRegistry, `@tool`, `to_openai_tools()`
- [x] `backend/app/agents/tools/__init__.py` — lazy imports (TEI/Redis no bloquean db_tools)
- [x] `backend/app/agents/tools/db_tools.py` — get_all_codes, get_code_details, get_existing_hypotheses
- [x] `backend/app/agents/tools/compare_tools.py` — compare_embeddings, find_similar_codes (requiere TEI)
- [x] `backend/app/agents/tools/search_tools.py` — search_segments, search_similar_codes (requiere TEI+RAG)
- [x] `backend/app/agents/self_refiner.py` — SelfRefinementLoop (Generate→Critic→Refine)
- [x] `backend/app/agents/react_runner.py` — ReactRunner (Thought→Action→Observation)
- [x] `backend/app/agents/plan_executor.py` — PlanExecutor (Plan→Execute→Evaluate)
- [x] `backend/app/agents/orchestrator.py` — OrchestratorAgent / OrchestratorRuleEngine

### Fase 0b — Corrección reasoning_content (G1, G2) ⚠️ PENDIENTE (no tocar hasta rebuild)

- [ ] `backend/app/core/together_client.py` — `chat()` debe capturar `reasoning_content` (documentado, sin aplicar)
- [ ] `workers/heavy/llm_client.py` — `_call_llm()` debe capturar `reasoning_content` (documentado, sin aplicar)
- [ ] `workers/fast/llm_client.py` — `_call_llm()` debe capturar `reasoning_content` (documentado, sin aplicar)

---

## Fase 1 — Self-Refinement Loop (B2)

- [ ] `workers/heavy/agents_b.py` — feature flag `AGENTIC_MODE` + `b2_open_code()` modificado
- [ ] `workers/heavy/llm_client.py` — `run_self_refinement()`
- [ ] `prompts/deepseek_pro/b2b_generate_codes.md` — sección `[SELF-CRITIC]`

---

## Fase 2 — ReAct Agent (B3)

- [ ] `workers/heavy/agents_b.py` — `b3_generate_hypotheses_agentic()`
- [ ] `workers/heavy/llm_client.py` — `run_react_loop()`
- [ ] `prompts/deepseek_pro/b3_hypothesis_generator.md` — versión ReAct-aware

---

## Fase 3 — Orchestrator Agent

- [ ] `backend/app/agents/orchestrator.py` — OrchestratorRuleEngine (determinístico)
- [ ] `backend/app/core/workflow.py` — nodo `orchestrator_decide` + edge dinámico

---

## Fase 4 — Debate + Reflexive + RAG

- [ ] `backend/app/services/elaboration_engine.py` — `elaborate_relationship_agentic()`
- [ ] `backend/app/services/saturation_gap_analyzer.py` — `ReflexiveSaturationMonitor`
- [ ] `backend/app/services/rag.py` — `agentic_search()`

---

## Optimizaciones (Sección 9 del plan)

- [x] O2: Orchestrator → Rule Engine (implementado: OrchestratorRuleEngine con 11 reglas + 2 heuristicas)
- [ ] O1: JSON Schema en Critic/Skeptic output
- [ ] O3: find_similar_codes como tool en Critic
- [ ] O5: Descomponer B2b (FLASH temas → PRO definiciones)
- [ ] O6: Evaluación algorítmica (regex + TEI)
- [ ] O7: PlanExecutor validación determinística
- [ ] O8: Cache de Thought/Action
- [ ] O9: Skeptic con tools propias

---

## Tests

- [ ] `tests/unit/test_agents.py` — unit tests para BaseAgent, ToolRegistry, runners
- [ ] `tests/test_integration.py` — A/B testing agentic vs single-shot
