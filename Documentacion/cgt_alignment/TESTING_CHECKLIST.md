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
| T0.10 | Prompts se cargan sin errores | 🤖 | `PROMPT_REGISTRY` → 70 | ✅ 70 prompts, naming prefijado (fa_, fb_, fc_, ...) |
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

### 1.1 Processing Verb System

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T1.1.1 | Crear proyecto con `processing_verb="resolver"` | 👤 | Verificar que `population_assumption.processing_verb` = "resolver" | ⬜ |
| T1.1.2 | Crear proyecto con `processing_verb="negociar"` | 👤 | Verificar `population_assumption.processing_gerund` = "negociando" | ⬜ |
| T1.1.3 | spaCy conjugation: population="recicladores" + verb="resolver" | 🤖 | `processing_verb_conjugated` = "resuelven" | ⬜ |
| T1.1.4 | spaCy conjugation: English population + English verb | 🤖 | No conjugation applied | ⬜ |
| T1.1.5 | Nemotrón genera RQ con `{processing_verb}` inyectado | 👤 | RQ contiene el verbo correcto | ⬜ |
| T1.1.6 | Nemotrón critic evalúa RQ+OQ | 👤 | Verdict SAT\|MOD\|FORCED en `population_assumption` | ⬜ |
| T1.1.7 | population_generalizer fuerza plural | 👤 | "un salón de clases" → "docentes y estudiantes" | ⬜ |
| T1.1.8 | Frontend hints dinámicos: cambiar object_of_study | 👤 | Hint cambia según tipo seleccionado | ⬜ |
| T1.1.9 | Frontend RQ preview: llenar población + verbo | 👤 | Preview se actualiza en vivo | ⬜ |
| T1.1.10 | `generalize_population` endpoint re-runs generalizer | 👤 | POST .../generalize → `population_assumption` actualizado | ⬜ |
| T1.1.11 | spaCy singular detection: "una escuela" → warning | 🤖 | `population_warning` en `population_assumption` | ⬜ |
| T1.1.12 | Nemotrón OQ es SINGULAR ("their concern", no "concerns") | 👤 | OQ no contiene plural del patrón | ⬜ |
| T1.1.13 | Processing verb defaults: cambiar concern→emotion → default cambia a "regulate" | 👤 | Frontend actualiza default del verbo al cambiar tipo | ⬜ |
| T1.1.14 | `processing_verb_conjugated` se persiste en `population_assumption` | 👤 | Crear proyecto → verificar campo en JSONB | ⬜ |

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

### 4.1 Core Pattern Extraction (Fase A4)

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T4.1.1 | `fa_core_pattern_extractor` genera patrón candidato por documento | 👤 | Patrón en gerundio por documento | ⬜ |
| T4.1.2 | Patrón incluye evidence_quotes[2-5] de incidentes distintos | 👤 | evidence_quotes con 2–5 citas de incidentes diferentes | ⬜ |
| T4.1.3 | `fa_core_pattern_verifier` corre cada 3 documentos | 👤 | Verifier se ejecuta tras acumular 3 docs | ⬜ |
| T4.1.4 | Verifier emite recomendación | 👤 | CONTINUE_COLLECTING \| READY_FOR_CROSS_DOC \| NEEDS_DIFFERENT_POPULATION | ⬜ |
| T4.1.5 | Verifier dispara HITL gate `pattern_of_interest` | 👤 | Modal HITL aparece con el patrón detectado | ⬜ |
| T4.1.6 | Verifier usa `operational_question` del Nemotrón | 🤖 | Verifier recibe OQ como variable | ⬜ |
| T4.1.7 | Verifier no recibe `_VERIFIER_GUIDANCE` dict (eliminado) | 🤖 | `pattern_verifier.py` no contiene el dict | ⬜ |

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

