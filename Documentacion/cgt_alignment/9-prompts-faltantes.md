# 9 Prompts Faltantes — Diseño Unificado

> **Fecha:** 2026-06-17  
> **Fuentes:** `AGENTES.md`, `kb.md`, `CHECKLIST_CGT_REFACTOR.md`, `secuencia_cgt.mermaid`  
> **Propósito:** Diseño canónico de los 9 prompts que no existen en `deepseek_pro/` o `deepseek_flash/`. Este documento es el plano de construcción — los archivos `.md` se crearán en una fase posterior.

---

## Índice

1. [Database A/B (4 prompts)](#1-database-ab)
2. [Core Pattern + Verifier (2 prompts)](#2-core-pattern--verifier)
3. [Gap Feeler + Memo Tagger + Final Report (3 prompts)](#3-gap-feeler--memo-tagger--final-report)
4. [Resumen de cambios en tasks.py y nuevos módulos](#4-cambios-en-código)

---

## 1. Database A/B

### 1.1 `database_a_proposer.md` (PRO)

**Propósito:** Transformar categorías saturadas en NODOS teóricos formales (Database A).

**Inputs esperados:** `{saturated_categories}`, `{core_category}`, `{object_of_study}`, `{research_question}`

**Diseño:**
- 3 fases: A (identificar core node) → B (clasificar resto: condition | consequence | strategy | dimension) → C (compilar definiciones desde propiedades acumuladas)
- `entity_type` canónico: `core_category | condition | consequence | strategy | dimension`
- PATTERN TYPE GUIDANCE parametrizado por `{object_of_study}`
- `grounding_incidents` para trazabilidad (kb.md §14)
- Exactamente 1 nodo con `is_core = true`

**Output:** `{nodes[{label, entity_type, definition, source_category_id, is_core, grounding_incidents, properties_inherited}], core_node_label, model_summary}`

---

### 1.2 `database_a_critic.md` (PRO)

**Propósito:** Evaluar cada nodo propuesto con 5 criterios.

**Inputs esperados:** `{nodes}`, `{saturated_categories}`, `{object_of_study}`, `{core_category}`

**Diseño:**
- Per-node: SAT | MOD | FORCED
- 5 criterios: entity_type correctness, definition grounding, abstraction level, incident sufficiency, core identification
- System-level checks: missing categories, duplicate nodes, is_core_count = 1, entity_type distribution
- PATTERN TYPE GUIDANCE adapta evaluación al tipo de patrón

**Output:** `{node_evaluations[{verdict, rationale, criteria_assessment, suggested_fix}], system_issues, overall_verdict}`

---

### 1.3 `database_b_proposer.md` (PRO)

**Propósito:** Proponer EDGES formales entre nodos (Database B) usando las familias de códigos teóricos de Glaser.

**Inputs esperados:** `{nodes}`, `{conceptual_relationships}`, `{hypotheses}`, `{object_of_study}`, `{research_question}`, `{core_concern}`

**Diseño:**
- 7 tipos canónicos: `PROCESSES | LEADS_TO | IS_A_STRATEGY_FOR | IS_A_CONSEQUENCE_OF | IS_A_CONDITION_FOR | VARIES_WITH | CO_OCCURS_WITH`
- `PROCESSES` es OBLIGATORIO (core category → cómo procesa el `{object_of_study}`)
- Orden de generación: 1º PROCESSES → 2º estrategias → 3º condiciones → 4º consecuencias → 5º edges secundarios
- Cada edge requiere `evidence` (hipótesis confirmada o relación conceptual elaborada)
- `missing_evidence_notes` para relaciones plausibles sin evidencia suficiente (honestidad metodológica)

**Output:** `{edges[{source, target, relationship_type, rationale, evidence, direction, strength}], processes_edge_present, edge_summary, missing_evidence_notes}`

---

### 1.4 `database_b_critic.md` (PRO)

**Propósito:** Auditar edges propuestos: verificar tipo, evidencia, consistencia lógica y coherencia global.

**Inputs esperados:** `{edges}`, `{nodes}`, `{hypotheses}`, `{object_of_study}`, `{core_concern}`

**Diseño:**
- Per-edge: SAT | MOD | FORCED con 4 criterios
- Detección de CONTRADICCIONES: circular causation, mutual typing, type clash
- Detección de MISSING EDGES: nodos que lógicamente deberían tener edges pero no los tienen
- Detección de ORPHAN NODES: nodos sin edges (¿legítimamente aislados?)
- Verifica que `PROCESSES` edge existe y es correcto

**Output:** `{edge_evaluations, system_issues{contradictions, missing_edges, orphan_nodes}, overall_verdict}`

---

## 2. Core Pattern + Verifier

### 2.1 `core_pattern_extractor.md` (PRO)

**Propósito:** Sintetizar UN patrón candidato (gerundio) a partir de TODOS los incidentes de UN documento. Per-documento, fase descubrimiento.

**Inputs esperados:** `{incidents_text}`, `{document_name}`, `{object_of_study}`, `{object_of_study_instruction}`, `{operational_question}`

**Diseño:**
- AISLADO: solo ve incidentes del documento actual. No conoce otros documentos ni categorías existentes.
- PLURAL → SINGULAR: sintetiza muchos incidentes en un solo patrón candidato
- `{object_of_study_instruction}` adapta el lente (concern→busca preocupación, emotion→busca patrón emocional, etc.)
- Evidencia: 2-5 citas textuales de incidentes distintos
- Reemplaza el system prompt hardcodeado en español de `pattern_extractor.py`

**Output:** `{core_pattern (gerund), description, evidence_quotes[], key_incident_ids[], confidence (HIGH|MEDIUM|LOW), no_clear_pattern, alternative_patterns[]}`

---

### 2.2 `core_pattern_verifier.md` (PRO)

**Propósito:** Comparar los últimos 3 patrones individuales y evaluar si convergen hacia un patrón compartido. Se ejecuta cada 3 documentos. Dispara 🛑 HITL gate.

**Inputs esperados:** `{patterns}` (últimos 3), `{population_context}`, `{object_of_study}`, `{PATTERN_TYPE_GUIDANCE}`, `{operational_question}`

**Diseño:**
- 4 preguntas de evaluación: Q1 surface similarity → Q2 structural convergence → Q3 population coherence → Q4 directionality
- 3 recomendaciones: `CONTINUE_COLLECTING | READY_FOR_CROSS_DOC | NEEDS_DIFFERENT_POPULATION`
- Distingue divergencia superficial (mismo fenómeno, distintas palabras) vs contextual (mismo fenómeno, distinto rol) vs fundamental (fenómenos distintos)
- `suggested_shared_pattern`: nombre tentativo del patrón compartido (si converge)
- `population_concerns`: si la población asumida no encaja con los patrones emergentes

**Output:** `{convergence_assessment, converging[{element, supporting_patterns, strength}], diverging[{element, divergence_type, explanation}], recommendation, suggested_shared_pattern, population_concerns}`

**Nuevo HITL gate:** `GATE_PATTERN_OF_INTEREST = "pattern_of_interest"` en `transitions.py`

**Nuevo módulo:** `workers/heavy/pattern_verifier.py` con `verify_core_pattern(proyecto_id)`

---

## 3. Gap Feeler + Memo Tagger + Final Report

### 3.1 `gap_feeler.md` (FLASH)

**Propósito:** Monitorear borradores en background durante la redacción. Detecta huecos teóricos sin interrumpir al writer.

**Inputs esperados:** `{draft}`, `{project_id}`, `{object_of_study}`, `{core_concern}`

**Diseño:**
- 5 tipos de gap: `MISSING_EVIDENCE | UNDERDEVELOPED_PROPERTY | DISCONNECTED_CATEGORY | CONCEPTUAL_LEAP | ORPHAN_CLAIM`
- 3 severidades: HIGH (bloquea publicación) | MEDIUM (necesita expansión) | LOW (cosmético)
- No bloquea — acumula señales para revisión del investigador
- Context-aware: gaps cerca del core concern → mayor severidad
- Reemplaza el system prompt hardcodeado en `writer.py::feel_gaps()`

**Output:** `{gaps[{type, description, severity, location}], total_gaps, summary}`

---

### 3.2 `memo_theoretical_tagger.md` (FLASH)

**Propósito:** Clasificar memos por afinidad a las 12 familias canónicas de códigos teóricos (Glaser). Ayuda al sorting pre-agrupando memos de la misma familia.

**Inputs esperados:** `{memo_content}`, `{object_of_study}`

**Diseño:**
- 12 familias canónicas (kb.md §8): Causes, Consequences, Conditions, Process, Degree, Dimension, Type, Strategy, Structural, Functional, Interaction, Identity
- ⚠️ CORRECCIÓN CRÍTICA: el archivo existente `deepseek_flash/memo_theoretical_tagger.md` usa una lista INCORRECTA de familias (zlegacy-era). Debe ser SOBRESCRITO.
- Scoring 0-1 por familia. Solo familias con score ≥ 0.3 en output.
- `object_of_study` contextualiza la clasificación (un memo sobre "percibir amenazas" puntúa distinto en Structural para un estudio de concern vs discourse)
- `primary_family` + `secondary_family` para sorting

**Output:** `{family_affinities[{family, score, rationale}], primary_family, secondary_family}`

**Nuevo módulo:** `workers/heavy/theoretical.py` con `tag_memo_theoretically(memo_id, proyecto_id)`

---

### 3.3 `final_report.md` (PRO)

**Propósito:** Nodo terminal del pipeline. Genera el reporte teórico completo integrando todas las fases del estudio.

**Inputs esperados:** `{object_of_study}`, `{research_question}`, `{core_concern}`, `{core_category}`, `{nodes}`, `{edges}`, `{hypotheses}`, `{population_description}`, `{literature_dialogue}`, `{applicability_guidelines}`

**Diseño:**
- 8 secciones: Abstract (200w) → Core Pattern → Core Category → Theoretical Model → Population Dimensions → Literature Dialogue → Applicability → Research Trajectory
- PROPOSER pattern: propone reporte completo. El investigador revisa vía HITL. No necesita critic separado (el investigador ES el critic).
- Hereda reglas de `natural_writer`: presente conceptual, conceptos como sujetos, gerundios para procesos, abstracción progresiva
- Adapta headings al `object_of_study` (si es "emotion" → "Core Emotion", no "Core Concern")
- Título: `"{Core Pattern} — A Classic Grounded Theory of {Generalized Population}"`
- Reemplaza el placeholder `node_final_report()` en `workflow.py`

**Output:** `{report: {title, abstract, core_pattern, core_category, theoretical_model, population_dimensions, literature_dialogue, applicability, research_trajectory}}`

**Nuevo módulo:** `workers/heavy/reporter.py` con `generate_final_report(proyecto_id)`

---

## 4. Cambios en código

### 4.1 `workers/heavy/tasks.py` — nuevas tareas Celery

```python
@app.task(name="verify_core_pattern")
def task_verify_core_pattern(proyecto_id: str) -> dict:
    """F2.5: Verifica convergencia patrones individuales (PRO). Cada 3 docs."""

@app.task(name="memo_theoretical_tagger")
def task_memo_theoretical_tagger(memo_id: str, proyecto_id: str) -> dict:
    """F6b: Clasifica memo en 12 familias teóricas (FLASH)."""

@app.task(name="final_report")
def task_final_report(proyecto_id: str) -> dict:
    """F6e: Genera reporte teórico final (PRO, nodo terminal)."""
```

### 4.2 `workers/heavy/tasks.py` — fixes en pipeline existentes

| Función | Cambio |
|---------|--------|
| `task_database_a_pipeline()` | Añadir fetch de `object_of_study`, `research_question`, `core_category` (real, no placeholder). Pasar a proposer y critic. |
| `task_database_b_pipeline()` | Añadir fetch de `object_of_study`, `research_question`, `core_concern`. Pasar a proposer y critic. |
| `process_document_agents_a()` | Tras `extract_core_pattern`, si `doc_count >= 3 AND doc_count % 3 == 0` → disparar `verify_core_pattern` |
| `task_core_saturation_loop()` | ✅ Ya arreglado (variable mismatch) |

### 4.3 Módulos nuevos

| Archivo | Función | Propósito |
|---------|---------|-----------|
| `workers/heavy/pattern_verifier.py` | `verify_core_pattern()` | Convergencia de patrones cada 3 docs |
| `workers/heavy/theoretical.py` | `tag_memo_theoretically()` | Clasificación de memos en 12 familias |
| `workers/heavy/reporter.py` | `generate_final_report()` | Síntesis terminal del estudio |

### 4.4 Módulos a modificar

| Archivo | Cambio |
|---------|--------|
| `workers/heavy/pattern_extractor.py` | Reemplazar system prompt hardcodeado por `llm.run_agent("core_pattern_extractor", ...)`. Eliminar `_PATTERN_SCHEMA`. |
| `workers/heavy/writer.py::feel_gaps()` | Reemplazar system prompt hardcodeado por `llm.run_agent("gap_feeler", ...)`. Añadir fetch de `object_of_study` y `core_concern`. |
| `backend/app/core/workflow.py::node_final_report()` | Reemplazar placeholder por dispatch a `final_report` Celery task |
| `backend/app/agents/transitions.py` | Añadir `GATE_PATTERN_OF_INTEREST = "pattern_of_interest"` |
| `backend/app/prompts/schemas.py` | Añadir schemas para `gap_feeler`, `memo_theoretical_tagger`, `final_report` |

### 4.5 Sobrescribir archivo existente

| Archivo | Razón |
|---------|-------|
| `deepseek_flash/memo_theoretical_tagger.md` | Usa lista de familias INCORRECTA (zlegacy). Debe usar las 12 canónicas de kb.md §8. |

---

## Resumen visual

```
┌──────────────────────────────────────────────────────────────┐
│                   9 PROMPTS FALTANTES                         │
├────────┬─────────────────────────────────────────────────────┤
│   DB   │ database_a_proposer  (PRO)  → database_a_critic     │
│        │ database_b_proposer  (PRO)  → database_b_critic     │
├────────┼─────────────────────────────────────────────────────┤
│  A4    │ core_pattern_extractor (PRO) → core_pattern_verifier│
│        │                              🛑 HITL gate            │
├────────┼─────────────────────────────────────────────────────┤
│  6a    │ gap_feeler (FLASH) — background monitoring          │
│  6b    │ memo_theoretical_tagger (FLASH) — 12 families       │
│   END  │ final_report (PRO) — nodo terminal                  │
└────────┴─────────────────────────────────────────────────────┘
```

---

> **Patrón de diseño:** Proposer → Critic → HITL gate (para database_a, database_b, core_pattern_verifier, final_report)  
> **Patrón de diseño:** Single-pass classification (para gap_feeler, memo_theoretical_tagger)  
> **Idioma:** System prompt en inglés 🇬🇧, output en idioma del usuario 🇪🇸  
> **Parametrización:** Todos reciben `{object_of_study}` + contexto de investigación relevante
