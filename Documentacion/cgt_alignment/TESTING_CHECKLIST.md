# TESTING CHECKLIST — CGT Refactor Debugging

> **Organizado por orden de pipeline (secuencia_cgt.mermaid).**
>
> Leyenda: 🤖 = Agente IA puede ejecutar | 👤 = Investigador debe ejecutar

---

## 0. Infraestructura Base

| # | Test | Quién | Comando / Verificación | Estado |
|---|------|-------|----------------------|--------|
| T0.1 | Todos los .py compilan (syntax check) | 🤖 | `find workers/ -name '*.py' ...` | ✅ 28/28 |
| T0.2 | Modelos SQLAlchemy cargan sin errores | 🤖 | `Base.metadata.tables` | ✅ 41 tablas |
| T0.3 | Migración Alembic está en head | 👤 | `cd backend && alembic current` | ✅ |
| T0.4 | Docker containers arrancan | 👤 | `docker compose up -d && docker compose ps` | ✅ |
| T0.5 | PostgreSQL acepta conexiones | 👤 | `docker compose exec postgres pg_isready` | ✅ |
| T0.6 | Redis responde | 👤 | `docker compose exec redis redis-cli ping` | ✅ |
| T0.7 | TEI embedding server responde | 👤 | `curl http://localhost:8080/health` | ✅ |
| T0.8 | MinIO accesible | 👤 | `curl http://localhost:9001` | ✅ |
| T0.9 | Seed de códigos teóricos funciona | 👤 | `seed_theoretical_codes()` → 12 built-in | ✅ |
| T0.10 | Prompts se cargan sin errores | 🤖 | `PROMPT_REGISTRY` → 68 | ✅ 68 prompts, 29/29 AGENTES.md |
| T0.11 | Schemas Pydantic para tablas nuevas | 🤖 | `response_schema()` para 5 modelos | ✅ 5/5 schemas |

---

## 1. Fase 0: Configuración del Proyecto

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T1.1 | `POST /projects` crea proyecto con `supuesto_poblacional` | 👤 | Verificar que `population_assumption` JSONB se llena automáticamente | ✅ |
| T1.2 | `population_generalizer` se ejecuta (FLASH) | 👤 | Logs deben mostrar "population_generalizer: project=X spatial=Y temporal=Z" | ✅ spatial=sparse, temporal=present_continuous |
| T1.3 | `population_generalizer` falla gracefully sin API key | 👤 | Proyecto se crea igual, sin `generalized_population` | ✅ |
| T1.4 | `object_of_study` default es "concern" | 🤖 | Columna `proyectos.object_of_study` tiene default en BD | ✅ |
| T1.5 | `coding_style_instruction` es nullable | 🤖 | Columna existe, nullable=True | ✅ |
| T1.6 | `GET /projects/{id}` incluye `object_of_study` | 👤 | Response JSON incluye el campo | ✅ |

---

## 2. Fase A: Open Coding (por documento)

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T2.1 | Upload de documento (PDF/TXT) funciona | 👤 | `POST /projects/{id}/documents` → 201 | ✅ test_entrevista.txt |
| T2.2 | `segmentar_documento` (NLP worker) segmenta y persiste | 👤 | `GET /projects/{id}/documents/{did}/segments` → segmentos con embeddings | ✅ 18 segmentos |
| T2.3 | `glaser_data_classifier` clasifica segmentos (⚙️ capa 1) | 👤 | `segmentos.tipo_dato_glaser` poblado con baseline_data/properline_data/etc | ✅ 18/18 clasificados |
| T2.4 | `glaser_data_classifier` fallback FLASH para borderline | 👤 | Logs muestran "Agent glaser_data_classifier → tier=FLASH" para confidence < 0.7 | ✅ FLASH calls activas |
| T2.5 | `extract_incident` (FLASH) extrae jots de segmentos baseline | 👤 | `extracted_incidents` se llena. `jot_text` es gerundio. | ✅ 63 incidentes, 5 docs |
| T2.6 | `extract_incident` aplica 4 preguntas de Glaser | 👤 | `preguntas_glaser_json` tiene 4 keys | ✅ |
| T2.7 | `extract_core_pattern` (PRO) sintetiza patrón por documento | 👤 | `document_processes` actualizado con core_pattern | ✅ "Negociando la agencia creativa..." |
| T2.8 | `a1_build_population_context` actualiza cada 3 docs | 👤 | `population_contexts.version` se incrementa | ✅ v1 creado |
| T2.9 | `a2_identify_process` identifica proceso por documento | 👤 | `document_processes.process_description` poblado | ✅ + prime_mover HIGH |
| T2.10 | `process_document_agents_a` usa AbortableTask | 🤖 | Decorador `base=AbortableTask` presente en código | ✅ |
| T2.11 | `process_document_agents_a` ejecuta pipeline A1→A2→A3 completo | 👤 | 1 doc → A1+A2. 3+ docs → A1+A2+A3. | ✅ A1+A2 OK (1 doc) |