### 7.1 Database A/B Prompts

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T7.1.1 | `ff_database_a_proposer` transforma categorías en nodos | 👤 | entity_type correcto por nodo | ⬜ |
| T7.1.2 | `ff_database_a_critic` evalúa nodos | 👤 | Verdict SAT\|MOD\|FORCED | ⬜ |
| T7.1.3 | `ff_database_b_proposer` genera PROCESSES edge obligatorio | 👤 | Al menos un edge tipo PROCESSES presente | ⬜ |
| T7.1.4 | `ff_database_b_critic` detecta contradicciones y missing edges | 👤 | Issues[] incluye contradictions y missing_edges | ⬜ |
| T7.1.5 | `database_nodes` table existe con columnas correctas | 🤖 | Migration 3de4964dd68c aplicada | ⬜ |
| T7.1.6 | `database_edges` table existe con FK a database_nodes | 🤖 | Migration aplicada, FK válidas | ⬜ |
| T7.1.7 | `reporter.py` queries usan `database_nodes` (no `database_a_nodes`) | 🤖 | Nombres de tabla corregidos | ⬜ |
| T7.1.8 | `reporter.py` edges query hace JOIN con nodes para labels | 🤖 | SQL con JOIN a database_nodes para src/tgt labels | ⬜ |

---

## 8. Fase 6b: Theoretical Playground

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T8.1 | `GET /projects/{id}/theory` carga ecosistema | 👤 | Blobs + tendrils + ghosts en response | ⬜ |
| T8.2 | `conceptual_elaborator` propone relaciones | 👤 | POST elaboration → `conceptual_relationships` nueva fila | ⬜ |
| T8.3 | `ghost_blob_mapper` absorbe memos huérfanos | 👤 | Memo vinculado a categoría | ⬜ |
| T8.4 | `memo_theoretical_tagger` (FLASH) clasifica memos | 👤 | `memo_sorting_attempts` poblado con family affinities | ⬜ |
| T8.5 | `memo_theoretical_tagger` se ejecuta en `_prepare_playground_for_project` | 👤 | Todos los memos reciben tag de 12 familias | ⬜ |
| T8.6 | `f6b_gap_alerter` se despacha si ≥3 ghost blobs sin link | 🤖 | gap_alerter llamado con gaps_summary | ⬜ |
| T8.7 | `ecosystem_gap_detector` cuenta ghost blobs huérfanos | 🤖 | SQL query retorna conteo correcto | ⬜ |

---

## 9. Fase 6a: Redacción Natural

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T9.1 | `natural_writer` (PRO) redacta desde memos | 👤 | `write_section` retorna draft + citations + concepts | ⬜ |
| T9.2 | `writing_critic` (PRO) evalúa borrador | 👤 | Issues detectados: tense, subject, citation, fidelity, abstraction | ⬜ |
| T9.3 | `gap_feeler` (FLASH) detecta huecos en background | 👤 | Gaps detectados sin bloquear escritura | ⬜ |

---

### 9.1 Gap Feeler + Memo Tagger

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T9.1.1 | `f6a_gap_feeler` (FLASH) detecta huecos | 👤 | MISSING_EVIDENCE, UNDERDEVELOPED_PROPERTY, etc. | ⬜ |
| T9.1.2 | Gap feeler no bloquea — acumula señales | 👤 | Escritura continúa aunque haya gaps detectados | ⬜ |
| T9.1.3 | `f6b_memo_theoretical_tagger` clasifica memos | 👤 | Memos clasificados en 12 familias canónicas | ⬜ |
| T9.1.4 | Solo familias con score ≥ 0.3 aparecen en output | 👤 | Familias por debajo del umbral no incluidas | ⬜ |

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

## 11b. Fase 6e: Final Report

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T11b.1 | `f6a_final_report` (PRO) genera reporte con 8 secciones | 👤 | Reporte estructurado con 8 headings | ⬜ |
| T11b.2 | Abstract 180-220 palabras | 👤 | Conteo de palabras del abstract dentro del rango | ⬜ |
| T11b.3 | Headings adaptados a `{object_of_study}` | 👤 | "Core Emotion" vs "Core Concern" según tipo | ⬜ |
| T11b.4 | Título: "{Core Pattern} — A Classic Grounded Theory of {Population}" | 👤 | Formato de título correcto | ⬜ |
| T11b.5 | Reporte se almacena en `final_reports` table | 👤 | O fallback graceful si tabla no existe | ⬜ |

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

### 12.1 "Core" Terminology Consistency

