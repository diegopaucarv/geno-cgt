# CGT System Refactor — Checklist Completo de Cambios

> **Fundamento:** kb.md, 1-Refaccion open coding.md, 2-Cascada modificacion.md, 3-memomaker.md, 4-Patrones_de_desarrollo.md, 5-Adaptacion_Sistema_Agencial.md
>
> Organizado del nivel más simple (sin tocar flujo actual) al más pervasivo (modifica el core), culminando en verificaciones integrativas (referencias, trazabilidad, consistencia).
>
> Cada ítem incluye: archivos a modificar, funciones/componentes a modificar/crear, y el **spillover cascade** (funciones y componentes que importan o dependen de lo modificado).

---

## Tabla de Contenido

1. [FASE 0: Capa de Datos y Estructura de Carpetas](#fase-0-capa-de-datos-y-estructura-de-carpetas)
2. [FASE 1: Cambios Puntuales sin Tocar el Flujo Actual](#fase-1-cambios-puntuales-sin-tocar-el-flujo-actual)
3. [FASE 2: Separación de Agentes y Refactor de Pipeline](#fase-2-separación-de-agentes-y-refactor-de-pipeline)
4. [FASE 3: Patrones de Desarrollo (Tracking, Resiliencia, Transiciones)](#fase-3-patrones-de-desarrollo-tracking-resiliencia-transiciones)
5. [FASE 4: Cambios Arquitectónicos Mayores (Core Flow)](#fase-4-cambios-arquitectónicos-mayores-core-flow)
6. [FASE 5: Fases No Implementadas (Nuevos Agentes, Endpoints, UI)](#fase-5-fases-no-implementadas-nuevos-agentes-endpoints-ui)
7. [FASE 6: Verificación Integrativa y Trazabilidad](#fase-6-verificación-integrativa-y-trazabilidad)
8. [Documentos de Diseño Complementarios](#documentos-de-diseño-complementarios)

---

## FASE 0: Capa de Datos y Estructura de Carpetas

Cambios que no afectan el flujo de ejecución — solo agregan esquemas, tablas y carpetas.

### F0.1 — Tablas Nuevas (3)

> 📎 **Refs:** `1-Refaccion open coding.md` §6.1-6.3 (esquema SQL), `kb.md` §4 L124-139 (extracción de incidentes)

| # | Tabla | Archivo Modificado | Funciones/Clases Creadas | Spillover Cascade (importadores afectados) |
|---|-------|-------------------|--------------------------|-------------------------------------------|
| F0.1.1 | `extracted_incidents` (incidente_id, segmento_id, documento_id, proyecto_id, jot_text, keep_moving, tipo_dato_glaser, preguntas_glaser_json, patrón_documento_id) | **CREATE:** `backend/app/models/domain/incident.py` | `class ExtractedIncident(Base, TimestampMixin)` con FK→`segmentos`, FK→`documentos`, FK→`proyectos` | `backend/app/models/domain/__init__.py` (registro del modelo); `backend/app/schemas/models.py` (si se expone en API); futuros tests en `tests/` |
| F0.1.2 | `incident_comparisons` (pair_id, incident_a_id, incident_b_id, proyecto_id, similarity_score, are_interchangeable, rationale) | **CREATE:** `backend/app/models/domain/incident.py` (mismo archivo) | `class IncidentComparison(Base, TimestampMixin)` con FK→`extracted_incidents` (x2), FK→`proyectos` | Igual que F0.1.1 |
| F0.1.3 | `incident_groups` (group_id, proyecto_id, label, definition, status, incident_ids_json, labeled_by_agent, critic_verdict) | **CREATE:** `backend/app/models/domain/incident.py` (mismo archivo) | `class IncidentGroup(Base, TimestampMixin)` con FK→`proyectos` | Igual que F0.1.1 |

### F0.2 — Tablas para MemoMaker / Sorting Log (2)

> 📎 **Refs:** `3-memomaker.md` §4.2 (nueva tabla `memo_sorting_attempts`), `kb.md` §8 L357-365 (Sorting Log)

| # | Tabla | Archivo Modificado | Funciones/Clases Creadas | Spillover Cascade |
|---|-------|-------------------|--------------------------|-------------------|
| F0.2.1 | `memo_sorting_attempts` (attempt_id, proyecto_id, theoretical_code_id, groups_json, homeless_json, forced_json, thin_json, score) | **CREATE:** `backend/app/models/domain/sorting.py` | `class MemoSortingAttempt(Base, TimestampMixin)` con FK→`proyectos`, FK→`theoretical_codes` | `backend/app/models/domain/__init__.py`; `backend/app/services/theory_seeder.py` (si se necesita seed); `frontend/src/components/theory/PlaygroundContext.tsx` (para fetching de sorting log al cargar el playground) |
| F0.2.2 | `memo_sorting_groups` (group_id, attempt_id, memos_json, cross_family_affinity_json) | **CREATE:** `backend/app/models/domain/sorting.py` (mismo archivo) | `class MemoSortingGroup(Base, TimestampMixin)` con FK→`memo_sorting_attempts` | Igual que F0.2.1 |

### F0.3 — Columnas Nuevas en Tablas Existentes (5)

> 📎 **Refs:** `1-Refaccion open coding.md` §6.4 (columnas en tablas existentes), `kb.md` §2 L71-79 (object_of_study), `kb.md` §6.4 L232-243 (panel de 4 señales)

| # | Tabla | Columna | Archivo Modificado | Clase/Función Modificada | Spillover Cascade |
|---|-------|---------|-------------------|--------------------------|-------------------|
| F0.3.1 | `memos` | `version` (Integer, default=1), `parent_memo_id` (FK→memos, nullable), `structured_fields` (JSONB, nullable) | `backend/app/models/domain/memo.py` | `class Memo(Base, TimestampMixin)` — agregar 3 columnas | `workers/heavy/agents_b.py` (`b1_distill_sampling`: INSERT INTO memos debe incluir nuevos defaults); `backend/app/api/v1/pipeline.py` (lectura/escritura de memos); `frontend/src/components/MemoHistory.tsx` (si se renderiza versionado); `backend/app/agents/hitl_modifier.py` (`_load_family_data` lee memos) |
| F0.3.2 | `categorias` | `saturation_panel_json` (JSONB, nullable — almacena las 4 señales pre-calculadas) | `backend/app/models/domain/category.py` | `class Categoria` — agregar columna | `workers/heavy/tasks.py` (`task_core_saturation_loop`, `task_global_saturation_check`); `backend/app/services/saturation_gap_analyzer.py` (`SaturationGapAnalyzer.run_analysis`); `backend/app/api/v1/analysis.py` (endpoint de saturation gaps) |
| F0.3.3 | `categorias` | `gerundio_label` (String(200), nullable — etiqueta en gerundio propuesta por el pattern_labeler) | `backend/app/models/domain/category.py` | `class Categoria` — agregar columna | `workers/heavy/agents_b.py` (`b2_open_code` → asigna `gerundio_label` al crear códigos); `frontend/src/components/theory/CategoryBlob.tsx` (renderizado del label) |
| F0.3.4 | `proyectos` | `coding_style_instruction` (Text, nullable — instrucción compilada de coding_styles inyectada en prompts) | `backend/app/models/domain/project.py` | `class Proyecto` — agregar columna | `backend/app/api/v1/analysis.py` (`set_coding_styles` debe escribir esta columna); `workers/heavy/agents_b.py` (`_get_coding_style_instruction` debe leer de aquí en vez de recalcular); `backend/app/core/coding_styles.py` (sin cambios, es fuente) |
| F0.3.5 | `proyectos` | `object_of_study` (String(50), default="concern") — extraer del JSONB `population_assumption` a columna dedicada | `backend/app/models/domain/project.py` | `class Proyecto` — agregar columna | `workers/heavy/agents_b.py` (`_get_population_assumption`); `workers/heavy/tasks.py` (`task_main_concern_pipeline`, `a1_build_population_context`); `backend/app/services/selective_elaborator.py` (`SelectiveElaborator`); `backend/app/api/v1/projects.py` (creación y edición de proyecto); `frontend/src/pages/Project.tsx` (si se expone en la UI) |

### F0.4 — Estructura de Carpetas Nueva (4)

> 📎 **Refs:** `4-Patrones_de_desarrollo.md` §4 (archivos a crear), `kb.md` §8 (theoretical coding), §11-13 (redacción, literatura, aplicabilidad)

| # | Carpeta | Propósito | Archivos que la poblarán |
|---|---------|-----------|--------------------------|
| F0.4.1 | `workers/heavy/` — nuevos archivos | Agentes CGT aislados (según kb.md y especificaciones) | `incident_extractor.py`, `pattern_extractor.py`, `comparator.py`, `labeler.py`, `label_critic.py`, `saturation_loop.py`, `database_ab.py`, `memo_maker.py` |
| F0.4.2 | `backend/app/prompts/deepseek_flash/memo_theoretical_tagger.md` | Prompt para el pre-clasificador de memos al entrar al Playground | Archivo .md con instrucciones de clasificación por afinidad a las 12 familias |
| F0.4.3 | `backend/app/prompts/deepseek_pro/natural_writer.md`, `writing_critic.md` | Prompts para la redacción natural (Fase 6a) | Archivos .md con instrucciones de escritura CGT desde pilas de memos |
| F0.4.4 | `backend/app/prompts/deepseek_pro/literature_comparer.md`, `literature_critic.md`, `applicability_engine.md`, `applicability_critic.md` | Prompts para diálogo con literatura (Fase 6c) y aplicabilidad (Fase 6d) | Archivos .md con instrucciones de emergent fit y directrices de intervención |

### F0.5 — Migración de Base de Datos

> 📎 **Refs:** `1-Refaccion open coding.md` §8.4 (migraciones de BD)

| # | Cambio | Comando / Archivo |
|---|--------|-------------------|
| F0.5.1 | Generar migración Alembic para todas las tablas y columnas nuevas | `cd backend && alembic revision --autogenerate -m "cgt_refactor_phase0"` |
| F0.5.2 | Aplicar migración | `cd backend && alembic upgrade head` |
| F0.5.3 | Verificar que los seeds sigan funcionando | Ejecutar `task_seed_theoretical_codes` → debe insertar 12 códigos sin error |

### F0.6 — Documento `AGENTES.md` (Fuente Única de Verdad de Agentes)

> 📎 **Refs:** `kb.md` §17 (glosario original — consolidado aquí), `5-Adaptacion_Sistema_Agencial.md` §1 (componentes agenciales existentes)

| # | Cambio | Archivo | Contenido | Spillover Cascade |
|---|--------|---------|-----------|-------------------|
| F0.6.1 | Extraer el glosario de agentes de kb.md §17 y enriquecerlo con tiers, estados, inputs/outputs y referencias a prompts de todos los documentos | **CREATE:** `Documentacion/cgt_alignment/AGENTES.md` | Tabla canónica con columnas: `Agente`, `Tier` (FLASH/PRO/ALG), `Fase CGT`, `Estado`, `Prompt`, `Input`, `Output`, `Consume`, `Alimenta` | `Documentacion/cgt_alignment/kb.md` §17 (marcar como "→ Ver AGENTES.md"); `Documentacion/cgt_alignment/1-Refaccion open coding.md` §5 (referenciar); `Documentacion/cgt_alignment/4-Patrones_de_desarrollo.md` (referenciar); `Documentacion/cgt_alignment/5-Adaptacion_Sistema_Agencial.md` (referenciar) |

### F0.7 — Documento `TECH_DEBT.md` (Deuda Técnica de Parámetros Hardcodeados)

> 📎 **Refs:** `1-Refaccion open coding.md` §10 completo (parámetros hardcodeados: coding_style, main_concern, 4 preguntas, jot, population_generalizer)

| # | Cambio | Archivo | Contenido | Spillover Cascade |
|---|--------|---------|-----------|-------------------|
| F0.7.1 | Extraer §10 de 1-Refaccion (parámetros hardcodeados: coding_style, main_concern, 4 preguntas, DEFAULT_POPULATION_ASSUMPTION, formato jot, population_generalizer) a documento independiente | **CREATE:** `Documentacion/cgt_alignment/TECH_DEBT.md` | Lista priorizada de hardcodeos con ubicación exacta (archivo + línea), valor actual, valor deseado, y esfuerzo estimado | `Documentacion/cgt_alignment/1-Refaccion open coding.md` §10 (reemplazar con referencia: "Ver TECH_DEBT.md"); `workers/heavy/agents_b.py`; `backend/app/models/domain/project.py`; `backend/app/core/coding_styles.py`; `backend/app/prompts/deepseek_pro/` (varios)

---

## FASE 1: Cambios Puntuales sin Tocar el Flujo Actual

Correcciones pequeñas, determinísticas, que no alteran el pipeline.

### F1.1 — Unificación Terminológica ("main concern" → "patrón de interés")

> 📎 **Refs:** `1-Refaccion open coding.md` §10.4 (main concern como término no modular), §10.9 (cambios en JSON schemas), `kb.md` §3 L87-109 (patrón de interés)

| # | Qué | Archivos Modificados | Funciones/Componentes Modificados | Spillover Cascade |
|---|-----|---------------------|----------------------------------|-------------------|
| F1.1.1 | Renombrar constantes y labels en el backend de "main_concern" a "pattern_of_interest" (sin cambiar nombres de tablas ni columnas DB) | `backend/app/agents/transitions.py` | `hitl_gate()` — gate_name "main_concern" → mantener (es nombre de gate, no cambia); comentarios internos | `workers/heavy/tasks.py` (`task_main_concern_pipeline` — comentarios y docstrings); `backend/app/api/v1/hitl.py` (`decide_hitl` — comentarios); `backend/app/models/domain/hitl_decision.py` (comentarios) |
| F1.1.2 | Actualizar labels en el frontend para reflejar "patrón de interés" | `frontend/src/components/HITLModal.tsx` | `GATE_LABELS` constante L12-20: `main_concern: "🎯 Main Concern"` → mantener el key, actualizar descripción; `renderProposal()` L30-172: labels que muestren "main_concern" | `frontend/src/pages/Project.tsx` (si `PIPELINE_STAGES` hace referencia) |
| F1.1.3 | Unificar `DEFAULT_POPULATION_ASSUMPTION` (hardcodeado en `project.py` L9-13) como un parámetro configurable | `backend/app/models/domain/project.py` | `DEFAULT_POPULATION_ASSUMPTION` L9-13: extraer a `backend/app/core/config.py` como setting | `workers/heavy/agents_b.py` (`_get_population_assumption` L41-48 que lee este default); `workers/heavy/tasks.py` (`_get_population_assumption` L107-115) |

### F1.2 — `population_generalizer` al Crear Proyecto

> 📎 **Refs:** `kb.md` §2 L63-69 (tu población), `4-Patrones_de_desarrollo.md` §1 Fase 0, `1-Refaccion open coding.md` §10.8 (population_generalizer hardcodeado)

| # | Qué | Archivos Modificados | Funciones/Componentes Creados o Modificados | Spillover Cascade |
|---|-----|---------------------|-------------------------------------------|-------------------|
| F1.2.1 | Crear endpoint o tarea que invoque `population_generalizer` al crear proyecto (FLASH, single-shot) | **CREATE:** `workers/fast/population_generalizer.py` | `def generalize_population(raw_description: str) -> dict` — llama LLM FLASH con prompt `deepseek_flash/population_generalizer.md`; **MODIFY:** `backend/app/api/v1/projects.py` — llamar esta función al crear proyecto | `backend/app/schemas/models.py` (`ProjectCreate` schema — agregar campo opcional); `frontend/src/pages/Projects.tsx` (formulario de creación — agregar feedback visual de generalización); `backend/app/core/config.py` (si se parametriza el modelo) |

### F1.3 — Extraer las 12 Familias de Códigos Teóricos a Módulo Independiente

> 📎 **Refs:** `3-memomaker.md` §2 (las 12 familias como configuración compartida), `kb.md` §8 L388-394 (las 12 familias siempre disponibles), `PROMPT_CRITERIA.md` (guía de programador para prompts)

| # | Qué | Archivos Modificados | Funciones/Componentes Modificados | Spillover Cascade |
|---|-----|---------------------|----------------------------------|-------------------|
| F1.3.1 | Extraer `BUILT_IN_THEORETICAL_CODES` a módulo de configuración reutilizable | **CREATE:** `backend/app/core/theoretical_families.py` | `THEORETICAL_FAMILIES: dict` — 12 familias con metadata (name, family, layer, visualization_hint, description, evaluation_logic) | `backend/app/services/theory_seeder.py` (importa `BUILT_IN_THEORETICAL_CODES` desde el nuevo módulo); `backend/app/core/workflow.py` (si se usan en el flujo); `backend/app/api/v1/theoretical_codes.py` |
| F1.3.2 | Refactorizar `theory_seeder.py` para usar el módulo extraído | `backend/app/services/theory_seeder.py` | `seed_theoretical_codes()` L272-313: reemplazar `BUILT_IN_THEORETICAL_CODES` por import desde `theoretical_families` | `backend/app/main.py` (lifespan L45-52 que llama `seed_theoretical_codes`); `workers/heavy/tasks.py` (`_prepare_playground_for_project` L998-1016, `task_seed_theoretical_codes` L1711-1725) |

### F1.4 — `maturity_gate()` Determinístico (Chequeo SQL, sin LLM)

> 📎 **Refs:** `kb.md` §7.2 L309-319 (el maturity gate con 3 condiciones), `5-Adaptacion_Sistema_Agencial.md` §2.2 (CRÍTICO #2), `4-Patrones_de_desarrollo.md` §3 (prioridad #4b)

| # | Qué | Archivos Modificados | Funciones/Componentes Creados o Modificados | Spillover Cascade |
|---|-----|---------------------|-------------------------------------------|-------------------|
| F1.4.1 | Implementar `maturity_gate(project_id)` en el Orchestrator. Chequea: ≥3 categorías saturadas (4 señales), ≥2 relaciones documentadas, ≥3 categorías vinculadas al patrón de interés | `backend/app/services/pipeline_orchestrator.py` | **CREATE:** `def maturity_gate(self, project_id: UUID) -> dict` (retorna `{passed: bool, missing: [{condition, detail}]}`) | `workers/heavy/tasks.py` (`selective_coding_coordinator` L1738-1834 — debe llamar `maturity_gate()` antes de Fase A); `backend/app/api/v1/pipeline.py` (`get_pipeline_status` — exponer resultado del gate) |
| F1.4.2 | Integrar `maturity_gate` en `OrchestratorRuleEngine` para que lo evalúe antes de `find_core_concern` | `backend/app/agents/orchestrator.py` | `OrchestratorRuleEngine.decide()` L67-99: agregar caso para `maturity_gate` antes de `find_core_concern`; `_resolve_after_reduce()` L103-121: verificar maturity antes de redirigir | `backend/app/core/workflow.py` (`route_via_orchestrator` L367-377 — ya usa OrchestratorRuleEngine en modo AGENTIC_ORCHESTRATOR) |

---

## FASE 2: Separación de Agentes y Refactor de Pipeline

Aislamiento de agentes según kb.md: incident_extractor per-segmento, Comparator/Labeler/Critic separados.

### F2.1 — `glaser_data_classifier` Aislado (Fase A, Pre-codificación)

> 📎 **Refs:** `1-Refaccion open coding.md` §5.1 (especificación A0), `kb.md` §4 L113-122 (lo que pasa antes de codificar), `AGENTES.md` §glaser_data_classifier (⚙️+FLASH dos capas)

| # | Qué | Archivos | Funciones/Componentes | Spillover Cascade |
|---|-----|---------|----------------------|-------------------|
| F2.1.1 | El `glaser_data_classifier` actual (`algorithmic_checks.preclassify_glaser`) ya existe como pre-clasificador algorítmico. **Dos capas (resolución C5):** (1) capa algorítmica para ~90% de segmentos (rápido, gratuito), (2) confirmación FLASH solo para segmentos con `confidence < 0.7` (borderline). | `workers/heavy/algorithmic_checks.py` | `preclassify_glaser()` — agregar flag `use_llm_fallback=False` y lógica de dos capas: si `confidence < 0.7` → dispatchear tarea FLASH de confirmación | `workers/nlp/segmentador.py` (si se llama post-segmentación); `workers/heavy/tasks.py` (`process_document_agents_a` — insertar clasificación en `segmentos.tipo_dato_glaser`) |
| F2.1.2 | Crear prompt `glaser_data_classifier.md` para confirmación FLASH de segmentos dudosos | **CREATE:** `backend/app/prompts/deepseek_flash/glaser_data_classifier.md` (ya existe L20 en fs — verificar que esté completo) | Prompt: clasifica segmento en baseline/properline/interpreted/vague con ejemplos | `backend/app/prompts/loader.py` (registro del prompt); `workers/heavy/llm_client.py` (si necesita ajuste de temperature) |

### F2.2 — `incident_extractor` Aislado (CRÍTICO #3 de kb.md §5-Adaptacion)

> 📎 **Refs:** `kb.md` §4 L124-139 (extracción de incidentes, keep-moving), `5-Adaptacion_Sistema_Agencial.md` §2.3 (CRÍTICO #3), `1-Refaccion open coding.md` §5.2 (especificación A1), `AGENTES.md` §incident_extractor (FLASH, output ≤1 párrafo), `PROMPT_CRITERIA.md` §Nemotron FLASH (parámetros, anti-patrones)

| # | Qué | Archivos | Funciones/Componentes Creados o Modificados | Spillover Cascade |
|---|-----|---------|-------------------------------------------|-------------------|
| F2.2.1 | Crear `incident_extractor.py` como worker **FLASH** independiente por segmento. NO ve otros documentos, NO ve categorías existentes. Aplica las 4 preguntas de Glaser (pregunta 4 parametrizada por `object_of_study` — ver C4). Produce un "jot" (gerundio). **PRO explícitamente rechazado**: keep-moving exige análisis rápido; la profundidad emerge de la acumulación de docenas de incidentes, no del análisis individual. | **CREATE:** `workers/heavy/incident_extractor.py` | `def extract_incident(segment_id: str, proyecto_id: str) -> dict` — usa `_make_patched(AbortableTask)` wrapper; `class IncidentExtractorTask(AbortableTask)` — ejecuta LLM **FLASH** con prompt `incident_extractor.md` (resolución C1) | `workers/heavy/tasks.py` (registrar tarea `@app.task(name="extract_incident")`); `backend/app/core/workflow.py` (si el workflow graph lo invoca); `backend/app/prompts/loader.py` (registrar nuevo prompt) |
| F2.2.2 | Desacoplar la extracción de indicadores del `b2a_extract_indicators` actual. El `b2a` actual corre en Fase B (cross-document) y debe correr per-segmento en Fase A | `workers/heavy/agents_b.py` | `_b2a_extract_indicators()` L153-157: renombrar a `_b2a_extract_indicators_legacy`; el nuevo `incident_extractor` reemplaza su función en Fase A | `workers/heavy/tasks.py` (`process_document_agents_a` — ya no debe llamar b2a; en su lugar, el NLP worker despachará `extract_incident` por cada segmento de oro); `backend/app/core/workflow.py` (`node_batch_code` L169-179 que importa `b2_open_code`) |

### F2.3 — Separar Comparator / Labeler / Critic en Fase B (CRÍTICO #1)

> 📎 **Refs:** `kb.md` §5 L159-169 (tres agentes, tres roles), `1-Refaccion open coding.md` §5.4-5.6 (especificación B1-B3), `4-Patrones_de_desarrollo.md` §2.1 (arquitectura objetivo), `5-Adaptacion_Sistema_Agencial.md` §2.1 (CRÍTICO #1), `AGENTES.md` §Fase B, `6-ContextWindowManager.md` §3.1-3.2 (estrategia de escalamiento para B1 y B2)

| # | Qué | Archivos | Funciones/Componentes Creados o Modificados | Spillover Cascade |
|---|-----|---------|-------------------------------------------|-------------------|
| F2.3.1 | Crear `incident_comparator` (B1). Recibe SOLO incidentes, sin ver categorías. Compara pares y agrupa por intercambiabilidad. **Estrategia incremental (resolución C6):** primera ejecución compara todos contra todos. Ejecuciones subsecuentes solo comparan incidentes nuevos contra grupos existentes y entre sí — mantiene fidelidad metodológica sin costo cuadrático (4.5M pares para 3000 incidentes). | **CREATE:** `workers/heavy/comparator.py` | `def b1_compare_incidents(proyecto_id: str, incremental: bool = False) -> dict` — PRO, 1-pass, sin ver categorías. Lee de `extracted_incidents`, escribe en `incident_comparisons` e `incident_groups`. Si `incremental=True`, usa `WHERE creado_en > last_run` para limitar scope. | `workers/heavy/tasks.py` (reemplazar `b1_distill_sampling` en `process_synthesis_agents_b` L886-893 por `b1_compare_incidents`); `workers/heavy/agents_b.py` (deprecar `b1_distill_sampling` L86-145 que actualmente VE categorías — violación directa) |
| F2.3.2 | Crear `pattern_labeler` (B2). Recibe grupos del Comparator. Propone etiquetas + definiciones. SelfRefinement loop con el Critic. | **CREATE:** `workers/heavy/labeler.py` | `def b2_label_groups(proyecto_id: str) -> dict` — PRO, usa `SelfRefinementLoop` con `generate_prompt_id="pattern_labeler"`, `critic_prompt_id="label_critic"`, `max_iterations=3` | `workers/heavy/tasks.py` (`process_synthesis_agents_b` — reemplazar `b2_open_code` L898-901); `backend/app/agents/self_refiner.py` (ya implementa SelfRefinementLoop — se reutiliza con nuevos prompt_ids) |
| F2.3.3 | Crear `label_critic` (B3). Evalúa cada etiqueta del Labeler. Aprueba, rechaza, o devuelve con feedback. **FLASH confirmado (resolución C2):** es evaluación estructurada (diff/comparación), no generación. FLASH es 10× más barato y suficiente para esta tarea. El bucle B2↔B3 puede iterar hasta 3 veces — usar PRO aquí triplicaría el costo innecesariamente. | **CREATE:** `workers/heavy/label_critic.py` | `def b3_critique_labels(groups_json: str, labels_json: str) -> dict` — **FLASH**, 1-pass, emite `{verdict, issues[], all_valid}` | `backend/app/prompts/deepseek_flash/label_critic.md` (crear prompt); `workers/heavy/labeler.py` (el SelfRefinementLoop lo invoca como critic) |
| F2.3.4 | Refactorizar `process_synthesis_agents_b` para ejecutar B1 → B2 (con bucle B2↔B3) → B4 (evidence retriever) en secuencia | `workers/heavy/tasks.py` | `process_synthesis_agents_b()` L877-951: reescribir la secuencia: B1 (comparator) → B2 (labeler con loop) → B4 (RAG evidence) → B3 ya no es paso separado, es el critic del loop de B2 | `workers/heavy/agents_b.py` (funciones legacy quedan deprecated); `backend/app/core/workflow.py` (`node_batch_code` L169-179, `node_generate_hypotheses` L257-267, `node_map_synthesize`, `node_reduce_synthesize`) |

### F2.4 — `core_pattern_extractor` por Documento (Fase A)

> 📎 **Refs:** `kb.md` §4 L141-143 (patrón individual de cada entrevistado), `1-Refaccion open coding.md` §5.3 (especificación A2), `AGENTES.md` §core_pattern_extractor (PRO, síntesis multi-párrafo)

| # | Qué | Archivos | Funciones/Componentes Creados | Spillover Cascade |
|---|-----|---------|------------------------------|-------------------|
| F2.4.1 | Crear extractor del patrón individual de cada entrevistado después de extraer incidentes. Usa solo datos de oro de ese documento. **PRO (resolución C1 — corolario):** a diferencia del incident_extractor (FLASH, per-segmento, alto volumen), este agente sintetiza por documento (bajo volumen, ~1 llamado por documento) y requiere razonamiento profundo para identificar el patrón unificador. | **CREATE:** `workers/heavy/pattern_extractor.py` | `def extract_core_pattern(documento_id: str, proyecto_id: str) -> dict` — **PRO**, 1-pass. Lee incidentes extraídos del doc, sintetiza patrón con citas y confianza | `workers/heavy/tasks.py` (nueva tarea `@app.task(name="extract_core_pattern")` — despachada después de que todos los segmentos del doc tengan incidentes extraídos); `workers/heavy/incident_extractor.py` (coordinar: cuando último segmento del doc se procesa → disparar pattern_extractor) |

---

## FASE 3: Patrones de Desarrollo (Tracking, Resiliencia, Transiciones)

Aplicar los 4 patrones de `4-Patrones_de_desarrollo.md` a tareas existentes.

### F3.1 — `AbortableTask` + Tracking en Tareas de Selective Coding Existentes

> 📎 **Refs:** `4-Patrones_de_desarrollo.md` §3 (Resiliencia + Tracking), `kb.md` §6.7 (resumen del flujo con HITL gates)

| # | Qué | Archivos Modificados | Funciones Modificadas | Spillover Cascade |
|---|-----|---------------------|----------------------|-------------------|
| F3.1.1 | Envolver `task_main_concern_pipeline` con `AbortableTask` (ya existe el decorator `@app.task` pero no hereda de `AbortableTask`) | `workers/heavy/tasks.py` | `task_main_concern_pipeline()` L1838-1940: cambiar `@app.task` → crear clase `MainConcernPipelineTask(AbortableTask)` | `backend/app/api/v1/pipeline.py` (endpoints de stop/cancel usan `celery_app.control.revoke`); `frontend/src/api/client.ts` (`stopWorker`, `cancelTask`, `killAllWorkers` ya implementados) |
| F3.1.2 | Ídem para `task_core_emergence_pipeline` | `workers/heavy/tasks.py` | `task_core_emergence_pipeline()` L1944-2019: misma refactorización | Igual que F3.1.1 |
| F3.1.3 | Ídem para `task_selective_reduction_pipeline` | `workers/heavy/tasks.py` | `task_selective_reduction_pipeline()` L2023-2104: misma refactorización | Igual que F3.1.1 |
| F3.1.4 | Ídem para `task_core_saturation_loop` | `workers/heavy/tasks.py` | `task_core_saturation_loop()` L2112-2316: misma refactorización + agregar checkpoints por iteración (ya tiene loop sobre categorías × docs) | Igual que F3.1.1; `frontend/src/pages/Project.tsx` (stage status polling L198-205) |

### F3.2 — Tracking (PipelineTask) para Tareas de Proyecto (sin document_id)

> 📎 **Refs:** `4-Patrones_de_desarrollo.md` §1-2 (Patrón 2: Trazabilidad), `kb.md` §15 (el investigador en el centro)

| # | Qué | Archivos Modificados | Funciones Modificadas | Spillover Cascade |
|---|-----|---------------------|----------------------|-------------------|
| F3.2.1 | `task_main_concern_pipeline` debe crear `PipelineTask` con `document_id=NULL` | `workers/heavy/tasks.py` | `task_main_concern_pipeline()` L1838: insertar en `pipeline_tasks` al iniciar | `backend/app/agents/transitions.py` (`_dispatch_next` L150-198 — ya soporta tracking con run_id); `backend/app/api/v1/pipeline.py` (`get_pipeline_log` L165-332 — ya consulta `pipeline_tasks`) |
| F3.2.2 | Ídem para todas las tareas del `selective_coding_coordinator` | `workers/heavy/tasks.py` | `selective_coding_coordinator()` L1738-1834: crear `PipelineRun` y `PipelineTask` por cada fase | Igual que F3.2.1 |
| F3.2.3 | Ídem para tareas del Theoretical Playground (`_prepare_playground_for_project`) | `workers/heavy/tasks.py` | `_prepare_playground_for_project()` L991-1042: tracking de seeding, ghost mapping, gap detection | Igual que F3.2.1 |

### F3.3 — Extender Transiciones de Proyecto

> 📎 **Refs:** `4-Patrones_de_desarrollo.md` §1 (Patrón 1: Transiciones), `kb.md` §15.1 (qué pasa cuando decidís — la cascada), `2-Cascada modificaicon.md` (mapa de cascada de modificaciones)

| # | Qué | Archivos Modificados | Funciones Modificadas | Spillover Cascade |
|---|-----|---------------------|----------------------|-------------------|
| F3.3.1 | Agregar `maturity_gate` como estado "pausado" en `PROJECT_STATES` para que el frontend muestre un estado intermedio | `backend/app/agents/transitions.py` | `PROJECT_STATES` L53-61: agregar `"sintetizado": "checking_maturity"` → `"checking_maturity": "finding_cc"` | `workers/heavy/tasks.py` (`selective_coding_coordinator` — transiciona usando `transition_project`); `frontend/src/pages/Project.tsx` (`PIPELINE_STAGES` L51-60 — agregar stage "Verificando madurez") |
| F3.3.2 | Agregar endpoint SSE/Redis para notificar cambio de estado de proyecto | `backend/app/core/celery_app.py` o `backend/app/api/v1/events.py` | Publicar en Redis `project:{id}:events` cuando `transition_project` cambia estado | `frontend/src/pages/Project.tsx` (polling actual L198-205 ya consulta `getPipelineStatus` — se puede migrar a SSE); `frontend/src/api/client.ts` (agregar `subscribeProjectEvents`) |

---

## FASE 4: Cambios Arquitectónicos Mayores (Core Flow)

Cambios que reestructuran el pipeline y la arquitectura de agentes.

### F4.1 — Refactorizar `agents_b.py` → Nuevos Módulos Aislados

> 📎 **Refs:** `1-Refaccion open coding.md` §8.3 (agentes a deprecated), `5-Adaptacion_Sistema_Agencial.md` §2.1 (CRÍTICO #1 con líneas de código), `4-Patrones_de_desarrollo.md` §2.1 (separación Comparator/Labeler/Critic)

| # | Qué | Archivos | Funciones | Spillover Cascade |
|---|-----|---------|----------|-------------------|
| F4.1.1 | Mover `b1_distill_sampling` a módulo legacy/deprecated. Su reemplazo es `incident_comparator` (F2.3.1) | `workers/heavy/agents_b.py` | `b1_distill_sampling()` L86-145: marcar con `@deprecated` y warning; no eliminar hasta que F2.3.1 esté estable | `workers/heavy/tasks.py` L849-854 (import); `backend/app/core/workflow.py` (si workflow lo referencia — no parece) |
| F4.1.2 | Mover `b2_open_code` a legacy. Su reemplazo es `pattern_labeler` + `label_critic` (F2.3.2-F2.3.3) | `workers/heavy/agents_b.py` | `b2_open_code()` L264-416: deprecated. Incluye `_b2a_extract_indicators`, `_b2b_generate_codes`, `_enrich_codes_with_evidence`, `_b2b_generate_codes_agentic` | `workers/heavy/tasks.py` L849-854; `backend/app/core/workflow.py` L169-179 |
| F4.1.3 | `b3_generate_hypotheses` y `b3_generate_hypotheses_agentic` se mantienen pero deben actualizarse para recibir los grupos etiquetados del nuevo flujo (no códigos raw de b2) | `workers/heavy/agents_b.py` | `b3_generate_hypotheses()` L574-662, `b3_generate_hypotheses_agentic()` L718-812: cambiar input de `codigos_segmento` + `categorias` → `incident_groups` etiquetados | `workers/heavy/tasks.py` L924-929; `backend/app/core/workflow.py` L257-267 |

### F4.2 — `core_saturation_loop` con Panel de 4 Señales

> 📎 **Refs:** `kb.md` §6.3-6.4 (loop de saturación + panel de 4 señales), `4-Patrones_de_desarrollo.md` §2.2 (prioridad #6: panel como endpoint dedicado), `AGENTES.md` §Fase 5b-C (SaturationGapAnalyzer, core_saturation_proposer/critic)

| # | Qué | Archivos | Funciones | Spillover Cascade |
|---|-----|---------|----------|-------------------|
| F4.2.1 | Refactorizar `task_core_saturation_loop` para que evalúe las 4 señales (matemática, cualitativa, cobertura, integración) antes de declarar saturación | `workers/heavy/tasks.py` | `task_core_saturation_loop()` L2112-2316: agregar consulta a `saturation_metrics.rolling_std` (señal 1); `paradigm_states` ventana de 5 (señal 2); cobertura de propiedades (señal 3); `conceptual_relationships` count (señal 4) | `backend/app/services/saturation_gap_analyzer.py` (`SaturationGapAnalyzer` — ya implementa lógica de 4 señales, pero `task_core_saturation_loop` no la invoca); `backend/app/models/domain/synthesis.py` (`ParadigmState`, `SaturationMetrics`) |
| F4.2.2 | Escribir `saturation_panel_json` en `categorias` al saturar (cache de las 4 señales) | `workers/heavy/tasks.py` | `task_core_saturation_loop()` — después de verificar las 4 señales, UPDATE `categorias.saturation_panel_json` | `backend/app/api/v1/analysis.py` (`get_saturation_gaps` endpoint — leer de esta cache en vez de recalcular); `frontend/src/pages/Project.tsx` (mostrar panel de saturación) |
| F4.2.3 | Activar TheoSampler solo bajo demanda (cuando no satura con datos existentes) | `workers/heavy/tasks.py` | `task_a06_theoretical_sample()` L1107-1180 ya está implementado. Asegurar que `task_core_saturation_loop` lo invoque condicionalmente (solo si `did_state_expand=False` por 3 iteraciones consecutivas) | `backend/app/services/emergent_sampler.py` (`EmergentSampler`); `backend/app/core/workflow.py` (`node_theosampler_evaluate` L615-625) |

### F4.3 — Integrar MemoMaker en el Loop de Saturación

> 📎 **Refs:** `3-memomaker.md` §3 (diseño del MemoMaker — 3 agentes), `kb.md` §6.3 L225-229 (MemoMaker integrado: Generate → Simplificar → Correlacionar), `AGENTES.md` §memo_theoretical_tagger (FLASH, pre-clasificación)

| # | Qué | Archivos | Funciones/Componentes Creados | Spillover Cascade |
|---|-----|---------|------------------------------|-------------------|
| F4.3.1 | Crear agente MemoMaker: Generate (integrar 4 análisis) → Simplify (tablas de doble entrada) → Correlate (matrices 2×2 con tipologías) | **CREATE:** `workers/heavy/memo_maker.py` | `def generate_saturation_memo(category_id: str, proyecto_id: str) -> dict` — PRO, 3 pasos. Inserta en `memos` con `structured_fields` (JSONB) y versionado | `workers/heavy/tasks.py` (`task_core_saturation_loop` — invocar MemoMaker al saturar una categoría); `backend/app/models/domain/memo.py` (columnas nuevas F0.3.1) |
| F4.3.2 | Crear `memo_theoretical_tagger` (FLASH) para pre-clasificar memos al entrar al Playground | **CREATE:** `workers/heavy/memo_maker.py` (mismo archivo o separado) | `def pre_classify_memo(memo_id: str, proyecto_id: str) -> dict` — FLASH, 1-pass, evalúa afinidad con las 12 familias y devuelve `{family: score}` | `backend/app/prompts/deepseek_flash/memo_theoretical_tagger.md` (F0.4.2); `workers/heavy/tasks.py` (`_prepare_playground_for_project` — invocar para todos los memos) |

### F4.4 — Corregir el Diagrama de Secuencia (`secuencia_actual.mermaid`)

> 📎 **Refs:** `5-Adaptacion_Sistema_Agencial.md` §6 (correcciones al mermaid), `kb.md` §15 (el Orchestrator es DELGADO). **Nota:** El diagrama objetivo ya está creado en `secuencia_cgt.mermaid`. Este paso corrige el diagrama del estado actual.

| # | Qué | Archivo | Cambio | Spillover |
|---|-----|---------|--------|-----------|
| F4.4.1 | Cambiar `ORC->>LLM` por `HVY->>LLM` en todas las interacciones (el Orchestrator es DELGADO, no llama LLMs) | `Documentacion/cgt_alignment/secuencia_actual.mermaid` | L97-98, L103-105, L117-119, L131-135, L137-143, L145-151, L153-157, L159-163, L167-173, L177-187, L192-197, L200-206 | Este es un artefacto de documentación, no afecta código. Pero coordinar con el equipo que la arquitectura documentada coincida con la implementada. |
| F4.4.2 | Agregar etapas faltantes: Fase 0 (configuración con population_generalizer), Fase 8+ (redacción, literatura, aplicabilidad) | `Documentacion/cgt_alignment/secuencia_actual.mermaid` | Insertar nuevas secciones después de ETAPA 7 | Solo documentación |

---

## FASE 5: Fases No Implementadas (Nuevos Agentes, Endpoints, UI)

Fases completas que kb.md especifica pero no existen en el código actual.

### F5.1 — Database A/B desde Cero

> 📎 **Refs:** `kb.md` §6.5 (Database A y Database B), `AGENTES.md` §Fase 5b-D (database_a/b proposers + critics)

| # | Qué | Archivos | Funciones/Componentes | Spillover Cascade |
|---|-----|---------|----------------------|-------------------|
| F5.1.1 | Database A y B ya tienen implementación parcial (`task_database_a_pipeline` L2379-2464, `task_database_b_pipeline` L2468-2598). Completar: persistir nodos/edges incluso cuando critic no es SAT (el HITL decide) | `workers/heavy/tasks.py` | `task_database_a_pipeline()`: actualmente solo persiste si `critic.get("verdict") == "SAT"`. Cambiar a siempre persistir en estado "pending" y que el HITL confirme. `task_database_b_pipeline()`: ídem | `backend/app/models/domain/database.py` (modelos `DatabaseNode`, `DatabaseEdge` ya existen); `backend/app/api/v1/hitl.py` (decide_hitl para gates "database_a", "database_b" ya existe) |
| F5.1.2 | Crear prompts `database_a_proposer.md`, `database_a_critic.md`, `database_b_proposer.md`, `database_b_critic.md` si no existen | Verificar `backend/app/prompts/deepseek_pro/` | Los tasks ya llaman `llm.run_agent("database_a_proposer", ...)` — los prompts deben existir o crearse | `backend/app/prompts/loader.py` (registro); `workers/heavy/llm_client.py` |

### F5.2 — Panel de 4 Señales como Endpoint Dedicado

> 📎 **Refs:** `kb.md` §6.4 L232-243 (el panel de saturación — cuatro señales, no una), `4-Patrones_de_desarrollo.md` §3 (prioridad #6)

| # | Qué | Archivos | Funciones/Componentes | Spillover Cascade |
|---|-----|---------|----------------------|-------------------|
| F5.2.1 | Crear endpoint `GET /api/v1/projects/{id}/saturation-panel` que devuelva las 4 señales para cada categoría | `backend/app/api/v1/analysis.py` | **CREATE:** `async def get_saturation_panel(project_id: UUID) -> list[SaturationPanelItem]` | `frontend/src/api/client.ts` (agregar `getSaturationPanel`); `frontend/src/pages/Project.tsx` (nueva sección de UI "Panel de Saturación" o integrado en el stage "Core Saturation"); `backend/app/schemas/hitl.py` o `backend/app/schemas/models.py` (nuevo schema `SaturationPanelItem`) |
| F5.2.2 | El endpoint debe cachear resultados en `categorias.saturation_panel_json` y refrescar bajo demanda (query param `?refresh=true`) | `backend/app/api/v1/analysis.py` | Mismo endpoint — si `refresh=true`, recalcular con `SaturationGapAnalyzer` y guardar en `saturation_panel_json` | `backend/app/services/saturation_gap_analyzer.py` `SaturationGapAnalyzer.run_analysis()` — ya existe |

### F5.3 — Redacción Natural (Fase 6a)

> 📎 **Refs:** `kb.md` §11 (de las pilas al papel), `4-Patrones_de_desarrollo.md` §1 (Fase 8+: no implementado), `AGENTES.md` §Fase 6a (natural_writer, writing_critic, gap_feeler)

| # | Qué | Archivos | Funciones/Componentes Creados | Spillover Cascade |
|---|-----|---------|------------------------------|-------------------|
| F5.3.1 | Crear `natural_writer` (PRO) — redacta borrador de sección desde una pila de memos | **CREATE:** `workers/heavy/writer.py` | `def write_section(sorting_group_id: str, proyecto_id: str) -> dict` — PRO, recibe memos ordenados, redacta en presente conceptual, inserta @ refs | `backend/app/prompts/deepseek_pro/natural_writer.md` (F0.4.3); `workers/heavy/tasks.py` (registrar `@app.task(name="natural_writer")`) |
| F5.3.2 | Crear `writing_critic` (PRO) — evalúa borrador contra reglas CGT (tiempo verbal, conceptos vs personas, dosis de citas, fidelidad a memos) | **CREATE:** `workers/heavy/writer.py` (mismo archivo) | `def critique_section(draft: str, memo_ids: list[str], proyecto_id: str) -> dict` — PRO, emite `{verdict: SAT|MOD|FORCED, issues: [{type, location, suggestion}]}` | `backend/app/prompts/deepseek_pro/writing_critic.md` (F0.4.3); `workers/heavy/tasks.py` |
| F5.3.3 | Crear `gap_feeler` (FLASH) — monitorea escritura en segundo plano, detecta afirmaciones sin memo, transiciones débiles, propiedades unipolares | **CREATE:** `workers/fast/gap_feeler.py` | `def feel_gaps(draft: str, project_id: str) -> list[dict]` — FLASH, corre asíncrono, no bloqueante | `backend/app/prompts/deepseek_flash/gap_feeler.md` (crear si no existe); `frontend/src/pages/Playground.tsx` (mostrar gaps detectados) |
| F5.3.4 | Crear UI para escritura (panel izquierdo: pila de memos; panel derecho: editor con marcado de critic) | **CREATE:** `frontend/src/components/theory/WritingPanel.tsx` (o nuevo componente) | Componente React con split view: `MemoStack` (lista de memos ordenados) + `SectionEditor` (textarea con highlights de colores según critic) | `frontend/src/pages/Playground.tsx` (nueva tab/sección "📝 Redacción Natural"); `frontend/src/api/client.ts` (endpoints para write, critique, gap-feel) |

### F5.4 — Diálogo con la Literatura (Fase 6c)

> 📎 **Refs:** `kb.md` §12 (el diálogo con la literatura), `4-Patrones_de_desarrollo.md` §1 (Fase 8+), `AGENTES.md` §Fase 6c (literature_comparer, literature_critic)

| # | Qué | Archivos | Funciones/Componentes Creados | Spillover Cascade |
|---|-----|---------|------------------------------|-------------------|
| F5.4.1 | Crear `literature_comparer` (PRO) — codifica fragmentos de literatura como incidentes, compara contra propiedades de la teoría, evalúa emergent fit | **CREATE:** `workers/heavy/literature.py` | `def compare_literature(proyecto_id: str, literature_fragments: list[str]) -> dict` — PRO, produce tabla Extiende/Modifica/Integra/Trasciende | `backend/app/prompts/deepseek_pro/literature_comparer.md` (F0.4.4); `backend/app/services/rag.py` (búsqueda semántica de literatura relevante) |
| F5.4.2 | Crear `literature_critic` (PRO) — evalúa si el comparer fuerza coincidencias o trata literatura como autoridad | **CREATE:** `workers/heavy/literature.py` | `def critique_literature_dialogue(comparison_table: dict) -> dict` — PRO | `backend/app/prompts/deepseek_pro/literature_critic.md` (F0.4.4) |
| F5.4.3 | Crear UI para tabla Extiende/Modifica/Integra/Trasciende + inserción automática de notas al pie | **CREATE:** `frontend/src/components/theory/LiteraturePanel.tsx` | Componente React con tabla interactiva: filas = categorías, columnas = 4 modos de diálogo, celdas clickeables para ver fragmentos | `frontend/src/pages/Playground.tsx` (nueva tab "📚 Literatura"); `frontend/src/api/client.ts` |

### F5.5 — Aplicabilidad (Fase 6d)

> 📎 **Refs:** `kb.md` §13 (de la teoría a la acción), `4-Patrones_de_desarrollo.md` §1 (Fase 8+), `AGENTES.md` §Fase 6d (applicability_engine, applicability_critic)

| # | Qué | Archivos | Funciones/Componentes Creados | Spillover Cascade |
|---|-----|---------|------------------------------|-------------------|
| F5.5.1 | Crear `applicability_engine` (PRO) — identifica variables de control y acceso, redacta directrices de intervención, propone implicaciones y agenda futura | **CREATE:** `workers/heavy/applicability.py` | `def generate_applicability(proyecto_id: str) -> dict` — PRO | `backend/app/prompts/deepseek_pro/applicability_engine.md` (F0.4.4) |
| F5.5.2 | Crear `applicability_critic` (PRO) — evalúa si directrices son genuinas vs. genéricas, si respeta límites de aplicabilidad, si lenguaje es accesible | **CREATE:** `workers/heavy/applicability.py` | `def critique_applicability(directrices: dict) -> dict` — PRO | `backend/app/prompts/deepseek_pro/applicability_critic.md` (F0.4.4) |

### F5.6 — Sistema de Re-especificación (Fallback Pattern)

> 📎 **Refs:** `kb.md` §10 (cuando algo no encaja), `1-Refaccion open coding.md` §20 (sistema de re-especificación jerárquica), `AGENTES.md` §Transversales (ReSpecAgent)

| # | Qué | Archivos | Funciones/Componentes Creados | Spillover Cascade |
|---|-----|---------|------------------------------|-------------------|
| F5.6.1 | Crear `ReSpecAgent` (PRO) — monitorea señales de que algo necesita revisión (incidentes ambiguos, etiquetas rechazadas, relaciones divergentes sin resolver, memos huérfanos, ejes vacíos) | **CREATE:** `backend/app/agents/respect_agent.py` | `class ReSpecAgent(BaseAgent)` — PRO, evalúa señales acumuladas y decide si sugerir re-especificación | `backend/app/agents/__init__.py` (registrar); `backend/app/agents/quality/scorer.py` (posible integración con scoring de señales) |
| F5.6.2 | Crear `ReSpecTool` — herramienta invocable desde cualquier nivel para bajar un nivel de abstracción y re-examinar | **CREATE:** `backend/app/agents/tools/respect_tool.py` | `class ReSpecTool`: `query_lower_level(entity_type, entity_id, direction) -> dict` | `backend/app/agents/tool_registry.py` (registrar la tool); `backend/app/agents/tools/__init__.py` |
| F5.6.3 | Crear botón "Stage-Gate Review" en el frontend — brilla cuando hay sugerencias de re-especificación | `frontend/src/pages/Project.tsx` | **CREATE:** componente `StageGateButton` (o integrar en el pipeline stage actual). Props: `stageKey`, `suggestionCount`. Brilla púrpura si `count > 0` | `frontend/src/api/client.ts` (endpoint `getReSpecSuggestions`); `backend/app/api/v1/pipeline.py` (endpoint `GET /projects/{id}/respect-suggestions`) |

---

## FASE 6: Verificación Integrativa y Trazabilidad

Chequeos finales de consistencia, referencias, y documentación.

### F6.1 — Auditoría de FK y Relaciones en BD

> 📎 **Refs:** `1-Refaccion open coding.md` §16.2 (eslabones FUERTES/DÉBILES/AUSENTES), `kb.md` §14 (trazabilidad — de la teoría al dato)

| # | Qué | Archivos a Verificar | Verificación | Acción Correctiva |
|---|-----|---------------------|-------------|-------------------|
| F6.1.1 | Verificar que todas las tablas nuevas tengan FK correctas. Las especificaciones indican 3 tipos de eslabones: FUERTES (FK + relationship en SQLAlchemy), DÉBILES (JSONB, sin FK), AUSENTES (no existen) | `backend/app/models/domain/` (todos los archivos) | SQLAlchemy `relationship()` debe existir para cada `ForeignKey`. Las relaciones JSONB deben documentarse con comentarios. | Agregar `relationship()` donde falte. Documentar JSONB links. |
| F6.1.2 | Verificar cascadas de DELETE: `incident_comparisons` deben eliminarse si se borra un `extracted_incident`. `incident_groups` deben eliminarse si se borra el proyecto. | `backend/app/models/domain/incident.py` (nuevo) | `cascade="all, delete-orphan"` en las FK apropiadas | Corregir. |
| F6.1.3 | Verificar índices: `extracted_incidents.segmento_id`, `incident_comparisons.proyecto_id`, `incident_groups.proyecto_id` deben tener índices para queries frecuentes | `backend/app/models/domain/incident.py` | Agregar `index=True` en `mapped_column` | Agregar índices. |

### F6.2 — Trazabilidad End-to-End (cadena de referencias kb.md §14)

> 📎 **Refs:** `kb.md` §14 L539-553 (cadena: código teórico → relación → categoría → incidente → segmento → cita), `1-Refaccion open coding.md` §16 (sistema relacional de referencias)

| # | Cadena | Tablas Involucradas | Estado Actual | Acción |
|---|--------|--------------------|---------------|--------|
| F6.2.1 | `Código teórico → Relación conceptual → Categoría` | `theoretical_codes` → `conceptual_relationships` (FK `theoretical_code_id`) → `categorias` (vía `category_ids` JSONB) | ✅ FUERTE para theoretical_code. ⚠️ DÉBIL para category_ids (JSONB) | Agregar tabla pivote `conceptual_relationship_categories` con FK real a `categorias` |
| F6.2.2 | `Categoría → Incidente → Segmento → Cita textual` | `categorias` → `extracted_incidents` (nueva tabla, FK a `categorias` via `incident_groups`) → `segmentos` (FK) | 🔴 AUSENTE — `extracted_incidents` no existe aún | Implementar con F0.1.1. Agregar FK `categoria_id` opcional en `extracted_incidents` o vincular vía `incident_groups` → `categorias` |
| F6.2.3 | `Relación conceptual → Incidentes convergentes/divergentes` | `conceptual_relationships` (campos JSONB `converging_incident_ids`, `diverging_incident_ids`) | ⚠️ DÉBIL — JSONB sin FK | Evaluar si se necesita FK real. Si hay muchos incidentes, considerar tabla pivote. Si son pocos, JSONB es aceptable documentándolo. |

### F6.3 — Consistencia de Estados entre Frontend y Backend

> 📎 **Refs:** `4-Patrones_de_desarrollo.md` §1 (Patrón 1: Transiciones con optimistic lock), `kb.md` §15 (estados del pipeline)

| # | Qué | Archivos | Verificación | Acción |
|---|-----|---------|-------------|--------|
| F6.3.1 | `PIPELINE_STAGES` en frontend debe coincidir con `PROJECT_STATES` en backend | `frontend/src/pages/Project.tsx` L51-60 vs `backend/app/agents/transitions.py` L53-61 | Comparar keys: `segment`, `agents`, `synthesis`, `find_cc`, `reduce`, `saturate`, `build_db`, `playground` vs `collecting`, `coding`, `finding_cc`, `reducing`, `saturating`, `building_db`, `playground_ready`, `completed` | Normalizar nombres. Agregar `checking_maturity` si se implementa F3.3.1 |
| F6.3.2 | `GATE_LABELS` en HITLModal debe coincidir con los `gate_name` usados en `hitl_gate()` | `frontend/src/components/HITLModal.tsx` L12-20 vs `backend/app/agents/transitions.py` `hitl_gate()` L319-377 (y todos los callers en tasks.py) | Gates: `main_concern`, `core_emergence`, `selective_reduction`, `core_saturation`, `database_a`, `database_b`, `global_saturation` | ✅ Coinciden. Verificar que `core_saturation` se use consistentemente (en tasks.py L2289 se usa "core_saturation", en L2297 se menciona en el dict) |
| F6.3.3 | `StageStatus` type en frontend debe cubrir todos los estados posibles de un stage | `frontend/src/pages/Project.tsx` L62 | `type StageStatus = "pending" \| "running" \| "done" \| "failed"` — verificar si se necesita "paused" para HITL gates | Agregar `"paused"` si el pipeline puede pausarse en un HITL gate |

### F6.4 — Verificación de Importaciones tras Refactor

> 📎 **Refs:** `1-Refaccion open coding.md` §9 (conexión con pipeline existente), §12 (matriz de dependencias entre agentes)

| # | Qué | Archivos | Verificación | Acción |
|---|-----|---------|-------------|--------|
| F6.4.1 | `from workers.heavy.agents_b import` en `backend/app/core/workflow.py` (L169, L257) quedará roto si `agents_b.py` se depreca | `backend/app/core/workflow.py` | Verificar que `b2_open_code` y `b3_generate_hypotheses` tengan nuevos paths de import | Actualizar imports a los nuevos módulos (`workers/heavy/labeler`, `workers/heavy/comparator`, etc.) |
| F6.4.2 | `from agents_b import` en `workers/heavy/tasks.py` L849-854 quedará roto | `workers/heavy/tasks.py` | Actualizar imports | Reemplazar por imports de los nuevos módulos aislados |
| F6.4.3 | Verificar que `backend/app/core/workflow.py` no dependa de funciones que se movieron a legacy | `backend/app/core/workflow.py` | `node_batch_code` L169-179, `node_generate_hypotheses` L257-267, `node_map_synthesize`, `node_reduce_synthesize` | Actualizar todos los references en el workflow graph |

### F6.5 — Verificación de Prompts (Existencia y Consistencia)

> 📎 **Refs:** `PROMPT_CRITERIA.md` (auditoría de prompts existentes, guía FLASH/PRO), `AGENTES.md` (columna Prompt para cada agente), `1-Refaccion open coding.md` §10 (parámetros hardcodeados en prompts)

| # | Prompt | Ruta Esperada | ¿Existe? | Acción |
|---|--------|---------------|----------|--------|
| F6.5.1 | `glaser_data_classifier` (FLASH) | `deepseek_flash/glaser_data_classifier.md` | ✅ Existe (L20 en fs) | Verificar que esté completo con ejemplos de baseline/properline/interpreted/vague |
| F6.5.2 | `incident_extractor` (FLASH) | `deepseek_flash/incident_extractor.md` | ✅ Existe (L15 en fs) | Verificar que incluya las 4 preguntas de Glaser |
| F6.5.3 | `incident_extractor` (PRO) | `deepseek_pro/incident_extractor.md` | ✅ Existe (L24 en fs) | Verificar que sea para el `core_pattern_extractor` (per-document), no confundir con el FLASH per-segmento |
| F6.5.4 | `pattern_labeler` (PRO) | `deepseek_pro/pattern_labeler.md` | ❓ No verificado | Crear si no existe. Debe recibir grupos del comparator y proponer etiquetas. |
| F6.5.5 | `label_critic` (FLASH) | `deepseek_flash/label_critic.md` | ❓ No verificado | Crear si no existe. Debe evaluar etiquetas del labeler. |
| F6.5.6 | `incident_comparator` (PRO) | `deepseek_pro/incident_comparator.md` | ❓ No verificado | Crear si no existe. Debe comparar incidentes sin ver categorías. |
| F6.5.7 | `database_a_proposer` / `database_a_critic` / `database_b_proposer` / `database_b_critic` (PRO) | `deepseek_pro/` | ❓ Los tasks llaman `llm.run_agent("database_a_proposer", ...)` — verificar existencia | Crear si no existen |
| F6.5.8 | `memo_theoretical_tagger` (FLASH) | `deepseek_flash/memo_theoretical_tagger.md` | 🔴 No existe | Crear (F0.4.2) |
| F6.5.9 | `natural_writer` / `writing_critic` (PRO) | `deepseek_pro/` | 🔴 No existen | Crear (F0.4.3) |
| F6.5.10 | `literature_comparer` / `literature_critic` (PRO) | `deepseek_pro/` | 🔴 No existen | Crear (F0.4.4) |
| F6.5.11 | `applicability_engine` / `applicability_critic` (PRO) | `deepseek_pro/` | 🔴 No existen | Crear (F0.4.4) |

### F6.6 — Verificación de Schemas Pydantic y TypeScript

> 📎 **Refs:** `1-Refaccion open coding.md` §10.9 (cambios en JSON schemas), §10.10 (cambios necesarios en código)

| # | Qué | Archivos | Verificación | Acción |
|---|-----|---------|-------------|--------|
| F6.6.1 | Schemas Pydantic para las nuevas tablas (`ExtractedIncident`, `IncidentComparison`, `IncidentGroup`) | `backend/app/schemas/models.py` | Agregar `IncidentResponse`, `IncidentCreate` usando `response_schema()` y `create_input_schema()` | Crear schemas |
| F6.6.2 | Interfaces TypeScript para las nuevas entidades | `frontend/src/api/client.ts` | Agregar `interface Incident`, `interface IncidentGroup`, `interface SaturationPanel` | Crear interfaces |
| F6.6.3 | Verificar que `ProjectCreate` schema acepte `object_of_study` como campo directo (no solo dentro de `population_assumption` JSONB) | `backend/app/schemas/models.py` L73-79 | `ProjectCreate = create_input_schema(Proyecto, exclude={...})` — si se agrega columna `object_of_study` (F0.3.5), el schema lo hereda automáticamente vía `create_input_schema` | Verificar tras agregar la columna |

---

## Resumen de Prioridades (Adaptado por Auditoría de Contradicciones)

> **Ver:** `AUDITORIA_CONTRADICCIONES.md` para el análisis completo de las 7 contradicciones (C1-C7) y 22 mejoras documentales (M2.1-M2.6).
>
> **Principio rector:** FLASH para extracción y crítica (alto volumen, tarea estructurada). PRO para síntesis y generación (bajo volumen, razonamiento profundo).

### 🔴 Crítico (bloquea otras fases) — 7 ítems
F0.6 (AGENTES.md — fuente única de verdad de agentes, previene recurrencia de C1-C7), F1.4 (maturity_gate), F2.2 (incident_extractor **FLASH** — resolución C1), F2.3 (separar Comparator/Labeler/Critic — resoluciones C2, C3, C7), F4.1 (refactor agents_b.py), F4.4 (corregir mermaid), F6.5 (verificar prompts)

### 🟡 Importante (desbloquea funcionalidad) — 13 ítems
F0.1-F0.3 (tablas y columnas nuevas), F0.5 (migración), F0.7 (TECH_DEBT.md), F1.1-F1.3 (unificación terminológica, population_generalizer, 12 familias), F2.1 (glaser_data_classifier dos capas — resolución C5), F2.4 (core_pattern_extractor **PRO** — resolución C1 corolario), F3.1-F3.3 (AbortableTask, tracking, transiciones), F4.2 (panel 4 señales), F5.1 (Database A/B completo)

### 🟢 Futuro (nice to have) — 15 ítems
F0.4 (carpetas), F4.3 (MemoMaker), F5.2-F5.6 (endpoints dedicados, redacción, literatura, aplicabilidad, re-especificación), F6.1-F6.4, F6.6 (auditoría FK, trazabilidad, consistencia estados, imports, schemas)

### 🆕 Add Memo System — 9 ítems (diseño: `7-AddMemo_System.md`)
A1 (columnas user_created/stage_at_creation), A2 (memo_types.py), A3-A4 (endpoints GET/POST memos), A5 (detección en coordinator), A6-A9 (frontend: modal, botón, historial, client.ts)

---

> **Total de ítems verificables:** 74 (63 originales + 2 documentos F0.6/F0.7 + 9 Add Memo System)
>
> **Archivos a crear:** ~27 (entre modelos, workers, prompts, componentes frontend, + AGENTES.md, TECH_DEBT.md, 6-ContextWindowManager.md)
>
> **Archivos a modificar:** ~18 (entre backend core, workers, frontend, documentación)
>
> **Estimación de esfuerzo:** Fase 0-2: 2-3 semanas. Fase 3-4: 3-4 semanas. Fase 5-6: 3-4 semanas.

---

## Oportunidades de Expansión del Checklist

Estos ítems no están en el checklist actual pero se recomienda agregarlos:

| # | Ítem | Fase | Prioridad | Justificación |
|---|------|------|-----------|---------------|
| **E1** | **Tests unitarios por cada nuevo agente.** Cada worker nuevo (`incident_extractor.py`, `comparator.py`, `labeler.py`, etc.) debe tener tests en `tests/workers/` con fixtures de segmentos/incidentes mock. | Fase 2 | 🔴 | Sin tests, los agentes nuevos son frágiles. El patrón `AbortableTask` ya facilita testing (se puede mockear el LLM). |
| **E2** | **Dockerfile + docker-compose para nuevos workers.** Si los nuevos agentes usan diferentes dependencias (ej. `ContextWindowManager` necesita `numpy` para embeddings), los Dockerfiles deben actualizarse. | Fase 2 | 🟡 | Los workers nuevos corren en el mismo contenedor `heavy` actual. Solo si requieren dependencias nuevas. |
| **E3** | **Verificar `secuencia_cgt.mermaid` contra kb.md.** El diagrama de secuencia objetivo debe ser auditado contra el flujo narrativo de kb.md §16 (el viaje completo) para asegurar que ninguna etapa falta. | Fase 6 | 🟡 | El mermaid se creó basado en los 5 documentos de especificación. Una verificación final contra kb.md §16 asegura consistencia. |
| **E4** | **Plan de rollback para migraciones de BD.** Las tablas nuevas (`extracted_incidents`, `incident_comparisons`, `incident_groups`) deben tener migraciones reversibles (`downgrade()`). | Fase 0 | 🟡 | Alembic autogenerate ya produce `downgrade()`. Verificar que funcionen antes de aplicar en producción. |
| **E5** | **Seed de datos de prueba.** Crear un script `scripts/seed_test_data.py` que inserte 3 documentos con segmentos, incidentes, y categorías mock para validar el pipeline end-to-end sin depender de datos reales. | Fase 0 | 🟢 | Acelera el desarrollo y testing de las Fases 2-5. |
| **E6** | **Métricas de costo por fase.** Agregar tracking de tokens consumidos y costo estimado por fase del pipeline (ya existe `agent_loop_logs.total_tokens` y `total_cost_est`). Extender a nivel de proyecto. | Fase 3 | 🟢 | Permite al investigador ver el costo acumulado de su proyecto. El modelo de datos ya lo soporta parcialmente. |
| **E7** | **Health check endpoint para workers.** Agregar `GET /api/v1/ping/workers` que verifique que NLP, Heavy, y Fast workers están respondiendo. | Fase 3 | 🟢 | Facilita debugging. |
| **E8** | **ContextWindowManager hibrido (Map-Reduce + ReAct).** Tool algoritmica Map-Reduce. Batches divergentes activan ReAct con search_segments + compare_tools. Diseno en 6-ContextWindowManager.md. | Fase 3 | 🟡 | Sin esto, B1 (125K pares) satura contexto. |
| **F0.8** | **Sistema de Historial Git-like.** Tabla generica entity_versions + version_evidence para 5 entidades. Timeline en frontend con hover/click a incidentes. HITL envia historial completo al LLM para cascade effects. | Fase 3 | 🟡 | Reemplaza category_definition_versions. Habilita F6.2 trazabilidad. |

---

## Documentos de Diseño Complementarios

Estos documentos no son items del checklist pero contienen diseños detallados referenciados por el:

| Documento | Referenciado por | Contenido |
|-----------|-----------------|-----------|
| `AGENTES.md` | F0.6 | Registro canonico de 38 agentes con tiers, estados, inputs/outputs, prompts |
| `6-ContextWindowManager.md` | F2.3.1, F2.3.2, E8 | Diseno de tool Map-Reduce + hibrido ReAct para batches divergentes (resuelve C6) |
| `7-GitLikeVersioning.md` | F0.8 | Sistema git-like: entity_versions + version_evidence para 5 entidades. Cascade evaluation FLASH. API y frontend. |
| `TECH_DEBT.md` | F0.7 | Deuda tecnica de parametros hardcodeados (extraido de 1-Refaccion 10) |