---

## 3. Fase B: Síntesis Cross-Document

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T3.1 | `b1_compare_incidents` (PRO) compara incidentes SIN ver categorías | 👤 | `incident_comparisons` poblado. El código NO pasa `categorias` al LLM. | ⬜ |
| T3.2 | `b1_compare_incidents` incremental funciona | 👤 | Segunda ejecución solo compara nuevos incidentes | ⬜ |
| T3.3 | `b2_label_groups` (PRO + SelfRefinement) etiqueta grupos | 👤 | `incident_groups.label` y `.definition` se llenan | ⬜ |
| T3.4 | `b2_label_groups` loop B2↔B3 máx 3 iteraciones | 👤 | Logs muestran "SelfRefinement iteration X/3" | ⬜ |
| T3.5 | `b3_critique_labels` (FLASH) emite SAT/MOD/FORCED | 👤 | `incident_groups.critic_verdict` tiene verdict | ⬜ |
| T3.6 | `process_synthesis_agents_b` ejecuta B1→B2→B2.5→B3 en secuencia | 👤 | Pipeline log muestra el orden correcto | ⬜ |
| T3.7 | `process_synthesis_agents_b` usa AbortableTask | 🤖 | Decorador presente | ⬜ |
| T3.8 | Legacy `b1_distill_sampling` emite DeprecationWarning | 👤 | Si se invoca, redirect a b1_compare_incidents | ⬜ |
| T3.9 | Legacy `b2_open_code` emite DeprecationWarning | 👤 | Si se invoca, redirect a b2_label_groups | ⬜ |

---

## 4. Fase 5b-A: Core Category Detection

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T4.1 | `maturity_gate()` se ejecuta antes de selective coding | 👤 | Pipeline log muestra "maturity gate" | ⬜ |
| T4.2 | `maturity_gate()` bloquea si <3 cats saturadas | 👤 | Proyecto se pausa en "checking_maturity" | ⬜ |
| T4.3 | `task_main_concern_pipeline` propone patrón de interés | 👤 | HITL gate con candidatos en gerundio | ⬜ |
| T4.4 | `task_main_concern_pipeline` usa AbortableTask | 🤖 | `base=AbortableTask` en decorador | ⬜ |
| T4.5 | `task_core_emergence_pipeline` evalúa centralidad | 👤 | HITL gate con candidates y centrality scores | ⬜ |
| T4.6 | `task_core_emergence_pipeline` usa AbortableTask | 🤖 | `base=AbortableTask` en decorador | ⬜ |
| T4.7 | `selective_coding_coordinator` orquesta fases A→B→C→D→E | 👤 | Estados de proyecto transicionan correctamente | ⬜ |
| T4.8 | `selective_coding_coordinator` crea PipelineTask tracking | 👤 | `pipeline_tasks` tiene fila con `document_id=NULL` | ⬜ |

---

## 5. Fase 5b-B: Selective Reduction

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T5.1 | `task_selective_reduction_pipeline` filtra y fusiona categorías | 👤 | HITL gate con kept/merged/discarded | ⬜ |
| T5.2 | `task_selective_reduction_pipeline` usa AbortableTask | 🤖 | `base=AbortableTask` en decorador | ⬜ |

---

