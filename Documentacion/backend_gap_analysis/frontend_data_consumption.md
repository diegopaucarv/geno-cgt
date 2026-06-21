# Frontend Data Consumption Analysis

> Generated: 2026-06-21  
> Scope: Complete audit of TS interfaces, displayed vs received data, API function usage, and Playground data flow

---

## Section 1: TypeScript Interface vs Backend Model Audit

### 1.1 `Project` interface (client.ts:89-105)

```typescript
export interface Project {
  id: string;
  nombre: string;
  ruta_de_codificacion: string;
  estado: string;
  creador_id: string;
  creado_en: string;
  num_documentos?: number;
  num_categorias?: number;
  // ── Config fields (from GET /projects/{id}/config) ──
  supuesto_poblacional?: string | null;
  object_of_study?: string;
  population_assumption?: Record<string, any> | null;
  config_segmentacion?: Record<string, any> | null;
  coding_style_instruction?: string | null;
  config_mutation_policy?: Record<string, string> | null;
}
```

| Status | Field | Notes |
|--------|-------|-------|
| ✅ Used | `id` | Displayed in URL routing; key identifier |
| ✅ Used | `nombre` | Project title in navbar (L1467-1468) |
| ✅ Used | `ruta_de_codificacion` | Displayed in header (L1641) + passed to MemoHistory (L3146) |
| ✅ Used | `estado` | Displayed in header (L1641); used for stale entity check (L254) |
| ⚠️ Ignored | `creador_id` | Fetched but never rendered |
| ⚠️ Ignored | `creado_en` | Fetched but never rendered |
| ⚠️ Unused | `num_documentos` | Optional field; never rendered (docs.length used instead) |
| ⚠️ Unused | `num_categorias` | Optional field; never rendered (cats.length used instead) |
| ✅ Used | `supuesto_poblacional` | Population section (L1809-1834); triggers generate button (L1974) |
| ✅ Used | `object_of_study` | Experimental mode (L283); pattern switching |
| ✅ Used | `population_assumption` | Full object used (L1839-1852); `generalized_population`, `population_description`, `custom_label`, `generalizer_confidence` accessed via `any` casts |
| ❌ Mystery | `config_segmentacion` | Declared in interface; never read/written in any frontend page |
| ❌ Mystery | `coding_style_instruction` | Declared in interface; never read/written in any frontend page |
| ❌ Mystery | `config_mutation_policy` | Declared in interface; never read/written in any frontend page |

**Key Gap**: The `Project` interface mixes core project fields with config fields that are actually fetched from a *separate* endpoint (`getProjectConfig`). Three fields (`config_segmentacion`, `coding_style_instruction`, `config_mutation_policy`) are typed in the interface but have ZERO consumers anywhere in the frontend.

---

### 1.2 `ProjectConfig` interface (client.ts:107-119)

