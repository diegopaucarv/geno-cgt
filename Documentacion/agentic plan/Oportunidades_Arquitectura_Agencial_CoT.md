# Oportunidades de Arquitectura Agencial CoT — Sistema GT

> **Análisis de transformación de llamadas LLM lineales → bucles agenciales con Chain of Thought, ReAct, y tool-use.**
>
> Fecha: 2026-06-15

---

## 1. Diagnóstico del Estado Actual

### 1.1 ¿Cómo se llama al LLM hoy?

El sistema tiene **dos clientes LLM** que operan en modo _single-shot_:

| Cliente | Ubicación | Patrón actual |
|---------|-----------|---------------|
| `TogetherLLM` | `backend/app/core/together_client.py` | `invoke_prompt(template, **vars)` → 1 llamada → respuesta |
| `LLMClient` (workers) | `workers/heavy/llm_client.py`, `workers/fast/llm_client.py` | `run_agent(agent_id, variables)` → 1 llamada → JSON |

**En ningún punto del sistema el LLM:**
- Ve su propia respuesta anterior y decide refinarla
- Elige qué herramienta llamar
- Itera hasta alcanzar un criterio de calidad
- Mantiene un _scratchpad_ de pensamiento entre llamadas
- **Preserva su `reasoning_content` entre turnos** — DeepSeek V4 Pro (modelo PRO) genera cadena de razonamiento nativa (RLVR) que se descarta: `together_client.py:85` y `llm_client.py:463` solo capturan `message.content`, no `message.reasoning_content`. Esto implica que ~40-60% de los tokens de salida ya pagados se tiran a la basura.

### 1.2 Cimientos existentes (¿qué ya tenés?)

El sistema **ya tiene** piezas que son fundamentales para una arquitectura agencial:

| Componente | Archivo | Rol actual | Potencial agencial |
|------------|---------|------------|-------------------|
| **Proposer/Critic pairs** | `prompts/deepseek_pro/` | Llamadas secuenciales separadas | Ya son el corazón de un **self-refinement loop** |
| **LangGraph StateGraph** | `core/workflow.py` | Orquesta nodos con checkpoints | Ya es un **orquestador agencial** (solo falta el bucle interno) |
| **PostgresSaver** | `langgraph_checkpoints.py` | Persiste estado entre nodos | **Memoria de largo plazo** para agentes |
| **Prompt Loader** | `prompts/loader.py` | Carga templates | Puede cargar **system prompts agenciales** |
| **RAG Service** | `services/rag.py` | Búsqueda semántica + léxica | **Tool #1** para agentes |
| **TEI Client** | `core/tei_client.py` | Embeddings | **Tool #2** (comparación semántica) |
| **Celery workers** | `workers/*/tasks.py` | Tareas asíncronas | **Tool #3** (acciones con side-effects) |
| **Database** | `models/domain/*.py` | Persistencia | **Tool #4** (consultas estructuradas) |
| **DeepSeek V4 Pro (RLVR)** | `core/llm_config.py` | Modelo PRO con razonamiento nativo | **Razonamiento interno** que debe preservarse entre turnos del bucle (`reasoning_content`) |

> ⚠️ **Gap crítico detectado:** DeepSeek V4 Pro es un modelo de razonamiento nativo (RLVR).
> Together.ai devuelve `response.choices[0].message.reasoning_content` con la cadena de
> pensamiento del modelo. Nuestro código descarta este campo. Sin él, el agente
> pierde el contexto de su reflexión entre turnos y comienza a divagar, repetir
> acciones, o alucinar datos. **Corregir esto es requisito para que cualquier
> bucle agencial funcione correctamente.**

---

## 2. Mapa de Oportunidades — 6 Patrones Agenciales Identificados

```
┌─────────────────────────────────────────────────────────────────┐
│                  OPORTUNIDADES POR CAPA                          │
├──────────┬──────────────────────────────────────────────────────┤
│ CAPA     │  PATRÓN AGENCIAL RECOMENDADO                         │
├──────────┼──────────────────────────────────────────────────────┤
│ Agent A  │  P1: Self-Refinement Loop (Proposer → Critic → Fix)  │
│ Agent B  │  P2: ReAct con Tools (Thought → Action → Observe)    │
│ Elab.    │  P3: Multi-Agent Debate (Generate → Challenge → Synth)│
│ Pipeline │  P4: Orchestrator Agent (Plan → Dispatch → Evaluate) │
│ Saturation│ P5: Reflexive Monitor (Observe → Diagnose → Prescribe)│
│ RAG      │  P6: Tool-Augmented Retrieval (Query → Expand → MMR) │
└──────────┴──────────────────────────────────────────────────────┘
```

