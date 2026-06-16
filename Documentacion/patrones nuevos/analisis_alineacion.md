# Análisis de Alineación — Patrón Maestro vs Sistema Actual

> **Auditoría archivo-por-archivo del código existente contra el `Patron_Desarrollo_Maestro.md`.**
>
> Fecha: 2026-06-16

---

## Resumen de Alineación

| Componente | Estado | Brecha principal |
|------------|--------|-----------------|
| `agents/transitions.py` | ⚠️ Parcial | Solo maneja estados de documento, no de proyecto. Sin `sintetizado`. |
| `core/workflow.py` | ❌ Desalineado | Mezcla open/selective coding. Sin Proposer→Critic→HITL. |
| `workers/heavy/tasks.py` | ❌ Desalineado | `trigger_selective_elaboration` viola R0.1, R0.2, R0.3. |
| `models/domain/` | ⚠️ Parcial | Theory models ✅. Falta `HitlDecision`. Project sin estados pipeline. |
| `api/v1/pipeline.py` | ⚠️ Parcial | Dispara stages antiguos. Sin endpoint HITL. |
| `api/v1/events.py` | ✅ Alineado | SSE + Redis pub/sub listo para HITL. |
| `services/` | ✅ Alineado | Todos los engines existen y cumplen el contrato. |
| `prompts/` | ❌ Incompleto | Faltan 12 prompts del pipeline selectivo. |
| `frontend/` | ⚠️ Parcial | Playground ✅. Pipeline stages antiguos. Sin HITLModal. |

---

## 1. `backend/app/agents/transitions.py` — Análisis Detallado

### Lo que EXISTE ✅

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 26-41 | `NEXT` dict con estados doc: crudo→segmentando→segmentado→procesando→listo | ✅ Correcto |
| 44-107 | `transition()` con optimistic locking (`WHERE estado=current`) | ✅ Cumple REGLA 5 |
| 115-121 | `_to_error()` | ✅ Correcto |
| 124-177 | `_dispatch_next()` con PipelineTask tracking | ✅ Cumple REGLA 2 |
| 180-232 | `_maybe_trigger_phase_b()` con deduplicación vía `processing_states` | ✅ Correcto pero limitado |
| 235-257 | `_get_active_run()`, `_get_texto()` | ✅ Correcto |

### Lo que FALTA ❌

| Elemento | Gravedad | Detalle |
|----------|----------|--------|
| Estado `sintetizado` | 🔴 | `NEXT` dict no tiene transición `listo → sintetizado`. Phase B debe actualizar docs a `sintetizado`, no dejarlos en `listo`. |
| Estados de proyecto | 🔴 | Solo maneja `documentos.estado`. No existe `proyectos.estado` con valores `collecting|coding|finding_cc|reducing|saturating|building_db|playground_ready|completed`. |
| HITL gate | 🔴 | No hay función `hitl_gate()` que pause el pipeline, guarde proposal+verdict en DB, y espere confirmación. |
| `_maybe_trigger_phase_b` no usa estado `sintetizado` | 🟠 | Actualmente verifica `COUNT(*) WHERE estado='listo'`. Debería verificar `estado='sintetizado'`. |

### Modificaciones necesarias

```diff
# transitions.py — Cambios requeridos

# 1. Agregar 'sintetizado' al NEXT dict
  NEXT: dict[str, tuple[str, str | None, str | None]] = {
      ...
-     "listo": (None, None, None),
+     "listo": ("sintetizado", None, None),   # Phase B transiciona
+     "sintetizado": (None, None, None),       # Terminal (espera selective coding)
      "error": ("crudo", None, None),
  }

# 2. Agregar manejo de estados de proyecto
+ PROJECT_STATES = {
+     "collecting": "coding",
+     "coding": "finding_cc",
+     "finding_cc": "reducing",
+     "reducing": "saturating",
+     "saturating": "building_db",
+     "building_db": "playground_ready",
+     "playground_ready": "completed",
+ }
+
+ def transition_project(session, proyecto_id, from_state, to_state) -> bool:
+     """Transiciona el estado de un proyecto con optimistic locking."""
+     ...

# 3. Agregar hitl_gate()
+ def hitl_gate(session, project_id, gate_name, proposal, critic_verdict) -> str:
+     """Inserta en hitl_decisions, notifica frontend, bloquea hasta decisión."""
+     ...

# 4. Actualizar _maybe_trigger_phase_b para usar estado 'sintetizado'
- SELECT COUNT(*) WHERE estado = 'listo'
+ SELECT COUNT(*) WHERE estado = 'sintetizado'
```

### Spillovers