## 6. Fase 5b-C: Core Saturation Loop (Panel de 4 Señales)

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T6.1 | Señal matemática (rolling_std) se consulta primero | 👤 | SQL query a `saturation_metrics` antes de LLM | ⬜ |
| T6.2 | Señal cualitativa (paradigm window 5) se consulta | 👤 | SQL query a `paradigm_states` | ⬜ |
| T6.3 | Señal cobertura (paradigm_snapshot props) se calcula | 👤 | JSONB parse de `paradigm_snapshot` | ⬜ |
| T6.4 | Señal integración (conceptual_relationships count) | 👤 | SQL COUNT con `category_ids @>` | ⬜ |
| T6.5 | LLM se salta si las 4 señales no son estables | 👤 | Log muestra "llm_skipped: true" | ⬜ |
| T6.6 | `saturation_panel_json` se actualiza en `categorias` | 👤 | Columna JSONB poblada con 4 señales | ⬜ |
| T6.7 | `GET /projects/{id}/saturation-panel` devuelve panel | 👤 | Endpoint F5.2 responde con 4 señales por categoría | ⬜ |
| T6.8 | TheoSampler se activa solo si stable_since ≥ 3 + cobertura < 80% | 👤 | Log muestra "TheoSampler activated" condicionalmente | ⬜ |
| T6.9 | MemoMaker se dispara al saturar categoría | 👤 | `memos` tiene fila con `structured_fields` después de saturar | ⬜ |
| T6.10 | `task_core_saturation_loop` abort check entre iteraciones | 👤 | Si se cancela, `pipeline_tasks.status='cancelled'` | ⬜ |

---

## 7. Fase 5b-D: Database A/B

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T7.1 | `task_database_a_pipeline` persiste nodos SIEMPRE | 👤 | `database_nodes` tiene filas incluso con critic != SAT | ⬜ |
| T7.2 | `task_database_b_pipeline` persiste edges SIEMPRE | 👤 | `database_edges` tiene filas incluso con critic != SAT | ⬜ |

---

## 8. Fase 6b: Theoretical Playground

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T8.1 | `GET /projects/{id}/theory` carga ecosistema | 👤 | Blobs + tendrils + ghosts en response | ⬜ |
| T8.2 | `conceptual_elaborator` propone relaciones | 👤 | POST elaboration → `conceptual_relationships` nueva fila | ⬜ |
| T8.3 | `ghost_blob_mapper` absorbe memos huérfanos | 👤 | Memo vinculado a categoría | ⬜ |
| T8.4 | `memo_theoretical_tagger` (FLASH) clasifica memos | 👤 | `memo_sorting_attempts` poblado con family affinities | ⬜ |

---

## 9. Fase 6a: Redacción Natural

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T9.1 | `natural_writer` (PRO) redacta desde memos | 👤 | `write_section` retorna draft + citations + concepts | ⬜ |
| T9.2 | `writing_critic` (PRO) evalúa borrador | 👤 | Issues detectados: tense, subject, citation, fidelity, abstraction | ⬜ |
| T9.3 | `gap_feeler` (FLASH) detecta huecos en background | 👤 | Gaps detectados sin bloquear escritura | ⬜ |

---

## 10. Fase 6c: Diálogo con Literatura

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T10.1 | `literature_comparer` (PRO) produce tabla Extiende/Modifica/Integra/Trasciende | 👤 | Tabla con 4 columnas por categoría | ⬜ |
| T10.2 | `literature_critic` (PRO) detecta forcing/authority bias | 👤 | Issues[] en response | ⬜ |

---

## 11. Fase 6d: Aplicabilidad

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T11.1 | `applicability_engine` (PRO) identifica variables control/acceso | 👤 | `control_variables[]` + `access_variables[]` poblados | ⬜ |
| T11.2 | `applicability_critic` (PRO) evalúa genuinidad | 👤 | Issues[] detecta generic/no_limits/jargon | ⬜ |

---