---

## 3. Oportunidad #1 — Self-Refinement Loop (Agentes A y B)

### 📍 Dónde: `workers/heavy/agents_b.py` → `b2_open_code()`

**Estado actual:**
```
b2_open_code(pid):
  1. b2a_extract_indicators() → LLM call → raw indicators
  2. b2b_generate_codes()    → LLM call → candidate codes  
  3. b2_5_assign_codes()     → algoritmo (no LLM)
```

Cada paso es una sola llamada. Si el LLM genera un código pobre, no hay segunda oportunidad.

**Oportunidad:** Convertir `b2b_generate_codes` en un **bucle de auto-refinamiento**:

```python
def b2b_generate_codes_agentic(pid, indicators, max_iterations=3):
    """
    Patrón: Generate → Self-Critic → Refine → Converge
    """
    history = [
        {"role": "system", "content": CODING_AGENT_SYSTEM_PROMPT},
        {"role": "user",   "content": f"Indicators: {indicators}"}
    ]
    
    for iteration in range(max_iterations):
        # 1. GENERATE: el LLM propone códigos (PRO — razona internamente)
        response = llm.chat(history + [
            {"role": "user", "content": GENERATE_CODES_TASK}
        ])
        proposed_codes = parse_json(response["content"])
        
        # ⚠️ CLAVE: Preservar reasoning_content de DeepSeek V4 Pro
        assistant_msg = {"role": "assistant", "content": json.dumps(proposed_codes)}
        if response.get("reasoning_content"):
            assistant_msg["reasoning_content"] = response["reasoning_content"]
        history.append(assistant_msg)
        
        # 2. SELF-CRITIC: el LLM evalúa sus propios códigos (FLASH — más barato)
        critique = llm.chat(history + [
            {"role": "user", "content": CRITIC_TASK}
        ])
        evaluation = parse_json(critique["content"])
        
        # 3. DECIDE: ¿convergió?
        if evaluation.get("all_codes_valid", False):
            break
        
        # 4. REFINE: el LLM corrige solo los códigos problemáticos
        #    El modelo aún tiene acceso a su reasoning_content previo
        history.append({"role": "user", "content": 
            f"Fix these issues: {evaluation['issues']}"})
    
    return proposed_codes
```

**Archivos afectados:**
- `workers/heavy/agents_b.py` — `b2b_generate_codes()` → `b2b_generate_codes_agentic()`
- `workers/heavy/llm_client.py` — nuevo método `run_agentic_loop()`
- `prompts/deepseek_pro/b2b_generate_codes.md` — añadir sección `[SELF-CRITIC]`
- `prompts/deepseek_pro/b2_critic.md` — adaptar para self-critique en bucle

**System Prompt propuesto:**
```markdown
[ROL]
Eres un codificador cualitativo experto en Grounded Theory (Strauss & Corbin).
Operás en un bucle de mejora continua.

[CICLO DE TRABAJO]
1. GENERAR: Proponé códigos basados en los indicadores.
2. AUTO-EVALUAR: Verificá que cada código cumpla:
   - Gerundio o in-vivo (según estilo configurado)
   - Definición clara con propiedades y dimensiones
   - Distinguible de otros códigos (no redundante)
   - Anclado en los indicadores (no abstracto sin evidencia)
3. REFINAR: Si algún código no cumple, reescribilo.
4. REPETIR hasta que todos los códigos pasen.
```

**Beneficio esperado:**
- Reducción de códigos redundantes o vagos
- Mayor grounding en los datos (menos alucinación conceptual)
- Sin cambios en la API externa (el caller sigue recibiendo `{codes: [...]}`)

**Costo estimado:** ~2-3x más tokens por documento (típicamente 2 iteraciones bastan).
**Nota sobre reasoning_content:** Los tokens de razonamiento de DeepSeek V4 Pro YA se generan y YA se cobran
(están en `completion_tokens`). Preservarlos en el historial NO aumenta el costo — solo dejamos de descartarlos.
El beneficio es que el modelo no tiene que re-razonar desde cero en cada iteración, lo que reduce
el número de iteraciones necesarias.