| # | Test | Quién | Qué verificar | Estado |
|---|------|-------|--------------|--------|
| T12.1.1 | Todos los prompts usan "core" no "main"/"dominant"/"primary" | 🤖 | Búsqueda en PROMPT_REGISTRY confirma consistencia terminológica | ⬜ |
| T12.1.2 | Frontend i18n: es="Patrón de Interés", de="Kernmuster", pt="Padrão Central" | 👤 | Labels en 3 idiomas cargan correctamente | ⬜ |
| T12.1.3 | Gate consolidado: solo `pattern_of_interest`, no `main_concern` | 🤖 | Búsqueda en codebase: `main_concern` no aparece en gates | ⬜ |
| T12.1.4 | SQL queries usan `proposal->>'core_concern'` (no `main_concern`) | 🤖 | Búsqueda en codebase: `main_concern` solo en agent IDs, no en SQL | ⬜ |
| T12.1.5 | `core_concern` como variable Python (no `main_concern`) | 🤖 | `tasks.py`, `workflow.py`, `orchestrator.py` usan `core_concern` | ⬜ |

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

### 14.7 Processing Verb + RQ Preview

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.7.1 | Selector object_of_study muestra hint dinámico por tipo | 👤 | Hint cambia al seleccionar "concern" vs "emotion" | ⬜ |
| T14.7.2 | Input processing_verb tiene default por tipo | 👤 | "resolver" para concern, default apropiado para emotion | ⬜ |
| T14.7.3 | RQ preview se actualiza al cambiar población, verbo, o tipo | 👤 | Preview en vivo refleja cambios en los 3 campos | ⬜ |
| T14.7.4 | Experimental Mode section permite cambiar object_of_study mid-project | 👤 | Cambio de tipo → estado vuelve a "coding" | ⬜ |
| T14.7.5 | Cambiar object_of_study → estado vuelve a "coding" | 👤 | Proyecto reinicia pipeline desde coding | ⬜ |

### 14.8 Population Configuration Panel

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T14.8.1 | Panel "🧬 Population Configuration" aparece si `supuesto_poblacional` existe | 👤 | Sección colapsable visible en Project detail | ⬜ |
| T14.8.2 | Generalized population se muestra como pill | 👤 | Texto de población generalizada visible | ⬜ |
| T14.8.3 | Botón "Generate" aparece si no hay generalized_population | 👤 | Botón visible, llama al endpoint generalize | ⬜ |
| T14.8.4 | Edit inline: click en Edit → input aparece, Save persiste | 👤 | Edición inline de population_description funciona | ⬜ |
| T14.8.5 | Spatial/Temporal frame labels traducidos | 👤 | "cohabiting_group" → "Grupo conviviente" | ⬜ |
| T14.8.6 | Confidence bar coloreada: >=80% verde, >=50% ambar, <50% rojo | 👤 | Barra de confianza con color correcto | ⬜ |

---

## 15. Prompt System v2: Renaming + i18n + agents/

> **Post-refactor verificacion.** 101 archivos renombrados, 125 carpetas agents/, 369 schemas traducidos.

### 15.1 Registry + Naming

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T15.1 | PROMPT_REGISTRY carga >= 68 prompts | 🤖 | `len(PROMPT_REGISTRY)` >= 68 | ⬜ |
| T15.2 | Todos los prompt_id usan prefijo de fase | 🤖 | Ningun prompt_id empieza sin fa_/fb_/fc_/f0_/f6a_/f6b_/f6c_/f6d_/ff_/fe_/fd_/hitl_/util_ | ⬜ |
| T15.3 | 125 carpetas agents/{id}/ contienen prompt.md | 🤖 | `find agents/ -name prompt.md | wc -l` >= 120 | ⬜ |
| T15.4 | Cada carpeta agents/{id}/ tiene schema.{en,es,de,pt}.json | 🤖 | 5 archivos por carpeta (prompt + 4 schemas) | ⬜ |

### 15.2 i18n Schema Loading

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T15.5 | `build_messages(language="es")` inyecta language_code + language_name | 🤖 | kwargs contiene `language_code="es"`, `language_name="español"` | ⬜ |
| T15.6 | `build_payload(language="es")` carga schema.es.json | 🤖 | response_format contiene descripciones en español | ⬜ |
| T15.7 | Fallback a schema.en.json si schema.{lang}.json no existe | 🤖 | `_load_i18n_schema("fr")` carga schema.en.json | ⬜ |
| T15.8 | Prompt sin agents_dir usa schema inline (legacy compat) | 🤖 | build_payload con prompt legacy mantiene schema original | ⬜ |

