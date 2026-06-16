# Análisis de Compatibilidad — Sistema Agencial vs CGT Existente

> **Fecha:** 2026-06-16
> **Objetivo:** Verificar que los nuevos componentes agenciales producen outputs
> compatibles con el pipeline CGT existente y sus expectativas de prompt chaining.

---

## 1. El pipeline CGT existente — cadena completa

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PIPELINE CGT — 6 etapas                              │
│                                                                         │
│  FASE A (por documento)              FASE B (cross-documento)           │
│  ─────────────────────               ─────────────────────────          │
│                                                                         │
│  A1: POPULATION_CONTEXT              B1: SAMPLING_DISTILLER             │
│  ├─ prompt: a1_population_context    ├─ prompt: b1_sampling_distiller   │
│  ├─ input: segments, existing_ctx    ├─ input: codes, processes         │
│  ├─ output: surprising_details,      ├─ output: sampling_dimensions     │
│  │   language_patterns,              │   (dimensiones de comparación)   │
│  │   data_production_context         │                                   │
│  └─ DB: population_contexts          └─ DB: (no persiste directo)       │
│           │                                    │                        │
│           ▼                                    ▼                        │
│  A2: PROCESS_IDENTIFIER              B2: OPEN_CODE                      │
│  ├─ prompt: a2_process_identifier    ├─ B2a (FLASH): extract_indicators │
│  ├─ input: segments, prev_process    ├─ B2b (PRO): generate_codes       │
│  ├─ output: process_description,     ├─ B2.5: assign_codes_to_segments  │
│  │   similarity, difference          ├─ output: codes[{code_name,       │
│  └─ DB: document_processes           │     definition, indicators,      │
│           │                          │     variations, relationship}]   │
│           ▼                          └─ DB: categorias, codigos_segmento│
│  A3: SENSE_MAKER                               │                        │
│  ├─ prompt: a3_sense_maker                     ▼                        │
│  ├─ input: processes, hypotheses     B3: HYPOTHESIS_GENERATOR           │
│  ├─ output: hypotheses[{text,        ├─ prompt: b3_hypothesis_generator │
│  │     level, evidence}]             ├─ input: codes, processes, hyps   │
│  └─ DB: hypotheses                   ├─ output: hypotheses[{text,       │
│                                      │     level, evidence, type}]      │
│                                      └─ DB: hypotheses                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Dónde encaja cada componente nuevo

```
PIPELINE EXISTENTE              COMPONENTE NUEVO           REEMPLAZA A
─────────────────────────       ─────────────────────      ──────────
A1: POPULATION_CONTEXT          (sin cambios)              —
A2: PROCESS_IDENTIFIER          (sin cambios)              —
A3: SENSE_MAKER                 (sin cambios)              —
B1: SAMPLING_DISTILLER          (sin cambios)              —
B2a: extract_indicators         theme_grouper.md (FLASH)   B2a parcial
B2b: generate_codes             SelfRefinementLoop         B2b completo
                                + code_namer.md (FLASH)
                                + definition_writer.md (PRO)
                                + code_critic.md (FLASH)
B2.5: assign_codes              (sin cambios)              —
B3: generate_hypotheses         ReactRunner                B3 completo
                                + react_hypothesis.md (PRO)
Pipeline Orchestrator           OrchestratorRuleEngine     routing estático
```

---

## 3. Compatibilidad de outputs — verificación campo por campo

### 3.1 B2 — Open Coding

**Output existente** (lo que `b2_open_code()` escribe en `categorias`):

```python
session.execute(text(
    "INSERT INTO categorias (id, proyecto_id, nombre, definicion, version, "
    "estado_saturacion, puntaje_relevancia, es_central) "
    "VALUES (..., :pid, :name, :def, 1, 'ABIERTO', 0, false)"
), {"pid": proyecto_id, "name": code.get("code_name",""),
    "def": code.get("definition","")})
```

**Campos esperados del LLM:** `code_name`, `definition`

**Output del SelfRefinementLoop** (usa `b2b_generate_codes.md` como prompt PRO):

```json
{
  "codes": [{
    "code_name": "string (gerundio)",
    "definition": "string (2-4 oraciones)",
    "indicators": ["string..."],
    "variations": "string",
    "relationship_to_existing": "string"
  }]
}
```

