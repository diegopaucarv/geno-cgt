# TESTING CHECKLIST — CGT Refactor Debugging

> **REORDENADO por velocidad de ejecución (rápido → lento) para detectar bottlenecks temprano.**
>
> Leyenda: 🤖 = Agente IA puede ejecutar | 👤 = Investigador debe ejecutar
> Velocidad: ⚡ instantáneo | 🏃 rápido (<30s) | 🚶 moderado (1-5min) | 🐢 lento (5-30min) | 💤 muy lento (30min+)
> API: 🔵 FLASH | 🔴 PRO | ⬜ sin API
> ⛔ = +20 llamadas API (requiere intervención humana)

---

## 🚨 BOTTLENECK SUMMARY (leer antes de testear)

| ID | Ubicación | Archivo | Llamadas API (5 docs) | Severidad |
|----|-----------|---------|----------------------|-----------|
| BN1 | glaser_data_classifier | `workers/heavy/algorithmic_checks.py:230` | ~72-90 FLASH | ⛔ CRÍTICO |
| BN2 | extract_incident | `workers/heavy/incident_extractor.py:246` | ~63 FLASH | ⛔ CRÍTICO |
| BN3 | Phase A completa | `workers/heavy/tasks.py:780` | ~169-187 total | ⛔ CRÍTICO |
| BN4 | Core Saturation Loop | `workers/heavy/tasks.py:3003` | 8-40 (variable) | ⚠️ ALTO |
| BN5 | NLP worker RAM | `workers/nlp/Dockerfile` | 6GB/concurrency | ⚠️ ALTO |

---

## ⚡ FASE RÁPIDA 1: Static Analysis & Code Checks (0 API calls, < 30s)

### 15. Prompt System v2 (STATIC ONLY — sin API)

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T15.1 | PROMPT_REGISTRY carga >= 68 prompts | 🤖 | ⚡ | `len(PROMPT_REGISTRY)` >= 68 | ⬜ |
| T15.2 | Todos los prompt_id usan prefijo de fase | 🤖 | ⚡ | Ningún prompt_id sin prefijo (fa_/fb_/fc_/...) | ⬜ |
| T15.3 | 125 carpetas agents/{id}/ contienen prompt.md | 🤖 | ⚡ | `find agents/ -name prompt.md \| wc -l` >= 120 | ⬜ |
| T15.4 | Cada carpeta agents/{id}/ tiene schema.{en,es,de,pt}.json | 🤖 | ⚡ | 5 archivos por carpeta | ⬜ |
| T15.5 | `build_messages(language="es")` inyecta language_code | 🤖 | ⚡ | kwargs contiene `language_code="es"` | ⬜ |
| T15.6 | `build_payload(language="es")` carga schema.es.json | 🤖 | ⚡ | response_format en español | ⬜ |
| T15.7 | Fallback a schema.en.json si schema.{lang}.json no existe | 🤖 | ⚡ | `_load_i18n_schema("fr")` carga schema.en.json | ⬜ |
| T15.8 | Prompt sin agents_dir usa schema inline (legacy compat) | 🤖 | ⚡ | build_payload con prompt legacy funciona | ⬜ |
| T15.16 | System prompts en INGLES | 🤖 | ⚡ | Ningún system prompt en español | ⬜ |
| T15.17 | Schema KEYS en INGLES | 🤖 | ⚡ | Property names en schemas son inglés | ⬜ |
| T15.18 | Schema DESCRIPTIONS coinciden con idioma del schema | 🤖 | ⚡ | schema.es.json tiene descriptions en español | ⬜ |
| T15.19 | Sin referencias a prompt_id antiguos en código | 🤖 | ⚡ | `grep -r "population_generalizer"` solo en legacy | ⬜ |

### 12.1 "Core" Terminology Consistency (STATIC ONLY)

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T12.1.1 | Todos los prompts usan "core" no "main"/"dominant"/"primary" | 🤖 | ⚡ | Búsqueda en PROMPT_REGISTRY | ⬜ |
| T12.1.3 | Gate consolidado: solo `pattern_of_interest`, no `main_concern` | 🤖 | ⚡ | Búsqueda en codebase | ⬜ |
| T12.1.4 | SQL queries usan `proposal->>'core_concern'` | 🤖 | ⚡ | Búsqueda: `main_concern` solo en agent IDs | ⬜ |
| T12.1.5 | `core_concern` como variable Python | 🤖 | ⚡ | `tasks.py`, `workflow.py`, `orchestrator.py` | ⬜ |

---

## ⚡ FASE RÁPIDA 2: Infraestructura Base (0 API calls, < 60s)

| # | Test | Quién | Vel | Comando / Verificación | Estado |
|---|------|-------|-----|----------------------|--------|
| T0.1 | Todos los .py compilan (syntax check) | 🤖 | ⚡ | `find workers/ -name '*.py' ...` | ⬜ 28/28 |
| T0.2 | Modelos SQLAlchemy cargan sin errores | 🤖 | ⚡ | `Base.metadata.tables` | ⬜ 41 tablas |
| T0.3 | Migración Alembic está en head | 👤 | ⚡ | `cd backend && alembic current` | ⬜ |
| T0.10 | Prompts se cargan sin errores | 🤖 | ⚡ | `PROMPT_REGISTRY` → 70 | ⬜ |
| T0.11 | Schemas Pydantic para tablas nuevas | 🤖 | ⚡ | `response_schema()` para 5 modelos | ⬜ |
| T0.4 | Docker containers arrancan | 👤 | 🏃 | `docker compose up -d && docker compose ps` | ⬜ |
| T0.5 | PostgreSQL acepta conexiones | 👤 | 🏃 | `docker compose exec postgres pg_isready` | ⬜ |
| T0.6 | Redis responde | 👤 | 🏃 | `docker compose exec redis redis-cli ping` | ⬜ |
| T0.7 | TEI embedding server responde | 👤 | 🏃 | `curl http://localhost:8080/health` | ⬜ |
| T0.8 | MinIO accesible | 👤 | 🏃 | `curl http://localhost:9001` | ⬜ |
| T0.9 | Seed de códigos teóricos funciona | 👤 | 🏃 | `seed_theoretical_codes()` → 12 built-in | ⬜ |