---

## 4. Oportunidad #2 — ReAct con Tools (Hypothesis Generation B3)

### 📍 Dónde: `workers/heavy/agents_b.py` → `b3_generate_hypotheses()`

**Estado actual:**
```python
def b3_generate_hypotheses(pid):
    codes = get_all_codes(pid)
    segments = get_sample_segments(pid)
    response = llm.run_agent("b3", variables={
        "codes": json.dumps(codes),
        "segments": json.dumps(segments)
    })
    return response  # single-shot
```

**Oportunidad:** Convertir en un **agente ReAct** que puede:
1. **Pensar** qué tipo de hipótesis buscar
2. **Actuar** llamando herramientas (buscar segmentos, comparar códigos)
3. **Observar** los resultados
4. **Decidir** si necesita más evidencia

```python
def b3_generate_hypotheses_agentic(pid, max_steps=5):
    """
    Patrón ReAct: Thought → Action → Observation → ... → Final Answer
    """
    
    # Herramientas disponibles para el agente
    tools = {
        "search_segments": lambda query, top_k: rag_service.search(query, pid, top_k),
        "get_code_details": lambda code_id: db.get_code_with_incidents(code_id),
        "compare_codes": lambda c1, c2: tei.compare_embeddings(c1, c2),
        "check_existing_hypotheses": lambda: db.get_hypotheses(pid),
    }
    
    history = [{"role": "system", "content": REACT_SYSTEM_PROMPT}]
    
    for step in range(max_steps):
        response = llm.chat(history + [{"role": "user", "content": "Next step?"}])
        
        parsed = parse_react_output(response["content"])
        # parsed = {"thought": "...", "action": "search_segments", "action_input": "..."}
        # o parsed = {"thought": "...", "final_answer": {...}}
        
        if "final_answer" in parsed:
            return parsed["final_answer"]
        
        # Ejecutar tool
        tool_result = execute_tool(parsed["action"], parsed["action_input"], tools)
        
        # ⚠️ CLAVE: Preservar reasoning_content en el historial
        assistant_msg = {"role": "assistant", "content": response["content"]}
        if response.get("reasoning_content"):
            assistant_msg["reasoning_content"] = response["reasoning_content"]
        history.append(assistant_msg)
        history.append({"role": "user", "content": f"Observation: {tool_result}"})
    
    return {"error": "Max steps reached"}
```

> 📌 **Upgrade path — Native Function Calling:** El formato `Thought:/Action:/Action Input:`
> con parsing de texto (regex) es frágil con modelos de razonamiento que generan `<think>` tags.
> La alternativa robusta es usar el parámetro `tools` nativo de la API (Together.ai lo soporta):
> ```python
> response = client.chat.completions.create(
>     model="deepseek-ai/DeepSeek-V4-Pro",
>     messages=history,
>     tools=[{"type": "function", "function": {"name": "search_segments", ...}}],
>     tool_choice="auto"
> )
> # response.choices[0].message.tool_calls → JSON estructurado garantizado
> ```
> Activar con feature flag `AGENTIC_NATIVE_FC=true`. La ventaja: el modelo decide autónomamente
> si llamar una tool o responder, los argumentos son JSON validado, y el `reasoning_content`
> se preserva automáticamente entre tool calls.

**System Prompt propuesto para ReAct:**
```markdown
[ROL]
Eres un generador de hipótesis para Grounded Theory. Trabajás con el método
de comparación constante. Tenés acceso a herramientas para buscar evidencia.

[FORMATO DE RESPUESTA]
Respondé SIEMPRE en este formato exacto:

Thought: [Tu razonamiento paso a paso sobre qué hacer ahora]
Action: [Nombre de la herramienta a usar, o "FinalAnswer"]
Action Input: [Input para la herramienta, en JSON]

Cuando tengas suficiente evidencia:
Thought: [Por qué la hipótesis está bien fundada]
FinalAnswer: {{"hypotheses": [...]}}

[HERRAMIENTAS DISPONIBLES]
1. search_segments(query, top_k=5) — busca segmentos semánticamente
2. get_code_details(code_id) — obtiene definición + incidentes de un código
3. compare_codes(code_id_a, code_id_b) — similitud semántica entre códigos
4. check_existing_hypotheses() — lista hipótesis ya generadas

[CÓDIGOS DISPONIBLES]
{codes_json}

[REGLAS]
- Generá hipótesis que relacionen 2+ códigos entre sí.
- Cada hipótesis debe estar respaldada por al menos 2 segmentos.
- Si no encontrás evidencia, no inventes — reportalo como gap.
```