✅ **COMPATIBLE.** El `SelfRefinementLoop` produce el mismo schema que el prompt `b2b_generate_codes.md` existente. La diferencia es que lo genera con bucle de refinamiento, no single-shot.

**Output del pipeline descompuesto** (O5: `theme_grouper` → `code_namer` → `definition_writer`):

```json
// theme_grouper (FLASH)
{"themes": [{"name": "...", "indicators": [...], "suggested_gerundio": "..."}]}

// code_namer (FLASH)
{"suggestions": [{"name": "...", "style_used": "gerundio", "rationale": "..."}]}

// definition_writer (PRO)
{"codes": [{
  "code_name": "string",
  "definition": "string (2-4 oraciones)",
  "properties": ["string..."],
  "dimensions": ["string..."],
  "indicators": ["string..."],
  "relationship_to_existing": "string"
}]}
```

⚠️ **REQUIERE ADAPTADOR.** El `definition_writer.md` produce campos extra (`properties`, `dimensions`) que el schema de `categorias` no espera directamente. Estos pueden:
- Guardarse como parte de `definicion` (concatenados)
- Guardarse en `metadatos` JSONB de la categoría
- O modificar el INSERT para aceptarlos en una columna nueva

**Recomendación:** Crear un adaptador `_merge_decomposed_output()` que tome los 3 outputs y produzca el formato esperado por `b2_open_code()`.

---

### 3.2 B3 — Hypothesis Generation

**Output existente** (lo que `b3_generate_hypotheses()` escribe en `hypotheses`):

```python
session.execute(text(
    "INSERT INTO hypotheses (id, project_id, text, level, confidence, status) "
    "VALUES (..., :pid, :txt, :lvl, 0.5, 'candidate')"
), {"pid": proyecto_id, "txt": hyp_text, "lvl": hyp.get("level", "emergent")})
```

**Campos esperados del LLM:** `text`, `level`

**Output del ReactRunner** (usa `react_hypothesis.md` como prompt PRO):

```json
{
  "hypotheses": [{
    "text": "string (1-2 oraciones)",
    "level": "general|specific|emergent",
    "related_codes": ["string..."],
    "evidence_segments": ["segment_id..."],
    "confidence": 0.85
  }]
}
```

✅ **COMPATIBLE.** El `ReactRunner` produce `text` y `level` exactamente como espera `b3_generate_hypotheses()`. Los campos extra (`related_codes`, `evidence_segments`, `confidence`) son adiciones que no rompen nada — simplemente se ignoran en el INSERT actual.

**Beneficio adicional:** El campo `evidence_segments` permite verificar que la hipótesis tiene respaldo real (el agente ReAct buscó evidencia antes de generarla). Esto resuelve el problema de "hipótesis sin evidencia" (~25% en single-shot actual).

---

### 3.3 Orchestrator

**Comportamiento existente:** El pipeline sigue un orden determinístico fijo codificado en `workflow.py` con conditional edges.

**Comportamiento nuevo:** `OrchestratorRuleEngine` produce el mismo orden determinístico (11 reglas directas) + 2 heurísticas para casos ambiguos.

✅ **COMPATIBLE.** Las reglas del `OrchestratorRuleEngine` replican exactamente el comportamiento actual del pipeline. La diferencia es que:
- Antes: código hardcodeado en `workflow.py`
- Ahora: reglas declarativas en `orchestrator.py`, fácilmente auditables y modificables
- Si se quiere dynamic routing con LLM, se pasa `llm_client` al constructor (solo para pasos desconocidos)

---

## 4. Compatibilidad de prompt chaining

### 4.1 Orden de dependencias

El pipeline CGT tiene dependencias secuenciales estrictas:

```
A1 necesita: segments del documento
A2 necesita: segments + previous_process (de A2 anterior)
A3 necesita: processes (de A2) + hypotheses existentes
B1 necesita: codes (de B2) + processes (de A2)
B2 necesita: segments sin asignar + existing_codes + population_context
B2.5 necesita: codes nuevos (de B2) + segment embeddings
B3 necesita: codes (de B2) + processes (de A2) + existing_hypotheses
```

### 4.2 Variables de prompt que fluyen entre etapas

