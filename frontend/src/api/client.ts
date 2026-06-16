const API_BASE = "/api/v1";

function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export function setToken(token: string) {
  localStorage.setItem("access_token", token);
}

export function clearToken() {
  localStorage.removeItem("access_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
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
  };
  segments_count: number;
  codes_count: number;
  next_action: "extract_text" | "segment" | "run_agents" | "done" | "error";
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
    need_agents: number;
    done: number;
    failed: number;
    errors: PipelineLogError[];
    categories: number;
    playground_ready: boolean;
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
}) {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getProject(id: string) {
  return request<Project>(`/projects/${id}`);
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
    punctuation_fix: boolean;
    message?: string;
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
    | "connect"
    | "absorb_ghost"
    | "rename"
    | "sample"
    | "resolve_tension";
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
    run_id: string;
    tasks_cancelled: number;
    details: {
      task_id: string;
      doc_rolled_back?: string;
      previous_state?: string;
    }[];
  }>(`/admin/projects/${projectId}/stop`, { method: "POST" });
}

export async function cancelTask(taskId: string) {
  return request<{
    status: string;
    task_id: string;
    document_rolled_back?: string;
    previous_state?: string;
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