**Archivos afectados:**
- `workers/heavy/agents_b.py` — `b3_generate_hypotheses()` → `b3_generate_hypotheses_agentic()`
- `workers/heavy/llm_client.py` — nuevo `run_react_loop(agent_id, tools, max_steps)` + **capturar `reasoning_content` en `_call_llm()`**
- `backend/app/core/together_client.py` — **`chat()` debe retornar `reasoning_content` en el dict de respuesta**
- `backend/app/services/rag.py` — exponer como tool callable
- `backend/app/core/tei_client.py` — nuevo método `compare_embeddings()`
- NUEVO: `backend/app/agents/tools.py` — registro centralizado de tools
- NUEVO: `backend/app/agents/react_runner.py` — motor genérico de bucle ReAct (con preservación de `reasoning_content`)

---

## 5. Oportunidad #3 — Multi-Agent Debate (Elaboration Engine)

### 📍 Dónde: `backend/app/services/elaboration_engine.py`

**Estado actual:**
```python
def elaborate_relationship(...):
    response = llm.run_agent("conceptual_elaborator", variables={...})
    # single LLM call → single perspective
```

**Oportunidad:** Implementar un **debate multi-agente** donde:
- **Agente A (Proposer):** Propone la relación conceptual
- **Agente B (Skeptic):** Busca evidencia divergente y contraejemplos
- **Agente C (Synthesizer):** Integra ambas perspectivas en una síntesis final

```python
def elaborate_relationship_agentic(project_id, category_ids, theoretical_code_id, question):
    """
    Patrón Multi-Agent Debate:
    Proposer → Skeptic → Proposer (rebuttal) → Synthesizer → Final
    
    ⚠️ Cada llamada a run_agent debe preservar reasoning_content
    para que el modelo no pierda el contexto de su reflexión entre fases.
    """
    
    # Fase 1: Proposer genera relación (PRO — razona)
    proposal = llm.run_agent("relationship_proposer", {
        "categories": get_categories_data(category_ids),
        "theoretical_code": get_theoretical_code(theoretical_code_id),
        "question": question
    })
    
    # Fase 2: Skeptic busca contraejemplos (FLASH — más barato, no razona)
    skeptic = llm.run_agent_with_tools("relationship_skeptic", {
        "proposal": proposal,
        "tools": ["search_diverging_segments", "check_property_coverage"]
    })
    
    # Fase 3: Si hay divergencia, Proposer responde
    #        El modelo recibe su reasoning_content previo + el challenge
    if skeptic.get("diverging_evidence"):
        rebuttal = llm.run_agent("relationship_proposer", {
            **proposal,
            "challenge": skeptic["diverging_evidence"]
        })
        proposal = rebuttal
    
    # Fase 4: Synthesizer produce final
    final = llm.run_agent("relationship_synthesizer", {
        "proposal": proposal,
        "skeptic_findings": skeptic,
        "divergence_resolution": skeptic.get("resolution_strategy")
    })
    
    return final
```

**Archivos afectados:**
- `backend/app/services/elaboration_engine.py` — método `elaborate_relationship_agentic()`
- `prompts/deepseek_pro/conceptual_elaborator.md` → desdoblar en:
  - `prompts/deepseek_pro/relationship_proposer.md` (NUEVO)
  - `prompts/deepseek_pro/relationship_skeptic.md` (NUEVO)
  - `prompts/deepseek_pro/relationship_synthesizer.md` (NUEVO)

---

## 6. Oportunidad #4 — Orchestrator Agent (Pipeline Coordinator)

### 📍 Dónde: `workers/heavy/tasks.py` → `invoke_graph()` y `trigger_selective_elaboration()`

**Estado actual:**
El LangGraph actual (`core/workflow.py`) orquesta nodos con un **grafo estático**:
```
segment → extract → batch_code → map → reduce → core_concern → hypotheses → saturation → hitl → final
```

