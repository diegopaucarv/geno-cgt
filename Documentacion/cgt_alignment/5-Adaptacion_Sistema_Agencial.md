# 5 — Adaptación del Sistema Agencial a la Especificación CGT

> **Fecha:** 2026-06-16
> **Base:** `kb.md` (knowledge base CGT), `4-Patrones_de_desarrollo.md` (patrones de desarrollo)
> **Analiza:** Cómo los componentes agenciales existentes se adaptan, qué falta, y qué debe cambiar.

---

## 1. Diagnóstico: qué ya tenemos y dónde encaja

### 1.1 Componentes agenciales existentes vs flujo CGT

```
FLUJO CGT (kb.md)                    COMPONENTE AGENCIAL EXISTENTE       ESTADO
─────────────────────────────        ─────────────────────────────       ──────
Fase 0: Configuración                (sin agente)                        ❌
Fase 1: Open Coding (per-segmento)   incident_extractor (FLASH)          ⚠️ fusionado con B2a
Fase 1: Patrón individual (per-doc)  (sin agente)                        ❌
Fase 1: Pausa cada 3 docs            (sin agente)                        ❌
Fase 2: Comparator (solo incidentes) (sin agente — fusionado con B2)     ❌ CRÍTICO
Fase 2: Labeler ↔ Critic             SelfRefinementLoop (B2b)            ✅ patrón correcto
Fase 2: Evidence retrieval           B2.5 assign_codes + RAG             ✅
Fase 3A: Main concern proposer       task_a14_main_concern               ✅ existe, sin tracking
Fase 3A: Main concern critic         (mismo task)                        ⚠️ fusionado
Fase 3A: Core emergence proposer     task_a15_core_emergence             ✅ existe
Fase 3A: Core emergence critic       (mismo task, FLASH)                 ✅ modelo correcto
Fase 3B: Selective reduction         trigger_selective_elaboration       ⚠️ parcial
Fase 3C: Saturation loop             (sin agente)                        ❌
Fase 3C: Saturation critic           (sin agente)                        ❌ (debe ser FLASH)
Fase 3D: Database A/B                (sin agente)                        ❌
Fase 4: Theoretical Playground       ElaborationEngine, GhostConnector   ✅ parcial
Fase 5: Redacción natural            (sin agente)                        ❌
Fase 6: Literatura                   (sin agente)                        ❌
Fase 7: Aplicabilidad                (sin agente)                        ❌
```

### 1.2 Lo que nuestro sistema agencial YA resuelve bien

| Componente | Patrón CGT que implementa | Valor |
|-----------|--------------------------|-------|
| `SelfRefinementLoop` | Labeler ↔ Critic (B2/B3 loop de 3 iteraciones) | Ya implementa exactamente el diálogo generativo-crítico que kb.md describe |
| `ReactRunner` | Búsqueda de evidencia antes de hipotetizar (B3) | El agente busca `search_segments` antes de generar — igual que kb.md §5 "Evidencia textual para cada categoría" |
| `OrchestratorRuleEngine` | Maturity gate + routing determinístico | kb.md §7.2 describe 3 condiciones pre-LLM. El Orchestrator puede implementarlas como reglas. |
| `BaseAgent._build_assistant_message()` | Preservación de razonamiento entre turnos | Esencial para el loop Etiquetador↔Crítico donde el modelo ve su propio análisis previo |
| `quality/scorer.py` | Evaluación algorítmica pre-critic | kb.md §6.4 describe 4 señales. La señal matemática YA es algorítmica. |
| `ToolRegistry` + 7 tools | Capacidad de buscar evidencia en el corpus | kb.md §5 "busca en todo el corpus segmentos que respalden esa categoría" |
| `PlanExecutor` | Multi-step planning para fases complejas | Database A/B requiere planificar: nodos → edges → verificar |

---

## 2. Los 3 cambios arquitectónicos críticos que kb.md exige

### 2.1 CRÍTICO #1: Separar Comparator de Labeler

**Problema:** Nuestro `b2_open_code()` fusiona tres roles que kb.md exige separar:
- El Comparator (B1) recibe SOLO incidentes, sin ver categorías existentes
- El Labeler (B2) recibe grupos del Comparator
- El Critic (B3) evalúa etiquetas y dialoga con el Labeler

**Evidencia en kb.md §5:** "El Comparador recibe todos los incidentes extraídos de todos los documentos — y solo los incidentes. No ve categorías existentes. No ve etiquetas previas."

**Nuestro código actual viola esto:** `b2_open_code()` pasa `existing_codes` a B2b, y el Comparator ni siquiera existe como etapa separada.

