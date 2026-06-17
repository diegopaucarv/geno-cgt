# 4 Patrones de Desarrollo — Alineación CGT ↔ Sistema

> **Base para buenas prácticas futuras. Mapea cada fase de la metodología CGT contra los patrones de desarrollo del sistema.**
>
> Fundamentado en: `kb.md` (knowledge base CGT) | `Patron_Desarrollo_Maestro.md` | `auditoria_coherencia.md`

---

## Los 4 Patrones

```
┌─────────────────────────────────────────────────────────────────┐
│  PATRÓN 1: TRANSICIONES     → R1 + R5                          │
│  Toda etapa llama transition() al terminar.                     │
│  Optimistic lock: WHERE estado = current.                       │
│                                                                  │
│  PATRÓN 2: TRAZABILIDAD     → R2                               │
│  Toda tarea despachada crea PipelineTask.                       │
│  Stop/Cancel/Restart/Resume funciona para toda tarea.           │
│                                                                  │
│  PATRÓN 3: RESILIENCIA      → R3 + R4                          │
│  Toda tarea es AbortableTask + SIGTERM handler.                 │
│  Tareas multi-step tienen checkpoints (resumibles).             │
│                                                                  │
│  PATRÓN 4: AGENCIAL         → Plan→Execute→Critique→Converge   │
│  Tareas generativas usan SelfRefinement o Proposer/Critic.      │
│  FLASH para critic/evaluación, PRO para generación/síntesis.    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Mapeo Fase por Fase

### FASE 0: Configuración del Proyecto

| Agente (kb.md) | ¿Implementado? | ¿Patrón aplica? | Beneficio |
|----------------|---------------|-----------------|-----------|
| `population_generalizer` | ❌ | P4 (PRO, single-shot) | Bajo — es una sola llamada al crear proyecto |

**Estado:** No implementado. El campo `population_assumption` existe en `proyectos` pero no hay agente que lo procese.

**Pendiente:** Crear endpoint/tarea que invoque `population_generalizer` al crear proyecto.

---

### FASE 1: Open Coding — Por Documento

| Agente (kb.md) | ¿Implementado? | ¿Patrón aplica? | Beneficio |
|----------------|---------------|-----------------|-----------|
| `glaser_data_classifier` | ⚠️ Parcial (`algorithmic_checks.preclassify_glaser`) | P4 (FLASH) | Medio — clasificación pre-LLM reduce costo |
| `incident_extractor` | ⚠️ Como `b2a_extract_indicators` en FASE B | **P2 + P4**: cada incidente → PipelineTask + Proposer/Critic | **Medio** — con componentes agenciales existentes (ReactRunner, SelfRefinementLoop) el esfuerzo se reduce |
| `core_pattern_extractor` | ❌ | P4 (PRO, per-document) | Alto — alimenta la pausa de 3 docs |

**Problema actual:** El `incident_extractor` está fusionado con `b2a_extract_indicators` y corre en FASE B (cross-document), no en FASE A (per-document). Según kb.md, debería correr **por segmento** apenas se termina de clasificar el dato.

**Arquitectura objetivo (kb.md):**
```
Por cada segmento de ORO:
  incident_extractor (FLASH, per-segmento) → jot (gerundio)
  
Por cada documento:
  core_pattern_extractor (PRO, per-documento) → patrón individual

Cada 3 documentos:
  population_generalizer (PRO) → ¿refinar población?
  core_pattern_verifier (PRO) → ¿convergen los patrones?
```

**Beneficio de aplicar los patrones:**
- **P2 (Tracking):** cada extracción de incidente → `PipelineTask`. Trazabilidad total.
- **P3 (Resiliencia):** `AbortableTask` en `incident_extractor`. Si falla un segmento, no pierde todo el doc.
- **P4 (Agencial):** El `incident_extractor` es FLASH puro (1-pass). El `core_pattern_extractor` es PRO con SelfRefinement.

---

### FASE 2: Síntesis Cross-Document (Phase B)

#### Agentes actuales vs kb.md

| kb.md | Código actual | ¿Alineado? |
|-------|--------------|------------|
| **Comparador** (B1): recibe SOLO incidentes, sin ver categorías | `b1_distill_sampling`: ve population_context + processes + codes | ❌ El código actual le da categorías existentes — kb.md dice explícitamente que NO debe verlas |
| **Etiquetador** (B2): propone etiquetas desde grupos del Comparador | `b2_open_code`: extrae indicadores + genera códigos | ⚠️ La separación Comparador→Etiquetador no se respeta |
| **Crítico** (B3): evalúa etiquetas, diálogo con Etiquetador | `b2_critic` existe como prompt pero no como bucle | ❌ No hay bucle Etiquetador↔Crítico |

**Estado del patrón:** ❌ 0/4 patrones aplicados.

**Arquitectura objetivo (kb.md):**
```
B1. incident_comparator (PRO, 1-pass)
    → recibe SOLO incidentes (sin categorías)
    → agrupa por intercambiabilidad
    → emite grupos