## 12. Transversales: HITL, Modificaciones, ReSpec

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T12.1 | `HITLModal` muestra "Patrón de Interés" (F1.1) | 👤 | Label en frontend, no "Main Concern Detection" | ⬜ |
| T12.2 | `PIPELINE_STAGES` incluye "Verificando madurez" | 👤 | Stage 🔍 entre synthesis y find_cc | ⬜ |
| T12.3 | `hitl_gate()` crea `hitl_decisions` y publica Redis | 👤 | Redis `PUBLISH project:{id}:events` con type=hitl_required | ⬜ |
| T12.4 | `transition_project()` publica Redis en cambio de estado | 👤 | Redis event con type=project_state_changed | ⬜ |
| T12.5 | `POST /modification/apply` aplica modificación HITL | 👤 | HITLModificationAgent P5: filter → plan → execute → evaluate | ⬜ |
| T12.6 | `evaluate_respec_signals` detecta 5 tipos de señales | 👤 | ambiguous_incidents, rejected_labels, unresolved_divergence, orphan_memos, empty_axes | ⬜ |
| T12.7 | `query_lower_level` baja de categoría → incidentes | 👤 | Retorna incidentes vinculados a la categoría | ⬜ |
| T12.8 | `query_lower_level` baja de relación → categorías | 👤 | Retorna category_ids + converging/diverging | ⬜ |
| T12.9 | PipelineTask tracking existe para tareas de proyecto | 👤 | `pipeline_tasks` con `document_id=NULL` para selective_coding_coordinator | ⬜ |
| T12.10 | `AbortableTask.on_failure` marca pipeline_tasks como failed | 👤 | Si una tarea falla, `pipeline_tasks.status='failed'` | ⬜ |

---

## 13. Regresiones: Lo que YA funcionaba y debe seguir funcionando

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T13.1 | Login/Register funciona | 👤 | `POST /auth/login` → JWT token | ⬜ |
| T13.2 | Listar/Crear proyectos funciona | 👤 | `GET /projects`, `POST /projects` | ⬜ |
| T13.3 | Upload de documentos (PDF, DOCX, TXT) funciona | 👤 | `POST /projects/{id}/documents` | ⬜ |
| T13.4 | `punctuate_text` (Fast worker) funciona | 👤 | Texto con puntuación agregada | ⬜ |
| T13.5 | `extract_graph_entities` (Fast worker) funciona | 👤 | `graph_entities` + `graph_relations` poblados | ⬜ |
| T13.6 | `a06_theoretical_sample` (TheoSampler) funciona | 👤 | Muestreo teórico con ANTI-JOIN | ⬜ |
| T13.7 | `a07_build_evidence_map` funciona | 👤 | Mapa de evidencia categoría × documento | ⬜ |
| T13.8 | `task_global_saturation_check` funciona | 👤 | Verificación de 3 condiciones globales | ⬜ |
| T13.9 | `_prepare_playground_for_project` funciona | 👤 | Seeding + ghost mapping + gap detection | ⬜ |
| T13.10 | Frontend Pipeline log streaming funciona | 👤 | Logs en tiempo real en Project.tsx | ⬜ |

---


---

## 14. Frontend UX: Pipeline Completo

> **Recorrido del investigador:** desde que crea un proyecto hasta que ve el Theoretical Playground.

### 14.1 Navegacion y Autenticacion

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.1 | Login renderiza formulario | 👤 | Campos email + password + boton | ⬜ |
| T14.2 | Register crea cuenta | 👤 | Redirige a /login tras registro | ⬜ |
| T14.3 | Logout limpia token y redirige | 👤 | No accede a /projects sin token | ⬜ |
| T14.4 | Ruta desconocida → /login | 👤 |  →  | ⬜ |

### 14.2 Proyectos

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.5 | Lista de proyectos | 👤 | Cards con nombre, estado, num_documentos | ⬜ |
| T14.6 | Crear proyecto aparece en lista | 👤 | Nuevo proyecto visible sin recargar | ⬜ |
| T14.7 | Formulario incluye supuesto_poblacional | 👤 | Textarea para descripcion de poblacion | ⬜ |
| T14.8 | Click en proyecto → ProjectDetail | 👤 | URL cambia a /projects/{id} | ⬜ |