---

## 🏃 FASE RÁPIDA 3: DB Schema & Static Model Checks (0 API calls)

### 7.1 Database A/B Schema

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T7.1.5 | `database_nodes` table existe con columnas correctas | 🤖 | ⚡ | Migration 3de4964dd68c aplicada | ⬜ |
| T7.1.6 | `database_edges` table existe con FK a database_nodes | 🤖 | ⚡ | Migration aplicada, FK válidas | ⬜ |
| T7.1.7 | `reporter.py` queries usan `database_nodes` | 🤖 | ⚡ | Nombres de tabla corregidos | ⬜ |
| T7.1.8 | `reporter.py` edges query hace JOIN con nodes para labels | 🤖 | ⚡ | SQL con JOIN a database_nodes | ⬜ |
| T0.12 | `concerns` table existe con columnas correctas | 🤖 | ⚡ | id, project_id, label, description, status, identified_at_batch | ⬜ |
| T0.13 | `categorias` tiene `concern_label` y `population_label` | 🤖 | ⚡ | Ambas columnas presentes, nullable | ⬜ |
| T0.14 | `hypotheses` tiene `concern_labels` (JSONB) y `batch_number` | 🤖 | ⚡ | Ambas columnas presentes | ⬜ |

### 1. Fase 0: Config — Schema Checks (sin API)

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T1.4 | `object_of_study` default es "concern" | 🤖 | ⚡ | Columna `proyectos.object_of_study` | ⬜ |
| T1.5 | `coding_style_instruction` es nullable | 🤖 | ⚡ | Columna existe, nullable=True | ⬜ |

### 4. Core Category — Static Checks

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T4.6 | `task_core_emergence_pipeline` usa AbortableTask | 🤖 | ⚡ | `base=AbortableTask` en decorador | ⬜ |
| T4.4 | `task_main_concern_pipeline` usa AbortableTask | 🤖 | ⚡ | `base=AbortableTask` en decorador | ⬜ |
| T4.1.6 | Verifier usa `operational_question` del Nemotrón | 🤖 | ⚡ | Verifier recibe OQ como variable | ⬜ |
| T4.1.7 | Verifier no recibe `_VERIFIER_GUIDANCE` dict (eliminado) | 🤖 | ⚡ | `pattern_verifier.py` no contiene el dict | ⬜ |

### 2. Fase A — Static Checks

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T2.10 | `process_document_agents_a` usa AbortableTask | 🤖 | ⚡ | Decorador `base=AbortableTask` presente | ⬜ |

### 3. Fase B — Static Checks

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T3.7 | `process_synthesis_agents_b` usa AbortableTask | 🤖 | ⚡ | Decorador presente | ⬜ |

### 5. Selective Reduction — Static Checks

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T5.2 | `task_selective_reduction_pipeline` usa AbortableTask | 🤖 | ⚡ | `base=AbortableTask` en decorador | ⬜ |

---

## 🏃 FASE RÁPIDA 4: Endpoints Simples & Auth (0-1 API calls)

### 12. Transversales: Frontend Labels & State

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T12.1 | `HITLModal` muestra "Patrón de Interés" (F1.1) | 👤 | 🏃 | Label en frontend | ⬜ |
| T12.2 | `PIPELINE_STAGES` incluye "Verificando madurez" | 👤 | 🏃 | Stage 🔍 entre synthesis y find_cc | ⬜ |
| T12.1.2 | Frontend i18n: es="Patrón de Interés", de="Kernmuster", pt="Padrão Central" | 👤 | 🏃 | Labels en 3 idiomas | ⬜ |

### 13. Regresiones: Auth & CRUD Básico (sin pipeline)

| # | Test | Quién | Vel | Qué verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T13.1 | Login/Register funciona | 👤 | 🏃 | `POST /auth/login` → JWT token | ⬜ |
| T13.2 | Listar/Crear proyectos funciona | 👤 | 🏃 | `GET /projects`, `POST /projects` | ⬜ |
| T13.3 | Upload de documentos (PDF, DOCX, TXT) funciona | 👤 | 🏃 | `POST /projects/{id}/documents` | ⬜ |

### 1. Fase 0: Config — API Endpoints

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T1.1 | `POST /projects` crea proyecto con `supuesto_poblacional` | 👤 | 🏃 | ⬜ | `population_assumption` JSONB se llena | ⬜ |
| T1.6 | `GET /projects/{id}` incluye `object_of_study` | 👤 | 🏃 | ⬜ | Response JSON incluye el campo | ⬜ |
| T1.3 | `population_generalizer` falla gracefully sin API key | 👤 | 🏃 | ⬜ | Proyecto se crea igual | ⬜ |
| T1.2 | `population_generalizer` se ejecuta (FLASH) | 👤 | 🏃 | 🔵×1 | Logs: "population_generalizer: project=X spatial=Y temporal=Z" | ⬜ |