**Solución:** Refactorizar `agents_b.py` en tres etapas:
```python
# Etapa 1: Comparator (PRO, 1-pass, sin ver categorías)
def b1_compare_incidents(proyecto_id):
    incidentes = get_all_incidents(proyecto_id)  # solo incidentes, sin categorías
    return llm.run_agent("incident_comparator", variables={
        "incidents": incidentes,
        "population_assumption": pop_assumption,
        # ⚠️ NO pasa existing_codes
    })

# Etapa 2: Labeler ↔ Critic (SelfRefinementLoop)
def b2_label_groups(proyecto_id, grupos_del_comparator):
    loop = SelfRefinementLoop("pattern_labeler", llm, 
        generate_prompt_id="pattern_labeler",
        critic_prompt_id="label_critic")
    return loop.run(proyecto_id, generate_vars={
        "groups": grupos_del_comparator,
        "population_context": pop_ctx,
    })
```

**Beneficio agencial:** El `SelfRefinementLoop` ya implementa el diálogo Labeler↔Critic. Solo falta separar el Comparator antes.

### 2.2 CRÍTICO #2: El maturity gate determinístico

**Problema:** kb.md §7.2 describe 3 condiciones que deben verificarse ANTES de siquiera proponer candidatos a core category. Esto NO debe usar LLM.

**Solución:** El `OrchestratorRuleEngine` ya tiene el patrón correcto (reglas determinísticas + heurísticas). Agregar:

```python
# En OrchestratorRuleEngine:
def maturity_gate(self, project_id, state):
    """kb.md 7.2: 3 condiciones pre-core-category-detection."""
    saturated = state.get("saturated_categories", 0)
    relationships = state.get("documented_relationships", 0)
    linked = state.get("categories_linked_to_concern", 0)
    
    if saturated >= 3 and relationships >= 2 and linked >= 3:
        return "core_emergence_proposer"  # gate abierto
    return "continue_coding"  # gate cerrado — seguir codificando
```

### 2.3 CRÍTICO #3: El incident extractor aislado

**Problema:** kb.md §4 es muy claro: "El extractor de incidentes está aislado. No ve otros documentos. No ve categorías existentes. No ve patrones previos."

Actualmente, los incidentes se extraen en B2a (Fase B), no en Fase A (per-documento), y el extractor comparte contexto con otros agentes.

**Solución:** Mover `b2a_extract_indicators` a una tarea independiente que corre por segmento apenas se clasifica el dato, usando FLASH (1-pass, sin SelfRefinement — es extracción, no generación):

```python
@app.task(name="extract_incident")
def extract_incident(segmento_id, object_of_study, coding_style):
    """kb.md 4: 4 preguntas de Glaser, aislado, FLASH."""
    segmento = get_segment(segmento_id)
    if segmento.tipo_dato_glaser != "baseline_data":
        return {"skip": True, "reason": "not gold data"}
    
    return llm.run_agent("incident_extractor", variables={
        "segment": segmento.texto,
        "object_of_study": object_of_study,
        "coding_style": coding_style,
        # ⚠️ NO pasa: existing_codes, population_context, otros segmentos
    }, tier="FLASH")
```

---

## 3. Cómo nuestros 4 patrones agenciales mapean al ritmo CGT

kb.md describe un ritmo universal: **Proponer → Criticar → Sintetizar → Volver a criticar → Decidir (HITL)**

Nuestros patrones agenciales implementan exactamente esto:

```
RITMO CGT (kb.md)              PATRÓN AGENCIAL              DÓNDE
──────────────────────         ───────────────────          ─────────────────
Proponer (sin ver lo que       SelfRefinementLoop          B2 (Labeler)
  ya existe)                   (Generate, sin existing_      B3 (Hypotheses)
                                codes en el prompt)          Main concern proposer

Criticar (comparando           SelfRefinementLoop          B2 critic (FLASH)
  contra los datos)            (Critic step)                B3 critic (FLASH)
                               quality/scorer.py (O6)       Core emergence critic

Sintetizar (integrando         SelfRefinementLoop          B2 refine step
  propuesta + crítica)         (Refine step)                B3 refine step

Volver a criticar              SelfRefinementLoop          Loop de 3 iteraciones
  (segunda pasada, más fina)   (max_iterations=3)           exactamente como kb.md

VOS DECIDÍS (HITL)             AgentResult + fallback      B2, B3, selective coding
                               (success/failure)            todos los gates HITL
```

---

## 4. Adaptaciones necesarias a nuestros componentes

### 4.1 `SelfRefinementLoop` — ya implementa el diálogo Labeler↔Critic