Las transiciones son **determinísticas**. El grafo no _decide_ qué hacer basado en razonamiento LLM.

**Oportunidad:** Agregar un **nodo Orchestrator** que use LLM reasoning para decidir
la ruta dinámicamente:

```python
def node_orchestrator_decide(state: AnalysisState) -> AnalysisState:
    """
    Nodo agencial que reemplaza las routing functions estáticas.
    El LLM analiza el estado y decide el próximo paso.
    """
    prompt = f"""
    [ESTADO ACTUAL DEL PIPELINE]
    - Project ID: {state['project_id']}
    - Documentos procesados: {state.get('docs_processed', 0)}
    - Códigos generados: {len(state.get('new_codes', []))}
    - Hipótesis candidatas: {len(state.get('candidate_hypotheses', []))}
    - Saturation status: {state.get('saturation_metrics', {})}
    - Errores: {state.get('errors', [])}
    - Current step: {state.get('current_step')}
    
    [NODOS DISPONIBLES]
    - segment_and_index: Segmentar nuevo documento
    - extract_entities: Extraer entidades GraphRAG
    - batch_code: Generar códigos (B2)
    - map_synthesize: Síntesis intra-documento
    - reduce_synthesize: Síntesis cross-documento
    - find_core_concern: Buscar preocupación central
    - generate_hypotheses: Generar hipótesis (B3)
    - calculate_saturation: Calcular saturación
    - theosampler_evaluate: Evaluar gaps de muestreo
    - hitl_review: Pausar para revisión humana
    - prepare_playground: Entrar al Playground
    - final_report: Finalizar
    
    [DECISIÓN]
    Basado en el estado actual, ¿cuál es el próximo nodo óptimo?
    Respondé en JSON: {{"next_node": "...", "reasoning": "..."}}
    """
    
    decision = llm.chat([{"role": "user", "content": prompt}])
    state["next_node"] = parse_json(decision)["next_node"]
    return state
```

**Archivos afectados:**
- `backend/app/core/workflow.py` — nuevo nodo `node_orchestrator_decide` + edge dinámico
- NUEVO: `backend/app/agents/orchestrator.py` — lógica de decisión agencial

---

## 7. Oportunidad #5 — Reflexive Monitor (Saturation)

### 📍 Dónde: `backend/app/services/saturation_gap_analyzer.py`

**Estado actual:**
El `SaturationGapAnalyzer` ejecuta 4 queries SQL determinísticas y produce un report.

**Oportunidad:** Agregar una **capa reflexiva** donde el LLM:
1. Recibe el reporte crudo de gaps
2. Lo **interpreta** cualitativamente
3. **Prioriza** acciones
4. **Redacta** recomendaciones en lenguaje natural para el investigador

```python
class ReflexiveSaturationMonitor:
    """
    Capa agencial sobre SaturationGapAnalyzer.
    No reemplaza el análisis SQL — lo aumenta con razonamiento LLM.
    """
    
    def analyze_with_reflection(self, project_id) -> dict:
        # 1. Análisis determinístico (igual que ahora)
        raw_report = self.analyzer.full_analysis(project_id)
        
        # 2. Reflexión LLM sobre los gaps
        reflection = self.llm.run_agent("saturation_reflector", {
            "critical_gaps": json.dumps(raw_report.critical),
            "warnings": json.dumps(raw_report.warnings),
            "saturated": json.dumps(raw_report.saturated),
            "project_context": self._get_project_context(project_id)
        })
        
        # 3. El LLM devuelve:
        # - narrative_summary: explicación en prosa
        # - prioritized_actions: top 3 acciones rankeadas
        # - saturation_confidence: 0-1 estimación de completitud
        # - blind_spots: qué podría estar faltando
        
        return {
            **raw_report,
            "reflection": reflection
        }
```

**Archivos afectados:**
- `backend/app/services/saturation_gap_analyzer.py` — nueva clase `ReflexiveSaturationMonitor`
- NUEVO: `prompts/deepseek_pro/saturation_reflector.md`
- `backend/app/api/v1/analysis.py` — nuevo endpoint `/reflection`

---

## 8. Oportunidad #6 — Tool-Augmented RAG (Query Expansion)