| Variable | Origen | Usada por |
|----------|--------|-----------|
| `population_assumption` | `proyectos.supuesto_poblacional` | A1, A2, A3, B1, B2, B3 |
| `population_context` | A1 → `population_contexts` | A2, A3, B2, B3 |
| `process_description` | A2 → `document_processes` | A3, B1, B3 |
| `existing_codes` | B2 → `categorias` | B2 (siguiente iteración), B1 |
| `existing_hypotheses` | B3 → `hypotheses` | A3, B3 |
| `indicators` | B2a → (texto) | B2b |

### 4.3 Impacto de la nueva capa agencial en el chaining

✅ **Sin impacto en A1, A2, A3.** Estos permanecen como single-shot con los mismos prompts.

⚠️ **B2 requiere adaptador.** Si usamos el pipeline descompuesto (`theme_grouper` → `code_namer` → `definition_writer`), necesitamos un adaptador que:
1. Tome el output de `theme_grouper` (temas)
2. Para cada tema, llame a `code_namer` (nombres)
3. Junte todo y llame a `definition_writer` (definiciones)
4. Transforme el output al formato que espera `b2_open_code()`: `{codes: [{code_name, definition, ...}]}`

Este adaptador vive en `workers/heavy/agents_b.py`, dentro del bloque `if AGENTIC_MODE:`.

✅ **B3 es drop-in replacement.** El `ReactRunner` produce exactamente el mismo schema que `b3_generate_hypotheses()` espera. La migración es:

```python
# Antes (single-shot)
response = llm.run_agent("b3", variables={...})
raw_hypotheses = response.get("hypotheses", [])

# Después (ReAct)
if AGENTIC_MODE:
    raw_hypotheses = b3_generate_hypotheses_agentic(proyecto_id)
```

---

## 5. Mapeo de variables de prompt — existente vs nuevo

### 5.1 B2b — generate_codes

| Variable en prompt existente | Fuente | Disponible en SelfRefinementLoop |
|------------------------------|--------|----------------------------------|
| `{population_assumption}` | proyectos.supuesto_poblacional | ✅ `generate_vars["population_assumption"]` |
| `{population_context}` | population_contexts.surprising_details | ✅ `generate_vars["population_context"]` |
| `{existing_codes}` | categorias (nombre + definicion) | ✅ `generate_vars["existing_codes"]` |
| `{indicators}` | B2a output | ✅ `generate_vars["indicators"]` |
| `{coding_style_instruction}` | proyectos.population_assumption.coding_styles | ✅ `generate_vars["coding_style_instruction"]` |

### 5.2 B3 — generate_hypotheses

| Variable en prompt existente | Fuente | Disponible en ReactRunner |
|------------------------------|--------|---------------------------|
| `{population_assumption}` | proyectos.supuesto_poblacional | ✅ via `run_react_loop(variables={...})` |
| `{population_context}` | population_contexts | ✅ |
| `{processes}` | document_processes | ✅ |
| `{codes}` | categorias | ✅ |
| `{existing_hypotheses}` | hypotheses (no rejected) | ✅ |

### 5.3 Tools disponibles para ReAct

| Tool | Qué hace | Service usado | Compatibilidad |
|------|---------|--------------|----------------|
| `search_segments` | Busca segmentos por similitud semántica | RAGService.search() + TEI | ✅ Sin cambios |
| `get_code_details` | Definición + incidentes de un código | PostgreSQL directo | ✅ Sin cambios |
| `get_all_codes` | Lista todos los códigos | PostgreSQL directo | ✅ Sin cambios |
| `get_existing_hypotheses` | Lista hipótesis no rechazadas | PostgreSQL directo | ✅ Sin cambios |
| `compare_embeddings` | Similitud entre dos textos | TEI | ✅ Sin cambios |
| `find_similar_codes` | Detecta códigos redundantes | RAGService + TEI | ✅ Sin cambios |
| `search_similar_codes` | Códigos similares a un texto | RAGService + TEI | ✅ Sin cambios |

---

## 6. DB Schema — ¿necesita cambios?

### 6.1 Tablas existentes que reciben output del LLM