- **`_maybe_trigger_phase_b`** se dispara cuando un doc llega a `listo` (línea 104). Con el nuevo estado `sintetizado`, el trigger se mueve: ahora `process_synthesis_agents_b` debe llamar `transition(session, doc_id, ..., "listo", "process_synthesis_agents_b", True)` para cada doc → eso transiciona a `sintetizado` → `_maybe_trigger_phase_b` ya no aplica desde `transition()`. **Spillover:** `process_synthesis_agents_b` en `workers/heavy/tasks.py` debe iterar los docs y transicionarlos individualmente.

---

## 2. `backend/app/core/workflow.py` — Análisis Detallado

### Lo que EXISTE ✅

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 34-91 | `AnalysisState` TypedDict | ✅ Cubre campos necesarios |
| 99-130 | `node_segment_and_index` | ✅ Open coding (conservar) |
| 133-150 | `node_extract_entities` | ✅ Open coding (conservar) |
| 153-179 | `node_batch_code` | ✅ Open coding (conservar) |
| 182-209 | `node_map_synthesize` | ✅ Open coding (conservar) |
| 212-216 | `node_reduce_synthesize` | ✅ Open coding (conservar) |
| 287-310 | `node_hitl_review` | ⚠️ Solo hipótesis, no es suficiente |
| 359-433 | `build_glaser_graph()` | ❌ Mezcla open + selective coding |
| 531-582 | `node_theosampler_evaluate` | ⚠️ Pre-emptive, debe ser reactivo |
| 585-618 | `node_hitl_gap_review` | ✅ Correcto pero aislado |
| 660-721 | `node_prepare_playground` | ✅ Correcto |
| 767-853 | `build_glaser_graph_with_feedback()` | ❌ Mismo problema que el grafo base |

### Lo que FALTA ❌

| Elemento | Gravedad | Detalle |
|----------|----------|--------|
| `node_find_core_concern` (L219-235) viola R0.1 | 🔴 | Llama `task_a14_main_concern()` directamente, sin Proposer→Critic→HITL. El resultado se asigna sin confirmación humana. |
| `node_find_core_concern` viola R0.2 | 🔴 | No ejecuta A1+A2 serialmente, ni A3+A4 después. Es una sola llamada. |
| Sin `node_selective_reduction` | 🔴 | Fase B del selective coding no existe en el grafo. |
| Sin `node_core_saturation` | 🔴 | Fase C no existe. |
| Sin `node_database_a` / `node_database_b` | 🔴 | Fase D no existe. |
| Sin `node_global_saturation_check` | 🔴 | Fase E no existe. |
| `build_glaser_graph()` mezcla nodos | 🔴 | `find_core_concern`, `theosampler_evaluate`, `prepare_playground` son selective coding, pero están en el mismo grafo que `batch_code` (open coding). |
| El grafo no usa `transitions.py` | 🟠 | Opera con `AnalysisState`, no con `documentos.estado`. No hay optimistic locking ni PipelineTask tracking desde los nodos. |

### Decisión arquitectónica

**El grafo actual debe dividirse en DOS grafos separados:**

1. **Grafo A — Open Coding:** `segment_and_index → extract_entities → batch_code → map_synthesize → reduce_synthesize` (termina, es determinista, sin HITL)
2. **Pipeline B — Selective Coding:** No necesita ser un StateGraph de LangGraph. Es un **orchestrator secuencial** (el `selective_coding_coordinator`) que despacha tareas Celery una tras otra con gates HITL entre fases.

Los nodos `node_theosampler_evaluate`, `node_hitl_gap_review`, `node_process_new_data`, `node_prepare_playground` se **migran al coordinator en `workers/heavy/tasks.py`**.

### Modificaciones necesarias

```diff
# workflow.py — Cambios requeridos

# 1. El grafo build_glaser_graph() se reduce a solo open coding
  builder.add_node("segment_and_index", node_segment_and_index)
  builder.add_node("extract_entities", node_extract_entities)
  builder.add_node("batch_code", node_batch_code)
  builder.add_node("map_synthesize", node_map_synthesize)
  builder.add_node("reduce_synthesize", node_reduce_synthesize)
- builder.add_node("find_core_concern", node_find_core_concern)     # ❌ migrar
- builder.add_node("generate_hypotheses", node_generate_hypotheses)  # ❌ migrar
- builder.add_node("calculate_saturation", node_calculate_saturation) # ❌ migrar
- builder.add_node("hitl_review", node_hitl_review)                  # ❌ migrar
- builder.add_node("final_report", node_final_report)                # ❌ migrar
+ # El grafo termina en reduce_synthesize → END (Fase B de open coding)

# 2. build_glaser_graph_with_feedback() se elimina o simplifica
#    Los nodos E07-E08 + T25 van al coordinator.

# 3. Los nodos extraídos se convierten en funciones standalone
#    (no nodos de LangGraph) invocadas desde el coordinator.
```