### 1.1 Processing Verb System — Endpoints (1-2 FLASH calls cada uno)

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T1.1.1 | Crear proyecto con `processing_verb="resolver"` | 👤 | 🏃 | ⬜ | `population_assumption.processing_verb` = "resolver" | ⬜ |
| T1.1.2 | Crear proyecto con `processing_verb="negociar"` | 👤 | 🏃 | ⬜ | `processing_gerund` = "negociando" | ⬜ |
| T1.1.3 | spaCy conjugation: population="recicladores" + verb="resolver" | 🤖 | 🏃 | ⬜ | `processing_verb_conjugated` = "resuelven" | ⬜ |
| T1.1.4 | spaCy conjugation: English population + English verb | 🤖 | 🏃 | ⬜ | No conjugation applied | ⬜ |
| T1.1.11 | spaCy singular detection: "una escuela" → warning | 🤖 | 🏃 | ⬜ | `population_warning` en JSONB | ⬜ |
| T1.1.14 | `processing_verb_conjugated` se persiste | 👤 | 🏃 | ⬜ | Crear proyecto → verificar campo | ⬜ |
| T1.1.5 | Nemotrón genera RQ con `{processing_verb}` inyectado | 👤 | 🏃 | 🔵×1 | RQ contiene el verbo correcto | ⬜ |
| T1.1.6 | Nemotrón critic evalúa RQ+OQ | 👤 | 🏃 | 🔵×1 | Verdict SAT\|MOD\|FORCED | ⬜ |
| T1.1.7 | population_generalizer fuerza plural | 👤 | 🏃 | 🔵×1 | "un salón de clases" → "docentes y estudiantes" | ⬜ |
| T1.1.10 | `generalize_population` endpoint re-runs generalizer | 👤 | 🏃 | 🔵×1 | `population_assumption` actualizado | ⬜ |
| T1.1.12 | Nemotrón OQ es SINGULAR | 👤 | 🏃 | 🔵×1 | OQ no contiene plural del patrón | ⬜ |
| T1.1.8 | Frontend hints dinámicos: cambiar object_of_study | 👤 | 🏃 | ⬜ | Hint cambia según tipo seleccionado | ⬜ |
| T1.1.9 | Frontend RQ preview: llenar población + verbo | 👤 | 🏃 | ⬜ | Preview se actualiza en vivo | ⬜ |
| T1.1.13 | Processing verb defaults: concern→emotion cambia default | 👤 | 🏃 | ⬜ | Frontend actualiza default del verbo | ⬜ |

---

## 🚶 FASE MODERADA 1: Phase A — Pasos Individuales (ATENCIÓN: pueden sumar)

### ⚠️ ADVERTENCIA: Cada sub-test de Phase A puede disparar llamadas API individuales.
### Correr T2.3 + T2.5 juntos = ~135 FLASH calls. Ver BN1 y BN2 arriba.

| # | Test | Quién | Vel | API est. | Qué verificar | Estado |
|---|------|-------|-----|----------|--------------|--------|
| T2.1 | Upload de documento (PDF/TXT) funciona | 👤 | 🏃 | ⬜ | `POST /projects/{id}/documents` → 201 | ⬜ |
| T2.2 | `segmentar_documento` (NLP worker) segmenta y persiste | 👤 | 🚶 | ⬜ | Segmentos con embeddings | ⬜ 18 segmentos |
| T2.3 | `glaser_data_classifier` clasifica segmentos | 👤 | 🚶 | 🔵×18/doc ⛔ | `segmentos.tipo_dato_glaser` poblado | ⬜ 18/18 |
| T2.4 | `glaser_data_classifier` fallback FLASH para borderline | 👤 | 🚶 | 🔵 extra | Logs: "tier=FLASH" para confidence < 0.7 | ⬜ |
| T2.5 | `extract_incident` (FLASH) extrae jots | 👤 | 🚶 | 🔵×~15/doc ⛔ | `extracted_incidents` con jot_text en gerundio | ⬜ 63 incidentes |
| T2.6 | `extract_incident` aplica 4 preguntas de Glaser | 👤 | 🚶 | 🔵×~15/doc | `preguntas_glaser_json` tiene 4 keys | ⬜ |
| T2.7 | `extract_core_pattern` (PRO) sintetiza patrón | 👤 | 🚶 | 🔴×1/doc | `document_processes` actualizado | ⬜ |
| T2.8 | `a1_build_population_context` actualiza cada 3 docs | 👤 | 🚶 | 🔵×1/doc | `population_contexts.version` incrementado | ⬜ v1 creado |
| T2.9 | `a2_identify_process` identifica proceso | 👤 | 🚶 | 🔵×1/doc | `document_processes.process_description` | ⬜ + prime_mover HIGH |

---

## 🚶 FASE MODERADA 2: Tareas Individuales (1-4 API calls cada una)

### 13. Regresiones — Tareas individuales

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T13.4 | `punctuate_text` (Fast worker) funciona | 👤 | 🚶 | 🔵×1 | Texto con puntuación agregada | ⬜ |
| T13.5 | `extract_graph_entities` (Fast worker) funciona | 👤 | 🚶 | 🔵×1 | `graph_entities` + `graph_relations` | ⬜ |
| T13.6 | `a06_theoretical_sample` (TheoSampler) funciona | 👤 | 🚶 | 🔵×1 | Muestreo teórico con ANTI-JOIN | ⬜ |
| T13.7 | `a07_build_evidence_map` funciona | 👤 | 🚶 | ⬜ | Mapa de evidencia categoría × doc | ⬜ |