B2. pattern_labeler (PRO, SelfRefinement)
    → recibe grupos del Comparador
    → propone etiquetas + definiciones
    → loop con B3 hasta 3 iteraciones

B3. label_critic (FLASH, 1-pass)
    → evalúa cada etiqueta
    → feedback al Etiquetador
    → aprueba/rechaza

B4. evidence_retriever (RAG, sin LLM)
    → busca segmentos en el corpus para cada categoría aprobada
```

**Beneficio de aplicar los patrones:**
- **P1 (Transiciones):** B1→B2→B3 como pipeline con `transition()` entre etapas.
- **P2 (Tracking):** `PipelineTask` por cada sub-etapa (B1, B2, B3).
- **P3 (Resiliencia):** `AbortableTask` + checkpoints en B2 (el loop puede ser largo).
- **P4 (Agencial):** B2 usa SelfRefinement. B3 usa FLASH (es evaluación, no generación).

**⚠️ Cambio arquitectónico mayor:** La separación Comparador/Etiquetador/Crítico requiere refactorizar `agents_b.py` completamente. El Comparador NO debe recibir categorías existentes — esto es una violación directa de la metodología CGT según kb.md §5.

---

### FASE 3: Selective Coding — Core Category Detection

#### Agentes

| Agente (kb.md) | Modelo | ¿Implementado? | ¿Patrón aplica? |
|----------------|--------|---------------|-----------------|
| `main_concern_proposer` | PRO | ✅ (`task_a14_main_concern`) | P2, P3, P4 pendientes |
| `main_concern_critic` | PRO | ✅ (mismo task) | P4: separar en llamada independiente |
| `core_emergence_proposer` | PRO | ✅ (`task_a15_core_emergence`) | P2, P3 pendientes |
| `core_emergence_critic` | **FLASH** | ✅ (mismo task) | P4: FLASH correcto para test de intercambiabilidad |

**Estado del patrón:** ❌ 0/4. Las tareas existen pero sin tracking, sin AbortableTask en sus wrappers individuales, sin checkpoints.

**Beneficio de aplicar los patrones:**
- **P2 (Tracking):** `PipelineTask` con `document_id=NULL` (tareas de proyecto).
- **P3 (Resiliencia):** `AbortableTask` en `task_a14_main_concern` y `task_a15_core_emergence`.
- **P4 (Agencial):** Proposer→Critic→HITL ya es el patrón. Solo falta formalizarlo.

**⚠️ Nota kb.md §7.2:** Hay un "maturity gate" con 3 condiciones antes de siquiera proponer candidatos. Esto DEBE implementarse como un chequeo determinístico (sin LLM) que revise la DB:
```python
def maturity_gate(project_id):
    saturated = count_categories_with_4_green_signals(project_id)
    relationships = count_documented_relationships(project_id)
    linked_to_concern = count_categories_linked_to_main_concern(project_id)
    return saturated >= 3 and relationships >= 2 and linked_to_concern >= 3