### Spillovers

- **`invoke_graph()` en `workers/heavy/tasks.py`** (L1453-1518): Actualmente invoca `build_glaser_graph()`. Después del split, solo debe invocar el grafo reducido (open coding). Las fases selectivas ya no pasan por LangGraph.
- **`trigger_selective_elaboration`** (L1399): Llama `invoke_graph()` entre sus tareas. Al eliminarse, `invoke_graph()` solo se usa para open coding.
- **`node_find_core_concern`** importa `task_a14_main_concern` de `workers.heavy.tasks`. Esta dependencia circular implícita desaparece.

---

## 3. `workers/heavy/tasks.py` — Análisis Detallado

### Lo que EXISTE ✅

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 1181-1232 | `task_a14_main_concern` | ⚠️ Existe pero sin critic ni HITL |
| 1236-1278 | `task_a15_core_emergence` | ⚠️ Existe pero paralelo (no serial) |
| 1282-1323 | `task_a16_interchangeability` | ✅ Correcto como utilidad |
| 1327-1390 | `task_a04_group_constructs` | ✅ Correcto |
| 929-1002 | `task_a06_theoretical_sample` | ⚠️ Pre-emptive, debe ser reactivo |
| 1006-1082 | `task_a01_integrate_paradigm` | ✅ Correcto como utilidad |
| 1086-1172 | `task_a07_build_evidence_map` | ✅ Correcto |
| 641-806 | `process_document_agents_a` | ✅ Cumple R1-R5 |
| 841-864 | `process_synthesis_agents_b` | ⚠️ Sin AbortableTask, sin checkpoints |
| 1453-1518 | `invoke_graph` | ⚠️ Usa grafo mixto |
| 1522-1536 | `task_seed_theoretical_codes` | ✅ Correcto |

### Lo que FALTA ❌ — `trigger_selective_elaboration` (L1399-1440)

**Este es el PROBLEMA CENTRAL.** La función actual:

1. Itera sobre todas las categorías del proyecto
2. Para cada una, llama `task_a01_integrate_paradigm()` (elaboración por código)
3. No hay Proposer→Critic→HITL en ninguna decisión teórica
4. Las tareas A06, A01, A07, A14, A15, A16, A04, invoke_graph se ejecutan como grupo paralelo (desde el caller en pipeline.py o el frontend)

**Violaciones:**

| Regla | Violación |
|-------|-----------|
| R0.1 | Sin HITL. `task_a14_main_concern` decide el core concern automáticamente. |
| R0.2 | `task_a15` corre en paralelo con `task_a14` en lugar de serial. |
| R0.3 | `invoke_graph()` contiene nodos de open coding (`batch_code`, `map_synthesize`) dentro de fase selectiva. |
| R1 | Sin `transitions.transition()`. |
| R2 | Sin PipelineTask tracking. |
| R3 | Sin `AbortableTask`. |

### Modificaciones necesarias

```diff
# tasks.py — Cambios requeridos

# ── ELIMINAR ──────────────────────────────────────────────────────
- trigger_selective_elaboration()        # L1399-1440
- Todas las llamadas a estas tareas desde trigger_selective_elaboration

# ── REFACTORIZAR ──────────────────────────────────────────────────
  task_a14_main_concern:
-   # Actual: una sola llamada LLM sin critic ni HITL
+   # Nuevo: task_main_concern_pipeline(self, proyecto_id)
+   #   1. Ejecuta main_concern_proposer (PRO)
+   #   2. Ejecuta main_concern_critic (PRO)
+   #   3. GUARDA en hitl_decisions, NOTIFICA frontend, PAUSA
+   #   4. Retorna (el pipeline se reanuda cuando el investigador decide)

  task_a15_core_emergence:
-   # Actual: independiente, paralelo
+   # Nuevo: task_core_emergence_pipeline(self, proyecto_id)
+   #   Serial después de A1+A2. Mismo patrón Proposer→Critic→HITL.

  process_synthesis_agents_b:
-   # Actual: sin AbortableTask
+   # Nuevo: base=AbortableTask, bind=True
+   #   Agregar TaskStepCheckpoint para B1, B2, B2.5, B3
+   #   Al terminar: transicionar docs a 'sintetizado'

  task_a06_theoretical_sample:
-   # Actual: pre-emptive, se ejecuta al inicio
+   # Nuevo: se invoca solo bajo demanda dentro de core_saturation_loop
+   #   cuando did_state_expand=false por 3 iteraciones

# ── CREAR ─────────────────────────────────────────────────────────
+ selective_coding_coordinator(self, proyecto_id):
+   """Coordinator: despacha Fase A → B → C → D → E serialmente con HITL."""
+   # base=AbortableTask, bind=True
+   # Fase A: task_main_concern_pipeline → HITL → task_core_emergence_pipeline → HITL
+   # Fase B: task_selective_reduction_pipeline → HITL
+   # Fase C: task_core_saturation_loop → HITL por categoría
+   # Fase D: task_database_a_pipeline → HITL → task_database_b_pipeline → HITL
+   # Fase E: task_global_saturation_check → HITL → playground_ready

+ task_main_concern_pipeline(self, proyecto_id)
+ task_core_emergence_pipeline(self, proyecto_id)
+ task_selective_reduction_pipeline(self, proyecto_id)
+ task_core_saturation_loop(self, proyecto_id)
+ task_database_a_pipeline(self, proyecto_id)
+ task_database_b_pipeline(self, proyecto_id)
+ task_global_saturation_check(self, proyecto_id)
```