### 4. Core Category Detection

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T4.1 | `maturity_gate()` se ejecuta antes de selective coding | 👤 | 🏃 | ⬜ | Pipeline log: "maturity gate" | ⬜ |
| T4.2 | `maturity_gate()` bloquea si <3 cats saturadas | 👤 | 🏃 | ⬜ | Proyecto pausa en "checking_maturity" | ⬜ |
| T4.3 | `task_main_concern_pipeline` propone patrón de interés | 👤 | 🚶 | 🔴×2 | HITL gate con candidatos en gerundio | ⬜ |
| T4.5 | `task_core_emergence_pipeline` evalúa centralidad | 👤 | 🚶 | 🔴×2 | HITL gate con centrality scores | ⬜ |
| T4.7 | `selective_coding_coordinator` orquesta fases | 👤 | 🚶 | 🔴×4-6 | Estados de proyecto transicionan | ⬜ |
| T4.8 | `selective_coding_coordinator` crea PipelineTask tracking | 👤 | 🏃 | ⬜ | `pipeline_tasks` con `document_id=NULL` | ⬜ |

### 4.1 Core Pattern Extraction (Fase A4)

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T4.1.1 | `fa_core_pattern_extractor` genera patrón | 👤 | 🚶 | 🔴×1/doc | Patrón en gerundio | ⬜ |
| T4.1.2 | Patrón incluye evidence_quotes[2-5] | 👤 | 🏃 | ⬜ | 2-5 citas de incidentes distintos | ⬜ |
| T4.1.3 | `fa_core_pattern_verifier` corre cada 3 docs | 👤 | 🚶 | 🔴×1 | Verifier tras 3 docs | ⬜ |
| T4.1.4 | Verifier emite recomendación | 👤 | 🏃 | ⬜ | CONTINUE_COLLECTING\|READY\|NEEDS_DIFFERENT | ⬜ |
| T4.1.5 | Verifier dispara HITL gate `pattern_of_interest` | 👤 | 🏃 | ⬜ | Modal HITL con patrón detectado | ⬜ |

### 5. Selective Reduction

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T5.1 | `task_selective_reduction_pipeline` filtra/fusiona | 👤 | 🚶 | 🔴×2 | HITL gate con kept/merged/discarded | ⬜ |

### 11b. Final Report

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T11b.1 | `f6a_final_report` (PRO) genera reporte 8 secciones | 👤 | 🚶 | 🔴×1 | Reporte estructurado con 8 headings | ⬜ |
| T11b.2 | Abstract 180-220 palabras | 👤 | 🏃 | ⬜ | Conteo de palabras dentro del rango | ⬜ |
| T11b.3 | Headings adaptados a `{object_of_study}` | 👤 | 🏃 | ⬜ | "Core Emotion" vs "Core Concern" | ⬜ |
| T11b.4 | Título: "{Core Pattern} — A Classic Grounded Theory..." | 👤 | 🏃 | ⬜ | Formato de título correcto | ⬜ |
| T11b.5 | Reporte se almacena en `final_reports` table | 👤 | 🏃 | ⬜ | O fallback graceful si tabla no existe | ⬜ |

### 9. Redacción Natural

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T9.1 | `natural_writer` (PRO) redacta desde memos | 👤 | 🚶 | 🔴×1 | draft + citations + concepts | ⬜ |
| T9.2 | `writing_critic` (PRO) evalúa borrador | 👤 | 🚶 | 🔴×1 | Issues: tense, subject, citation, fidelity | ⬜ |
| T9.3 | `gap_feeler` (FLASH) detecta huecos | 👤 | 🚶 | 🔵×1 | Gaps sin bloquear escritura | ⬜ |

### 9.1 Gap Feeler + Memo Tagger

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T9.1.1 | `f6a_gap_feeler` (FLASH) detecta huecos | 👤 | 🚶 | 🔵×1 | MISSING_EVIDENCE, UNDERDEVELOPED_PROPERTY | ⬜ |
| T9.1.2 | Gap feeler no bloquea — acumula señales | 👤 | 🏃 | ⬜ | Escritura continúa aunque haya gaps | ⬜ |
| T9.1.3 | `f6b_memo_theoretical_tagger` clasifica memos | 👤 | 🚶 | 🔵×N | Memos en 12 familias canónicas | ⬜ |
| T9.1.4 | Solo familias con score ≥ 0.3 en output | 👤 | 🏃 | ⬜ | Familias bajo umbral no incluidas | ⬜ |

### 10. Diálogo con Literatura

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T10.1 | `literature_comparer` (PRO) tabla Extiende/Modifica/Integra/Trasciende | 👤 | 🚶 | 🔴×1 | Tabla con 4 columnas | ⬜ |
| T10.2 | `literature_critic` (PRO) detecta forcing/authority bias | 👤 | 🚶 | 🔴×1 | Issues[] en response | ⬜ |

### 11. Aplicabilidad

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T11.1 | `applicability_engine` (PRO) identifica variables | 👤 | 🚶 | 🔴×1 | `control_variables[]` + `access_variables[]` | ⬜ |
| T11.2 | `applicability_critic` (PRO) evalúa genuinidad | 👤 | 🚶 | 🔴×1 | Issues[] detecta generic/no_limits/jargon | ⬜ |

