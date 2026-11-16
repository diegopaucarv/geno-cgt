const API_BASE = "/api/v1";

export function getToken(): string | null {
  return localStorage.getItem("access_token");
}

function getRefreshToken(): string | null {
  return localStorage.getItem("refresh_token");
}

export function setToken(token: string) {
  localStorage.setItem("access_token", token);
}

export function setRefreshToken(token: string) {
  localStorage.setItem("refresh_token", token);
}

export function clearToken() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

let _refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  // Deduplicate concurrent refresh attempts
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    try {
      const res = await fetch(
        `${API_BASE}/auth/refresh?refresh_token=${encodeURIComponent(refresh)}`,
        {
          method: "POST",
        },
      );
      if (!res.ok) return null;
      const data = await res.json();
      setToken(data.access_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    // Try refresh once
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    }
  }

  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const error = new Error(err.detail || `HTTP ${res.status}`) as Error & {
      status?: number;
    };
    error.status = res.status;
    throw error;
  }
  return res.json();
}

// ── Types ───────────────────────────────────────────────────────────

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

export interface ConfigHistoryEntry {
  id: string;
  field: string;
  old_value: string | null;
  new_value: string;
  triggered_by: string;
  agent_run_id: string | null;
  mutation_level: string | null;
  rationale: string | null;
  confidence: number | null;
  context: Record<string, any> | null;
  timestamp: string | null;
}

export interface ConfigHistory {
  project_id: string;
  total: number;
  entries: ConfigHistoryEntry[];
}

export interface ConfigSuggestion {
  id: string;
  field: string;
  old_value: string | null;
  new_value: string;
  triggered_by: string;
  rationale: string | null;
  confidence: number | null;
  context: Record<string, any> | null;
  timestamp: string | null;
}

/** One Glaser-classified span as returned flattened by the backend. */
export interface GlaserBlock {
  class: string;
  start_pos: number;
  end_pos: number;
  segment_positions: number[];
  confidence?: string;
  text: string;
}

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
  texto_clasificado?: string;
  texto_original?: string;
  preprocess_warning?: string;
  sort_order?: number;
  glaser_blocks?: GlaserBlock[];
  glaser_used_fallback?: boolean;
}

export interface PipelineStatus {
  project_id: string;
  documents: number;
  segments: number;
  categories: number;
  hypotheses: number;
  stages: Record<string, "done" | "in_progress" | "pending">;
}

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
    /** Classification metadata persisted (absent in older backends). */
    classified?: boolean;
    /** At least one extracted incident (absent in older backends). */
    incidents?: boolean;
  };
  segments_count: number;
  codes_count: number;
  /** `metadatos.glaser_blocks`/`texto_clasificado` present in the DB. */
  has_classification: boolean;
  /** Segments carrying a Glaser tag. */
  classified_count: number;
  /** Rows in `extracted_incidents` for this document. */
  incidents_count: number;
  /** State combinations the classify-first ladder cannot produce. */
  inconsistencies: string[];
  next_action:
    | "extract_text"
    | "segment"
    | "classify"
    | "run_agents"
    | "run_synthesis"
    | "done"
    | "error";
}

export interface PipelineLogError {
  document_id: string;
  filename: string;
  estado: string;
}

export interface PipelineLog {
  project_id: string;
  documents: DocPipelineLog[];
  summary: {
    total: number;
    need_segment: number;
    /** Docs that still need Glaser classification (absent in older logs). */
    need_classify?: number;
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
    /** UI agent ids with a task still in flight (derived server-side). */
    running_agents?: string[];
    /** UI agent ids whose last task succeeded within the 4 h window. Lets the
     *  UI show ↻ (re-run) instead of ▶ after reloading mid-run. */
    succeeded_agents?: string[];
    /** Stage keys whose phase orchestrator is in flight. Phase tasks are not
     *  individual agents, so they spin the whole stage instead. */
    running_phases?: string[];
    /** Runs still marked 'running'. If nothing is in flight they are leftovers
     *  from a dead worker and the UI offers to close them. */
    open_runs?: number;
    /** Documents whose state contradicts the classify-first ladder. */
    docs_inconsistent?: number;
    /** Documents whose next step is Glaser classification. */
    docs_need_classify?: number;
  };
}

export interface Category {
  id: string;
  proyecto_id: string;
  nombre: string;
  definicion: string;
  estado_saturacion: string;
  es_central: boolean;
}

export interface Segment {
  id: string;
  documento_id: string;
  texto: string;
  parafrasis: string | null;
  posicion: number;
  conteo_tokens: number;
  es_anomalia: boolean;
  tipo_dato_glaser?: string | null;
}

// ── Auth ────────────────────────────────────────────────────────────