### Spillovers

- **`pipeline.py` L97-99**: `stage_name == "selective"` dispara `trigger_selective_elaboration`. Debe cambiar a disparar `selective_coding_coordinator`.
- **`pipeline.py` L87-93**: `stage_name == "main_concern"` dispara `a14_find_main_concern` directamente. Debe redirigir al coordinator o eliminarse (el coordinator lo maneja).
- **`invoke_graph` (L1453)**: Se usa desde `trigger_selective_elaboration`. Después del refactor, `invoke_graph` solo se usa para open coding individual (si acaso). El coordinator no depende de LangGraph.
- **Dependencia de `llm` global**: `task_a14_main_concern` usa `llm.run_agent()` del módulo. El coordinator necesitará acceso al mismo `llm` client.

---

## 4. `backend/app/models/domain/` — Análisis Detallado

### Lo que EXISTE ✅

| Archivo | Modelos | Estado |
|---------|---------|--------|
| `theory.py` | `TheoreticalCode`, `ConceptualRelationship`, `ElaborationMemo`, `EcosystemLayout`, `CategoryDefinitionVersion` | ✅ Completo |
| `canvas.py` | `LienzoDelPlanDeAnalisis`, `NodoDeLienzo`, `BordeDeLienzo` | ✅ Completo |
| `pipeline_run.py` | `PipelineRun`, `PipelineTask`, `TaskStepCheckpoint` | ✅ Completo |
| `project.py` | `Proyecto` | ⚠️ `estado` solo tiene "ACTIVO" |
| `document.py` | `Documento` | ⚠️ `estado` no incluye "sintetizado" |
| `enums.py` | `RolDeUsuario`, `TipoPlanSuscripcion`, `EstadoDeSaturacion`, `RecategorizationAction` | ✅ Completo |

### Lo que FALTA ❌

| Elemento | Gravedad | Detalle |
|----------|----------|--------|
| Modelo `HitlDecision` | 🔴 | No existe. Necesita tabla `hitl_decisions`. |
| `Proyecto.estado` sin valores pipeline | 🔴 | Solo "ACTIVO". Necesita: `collecting|coding|finding_cc|reducing|saturating|building_db|playground_ready|completed`. |
| `Documento.estado` sin "sintetizado" | 🟠 | El docstring L31-32 dice `crudo → segmentando → segmentado → procesando → listo → error`. Falta `sintetizado`. |

### Modificaciones necesarias

#### 4.1 Nuevo modelo: `backend/app/models/domain/hitl_decision.py`

```python
class HitlDecision(Base, TimestampMixin):
    __tablename__ = "hitl_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    gate_name: Mapped[str] = mapped_column(String(100))
    # "main_concern" | "core_emergence" | "selective_reduction"
    # | "core_saturation" | "database_a" | "database_b" | "global_saturation"

    proposal: Mapped[dict] = mapped_column(JSONB)        # output del proposer
    critic_verdict: Mapped[dict] = mapped_column(JSONB)  # output del critic

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # "pending" | "accepted" | "modified" | "rejected"

    researcher_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    researcher_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    researcher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

#### 4.2 Modificar `project.py`

```diff
- estado: Mapped[str] = mapped_column(String(50), default="ACTIVO")
+ estado: Mapped[str] = mapped_column(String(50), default="collecting")
  # "collecting" | "coding" | "finding_cc" | "reducing" |
  # "saturating" | "building_db" | "playground_ready" | "completed"