### 15.3 LLMClient Integration (requiere API key real o mock)

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T15.9 | `LLMClient.run_agent(agent_id, language="es")` pasa language | 🤖 | 🚶 | 🔵×1 | system_prompt contiene language_code | ⬜ |
| T15.10 | `LLMClient.set_user_language("es")` configura idioma global | 👤 | 🚶 | 🔵×1 | Llamadas subsecuentes usan español | ⬜ |
| T15.11 | Código legacy sin `language=` usa default de clase | 🤖 | 🚶 | 🔵×1 | `run_agent("fb_incident_comparator", ...)` → es | ⬜ |

---

## 🐢 FASE LENTA 1: Phase A Pipeline Completo ⛔

### ⛔⛔⛔ CORRER SOLO CON APROBACIÓN DEL USUARIO ⛔⛔⛔
### ~169-187 llamadas API para 5 documentos (FLASH + PRO)
### Archivos: workers/heavy/tasks.py:780-1030, algorithmic_checks.py:230, incident_extractor.py:246

| # | Test | Quién | Vel | API est. | Qué verificar | Estado |
|---|------|-------|-----|----------|--------------|--------|
| T2.11 | `process_document_agents_a` ejecuta A1→A2→A3 completo | 👤 | 🐢 | 🔵~157 + 🔴~12 ⛔ | 1 doc → A1+A2. 3+ docs → A1+A2+A3 | ⬜ |

---

## 🐢 FASE LENTA 2: Phase B — Síntesis Cross-Document

### ~6-8 llamadas PRO (con pre-filtro embedding que reduce 97% de pares)

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T3.1 | `b1_compare_incidents` (PRO) compara incidentes | 👤 | 🐢 | 🔴×~3 batches | `incident_comparisons` poblado | ⬜ |
| T3.2 | `b1_compare_incidents` incremental funciona | 👤 | 🚶 | 🔴×1 | Segunda ejecución solo nuevos | ⬜ |
| T3.3 | `b2_label_groups` (PRO + SelfRefinement) etiqueta | 👤 | 🐢 | 🔴×1-3 | `incident_groups.label` y `.definition` | ⬜ |
| T3.4 | `b2_label_groups` loop B2↔B3 máx 3 iteraciones | 👤 | 🐢 | 🔴×~3 | Logs: "SelfRefinement iteration X/3" | ⬜ |
| T3.5 | `b3_critique_labels` (FLASH) emite SAT/MOD/FORCED | 👤 | 🚶 | 🔵×1 | `incident_groups.critic_verdict` | ⬜ |
| T3.6 | `process_synthesis_agents_b` ejecuta B1→B2→B2.5→B3 | 👤 | 🐢 | 🔴×~6 + 🔵×1 | Pipeline log muestra orden correcto | ⬜ |
| T3.8 | Legacy `b1_distill_sampling` emite DeprecationWarning | 👤 | 🏃 | ⬜ | Redirect a b1_compare_incidents | ⬜ |
| T3.9 | Legacy `b2_open_code` emite DeprecationWarning | 👤 | 🏃 | ⬜ | Redirect a b2_label_groups | ⬜ |

### Fase A/B — Every-3-Doc Pause

| # | Test | Quién | Vel | Qué verificar |
|---|------|-------|-----|--------------|
| T3.10 | Phase B triggers automatically when 3 docs reach 'listo' | 👤 | 🐢 | `process_synthesis_agents_b` dispatched |
| T3.11 | Phase B triggers for last incomplete batch (1-2 docs) | 👤 | 🐢 | Guardrail allows <3 docs when all are listo |
| T3.12 | Synthesizer 1 merges categories after batch | 👤 | 🐢 | Previous + new categories unified |
| T3.13 | Synthesizer 2 updates hypotheses after synthesizer 1 | 👤 | 🐢 | Growing hypothesis note with references |
| T3.14 | Configuration Critic reviews concerns, population, coding style | 👤 | 🐢 | concerns[], population_variants[], coding_style_rec returned |
| T3.15 | HITL overlay shows unified category set + hypotheses + concerns + population + coding style | 👤 | 🐢 | All options visible in modal |
| T3.16 | User can select multiple concerns during early batches | 👤 | 🐢 | Multi-select works |
| T3.17 | User can keep current population/concern/style selection | 👤 | 🐢 | "Mantener selección actual" option works |
| T3.18 | After selecting "no volver a preguntar", config locks for remaining batches | 👤 | 🐢 | Config frozen, no more HITL for config |

### 15.4 Pre-filtro B1 + Batching

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T15.12 | B1 comparator usa pre-filtro embedding (cosine > 0.75) | 👤 | 🐢 | 🔴×batches | Log: "Pre-filter: X/Y pairs survive" | ⬜ |
| T15.13 | B1 batch size = 25 pares por llamada LLM | 👤 | 🐢 | 🔴×batches | Log: "N candidate pairs -> M LLM batches" | ⬜ |
| T15.14 | B1 Union-Find agrupa pares intercambiables | 👤 | 🐢 | ⬜ | `incident_groups` con >= 2 incidentes | ⬜ |
| T15.15 | B1 total pairs 9870 → pre-filter 295 (3.0%) | 👤 | 🐢 | 🔴×~12 | Reducción ~97% sin LLM | ⬜ |

---

## 🐢 FASE LENTA 3: Core Saturation Loop + Database A/B

