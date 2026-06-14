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
  texto_extraido?: string;
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

export async function deleteDocument(documentId: string) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}