export async function login(email: string, password: string) {
  const params = new URLSearchParams({ email, password });
  const res = await fetch(`${API_BASE}/auth/login?${params}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Credenciales inválidas");
  const data = await res.json();
  setToken(data.access_token);
  if (data.refresh_token) setRefreshToken(data.refresh_token);
  return data;
}

export async function ping() {
  return request<{ status: string; user_id: string }>("/ping");
}

// ── Projects ────────────────────────────────────────────────────────

export async function listProjects() {
  return request<Project[]>("/projects");
}

export async function createProject(body: {
  nombre: string;
  ruta_de_codificacion?: string;
  supuesto_poblacional?: string;
  object_of_study?: string;
  custom_label?: string;
  processing_verb?: string;
  processing_gerund?: string;
}) {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getProject(id: string) {
  return request<Project>(`/projects/${id}`);
}

export async function updateProject(
  id: string,
  body: {
    nombre?: string;
    supuesto_poblacional?: string;
    object_of_study?: string;
    custom_label?: string;
  },
) {
  return request<Project>(`/projects/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteProject(id: string) {
  return request<{ status: string; nombre: string; id: string }>(
    `/projects/${id}`,
    { method: "DELETE" },
  );
}

export async function deleteAllDocuments(projectId: string) {
  return request<{ status: string; count: number; project_id: string }>(
    `/projects/${projectId}/documents`,
    { method: "DELETE" },
  );
}

export async function getProjectConfig(projectId: string) {
  return request<ProjectConfig>(`/projects/${projectId}/config`);
}

export async function getProjectConfigHistory(
  projectId: string,
  field?: string,
  limit?: number,
) {
  const params = new URLSearchParams();
  if (field) params.set("field", field);
  if (limit) params.set("limit", String(limit));
  const qs = params.toString();
  return request<ConfigHistory>(
    `/projects/${projectId}/config/history${qs ? "?" + qs : ""}`,
  );
}

export async function updateMutationPolicy(
  projectId: string,
  policy: Record<string, string>,
) {
  return request<{
    status: string;
    message: string;
    mutation_policy: Record<string, string>;
  }>(`/projects/${projectId}/config/mutation-policy`, {
    method: "PUT",
    body: JSON.stringify(policy),
  });
}

export async function updatePopulationAssumption(
  projectId: string,
  body: Record<string, any>,
) {
  return request<{
    status: string;
    population_assumption: Record<string, any>;
    supuesto_poblacional: string | null;
  }>(`/projects/${projectId}/config/population-assumption`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** Trigger the f0_population_generalizer (FLASH) on an existing project. */
export async function generatePopulationGeneralization(projectId: string) {
  return request<{
    status: string;
    population_assumption: Record<string, any>;
    supuesto_poblacional: string | null;
  }>(`/projects/${projectId}/config/population-assumption/generalize`, {
    method: "POST",
  });
}

// ── Research Question (Nemotrón / F0.6) ──────────────────────────────

export interface KeyDimension {
  dimension: string;
  rationale: string;
}

export interface ResearchQuestionResponse {
  project_id: string;
  research_question: string | null;
  operational_question: string | null;
  rationale: string | null;
  key_dimensions: KeyDimension[] | null;
  generated_at: string | null;
  message?: string;
}

export interface RQPreviewResponse {
  research_question: string;
  operational_question: string;
  oq_discovery?: string;
  oq_selective?: string;
  oq_theoretical?: string;
  population_number: string;
  conjugated_verb: string;
  language: string;
}

export interface GenerateResearchQuestionResponse {
  project_id: string;
  research_question: string;
  operational_question: string;
  oq_discovery?: string;
  oq_selective?: string;
  oq_theoretical?: string;
  generated_at: string;
  auto_generated?: boolean;
  population_number: string;
  conjugated_verb: string;
  language: string;
  /** Legacy async fields — the endpoint is synchronous. */
  status?: string;
  task_id?: string;
  message?: string;
}

export async function getResearchQuestion(projectId: string) {
  return request<ResearchQuestionResponse>(
    `/projects/${projectId}/research-question`,
  );
}

export async function previewResearchQuestionStandalone(body: {
  population: string;
  object_of_study: string;
  processing_verb: string;
  custom_label?: string;
}) {
  return request<RQPreviewResponse>(`/projects/research-question/preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function previewResearchQuestion(
  projectId: string,
  body: {
    population: string;
    object_of_study: string;
    processing_verb: string;
    custom_label?: string;
  },
) {
  return request<RQPreviewResponse>(
    `/projects/${projectId}/research-question/preview`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function updateResearchQuestion(
  projectId: string,
  body: { research_question?: string; operational_question?: string },
) {
  return request<ResearchQuestionResponse>(
    `/projects/${projectId}/research-question`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

export async function generateResearchQuestion(projectId: string) {
  return request<GenerateResearchQuestionResponse>(
    `/projects/${projectId}/research-question/generate`,
    { method: "POST" },
  );
}

// ── Documents ───────────────────────────────────────────────────────

export async function listDocuments(proyecto_id: string) {
  return request<Document[]>(`/documents?proyecto_id=${proyecto_id}`);
}

export async function getPresignedUrl(document_id: string) {
  return request<{ url: string }>(`/documents/presigned/${document_id}`);
}

export async function uploadDocument(projectId: string, file: File) {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/documents/upload/${projectId}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Categories ──────────────────────────────────────────────────────

export async function listCategories(proyecto_id: string) {
  return request<Category[]>(`/categories?proyecto_id=${proyecto_id}`);
}

export async function createCategory(body: {
  proyecto_id: string;
  nombre: string;
  definicion: string;
}) {
  return request<Category>("/categories", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Segments ────────────────────────────────────────────────────────

export async function listSegments(document_id: string) {
  return request<Segment[]>(`/documents/${document_id}/segments`);
}

export async function segmentDocument(documentId: string) {
  return request<{ status: string; num_segmentos?: number; task_id?: string }>(
    `/documents/${documentId}/segment`,
    { method: "POST" },
  );
}

export async function deleteDocumentSegments(
  documentId: string,
  opts?: { keepClassification?: boolean },
) {
  // Bajo la escalera classify-first los segmentos derivan del texto ya
  // clasificado, así que borrarlos puede conservar la clasificación.
  const query = opts?.keepClassification ? "?keep_classification=true" : "";
  return request<{ status: string; message: string }>(
    `/documents/${documentId}/segments${query}`,
    { method: "DELETE" },
  );
}

export async function deleteDocumentIncidents(documentId: string) {
  return request<{ status: string; deleted: number }>(
    `/documents/${documentId}/incidents`,
    { method: "DELETE" },
  );
}

// ── Document curation: clasificación y segmentos ─────────────────────

export interface ClassificationBlockUpdate {
  /** Índice en `metadatos.glaser_blocks`, tal cual lo ve la UI. */
  index: number;
  /** `null` = borrar la categoría del bloque (el texto sigue visible). */
  class: string | null;
}

export interface ClassificationPatchResult {
  status: string;
  blocks: GlaserBlock[];
  /** Cuántos bloques cambiaron realmente. */
  changed: number;
  /** Cuántos segmentos cambiaron de etiqueta al re-derivarla. */
  segments_updated: number;
  texto_clasificado: string;
  baseline_tags_count: number;
}

export async function patchDocumentClassification(
  documentId: string,
  blocks: ClassificationBlockUpdate[],
) {
  return request<ClassificationPatchResult>(
    `/documents/${documentId}/classification`,
    { method: "PATCH", body: JSON.stringify({ blocks }) },
  );
}

export interface DeleteSegmentResult {
  status: string;
  /** `merged` = el texto sobrevivió en el segmento siguiente. */
  action: "merged" | "deleted";
  removed_id: string;
  survivor_id: string | null;
  /** Incidentes que se quedaron sin ninguna cita y se borraron. */
  incidents_deleted: number;
  incidents_updated: number;
  segments: Segment[];
}

export async function deleteDocumentSegment(
  documentId: string,
  segmentId: string,
) {
  return request<DeleteSegmentResult>(
    `/documents/${documentId}/segments/${segmentId}`,
    { method: "DELETE" },
  );
}

export async function listDocumentIncidents(
  documentId: string,
): Promise<IncidentsPayload> {
  return request<IncidentsPayload>(`/documents/${documentId}/incidents`);
}

// ── Incident curation ───────────────────────────────────────────────

export interface IncidentQuotePayload {
  segmento_id: string;
  posicion: number;
  texto: string;
  /** Categoría efectiva de la cita (override propio o la del segmento). */
  categoria: string | null;
  /** De dónde sale `categoria`: del segmento o de una anotación de la cita. */
  categoria_origen: "segment" | "override";
  is_manual: boolean;
  /** Cita primaria denormalizada (`extracted_incidents.segmento_id`). */
  primario: boolean;
}

export interface IncidentPayload {
  id: string;
  segmento_id: string | null;
  jot_text: string | null;
  keep_moving: boolean;
  tipo_dato_glaser: string | null;
  origen: "ia" | "manual" | string;
  preguntas_glaser_json: Record<string, unknown>;
  segments: IncidentQuotePayload[];
  categorias: Record<string, number>;
  mixto: boolean;
}

export interface IncidentsPayload {
  incidents: IncidentPayload[];
  prime_mover: string | null;
  prime_mover_confidence: string | null;
}

export interface UnassignedSegmentPayload {
  id: string;
  posicion: number;
  tipo_dato_glaser: string | null;
  texto: string;
  first_10: string | null;
  start_char: number | null;
  end_char: number | null;
}

export interface UnassignedPayload {
  document_id: string;
  segments: UnassignedSegmentPayload[];
  counts: {
    total: number;
    unassigned: number;
    baseline: number;
    non_baseline: number;
  };
}

/** Toda mutación de curación devuelve el mismo payload que el GET. */
export type IncidentMutationResult = IncidentsPayload & { status: string };

export interface IncidentSegmentRef {
  segmento_id: string;
  tipo_dato_glaser?: string | null;
}

export async function listUnassignedSegments(
  documentId: string,
): Promise<UnassignedPayload> {
  return request<UnassignedPayload>(
    `/documents/${documentId}/unassigned-segments`,
  );
}

export async function createIncident(
  documentId: string,
  body: {
    segmentos: IncidentSegmentRef[];
    jot_text?: string | null;
    keep_moving?: boolean;
  },
): Promise<IncidentMutationResult & { incident_id: string }> {
  return request(`/documents/${documentId}/incidents`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function attachIncidentSegments(
  incidentId: string,
  body: { segmentos: IncidentSegmentRef[]; mode?: "move" | "add" },
): Promise<
  IncidentMutationResult & { added: string[]; already_assigned: string[] }
> {
  return request(`/incidents/${incidentId}/segments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function detachIncidentSegment(
  incidentId: string,
  segmentId: string,
): Promise<IncidentMutationResult & { segment_now_unassigned: boolean }> {
  return request(`/incidents/${incidentId}/segments/${segmentId}`, {
    method: "DELETE",
  });
}

export async function patchIncidentSegment(
  incidentId: string,
  segmentId: string,
  body: { tipo_dato_glaser: string | null },
): Promise<IncidentMutationResult> {
  return request(`/incidents/${incidentId}/segments/${segmentId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function patchIncident(
  incidentId: string,
  body: { jot_text?: string; keep_moving?: boolean },
): Promise<IncidentMutationResult> {
  return request(`/incidents/${incidentId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteIncident(
  incidentId: string,
): Promise<IncidentMutationResult & { freed_segment_ids: string[] }> {
  return request(`/incidents/${incidentId}`, { method: "DELETE" });
}

export async function resetDocsToCrudo(projectId: string) {
  return request<{ status: string; message: string }>(
    `/documents/project/${projectId}/reset-to-crudo`,
    { method: "POST" },
  );
}

export async function restoreDocumentOriginal(documentId: string) {
  return request<{ status: string; message: string }>(
    `/documents/${documentId}/restore-original`,
    { method: "POST" },
  );
}

export async function getTaskStatus(taskId: string) {
  return request<{ task_id: string; status: string; result: any }>(
    `/documents/tasks/${taskId}`,
  );
}

export async function saveTaskSegments(documentId: string, taskId: string) {
  return request<{ num_segmentos: number }>(
    `/documents/${documentId}/segments-from-task?task_id=${taskId}`,
    { method: "POST" },
  );
}

export async function punctuateDocument(documentId: string) {
  return request<{
    status: string;
    task_id?: string;
    punctuation_fix?: boolean;
    message?: string;
    changes_made?: boolean;
  }>(`/documents/${documentId}/punctuate`, { method: "POST" });
}

export async function processDocument(documentId: string, steps: string[]) {
  return request<{
    document_id: string;
    steps: Record<
      string,
      { task_id?: string; status: string; reason?: string }
    >;
  }>(`/documents/${documentId}/process`, {
    method: "POST",
    body: JSON.stringify({ steps }),
  });
}

export async function deleteDocument(documentId: string) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function getPipelineStatus(projectId: string) {
  return request<PipelineStatus>(`/projects/${projectId}/pipeline/status`);
}

export async function getPipelineLog(projectId: string) {
  return request<PipelineLog>(`/projects/${projectId}/pipeline/log`);
}

export async function getAgentMemos(projectId: string) {
  return request<{ memos: any[]; total: number; families: any[] }>(
    `/projects/${projectId}/agent-memos`,
  );
}

export interface AgentMemosDeletion {
  deleted: number;
  by_table: Record<string, number>;
  family: string;
}

/** Bulk-deletes the agent memos of a project (optionally one family only). */
export async function deleteAgentMemos(projectId: string, family?: string) {
  const query = family ? `?family=${encodeURIComponent(family)}` : "";
  return request<AgentMemosDeletion>(
    `/projects/${projectId}/agent-memos${query}`,
    { method: "DELETE" },
  );
}

/** Deletes a single agent memo (`pc-*`, `dp-*`, `cat-*`). 404 if missing. */
export async function deleteAgentOutput(id: string) {
  return request<{ deleted: number }>(`/agent-outputs/${id}`, {
    method: "DELETE",
  });
}

export interface AgentDispatchResponse {
  status: string;
  agent_id: string;
  task_id: string;
  task_name: string;
}

export async function runPipelineStage(
  projectId: string,
  stage: string,
): Promise<{
  stage: string;
  project_id: string;
  status: string;
  task_ids: string[];
  note?: string;
}> {
  return request<{
    stage: string;
    project_id: string;
    status: string;
    task_ids: string[];
    note?: string;
  }>(`/projects/${projectId}/pipeline/run-stage/${stage}`, { method: "POST" });
}

// ── Playground Types ──────────────────────────────────────────────────

export interface TheoreticalCode {
  id: string;
  name: string;
  family: string;
  description: string;
  glaserian: boolean;
  user_defined: boolean;
  evaluation_logic: Record<string, any>;
  compatible_with: string[];
  layer: string;
  visualization_hint: string;
}

export interface BlobData {
  id: string;
  name: string;
  definition: string;
  version: number;
  relevance: number;
  saturation: string;
  is_core: boolean;
}

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

export interface GhostData {
  id: string;
  content: string;
  type: string;
}

export interface EcosystemState {
  blobs: BlobData[];
  tendrils: TendrilData[];
  layout: EcosystemLayout | null;
}

export interface EcosystemLayout {
  blob_positions: Record<string, { x: number; y: number }>;
  ghost_positions: Record<string, { x: number; y: number }>;
  fog_zones: Record<string, any>;
  physics_params: Record<string, number>;
}

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

export interface RenameSuggestion {
  name: string;
  level: "conservative" | "moderate" | "transformative";
  rationale: string;
  what_it_gains: string;
  in_vivo_inspiration?: string;
}

export interface RenameSuggestions {
  needs_rename: boolean;
  suggestions: RenameSuggestion[];
  status?: string;
  task_id?: string;
}

export interface DefinitionVersion {
  version: number;
  name: string;
  definition: string;
  trigger: string;
  detail: string | null;
  created_at: string;
}

export interface Recommendation {
  category: string;
  title: string;
  description: string;
  action_type:
    "connect" | "absorb_ghost" | "rename" | "sample" | "resolve_tension";
  category_ids: string[];
  suggested_code: string;
  impact_score: number;
}

export interface ModelSummary {
  relationships: TendrilData[];
  orphan_categories: { id: string; name: string }[];
  layers_coverage: { covered: string[]; missing: string[] };
}

// ── Theoretical Codes ─────────────────────────────────────────────────

export async function getTheoreticalCodes(projectId: string) {
  return request<TheoreticalCode[]>(`/projects/${projectId}/theoretical/codes`);
}

export async function createTheoreticalCode(
  projectId: string,
  body: Record<string, any>,
) {
  return request<void>(`/projects/${projectId}/theoretical/codes`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Ecosystem ─────────────────────────────────────────────────────────

export async function getEcosystem(projectId: string) {
  return request<EcosystemState>(
    `/projects/${projectId}/elaboration/ecosystem`,
  );
}

export async function saveEcosystemLayout(
  projectId: string,
  layout: Partial<EcosystemLayout>,
) {
  return request<void>(`/projects/${projectId}/elaboration/ecosystem/layout`, {
    method: "PUT",
    body: JSON.stringify(layout),
  });
}

// ── Relationships ─────────────────────────────────────────────────────

export async function elaborateRelationship(
  projectId: string,
  body: {
    category_ids: string[];
    theoretical_code_id: string;
    researcher_question: string;
  },
) {
  return request<{ status: string; task_id: string }>(
    `/projects/${projectId}/elaboration/relationships`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function getRelationships(projectId: string) {
  return request<Relationship[]>(
    `/projects/${projectId}/elaboration/relationships`,
  );
}

export async function getRelationship(projectId: string, relId: string) {
  return request<Relationship>(
    `/projects/${projectId}/elaboration/relationships/${relId}`,
  );
}

export async function resolveDivergence(
  projectId: string,
  relId: string,
  body: { divergence_resolution: string },
) {
  return request<void>(
    `/projects/${projectId}/elaboration/relationships/${relId}/diverge`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

// ── Ghosts ────────────────────────────────────────────────────────────

export async function getGhosts(projectId: string) {
  return request<GhostData[]>(`/projects/${projectId}/elaboration/ghosts`);
}

export async function absorbGhost(
  projectId: string,
  memoId: string,
  targetCategoryId: string,
) {
  return request<void>(
    `/projects/${projectId}/elaboration/ghosts/${memoId}/absorb`,
    {
      method: "POST",
      body: JSON.stringify({ target_category_id: targetCategoryId }),
    },
  );
}

// ── Renames ───────────────────────────────────────────────────────────

export async function getRenameSuggestions(
  projectId: string,
  categoryId: string,
) {
  return request<RenameSuggestions>(
    `/projects/${projectId}/elaboration/rename-suggestions/${categoryId}`,
  );
}

export async function applyRename(
  projectId: string,
  body: { category_id: string; new_name: string; rationale: string },
) {
  return request<void>(`/projects/${projectId}/elaboration/rename`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getDefinitionHistory(
  projectId: string,
  categoryId: string,
) {
  return request<DefinitionVersion[]>(
    `/projects/${projectId}/elaboration/categories/${categoryId}/definition-history`,
  );
}

// ── Recommendations ───────────────────────────────────────────────────

export async function getRecommendations(projectId: string) {
  return request<Recommendation[]>(
    `/projects/${projectId}/elaboration/recommendations`,
  );
}

export async function getTheoreticalModel(projectId: string) {
  return request<ModelSummary>(`/projects/${projectId}/elaboration/model`);
}

// ── Saturation (Gap Report) ───────────────────────────────────────────

export async function getSaturationGaps(projectId: string) {
  return request<{
    project_id: string;
    generated_at: string;
    critical: { severity: string; description: string; action: string }[];
    warnings: {
      severity: string;
      source: string;
      description: string;
      action: string;
    }[];
    saturated: string[];
  }>(`/projects/${projectId}/analysis/saturation-gaps`);
}

export async function refreshSaturationGaps(projectId: string) {
  return request<void>(
    `/projects/${projectId}/analysis/saturation-gaps/refresh`,
    {
      method: "POST",
    },
  );
}

// ── Admin: Pipeline Control ──────────────────────────────────────────

export interface PipelineTaskInfo {
  task_id: string;
  document_id?: string;
  task_name: string;
  status: string;
  doc_estado_before?: string;
}

export async function stopWorker(workerName: "fast" | "heavy" | "nlp") {
  return request<{ status: string; tasks_revoked: number }>(
    `/admin/workers/${workerName}/stop`,
    { method: "POST" },
  );
}

export async function killAllWorkers() {
  return request<{
    status: string;
    workers_shutdown: boolean;
    tasks_revoked: number;
  }>(`/admin/workers/kill-all`, { method: "POST" });
}

export async function stopProjectPipeline(projectId: string) {
  return request<{
    status: string;
    active_run?: null;
    tasks_revoked?: number;
    run_id?: string;
    tasks_cancelled?: number;
    details?: {
      task_id: string;
      status: string;
      doc_id: string | null;
    }[];
  }>(`/admin/projects/${projectId}/stop`, { method: "POST" });
}

/** Marca como cerrados los runs que quedaron en 'running' sin nada en vuelo.
 *  Solo arregla la columna de estado: no revoca tareas ni toca documentos. */
export async function closeIdlePipelineRuns(projectId: string) {
  return request<{ closed: number }>(
    `/projects/${projectId}/pipeline/close-idle-runs`,
    { method: "POST" },
  );
}

export async function cancelTask(taskId: string) {
  return request<{
    status: string;
    task_id: string;
    cleanup?: "unknown";
    document_rolled_back?: string | null;
    previous_state?: string | null;
  }>(`/admin/tasks/${taskId}/cancel`, { method: "POST" });
}

export async function restartTask(taskId: string) {
  return request<{ status: string; old_task_id: string; new_task_id: string }>(
    `/admin/tasks/${taskId}/restart`,
    { method: "POST" },
  );
}

export async function resumeTask(taskId: string) {
  return request<{
    status: string;
    old_task_id: string;
    new_task_id: string;
    resume_from_step?: string;
    note?: string;
  }>(`/admin/tasks/${taskId}/resume`, { method: "POST" });
}

export async function restartFailedTasks(projectId: string) {
  return request<{
    status: string;
    count: number;
    tasks: { old_task_id: string; new_task_id: string }[];
  }>(`/admin/projects/${projectId}/pipeline/restart-failed`, {
    method: "POST",
  });
}

// ── HITL Types ──────────────────────────────────────────────────────

export interface HitlPendingItem {
  id: string;
  gate_name: string;
  proposal_summary: string;
  critic_verdict: string;
  created_at: string;
}

export interface HitlDecisionResponse {
  id: string;
  project_id: string;
  gate_name: string;
  status: string;
  researcher_decision: string | null;
  researcher_note: string | null;
  decided_at: string | null;
}

// ── HITL API ────────────────────────────────────────────────────────

export async function getPendingHitl(
  projectId: string,
): Promise<HitlPendingItem[]> {
  return request<HitlPendingItem[]>(`/projects/${projectId}/hitl/pending`);
}

export async function decideHitl(
  projectId: string,
  gateName: string,
  decision: "accept" | "modify" | "reject",
  note: string,
  feedback?: string,
): Promise<HitlDecisionResponse> {
  return request<HitlDecisionResponse>(
    `/projects/${projectId}/hitl/${gateName}/decide`,
    {
      method: "POST",
      body: JSON.stringify({ decision, note, feedback }),
    },
  );
}

export async function getHitlDetail(
  projectId: string,
  gateName: string,
): Promise<{
  id: string;
  gate_name: string;
  proposal: Record<string, unknown>;
  critic_verdict: Record<string, unknown>;
  status: string;
  created_at: string;
}> {
  return request(`/projects/${projectId}/hitl/${gateName}/detail`);
}

// ── HITL: CRUD de decisiones ─────────────────────────────────────────
// Sobre hitl_decisions. Convive con los gates (pending/detail/decide):
// aquí el investigador puede crear, leer, editar y borrar decisiones
// sueltas sin pasar por el flujo de propuesta → crítico → decisión.

export type HitlStatus = "pending" | "accepted" | "modified" | "rejected";

export interface HitlDecisionFull {
  id: string;
  project_id: string;
  gate_name: string;
  status: HitlStatus;
  proposal: Record<string, unknown>;
  critic_verdict: Record<string, unknown>;
  researcher_decision: string | null;
  researcher_note: string | null;
  researcher_feedback: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface HitlStatusCounts {
  pending: number;
  accepted: number;
  modified: number;
  rejected: number;
}

export interface HitlDecisionList {
  items: HitlDecisionFull[];
  total: number;
  counts: HitlStatusCounts;
}

export interface HitlDecisionCreateBody {
  gate_name: string;
  note?: string;
  proposal?: Record<string, unknown>;
  critic_verdict?: Record<string, unknown>;
  status?: HitlStatus;
}

export interface HitlDecisionUpdateBody {
  note?: string;
  feedback?: string | null;
  status?: HitlStatus;
  gate_name?: string;
}

export interface HitlDecisionBulkDeleteBody {
  ids?: string[];
  status?: HitlStatus;
  gate_name?: string;
}

export async function listHitlDecisions(
  projectId: string,
  opts: {
    status?: HitlStatus;
    gateName?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<HitlDecisionList> {
  const qs = new URLSearchParams();
  if (opts.status) qs.set("status", opts.status);
  if (opts.gateName) qs.set("gate_name", opts.gateName);
  if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
  if (opts.offset !== undefined) qs.set("offset", String(opts.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<HitlDecisionList>(
    `/projects/${projectId}/hitl/decisions${suffix}`,
  );
}

export async function getHitlDecision(
  projectId: string,
  decisionId: string,
): Promise<HitlDecisionFull> {
  return request<HitlDecisionFull>(
    `/projects/${projectId}/hitl/decisions/${decisionId}`,
  );
}

export async function createHitlDecision(
  projectId: string,
  body: HitlDecisionCreateBody,
): Promise<HitlDecisionFull> {
  return request<HitlDecisionFull>(`/projects/${projectId}/hitl/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateHitlDecision(
  projectId: string,
  decisionId: string,
  body: HitlDecisionUpdateBody,
): Promise<HitlDecisionFull> {
  return request<HitlDecisionFull>(
    `/projects/${projectId}/hitl/decisions/${decisionId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export async function deleteHitlDecision(
  projectId: string,
  decisionId: string,
): Promise<{ status: string; deleted: number }> {
  return request<{ status: string; deleted: number }>(
    `/projects/${projectId}/hitl/decisions/${decisionId}`,
    { method: "DELETE" },
  );
}

export async function bulkDeleteHitlDecisions(
  projectId: string,
  body: HitlDecisionBulkDeleteBody,
): Promise<{ deleted: number }> {
  return request<{ deleted: number }>(`/projects/${projectId}/hitl/decisions`, {
    method: "DELETE",
    body: JSON.stringify(body),
  });
}

// ── HITL: gate unificado de codificación abierta ─────────────────────
// Concern principal + población + categorías centrales. Es el único gate
// HITL que no depende de que un worker haya insertado una fila pendiente:
// se puede abrir en cualquier momento y se guarda en proyectos
// (chosen_concern / chosen_population) + hitl_decisions.

export interface ConcernCandidate {
  label: string;
  supporting_codes: string[];
  rationale: string;
}

export interface PopulationProposal {
  description: string;
  source_batch: number;
}

export interface UnifiedCategory {
  id: string;
  label: string;
  definition: string;
  is_core_candidate: boolean;
}

export interface UnifiedHypothesis {
  id: string;
  text: string;
  concern_relevance: string;
  is_core_candidate: boolean;
}

export interface OpenCodingHitlStatus {
  docs_processed: number;
  total_docs: number;
  batch_number: number;
  concern_candidates: ConcernCandidate[];
  population_proposals: PopulationProposal[];
  unified_categories: UnifiedCategory[];
  unified_hypotheses: UnifiedHypothesis[];
  chosen_concern: string | null;
  chosen_population: string | null;
  can_proceed: boolean;
}

export interface OpenCodingHitlDecision {
  chosen_concern: string;
  chosen_population: string;
  core_category_ids: string[];
  confirmed: boolean;
  researcher_note: string;
}

export interface OpenCodingHitlDecisionResponse {
  status: string;
  chosen_concern: string;
  chosen_population: string;
  core_categories_set: number;
  confirmed: boolean;
}

export async function getOpenCodingHitlStatus(
  projectId: string,
): Promise<OpenCodingHitlStatus> {
  return request<OpenCodingHitlStatus>(
    `/projects/${projectId}/hitl/open-coding/status`,
  );
}

export async function decideOpenCodingHitl(
  projectId: string,
  body: OpenCodingHitlDecision,
): Promise<OpenCodingHitlDecisionResponse> {
  return request<OpenCodingHitlDecisionResponse>(
    `/projects/${projectId}/hitl/open-coding/decide`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// ── Hypotheses CRUD + duplicates ─────────────────────────────────────

export interface HypothesisItem {
  id: string;
  text: string;
  level: string;
  confidence: number;
  status: string;
  code_id: string | null;
  parent_hypothesis_id: string | null;
  concern_labels: string[];
  batch_number: number | null;
}

export interface HypothesisListResponse {
  items: HypothesisItem[];
  total: number;
  by_status: Record<string, number>;
}

export interface CreateHypothesisBody {
  project_id: string;
  text: string;
  level?: string;
  confidence?: number;
  status?: string;
  code_id?: string | null;
  concern_labels?: string[];
}

export interface UpdateHypothesisBody {
  text?: string;
  level?: string;
  confidence?: number;
  status?: string;
  concern_labels?: string[];
}

export interface HypothesisDuplicateItem {
  id: string;
  text: string;
  level: string;
  status: string;
  confidence: number;
  similarity: number;
  is_suggested_keep: boolean;
}

export interface HypothesisDuplicateCluster {
  cluster_id: number;
  size: number;
  items: HypothesisDuplicateItem[];
}

export interface HypothesisDuplicatesResponse {
  threshold: number;
  total_hypotheses: number;
  clusters: HypothesisDuplicateCluster[];
  redundant_count: number;
}

export async function getHypothesesByProject(
  projectId: string,
  params: { status?: string; level?: string } = {},
): Promise<HypothesisListResponse> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.level) qs.set("level", params.level);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<HypothesisListResponse>(
    `/hypotheses/by-project/${projectId}${suffix}`,
  );
}

export async function createHypothesis(
  body: CreateHypothesisBody,
): Promise<HypothesisItem> {
  return request<HypothesisItem>("/hypotheses", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateHypothesis(
  hypothesisId: string,
  body: UpdateHypothesisBody,
): Promise<HypothesisItem> {
  return request<HypothesisItem>(`/hypotheses/${hypothesisId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteHypothesis(
  hypothesisId: string,
): Promise<{ deleted: boolean; id: string }> {
  return request<{ deleted: boolean; id: string }>(
    `/hypotheses/${hypothesisId}`,
    { method: "DELETE" },
  );
}

export async function bulkDeleteHypotheses(
  ids: string[],
): Promise<{ deleted: number }> {
  return request<{ deleted: number }>("/hypotheses/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}

export async function getHypothesisDuplicates(
  projectId: string,
  threshold = 0.8,
): Promise<HypothesisDuplicatesResponse> {
  return request<HypothesisDuplicatesResponse>(
    `/hypotheses/duplicates/${projectId}?threshold=${threshold}`,
  );
}

// ── User Memos ────────────────────────────────────────────────────────

export interface MemoTypeItem {
  key: string;
  label: string;
  icon: string;
  color: string;
  description: string;
  requires_agent?: string;
  agent_status?: string;
  stage_available?: boolean;
}

export interface AvailableMemoTypes {
  stage: string;
  pipeline_running: boolean;
  can_add_memo: boolean;
  available_types: MemoTypeItem[];
  all_types: MemoTypeItem[];
}

export async function getAvailableMemoTypes(
  projectId: string,
  lang?: string,
): Promise<AvailableMemoTypes> {
  const query = lang ? `?lang=${encodeURIComponent(lang)}` : "";
  return request(`/projects/${projectId}/available-memo-types${query}`);
}

export async function getEntityTypeColors(lang?: string): Promise<{
  types: Array<{
    key: string;
    label: string;
    icon: string;
    color: string;
    description: string;
    requires_agent?: string;
    stage_available?: boolean;
  }>;
}> {
  const query = lang ? `?lang=${encodeURIComponent(lang)}` : "";
  return request(`/entity-type-colors${query}`);
}

export async function createMemo(
  projectId: string,
  body: {
    tipo: string;
    contenido: string;
    es_confidencial: boolean;
    structured_fields?: Record<string, unknown>;
    /** Nombre de la categoría a crear (solo tipo CATEGORIA). */
    nombre?: string;
  },
): Promise<{ id: string; tipo: string; stage: string; user_created: boolean }> {
  return request(`/projects/${projectId}/memos`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getStaleUserEntities(
  projectId: string,
  currentStage: string,
): Promise<{
  count: number;
  affected_stages: string[];
  earliest_stage: string | null;
}> {
  return request(
    `/projects/${projectId}/stale-user-entities?current_stage=${currentStage}`,
  );
}

export async function getPipelineDecisions(projectId: string): Promise<{
  project_id: string;
  decisions: Array<{
    gate: string;
    proposal: Record<string, unknown>;
    critic_verdict: Record<string, unknown>;
    status: string;
    decision: string;
    note: string;
    decided_at: string | null;
  }>;
  saturation: Record<
    string,
    { no_expansion_count: number; saturated: boolean }
  >;
}> {
  return request(`/projects/${projectId}/pipeline/decisions`);
}

// ── Chain Runs ───────────────────────────────────────────────────────

export interface AgentRunItem {
  agent_id: string;
  attempt_number: number;
  output: Record<string, any>;
  tokens_used: number;
  tool_calls_count: number;
  retry_count: number;
  orchestrator_action: "proceed" | "force_proceed" | "skip";
  started_at: string | null;
  finished_at: string | null;
}

export interface ChainRunItem {
  id: string;
  project_id: string;
  chain_id: string;
  parent_chain_run_id: string | null;
  status: "running" | "completed" | "aborted" | "paused_hitl";
  agent_runs: AgentRunItem[] | null;
  total_tokens: number;
  total_retries: number;
  started_at: string | null;
  finished_at: string | null;
  created_by: string;
  created_at: string | null;
}

export async function getChainRuns(
  projectId: string,
  chainId?: string,
  limit?: number,
  includeAgentRuns?: boolean,
): Promise<ChainRunItem[]> {
  const params = new URLSearchParams();
  if (chainId) params.set("chain_id", chainId);
  if (limit) params.set("limit", String(limit));
  params.set("include_agent_runs", String(includeAgentRuns ?? true));
  return request(`/projects/${projectId}/chain-runs?${params}`);
}

// ── Agent Log Types ──

export interface AgentLogEntry {
  ts: number;
  type: "prompt_sent" | "prompt_response";
  agent_id: string;
  prompt?: string;
  schema?: string;
  response?: string;
  tokens?: number;
}

// ── Setup ───────────────────────────────────────────────────────────

export async function getSetupStatus() {
  return request<{
    language: string;
    spacy_ready: boolean;
    stanza_ready: boolean;
  }>("/setup/status");
}

export async function initializeSetup(language: string) {
  return request<{ status: string }>("/setup/initialize", {
    method: "POST",
    body: JSON.stringify({ language }),
  });
}

export async function getSetupProgress() {
  return request<{ status: string; progress: number; message: string }>(
    "/setup/progress",
  );
}

export async function getAgentLogs(
  projectId: string,
): Promise<AgentLogEntry[]> {
  const token = localStorage.getItem("access_token") || "";
  const res = await fetch(`/api/v1/projects/${projectId}/agent-logs`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  return res.json();
}