### ⚠️ Puede disparar 8-40 llamadas adicionales según estado de señales

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T6.1 | Señal matemática (rolling_std) se consulta primero | 👤 | 🏃 | ⬜ | SQL query a `saturation_metrics` | ⬜ |
| T6.2 | Señal cualitativa (paradigm window 5) se consulta | 👤 | 🏃 | ⬜ | SQL query a `paradigm_states` | ⬜ |
| T6.3 | Señal cobertura (paradigm_snapshot props) se calcula | 👤 | 🏃 | ⬜ | JSONB parse de `paradigm_snapshot` | ⬜ |
| T6.4 | Señal integración (conceptual_relationships count) | 👤 | 🏃 | ⬜ | SQL COUNT con `category_ids @>` | ⬜ |
| T6.5 | LLM se salta si las 4 señales no son estables | 👤 | 🐢 | variable | Log: "llm_skipped: true" | ⬜ |
| T6.6 | `saturation_panel_json` se actualiza en `categorias` | 👤 | 🏃 | ⬜ | Columna JSONB poblada con 4 señales | ⬜ |
| T6.7 | `GET /projects/{id}/saturation-panel` devuelve panel | 👤 | 🏃 | ⬜ | Endpoint F5.2 con 4 señales | ⬜ |
| T6.8 | TheoSampler se activa condicionalmente | 👤 | 🐢 | 🔵×1 | Log: "TheoSampler activated" | ⬜ |
| T6.9 | MemoMaker se dispara al saturar categoría | 👤 | 🐢 | 🔵×1 | `memos` con `structured_fields` | ⬜ |
| T6.10 | `task_core_saturation_loop` abort check | 👤 | 🐢 | variable | `pipeline_tasks.status='cancelled'` | ⬜ |

### 7. Database A/B (requiere fases previas completas)

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T7.1 | `task_database_a_pipeline` persiste nodos SIEMPRE | 👤 | 🐢 | 🔴×2 | `database_nodes` con filas | ⬜ |
| T7.2 | `task_database_b_pipeline` persiste edges SIEMPRE | 👤 | 🐢 | 🔴×2 | `database_edges` con filas | ⬜ |
| T7.1.1 | `ff_database_a_proposer` transforma categorías en nodos | 👤 | 🐢 | 🔴×1 | entity_type correcto por nodo | ⬜ |
| T7.1.2 | `ff_database_a_critic` evalúa nodos | 👤 | 🐢 | 🔴×1 | Verdict SAT\|MOD\|FORCED | ⬜ |
| T7.1.3 | `ff_database_b_proposer` genera PROCESSES edge | 👤 | 🐢 | 🔴×1 | Al menos un edge PROCESSES | ⬜ |
| T7.1.4 | `ff_database_b_critic` detecta contradicciones | 👤 | 🐢 | 🔴×1 | Issues[] con contradictions + missing_edges | ⬜ |

### 7.2 Core Category Selection (Guardrails + HITL)

| # | Test | Quién | Vel | Qué verificar |
|---|------|-------|-----|--------------|
| T7.3 | Guardrail 1: blocks if ≠1 confirmed concern | 👤 | 🐢 | Error message shown |
| T7.4 | Guardrail 2: blocks if categories lack concern_label | 👤 | 🐢 | Unlinked categories listed |
| T7.5 | Core Category Proposer ranks candidates by hypothesis connections | 👤 | 🐢 | Candidates with centrality scores |
| T7.6 | User selects ONE core category → unlocks selective coding | 👤 | 🐢 | HITL gate resolved, pipeline advances |

### 8. Theoretical Playground (requiere fases previas)

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T8.1 | `GET /projects/{id}/theory` carga ecosistema | 👤 | 🏃 | ⬜ | Blobs + tendrils + ghosts | ⬜ |
| T8.2 | `conceptual_elaborator` propone relaciones | 👤 | 🚶 | 🔴×1 | `conceptual_relationships` nueva fila | ⬜ |
| T8.3 | `ghost_blob_mapper` absorbe memos huérfanos | 👤 | 🚶 | 🔵×1 | Memo vinculado a categoría | ⬜ |
| T8.4 | `memo_theoretical_tagger` (FLASH) clasifica memos | 👤 | 🚶 | 🔵×N | `memo_sorting_attempts` | ⬜ |
| T8.5 | `memo_theoretical_tagger` en `_prepare_playground_for_project` | 👤 | 🐢 | 🔵×N | Todos los memos con tag | ⬜ |
| T8.6 | `f6b_gap_alerter` se despacha si ≥3 ghost blobs | 🤖 | 🏃 | ⬜ | gap_alerter con gaps_summary | ⬜ |
| T8.7 | `ecosystem_gap_detector` cuenta ghost blobs huérfanos | 🤖 | 🏃 | ⬜ | SQL query retorna conteo | ⬜ |

---