```

---

### FASE 4: Selective Coding — Selective Reduction

| Agente (kb.md) | Modelo | ¿Implementado? | ¿Patrón aplica? |
|----------------|--------|---------------|-----------------|
| `selective_reduction_proposer` | PRO | ✅ (`trigger_selective_elaboration` → `task_a01` etc.) | P2, P3 pendientes |
| `selective_reduction_critic` | PRO | ✅ (mismo flujo) | P4: separar proposer/critic |

**Estado del patrón:** ❌ 0/4.

**Beneficio de aplicar los patrones:**
- **P1 (Transiciones):** Al terminar selective reduction → `transition(project_id, "reducido")`.
- **P2 (Tracking):** `PipelineTask` por cada categoría evaluada.
- **P4 (Agencial):** Proposer→Critic→HITL formalizado.

---

### FASE 5: Selective Coding — Core Saturation Loop

| Agente (kb.md) | Modelo | ¿Implementado? | Loop? |
|----------------|--------|---------------|-------|
| `core_saturation_proposer` | PRO | ❌ | Sí — itera sobre categorías × documentos |
| `core_saturation_critic` | **FLASH** | ❌ | Sí — potencialmente cientos de llamadas |
| `rename_detector` | Algorítmico | ✅ (`rename_detector.py`) | N/A |
| `SaturationGapAnalyzer` | Algorítmico + 4 señales | ✅ (`saturation_gap_analyzer.py`) | N/A |
| `EmergentSampler` (TheoSampler) | RAG + LLM | ⚠️ Parcial | Bajo demanda |

**Estado del patrón:** ❌ 0/4. Esta es la fase más intensiva en llamadas y la que más se beneficia de los patrones.

**Beneficio CRÍTICO de aplicar los patrones:**
- **P2 (Tracking):** Sin tracking, no hay forma de saber cuántas iteraciones del loop se completaron. El usuario no puede ver progreso.
- **P3 (Resiliencia):** `AbortableTask` es ESENCIAL — el loop puede correr cientos de iteraciones. Si el usuario quiere parar, debe poder hacerlo.
- **P4 (Agencial):** El critic es FLASH (decisión de costo consciente — kb.md §6.3 lo explica). El loop con criterio de 3 iteraciones sin `did_state_expand` ya está diseñado.

**⚠️ El panel de 4 señales (kb.md §6.4):**
1. Señal matemática (barata) → `saturation_metrics.rolling_std`
2. Señal cualitativa (cara) → `did_state_expand` del critic FLASH
3. Cobertura → extremos de propiedades documentados
4. Integración → conexiones con otras categorías

Este panel DEBE implementarse como un endpoint dedicado que el frontend consulte. No como parte del loop.

---

### FASE 6: Database A/B

| Agente (kb.md) | Modelo | ¿Implementado? |
|----------------|--------|---------------|
| `database_a_proposer` | PRO | ❌ |
| `database_a_critic` | PRO | ❌ |
| `database_b_proposer` | PRO | ❌ |
| `database_b_critic` | PRO | ❌ |

**Estado del patrón:** ❌ 0/4. No implementado en absoluto.

---

### FASE 7: Theoretical Coding (Playground)

| Agente (kb.md) | ¿Implementado? | ¿Patrón aplica? |
|----------------|---------------|-----------------|
| `conceptual_elaborator` | ✅ (`elaboration_engine.py`) | P4 (PRO) — ya usa LLM |
| `ghost_blob_mapper` | ✅ (`ghost_connector.py`) | P4 (PRO) — ya usa LLM |
| `ecosystem_gap_detector` | ⚠️ Parcial (`recommendation_engine.py`) | N/A (algorítmico) |

**Estado del patrón:** ⚠️ Los agentes existen pero sin tracking (P2), sin cancelabilidad (P3).

---

### FASE 8+: Redacción, Literatura, Aplicabilidad

| Fase (kb.md) | Agentes | ¿Implementado? |
|-------------|---------|---------------|
| Redacción natural (§11) | `natural_writer`, `writing_critic`, `gap_feeler` | ❌ |
| Diálogo con literatura (§12) | `literature_comparer`, `literature_critic` | ❌ |
| Aplicabilidad (§13) | `applicability_engine`, `applicability_critic` | ❌ |

**Estado del patrón:** No implementado. Estas fases se benefician principalmente de P4 (Proposer/Critic/HITL) y P2 (Tracking).

---

## 2. Priorización — Qué aplicar primero

### 🔴 Crítico (bloquea otras fases)

| # | Qué | Fase CGT | Patrones | Esfuerzo |
|---|-----|----------|----------|----------|
| 1 | Separar `incident_extractor` de `b2a` — que corra per-segmento en FASE A | Open Coding | P2, P4 | Medio |
| 2 | Refactorizar FASE B: Comparador → Etiquetador ↔ Crítico | Síntesis | P1, P2, P3, P4 | Alto |
| 3 | `maturity_gate` determinístico antes de Selective Coding | Selective | P1 | Bajo |
| 4 | `AbortableTask` + tracking en todas las tareas de selective coding | Selective | P2, P3 | Medio |
| 4b | `maturity_gate` deterministico en OrchestratorRuleEngine | Selective | P1 | Bajo |

### 🟡 Importante (desbloquea funcionalidad)

| # | Qué | Fase CGT | Patrones | Esfuerzo |
|---|-----|----------|----------|----------|
| 5 | Core Saturation Loop con checkpoints por iteración | Selective | P3, P4 | Alto |
| 6 | Panel de 4 señales como endpoint dedicado | Selective | P1 | Medio |
| 7 | Database A/B desde cero | Selective | P2, P4 | Alto |
| 8 | Tracking en Theoretical Playground | Theoretical | P2 | Bajo |

### 🟢 Futuro (nice to have)

| # | Qué | Fase CGT | Esfuerzo |
|---|-----|----------|----------|
| 9 | Redacción natural con proposer/critic | Escritura | Alto |
| 10 | Diálogo con literatura | Escritura | Medio |
| 11 | Aplicabilidad | Escritura | Medio |

---

## 3. Decisión Arquitectónica: Orchestrator ¿Inteligente o Delgado?

El mermaid (`secuencia_actual.mermaid`) muestra un Orchestrator que llama LLMs directamente. Nuestro código tiene un Orchestrator delgado que solo despacha tareas Celery. **¿Cuál es correcto?**

### Recomendación: Orchestrator DELGADO

| Criterio | Delgado (actual) | Inteligente (mermaid) |
|----------|-----------------|----------------------|
| Cancelabilidad | ✅ Celery revoke por tarea | ❌ Threads sin control granular |
| Tracking | ✅ PipelineTask por tarea | ❌ Sin tracking granular |
| Resumibilidad | ✅ Checkpoints por tarea | ❌ Sin checkpoints |
| Escalabilidad | ✅ Workers independientes | ❌ FastAPI bloqueado en LLM calls |
| Timeouts | ✅ Por tarea Celery | ❌ HTTP timeouts (30s) |

El Orchestrator delgado es **consistente con los 4 patrones**. El Orchestrator inteligente los rompe todos. El mermaid debe corregirse para mostrar `HVY->>LLM`, no `ORC->>LLM`.

---

## 4. Resumen de Modificaciones Pendientes

### Archivos a crear (7)

| Archivo | Fase CGT | Contenido |
|---------|----------|-----------|
| `workers/heavy/incident_extractor.py` | Open Coding | `incident_extractor` (FLASH, per-segmento) |
| `workers/heavy/pattern_extractor.py` | Open Coding | `core_pattern_extractor` (PRO, per-documento) |
| `workers/heavy/comparator.py` | Síntesis | `incident_comparator` (PRO, 1-pass, sin ver categorías) |
| `workers/heavy/labeler.py` | Síntesis | `pattern_labeler` (PRO, SelfRefinement) |
| `workers/heavy/label_critic.py` | Síntesis | `label_critic` (FLASH, 1-pass) |
| `workers/heavy/saturation_loop.py` | Selective | `core_saturation_proposer` + `critic` + loop |
| `workers/heavy/database_ab.py` | Selective | Database A/B proposers + critics |

### Archivos a modificar (8)

| Archivo | Cambio |
|---------|--------|
| `workers/heavy/agents_b.py` | Refactorizar: separar Comparador/Etiquetador/Crítico |
| `workers/heavy/tasks.py` | `AbortableTask` en `task_a14`, `task_a15`, `trigger_selective_elaboration` |
| `agents/transitions.py` | Extender `NEXT` con estados de proyecto |
| `backend/app/services/pipeline_orchestrator.py` | `maturity_gate()` determinístico |
| `backend/app/api/v1/pipeline.py` | Endpoint para panel de 4 señales |
| `backend/app/models/domain/project.py` | Agregar `estados_proyecto` |
| `frontend/src/pages/Project.tsx` | PIPELINE_STAGES con etapas reales |
| `Documentacion/cgt_alignment/secuencia_actual.mermaid` | Corregir `ORC->>LLM` → `HVY->>LLM` |