### 📍 Dónde: `backend/app/services/rag.py` → `search()`

**Estado actual:**
El RAG hace una sola búsqueda con la query del usuario y aplica RRF + MMR.

**Oportunidad:** Dejar que un **agente LLM** expanda y refina la query antes de buscar:

```python
def agentic_search(query, project_id, top_k):
    """
    Patrón: Query → LLM expands → Multi-query → RRF fusion → MMR
    """
    
    # 1. LLM genera variantes de la query
    expansions = llm.run_agent("query_expander", {
        "original_query": query,
        "expansion_types": ["synonym", "broader", "narrower", "related_concept"]
    })
    
    # 2. Búsqueda multi-query en paralelo
    all_results = []
    for expanded_query in expansions["queries"]:
        results = rag_service.search(expanded_query, project_id, top_k * 2)
        all_results.extend(results)
    
    # 3. RRF fusion de todos los rankings
    fused = reciprocal_rank_fusion(all_results, k=60)
    
    # 4. MMR para diversidad (ya existente)
    if len(fused) > top_k:
        fused = mmr_rerank(fused, top_k)
    
    return fused[:top_k]
```

**Archivos afectados:**
- `backend/app/services/rag.py` — método `agentic_search()`
- NUEVO: `prompts/deepseek_flash/query_expander.md`

---

## 9. Plan de Implementación Progresiva

### Fase 0 — Infraestructura (1-2 días)
```
[ ] Crear backend/app/agents/__init__.py
[ ] Crear backend/app/agents/tools.py — Tool Registry centralizado
[ ] Crear backend/app/agents/react_runner.py — Motor ReAct genérico
[ ] Crear backend/app/agents/base_agent.py — BaseAgent class
[ ] Añadir AgentLoopLog a models/ (traceabilidad de bucles)
[ ] ⚠️ CRÍTICO: Modificar together_client.py::chat() → capturar y retornar reasoning_content
[ ] ⚠️ CRÍTICO: Modificar llm_client.py::_call_llm() → capturar y retornar reasoning_content
[ ] ⚠️ CRÍTICO: BaseAgent._step() → reinyectar reasoning_content en mensajes assistant del historial
```

### Fase 1 — Self-Refinement (3-4 días, alto impacto/bajo riesgo)
```
[ ] Modificar workers/heavy/agents_b.py::b2b_generate_codes → agentic loop
[ ] Crear prompts/deepseek_pro/b2b_generate_codes_agentic.md
[ ] Añadir test: mismo input → comparar calidad single-shot vs agentic
[ ] Activar con feature flag: AGENTIC_MODE=true
```

### Fase 2 — ReAct Hypothesis (4-5 días)
```
[ ] Implementar react_runner.py con tool registry
[ ] Convertir b3_generate_hypotheses → ReAct loop
[ ] Exponer RAGService.search como tool
[ ] Exponer TEIClient.compare_embeddings como tool
[ ] Crear prompts/deepseek_pro/b3_react_system.md
```

### Fase 3 — Orchestrator Agent (3-4 días)
```
[ ] Añadir node_orchestrator_decide al LangGraph
[ ] Crear prompts/deepseek_pro/orchestrator_decider.md
[ ] Hacer edges dinámicos basados en LLM decision
[ ] Fallback determinístico si LLM no disponible
```

### Fase 4 — Debate + Reflexive (5-6 días)
```
[ ] Multi-agent debate en ElaborationEngine
[ ] ReflexiveSaturationMonitor
[ ] Query expansion agentic en RAG
[ ] Integración con frontend (mostrar "pensamiento" del agente)
```

---

## 10. Resumen de Archivos Nuevos Necesarios

```
backend/app/agents/
├── __init__.py                    # Package init
├── base_agent.py                  # BaseAgent: template method para bucles
├── react_runner.py                # Motor ReAct genérico (Thought→Action→Observe)
├── tool_registry.py               # Registro centralizado de tools
├── tools/
│   ├── __init__.py
│   ├── search_tools.py            # search_segments, get_code_details
│   ├── db_tools.py                # get_hypotheses, get_codes, check_saturation
│   └── compare_tools.py           # compare_embeddings, find_similar
├── orchestrator.py                # Orchestrator Agent para LangGraph
├── self_refiner.py                # SelfRefinementLoop genérico
└── prompts/
    ├── react_system.md            # System prompt universal para ReAct
    ├── self_critic_system.md      # System prompt para self-refinement
    └── orchestrator_system.md     # System prompt para orchestrator
```