### 14.3 Pipeline — Project Detail

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.9 | 9 stages en orden correcto | 👤 | Segmentacion → Open Coding → Sintesis → Verificando madurez → Patron de Interes → Selective Reduction → Core Saturation → Database A/B → Playground | ⬜ |
| T14.10 | Stage status cambia con progreso | 👤 | pending (gris) → running (azul spinner) → done (verde) → error (rojo) | ⬜ |
| T14.11 | Boton Ejecutar Pipeline condicional | 👤 | Deshabilitado si no hay documentos | ⬜ |
| T14.12 | Boton Detener Workers cancela tareas | 👤 | Workers reciben SIGTERM → stages marcan error | ⬜ |
| T14.13 | Panel de logs streaming tiempo real | 👤 | Timestamp, autoscroll, colores por nivel | ⬜ |
| T14.14 | Upload documento muestra progress | 👤 | File input → progress → doc en lista | ⬜ |
| T14.15 | Documentos muestran estado | 👤 | Badge color: crudo/segmentado/listo/etc | ⬜ |
| T14.16 | Expandir doc muestra segmentos+codigos | 👤 | Lista de segmentos con codigos asignados | ⬜ |
| T14.17 | Toggle vista original vs segmentada | 👤 | Cambia entre texto crudo y segmentos | ⬜ |

### 14.4 HITL Gates (modales)

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.18 | Modal HITL aparece en gates | 👤 | Propuesta del agente + critic verdict | ⬜ |
| T14.19 | Modal muestra Patron de Interes | 👤 | Label F1.1 aplicado, no Main Concern | ⬜ |
| T14.20 | Botones Accept/Modify/Reject | 👤 | POST /hitl/{gate}/decide → pipeline avanza | ⬜ |
| T14.21 | Modify abre textarea feedback | 👤 | Campo texto + boton enviar | ⬜ |
| T14.22 | Modal muestra evidencia | 👤 | Incidentes, scores, rationale | ⬜ |

### 14.5 Theoretical Playground

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.23 | Canvas: blobs + tendrils | 👤 | Nodos y conexiones, colores por capa | ⬜ |
| T14.24 | Click blob → panel detalle | 👤 | Nombre, definicion, saturation_panel | ⬜ |
| T14.25 | Drag & drop blobs persiste | 👤 | Posiciones se guardan | ⬜ |
| T14.26 | Panel Recommendations muestra gaps | 👤 | Lista con severidad critico/warning | ⬜ |
| T14.27 | Boton Sync gaps refresca | 👤 | POST /analysis/saturation-gaps/refresh | ⬜ |
| T14.28 | Banner N docs nuevos | 👤 | Banner purpura + link Expandir analisis | ⬜ |
| T14.29 | RenameModal sugiere nombres IA | 👤 | Modal con sugerencias de renombre | ⬜ |
| T14.30 | Panel historial de cambios | 👤 | Timeline versiones con triggers | ⬜ |

### 14.6 Estados y Edge Cases

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.31 | Proyecto sin documentos | 👤 | Mensaje: No hay documentos | ⬜ |
| T14.32 | Pipeline en error | 👤 | Stage rojo + boton Reintentar | ⬜ |
| T14.33 | Pipeline cancelado limpia estado | 👤 | Stages vuelven, sin tareas huerfanas | ⬜ |
| T14.34 | Refrescar pagina mantiene estado | 👤 | Polling recupera, no empieza de cero | ⬜ |
| T14.35 | Navegar proyectos no mezcla estados | 👤 | Pipeline del proyecto correcto | ⬜ |


## Resumen

| Sección | Tests | 🤖 Agente | 👤 Investigador |
|---------|-------|-----------|----------------|
| 0. Infraestructura | 11 | 4 | 7 |
| 1. Fase 0: Configuración | 6 | 2 | 4 |
| 2. Fase A: Open Coding | 11 | 1 | 10 |
| 3. Fase B: Síntesis | 9 | 1 | 8 |
| 4. Fase 5b-A: Core Category | 8 | 3 | 5 |
| 5. Fase 5b-B: Reduction | 2 | 1 | 1 |
| 6. Fase 5b-C: Saturation | 10 | 0 | 10 |
| 7. Fase 5b-D: Database | 2 | 0 | 2 |
| 8. Fase 6b: Playground | 4 | 0 | 4 |
| 9. Fase 6a: Redacción | 3 | 0 | 3 |
| 10. Fase 6c: Literatura | 2 | 0 | 2 |
| 11. Fase 6d: Aplicabilidad | 2 | 0 | 2 |
| 12. Transversales | 10 | 0 | 10 |
| 13. Regresiones | 10 | 0 | 10 |
| 14. Frontend UX Pipeline | 35 | 0 | 35 |
| **TOTAL** | **125** | **12** | **113** |