```

#### 4.3 Modificar `document.py`

```diff
  # En el docstring L31-32:
- crudo → segmentando → segmentado → procesando → listo → error
+ crudo → segmentando → segmentado → procesando → listo → sintetizado
+ (error puede ocurrir en cualquier etapa)
```

### Spillovers

- **Migración Alembic**: Nuevo modelo requiere `alembic revision --autogenerate -m "add_hitl_decisions"`.
- **`Proyecto.estado` default cambia**: El valor default `"ACTIVO"` → `"collecting"`. Código existente que verifique `estado == "ACTIVO"` debe actualizarse.
- **`Documento.estado`**: Agregar `sintetizado` no rompe nada existente porque es un valor nuevo. Pero `_maybe_trigger_phase_b` en `transitions.py` debe actualizarse para contar `sintetizado` en vez de `listo`.
- **Importación circular**: `project.py` importa de `canvas.py` y `theory.py` al final (L79-80). `hitl_decision.py` debe importarse de forma similar o manejarse con `TYPE_CHECKING`.

---

## 5. `backend/app/api/v1/` — Análisis Detallado

### `pipeline.py` — Estado actual

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 38-56 | `stage_name == "upload"` | ✅ |
| 58-62 | `stage_name == "precoding"` | ✅ |
| 64-76 | `stage_name == "open_coding"` | ✅ |
| 78-85 | `stage_name == "cross_doc"` | ✅ |
| 87-94 | `stage_name == "main_concern"` → `a14_find_main_concern` | ❌ Debe apuntar al coordinator |
| 96-103 | `stage_name == "selective"` → `trigger_selective_elaboration` | ❌ Debe apuntar al coordinator |
| 105-108 | `stage_name == "saturation"` | ⚠️ Placeholder |
| 116-200+ | `getPipelineLog` | ⚠️ No incluye nuevos estados |

### Modificaciones necesarias

```diff
# pipeline.py — Cambios requeridos

  elif stage_name == "main_concern":
-     task = celery_app.send_task("a14_find_main_concern", ...)
+     task = celery_app.send_task("selective_coding_coordinator",
+         args=[str(project_id), "main_concern"], ...)

  elif stage_name == "selective":
-     task = celery_app.send_task("trigger_selective_elaboration", ...)
+     task = celery_app.send_task("selective_coding_coordinator",
+         args=[str(project_id)], ...)

+ elif stage_name == "reduce":
+     task = celery_app.send_task("selective_coding_coordinator",
+         args=[str(project_id), "reduce"], ...)
+
+ elif stage_name == "saturate":
+     task = celery_app.send_task("selective_coding_coordinator",
+         args=[str(project_id), "saturate"], ...)
+
+ elif stage_name == "build_db":
+     task = celery_app.send_task("selective_coding_coordinator",
+         args=[str(project_id), "build_db"], ...)
```

### `projects.py` — Faltante

Se necesita un **nuevo endpoint o archivo `hitl.py`**:

```python
# Nuevo archivo: backend/app/api/v1/hitl.py

@router.post("/projects/{project_id}/hitl/{gate_name}/decide")
async def hitl_decide(project_id, gate_name, body: HitlDecisionRequest):
    """ACCEPT → avanzar pipeline, MODIFY → re-ejecutar, REJECT → archivar."""

@router.get("/projects/{project_id}/hitl/pending")
async def hitl_pending(project_id):
    """Devuelve decisiones pendientes para el frontend."""
```

### `events.py` — Extensión necesaria

```diff
# events.py — Ya tiene SSE + publish_event. Solo agregar tipo de evento.

  def publish_event(proyecto_id, event_type, data):
      ...