## 🐢 FASE LENTA 4: Transversales con API

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T12.3 | `hitl_gate()` crea `hitl_decisions` y publica Redis | 👤 | 🏃 | ⬜ | Redis `PUBLISH project:{id}:events` | ⬜ |
| T12.4 | `transition_project()` publica Redis | 👤 | 🏃 | ⬜ | Redis event type=project_state_changed | ⬜ |
| T12.5 | `POST /modification/apply` aplica modificación HITL | 👤 | 🚶 | 🔴×1-2 | HITLModificationAgent P5: filter→plan→execute | ⬜ |
| T12.6 | `evaluate_respec_signals` detecta 5 tipos | 👤 | 🚶 | 🔵×1 | ambiguous_incidents, rejected_labels, etc | ⬜ |
| T12.7 | `query_lower_level` baja de categoría → incidentes | 👤 | 🏃 | ⬜ | Incidentes vinculados a la categoría | ⬜ |
| T12.8 | `query_lower_level` baja de relación → categorías | 👤 | 🏃 | ⬜ | category_ids + converging/diverging | ⬜ |
| T12.9 | PipelineTask tracking para tareas de proyecto | 👤 | 🏃 | ⬜ | `pipeline_tasks` con `document_id=NULL` | ⬜ |
| T12.10 | `AbortableTask.on_failure` marca pipeline_tasks failed | 👤 | 🏃 | ⬜ | `pipeline_tasks.status='failed'` | ⬜ |

### 13. Regresiones — Tareas que requieren pipeline previo

| # | Test | Quién | Vel | API | Qué verificar | Estado |
|---|------|-------|-----|-----|--------------|--------|
| T13.8 | `task_global_saturation_check` funciona | 👤 | 🐢 | 🔴×1 | 3 condiciones globales | ⬜ |
| T13.9 | `_prepare_playground_for_project` funciona | 👤 | 🐢 | 🔵×N | Seeding + ghost mapping + gap detection | ⬜ |
| T13.10 | Frontend Pipeline log streaming funciona | 👤 | 🏃 | ⬜ | Logs en tiempo real en Project.tsx | ⬜ |

---

## 💤 FASE MUY LENTA: Frontend UX — Pipeline Completo (MANUAL — requiere investigador)

> **Recorrido del investigador:** desde que crea un proyecto hasta que ve el Theoretical Playground.
> **Depende de que TODAS las fases del pipeline backend funcionen.**

### 14.1 Navegacion y Autenticacion

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.1 | Login renderiza formulario | 👤 | 🏃 | Campos email + password + boton | ⬜ |
| T14.2 | Register crea cuenta | 👤 | 🏃 | Redirige a /login tras registro | ⬜ |
| T14.3 | Logout limpia token y redirige | 👤 | 🏃 | No accede a /projects sin token | ⬜ |
| T14.4 | Ruta desconocida → /login | 👤 | 🏃 | → | ⬜ |

### 14.2 Proyectos

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.5 | Lista de proyectos | 👤 | 🏃 | Cards con nombre, estado, num_documentos | ⬜ |
| T14.6 | Crear proyecto aparece en lista | 👤 | 🏃 | Nuevo proyecto visible sin recargar | ⬜ |
| T14.7 | Formulario incluye supuesto_poblacional | 👤 | 🏃 | Textarea para descripcion de poblacion | ⬜ |
| T14.8 | Click en proyecto → ProjectDetail | 👤 | 🏃 | URL cambia a /projects/{id} | ⬜ |

### 14.3 Pipeline — Project Detail

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.9 | 9 stages en orden correcto | 👤 | 🏃 | Segmentacion → Open Coding → ... → Playground | ⬜ |
| T14.10 | Stage status cambia con progreso | 👤 | 🏃 | pending → running → done → error | ⬜ |
| T14.11 | Boton Ejecutar Pipeline condicional | 👤 | 🏃 | Deshabilitado si no hay documentos | ⬜ |
| T14.12 | Boton Detener Workers cancela tareas | 👤 | 🏃 | Workers reciben SIGTERM | ⬜ |
| T14.13 | Panel de logs streaming tiempo real | 👤 | 🏃 | Timestamp, autoscroll, colores | ⬜ |
| T14.14 | Upload documento muestra progress | 👤 | 🏃 | File input → progress → doc en lista | ⬜ |
| T14.15 | Documentos muestran estado | 👤 | 🏃 | Badge color: crudo/segmentado/listo/etc | ⬜ |
| T14.16 | Expandir doc muestra segmentos+codigos | 👤 | 🏃 | Lista de segmentos con codigos | ⬜ |
| T14.17 | Toggle vista original vs segmentada | 👤 | 🏃 | Cambia entre texto crudo y segmentos | ⬜ |

### 14.4 HITL Gates (modales)

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.18 | Modal HITL aparece en gates | 👤 | 🏃 | Propuesta del agente + critic verdict | ⬜ |
| T14.19 | Modal muestra Patron de Interes | 👤 | 🏃 | Label F1.1 aplicado | ⬜ |
| T14.20 | Botones Accept/Modify/Reject | 👤 | 🏃 | POST /hitl/{gate}/decide | ⬜ |
| T14.21 | Modify abre textarea feedback | 👤 | 🏃 | Campo texto + boton enviar | ⬜ |
| T14.22 | Modal muestra evidencia | 👤 | 🏃 | Incidentes, scores, rationale | ⬜ |

### 14.5 Theoretical Playground

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.23 | Canvas: blobs + tendrils | 👤 | 🏃 | Nodos y conexiones, colores por capa | ⬜ |
| T14.24 | Click blob → panel detalle | 👤 | 🏃 | Nombre, definicion, saturation_panel | ⬜ |
| T14.25 | Drag & drop blobs persiste | 👤 | 🏃 | Posiciones se guardan | ⬜ |
| T14.26 | Panel Recommendations muestra gaps | 👤 | 🏃 | Lista con severidad critico/warning | ⬜ |
| T14.27 | Boton Sync gaps refresca | 👤 | 🏃 | POST /analysis/saturation-gaps/refresh | ⬜ |
| T14.28 | Banner N docs nuevos | 👤 | 🏃 | Banner purpura + link Expandir analisis | ⬜ |
| T14.29 | RenameModal sugiere nombres IA | 👤 | 🏃 | Modal con sugerencias de renombre | ⬜ |
| T14.30 | Panel historial de cambios | 👤 | 🏃 | Timeline versiones con triggers | ⬜ |