**No requiere cambios.** kb.md §5 describe exactamente lo que hace: "El Etiquetador mejora la etiqueta y la reenvía. Este bucle generativo-crítico se repite hasta tres veces."

Nuestro `SelfRefinementLoop(max_iterations=3)` con `generate_prompt_id` y `critic_prompt_id` es una implementación directa. Solo necesitamos los prompts correctos (`pattern_labeler.md` y `label_critic.md`).

### 4.2 `ReactRunner` — necesita adaptación para el "keep moving"

kb.md §4: "Si un incidente es ambiguo, anotalo y avanza. Confiá en que el patrón se revelará cuando tengas docenas de incidentes."

**Adaptación:** Agregar una tool `mark_keep_moving` que el agente puede llamar cuando un incidente es ambiguo:

```python
@tool(name="mark_keep_moving", description="Marca un incidente como ambiguo y avanza sin sobre-analizar.",
      parameters={"incident_id": "ID del incidente", "reason": "Por qué es ambiguo"})
def mark_keep_moving(incident_id, reason):
    # actualiza segmento: keep_moving=true
    return {"status": "marked", "principle": "keep_moving"}
```

### 4.3 `OrchestratorRuleEngine` — perfecto para el maturity gate

El Orchestrator determinístico que construimos es la herramienta ideal para implementar:
- El maturity gate (3 condiciones, sin LLM)
- Las transiciones entre fases (cada 3 documentos → pausa)
- El routing del loop de saturación (por categoría × documento)

**Agregar reglas:**
```python
RULES = {
    # ... existing ...
    "maturity_check": "core_emergence_proposer",  # si gate abierto
    "maturity_check": "continue_coding",           # si gate cerrado
}
```

### 4.4 `quality/scorer.py` — alineado con el panel de 4 señales

kb.md §6.4 describe 4 señales de saturación. Nuestro scorer ya implementa la señal algorítmica (estilo, redundancia). El `SaturationGapAnalyzer` existente implementa las 4 señales vía SQL. La integración es directa: el scorer algorítmico es el pre-filtro, el analyzer es la verificación completa.

### 4.5 `PlanExecutor` — ideal para Database A/B

kb.md §6.5 describe Database A (nodos) y Database B (edges) como construcciones multi-step. El PlanExecutor puede orquestar:
```
Plan: [build_nodes, verify_nodes, build_edges, verify_edges, hitl_review]
```

---

## 5. Lo que el sistema agencial NO cubre (y debe construirse)

### 5.1 Agentes nuevos requeridos por kb.md

| Agente (kb.md) | Prioridad | Nuestro componente base |
|----------------|----------|------------------------|
| `incident_extractor` (FLASH, per-segmento) | CRÍTICA | Nuevo. Prompt nuevo. FLASH, 1-pass. |
| `core_pattern_extractor` (PRO, per-documento) | ALTA | Nuevo. Usa SelfRefinementLoop. |
| `incident_comparator` (PRO, solo incidentes) | CRÍTICA | Nuevo. Refactorizar B1. |
| `pattern_labeler` (PRO, SelfRefinement) | CRÍTICA | Usa SelfRefinementLoop existente. |
| `label_critic` (FLASH, 1-pass) | CRÍTICA | Usa quality/scorer.py + FLASH. |
| `core_saturation_proposer` (PRO) | ALTA | Nuevo. |
| `core_saturation_critic` (FLASH) | ALTA | Nuevo. FLASH por costo. |
| `database_a_proposer` + `critic` (PRO) | MEDIA | Nuevo. PlanExecutor. |
| `database_b_proposer` + `critic` (PRO) | MEDIA | Nuevo. PlanExecutor. |

### 5.2 Prompts nuevos requeridos

| Prompt | Tier | Basado en |
|--------|------|----------|
| `incident_extractor.md` | FLASH | Las 4 preguntas de Glaser (kb.md §4) |
| `incident_comparator.md` | PRO | Comparación constante sin ver categorías |
| `pattern_labeler.md` | PRO | Similar a b2b_generate_codes.md pero recibe grupos |
| `label_critic.md` | FLASH | Similar a code_critic.md |
| `core_saturation_proposer.md` | PRO | Compara incidentes contra paradigm_state |
| `core_saturation_critic.md` | FLASH | Diff estructurado — ¿expansión genuina? |

---

## 6. Correcciones al mermaid (`secuencia_actual.mermaid`)

El diagrama actual tiene 2 problemas que kb.md y 4-Patrones corrigen:

### 6.1 `ORC->>LLM` debe ser `HVY->>LLM`