**Archivos existentes a modificar:**

| Archivo | Cambio |
|---------|--------|
| `workers/heavy/agents_b.py` | `b2b_generate_codes()` y `b3_generate_hypotheses()` → versiones agentic con preservación de `reasoning_content` |
| `workers/heavy/llm_client.py` | Nuevo método `run_agentic_loop()` + **`_call_llm()` captura `reasoning_content`** |
| `workers/heavy/tasks.py` | `trigger_selective_elaboration()` → orchestrator-aware |
| `workers/fast/tasks.py` | `extract_graph_entities()` → opcionalmente agentic |
| `backend/app/core/workflow.py` | Nuevo nodo `orchestrator_decide` |
| `backend/app/services/elaboration_engine.py` | `elaborate_relationship()` → multi-agent con preservación de razonamiento |
| `backend/app/services/saturation_gap_analyzer.py` | Nueva clase `ReflexiveSaturationMonitor` |
| `backend/app/services/rag.py` | `agentic_search()` con query expansion |
| `backend/app/core/together_client.py` | **`chat()` retorna `reasoning_content` en el dict** + método `chat_multi_turn()` |
| `backend/app/core/llm_config.py` | Registrar nuevos `prompt_id` en `PROMPT_TIER_MAP` |

---

## 11. Métricas de Éxito

| Métrica | Single-shot actual | Target agentic | Cómo medir |
|---------|-------------------|----------------|------------|
| Códigos redundantes (B2) | ~15-20% | <5% | Jaccard similarity entre códigos |
| Hipótesis sin evidencia (B3) | ~25% | <10% | Verificación automática contra segmentos |
| Iteraciones hasta convergencia | 1 (no itera) | 2-3 | Log del bucle |
| Tasa de ghost-blobs absorbed | ~30% | >60% | ElaborationMemo.type='ghost_absorbed' |
| Tiempo hasta playground-ready | variable | -20% (menos retrabajo) | PipelineStatus.stages |

---

## 12. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| **Cost explosion** (muchos tokens) | Alta | Feature flags, límite de iteraciones, usar FLASH para critic |
| **Loop infinito** | Media | `max_iterations` + timeout por agente |
| **Degradación de calidad** | Baja | Evaluación A/B con ground truth de proyectos reales |
| **Latencia percibida** | Alta | Mostrar "thinking..." en frontend, streaming SSE del pensamiento |
| **Tool hallucination** (inventa tools) | Media | Strict system prompt + validación de tool names |
| **Pérdida de razonamiento entre turnos** | **Crítica** | **Capturar `reasoning_content` en `together_client.py` y `llm_client.py`, reinyectarlo en cada `assistant` message del historial. Sin esto, DeepSeek V4 Pro divaga, repite acciones y alucina datos al perder el contexto de su propia reflexión.** |

---

## Conclusión

El sistema GT está **notablemente bien posicionado** para adoptar patrones agenciales. Ya tiene:

1. **LangGraph** como orquestador con checkpoints
2. **Proposer/Critic pairs** que son el 50% de un self-refinement loop
3. **Servicios modulares** (RAG, TEI, DB) fácilmente exponibles como tools
4. **Separación PRO/FLASH** que permite usar modelo barato para critic y caro para generate
5. **DeepSeek V4 Pro como modelo PRO** — modelo de razonamiento nativo (RLVR) cuyo `reasoning_content` debe preservarse entre turnos del bucle agencial

La transformación recomendada es **progresiva y con feature flags**, empezando por el self-refinement loop en B2 (máximo impacto, mínimo riesgo) y escalando hacia el orchestrator agent y el multi-agent debate.

> ⚠️ **Precondición crítica:** Antes de implementar cualquier bucle agencial, es obligatorio
> corregir `together_client.py` y `llm_client.py` para capturar `reasoning_content` de DeepSeek
> V4 Pro y reinyectarlo en el historial de mensajes. Sin esto, el agente se degrada con cada
> iteración: divaga, repite acciones, y alucina datos. Ver `Analisis_CoT_Gaps.md` para detalle.