### 14.6 Estados y Edge Cases

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.31 | Proyecto sin documentos | 👤 | 🏃 | Mensaje: No hay documentos | ⬜ |
| T14.32 | Pipeline en error | 👤 | 🏃 | Stage rojo + boton Reintentar | ⬜ |
| T14.33 | Pipeline cancelado limpia estado | 👤 | 🏃 | Stages vuelven, sin tareas huerfanas | ⬜ |
| T14.34 | Refrescar pagina mantiene estado | 👤 | 🏃 | Polling recupera, no empieza de cero | ⬜ |
| T14.35 | Navegar proyectos no mezcla estados | 👤 | 🏃 | Pipeline del proyecto correcto | ⬜ |

### 14.7 Processing Verb + RQ Preview

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.7.1 | Selector object_of_study muestra hint dinámico | 👤 | 🏃 | Hint cambia al seleccionar tipo | ⬜ |
| T14.7.2 | Input processing_verb tiene default por tipo | 👤 | 🏃 | "resolver" para concern | ⬜ |
| T14.7.3 | RQ preview se actualiza al cambiar campos | 👤 | 🏃 | Preview en vivo | ⬜ |
| T14.7.4 | Experimental Mode permite cambiar object_of_study | 👤 | 🏃 | Cambio de tipo → estado "coding" | ⬜ |
| T14.7.5 | Cambiar object_of_study → estado vuelve a "coding" | 👤 | 🏃 | Proyecto reinicia pipeline | ⬜ |

### 14.8 Population Configuration Panel

| # | Test | Quien | Vel | Que verificar | Estado |
|---|------|-------|-----|--------------|--------|
| T14.8.1 | Panel "🧬 Population Configuration" aparece | 👤 | 🏃 | Sección colapsable visible | ⬜ |
| T14.8.2 | Generalized population se muestra como pill | 👤 | 🏃 | Texto de población generalizada | ⬜ |
| T14.8.3 | Botón "Generate" si no hay generalized_population | 👤 | 🏃 | Botón visible, llama a generalize | ⬜ |
| T14.8.4 | Edit inline: Edit → input → Save persiste | 👤 | 🏃 | Edición inline funciona | ⬜ |
| T14.8.5 | Spatial/Temporal frame labels traducidos | 👤 | 🏃 | "cohabiting_group" → "Grupo conviviente" | ⬜ |
| T14.8.6 | Confidence bar coloreada: >=80% verde, >=50% ambar, <50% rojo | 👤 | 🏃 | Barra de confianza con color correcto | ⬜ |

---

## 📊 RESUMEN REORDENADO

| Fase | Secciones | Tests | Velocidad | API calls | Riesgo |
|------|-----------|-------|-----------|-----------|--------|
| ⚡ Rápida 1 | 15, 12.1 | 21 | < 30s | 0 | ✅ Ninguno |
| ⚡ Rápida 2 | 0 | 11 | < 60s | 0 | ✅ Ninguno |
| 🏃 Rápida 3 | 7.1, 0(new schema), 1(schema), 4(static), 2(static), 3(static), 5(static) | 19 | < 60s | 0 | ✅ Ninguno |
| 🏃 Rápida 4 | 12(labels), 13(auth), 1(endpoints), 1.1(verbs) | 30 | < 2min | ~10 FLASH | ✅ Bajo |
| 🚶 Moderada 1 | 2(Phase A individual) | 9 | 2-10min | ~100 FLASH + ~8 PRO | ⛔ ALTO |
| 🚶 Moderada 2 | 13(regr), 4(core), 5(red), 9-11b(writing), 15.3(llm) | 37 | 3-15min | ~30 PRO + ~10 FLASH | ⚠️ Medio |
| 🐢 Lenta 1 | 2.11 (Phase A full) | 1 | 10-30min | ~169-187 total | ⛔ CRÍTICO |
| 🐢 Lenta 2 | 3 (Phase B), 3(AB pause), 15.4 (pre-filtro) | 22 | 5-20min | ~10-15 PRO | ⚠️ Medio |
| 🐢 Lenta 3 | 6 (sat), 7 (DB), 7.2(core sel), 8 (playground) | 27 | 10-40min | ~15-50 variable | ⚠️ Variable |
| 🐢 Lenta 4 | 12 (HITL API), 13 (regr pipeline) | 10 | 5-20min | ~5-10 mixto | ✅ Bajo |
| 💤 Muy Lenta | 14 (frontend UX) | 46 | Manual | 0 (frontend) | ✅ Ninguno |
| **TOTAL** | | **233** | | | |

### 🚨 TESTS QUE REQUIEREN INTERVENCIÓN HUMANA ANTES DE CORRER

| Test | Razón | API calls estimadas |
|------|-------|---------------------|
| **T2.3** | `glaser_data_classifier` per-segmento | ~72-90 FLASH |
| **T2.5** | `extract_incident` per-segmento | ~63 FLASH |
| **T2.11** | Phase A pipeline completo | ~169-187 total |
| **T6.5-T6.10** | Core Saturation Loop | 8-40 variable |