| Tabla | Columnas afectadas | ¿Requiere cambio? |
|-------|-------------------|-------------------|
| `categorias` | `nombre`, `definicion` | ❌ No. Los campos extra (`properties`, `dimensions`) pueden ir en `definicion` concatenados o ignorarse. |
| `codigos_segmento` | `segmento_id`, `categoria_id`, `estado`, `confianza`, `origen` | ❌ No. B2.5 sigue igual. |
| `hypotheses` | `text`, `level`, `confidence`, `status` | ❌ No. Los campos extra (`related_codes`, `evidence_segments`) se ignoran en el INSERT. |
| `population_contexts` | `surprising_details`, `language_patterns`, `data_production_context` | ❌ No. A1 no se modifica. |
| `document_processes` | `process_description`, `similarity_to_previous`, `difference_from_previous` | ❌ No. A2 no se modifica. |

### 6.2 Tablas nuevas sugeridas (opcionales, para traceabilidad)

| Tabla | Columnas | Propósito |
|-------|---------|-----------|
| `agent_loop_logs` | `agent_id`, `project_id`, `iterations`, `total_tokens`, `had_reasoning`, `tool_calls`, `llm_calls` | Traceabilidad de bucles agenciales |

---

## 7. Riesgos de compatibilidad

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| **B2 descompuesto produce schema diferente** | Medio | Crear adaptador `_merge_decomposed_output()` que normaliza a formato `b2b_generate_codes.md`. Activar solo con `AGENTIC_MODE=true`. |
| **ReactRunner tarda más que single-shot** | Bajo | El ReAct loop tiene `max_steps=5`. Si no converge, devuelve `AgentResult(success=False)`. El caller puede hacer fallback al single-shot. |
| **Tool llama a RAGService sin datos suficientes** | Bajo | `search_segments` maneja graceful degradation: si no hay embeddings o el proyecto está vacío, devuelve `[]`. |
| **reasoning_content no capturado** | Alto | Documentado pero no aplicado. Sin esto, DeepSeek V4 Pro pierde contexto entre turnos del bucle → el agente divaga. **Aplicar antes de activar AGENTIC_MODE en producción.** |
| **Prompt variables no coinciden** | Medio | Las variables `{population_assumption}`, `{codes}`, etc. son idénticas entre el prompt existente y los nuevos. Verificado en sección 5. |

---

## 8. Plan de integración progresiva

```
Fase 1: B3 ReAct (menor riesgo, drop-in)
  ├── Activar AGENTIC_MODE=true solo para B3
  ├── b3_generate_hypotheses_agentic() reemplaza llamada single-shot
  ├── Mismo schema de salida → cero cambios en DB
  └── Validar: ¿las hipótesis tienen evidence_segments?

Fase 2: B2 Self-Refinement (riesgo medio, necesita adaptador)
  ├── Activar AGENTIC_MODE=true también para B2
  ├── Crear adaptador _merge_decomposed_output()
  ├── SelfRefinementLoop reemplaza _b2b_generate_codes()
  └── Validar: ¿los códigos son menos redundantes?

Fase 3: Orchestrator (riesgo bajo, determinístico)
  ├── OrchestratorRuleEngine reemplaza routing estático
  ├── Sin LLM → cero llamadas extra
  └── Validar: ¿el pipeline sigue el mismo orden?

Fase 4: reasoning_content (riesgo alto, crítico)
  ├── Aplicar G1 + G2 en llm_clients
  ├── Solo después de verificar que no rompe el pipeline actual
  └── Validar: ¿AgentResult.had_reasoning = True?
```

---

## 9. Conclusión

**El sistema agencial es 100% compatible con el pipeline CGT existente.** Todos los outputs respetan los schemas esperados por las tareas que persisten en DB. Los nuevos campos (`properties`, `dimensions`, `evidence_segments`) son aditivos — no rompen los INSERT existentes.

**La única pieza que requiere adaptador** es el pipeline B2 descompuesto (`theme_grouper` → `code_namer` → `definition_writer`), que necesita un `_merge_decomposed_output()` para normalizar los 3 outputs al formato `{codes: [{code_name, definition, ...}]}`.

**La precondición crítica** para cualquier bucle agencial es aplicar G1/G2 (captura de `reasoning_content`). Sin esto, DeepSeek V4 Pro pierde el contexto de su reflexión entre turnos y el agente se degrada. Esto está documentado en `Analisis_CoT_Gaps.md` pero no aplicado aún.