+ # Los workers llamarán:
+ publish_event(pid, "hitl_required", {"gate": "main_concern", ...})
```

### Spillovers

- **`main.py`**: Debe registrar el nuevo router `hitl.py`.
- **Frontend API client** (`frontend/src/api/client.ts`): Necesita nuevas funciones `decideHitl()` y `getPendingHitl()`.
- **`getPipelineLog`**: Debe reflejar los nuevos estados `sintetizado`, `finding_cc`, etc.

---

## 6. `backend/app/services/` — Análisis Detallado

### Estado: ✅ ALTAMENTE ALINEADO

| Archivo | Clase/Función | Estado | Nota |
|---------|--------------|--------|------|
| `elaboration_engine.py` | `ElaborationEngine` | ✅ | `elaborate_relationship()`, `elaborate_divergence()`, `absorb_ghost_blob()`, `_get_lens_instruction()` — todo implementado |
| `selective_elaborator.py` | `SelectiveElaborator` | ✅ | `elaborate_incident()`, `get_category_evolution()` — listo para saturation loop |
| `emergent_sampler.py` | `EmergentSampler` | ✅ | `detect_emergent_dimensions()`, `sample_for_property_extreme()` — reemplazo del viejo TheoSampler |
| `ghost_connector.py` | `GhostConnector` | ✅ | `generate_ghost_blobs()`, `absorb_ghost()` |
| `rename_detector.py` | `RenameDetector` | ✅ | `get_rename_candidates()`, `should_suggest_rename()` |
| `recommendation_engine.py` | `RecommendationEngine` | ✅ | 5 dimensiones de recomendación |
| `saturation_gap_analyzer.py` | `SaturationGapAnalyzer` | ✅ | `full_analysis()` con 4 fuentes de gap |
| `theory_seeder.py` | `seed_theoretical_codes()` | ✅ | 12 códigos built-in |
| `pipeline_orchestrator.py` | — | ⚠️ | ¿Existe pero no se usa en el pipeline principal? |

### Cambios necesarios en services: **NINGUNO**

Los services existentes ya implementan las capacidades que el pipeline selectivo y el playground necesitan. Solo hay que **conectarlos** desde el `selective_coding_coordinator` y desde los endpoints del Playground.

---

## 7. `backend/app/prompts/` — Análisis Detallado

### Estado: ❌ INCOMPLETO

| Prompt | Archivo | Estado |
|--------|---------|--------|
| `batch_coder_producer` | `prompts/pro/batch_coder_producer.md` | ✅ |
| `batch_coder_critic` | `prompts/pro/batch_coder_critic.md` | ✅ |
| `map_synthesis` | `prompts/pro/map_synthesis.md` | ✅ |
| `reduce_synthesis` | `prompts/pro/reduce_synthesis.md` | ✅ |
| `core_concern_finder` | `prompts/pro/core_concern_finder.md` | ✅ (legacy, será reemplazado) |
| `hypothesis_generation` | `prompts/pro/hypothesis_generation.md` | ✅ |
| `final_report` | `prompts/pro/final_report.md` | ✅ |
| `main_concern_proposer` | — | ❌ **CREAR** |
| `main_concern_critic` | — | ❌ **CREAR** |
| `core_emergence_proposer` | — | ❌ **CREAR** |
| `core_emergence_critic` | — | ❌ **CREAR** |
| `selective_reduction_proposer` | — | ❌ **CREAR** |
| `selective_reduction_critic` | — | ❌ **CREAR** |
| `core_saturation_proposer` | — | ❌ **CREAR** |
| `core_saturation_critic` | — | ❌ **CREAR** |
| `database_a_proposer` | — | ❌ **CREAR** |
| `database_a_critic` | — | ❌ **CREAR** |
| `database_b_proposer` | — | ❌ **CREAR** |
| `database_b_critic` | — | ❌ **CREAR** |

### Plantilla de contrato (según Patrón §6.4)

Cada nuevo prompt debe seguir:

```markdown
---
prompt_id: main_concern_proposer
version: 1.0.0
model_profile: pro
description: Identifica la principal preocupación latente compartida por los participantes.
langgraph_node: null
execution_order: "Fase A — Paso A1"
input_state: all_codes, all_memos, prime_movers_per_document
output_state: main_concern, confidence, recurring_problems, relevant_population_dimensions
depends_on: null
prerequisite_for: main_concern_critic
agent_id: A14
triggers_on: "Proyecto en estado 'finding_cc' con sub-estado 'proposing_mc'"
note: "PRO porque requiere sensibilidad teórica y juicio cualitativo."
---

## System
[ROL] ...
[OBJETIVO] ...
[RESTRICCIONES] ...

## User
[SECCIÓN DE DATOS]
{all_codes}
{all_memos}
{prime_movers_per_document}