El Orchestrator es **delgado** — solo despacha tareas y verifica transiciones. Las llamadas LLM las hacen los workers (Heavy Worker). El mermaid muestra `ORC->>LLM` en varias etapas (B1, Map Synthesis, Reduce Synthesis, etc.) cuando debería mostrar `HVY->>LLM`.

### 6.2 Faltan etapas completas

El mermaid omite:
- El incident_extractor per-segmento en Fase A
- La pausa cada 3 documentos
- El maturity gate determinístico
- El panel de 4 señales de saturación
- Database A/B como etapas separadas
- El loop de saturación (C1+C2 por categoría × documento)
- La separación Comparator → Labeler ↔ Critic

---

## 7. Recomendación de prioridades

```
FASE INMEDIATA (lo que ya podemos construir con lo que tenemos):
─────────────────────────────────────────────────────────────────
1. Separar Comparator de Labeler en agents_b.py
   → Usa SelfRefinementLoop para Labeler↔Critic
   → Nuevo prompt: incident_comparator.md (PRO, 1-pass, sin categorías)
   
2. Mover incident_extractor a Fase A (per-segmento, FLASH)
   → Nuevo prompt: incident_extractor.md
   → Nueva tarea Celery: extract_incident
   
3. Implementar maturity_gate en OrchestratorRuleEngine
   → 3 reglas determinísticas, sin LLM
   
4. Crear prompts para labeler/critic
   → pattern_labeler.md (PRO)
   → label_critic.md (FLASH)

FASE SIGUIENTE (requiere más infraestructura):
─────────────────────────────────────────────────────────────────
5. Core saturation loop con FLASH critic
6. Database A/B con PlanExecutor
7. Panel de 4 señales como endpoint dedicado
```

---

## 8. Modificaciones a `4-Patrones_de_desarrollo.md` ✅ [APLICADO — 2026-06-16]

> **Estado:** Las modificaciones propuestas en esta seccion fueron aplicadas. Ver `AGENTES.md` para el registro de patrones agenciales operativos. La prioridad del incident_extractor se corrigio a Medio en `CHECKLIST_CGT_REFACTOR.md` F2.2.1. El maturity gate se documento como tarea de bajo esfuerzo en F1.4.

El documento original proponia:

### 8.1 Agregar sección "Patrones agenciales implementados"

Después de la tabla de los 4 patrones, agregar:

```markdown
### Patrones agenciales ya operativos

El sistema ya cuenta con componentes que implementan los patrones CGT:

| Componente | Patrón CGT | Estado |
|-----------|-----------|--------|
| `SelfRefinementLoop` | Proposer → Critic → Refine (Labeler↔Critic) | ✅ Listo |
| `ReactRunner` | Búsqueda de evidencia con tools antes de generar | ✅ Listo |
| `OrchestratorRuleEngine` | Maturity gate + routing determinístico | ✅ Listo |
| `quality/scorer.py` | Evaluación algorítmica pre-critic (señal matemática) | ✅ Listo |
| `ToolRegistry` (7 tools) | Búsqueda de evidencia en corpus (RAG, TEI, DB) | ✅ Listo |
| `PlanExecutor` | Multi-step planning (Database A/B) | ✅ Listo |
```

### 8.2 Corregir prioridad del incident_extractor

La sección "Priorización — Qué aplicar primero" marca el `incident_extractor` como esfuerzo "Alto". Con los componentes agenciales existentes, el esfuerzo es **Medio**:

- El prompt `incident_extractor.md` se escribe en 1 hora (ya tenemos el patrón de prompts FLASH)
- La tarea Celery `extract_incident` es una función de 30 líneas
- El `ReactRunner` puede orquestar la extracción si el incidente es ambiguo (keep_moving)

Propongo cambiar `Alto → Medio` en la tabla de priorización.

### 8.3 Agregar el maturity gate como tarea de bajo esfuerzo

El documento menciona el maturity gate en §7.2 de kb.md pero no lo lista en la sección de prioridades. Con el `OrchestratorRuleEngine`, implementarlo es **3 reglas determinísticas** — esfuerzo Bajo, no Alto.

---

## 9. Conclusión

El sistema agencial que construimos está **sorprendentemente alineado** con la especificación CGT de kb.md. Los 4 patrones (SelfRefinement, ReAct, Plan-Execute, Multi-Agent Debate) son implementaciones directas del ritmo "Proponer → Criticar → Sintetizar → Decidir" que kb.md describe como el latido del sistema.

**Las 3 brechas críticas** (Comparator aislado, maturity gate, incident extractor per-segmento) son corregibles con componentes que YA existen. No requieren nueva infraestructura — solo nueva configuración de lo que ya tenemos.

**La arquitectura agencial que construimos no compite con la especificación CGT — la implementa.**