```typescript
export interface ProjectConfig {
  project_id: string;
  nombre: string;
  estado: string;
  ruta_de_codificacion: string;
  supuesto_poblacional: string | null;
  object_of_study: string;
  population_assumption: Record<string, any>;
  coding_style_instruction: string | null;
  config_segmentacion: Record<string, any>;
  mutation_policy: Record<string, string>;
  pending_suggestions: ConfigSuggestion[];
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `project_id` | ProjectConfigPanel (implicit via prop) |
| ✅ Used | `nombre` | Config panel display |
| ✅ Used | `estado` | Config panel display |
| ✅ Used | `ruta_de_codificacion` | Config panel display |
| ✅ Used | `supuesto_poblacional` | Config panel display |
| ✅ Used | `object_of_study` | Config panel display |
| ✅ Used | `population_assumption` | Config panel (edit + display) |
| ⚠️ Ignored | `coding_style_instruction` | Fetched by config panel but NOT displayed in any tab |
| ⚠️ Ignored | `config_segmentacion` | Fetched by config panel but NOT displayed in any tab |
| ✅ Used | `mutation_policy` | Config panel "policy" tab |
| ✅ Used | `pending_suggestions` | Config panel "suggestions" tab |

**Gap**: `coding_style_instruction` and `config_segmentacion` are fetched from `GET /projects/:id/config` but have no UI rendering anywhere.

---

### 1.3 `Document` interface (client.ts:153-168)

```typescript
export interface Document {
  id: string;
  proyecto_id: string;
  original_filename: string;
  tipo_de_fuente: string;
  storage_key: string;
  mime_type: string;
  size_bytes: number;
  creado_en: string;
  estado: string;
  texto_extraido?: string;
  texto_preprocesado?: string;
  texto_original?: string;
  preprocess_warning?: string;
  sort_order?: number;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | URL routing, drag-drop, segment fetching, deletion |
| ⚠️ Ignored | `proyecto_id` | Fetched but never rendered |
| ✅ Used | `original_filename` | Document card title (L2559) |
| ❌ Unused | `tipo_de_fuente` | Fetched but never rendered anywhere |
| ⚠️ Ignored | `storage_key` | Internal field, never rendered (correctly) |
| ✅ Used | `mime_type` | Displayed as badge via `mimeLabel()` (L2563) |
| ❌ Unused | `size_bytes` | Fetched but never rendered anywhere |
| ⚠️ Ignored | `creado_en` | Fetched but never rendered |
| ✅ Used | `estado` | Determines status badge (crudo/preprocesado/segmentado/listo/etc.) (L1347-1426) |
| ✅ Used | `texto_extraido` | Textarea when viewing "Original" text; also saved as backup before punctuation (L463-464, L2928) |
| ✅ Used | `texto_preprocesado` | Textarea when toggled to "Preprocessed" view (L2925-2927) |
| ✅ Used | `texto_original` | Textarea when showing edited original (L2928-2930) |
| ✅ Used | `preprocess_warning` | Warning badge next to document state (L2568-2604) |
| ⚠️ Ignored | `sort_order` | Not directly rendered; used implicitly via reorder API (POST `/documents/project/:id/reorder`) |

**Key Gap**: `tipo_de_fuente` and `size_bytes` are completely unused in the UI. `creado_en` and `proyecto_id` could be useful for sorting/filtering but aren't used.

---

### 1.4 `PipelineLog` interface (client.ts:208-225)

```typescript
export interface PipelineLog {
  project_id: string;
  documents: DocPipelineLog[];
  summary: {
    total: number;
    need_segment: number;
    need_agents: number;
    need_synthesis: number;
    sintetizados: number;
    done: number;
    failed: number;
    failed_tasks: number;
    errors: PipelineLogError[];
    categories: number;
    project_state: string;
    playground_ready: boolean;
  };
}
```

**`PipelineLog` top-level fields:**

| Status | Field | Where Used |
|--------|-------|------------|
| ⚠️ Ignored | `project_id` | Fetched but never read directly |
| ✅ Used | `documents[]` | `getDocLog()` helper (L1274-1276); doc count (L3100) |

**`PipelineLog.summary` fields:**

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `total` | Stage derivation (L296, L316-346); completion check (L340, L1081) |
| ✅ Used | `need_segment` | `docsNeedSegment` (L1259); pills (L1645); stage derivation (L317) |
| ✅ Used | `need_agents` | `docsNeedAgents` (L1260); pills (L1663); stage derivation (L322) |
| ✅ Used | `need_synthesis` | Pipeline continuation check (L902); Playground.tsx newDocs banner (L50) |
| ❌ Unused | `sintetizados` | Field exists in TS interface but NEVER read by any frontend code |
| ✅ Used | `done` | `docsDone` (L1261); completion check (L340, L1081) |
| ✅ Used | `failed` | Failure detection during pipeline polling (L1047) |
| ✅ Used | `failed_tasks` | Failure detection (L1047) |
| ✅ Used | `errors[]` | Error filename extraction (L1048-1050) |
| ✅ Used | `categories` | Not directly used in Project.tsx but contributes to playground_ready |
| ✅ Used | `project_state` | Stage derivation (L329-337); Playground ready banner (L1574) |
| ✅ Used | `playground_ready` | Stage derivation (L332); playground link enable/disable (L1263, L1722-1746) |

**Key Gap**: `sintetizados` is declared in the TS interface but has ZERO consumers anywhere in the frontend. This is wasted data transfer.

---

### 1.5 `DocPipelineLog` interface (client.ts:179-200)

```typescript
export interface DocPipelineLog {
  document_id: string;
  filename: string;
  estado: string;
  steps: {
    text_extracted: boolean;
    punctuation_fixed: boolean;
    segmented: boolean;
    coded: boolean;
    agents_done: boolean;
    synthesis_done: boolean;
  };
  segments_count: number;
  codes_count: number;
  next_action: "extract_text" | "segment" | "run_agents" | "run_synthesis" | "done" | "error";
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `document_id` | `getDocLog()` lookup (L1274-1276) |
| ⚠️ Ignored | `filename` | Fetched but never directly read (doc.original_filename used instead) |
| ⚠️ Ignored | `estado` | Fetched but not directly read (doc.estado used instead) |
| ❌ Unused | `steps.*` | ALL six boolean fields (`text_extracted`, `punctuation_fixed`, `segmented`, `coded`, `agents_done`, `synthesis_done`) are NEVER read by ANY frontend code |
| ✅ Used | `segments_count` | `hasSegments()` helper (L420) |
| ❌ Unused | `codes_count` | NEVER read by ANY frontend code |
| ✅ Used | `next_action` | Pipeline continuation logic (L914) |

**Key Gap**: The entire `steps` sub-object (6 booleans) and `codes_count` are completely ignored by the frontend despite being part of every `getPipelineLog` response for every document.

---

### 1.6 `PipelineLogError` interface (client.ts:202-206)

```typescript
export interface PipelineLogError {
  document_id: string;
  filename: string;
  estado: string;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ⚠️ Ignored | `document_id` | Fetched but only `filename` is used |
| ✅ Used | `filename` | Error message construction (L1049) |
| ⚠️ Ignored | `estado` | Fetched but never read |

---

### 1.7 `PipelineStatus` interface (client.ts:170-177)

```typescript
export interface PipelineStatus {
  project_id: string;
  documents: number;
  segments: number;
  categories: number;
  hypotheses: number;
  stages: Record<string, "done" | "in_progress" | "pending">;
}
```

| Status | Field | Notes |
|--------|-------|-------|
| ❌ Unused | ALL | `getPipelineStatus()` is **never called anywhere**. The frontend uses `getPipelineLog()` instead. |

---

### 1.8 `Category` interface (client.ts:227-234)

```typescript
export interface Category {
  id: string;
  proyecto_id: string;
  nombre: string;
  definicion: string;
  estado_saturacion: string;
  es_central: boolean;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | Key for list rendering (implicit) |
| ⚠️ Ignored | `proyecto_id` | Fetched but never rendered |
| ⚠️ Ignored | `nombre` | **cats.length** is displayed (L1481) but individual `nombre` is NOT rendered in Project.tsx. Shown in playground as `BlobData.name` via ecosystem API |
| ❌ Unused | `definicion` | Never rendered in Project.tsx (shown in playground as `BlobData.definition`) |
| ❌ Unused | `estado_saturacion` | Never rendered in Project.tsx (shown in playground as `BlobData.saturation`) |
| ❌ Unused | `es_central` | Never rendered in Project.tsx (shown in playground as `BlobData.is_core`) |

**Key Gap**: In Project.tsx, categories are fetched via `listCategories()` but ONLY `cats.length` is displayed. All individual category fields (`nombre`, `definicion`, `estado_saturacion`, `es_central`) are ignored. The playground displays equivalent data through the ecosystem API (`BlobData`).

---

### 1.9 `Segment` interface (client.ts:236-244)

```typescript
export interface Segment {
  id: string;
  documento_id: string;
  texto: string;
  parafrasis: string | null;
  posicion: number;
  conteo_tokens: number;
  es_anomalia: boolean;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | Key for list rendering (implicit) |
| ⚠️ Ignored | `documento_id` | Fetched but always queried per-document (redundant) |
| ✅ Used | `texto` | Displayed in segment view (through segments array rendering) |
| ❌ Unused | `parafrasis` | NEVER rendered in Project.tsx |
| ❌ Unused | `posicion` | NEVER rendered in Project.tsx |
| ❌ Unused | `conteo_tokens` | NEVER rendered in Project.tsx |
| ❌ Unused | `es_anomalia` | NEVER rendered in Project.tsx |

**Key Gap**: Four of seven Segment fields are fetched but completely ignored in the UI. `parafrasis` (paraphrase) is particularly notable — it's an AI-generated field that could add value but has no UI.

---

### 1.10 `HitlPendingItem` interface (client.ts:953-959)

```typescript
export interface HitlPendingItem {
  id: string;
  gate_name: string;
  proposal_summary: string;
  critic_verdict: string;
  created_at: string;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ⚠️ Ignored | `id` | Never rendered directly |
| ✅ Used | `gate_name` | HITL banner (L1511-1524); gate mapping for stage status (L358-368) |
| ❌ Unused | `proposal_summary` | NEVER rendered — `getHitlDetail()` fetches the full proposal instead (HITLModal) |
| ❌ Unused | `critic_verdict` | NEVER rendered — `getHitlDetail()` fetches the full verdict instead |
| ❌ Unused | `created_at` | NEVER rendered |

**Key Gap**: `proposal_summary` and `critic_verdict` are available in the pending list response but the HITLModal makes a separate `getHitlDetail()` call to get the full data. These summary fields are wasted.

---

### 1.11 Ecosystem/Theoretical Types

#### `BlobData` (client.ts:612-620)

```typescript
export interface BlobData {
  id: string;
  name: string;
  definition: string;
  version: number;
  relevance: number;
  saturation: string;
  is_core: boolean;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | Canvas lookup, select target |
| ✅ Used | `name` | CategoryBlob label; ElaborationPanel header; core badge |
| ✅ Used | `definition` | ElaborationPanel definition paragraph |
| ✅ Used | `version` | ElaborationPanel badge |
| ✅ Used | `relevance` | Circle radius on canvas (`blobRadius()`) |
| ✅ Used | `saturation` | ElaborationPanel saturation display; CategoryBlob pulsating state |
| ✅ Used | `is_core` | CategoryBlob special render (dashed ring); ElaborationPanel badge; bottom bar (Playground L278-280) |

**All fields consumed** ✅

#### `TendrilData` (client.ts:622-632)

```typescript
export interface TendrilData {
  id: string;
  category_ids: string[];
  code_id: string;
  status: string;
  converging: number;
  diverging: number;
  fit: number;
  layer: string;
  tension: number;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | Canvas lookup, select target |
| ✅ Used | `category_ids` | Canvas edge endpoints (requires at least 2) |
| ✅ Used | `code_id` | ElaborationPanel tendril detail header |
| ✅ Used | `status` | Canvas (emerging = dashed, lower opacity) |
| ✅ Used | `converging` | Canvas line thickness; ElaborationPanel evidence count |
| ✅ Used | `diverging` | Canvas "fissure" overlay; ElaborationPanel evidence count |
| ✅ Used | `fit` | ElaborationPanel progress bar |
| ✅ Used | `layer` | Canvas line color |
| ✅ Used | `tension` | Canvas fissure opacity |

**All fields consumed** ✅

#### `GhostData` (client.ts:634-638)

```typescript
export interface GhostData {
  id: string;
  content: string;
  type: string;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | Canvas lookup, drag source |
| ✅ Used | `content` | GhostBlob label (first 60 chars) |
| ❌ Unused | `type` | NEVER read in GhostBlob or anywhere |

**Gap**: `type` is fetched but never displayed.

#### `EcosystemLayout` (client.ts:646-651)

```typescript
export interface EcosystemLayout {
  blob_positions: Record<string, { x: number; y: number }>;
  ghost_positions: Record<string, { x: number; y: number }>;
  fog_zones: Record<string, any>;
  physics_params: Record<string, number>;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ❌ Unused | `blob_positions` | Layout positions are NOT used; canvas uses spiral/grid algorithm instead |
| ❌ Unused | `ghost_positions` | Ghosts are placed in a grid on the right side |
| ❌ Unused | `fog_zones` | Never rendered in canvas |
| ❌ Unused | `physics_params` | Never applied to canvas |

**Key Gap**: The entire `EcosystemLayout` is fetched by `getEcosystem()` but COMPLETELY IGNORED. The canvas calculates positions client-side. `saveEcosystemLayout()` is never called either. This is a major dead feature.

#### `Relationship` (client.ts:653-666)

```typescript
export interface Relationship {
  id: string;
  category_ids: string[];
  theoretical_code_id: string;
  elaboration_status: string;
  direction: string | null;
  converging_docs: number;
  diverging_docs: number;
  conceptual_fit: number;
  layer: string;
  position_tension: number;
  question: string;
  code_name: string;
}
```

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | Fetch lookup |
| ⚠️ Unused | ALL except `id` | `getRelationship()` is called in RelationshipTendril (L47) but the RESULT is DISCARDED — only `pg.selectTendril(tendril as any)` is used, using existing TendrilData, not the returned Relationship detail |

**Key Gap**: `getRelationship()` fetches detail data but the response is completely thrown away. The ElaborationPanel uses TendrilData for rendering, not Relationship.

#### `RenameSuggestion` / `RenameSuggestions` (client.ts:668-681)

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `name` | Radio button label in RenameModal |
| ✅ Used | `level` | Groups suggestions (conservative/moderate/transformative) |
| ✅ Used | `rationale` | Not directly displayed in UI (stored in state but not shown) |
| ✅ Used | `what_it_gains` | Displayed below suggestion name (L110) |
| ❌ Unused | `in_vivo_inspiration` | Optional field; NEVER displayed |
| ✅ Used | `needs_rename` | Trigger for showing rename modal |
| ✅ Used | `suggestions[]` | Full list rendered |

**Minor gap**: `rationale` is stored in state but not shown to user. `in_vivo_inspiration` is never rendered.

#### `DefinitionVersion` (client.ts:683-690)

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `version` | Timeline ordering; active indicator (last = purple) |
| ✅ Used | `name` | Displayed in CategoryEvolutionPanel |
| ✅ Used | `definition` | Displayed in CategoryEvolutionPanel |
| ✅ Used | `trigger` | Mapped to translated label via `triggerLabels` |
| ✅ Used | `detail` | Displayed if non-null |
| ✅ Used | `created_at` | Displayed as timestamp |

**All fields consumed** ✅

#### `Recommendation` (client.ts:692-705)

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `category` | Not displayed (used internally?) |
| ✅ Used | `title` | Recommendation card title |
| ✅ Used | `description` | Recommendation card description |
| ✅ Used | `action_type` | Groups recommendations + determines button label |
| ❌ Unused | `category_ids` | Fetch but never displayed |
| ❌ Unused | `suggested_code` | Fetch but never displayed |
| ❌ Unused | `impact_score` | Fetch but never displayed |

**Gap**: Three fields fetched but not rendered.

#### `TheoreticalCode` (client.ts:599-610)

| Status | Field | Where Used |
|--------|-------|------------|
| ✅ Used | `id` | Internal lookup (not shown in UI) |
| ❌ Unused | `name` | The codes are fetched but the UI doesn't display them — playgroundContext stores them but no component reads `theoreticalCodes` from context |
| ❌ Unused | ALL (family, description, glaserian, user_defined, evaluation_logic, compatible_with, layer, visualization_hint) | Complete waste |

**Key Gap**: `getTheoreticalCodes()` fetches codes into PlaygroundContext state, but NO COMPONENT in the playground reads `pg.theoreticalCodes`. The data is fetched, stored, and never displayed.

#### `ModelSummary` (client.ts:707-711)

```typescript
export interface ModelSummary {
  relationships: TendrilData[];
  orphan_categories: { id: string; name: string }[];
  layers_coverage: { covered: string[]; missing: string[] };
}
```

| Status | Field | Notes |
|--------|-------|-------|
| ❌ Unused | ALL | `getTheoreticalModel()` is **never called** anywhere |

---

## Section 2: Displayed vs Received Data (Project.tsx)

### 2.1 Project Fields — Detailed Consumption

| Field | Fetched? | Rendered? | Location in JSX |
|-------|----------|-----------|-----------------|
| `id` | ✅ | Route param only | URL-only |
| `nombre` | ✅ | ✅ | Navbar title (L1467) |
| `ruta_de_codificacion` | ✅ | ✅ | Header metadata (L1641); MemoHistory prop (L3146) |
| `estado` | ✅ | ✅ | Header metadata (L1641); stale entity query (L254) |
| `creador_id` | ✅ | ❌ | — |
| `creado_en` | ✅ | ❌ | — |
| `num_documentos` | ✅ | ❌ | Uses `docs.length` instead |
| `num_categorias` | ✅ | ❌ | Uses `cats.length` instead |
| `supuesto_poblacional` | ✅ | ✅ | Population section (L1809-1834) |
| `object_of_study` | ✅ | ✅ | Experimental mode state (L283) |
| `population_assumption` | ✅ | ✅ | Population section (L1839-1852) |
| `config_segmentacion` | ✅ | ❌ | — |
| `coding_style_instruction` | ✅ | ❌ | — |
| `config_mutation_policy` | ✅ | ❌ | — |

**Received but IGNORED**: 7 of 14 fields (`creador_id`, `creado_en`, `num_documentos`, `num_categorias`, `config_segmentacion`, `coding_style_instruction`, `config_mutation_policy`) = 50% waste

### 2.2 Document Fields — Detailed Consumption

| Field | Fetched? | Rendered? | Location in JSX |
|-------|----------|-----------|-----------------|
| `id` | ✅ | ✅ | Implicit key; drag-drop; segment lookup |
| `proyecto_id` | ✅ | ❌ | — |
| `original_filename` | ✅ | ✅ | Doc card title (L2559) |
| `tipo_de_fuente` | ✅ | ❌ | — |
| `storage_key` | ✅ | ❌ | — (internal, correct to ignore) |
| `mime_type` | ✅ | ✅ | Badge via `mimeLabel()` (L2563) |
| `size_bytes` | ✅ | ❌ | — |
| `creado_en` | ✅ | ❌ | — |
| `estado` | ✅ | ✅ | Status badge (L1347-1426); preprocessing condition |
| `texto_extraido` | ✅ | ✅ | Textarea content (L2936-2942) |
| `texto_preprocesado` | ✅ | ✅ | Toggle view (L2925) |
| `texto_original` | ✅ | ✅ | Toggle view (L2928) |
| `preprocess_warning` | ✅ | ✅ | Warning badge (L2583-2604) |
| `sort_order` | ✅ | ⚠️ | Implicit in reorder API; not rendered |

**Received but IGNORED**: 5 of 14 fields (`proyecto_id`, `tipo_de_fuente`, `size_bytes`, `creado_en`, `storage_key`) = ~36% waste (excluding `storage_key` as legitimate internal field = ~29%)

### 2.3 PipelineLog.summary Fields — All Used Check

| Field | Used? | Where |
|-------|-------|-------|
| `total` | ✅ | Stage derivation, completion check |
| `need_segment` | ✅ | DocsNeedSegment pills, stage derivation |
| `need_agents` | ✅ | DocsNeedAgents pills, stage derivation |
| `need_synthesis` | ✅ | Pipeline continue check, Playground newDocs banner |
| `sintetizados` | ❌ | **Never read** |
| `done` | ✅ | DocsDone, completion check |
| `failed` | ✅ | Error detection |
| `failed_tasks` | ✅ | Error detection |
| `errors` | ✅ | Filename extraction for error messages |
| `categories` | ⚠️ | Not directly used |
| `project_state` | ✅ | Stage derivation, playground ready banner |
| `playground_ready` | ✅ | Stage derivation, link enable/disable |

### 2.4 DocPipelineLog Fields — Per-Document Log

| Field | Used? | Where |
|-------|-------|-------|
| `document_id` | ✅ | getDocLog() lookup |
| `filename` | ❌ | Uses doc.original_filename instead |
| `estado` | ❌ | Uses doc.estado instead |
| `steps.text_extracted` | ❌ | **Never read** |
| `steps.punctuation_fixed` | ❌ | **Never read** |
| `steps.segmented` | ❌ | **Never read** |
| `steps.coded` | ❌ | **Never read** |
| `steps.agents_done` | ❌ | **Never read** |
| `steps.synthesis_done` | ❌ | **Never read** |
| `segments_count` | ✅ | hasSegments() helper |
| `codes_count` | ❌ | **Never read** |
| `next_action` | ✅ | Pipeline continue logic |

### 2.5 Category Display

In Project.tsx, categories are fetched by `listCategories()` but ONLY `cats.length` is ever displayed:

- L1481: `{docs.length} docs · {cats.length} cats`
- `cats` array is passed to no other component
- Individual category `nombre`, `definicion`, `estado_saturacion`, `es_central` are COMPLETELY IGNORED

### 2.6 Segment Display

Segments are fetched per-document via `listSegments()`. What's rendered:

- Segment count pill: `{n}` (L2873)
- Segment `texto` in the segment view
- That's it. `parafrasis`, `posicion`, `conteo_tokens`, `es_anomalia` are never displayed.

---

## Section 3: API Functions Used vs Unused

### Key
- ✅ **Used** — Called from at least one component/page
- ❌ **UNUSED** — Defined in client.ts but never called anywhere
- ⚠️ **Imported but not called** — Imported in a file but the call is dead code or commented out

### 3.1 Auth

| Function | Status | Consumer |
|----------|--------|----------|
| `login` | ✅ | `Login.tsx` |
| `ping` | ✅ | `Project.tsx` (L260 — gets user_id for display) |

### 3.2 Projects

| Function | Status | Consumer |
|----------|--------|----------|
| `listProjects` | ✅ | `Projects.tsx` |
| `createProject` | ✅ | `Projects.tsx` |
| `getProject` | ✅ | `Project.tsx` (L251) |
| `updateProject` | ✅ | `Project.tsx` (L1245 — experimental mode pattern switch) |
| `deleteProject` | ✅ | `Projects.tsx` |
| `deleteAllDocuments` | ✅ | `Project.tsx` (L1160) |

### 3.3 Project Config

| Function | Status | Consumer |
|----------|--------|----------|
| `getProjectConfig` | ✅ | `ProjectConfigPanel.tsx` |
| `getProjectConfigHistory` | ✅ | `ProjectConfigPanel.tsx` |
| `updateMutationPolicy` | ✅ | `ProjectConfigPanel.tsx` |
| `updatePopulationAssumption` | ✅ | `Project.tsx` (L1198); `ProjectConfigPanel.tsx` |
| `generatePopulationGeneralization` | ✅ | `Project.tsx` (L1180) |

### 3.4 Research Question

| Function | Status | Consumer |
|----------|--------|----------|
| `getResearchQuestion` | ✅ | `ProjectConfigPanel.tsx` |
| `previewResearchQuestionStandalone` | ✅ | `Projects.tsx` (create page debounced preview) |
| `previewResearchQuestion` | ❌ | **UNUSED** — declared but never called |
| `updateResearchQuestion` | ✅ | `ProjectConfigPanel.tsx` |
| `generateResearchQuestion` | ✅ | `ProjectConfigPanel.tsx` |

### 3.5 Documents

| Function | Status | Consumer |
|----------|--------|----------|
| `listDocuments` | ✅ | `Project.tsx` (L401) |
| `getPresignedUrl` | ❌ | **UNUSED** — declared but never called (documents are uploaded directly, not via presigned URL) |
| `uploadDocument` | ✅ | `Project.tsx` (L1144) |
| `punctuateDocument` | ✅ | `Project.tsx` (L467) |
| `getTaskStatus` | ✅ | `Project.tsx` (L490 — punctuation polling) |
| `processDocument` | ❌ | **UNUSED** — declared but never called |
| `deleteDocument` | ✅ | `Project.tsx` (L2787) |
| `restoreDocumentOriginal` | ✅ | `Project.tsx` (L2708) |
| `deleteDocumentSegments` | ✅ | `Project.tsx` (L2888) |
| `resetDocsToCrudo` | ✅ | `Project.tsx` (L2439) |
| `segmentDocument` | ❌ | **UNUSED** — segmentation is done via pipeline, not directly |
| `saveTaskSegments` | ❌ | **UNUSED** — declared but never called |

### 3.6 Categories

| Function | Status | Consumer |
|----------|--------|----------|
| `listCategories` | ✅ | `Project.tsx` (L259) |
| `createCategory` | ❌ | **UNUSED** — declared but never called |

### 3.7 Segments

| Function | Status | Consumer |
|----------|--------|----------|
| `listSegments` | ✅ | `Project.tsx` (L411) |

### 3.8 Pipeline

| Function | Status | Consumer |
|----------|--------|----------|
| `getPipelineLog` | ✅ | `Project.tsx` (L263, L905, L1041, L1126, L1147, L1700, L3270); `Playground.tsx` (L48) |
| `getPipelineStatus` | ❌ | **UNUSED** — declared but never called |
| `getAgentMemos` | ✅ | `Project.tsx` (L266, L375) |
| `getAgentLogs` | ✅ | `Project.tsx` (L272, L895) |
| `getPipelineDecisions` | ✅ | `PlaygroundDataPanel.tsx` |

### 3.9 HITL

| Function | Status | Consumer |
|----------|--------|----------|
| `getPendingHitl` | ✅ | `Project.tsx` (L388 — polling interval) |
| `decideHitl` | ✅ | `HITLModal.tsx` |
| `getHitlDetail` | ✅ | `HITLModal.tsx` |

### 3.10 Memos

| Function | Status | Consumer |
|----------|--------|----------|
| `getAvailableMemoTypes` | ✅ | `AddMemoModal.tsx` |
| `getEntityTypeColors` | ✅ | `MemoHistory.tsx` |
| `createMemo` | ✅ | `AddMemoModal.tsx` |
| `getStaleUserEntities` | ✅ | `Project.tsx` (L254) |
| `deleteMemosByType` | ✅ | `MemoHistory.tsx` |

### 3.11 Ecosystem / Theory (Playground)

| Function | Status | Consumer |
|----------|--------|----------|
| `getEcosystem` | ✅ | `PlaygroundContext.tsx` (L59) |
| `saveEcosystemLayout` | ❌ | **UNUSED** — no layout is ever persisted |
| `getTheoreticalCodes` | ⚠️ | `PlaygroundContext.tsx` (L63) — data fetched but NEVER read by any component |
| `createTheoreticalCode` | ❌ | **UNUSED** |
| `getRelationships` | ✅ | `PlaygroundContext.tsx` (L60) |
| `getRelationship` | ⚠️ | `RelationshipTendril.tsx` (L47) — result is DISCARDED |
| `elaborateRelationship` | ⚠️ | `EcosystemCanvas.tsx` (L6) — imported but only used in drag-drop TODO code |
| `resolveDivergence` | ❌ | **UNUSED** |
| `getGhosts` | ✅ | `PlaygroundContext.tsx` (L61) |
| `absorbGhost` | ❌ | **UNUSED** |
| `getRenameSuggestions` | ✅ | `CategoryBlob.tsx` (L53); `RenameModal.tsx` (L23) |
| `applyRename` | ✅ | `RenameModal.tsx` (L33); `CategoryBlob.tsx` |
| `getDefinitionHistory` | ✅ | `CategoryBlob.tsx` (L54); `CategoryEvolutionPanel.tsx` (L21) |
| `getRecommendations` | ✅ | `PlaygroundContext.tsx` (L62) |
| `getTheoreticalModel` | ❌ | **UNUSED** |
| `getSaturationGaps` | ❌ | **UNUSED** |
| `refreshSaturationGaps` | ❌ | **UNUSED** |

### 3.12 Admin / Worker Control

| Function | Status | Consumer |
|----------|--------|----------|
| `stopProjectPipeline` | ✅ | `Project.tsx` (L1106) |
| `restartFailedTasks` | ⚠️ | Imported in `Project.tsx` but **never called** |
| `stopWorker` | ❌ | **UNUSED** |
| `killAllWorkers` | ❌ | **UNUSED** |
| `cancelTask` | ❌ | **UNUSED** (but cancelTask endpoint is called directly via fetch in Project.tsx L640 for punctuation) |
| `restartTask` | ❌ | **UNUSED** |
| `resumeTask` | ❌ | **UNUSED** |

### 3.13 Setup

| Function | Status | Consumer |
|----------|--------|----------|
| `getSetupStatus` | ✅ | `Setup.tsx` |
| `initializeSetup` | ✅ | `Setup.tsx` |
| `getSetupProgress` | ✅ | `Setup.tsx` |

---

## Section 4: Playground Data Analysis

### 4.1 Data Flow Summary

```
PlaygroundContext.refreshEcosystem()
  ├─ getEcosystem(projectId)        → { blobs, tendrils, layout }
  ├─ getRelationships(projectId)     → Relationship[]  // NOTE: not used directly
  ├─ getGhosts(projectId)            → GhostData[]
  ├─ getRecommendations(projectId)   → Recommendation[]
  └─ getTheoreticalCodes(projectId)  → TheoreticalCode[]  // STORED BUT NEVER DISPLAYED

Playground.tsx (direct)
  └─ getPipelineLog(projectId)       → summary.need_synthesis (new docs banner)

PlaygroundDataPanel (child component)
  └─ getPipelineDecisions(projectId) → PipelineDecisions (gate decisions + saturation)
```

### 4.2 Data Fetched but NOT Displayed in Playground

| Data | Fetched By | Consumer Problem |
|------|-----------|-----------------|
| `EcosystemLayout` (blob_positions, ghost_positions, fog_zones, physics_params) | `getEcosystem()` | Canvas calculates positions client-side; layout data ignored |
| `TheoreticalCode[]` | `PlaygroundContext` | Stored in state (`pg.theoreticalCodes`) but NO component reads it |
| `Relationship[]` detail from `getRelationships()` | `PlaygroundContext` | Data is fetched but the result is **completely discarded** — `setRelationships()` is never called; only `eco.tendrils` from `getEcosystem()` is used |
| `Relationship` detail from `getRelationship()` | `RelationshipTendril.tsx` | Result fetched on click but `const detail = await getRelationship(...)` is discarded (L47) |
| `Recommendation.category_ids` | `PlaygroundContext` | Recommendations displayed but `category_ids` field not shown |
| `Recommendation.suggested_code` | `PlaygroundContext` | Not displayed |
| `Recommendation.impact_score` | `PlaygroundContext` | Not displayed |
| `RenameSuggestion.in_vivo_inspiration` | `RenameModal` | Optional field never rendered |
| `GhostData.type` | `PlaygroundContext` | Not displayed |

### 4.3 Displayed Data by Playground Component

#### EcosystemCanvas
- `EcosystemState.blobs[]` → `{ id, name, saturation, is_core, relevance, version }` (via CategoryBlob props)
- `EcosystemState.tendrils[]` → `{ id, category_ids, status, converging, diverging, fit, layer, tension }` (via RelationshipTendril props)
- `GhostData[]` → `{ id, content }` (via GhostBlob props; `type` ignored)

#### ElaborationPanel
- `BlobData` → `{ name, definition, version, is_core, saturation, id }`
- `TendrilData` → `{ code_id, converging, diverging, fit, layer }`

#### RecommendationGuide
- `Recommendation[]` → `{ title, description, action_type, category }`

#### RenameModal
- `RenameSuggestion[]` → `{ name, level, what_it_gains }` (rationale stored but not shown; in_vivo_inspiration ignored)

#### PlaygroundDataPanel
- `PipelineDecisions.decisions[]` → `{ gate, proposal, status }` (decision, note, decided_at NOT displayed)
- `PipelineDecisions.saturation` → `{ [name]: { no_expansion_count, saturated } }`

#### Bottom Bar (Playground.tsx render)
- `pg.blobs.length` → categories count
- `pg.tendrils.length` → relationships count
- `pg.recommendations.length` → gaps count
- `coreBlob.name` → core category name

### 4.4 What Playground Needs but Has NO Backend Source

| UI Element | Data Needed | Backend Source | Status |
|------------|------------|----------------|--------|
| "New Data" banner | `need_synthesis` count | `getPipelineLog().summary.need_synthesis` | ✅ Has source |
| Pipeline decisions panel | Gate decisions + saturation | `getPipelineDecisions()` | ✅ Has source |
| Category canvas blobs | Category positions (from saved layout) | `EcosystemLayout.blob_positions` | ⚠️ Source exists but FRONTEND IGNORES IT |
| Ghost canvas positions | Ghost positions | `EcosystemLayout.ghost_positions` | ⚠️ Source exists but FRONTEND IGNORES IT |
| Fog zones on canvas | Fog zone definitions | `EcosystemLayout.fog_zones` | ⚠️ Source exists but FRONTEND IGNORES IT |
| Theoretical codes reference | Available codes | `getTheoreticalCodes()` | ⚠️ Source exists but FRONTEND NEVER DISPLAYS IT |
| Category evolution history | Definition versions | `getDefinitionHistory()` | ✅ Has source (but only via CategoryBlob click) |
| Theoretical model summary | `ModelSummary` | `getTheoreticalModel()` | ⚠️ **ENDPOINT EXISTS but NEVER CALLED** |
| Saturation gaps report | Gap analysis | `getSaturationGaps()` | ⚠️ **ENDPOINT EXISTS but NEVER CALLED** |
| Relationship detail modal | Full relationship data | `getRelationship()` | ⚠️ Source exists but RESULT DISCARDED |

---

## Section 5: Summary of Dead Data & Dead Code

### 5.1 Unused API Functions (16 functions — dead code in client.ts)

1. `previewResearchQuestion` — project-scoped RQ preview (standalone version is used in create page)
2. `getPresignedUrl` — no consumer
3. `processDocument` — no consumer (pipeline orchestrator handles processing)
4. `segmentDocument` — no consumer (segmentation via pipeline)
5. `saveTaskSegments` — no consumer
6. `createCategory` — no consumer
7. `getPipelineStatus` — no consumer (getPipelineLog used instead)
8. `stopWorker` — no consumer
9. `killAllWorkers` — no consumer
10. `cancelTask` — no consumer (direct fetch used in one place)
11. `restartTask` — no consumer
12. `resumeTask` — no consumer
13. `createTheoreticalCode` — no consumer
14. `saveEcosystemLayout` — no consumer (layout positions ignored)
15. `resolveDivergence` — no consumer
16. `absorbGhost` — no consumer
17. `getTheoreticalModel` — no consumer
18. `getSaturationGaps` — no consumer
19. `refreshSaturationGaps` — no consumer

### 5.2 Unused TypeScript Interface Fields (data over-fetching)

| Interface | Unused Fields | Wasted % |
|-----------|--------------|----------|
| `Project` | `creador_id`, `creado_en`, `num_documentos`, `num_categorias`, `config_segmentacion`, `coding_style_instruction`, `config_mutation_policy` | 50% |
| `Document` | `proyecto_id`, `tipo_de_fuente`, `size_bytes`, `creado_en` (+ `storage_key` for UI purposes) | 29-36% |
| `DocPipelineLog` | `filename`, `estado`, `steps.*` (6 fields), `codes_count` | 75% |
| `PipelineLog.summary` | `sintetizados` | 8% |
| `PipelineLogError` | `document_id`, `estado` | 67% |
| `PipelineStatus` | ALL (entire interface unused) | 100% |
| `Category` | `proyecto_id`, `nombre`, `definicion`, `estado_saturacion`, `es_central` | 83% (in Project.tsx) |
| `Segment` | `documento_id`, `parafrasis`, `posicion`, `conteo_tokens`, `es_anomalia` | 71% |
| `HitlPendingItem` | `id`, `proposal_summary`, `critic_verdict`, `created_at` | 80% |
| `EcosystemLayout` | ALL (blob_positions, ghost_positions, fog_zones, physics_params) | 100% |
| `Recommendation` | `category_ids`, `suggested_code`, `impact_score` | 43% |
| `TheoreticalCode` | ALL (entire array unused in UI) | 100% |
| `ModelSummary` | ALL (entire interface unused) | 100% |

### 5.3 Data Fetched via Context but Discarded

| Context State | Set By | Read By | Status |
|--------------|--------|---------|--------|
| `pg.theoreticalCodes` | `PlaygroundContext` L68 | **Nothing** | Dead data |
| `pg.relationDetail` | Never set | **Nothing** | Dead field |
| `pg.definitionHistory` | Never set via context | **Nothing** | Dead field (fetched in CategoryBlob directly) |
| `pg.renameSuggestions` | Never set via context | **Nothing** | Dead field (fetched in RenameModal directly) |
| `pg.dragState` | `EcosystemCanvas` / `GhostBlob` | `EcosystemCanvas` (partially) | Underutilized |

### 5.4 Imported but Never Called

- `restartFailedTasks` — imported in Project.tsx L25, never invoked
- `elaborateRelationship` — imported in EcosystemCanvas.tsx L6, only used in TODO code path (drop handler that doesn't execute the API call)

---

## Section 6: Recommendations

### High Priority (remove dead data from API responses)

1. **Remove `PipelineStatus` endpoint** or deprecate it — `getPipelineLog` provides equivalent data and is actually used
2. **Trim `DocPipelineLog`** — remove `steps.*` (6 booleans) and `codes_count` from the response, or add UI to display them
3. **Trim `Project` response** — remove `num_documentos`, `num_categorias`, `config_segmentacion`, `coding_style_instruction`, `config_mutation_policy` from the project list endpoint (they belong only in config endpoint)
4. **Add `sintetizados` display** or remove from PipelineLog.summary
5. **Add Segment detail display** — `parafrasis`, `posicion`, `es_anomalia` have potential value

### Medium Priority (dead code cleanup)

6. **Remove 19 unused API functions** from `client.ts` (or comment as "planned")
7. **Implement or remove `EcosystemLayout` persistence** — currently a round-trip waste
8. **Display `TheoreticalCode` data** in playground or stop fetching it

### Low Priority (UI enhancements)

9. **Display `tipo_de_fuente`** in document cards (e.g., "Interview", "Field Note")
10. **Display `size_bytes`** as human-readable file size
11. **Display `es_anomalia`** as a flag on anomalous segments
12. **Wire up `getTheoreticalModel()`** to show model summary in playground
13. **Wire up `getSaturationGaps()`** to show gap analysis in playground