### 15.3 LLMClient Integration

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T15.9 | `LLMClient.run_agent(agent_id, language="es")` pasa language a formato | 🤖 | system_prompt contiene language_code en variables | ⬜ |
| T15.10 | `LLMClient.set_user_language("es")` configura idioma global | 👤 | Llamadas subsecuentes usan español por defecto | ⬜ |
| T15.11 | Codigo legacy sin `language=` usa default de clase | 🤖 | `run_agent("fb_incident_comparator", {...})` → language="es" (default) | ⬜ |

### 15.4 Pre-filtro B1 + Batching

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T15.12 | B1 comparator usa pre-filtro embedding (cosine > 0.75) | 👤 | Log: "Pre-filter: X/Y pairs survive (Z.Z%)" | ⬜ |
| T15.13 | B1 batch size = 25 pares por llamada LLM | 👤 | Log: "N candidate pairs -> M LLM batches (batch_size=25)" | ⬜ |
| T15.14 | B1 Union-Find agrupa pares intercambiables | 👤 | `incident_groups` creados con >= 2 incidentes por grupo | ⬜ |
| T15.15 | B1 total pairs 9870 → pre-filter 295 (3.0%) para 141 incidentes | 👤 | Reduccion ~97% sin LLM | ⬜ |

### 15.5 Prompt Language Audit

| # | Test | Quien | Que verificar | Estado |
|---|------|-------|--------------|--------|
| T15.16 | System prompts en INGLES | 🤖 | Ningun system prompt contiene texto en español | ⬜ |
| T15.17 | Schema KEYS en INGLES | 🤖 | Todas las property names en schemas son ingles | ⬜ |
| T15.18 | Schema DESCRIPTIONS coinciden con idioma del schema file | 🤖 | schema.es.json tiene descriptions en español | ⬜ |
| T15.19 | Sin referencias a prompt_id antiguos en codigo | 🤖 | `grep -r "population_generalizer" workers/ backend/` solo en legacy/deprecated | ⬜ |


## Resumen

| Sección | Tests | 🤖 Agente | 👤 Investigador |
|---------|-------|-----------|----------------|
| 0. Infraestructura | 11 | 4 | 7 |
| 1. Fase 0: Configuración | 6 + 14 (1.1) | 2 + 3 (🤖 1.1) | 4 + 11 (👤 1.1) |
| 2. Fase A: Open Coding | 11 | 1 | 10 |
| 3. Fase B: Síntesis | 9 | 1 | 8 |
| 4. Fase 5b-A: Core Category | 8 + 7 (4.1) | 3 + 2 (🤖 4.1) | 5 + 5 (👤 4.1) |
| 5. Fase 5b-B: Reduction | 2 | 1 | 1 |
| 6. Fase 5b-C: Saturation | 10 | 0 | 10 |
| 7. Fase 5b-D: Database | 2 + 8 (7.1) | 0 + 4 (🤖 7.1) | 2 + 4 (👤 7.1) |
| 8. Fase 6b: Playground | 7 | 2 | 5 |
| 9. Fase 6a: Redacción | 3 + 4 (9.1) | 0 | 3 + 4 (👤 9.1) |
| 10. Fase 6c: Literatura | 2 | 0 | 2 |
| 11. Fase 6d: Aplicabilidad | 2 | 0 | 2 |
| 11b. Fase 6e: Final Report | 5 | 0 | 5 |
| 12. Transversales | 10 + 5 (12.1) | 0 + 4 (🤖 12.1) | 10 + 1 (👤 12.1) |
| 13. Regresiones | 10 | 0 | 10 |
| 14. Frontend UX Pipeline | 35 + 5 (14.7) + 6 (14.8) | 0 | 35 + 5 (👤 14.7) + 6 (👤 14.8) |
| 15. Prompt System v2 | 19 (15.1-15.5) | 16 (🤖 15.1-15.4) + 1 (🤖 15.5) | 3 (👤 15.3) |
| **TOTAL** | **192 → 211** | **27 → 44** | **165 → 167** |