## Output Schema
```json
{...}
```
```

---

## 8. `frontend/` — Análisis Detallado

### Estado: ⚠️ PARCIAL

| Componente | Archivo | Estado |
|-----------|---------|--------|
| `Project.tsx` | `frontend/src/pages/Project.tsx` | ⚠️ Pipeline stages antiguos |
| `Playground.tsx` | `frontend/src/pages/Playground.tsx` | ✅ Layout completo |
| `EcosystemCanvas` | `components/theory/EcosystemCanvas.tsx` | ✅ |
| `ElaborationPanel` | `components/theory/ElaborationPanel.tsx` | ✅ |
| `RecommendationGuide` | `components/theory/RecommendationGuide.tsx` | ✅ |
| `RenameModal` | `components/theory/RenameModal.tsx` | ✅ |
| `GhostBlob` | `components/theory/GhostBlob.tsx` | ✅ |
| `CategoryBlob` | `components/theory/CategoryBlob.tsx` | ✅ |
| `RelationshipTendril` | `components/theory/RelationshipTendril.tsx` | ✅ |
| `PlaygroundContext` | `components/theory/PlaygroundContext.tsx` | ✅ |
| `CategoryEvolutionPanel` | `components/selective/CategoryEvolutionPanel.tsx` | ✅ |
| **HITLModal** | — | ❌ **CREAR** |

### Cambios necesarios

#### 8.1 `frontend/src/pages/Project.tsx` — PIPELINE_STAGES

```diff
  const PIPELINE_STAGES: StageDef[] = [
-   { key: "workers", icon: "🚀", label: "Iniciando workers" },
    { key: "segment", icon: "✂️", label: "Segmentación" },
-   { key: "agents", icon: "🧠", label: "Codificación abierta (agentes IA)" },
-   { key: "categories", icon: "🏷️", label: "Categorización" },
-   { key: "done", icon: "✅", label: "Pipeline completado" },
+   { key: "agents", icon: "🧠", label: "Open Coding (Agentes A)" },
+   { key: "synthesis", icon: "🔗", label: "Síntesis Cross-Doc (Phase B)" },
+   { key: "find_cc", icon: "🎯", label: "Core Category Detection" },
+   { key: "reduce", icon: "✂️", label: "Selective Reduction" },
+   { key: "saturate", icon: "🔄", label: "Core Saturation" },
+   { key: "build_db", icon: "🗄️", label: "Database A/B" },
+   { key: "playground", icon: "🎨", label: "Theoretical Playground" },
  ];
