# GT System — Complete Database Schema Analysis

> **Generated**: 2026-06-21  
> **Source**: `/mnt/hdd/Program Files/Docker/gt/backend/app/models/domain/*.py`  
> **Total Tables**: 46  
> **Total Enum Types**: 5

---

## Table of Contents

1. [Complete Table Catalog](#section-1-complete-table-catalog)
2. [Entity-Relationship Map](#section-2-entity-relationship-map)
3. [Enumeration of All Enum Types](#section-3-enumeration-of-all-enum-types)
4. [Pydantic Schema Catalog](#section-4-pydantic-schema-catalog)

---

## Section 1: Complete Table Catalog

### Base Classes

**File**: `backend/app/models/base.py`

| Class | Purpose |
|---|---|
| `Base` | SQLAlchemy `DeclarativeBase` — root for all ORM models. |
| `TimestampMixin` | Mixin adding `creado_en` and `actualizado_en` timestamps. |

**TimestampMixin columns** (inherited by most models):

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | Creation timestamp (server-side default) |
| `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | Last-update timestamp (auto on flush) |

---

### Table 1: `usuarios` (User)

**File**: `backend/app/models/domain/user.py` — Class: `Usuario`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `nombre` | `String(100)` | NO | — | User's name |
| 3 | `correo` | `String(255)` | NO | — | Email (unique, indexed) |
| 4 | `hashed_password` | `String(255)` | NO | — | Hashed password |
| 5 | `rol` | `Enum(RolDeUsuario, name="rol_usuario_enum")` | NO | `INVESTIGADOR_PRINCIPAL` | User role |
| 6 | `plan` | `Enum(TipoPlanSuscripcion, name="plan_suscripcion_enum")` | NO | `BASICO` | Subscription plan |
| 7 | `tokens_mensuales_usados` | `Integer` | NO | `0` | Monthly token usage |
| 8 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 9 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Indexes**: `correo` (unique + index)

**Relationships**:
- `proyectos` → `Proyecto.creador` (1:N, back_populates="creador")

---

### Table 2: `proyectos` (Project)

**File**: `backend/app/models/domain/project.py` — Class: `Proyecto`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `nombre` | `String(200)` | NO | — | Project name |
| 3 | `ruta_de_codificacion` | `String(50)` | NO | `"ABDUCTIVA_CGT"` | Coding path/strategy |
| 4 | `estado` | `String(50)` | NO | `"collecting"` | Pipeline state: collecting / coding / finding_cc / reducing / saturating / building_db / playground_ready / completed |
| 5 | `supuesto_poblacional` | `Text` | YES | `DEFAULT_POPULATION_ASSUMPTION` | Population assumption text |
| 6 | `config_segmentacion` | `JSONB` | YES | — | ProgressiveSegmenter config: window_size, similarity_threshold, max_tokens, reinert_micro |
| 7 | `population_assumption` | `JSONB` | YES | — | Epistemological config: object_of_study, temporal_frame, spatial_frame, population_description, gerundio_esperado, custom_label, coding_styles |
| 8 | `coding_style_instruction` | `Text` | YES | — | Compiled coding style instruction injected into agent prompts |
| 9 | `object_of_study` | `String(50)` | NO | `"concern"` | concern / emotion / behavior / discourse / identity / custom / meaning |
| 10 | `language` | `String(5)` | NO | `"es"` | LLM output language: es / en / de / pt |
| 11 | `config_mutation_policy` | `JSONB` | YES | — | Per-field mutation policy levels (auto / suggest / require_approval / locked) |
| 12 | `context_window_real` | `Integer` | NO | `150000` | Real context window for project data (tokens) |
| 13 | `batch_number` | `Integer` | NO | `0` | Open coding batch counter |
| 14 | `chosen_concern` | `Text` | YES | — | Concern label chosen in HITL gate |
| 15 | `chosen_population` | `Text` | YES | — | Population description chosen in HITL gate |
| 16 | `pause_mode` | `String(20)` | NO | `"manual"` | Pipeline pause mode: auto / manual |
| 17 | `creador_id` | `UUID` (FK → `usuarios.id`) | NO | — | Creator user |
| 18 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 19 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `creador_id` → `usuarios.id`

**Relationships**:
- `creador` → `Usuario` (M:1, back_populates="proyectos")
- `documentos` → `Documento` (1:N, cascade all delete-orphan)
- `lienzo` → `LienzoDelPlanDeAnalisis` (1:1, cascade)
- `ecosystem_layout` → `EcosystemLayout` (1:1, cascade)
- `config_history` → `ProjectConfigHistory` (1:N, cascade)
- `concerns` → `Concern` (1:N, cascade)

---

### Table 3: `documentos` (Document)

**File**: `backend/app/models/domain/document.py` — Class: `Documento`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `original_filename` | `String(255)` | NO | — | Original file name |
| 4 | `tipo_de_fuente` | `String(50)` | NO | — | Source type: AUDIO_VIDEO, GRUPO_FOCAL, etc. |
| 5 | `ruta_s3` | `String(1000)` | YES | — | S3/MinIO path to raw file |
| 6 | `storage_key` | `String(500)` | NO | — | Storage key (unique) |
| 7 | `mime_type` | `String(100)` | NO | — | MIME type |
| 8 | `size_bytes` | `Integer` | NO | — | File size in bytes |
| 9 | `metadatos` | `JSONB` | NO | `{}` | Flexible metadata (IA summaries, extracted text, etc.) |
| 10 | `sort_order` | `Float` | YES | — | Manual ordering |
| 11 | `estado` | `String(50)` | NO | `"crudo"` | Pipeline state: crudo → preprocesando → preprocesado → segmentando → segmentado → procesando → listo → resumiendo → resumido → sintetizado |
| 12 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 13 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Indexes**: `storage_key` (unique)

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`

**Relationships**:
- `proyecto` → `Proyecto` (M:1, back_populates="documentos")
- `segmentos` → `Segmento` (1:N, cascade)
- `document_processes` → `DocumentProcess` (1:N, cascade, foreign_keys=[DocumentProcess.documento_id])

**Properties**:
- `texto_extraido` → extracted text from `metadatos`
- `texto_preprocesado` → preprocessed text from `metadatos`

---

### Table 4: `categorias` (Category)

**File**: `backend/app/models/domain/category.py` — Class: `Categoria`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `nombre` | `String(200)` | NO | — | Category name |
| 4 | `definicion` | `Text` | NO | — | Category definition |
| 5 | `limites` | `Text` | YES | — | Category boundaries/exclusion criteria |
| 6 | `estado_saturacion` | `String(50)` | NO | `"ABIERTO"` | Saturation state: ABIERTO / ESTABLE / SATURADO / REVISION_FORZADA |
| 7 | `puntaje_relevancia` | `Integer` | NO | `0` | Relevance score |
| 8 | `version` | `Integer` | NO | `1` | Version number |
| 9 | `es_central` | `Boolean` | NO | `False` | Is core category |
| 10 | `embedding_centroide` | `Vector(1024)` (pgvector) | YES | — | Centroid embedding for mathematical saturation |
| 11 | `saturation_docs` | `JSONB` | NO | `[]` | UUIDs of already-saturated documents (TheoSampler ANTI-JOIN) |
| 12 | `parent_category_id` | `UUID` (FK → `categorias.id`) | YES | — | Parent category (self-referential hierarchy) |
| 13 | `source_memo_id` | `UUID` (FK → `memos.id`) | YES | — | Origin memo (NOT NULL = manually created; NULL = agent-generated) |
| 14 | `saturation_panel_json` | `JSONB` | YES | — | Pre-calculated 4-signal saturation panel: matematica, cualitativa, cobertura, integracion |
| 15 | `gerundio_label` | `String(200)` | YES | — | Gerund label proposed by pattern_labeler (B2). e.g. "Negociando permanencia" |
| 16 | `concern_label` | `String(255)` | YES | — | Concern label linking to a gerund concern. Matches Concern.label |
| 17 | `population_label` | `String(255)` | YES | — | Population-level label |
| 18 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 19 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`
- `parent_category_id` → `categorias.id` (self-referential)
- `source_memo_id` → `memos.id`

**Relationships**:
- `doc_codes` → `DocCode` (1:N, cascade)
- `codigos_segmento` → `CodigoSegmento` (1:N, cascade)
- `parent` → `Categoria` (M:1, self-referential, remote_side=[Categoria.id])
- `children` → `Categoria` (1:N, self-referential, cascade)
- `definition_versions` → `CategoryDefinitionVersion` (1:N, cascade)
- `paradigm_states` → `ParadigmState` (1:N, cascade)

---

### Table 5: `doc_codes` (Document–Category Pivot)

**File**: `backend/app/models/domain/category.py` — Class: `DocCode`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `documento_id` | `UUID` (FK → `documentos.id`) | NO (PK) | — | Composite PK: document |
| 2 | `categoria_id` | `UUID` (FK → `categorias.id`) | NO (PK) | — | Composite PK: category |
| 3 | `estado` | `String(50)` | NO | `"presente"` | Status: presente / ausente / no_evaluado |
| 4 | `resumen_evidencia` | `Text` | NO | — | Evidence summary for code assignment |
| 5 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 6 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `documento_id` → `documentos.id`
- `categoria_id` → `categorias.id`

**Relationships**:
- `categoria` → `Categoria` (M:1, back_populates="doc_codes")

**Note**: Composite PK on (documento_id, categoria_id). No direct relationship to Documento defined (only accessed via categoria).

---

### Table 6: `codigos_segmento` (Segment–Category Pivot)

**File**: `backend/app/models/domain/category.py` — Class: `CodigoSegmento`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `segmento_id` | `UUID` (FK → `segmentos.id`) | NO (PK) | — | Composite PK: segment |
| 2 | `categoria_id` | `UUID` (FK → `categorias.id`) | NO (PK) | — | Composite PK: category |
| 3 | `estado` | `String(50)` | NO | `"asignado"` | Status: asignado / confirmado / descartado |
| 4 | `confianza` | `Float` | NO | `1.0` | Confidence 0.0–1.0 |
| 5 | `origen` | `String(50)` | NO | `"manual"` | Origin: manual / ia / recomendacion |
| 6 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 7 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `segmento_id` → `segmentos.id`
- `categoria_id` → `categorias.id`

**Relationships**:
- `segmento` → `Segmento` (M:1, back_populates="codigos")
- `categoria` → `Categoria` (M:1, back_populates="codigos_segmento")

---

### Table 7: `segmentos` (Segment)

**File**: `backend/app/models/domain/segment.py` — Class: `Segmento`

Inherits: `Base` (does NOT use `TimestampMixin`)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `documento_id` | `UUID` (FK → `documentos.id`) | NO | — | Parent document |
| 3 | `texto` | `Text` | NO | — | Segment text content |
| 4 | `parafrasis` | `Text` | YES | — | AI paraphrase |
| 5 | `posicion` | `Integer` | NO | — | Position in original document |
| 6 | `conteo_tokens` | `Integer` | NO | `0` | Token count |
| 7 | `es_anomalia` | `Boolean` | NO | `False` | Is anomaly flag |
| 8 | `tipo_dato_glaser` | `String(50)` | YES | — | Glaser data type: baseline_data / properline_data / interpreted_data / vague_data / interviewer_context |
| 9 | `first_10` | `String(200)` | YES | — | First 10 exact words (anchoring for deterministic reconstruction) |
| 10 | `start_char` | `Integer` | YES | — | Start char position in original text (0-based) |
| 11 | `end_char` | `Integer` | YES | — | End char position in original text (0-based) |
| 12 | `is_exact_match` | `Boolean` | NO | `True` | False if anchor not found (fuzzy fallback) |
| 13 | `embedding` | `Vector(1024)` (pgvector) | YES | — | Semantic embedding (voyage-4-nano) |

**Foreign Keys**:
- `documento_id` → `documentos.id`

**Relationships**:
- `documento` → `Documento` (M:1, back_populates="segmentos")
- `codigos` → `CodigoSegmento` (1:N, cascade)

**Note**: No timestamps inherited — does not use `TimestampMixin`.

---

### Table 8: `memos` (Memo)

**File**: `backend/app/models/domain/memo.py` — Class: `Memo`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `autor_id` | `UUID` (FK → `usuarios.id`) | NO | — | Author user |
| 4 | `tipo` | `String(50)` | NO | — | Memo type: HIPOTESIS / METODOLOGICO / MUESTREO / etc. |
| 5 | `estado` | `String(50)` | NO | `"ABIERTO"` | Status |
| 6 | `contenido` | `Text` | NO | — | Memo content |
| 7 | `es_confidencial` | `Boolean` | NO | `False` | Confidential flag |
| 8 | `hash_tema` | `String(256)` | YES | — | Topic hash |
| 9 | `version` | `Integer` | NO | `1` | Version number |
| 10 | `parent_memo_id` | `UUID` (FK → `memos.id`) | YES | — | Parent memo (versioning chain) |
| 11 | `structured_fields` | `JSONB` | YES | — | Structured fields from MemoMaker: sorting_family, cross_references, tables, correlations, tipologias |
| 12 | `user_created` | `Boolean` | NO | `False` | Whether created by user |
| 13 | `stage_at_creation` | `String(50)` | YES | — | Pipeline stage at creation time |
| 14 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 15 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`
- `autor_id` → `usuarios.id`
- `parent_memo_id` → `memos.id` (self-referential)

**Relationships**: (none explicitly defined on this model — referenced by `Categoria.source_memo_id`, `TheoreticalCode.source_memo_id`, `ElaborationMemo.memo_id`)

---

### Table 9: `concerns` (Concern)

**File**: `backend/app/models/domain/concern.py` — Class: `Concern`

Inherits: `Base` (does NOT use `TimestampMixin`; has own timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`, ON DELETE CASCADE) | NO | — | Parent project |
| 3 | `label` | `String(255)` | NO | — | Gerund concern label. e.g. "Negotiating permanence" |
| 4 | `description` | `Text` | YES | — | Concern description |
| 5 | `status` | `String(50)` | NO | `"candidate"` | candidate / confirmed / rejected |
| 6 | `identified_at_batch` | `Integer` | YES | — | Batch number when identified |
| 7 | `created_at` | `DateTime(timezone=True)` | NO | `func.now()` | Creation timestamp |
| 8 | `updated_at` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | Update timestamp |

**Foreign Keys**:
- `project_id` → `proyectos.id` (ON DELETE CASCADE)

**Relationships**:
- `proyecto` → `Proyecto` (M:1, back_populates="concerns")

---

### Table 10: `population_contexts` (Population Context)

**File**: `backend/app/models/domain/population_context.py` — Class: `PopulationContext`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `surprising_details` | `Text` | NO | `""` | Surprising/differential details about population |
| 4 | `language_patterns` | `Text` | NO | `""` | Language patterns: metaphors, euphemisms, discourse structures |
| 5 | `data_production_context` | `Text` | NO | `""` | Data production context |
| 6 | `source_document_ids` | `JSONB` | NO | `[]` | UUIDs of contributing documents |
| 7 | `version` | `Integer` | NO | `1` | Version number |
| 8 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 9 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`

**Relationships**: (none defined)

---

### Table 11: `extracted_incidents` (Extracted Incident)

**File**: `backend/app/models/domain/incident.py` — Class: `ExtractedIncident`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `segmento_id` | `UUID` (FK → `segmentos.id`) | NO (indexed) | — | Source segment |
| 3 | `documento_id` | `UUID` (FK → `documentos.id`) | NO (indexed) | — | Source document |
| 4 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO (indexed) | — | Parent project |
| 5 | `jot_text` | `Text` | YES | — | Gerund jot: first impression. e.g. "Escaneando el horizonte de amenazas" |
| 6 | `keep_moving` | `Boolean` | NO | `True` | Whether more patterns exist in segment |
| 7 | `tipo_dato_glaser` | `String(50)` | YES | — | baseline / properline / interpreted / vague |
| 8 | `preguntas_glaser_json` | `JSONB` | NO | `{}` | Structured Glaser 4-questions responses: what_is_this_about, what_category, what_is_happening, participants_pattern, confidence |
| 9 | `patrón_documento_id` | `UUID` (FK → `document_processes.id`) | YES | — | Links to per-document core pattern |
| 10 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 11 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `segmento_id` → `segmentos.id`
- `documento_id` → `documentos.id`
- `proyecto_id` → `proyectos.id`
- `patrón_documento_id` → `document_processes.id`

**Indexes**: `segmento_id`, `documento_id`, `proyecto_id`

---

### Table 12: `incident_comparisons` (Incident Comparison)

**File**: `backend/app/models/domain/incident.py` — Class: `IncidentComparison`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `incident_a_id` | `UUID` (FK → `extracted_incidents.id`) | NO | — | First incident |
| 3 | `incident_b_id` | `UUID` (FK → `extracted_incidents.id`) | NO | — | Second incident |
| 4 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO (indexed) | — | Parent project |
| 5 | `similarity_score` | `Float` | NO | `0.0` | Semantic similarity 0.0–1.0 (pre-filter) |
| 6 | `are_interchangeable` | `Boolean` | NO | `False` | Whether incidents measure same underlying phenomenon |
| 7 | `rationale` | `Text` | YES | — | Justification for interchangeability decision |
| 8 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 9 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `incident_a_id` → `extracted_incidents.id`
- `incident_b_id` → `extracted_incidents.id`
- `proyecto_id` → `proyectos.id`

**Indexes**: `proyecto_id`

---

### Table 13: `incident_groups` (Incident Group)

**File**: `backend/app/models/domain/incident.py` — Class: `IncidentGroup`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO (indexed) | — | Parent project |
| 3 | `label` | `String(200)` | YES | — | Gerund label proposed by pattern_labeler |
| 4 | `definition` | `Text` | YES | — | Category definition proposed by pattern_labeler |
| 5 | `status` | `String(50)` | NO | `"open"` | open / labeled / approved / rejected |
| 6 | `incident_ids_json` | `JSONB` | NO | `[]` | UUIDs of incidents in group (weak link, no FK) |
| 7 | `labeled_by_agent` | `String(100)` | YES | — | Agent name that performed labeling |
| 8 | `critic_verdict` | `JSONB` | YES | — | Label critic verdict: verdict(SAT/MOD/FORCED), issues[], all_valid |
| 9 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 10 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`

**Indexes**: `proyecto_id`

---

### Table 14: `code_prototypes` (Code Prototype)

**File**: `backend/app/models/domain/synthesis.py` — Class: `CodePrototype`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `code_id` | `UUID` (FK → `categorias.id`) | NO (PK) | — | Category (PK) |
| 2 | `segment_ids` | `JSONB` | NO | `[]` | Up to 3 exemplary segments |
| 3 | `updated_at` | `String(100)` | YES | — | Update timestamp (string) |

**Foreign Keys**:
- `code_id` → `categorias.id`

---

### Table 15: `code_document_summaries` (Code-Document Summary)

**File**: `backend/app/models/domain/synthesis.py` — Class: `CodeDocumentSummary`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `code_id` | `UUID` (FK → `categorias.id`) | NO (PK) | — | Category (composite PK) |
| 2 | `document_id` | `UUID` (FK → `documentos.id`) | NO (PK) | — | Document (composite PK) |
| 3 | `summary` | `Text` | NO | — | Intra-document qualitative synthesis |
| 4 | `updated_at` | `String(100)` | YES | — | Update timestamp (string) |

**Foreign Keys**:
- `code_id` → `categorias.id`
- `document_id` → `documentos.id`

---

### Table 16: `code_global_summaries` (Code Global Summary)

**File**: `backend/app/models/domain/synthesis.py` — Class: `CodeGlobalSummary`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `code_id` | `UUID` (FK → `categorias.id`) | NO (PK) | — | Category (PK) |
| 2 | `summary` | `Text` | NO | — | Consolidated inter-document synthesis |
| 3 | `version` | `Integer` | NO | `1` | Version number |

**Foreign Keys**:
- `code_id` → `categorias.id`

---

### Table 17: `saturation_metrics` (Saturation Metrics)

**File**: `backend/app/models/domain/synthesis.py` — Class: `SaturationMetrics`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `code_id` | `UUID` (FK → `categorias.id`) | NO (PK) | — | Category (PK) |
| 2 | `centroid` | `Vector(1024)` (pgvector) | NO | — | Average embedding of recent summaries |
| 3 | `rolling_std` | `Float` | NO | `0.0` | Rolling standard deviation |
| 4 | `saturation_status` | `String(50)` | NO | `"unsaturated"` | Saturation status |
| 5 | `documents_since_change` | `Integer` | NO | `0` | Documents processed since last change |

**Foreign Keys**:
- `code_id` → `categorias.id`

---

### Table 18: `hypotheses` (Hypothesis)

**File**: `backend/app/models/domain/synthesis.py` — Class: `Hypothesis`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `code_id` | `UUID` (FK → `categorias.id`) | YES | — | Related category |
| 4 | `text` | `Text` | NO | — | Hypothesis text |
| 5 | `level` | `String(50)` | NO | — | Level: general / specific / emergent |
| 6 | `confidence` | `Float` | NO | `0.0` | Confidence score |
| 7 | `status` | `String(50)` | NO | `"candidate"` | Status |
| 8 | `parent_hypothesis_id` | `UUID` (FK → `hypotheses.id`) | YES | — | Parent hypothesis (Tree of Thoughts) |
| 9 | `concern_labels` | `JSONB` | NO | `[]` | List of concern labels. e.g. ["Negotiating permanence", "Scanning threats"] |
| 10 | `batch_number` | `Integer` | YES | — | Batch number that produced this hypothesis |

**Foreign Keys**:
- `project_id` → `proyectos.id`
- `code_id` → `categorias.id`
- `parent_hypothesis_id` → `hypotheses.id` (self-referential)

---

### Table 19: `processing_states` (Processing State Tracker)

**File**: `backend/app/models/domain/synthesis.py` — Class: `ProcessingState`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `entity_type` | `String(50)` | NO (PK) | — | Entity type: document / segment / code |
| 2 | `entity_id` | `UUID` | NO (PK) | — | Entity ID |
| 3 | `step` | `String(50)` | NO (PK) | — | Step: segmented / coded / synthesized |

**Note**: Composite PK on (entity_type, entity_id, step). Tracks idempotent batch processing.

---

### Table 20: `graph_entities` (Graph Entity)

**File**: `backend/app/models/domain/synthesis.py` — Class: `GraphEntity`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `name` | `String(200)` | NO | — | Entity name |
| 4 | `type` | `String(100)` | NO | — | person / concept / event |
| 5 | `frequency` | `Integer` | NO | `1` | Frequency count |

**Foreign Keys**:
- `project_id` → `proyectos.id`

---

### Table 21: `graph_relations` (Graph Relation)

**File**: `backend/app/models/domain/synthesis.py` — Class: `GraphRelation`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `source_id` | `UUID` (FK → `graph_entities.id`) | NO (PK) | — | Source entity (composite PK) |
| 2 | `target_id` | `UUID` (FK → `graph_entities.id`) | NO (PK) | — | Target entity (composite PK) |
| 3 | `relation_type` | `String(100)` | NO (PK) | — | Relation type (composite PK) |
| 4 | `strength` | `Float` | NO | `1.0` | Relationship strength |

**Foreign Keys**:
- `source_id` → `graph_entities.id`
- `target_id` → `graph_entities.id`

---

### Table 22: `paradigm_states` (Paradigm State)

**File**: `backend/app/models/domain/synthesis.py` — Class: `ParadigmState`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `code_id` | `UUID` (FK → `categorias.id`) | NO | — | Category |
| 3 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 4 | `iteration` | `Integer` | NO | — | Iteration number |
| 5 | `did_state_expand` | `Boolean` | NO | `False` | Whether paradigm state expanded |
| 6 | `expansion_type` | `String(50)` | YES | — | NEW_DIMENSION / NEW_CONDITION / NEW_CONSEQUENCE / NEW_STRATEGY / NONE |
| 7 | `paradigm_snapshot` | `JSONB` | NO | `{}` | dimensions[], conditions[], consequences[], strategies[] |
| 8 | `integration_memo` | `Text` | YES | — | Integration memo text |
| 9 | `metadata_group` | `String(200)` | YES | — | Sampling subgroup |
| 10 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 11 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `code_id` → `categorias.id`
- `proyecto_id` → `proyectos.id`

**Relationships**:
- `category` → `Categoria` (M:1, back_populates="paradigm_states")

---

### Table 23: `agent_outputs` (Agent Output Metadata)

**File**: `backend/app/models/domain/agent_outputs.py` — Class: `AgentOutput`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `output_table` | `String(100)` | NO | — | Table of concrete output: categorias / hypotheses / population_contexts / document_processes / conceptual_relationships |
| 4 | `output_id` | `UUID` | NO | — | Row ID in output_table (polymorphic reference) |
| 5 | `agent_id` | `String(100)` | NO | — | Agent ID: b2b, b3, a1, etc. |
| 6 | `agent_family` | `String(50)` | NO | — | Prompt family: inductive_data / inductive_concepts / descriptive_data / evaluative / structural / elaborative |
| 7 | `agent_tier` | `String(10)` | NO | — | PRO or FLASH |
| 8 | `version` | `Integer` | NO | `1` | Version number |
| 9 | `is_final` | `Boolean` | NO | `True` | False for intermediate loop iterations |
| 10 | `prompt_id` | `String(100)` | YES | — | Prompt file used |
| 11 | `prompt_hash` | `String(64)` | YES | — | SHA-256 of rendered prompt |
| 12 | `loop_log_id` | `UUID` (FK → `agent_loop_logs.id`) | YES | — | If produced by an agentic loop |
| 13 | `iteration_number` | `Integer` | YES | — | Iteration number in loop |
| 14 | `parent_output_id` | `UUID` (FK → `agent_outputs.id`) | YES | — | Previous version (self-reference) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`
- `loop_log_id` → `agent_loop_logs.id`
- `parent_output_id` → `agent_outputs.id` (self-referential)

---

### Table 24: `agent_loop_logs` (Agent Loop Log)

**File**: `backend/app/models/domain/agent_outputs.py` — Class: `AgentLoopLog`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `agent_id` | `String(100)` | NO | — | Agent that executed loop |
| 4 | `pattern` | `String(50)` | NO | — | self_refinement / react / plan_execute / debate / hitl_modification |
| 5 | `iterations` | `Integer` | NO | — | Number of iterations |
| 6 | `total_tokens` | `Integer` | NO | `0` | Total tokens used |
| 7 | `total_cost_est` | `Float` | NO | `0.0` | Estimated cost |
| 8 | `had_reasoning` | `Boolean` | NO | `False` | Whether DeepSeek V4 Pro generated reasoning_content |
| 9 | `tool_calls` | `JSONB` | NO | `[]` | [{tool_name, input, observation, timestamp}] |
| 10 | `llm_calls` | `JSONB` | NO | `[]` | [{tier, model, tokens_in, tokens_out, duration_ms}] |
| 11 | `result_summary` | `Text` | YES | — | First 500 chars of final output |
| 12 | `error` | `Text` | YES | — | Error if loop failed |
| 13 | `started_at` | `String(100)` | NO | — | Start timestamp (ISO string) |
| 14 | `finished_at` | `String(100)` | NO | — | End timestamp (ISO string) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`

---

### Table 25: `output_modifications` (Output Modification History)

**File**: `backend/app/models/domain/agent_outputs.py` — Class: `OutputModification`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `modified_by` | `UUID` (FK → `usuarios.id`) | YES | — | Modifying user |
| 4 | `agent_output_id` | `UUID` (FK → `agent_outputs.id`) | NO | — | Agent output being modified |
| 5 | `user_request` | `Text` | NO | — | What the user asked for |
| 6 | `rewritten_request` | `Text` | YES | — | Reworded by PRO planner |
| 7 | `recommended` | `Boolean` | YES | — | Evaluator verdict |
| 8 | `recommendation_reason` | `Text` | YES | — | Why recommended or not |
| 9 | `recommendation_confidence` | `Float` | YES | — | Evaluator confidence 0–1 |
| 10 | `original_content` | `JSONB` | NO | — | Snapshot before modification |
| 11 | `modified_content` | `JSONB` | YES | — | Modified version (null if not applied) |
| 12 | `evidence_collected` | `JSONB` | NO | `[]` | Evidence from search tools |
| 13 | `verification_plan` | `JSONB` | YES | — | Plan from PRO planner |
| 14 | `applied` | `Boolean` | NO | `False` | Whether user confirmed modification |
| 15 | `applied_at` | `String(100)` | YES | — | ISO timestamp when applied |
| 16 | `wiped_tables` | `JSONB` | NO | `[]` | Tables cleaned as consequence |
| 17 | `pipeline_restarted_from` | `String(100)` | YES | — | Pipeline node where restarted |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`
- `modified_by` → `usuarios.id`
- `agent_output_id` → `agent_outputs.id`

---

### Table 26: `agent_families` (Agent Family Reference)

**File**: `backend/app/models/domain/agent_outputs.py` — Class: `AgentFamilyReference`

Inherits: `Base` (no timestamps)

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `family` | `String(50)` | NO (PK) | — | Primary key: inductive_data / inductive_concepts / descriptive_data / evaluative / structural / elaborative |
| 2 | `label` | `String(100)` | NO | — | Human-readable label in Spanish |
| 3 | `icon` | `String(10)` | NO | — | Emoji icon |
| 4 | `description` | `Text` | NO | — | CGT methodological description |
| 5 | `research_question` | `Text` | NO | — | Key research question addressed |
| 6 | `verification_method` | `Text` | NO | — | How to verify correctness |
| 7 | `accepted_questions` | `JSONB` | NO | — | Examples of accepted questions |
| 8 | `rejected_questions` | `JSONB` | NO | — | Examples of rejected questions and why |
| 9 | `recommended_tools` | `JSONB` | NO | — | Recommended tools for verification |

---

### Table 27: `theoretical_codes` (Theoretical Code)

**File**: `backend/app/models/domain/theory.py` — Class: `TheoreticalCode`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | YES | — | NULL = built-in global; NOT NULL = user-defined |
| 3 | `name` | `String(200)` | NO | — | Code name |
| 4 | `family` | `String(100)` | NO | — | Theoretical family |
| 5 | `description` | `Text` | NO | — | Code description |
| 6 | `glaserian` | `Boolean` | NO | `False` | Glaserian code flag |
| 7 | `user_defined` | `Boolean` | NO | `False` | User-defined flag |
| 8 | `evaluation_logic` | `JSONB` | NO | `{}` | Evaluation logic |
| 9 | `output_schema` | `JSONB` | NO | `{}` | Output schema |
| 10 | `compatible_with` | `JSONB` | NO | `[]` | Compatible code families |
| 11 | `layer` | `String(50)` | NO | — | Visualization layer |
| 12 | `visualization_hint` | `String(50)` | NO | `"tendril"` | Visualization hint |
| 13 | `source_memo_id` | `UUID` (FK → `memos.id`) | YES | — | Origin memo |
| 14 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 15 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`
- `source_memo_id` → `memos.id`

**Relationships**:
- `relationships` → `ConceptualRelationship` (1:N, back_populates="theoretical_code")

---

### Table 28: `category_definition_versions` (Category Definition Version History)

**File**: `backend/app/models/domain/theory.py` — Class: `CategoryDefinitionVersion`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `category_id` | `UUID` (FK → `categorias.id`) | NO | — | Category |
| 3 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 4 | `version` | `Integer` | NO | — | Version number |
| 5 | `name_at_version` | `String(200)` | NO | — | Category name at this version |
| 6 | `definition_at_version` | `Text` | NO | — | Definition at this version |
| 7 | `properties_at_version` | `JSONB` | NO | `{}` | Properties at this version |
| 8 | `incident_count_at_version` | `Integer` | NO | `0` | Incident count at this version |
| 9 | `trigger` | `String(50)` | NO | — | Trigger: manual_edit / ghost_absorbed / relationship_elaborated / rename_applied / incident_converged / incident_diverged_property / incident_diverged_dimension |
| 10 | `trigger_detail` | `Text` | YES | — | Additional trigger detail |
| 11 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 12 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `category_id` → `categorias.id`
- `project_id` → `proyectos.id`

**Relationships**:
- `category` → `Categoria` (M:1, back_populates="definition_versions")

---

### Table 29: `conceptual_relationships` (Conceptual Relationship)

**File**: `backend/app/models/domain/theory.py` — Class: `ConceptualRelationship`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `category_ids` | `JSONB` | NO | `[]` | Category IDs involved |
| 4 | `theoretical_code_id` | `UUID` (FK → `theoretical_codes.id`) | NO | — | Theoretical code |
| 5 | `researcher_question` | `Text` | NO | — | Researcher's question |
| 6 | `elaboration_status` | `String(50)` | NO | `"emerging"` | Elaboration status |
| 7 | `direction` | `String(100)` | YES | — | Relationship direction |
| 8 | `converging_incident_ids` | `JSONB` | NO | `[]` | Converging incident IDs |
| 9 | `converging_doc_count` | `Integer` | NO | `0` | Converging document count |
| 10 | `diverging_incident_ids` | `JSONB` | NO | `[]` | Diverging incident IDs |
| 11 | `diverging_doc_count` | `Integer` | NO | `0` | Diverging document count |
| 12 | `divergence_resolution` | `Text` | YES | — | Divergence resolution text |
| 13 | `origin_memo_ids` | `JSONB` | NO | `[]` | Origin memo IDs |
| 14 | `origin_hypothesis_ids` | `JSONB` | NO | `[]` | Origin hypothesis IDs |
| 15 | `conceptual_fit` | `Float` | NO | `0.0` | Conceptual fit score |
| 16 | `layer` | `String(50)` | YES | — | Layer |
| 17 | `position_tension` | `Float` | NO | `0.0` | Position tension |
| 18 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 19 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`
- `theoretical_code_id` → `theoretical_codes.id`

**Relationships**:
- `theoretical_code` → `TheoreticalCode` (M:1, back_populates="relationships")

---

### Table 30: `elaboration_memos` (Elaboration Memo)

**File**: `backend/app/models/domain/theory.py` — Class: `ElaborationMemo`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `elaboration_type` | `String(50)` | NO | — | relationship_proposed / divergence_expanded / ghost_absorbed / rename_applied / definition_expanded / sampling_recommended |
| 4 | `relationship_id` | `UUID` (FK → `conceptual_relationships.id`) | YES | — | Related conceptual relationship |
| 5 | `category_id` | `UUID` (FK → `categorias.id`) | YES | — | Related category |
| 6 | `memo_id` | `UUID` (FK → `memos.id`) | YES | — | Related base memo |
| 7 | `content` | `Text` | NO | — | Memo content |
| 8 | `ecosystem_snapshot` | `JSONB` | NO | `{}` | Ecosystem state snapshot |
| 9 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 10 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`
- `relationship_id` → `conceptual_relationships.id`
- `category_id` → `categorias.id`
- `memo_id` → `memos.id`

---

### Table 31: `ecosystem_layouts` (Ecosystem Layout)

**File**: `backend/app/models/domain/theory.py` — Class: `EcosystemLayout`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`, UNIQUE) | NO | — | Parent project (1:1) |
| 3 | `version` | `Integer` | NO | `1` | Layout version |
| 4 | `blob_positions` | `JSONB` | NO | `{}` | Blob positions |
| 5 | `ghost_positions` | `JSONB` | NO | `{}` | Ghost blob positions |
| 6 | `fog_zones` | `JSONB` | NO | `{}` | Fog zone definitions |
| 7 | `physics_params` | `JSONB` | NO | `{}` | Physics parameters |
| 8 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 9 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id` (UNIQUE)

**Relationships**:
- `proyecto` → `Proyecto` (M:1, back_populates="ecosystem_layout")

---

### Table 32: `lienzos` (Analysis Canvas)

**File**: `backend/app/models/domain/canvas.py` — Class: `LienzoDelPlanDeAnalisis`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`, UNIQUE) | NO | — | Parent project (1:1) |
| 3 | `version_lienzo` | `Integer` | NO | `1` | Canvas version |
| 4 | `esta_bloqueado` | `Boolean` | NO | `False` | Whether locked |
| 5 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 6 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id` (UNIQUE)

**Relationships**:
- `proyecto` → `Proyecto` (M:1, back_populates="lienzo")
- `nodos` → `NodoDeLienzo` (1:N, cascade)
- `bordes` → `BordeDeLienzo` (1:N, cascade)

---

### Table 33: `nodos_lienzo` (Canvas Node)

**File**: `backend/app/models/domain/canvas.py` — Class: `NodoDeLienzo`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `lienzo_id` | `UUID` (FK → `lienzos.id`) | NO | — | Parent canvas |
| 3 | `tipo` | `String(50)` | NO | — | FUENTE_DE_DATOS / FASE / PUERTA_DE_DECISION |
| 4 | `etiqueta` | `String(200)` | NO | — | Node label |
| 5 | `estado` | `String(50)` | NO | `"NO_INICIADO"` | Node state |
| 6 | `pos_x` | `Float` | NO | `0.0` | X position |
| 7 | `pos_y` | `Float` | NO | `0.0` | Y position |
| 8 | `parametros_configuracion` | `JSONB` | NO | `{}` | Configuration parameters |
| 9 | `es_obligatorio` | `Boolean` | NO | `True` | Is mandatory |
| 10 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 11 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `lienzo_id` → `lienzos.id`

**Relationships**:
- `lienzo` → `LienzoDelPlanDeAnalisis` (M:1, back_populates="nodos")

---

### Table 34: `bordes_lienzo` (Canvas Edge)

**File**: `backend/app/models/domain/canvas.py` — Class: `BordeDeLienzo`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `lienzo_id` | `UUID` (FK → `lienzos.id`) | NO | — | Parent canvas |
| 3 | `nodo_origen_id` | `UUID` (FK → `nodos_lienzo.id`) | NO | — | Source node |
| 4 | `nodo_destino_id` | `UUID` (FK → `nodos_lienzo.id`) | NO | — | Destination node |
| 5 | `tipo_de_dato` | `String(100)` | YES | — | Data type on edge |
| 6 | `es_condicional` | `Boolean` | NO | `False` | Is conditional |
| 7 | `expresion_condicional` | `String(500)` | YES | — | Conditional expression |
| 8 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 9 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `lienzo_id` → `lienzos.id`
- `nodo_origen_id` → `nodos_lienzo.id`
- `nodo_destino_id` → `nodos_lienzo.id`

**Relationships**:
- `lienzo` → `LienzoDelPlanDeAnalisis` (M:1)
- `nodo_origen` → `NodoDeLienzo` (M:1, foreign_keys=[nodo_origen_id])
- `nodo_destino` → `NodoDeLienzo` (M:1, foreign_keys=[nodo_destino_id])

---

### Table 35: `hitl_decisions` (HITL Decision)

**File**: `backend/app/models/domain/hitl_decision.py` — Class: `HitlDecision`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `gate_name` | `String(100)` | NO | — | pattern_of_interest / core_category / selective_reduction / core_saturation / database_a / database_b / global_saturation |
| 4 | `proposal` | `JSONB` | NO | — | Proposer output |
| 5 | `critic_verdict` | `JSONB` | NO | — | Critic output: verdict (SAT/MOD/FORCED), rationale, suggestions |
| 6 | `status` | `String(20)` | NO | `"pending"` | pending / accepted / modified / rejected |
| 7 | `researcher_decision` | `String(20)` | YES | — | accept / modify / reject |
| 8 | `researcher_note` | `Text` | YES | — | Researcher note |
| 9 | `researcher_feedback` | `Text` | YES | — | Feedback for re-execution (MODIFY only) |
| 10 | `decided_at` | `DateTime` | YES | — | Decision timestamp |
| 11 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 12 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`

---

### Table 36: `pipeline_runs` (Pipeline Run)

**File**: `backend/app/models/domain/pipeline_run.py` — Class: `PipelineRun`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `status` | `String(20)` | NO | `"running"` | running / completed / cancelled / failed |
| 4 | `triggered_by` | `String(50)` | NO | `"user"` | user / auto |
| 5 | `summary` | `JSONB` | NO | `{}` | {total_docs, need_segment, need_agents, already_done} |
| 6 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 7 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`

---

### Table 37: `pipeline_tasks` (Pipeline Task)

**File**: `backend/app/models/domain/pipeline_run.py` — Class: `PipelineTask`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `run_id` | `UUID` (FK → `pipeline_runs.id`) | NO | — | Parent pipeline run |
| 3 | `document_id` | `UUID` (FK → `documentos.id`) | YES | — | Target document |
| 4 | `celery_task_id` | `String(100)` | NO | — | Celery task ID (unique) |
| 5 | `task_name` | `String(100)` | NO | — | segmentar_documento / process_document_agents_a / punctuate_text / etc. |
| 6 | `queue` | `String(20)` | NO | `"heavy"` | nlp / fast / heavy |
| 7 | `status` | `String(20)` | NO | `"queued"` | queued / running / completed / cancelled / failed |
| 8 | `doc_estado_before` | `String(50)` | YES | — | Document state BEFORE execution (for rollback) |
| 9 | `segments_before` | `Integer` | NO | `0` | Segments before execution |
| 10 | `codes_before` | `Integer` | NO | `0` | Codes before execution |
| 11 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 12 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `run_id` → `pipeline_runs.id`
- `document_id` → `documentos.id`

**Indexes**: `celery_task_id` (unique)

---

### Table 38: `task_step_checkpoints` (Task Step Checkpoint)

**File**: `backend/app/models/domain/pipeline_run.py` — Class: `TaskStepCheckpoint`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `pipeline_task_id` | `UUID` (FK → `pipeline_tasks.id`) | YES | — | Parent task |
| 3 | `document_id` | `UUID` (FK → `documentos.id`) | YES | — | Target document |
| 4 | `step_name` | `String(100)` | NO | — | a1_population_context / segmentation / anchoring / a2_identify_process / extract_prime_mover / a3_make_sense / b2_open_code / b3_hypotheses / punctuation / etc. |
| 5 | `status` | `String(20)` | NO | `"in_progress"` | in_progress / completed / failed |
| 6 | `affected_rows` | `JSONB` | NO | `{}` | Snapshot of inserted/modified rows for cleanup on resume |
| 7 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 8 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `pipeline_task_id` → `pipeline_tasks.id`
- `document_id` → `documentos.id`

---

### Table 39: `batch_executions` (Batch Execution)

**File**: `backend/app/models/domain/pipeline_run.py` — Class: `BatchExecution`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `agent_id` | `String(100)` | NO | — | Agent run in batch: open_coding / memo_proposer / etc. |
| 4 | `total_items` | `Integer` | NO | — | Total items to process |
| 5 | `batches` | `Integer` | NO | — | Number of batches |
| 6 | `items_per_batch` | `Integer` | NO | — | Average items per batch |
| 7 | `tokens_per_batch` | `Integer` | NO | `0` | Estimated tokens per batch |
| 8 | `map_strategy` | `String(30)` | NO | — | ai_only / map_reduce / hybrid_react |
| 9 | `status` | `String(20)` | NO | `"running"` | running / completed / failed |
| 10 | `started_at` | `DateTime(timezone=True)` | YES | — | Start timestamp |
| 11 | `finished_at` | `DateTime(timezone=True)` | YES | — | End timestamp |
| 12 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 13 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`

---

### Table 40: `document_processes` (Document Process)

**File**: `backend/app/models/domain/document_process.py` — Class: `DocumentProcess`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `documento_id` | `UUID` (FK → `documentos.id`) | NO | — | Parent document |
| 3 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 4 | `process_description` | `Text` | NO | — | Central process in gerund. e.g. "Negociando permanencia en la plataforma" |
| 5 | `similarity_to_previous` | `Text` | YES | — | How this document's process resembles the previous one |
| 6 | `difference_from_previous` | `Text` | YES | — | How this document's process differs from the previous one |
| 7 | `previous_document_id` | `UUID` (FK → `documentos.id`) | YES | — | Previous document in processing sequence |
| 8 | `prime_mover` | `Text` | YES | — | Prime mover (gerund) extracted from baseline_data only |
| 9 | `prime_mover_confidence` | `String(10)` | YES | — | HIGH / MEDIUM / LOW |
| 10 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 11 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `documento_id` → `documentos.id`
- `proyecto_id` → `proyectos.id`
- `previous_document_id` → `documentos.id`

**Relationships**:
- `documento` → `Documento` (M:1, foreign_keys=[documento_id], back_populates="document_processes")
- `previous_document` → `Documento` (M:1, foreign_keys=[previous_document_id])

---

### Table 41: `database_nodes` (Database Node)

**File**: `backend/app/models/domain/database.py` — Class: `DatabaseNode`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `category_id` | `UUID` (FK → `categorias.id`) | YES | — | Linked category |
| 4 | `label` | `String(200)` | NO | — | Node label |
| 5 | `entity_type` | `String(50)` | NO | — | PROCESS / ACTOR / CONDITION / CONSEQUENCE / CONTEXT / STRATEGY |
| 6 | `definition` | `Text` | NO | — | Node definition |
| 7 | `is_core` | `Boolean` | NO | `False` | Is core node |
| 8 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 9 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`
- `category_id` → `categorias.id`

---

### Table 42: `database_edges` (Database Edge)

**File**: `backend/app/models/domain/database.py` — Class: `DatabaseEdge`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `project_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `source_node_id` | `UUID` (FK → `database_nodes.id`) | NO | — | Source node |
| 4 | `target_node_id` | `UUID` (FK → `database_nodes.id`) | NO | — | Target node |
| 5 | `relationship_type` | `Text` | NO | — | Free-text theoretical relationship description |
| 6 | `description` | `Text` | NO | `""` | Complete free-text relationship description from proposer |
| 7 | `evidence` | `Text` | NO | — | Evidence |
| 8 | `direction` | `String(20)` | NO | `"unidirectional"` | Direction |
| 9 | `strength` | `String(20)` | NO | `"moderate"` | weak / moderate / strong |
| 10 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 11 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `project_id` → `proyectos.id`
- `source_node_id` → `database_nodes.id`
- `target_node_id` → `database_nodes.id`

---

### Table 43: `project_config_history` (Project Config History)

**File**: `backend/app/models/domain/project_config_history.py` — Class: `ProjectConfigHistory`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `field` | `String(100)` | NO | — | Field modified. e.g. "population_assumption.temporal_frame" |
| 4 | `old_value` | `Text` | YES | — | Previous value (serialized). NULL = creation |
| 5 | `new_value` | `Text` | NO | — | New value (serialized) |
| 6 | `triggered_by` | `String(50)` | NO | `"user"` | user / agent name / system |
| 7 | `agent_run_id` | `String(100)` | YES | — | Pipeline run or task ID if agent-triggered |
| 8 | `mutation_level` | `String(20)` | YES | — | Policy level: auto / suggest / require_approval / locked |
| 9 | `rationale` | `Text` | YES | — | Change justification |
| 10 | `confidence` | `Float` | YES | — | Agent confidence 0.0–1.0. NULL if manual |
| 11 | `context` | `JSONB` | YES | — | Additional context (docs, full diff) |
| 12 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 13 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`

**Relationships**:
- `proyecto` → `Proyecto` (M:1, back_populates="config_history")

---

### Table 44: `fases` (Phase)

**File**: `backend/app/models/domain/workflow.py` — Class: `Fase`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO | — | Parent project |
| 3 | `nodo_lienzo_id` | `UUID` (FK → `nodos_lienzo.id`) | YES | — | Linked canvas node |
| 4 | `numero` | `String(20)` | NO | — | Phase number |
| 5 | `nombre` | `String(200)` | NO | — | Phase name |
| 6 | `estado` | `String(50)` | NO | `"PENDIENTE"` | Phase state |
| 7 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 8 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`
- `nodo_lienzo_id` → `nodos_lienzo.id`

**Relationships**:
- `proyecto` → `Proyecto` (M:1)

---

### Table 45: `memo_sorting_attempts` (Memo Sorting Attempt)

**File**: `backend/app/models/domain/sorting.py` — Class: `MemoSortingAttempt`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `proyecto_id` | `UUID` (FK → `proyectos.id`) | NO (indexed) | — | Parent project |
| 3 | `theoretical_code_id` | `UUID` (FK → `theoretical_codes.id`) | YES (indexed) | — | Theoretical code family used for sorting. NULL = exploratory |
| 4 | `groups_json` | `JSONB` | NO | `{}` | Groups formed: {group_label: [memo_id, ...]} |
| 5 | `homeless_json` | `JSONB` | NO | `[]` | UUIDs of orphan memos |
| 6 | `forced_json` | `JSONB` | NO | `[]` | UUIDs of forced memos |
| 7 | `thin_json` | `JSONB` | NO | `[]` | UUIDs of weak groups |
| 8 | `score` | `Float` | YES | — | Sorting quality score 0.0–1.0 |
| 9 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 10 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `proyecto_id` → `proyectos.id`
- `theoretical_code_id` → `theoretical_codes.id`

**Indexes**: `proyecto_id`, `theoretical_code_id`

---

### Table 46: `memo_sorting_groups` (Memo Sorting Group)

**File**: `backend/app/models/domain/sorting.py` — Class: `MemoSortingGroup`

Inherits: `Base`, `TimestampMixin`

| # | Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|---|
| 1 | `id` | `UUID` | NO (PK) | `uuid.uuid4` | Primary key |
| 2 | `attempt_id` | `UUID` (FK → `memo_sorting_attempts.id`) | NO (indexed) | — | Parent sorting attempt |
| 3 | `memos_json` | `JSONB` | NO | `[]` | UUIDs of memos in group (weak link, no FK) |
| 4 | `cross_family_affinity_json` | `JSONB` | YES | — | Cross-family affinity scores: {family_name: score, ...} |
| 5 | `creado_en` | `DateTime(timezone=True)` | NO | `func.now()` | (inherited) |
| 6 | `actualizado_en` | `DateTime(timezone=True)` | YES | `onupdate=func.now()` | (inherited) |

**Foreign Keys**:
- `attempt_id` → `memo_sorting_attempts.id`

**Indexes**: `attempt_id`

---

## Section 2: Entity-Relationship Map

### Core Domain Relationships

```
Usuario (usuarios)
  └── Proyecto (proyectos) ................................... Usuario.id ← Proyecto.creador_id [1:N]

Proyecto (proyectos)
  ├── Documento (documentos) ................................ Proyecto.id ← Documento.proyecto_id [1:N]
  ├── Categoria (categorias) ................................ Proyecto.id ← Categoria.proyecto_id [1:N]
  ├── Memo (memos) ......................................... Proyecto.id ← Memo.proyecto_id [1:N]
  ├── Concern (concerns) ................................... Proyecto.id ← Concern.project_id [1:N]
  ├── PopulationContext (population_contexts) ................ Proyecto.id ← PopulationContext.proyecto_id [1:N]
  ├── LienzoDelPlanDeAnalisis (lienzos) .................... Proyecto.id ← LienzoDelPlanDeAnalisis.proyecto_id [1:1, UNIQUE]
  ├── EcosystemLayout (ecosystem_layouts) ................... Proyecto.id ← EcosystemLayout.project_id [1:1, UNIQUE]
  ├── ProjectConfigHistory (project_config_history) .......... Proyecto.id ← ProjectConfigHistory.proyecto_id [1:N]
  ├── HitlDecision (hitl_decisions) ........................ Proyecto.id ← HitlDecision.project_id [1:N]
  ├── Fase (fases) ......................................... Proyecto.id ← Fase.proyecto_id [1:N]
  ├── Hypothe sis (hypotheses) .............................. Proyecto.id ← Hypothe sis.project_id [1:N]
  ├── GraphEntity (graph_entities) ......................... Proyecto.id ← GraphEntity.project_id [1:N]
  ├── DatabaseNode (database_nodes) ........................ Proyecto.id ← DatabaseNode.project_id [1:N]
  ├── DatabaseEdge (database_edges) ......................... Proyecto.id ← DatabaseEdge.project_id [1:N]
  ├── ParadigmState (paradigm_states) ...................... Proyecto.id ← ParadigmState.proyecto_id [1:N]
  ├── TheoreticalCode (theoretical_codes) ................... Proyecto.id ← TheoreticalCode.project_id [1:N] (nullable for built-ins)
  ├── ConceptualRelationship (conceptual_relationships) ..... Proyecto.id ← ConceptualRelationship.project_id [1:N]
  ├── ElaborationMemo (elaboration_memos) .................. Proyecto.id ← ElaborationMemo.project_id [1:N]
  ├── CategoryDefinitionVersion (category_definition_versions) Proyecto.id ← CategoryDefinitionVersion.project_id [1:N]
  ├── AgentOutput (agent_outputs) ......................... Proyecto.id ← AgentOutput.proyecto_id [1:N]
  ├── AgentLoopLog (agent_loop_logs) ....................... Proyecto.id ← AgentLoopLog.proyecto_id [1:N]
  ├── OutputModification (output_modifications) ............. Proyecto.id ← OutputModification.proyecto_id [1:N]
  ├── PipelineRun (pipeline_runs) ......................... Proyecto.id ← PipelineRun.project_id [1:N]
  ├── BatchExecution (batch_executions) ................... Proyecto.id ← BatchExecution.project_id [1:N]
  ├── ExtractedIncident (extracted_incidents) .............. Proyecto.id ← ExtractedIncident.proyecto_id [1:N]
  ├── IncidentComparison (incident_comparisons) ............ Proyecto.id ← IncidentComparison.proyecto_id [1:N]
  ├── IncidentGroup (incident_groups) ...................... Proyecto.id ← IncidentGroup.proyecto_id [1:N]
  ├── DocumentProcess (document_processes) ................. Proyecto.id ← DocumentProcess.proyecto_id [1:N]
  ├── MemoSortingAttempt (memo_sorting_attempts) ............ Proyecto.id ← MemoSortingAttempt.proyecto_id [1:N]
  └── MemoSortingGroup (memo_sorting_groups) .............. Proyecto.id ← (via attempt) ... [1:N indirect]
```

### Document Processing Chain

```
Documento (documentos)
  ├── Segmento (segmentos) .................................. Documento.id ← Segmento.documento_id [1:N]
  ├── DocumentProcess (document_processes) .................. Documento.id ← DocumentProcess.documento_id [1:N]
  │   └── DocumentProcess.previous_document_id → Documento.id [M:1] (self-referential on documentos)
  ├── DocCode (doc_codes) ................................. Documento.id ← DocCode.documento_id [1:N] (composite PK)
  ├── CodeDocumentSummary (code_document_summaries) ......... Documento.id ← CodeDocumentSummary.document_id [1:N] (composite PK)
  ├── ExtractedIncident (extracted_incidents) ............... Documento.id ← ExtractedIncident.documento_id [1:N]
  ├── PipelineTask (pipeline_tasks) ........................ Documento.id ← PipelineTask.document_id [1:N] (nullable)
  └── TaskStepCheckpoint (task_step_checkpoints) ........... Documento.id ← TaskStepCheckpoint.document_id [1:N] (nullable)
```

### Segment Chain

```
Segmento (segmentos)
  ├── CodigoSegmento (codigos_segmento) .................... Segmento.id ← CodigoSegmento.segmento_id [1:N] (composite PK)
  └── ExtractedIncident (extracted_incidents) ............... Segmento.id ← ExtractedIncident.segmento_id [1:N]
```

### Category / Code Chain

```
Categoria (categorias)
  ├── Categoria (self-referential hierarchy) ................ Categoria.id ← Categoria.parent_category_id [1:N] (tree)
  ├── Memo (memos) ........................................ Categoria.source_memo_id → Memo.id [M:1] (origin memo)
  ├── DocCode (doc_codes) ................................. Categoria.id ← DocCode.categoria_id [1:N] (composite PK)
  ├── CodigoSegmento (codigos_segmento) .................... Categoria.id ← CodigoSegmento.categoria_id [1:N] (composite PK)
  ├── CategoryDefinitionVersion (category_definition_versions) Categoria.id ← CategoryDefinitionVersion.category_id [1:N]
  ├── ParadigmState (paradigm_states) ...................... Categoria.id ← ParadigmState.code_id [1:N]
  ├── CodePrototype (code_prototypes) ...................... Categoria.id ← CodePrototype.code_id [1:1] (PK = FK)
  ├── CodeDocumentSummary (code_document_summaries) ......... Categoria.id ← CodeDocumentSummary.code_id [1:N] (composite PK)
  ├── CodeGlobalSummary (code_global_summaries) ............. Categoria.id ← CodeGlobalSummary.code_id [1:1] (PK = FK)
  ├── SaturationMetrics (saturation_metrics) ............... Categoria.id ← SaturationMetrics.code_id [1:1] (PK = FK)
  ├── Hypothe sis (hypotheses) .............................. Categoria.id ← Hypothe sis.code_id [1:N] (nullable)
  ├── DatabaseNode (database_nodes) ....................... Categoria.id ← DatabaseNode.category_id [1:N] (nullable)
  └── ElaborationMemo (elaboration_memos) ................. Categoria.id ← ElaborationMemo.category_id [1:N] (nullable)
```

### Incident Chain

```
ExtractedIncident (extracted_incidents)
  ├── IncidentComparison (incident_comparisons) via incident_a_id [1:N]
  ├── IncidentComparison (incident_comparisons) via incident_b_id [1:N]
  └── DocumentProcess (document_processes) ................ ExtractedIncident.patrón_documento_id → DocumentProcess.id [M:1]

IncidentGroup (incident_groups) .......................... (weak link via incident_ids_json → ExtractedIncident.id)
```

### Agent / AI Metadata Layer

```
AgentOutput (agent_outputs)
  ├── AgentLoopLog (agent_loop_logs) ....................... AgentOutput.loop_log_id → AgentLoopLog.id [M:1]
  ├── AgentOutput (self-referential) ....................... AgentOutput.parent_output_id → AgentOutput.id [M:1]
  └── OutputModification (output_modifications) ............ AgentOutput.id ← OutputModification.agent_output_id [1:N]

OutputModification (output_modifications)
  └── Usuario (usuarios) .................................. OutputModification.modified_by → Usuario.id [M:1]
```

### Theoretical Playground (Fase 6b)

```
TheoreticalCode (theoretical_codes)
  ├── Memo (memos) ........................................ TheoreticalCode.source_memo_id → Memo.id [M:1]
  ├── ConceptualRelationship (conceptual_relationships) ..... TheoreticalCode.id ← ConceptualRelationship.theoretical_code_id [1:N]
  └── MemoSortingAttempt (memo_sorting_attempts) ........... TheoreticalCode.id ← MemoSortingAttempt.theoretical_code_id [1:N] (nullable)

ConceptualRelationship (conceptual_relationships)
  └── ElaborationMemo (elaboration_memos) ................. ConceptualRelationship.id ← ElaborationMemo.relationship_id [1:N] (nullable)

MemoSortingAttempt (memo_sorting_attempts)
  └── MemoSortingGroup (memo_sorting_groups) ............... MemoSortingAttempt.id ← MemoSortingGroup.attempt_id [1:N]
```

### Canvas / Workflow

```
LienzoDelPlanDeAnalisis (lienzos)
  ├── NodoDeLienzo (nodos_lienzo) ......................... LienzoDelPlanDeAnalisis.id ← NodoDeLienzo.lienzo_id [1:N]
  └── BordeDeLienzo (bordes_lienzo) ........................ LienzoDelPlanDeAnalisis.id ← BordeDeLienzo.lienzo_id [1:N]

NodoDeLienzo (nodos_lienzo)
  ├── BordeDeLienzo via nodo_origen_id [1:N]
  ├── BordeDeLienzo via nodo_destino_id [1:N]
  └── Fase (fases) ........................................ NodoDeLienzo.id ← Fase.nodo_lienzo_id [1:N] (nullable)
```

### Pipeline / Execution Tracking

```
PipelineRun (pipeline_runs)
  └── PipelineTask (pipeline_tasks) ....................... PipelineRun.id ← PipelineTask.run_id [1:N]

PipelineTask (pipeline_tasks)
  └── TaskStepCheckpoint (task_step_checkpoints) ........... PipelineTask.id ← TaskStepCheckpoint.pipeline_task_id [1:N] (nullable)
```

### Database Model (A/B)

```
DatabaseNode (database_nodes)
  └── DatabaseEdge (database_edges) via source_node_id [1:N]
  └── DatabaseEdge (database_edges) via target_node_id [1:N]
```

### Graph Entities

```
GraphEntity (graph_entities)
  └── GraphRelation (graph_relations) via source_id [1:N] (composite PK)
  └── GraphRelation (graph_relations) via target_id [1:N] (composite PK)
```

### Memo Relationships

```
Memo (memos)
  ├── Usuario (usuarios) .................................. Memo.autor_id → Usuario.id [M:1]
  ├── Memo (self-referential) ............................. Memo.parent_memo_id → Memo.id [M:1]
  ├── Categoria (categorias) .............................. Memo.id → Categoria.source_memo_id [1:N]
  ├── TheoreticalCode (theoretical_codes) ................. Memo.id → TheoreticalCode.source_memo_id [1:N]
  └── ElaborationMemo (elaboration_memos) ................. Memo.id ← ElaborationMemo.memo_id [1:N] (nullable)
```

### Hypothe sis Self-Reference

```
Hypothe sis (hypotheses)
  └── Hypothe sis (self-referential) ....................... Hypothe sis.parent_hypothesis_id → Hypothe sis.id [M:1]
```

### Weak / JSONB-based References (no FK constraint)

- `IncidentGroup.incident_ids_json` → `ExtractedIncident.id` (list of UUIDs in JSONB)
- `MemoSortingGroup.memos_json` → `Memo.id` (list of UUIDs in JSONB)
- `MemoSortingAttempt.groups_json` → `Memo.id` (dict of group_label → [memo_id, ...] in JSONB)
- `MemoSortingAttempt.homeless_json` → `Memo.id` (list of UUIDs in JSONB)
- `MemoSortingAttempt.forced_json` → `Memo.id` (list of UUIDs in JSONB)
- `MemoSortingAttempt.thin_json` → `MemoSortingGroup.id` (list of UUIDs in JSONB)
- `ConceptualRelationship.category_ids` → `Categoria.id` (list of UUIDs in JSONB)
- `ConceptualRelationship.origin_memo_ids` → `Memo.id` (list of UUIDs in JSONB)
- `ConceptualRelationship.origin_hypothesis_ids` → `Hypothe sis.id` (list of UUIDs in JSONB)
- `PopulationContext.source_document_ids` → `Documento.id` (list of UUIDs in JSONB)
- `Categoria.saturation_docs` → `Documento.id` (list of UUIDs in JSONB)
- `Hypothe sis.concern_labels` → `Concern.label` (list of strings in JSONB)

---

## Section 3: Enumeration of All Enum Types

### 3.1 `RolDeUsuario` (User Role)

**File**: `backend/app/models/domain/enums.py`  
**Python type**: `str, enum.Enum`  
**SQL type**: `Enum(RolDeUsuario, name="rol_usuario_enum")`  
**Used in**: `Usuario.rol`

| Value | Constant |
|---|---|
| `"INVESTIGADOR_PRINCIPAL"` | `RolDeUsuario.INVESTIGADOR_PRINCIPAL` |
| `"COLABORADOR"` | `RolDeUsuario.COLABORADOR` |
| `"ESTUDIANTE"` | `RolDeUsuario.ESTUDIANTE` |
| `"AUDITOR"` | `RolDeUsuario.AUDITOR` |
| `"VISUALIZADOR"` | `RolDeUsuario.VISUALIZADOR` |

---

### 3.2 `TipoPlanSuscripcion` (Subscription Plan Type)

**File**: `backend/app/models/domain/enums.py`  
**Python type**: `str, enum.Enum`  
**SQL type**: `Enum(TipoPlanSuscripcion, name="plan_suscripcion_enum")`  
**Used in**: `Usuario.plan`

| Value | Constant |
|---|---|
| `"BASICO"` | `TipoPlanSuscripcion.BASICO` |
| `"PROFESIONAL"` | `TipoPlanSuscripcion.PROFESIONAL` |

---

### 3.3 `EstadoDeSaturacion` (Saturation State)

**File**: `backend/app/models/domain/enums.py`  
**Python type**: `str, enum.Enum`  
**Used as**: String values (referenced in `Categoria.estado_saturacion` as `String(50)` with default `"ABIERTO"`)

| Value | Constant |
|---|---|
| `"ABIERTO"` | `EstadoDeSaturacion.ABIERTO` |
| `"ESTABLE"` | `EstadoDeSaturacion.ESTABLE` |
| `"SATURADO"` | `EstadoDeSaturacion.SATURADO` |
| `"REVISION_FORZADA"` | `EstadoDeSaturacion.REVISION_FORZADA` |

---

### 3.4 `RecategorizationAction` (Recategorization Decision Triad)

**File**: `backend/app/models/domain/enums.py`  
**Python type**: `str, enum.Enum`  
**Used in**: A5 recategorization agent logic (not a DB column enum, used in application code)

| Value | Constant |
|---|---|
| `"ENRICH"` | `RecategorizationAction.ENRICH` |
| `"SUBDIVIDE"` | `RecategorizationAction.SUBDIVIDE` |
| `"DIVIDE"` | `RecategorizationAction.DIVIDE` |

---

### 3.5 `AgentFamily` (Agent Prompt Family)

**File**: `backend/app/models/domain/enums.py`  
**Python type**: `str, enum.Enum`  
**Used in**: `AgentOutput.agent_family` (String(50)), `AgentFamilyReference.family` (String(50) PK)

| Value | Constant |
|---|---|
| `"inductive_data"` | `AgentFamily.INDUCTIVE_DATA` |
| `"inductive_concepts"` | `AgentFamily.INDUCTIVE_CONCEPTS` |
| `"descriptive_data"` | `AgentFamily.DESCRIPTIVE_DATA` |
| `"evaluative"` | `AgentFamily.EVALUATIVE` |
| `"structural"` | `AgentFamily.STRUCTURAL` |
| `"elaborative"` | `AgentFamily.ELABORATIVE` |

---

### 3.6 `AgentPattern` (Agentic Pattern)

**File**: `backend/app/models/domain/enums.py`  
**Python type**: `str, enum.Enum`  
**Used in**: `AgentLoopLog.pattern` (String(50))

| Value | Constant |
|---|---|
| `"self_refinement"` | `AgentPattern.SELF_REFINEMENT` |
| `"react"` | `AgentPattern.REACT` |
| `"plan_execute"` | `AgentPattern.PLAN_EXECUTE` |
| `"debate"` | `AgentPattern.DEBATE` |
| `"hitl_modification"` | `AgentPattern.HITL_MODIFICATION` |

---

### 3.7 Implicit String Enumerations (NOT formal Python Enums)

These are string fields with documented sets of valid values but defined inline as `String(N)` columns rather than formal `Enum` types:

| Column | Table | Valid Values |
|---|---|---|
| `Proyecto.estado` | `proyectos` | `collecting`, `coding`, `finding_cc`, `reducing`, `saturating`, `building_db`, `playground_ready`, `completed` |
| `Proyecto.pause_mode` | `proyectos` | `auto`, `manual` |
| `Proyecto.object_of_study` | `proyectos` | `concern`, `emotion`, `behavior`, `discourse`, `identity`, `custom`, `meaning` |
| `Proyecto.language` | `proyectos` | `es`, `en`, `de`, `pt` |
| `Documento.estado` | `documentos` | `crudo`, `preprocesando`, `preprocesado`, `segmentando`, `segmentado`, `procesando`, `listo`, `resumiendo`, `resumido`, `sintetizado` |
| `Categoria.estado_saturacion` | `categorias` | `ABIERTO`, `ESTABLE`, `SATURADO`, `REVISION_FORZADA` |
| `DocCode.estado` | `doc_codes` | `presente`, `ausente`, `no_evaluado` |
| `CodigoSegmento.estado` | `codigos_segmento` | `asignado`, `confirmado`, `descartado` |
| `CodigoSegmento.origen` | `codigos_segmento` | `manual`, `ia`, `recomendacion` |
| `Segmento.tipo_dato_glaser` | `segmentos` | `baseline_data`, `properline_data`, `interpreted_data`, `vague_data`, `interviewer_context` |
| `Memo.estado` | `memos` | `ABIERTO` (default) |
| `Memo.tipo` | `memos` | `HIPOTESIS`, `METODOLOGICO`, `MUESTREO`, etc. |
| `Concern.status` | `concerns` | `candidate`, `confirmed`, `rejected` |
| `ExtractedIncident.tipo_dato_glaser` | `extracted_incidents` | `baseline`, `properline`, `interpreted`, `vague` |
| `IncidentGroup.status` | `incident_groups` | `open`, `labeled`, `approved`, `rejected` |
| `SaturationMetrics.saturation_status` | `saturation_metrics` | `unsaturated` (default) |
| `Hypothe sis.level` | `hypotheses` | `general`, `specific`, `emergent` |
| `Hypothe sis.status` | `hypotheses` | `candidate` (default) |
| `ProcessingState.entity_type` | `processing_states` | `document`, `segment`, `code` |
| `ProcessingState.step` | `processing_states` | `segmented`, `coded`, `synthesized` |
| `GraphEntity.type` | `graph_entities` | `person`, `concept`, `event` |
| `ParadigmState.expansion_type` | `paradigm_states` | `NEW_DIMENSION`, `NEW_CONDITION`, `NEW_CONSEQUENCE`, `NEW_STRATEGY`, `NONE` |
| `AgentOutput.output_table` | `agent_outputs` | `categorias`, `hypotheses`, `population_contexts`, `document_processes`, `conceptual_relationships` |
| `AgentOutput.agent_tier` | `agent_outputs` | `PRO`, `FLASH` |
| `AgentLoopLog.pattern` | `agent_loop_logs` | `self_refinement`, `react`, `plan_execute`, `debate`, `hitl_modification` |
| `CategoryDefinitionVersion.trigger` | `category_definition_versions` | `manual_edit`, `ghost_absorbed`, `relationship_elaborated`, `rename_applied`, `incident_converged`, `incident_diverged_property`, `incident_diverged_dimension` |
| `ElaborationMemo.elaboration_type` | `elaboration_memos` | `relationship_proposed`, `divergence_expanded`, `ghost_absorbed`, `rename_applied`, `definition_expanded`, `sampling_recommended` |
| `NodoDeLienzo.tipo` | `nodos_lienzo` | `FUENTE_DE_DATOS`, `FASE`, `PUERTA_DE_DECISION` |
| `NodoDeLienzo.estado` | `nodos_lienzo` | `NO_INICIADO` (default) |
| `HitlDecision.gate_name` | `hitl_decisions` | `pattern_of_interest`, `core_category`, `selective_reduction`, `core_saturation`, `database_a`, `database_b`, `global_saturation` |
| `HitlDecision.status` | `hitl_decisions` | `pending`, `accepted`, `modified`, `rejected` |
| `HitlDecision.researcher_decision` | `hitl_decisions` | `accept`, `modify`, `reject` |
| `PipelineRun.status` | `pipeline_runs` | `running`, `completed`, `cancelled`, `failed` |
| `PipelineRun.triggered_by` | `pipeline_runs` | `user`, `auto` |
| `PipelineTask.status` | `pipeline_tasks` | `queued`, `running`, `completed`, `cancelled`, `failed` |
| `PipelineTask.queue` | `pipeline_tasks` | `nlp`, `fast`, `heavy` |
| `TaskStepCheckpoint.status` | `task_step_checkpoints` | `in_progress`, `completed`, `failed` |
| `BatchExecution.status` | `batch_executions` | `running`, `completed`, `failed` |
| `BatchExecution.map_strategy` | `batch_executions` | `ai_only`, `map_reduce`, `hybrid_react` |
| `DocumentProcess.prime_mover_confidence` | `document_processes` | `HIGH`, `MEDIUM`, `LOW` |
| `DatabaseNode.entity_type` | `database_nodes` | `PROCESS`, `ACTOR`, `CONDITION`, `CONSEQUENCE`, `CONTEXT`, `STRATEGY` |
| `DatabaseEdge.direction` | `database_edges` | `unidirectional` (default) |
| `DatabaseEdge.strength` | `database_edges` | `weak`, `moderate`, `strong` |
| `ProjectConfigHistory.triggered_by` | `project_config_history` | `user`, agent name, `system` |
| `ProjectConfigHistory.mutation_level` | `project_config_history` | `auto`, `suggest`, `require_approval`, `locked` |
| `Fase.estado` | `fases` | `PENDIENTE` (default) |
| `EcosystemLayout` fields | `ecosystem_layouts` | (JSONB dicts for blob_positions, ghost_positions, fog_zones, physics_params) |

---

## Section 4: Pydantic Schema Catalog

### 4.1 Factory-Generated Schemas

**File**: `backend/app/schemas/factory.py`

The factory dynamically generates Pydantic models from SQLAlchemy models. Key configuration:

| Constant | Value | Purpose |
|---|---|---|
| `AUTO_FIELDS` | `{"id", "creado_en", "actualizado_en"}` | Auto-excluded from input schemas |
| `SENSITIVE_FIELDS` | `{"hashed_password"}` | Auto-excluded from response schemas |
| `VECTOR_FIELDS` | `{"embedding", "embedding_centroide", "centroid"}` | Vector fields (identified but not automatically excluded) |
| `_CUSTOM_TYPE_MAP` | `VECTOR→list[float]`, `JSONB→dict\|list`, `JSON→dict\|list` | Type mapping for non-standard SQLAlchemy types |

**Functions**:

| Function | Purpose | Auto-Excludes |
|---|---|---|
| `response_schema(model, exclude)` | GET response schemas | `SENSITIVE_FIELDS` |
| `create_input_schema(model, exclude)` | POST/PUT input schemas | `AUTO_FIELDS` + `SENSITIVE_FIELDS` |

All generated schemas use `ConfigDict(from_attributes=True)` for ORM compatibility. Nullable columns and columns with defaults become `Optional` fields. Non-nullable columns without defaults become required (`...`).

---

### 4.2 Defined Schemas

**File**: `backend/app/schemas/models.py`

#### `CategoryResponse` (Response)
Generated from `Categoria`. `exclude={"embedding_centroide"}` (plus `SENSITIVE_FIELDS` auto).

| Field | Type | Source |
|---|---|---|
| `id` | `UUID` | `Categoria.id` |
| `proyecto_id` | `UUID` | `Categoria.proyecto_id` |
| `nombre` | `str` | `Categoria.nombre` |
| `definicion` | `str` | `Categoria.definicion` |
| `limites` | `str \| None` | `Categoria.limites` |
| `estado_saturacion` | `str` | `Categoria.estado_saturacion` |
| `puntaje_relevancia` | `int` | `Categoria.puntaje_relevancia` |
| `version` | `int` | `Categoria.version` |
| `es_central` | `bool` | `Categoria.es_central` |
| `saturation_docs` | `dict \| list` | `Categoria.saturation_docs` |
| `parent_category_id` | `UUID \| None` | `Categoria.parent_category_id` |
| `source_memo_id` | `UUID \| None` | `Categoria.source_memo_id` |
| `saturation_panel_json` | `dict \| list \| None` | `Categoria.saturation_panel_json` |
| `gerundio_label` | `str \| None` | `Categoria.gerundio_label` |
| `concern_label` | `str \| None` | `Categoria.concern_label` |
| `population_label` | `str \| None` | `Categoria.population_label` |
| `creado_en` | `datetime` | (inherited) |
| `actualizado_en` | `datetime \| None` | (inherited) |

**Excluded**: `embedding_centroide`

---

#### `CategoryCreate` (Input)
Generated from `Categoria`. Auto-excludes `{id, creado_en, actualizado_en, hashed_password}` plus explicit `exclude={"embedding_centroide", "estado_saturacion", "puntaje_relevancia", "version"}`.

| Field | Type | Required | Default |
|---|---|---|---|
| `proyecto_id` | `UUID` | YES | — |
| `nombre` | `str` | YES | — |
| `definicion` | `str` | YES | — |
| `limites` | `str \| None` | — | `None` |
| `es_central` | `bool` | — | `False` |
| `saturation_docs` | `dict \| list` | — | `[]` |
| `parent_category_id` | `UUID \| None` | — | `None` |
| `source_memo_id` | `UUID \| None` | — | `None` |
| `saturation_panel_json` | `dict \| list \| None` | — | `None` |
| `gerundio_label` | `str \| None` | — | `None` |
| `concern_label` | `str \| None` | — | `None` |
| `population_label` | `str \| None` | — | `None` |

---

#### `SegmentResponse` (Response)
Generated from `Segmento`. `exclude={"embedding"}` (plus `SENSITIVE_FIELDS` auto).

| Field | Type | Source |
|---|---|---|
| `id` | `UUID` | `Segmento.id` |
| `documento_id` | `UUID` | `Segmento.documento_id` |
| `texto` | `str` | `Segmento.texto` |
| `parafrasis` | `str \| None` | `Segmento.parafrasis` |
| `posicion` | `int` | `Segmento.posicion` |
| `conteo_tokens` | `int` | `Segmento.conteo_tokens` |
| `es_anomalia` | `bool` | `Segmento.es_anomalia` |
| `tipo_dato_glaser` | `str \| None` | `Segmento.tipo_dato_glaser` |
| `first_10` | `str \| None` | `Segmento.first_10` |
| `start_char` | `int \| None` | `Segmento.start_char` |
| `end_char` | `int \| None` | `Segmento.end_char` |
| `is_exact_match` | `bool` | `Segmento.is_exact_match` |

**Excluded**: `embedding`

**Note**: `Segmento` does not inherit `TimestampMixin`, so no `creado_en`/`actualizado_en` fields.

---

#### `CodeAssignRequest` (Input)
Generated from `CodigoSegmento`. Auto-excludes `{id, creado_en, actualizado_en, hashed_password}` plus explicit `exclude={"estado", "confianza", "creado_en", "actualizado_en"}`.

| Field | Type | Required | Default |
|---|---|---|---|
| `segmento_id` | `UUID` | YES | — |
| `categoria_id` | `UUID` | YES | — |
| `origen` | `str` | — | `"manual"` |

---

#### `CodeAssignResponse` (Response)
Generated from `CodigoSegmento` (no explicit excludes beyond `SENSITIVE_FIELDS`).

| Field | Type | Source |
|---|---|---|
| `segmento_id` | `UUID` | `CodigoSegmento.segmento_id` |
| `categoria_id` | `UUID` | `CodigoSegmento.categoria_id` |
| `estado` | `str` | `CodigoSegmento.estado` |
| `confianza` | `float` | `CodigoSegmento.confianza` |
| `origen` | `str` | `CodigoSegmento.origen` |
| `creado_en` | `datetime` | (inherited) |
| `actualizado_en` | `datetime \| None` | (inherited) |

---

#### `RecommendationItem` (Response — manually defined)

| Field | Type | Required | Default |
|---|---|---|---|
| `categoria` | `CategoryResponse` | YES | — |
| `score` | `float` | YES | — |
| `definicion` | `str` | — | `""` |

Uses `ConfigDict(from_attributes=True)`.

---

#### `ProjectResponse` (Response)
Generated from `Proyecto` (no explicit excludes beyond `SENSITIVE_FIELDS`).

All 17 columns of `Proyecto` (including `creado_en`, `actualizado_en`) except `hashed_password` (not applicable to Proyecto anyway).

---

#### `ProjectCreate` (Input)
Extends auto-generated `_BaseProjectCreate` from `Proyecto`, which excludes `{id, creado_en, actualizado_en, hashed_password, estado, creador_id}`.

**Additional field**:

| Field | Type | Required | Default |
|---|---|---|---|
| `custom_label` | `str \| None` | — | `None` |

Plus all remaining Proyecto columns:
- `nombre` (str, required)
- `ruta_de_codificacion` (str, default `"ABDUCTIVA_CGT"`)
- `supuesto_poblacional` (str | None)
- `config_segmentacion` (dict | list | None)
- `population_assumption` (dict | list | None)
- `coding_style_instruction` (str | None)
- `object_of_study` (str, default `"concern"`)
- `language` (str, default `"es"`)
- `config_mutation_policy` (dict | list | None)
- `context_window_real` (int, default `150000`)
- `batch_number` (int, default `0`)
- `chosen_concern` (str | None)
- `chosen_population` (str | None)
- `pause_mode` (str, default `"manual"`)

Uses `ConfigDict(from_attributes=True, extra="allow")`.

---

#### `DocumentResponse` (Response)
Generated from `Documento`. `exclude={"metadatos"}` (plus `SENSITIVE_FIELDS` auto).

| Field | Type | Source |
|---|---|---|
| `id` | `UUID` | `Documento.id` |
| `proyecto_id` | `UUID` | `Documento.proyecto_id` |
| `original_filename` | `str` | `Documento.original_filename` |
| `tipo_de_fuente` | `str` | `Documento.tipo_de_fuente` |
| `ruta_s3` | `str \| None` | `Documento.ruta_s3` |
| `storage_key` | `str` | `Documento.storage_key` |
| `mime_type` | `str` | `Documento.mime_type` |
| `size_bytes` | `int` | `Documento.size_bytes` |
| `sort_order` | `float \| None` | `Documento.sort_order` |
| `estado` | `str` | `Documento.estado` |
| `creado_en` | `datetime` | (inherited) |
| `actualizado_en` | `datetime \| None` | (inherited) |

**Excluded**: `metadatos`

---

### 4.3 HITL Schemas

**File**: `backend/app/schemas/hitl.py`

#### `HitlDecisionRequest` (Input — POST /hitl/{gate}/decide)

| Field | Type | Required | Constraints |
|---|---|---|---|
| `decision` | `str` | YES | `pattern="^(accept\|modify\|reject)$"` |
| `note` | `str` | — (default `""`) | `max_length=2000` |
| `feedback` | `str \| None` | — | `max_length=2000` (only used if decision == "modify") |

---

#### `HitlDecisionResponse` (Response)

| Field | Type |
|---|---|
| `id` | `UUID` |
| `project_id` | `UUID` |
| `gate_name` | `str` |
| `status` | `str` |
| `researcher_decision` | `str \| None` |
| `researcher_note` | `str \| None` |
| `decided_at` | `datetime \| None` |

Uses `model_config = {"from_attributes": True}`.

---

#### `HitlPendingItem` (Response — list of pending decisions)

| Field | Type |
|---|---|
| `id` | `UUID` |
| `gate_name` | `str` |
| `proposal_summary` | `str` |
| `critic_verdict` | `str` |
| `created_at` | `datetime` |

Uses `model_config = {"from_attributes": True}`.

---

#### `ConcernCandidate` (Response — nested in OpenCodingHITLStatusResponse)

| Field | Type | Required | Default |
|---|---|---|---|
| `label` | `str` | YES | — |
| `supporting_codes` | `list[str]` | — | `[]` |
| `rationale` | `str` | — | `""` |

---

#### `PopulationProposal` (Response — nested in OpenCodingHITLStatusResponse)

| Field | Type | Required |
|---|---|---|
| `description` | `str` | YES |
| `source_batch` | `int` | YES |

---

#### `UnifiedCategory` (Response — nested in OpenCodingHITLStatusResponse)

| Field | Type | Required |
|---|---|---|
| `id` | `UUID` | YES |
| `label` | `str` | YES |
| `definition` | `str` | YES |
| `is_core_candidate` | `bool` | YES |

---

#### `UnifiedHypothe sis` (Response — nested in OpenCodingHITLStatusResponse)

| Field | Type | Required | Default |
|---|---|---|---|
| `id` | `UUID` | YES | — |
| `text` | `str` | YES | — |
| `concern_relevance` | `str` | — | `"INDIRECT"` (values: `"DIRECT"`, `"INDIRECT"`) |
| `is_core_candidate` | `bool` | — | `False` |

---

#### `OpenCodingHITLStatusResponse` (Response)

| Field | Type |
|---|---|
| `docs_processed` | `int` |
| `total_docs` | `int` |
| `batch_number` | `int` |
| `concern_candidates` | `list[ConcernCandidate]` |
| `population_proposals` | `list[PopulationProposal]` |
| `unified_categories` | `list[UnifiedCategory]` |
| `unified_hypotheses` | `list[UnifiedHypothe sis]` |
| `chosen_concern` | `str \| None` |
| `chosen_population` | `str \| None` |
| `can_proceed` | `bool` |

---

#### `OpenCodingHITLDecision` (Input — POST /hitl/open-coding/decide)

| Field | Type | Required | Constraints / Default |
|---|---|---|---|
| `chosen_concern` | `str` | YES | `min_length=1`, `max_length=255` |
| `chosen_population` | `str` | YES | `min_length=1`, `max_length=2000` |
| `core_category_ids` | `list[UUID]` | — | `default_factory=list` |
| `confirmed` | `bool` | — | `False` |
| `researcher_note` | `str` | — | `default=""`, `max_length=2000` |

---

#### `OpenCodingHITLDecisionResponse` (Response)

| Field | Type |
|---|---|
| `status` | `str` |
| `chosen_concern` | `str` |
| `chosen_population` | `str` |
| `core_categories_set` | `int` |
| `confirmed` | `bool` |

---

#### `PauseConfigRequest` (Input — PATCH /pipeline/pause-config)

| Field | Type | Required | Constraints |
|---|---|---|---|
| `mode` | `str` | YES | `pattern="^(auto\|manual)$"` |

---

## Summary Statistics

| Metric | Count |
|---|---|
| **Total DB Tables** | 46 |
| **Total SQLAlchemy Models** | 46 |
| **Formal Python Enum Types** | 6 |
| **Implicit String Enumerations** | ~38 documented valid-value sets |
| **Pydantic Schema Classes (factory-generated)** | 8 |
| **Pydantic Schema Classes (manually defined)** | 12 |
| **Total Relationships (ORM)** | ~98 |
| **Weak/JSONB References (no FK)** | 11 identified |
| **Composite Primary Keys** | 7 tables (`doc_codes`, `codigos_segmento`, `code_document_summaries`, `processing_states`, `graph_relations`, `code_prototypes`, `code_global_summaries`) |
| **Self-Referential FKs** | 5 (`categorias.parent_category_id`, `memos.parent_memo_id`, `hypotheses.parent_hypothesis_id`, `agent_outputs.parent_output_id`, `document_processes.previous_document_id`) |
| **Unique Constraints (non-PK)** | 4 (`usuarios.correo`, `documentos.storage_key`, `pipeline_tasks.celery_task_id`, `ecosystem_layouts.project_id`, `lienzos.proyecto_id`) |
| **CASCADE delete-orphan** | ~20 relationships |
| **pgvector columns** | 3 (`segmentos.embedding`, `categorias.embedding_centroide`, `saturation_metrics.centroid`) |