```

Este cambio requiere también actualizar toda la lógica de `stageStatuses` en el mismo archivo para mapear los nuevos keys a los datos reales del pipeline (estado del proyecto, conteos, etc.).

#### 8.2 `frontend/src/components/HITLModal.tsx` — NUEVO

```tsx
// Componente modal que muestra:
// - Nombre del gate (main_concern, core_emergence, etc.)
// - Propuesta del Proposer (formateada)
// - Veredicto del Critic (SAT/MOD/FORCED con rationale)
// - Botones: ACCEPT | MODIFY (con campo de texto) | REJECT (con nota)
// - Llama a POST /api/v1/projects/{id}/hitl/{gate}/decide
```

#### 8.3 `frontend/src/api/client.ts` — Nuevas funciones

```typescript
// Funciones a agregar:
decideHitl(projectId: string, gateName: string, decision: HitlDecision): Promise<void>
getPendingHitl(projectId: string): Promise<HitlPending[]>
```

---

## 9. Matriz de Spillovers (Efectos en Cascada)

| Acción | Archivos afectados directamente | Archivos afectados indirectamente |
|--------|-------------------------------|----------------------------------|
| **Eliminar `trigger_selective_elaboration`** | `workers/heavy/tasks.py` L1399-1440 | `pipeline.py` L97-99, cualquier test que lo invoques |
| **Separar open/selective en workflow.py** | `workflow.py` (reducir grafo) | `invoke_graph()` en `tasks.py`, `node_find_core_concern` |
| **Agregar `HitlDecision` model** | `models/domain/hitl_decision.py` (nuevo), `project.py` | `alembic/versions/`, `main.py` (import), `api/v1/hitl.py` (nuevo router) |
| **Agregar `sintetizado` a doc.estado** | `document.py` L29-32 | `transitions.py` NEXT dict, `_maybe_trigger_phase_b` query, `pipeline.py` getPipelineLog |
| **Cambiar `Proyecto.estado` default** | `project.py` L24 | Cualquier código que verifique `estado == "ACTIVO"`, seeders, tests |
| **Agregar `transition_project()`** | `transitions.py` | `selective_coding_coordinator` (tasks.py), `pipeline.py` |
| **Crear `selective_coding_coordinator`** | `workers/heavy/tasks.py` (nuevo) | `pipeline.py` stages, `events.py` (publica eventos de progreso) |
| **Mover TheoSampler a reactivo** | `tasks.py` task_a06 | `emergent_sampler.py` (ya existe), `selective_coding_coordinator` |
| **Crear 12 prompts nuevos** | `prompts/pro/*.md` (8), `prompts/flash/*.md` (4) | `prompts/loader.py` (si requiere registro), `core/llm_config.py` PROMPT_TIER_MAP |
| **Cambiar PIPELINE_STAGES en frontend** | `Project.tsx` L44-50 | Cualquier componente que lea `stageStatuses` keys |
| **Crear HITLModal** | `components/HITLModal.tsx` (nuevo) | `Project.tsx` (integración), `client.ts` (nuevas funciones API) |
| **Agregar endpoint HITL** | `api/v1/hitl.py` (nuevo) | `main.py` (registro router), `projects.py` o nuevo archivo |

---

## 10. Riesgos Identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|--------|------------|
| **Romper el pipeline actual al eliminar `trigger_selective_elaboration`** | Alta | Medio | E0 es deliberadamente destructiva. El frontend mostrará "selective" como no disponible hasta que E2 implemente el coordinator. |
| **Migración de `Proyecto.estado` rompe datos existentes** | Media | Alto | Usar migración con valor default `collecting`. Proyectos existentes en "ACTIVO" se migran a "collecting". |
| **Dependencia circular `transitions.py` ↔ `tasks.py`** | Media | Medio | El coordinator llama a `transition_project()`; `transition_project()` no debe importar tareas. |
| **SSE HITL no funciona sin Redis** | Baja | Medio | El endpoint SSE ya tiene fallback (heartbeat sin Redis). El polling vía `GET /hitl/pending` sirve como backup. |
| **12 prompts nuevos requieren ajuste iterativo** | Alta | Bajo | Los prompts son el componente más fácil de iterar. Se crean con el contrato mínimo y se refinan con uso. |
| **El coordinator es una tarea Celery de larga duración** | Media | Alto | Con gates HITL, el coordinator puede estar vivo días. Usar `task_step_checkpoints` y `soft_time_limit` generoso (o ilimitado con `time_limit=None`). |
| **`invoke_graph()` se rompe al reducir el grafo** | Media | Medio | Solo se usa para open coding. Reducir el grafo a solo nodos open coding mantiene su funcionalidad intacta. |

---

## 11. Orden de Ejecución Recomendado (Validado contra Spillovers)

```
Paso 1: models/domain/hitl_decision.py (nuevo) + migración
        → Sin dependencias. Nadie lo importa aún.

Paso 2: project.py (cambiar default estado) + document.py (agregar 'sintetizado')
        → Sin dependencias críticas. Migración incluida.

Paso 3: agents/transitions.py (agregar 'sintetizado', hitl_gate, transition_project)
        → Depende de paso 1 (HitlDecision) y paso 2 (nuevo default estado).

Paso 4: api/v1/hitl.py (nuevo router) + extender events.py
        → Depende de paso 1 (modelo). Usa transition_project del paso 3.

Paso 5: prompts/ (12 nuevos archivos .md)
        → Sin dependencias de código. Se pueden crear en paralelo.

Paso 6: workflow.py (reducir grafo a solo open coding)
        → Depende de paso 5 conceptualmente (los nodos extraídos van al coordinator).

Paso 7: workers/heavy/tasks.py (eliminar trigger_selective, crear coordinator + 6 pipelines)
        → Depende de pasos 1-6.

Paso 8: api/v1/pipeline.py (actualizar stages)
        → Depende de paso 7 (nuevos task names).

Paso 9: frontend/ (HITLModal + actualizar PIPELINE_STAGES + client.ts)
        → Depende de paso 4 (endpoint HITL) y paso 8 (stages).
```

---

## 12. Notas Finales

1. **Los services NO necesitan cambios.** `ElaborationEngine`, `SelectiveElaborator`, `EmergentSampler`, `GhostConnector`, `RenameDetector`, `RecommendationEngine`, `SaturationGapAnalyzer`, `TheorySeeder` ya están implementados y cumplen el contrato metodológico.

2. **El frontend del Playground YA EXISTE.** `PlaygroundPage`, `EcosystemCanvas`, `ElaborationPanel`, `RecommendationGuide`, `RenameModal`, `GhostBlob`, `CategoryBlob`, `RelationshipTendril`, `PlaygroundContext`, `CategoryEvolutionPanel` están implementados. Solo falta el `HITLModal`.

3. **El SSE YA EXISTE.** `events.py` tiene `publish_event()` y `stream_events()`. Solo hay que agregar el tipo de evento `hitl_required` y publicarlo desde los workers.

4. **La arquitectura de transiciones YA CUMPLE R1-R5.** `transitions.py` tiene optimistic locking, PipelineTask tracking, y AbortableTask. Solo hay que extenderlo a nivel proyecto y agregar el gate HITL.

5. **El cambio más disruptivo es eliminar `trigger_selective_elaboration` y dividir el grafo de LangGraph.** Esto dejará el pipeline selectivo inoperativo hasta que el `selective_coding_coordinator` esté completo. Es aceptable porque el pipeline actual ya es metodológicamente incorrecto.
