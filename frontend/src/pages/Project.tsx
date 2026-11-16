import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useI18n } from "../i18n";
import {
  getProject,
  listDocuments,
  listCategories,
  listSegments,
  uploadDocument,
  punctuateDocument,
  getTaskStatus,
  deleteDocument,
  deleteAllDocuments,
  deleteDocumentSegments,
  deleteDocumentIncidents,
  restoreDocumentOriginal,
  getPipelineLog,
  getAgentMemos,
  deleteAgentOutput,
  deleteAgentMemos,
  getPendingHitl,
  decideHitl,
  getOpenCodingHitlStatus,
  getHypothesisDuplicates,
  ping,
  clearToken,
  stopProjectPipeline,
  closeIdlePipelineRuns,
  restartFailedTasks,
  updateProject,
  updatePopulationAssumption,
  generatePopulationGeneralization,
  getStaleUserEntities,
  Project,
  Document,
  Category,
  Segment,
  GlaserBlock,
  PipelineLog,
  DocPipelineLog,
  HitlPendingItem,
  OpenCodingHitlStatus,
} from "../api/client";
import {
  MemoHistory,
  type MemoEntry,
  ConfirmDeleteButton,
} from "../components/MemoHistory";
import { Toast } from "../components/Toast";
import HITLModal from "../components/HITLModal";
import OpenCodingHITLModal from "../components/OpenCodingHITLModal";
import HitlDecisionsPanel from "../components/HitlDecisionsPanel";
import AddMemoModal from "../components/AddMemoModal";
import ProjectConfigPanel from "../components/ProjectConfigPanel";
import PipelineAgents from "../components/PipelineAgents";
import AgentModal from "../components/AgentModal";
import IncidentsPanel from "../components/incidents/IncidentsPanel";
import ClassifiedBlockEditor from "../components/curation/ClassifiedBlockEditor";
import SegmentsMergeList from "../components/curation/SegmentsMergeList";
import { getAgentLogs, type AgentLogEntry } from "../api/client";
import { PIPELINE_STAGES, FAMILY_COLORS } from "../config/pipelineChains";
import { STEP_TIMEOUT_MS, STEP_TIMEOUT_MINUTES } from "../config/timeouts";

// ── Styles ────────────────────────────────────────────────────────

const btnSmall: React.CSSProperties = {
  padding: "5px 12px",
  borderRadius: 6,
  border: "1px solid #21262D",
  background: "#1C2333",
  color: "#E6EDF3",
  fontSize: 12,
  cursor: "pointer",
};

type StageStatus = "pending" | "running" | "done" | "error";

/** Per-interview pipeline steps, in classify-first order.
 *
 *  `original → preprocessed → classified → segmented → incidents`: the Glaser
 *  classifier tags the TEXT first, segments are created afterwards and inherit
 *  their tag, and only then does the extractor consume `baseline_data`. */
const DOC_STEPS = [
  "original",
  "preprocessed",
  "classified",
  "segmented",
  "incidents",
] as const;
type DocStepKey = (typeof DOC_STEPS)[number];

/** Estados que implican que el texto ya pasó por el preprocesado. */
const PREPROCESSED_ESTADOS = [
  "preprocesado",
  "clasificando",
  "clasificado",
  "segmentando",
  "segmentado",
  "procesando",
  "extrayendo",
  "incidentes_extraidos",
  "procesado",
  "codificando",
  "codificado",
  "listo",
];

/** Estados en los que la extracción de incidentes ya corrió (o terminó). */
const INCIDENT_TERMINAL_ESTADOS = [
  "incidentes_extraidos",
  "procesado",
  "codificado",
  "listo",
];

const STEP_LABEL_KEYS: Record<DocStepKey, string> = {
  original: "project.original",
  preprocessed: "project.stepPreprocessed",
  classified: "project.stepClassified",
  segmented: "project.stepSegmented",
  incidents: "project.stepIncidents",
};

const STEP_ICONS: Record<DocStepKey, string> = {
  original: "\uD83D\uDCC4",
  preprocessed: "\uD83D\uDCDD",
  classified: "\uD83C\uDFF7\uFE0F",
  segmented: "\u2702\uFE0F",
  incidents: "\uD83D\uDD0D",
};

const STEP_COLORS: Record<DocStepKey, string> = {
  original: "#8B949E",
  preprocessed: "#A371F7",
  classified: "#3FB950",
  segmented: "#58A6FF",
  incidents: "#D29922",
};

/** Inconsistency codes the pipeline log may report per document. */
const INCONSISTENCY_LABEL_KEYS: Record<string, string> = {
  missing_classified: "project.stepMissingClassified",
  missing_segmented: "project.stepMissingSegmented",
  segmented_without_segments: "project.stepSegmentedWithoutSegments",
  segments_unclassified: "project.stepSegmentsUnclassified",
};

/** Single-line, length-capped preview for compact segment lists. */
function shorten(text: string, max = 160): string {
  const clean = String(text ?? "")
    .replace(/\s+/g, " ")
    .trim();
  return clean.length > max ? clean.slice(0, max) + "…" : clean;
}

/** Per-document pipeline log as extended by the classify-first backend. */
type ExtendedDocLog = DocPipelineLog & {
  has_classification?: boolean;
  classified_count?: number;
  incidents_count?: number;
  inconsistencies?: string[];
  steps: DocPipelineLog["steps"] & {
    classified?: boolean;
    incidents?: boolean;
  };
};

/** Estados transitorios mientras un worker procesa el documento. */
const IN_FLIGHT_DOC_STATES = [
  "preprocesando",
  "segmentando",
  "clasificando",
  "procesando",
  "extrayendo",
  "codificando",
  "resumiendo",
];

// ── Component ─────────────────────────────────────────────────────

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [project, setProject] = useState<Project | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [segments, setSegments] = useState<Record<string, Segment[]>>({});
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
  const [punctStatus, setPunctStatus] = useState<Record<string, string>>({});
  const [punctRunning, setPunctRunning] = useState<string | null>(null);
  const punctTaskRef = useRef<string | null>(null);
  const runningOp = useRef<{
    docId: string;
    op: "punctuate" | "classify" | "segment" | "extract";
  } | null>(null);

  // ── Modular cancel: each operation reverts ONLY its own step ──
  // punctuate: restore → crudo
  // segment:   delete segs → preprocesado
  // classify:  clear classified text → segmentado
  // extract:   nothing to revert (the backend cancel already restores estado,
  //            and deleting segments here would destroy classification work)
  const OP_ROLLBACK: Record<
    string,
    Array<"restore" | "deleteSegs" | "clearClassified">
  > = {
    punctuate: ["restore"],
    classify: ["clearClassified"],
    segment: ["deleteSegs"],
    extract: [],
  };

  // ── Unified agent state definitions ──
  // Each per-doc agent: input estado (what it consumes), output estado (what it produces).
  // canRun = docs exist in input state. done = no docs in input state AND some docs at output+.
  // Classify-first: punctuator → Glaser classifier (tags the TEXT) → segmenter
  // (segments inherit the tag) → incident extractor (consumes `baseline_data`).
  const PER_DOC_AGENTS = {
    util_punctuator: { input: "crudo", output: "preprocesado" },
    fa_glaser_data_classifier: {
      input: "preprocesado",
      output: "clasificado",
    },
    segmentar_documento: { input: "clasificado", output: "segmentado" },
    fa_document_pattern_extractor: {
      input: "segmentado",
      output: "incidentes_extraidos",
    },
  } as const;

  /** Estados desde los que el extractor de incidentes puede arrancar.
   *
   * Espejo del guard 409 de `run_single_agent` (backend/app/api/v1/pipeline.py).
   * Con el orden classify-first el extractor consume segmentos ya etiquetados,
   * así que su estado natural de entrada es "segmentado". La UI además exige
   * `hasSegments(doc)`, de modo que un doc "clasificado" sin segmentos nunca
   * llega a la cola aunque el backend lo aceptara.
   */
  const EXTRACTOR_STATES: ReadonlyArray<string> = [
    "clasificado",
    "segmentado",
    "incidentes_extraidos",
    "procesado",
    "listo",
    "error",
  ];

  /** All estados that are at or beyond a given output estado */
  const BEYOND: Record<string, string[]> = {
    crudo: [
      "crudo",
      "preprocesado",
      "clasificado",
      "segmentado",
      "procesando",
      "incidentes_extraidos",
      "procesado",
      "codificando",
      "codificado",
      "listo",
    ],
    preprocesado: [
      "preprocesado",
      "clasificado",
      "segmentado",
      "procesando",
      "incidentes_extraidos",
      "procesado",
      "codificando",
      "codificado",
      "listo",
    ],
    clasificado: [
      "clasificado",
      "segmentado",
      "procesando",
      "incidentes_extraidos",
      "procesado",
      "codificando",
      "codificado",
      "listo",
    ],
    segmentado: [
      "segmentado",
      "procesando",
      "incidentes_extraidos",
      "procesado",
      "codificando",
      "codificado",
      "listo",
    ],
    incidentes_extraidos: [
      "incidentes_extraidos",
      "procesado",
      "codificando",
      "codificado",
      "listo",
    ],
    codificado: ["codificado", "listo"],
  };
  async function cancelRunningOp(docId: string) {
    const op = runningOp.current;
    if (!op || op.docId !== docId) return;
    const token = `Bearer ${localStorage.getItem("access_token")}`;
    runningOp.current = null;
    abortRef.current = true;
    const taskId = punctTaskRef.current;
    setPunctRunning(null);
    // Clear the per-doc marker too, otherwise the card stays stuck on
    // "En curso" until the next refresh.
    setRunningOps((prev) => {
      if (!prev[docId]) return prev;
      const n = { ...prev };
      delete n[docId];
      return n;
    });
    setPunctStatus((prev) => ({
      ...prev,
      [docId]: t("project.preprocessingCancelled"),
    }));
    punctTaskRef.current = null;
    if (taskId) {
      await fetch(`/api/v1/admin/tasks/${taskId}/cancel`, {
        method: "POST",
        headers: { Authorization: token },
      }).catch(() => {});
    }
    const rollbacks = OP_ROLLBACK[op.op] || [];
    for (const rb of rollbacks) {
      if (rb === "restore")
        await restoreDocumentOriginal(docId).catch(() => {});
      if (rb === "deleteSegs")
        await deleteDocumentSegments(docId).catch(() => {});
      if (rb === "clearClassified") {
        await fetch(`/api/v1/documents/${docId}/classify-glaser`, {
          method: "DELETE",
          headers: { Authorization: token },
        }).catch(() => {});
      }
    }
    refreshAll();
  }

  /** Unified task dispatch + poll + refresh. All per-doc handlers and the
   *  sidebar dispatchAgentLoop delegate to this. */
  async function runDocTask(
    docId: string,
    endpoint: string,
    signal: { current: boolean },
    maxWaitMs = STEP_TIMEOUT_MS,
  ): Promise<"success" | "failed" | "aborted" | "timeout"> {
    console.log("[runDocTask] POST", endpoint, "docId:", docId);
    const token = `Bearer ${localStorage.getItem("access_token")}`;
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: token,
      },
      body: JSON.stringify({ document_id: docId }),
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const body = await resp.json();
        if (body?.detail) {
          detail =
            typeof body.detail === "string"
              ? body.detail
              : JSON.stringify(body.detail);
        }
      } catch {
        /* non-JSON error body */
      }
      throw new Error(detail);
    }
    const res = await resp.json();

    const taskId = res.task_id;
    punctTaskRef.current = taskId;
    if (!taskId) {
      refreshAll();
      return "success";
    }

    const pollInterval = 2000;
    const maxPolls = Math.ceil(maxWaitMs / pollInterval);
    for (let i = 0; i < maxPolls && !signal.current; i++) {
      await new Promise((r) => setTimeout(r, pollInterval));
      try {
        const ts = await getTaskStatus(taskId);
        if (ts.status === "SUCCESS") {
          // Surface the real estado without requiring a manual reload.
          refreshAll();
          return "success";
        }
        if (ts.status === "FAILURE" || ts.status === "REVOKED") {
          // The worker may still have advanced state before failing/cancelling.
          refreshAll();
          return "failed";
        }
        // STARTED / RETRY / PENDING: keep polling.
      } catch {
        /* polling error, keep trying */
      }
    }
    // Even on timeout the task may have completed server-side; surface the
    // real estado instead of leaving the UI stale until a manual reload.
    refreshAll();
    return signal.current ? "aborted" : "timeout";
  }

  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState("");
  const [userName, setUserName] = useState("");
  const abortRef = useRef(false);
  const originalTexts = useRef<Record<string, string>>({});

  /** Floating confirmation bar — replaces blocked window.confirm() */
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null);
  const confirmResolve = useRef<((ok: boolean) => void) | null>(null);
  function safeConfirm(msg: string): Promise<boolean> {
    // Always use the floating bar: a blocked native confirm() resolves falsy
    // and would silently answer "no".
    return new Promise((resolve) => {
      confirmResolve.current = resolve;
      setConfirmMsg(msg);
    });
  }
  function resolveConfirm(ok: boolean) {
    setConfirmMsg(null);
    confirmResolve.current?.(ok);
    confirmResolve.current = null;
  }

  // ── Pipeline state ──
  const [pipelineLog, setPipelineLog] = useState<PipelineLog | null>(null);
  const [stageStatuses, setStageStatuses] = useState<
    Record<string, StageStatus>
  >({});
  const [stoppingWorkers, setStoppingWorkers] = useState(false);
  const [openCodingRunning, setOpenCodingRunning] = useState(false);

  // ── Global view switch REMOVED ──
  // The viewed step is now shared by every interview (see `globalStep`), so
  // there is no "original vs segmented" switch to keep in sync.

  // ── Execution log ──
  const [pipelineFailed, setPipelineFailed] = useState(false);
  const [memoFilter, setMemoFilter] = useState("all");
  const [agentMemos, setAgentMemos] = useState<any[]>([]);
  const [toastMsg, setToastMsg] = useState("");
  const [toastVisible, setToastVisible] = useState(false);
  const [toastType, setToastType] = useState<"info" | "error">("info");
  const [pipelineLiveLogs, setPipelineLiveLogs] = useState<
    Array<{ ts: number; msg: string }>
  >([]);
  const logPanelRef = useRef<HTMLDivElement>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const agentPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── HITL state ──
  const [hitlPending, setHitlPending] = useState<HitlPendingItem[]>([]);
  const [showHITLModal, setShowHITLModal] = useState(false);
  // Gate de codificación abierta (concern / población / categorías centrales)
  const [ocHitl, setOcHitl] = useState<OpenCodingHitlStatus | null>(null);
  const [ocHitlOpen, setOcHitlOpen] = useState(false);
  // Aviso de hipótesis duplicadas (se revisan/anulan en el gate HITL abierto)
  const [dupClusters, setDupClusters] = useState(0);
  const [dupRedundant, setDupRedundant] = useState(0);
  const [showAddMemo, setShowAddMemo] = useState(false);
  const [showConfigPanel, setShowConfigPanel] = useState(false);

  // ── Stale entities warning (FIX 4) ──
  const [staleWarning, setStaleWarning] = useState<{
    count: number;
    affected_stages: string[];
    earliest_stage: string | null;
  } | null>(null);

  // ── Agent monitoring ──
  const [sidebarViewMode, setSidebarViewMode] = useState<
    "stages" | "agents" | "logs" | "hitl"
  >("agents");
  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([]);
  /** Ephemeral: agent IDs currently executing (pulse animation).
   *  Set on play, cleared on finish/abort. NOT derived from docs. */
  const [runningAgentIds, setRunningAgentIds] = useState<Set<string>>(
    new Set(),
  );
  /** Derived from /pipeline/log (running_agents). Survives a reload, whereas
   *  runningAgentIds only reflects what this browser session dispatched. */
  const [serverRunningAgentIds, setServerRunningAgentIds] = useState<
    Set<string>
  >(new Set());
  const isAgentRunning = (agentId: string) =>
    runningAgentIds.has(agentId) || serverRunningAgentIds.has(agentId);
  /** Etapas cuyo orquestador de fase (A/B) está en vuelo en el servidor. */
  const runningPhases = new Set(pipelineLog?.summary?.running_phases ?? []);
  const phaseRunning = runningPhases.size > 0;
  /** Borrar entidades mientras corre el pipeline pelea con los agentes que
   *  las escriben (el servidor lo rechaza con 409). `pipelineRunning` solo
   *  sabe de las ejecuciones lanzadas desde esta pestaña; esto sí refleja
   *  el estado del servidor. */
  const entitiesLocked =
    pipelineRunning || phaseRunning || serverRunningAgentIds.size > 0;
  /** Synthesized: "running" if in runningAgentIds, else "pending".
   *  PipelineAgents derives done/canRun from agentDocCounts internally. */
  const agentStatuses: Record<
    string,
    "pending" | "running" | "done" | "error"
  > = {};
  // Cover every agent in every stage, not just PER_DOC_AGENTS — otherwise
  // open-coding agents read "pending" forever and can never show a spinner.
  for (const stage of PIPELINE_STAGES) {
    for (const agent of stage.agents) {
      agentStatuses[agent.id] = isAgentRunning(agent.id)
        ? "running"
        : "pending";
    }
  }

  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [selectedAgentLabel, setSelectedAgentLabel] = useState("");

  // ── Population Configuration ──
  const [popConfigOpen, setPopConfigOpen] = useState(false);
  const [editingPop, setEditingPop] = useState(false);
  const [popEditValue, setPopEditValue] = useState("");
  const [popGenerating, setPopGenerating] = useState(false);

  // ── Experimental Mode ──
  const [expModeOpen, setExpModeOpen] = useState(false);
  const [switchingPattern, setSwitchingPattern] = useState(false);
  const [selectedOOS, setSelectedOOS] = useState<string>("");
  const [customLabel, setCustomLabel] = useState("");

  // ── Text editing state ──
  /** Pending edit per document. The step is pinned when the editor opens, so
   *  navigating elsewhere cannot redirect the save to another field. */
  const [textEdits, setTextEdits] = useState<
    Record<string, { text: string; step: "original" | "preprocessed" }>
  >({});
  const [textSaving, setTextSaving] = useState<Record<string, boolean>>({});

  // ── Per-document error state (for routing retries) ──
  const [docError, setDocError] = useState<
    Record<string, { action: string; message: string }>
  >({});

  // ── Drag-and-drop state ──
  const dragDoc = useRef<string | null>(null);

  // ── Agent execution state ──
  // Las claves de localStorage se indexan por proyecto: una clave global
  // mezclaba el avance de proyectos distintos (el botón ↻ aparecía para
  // agentes que nunca corrieron en el proyecto abierto).
  const completedAgentsKey = `gt_completed_agents:${id ?? "none"}`;
  const iterationsKey = `gt_iterations:${id ?? "none"}`;
  const [completedAgents, setCompletedAgents] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(`gt_completed_agents:${id ?? "none"}`);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch {
      return new Set();
    }
  });
  const runningTaskRef = useRef<string | null>(null);
  /** Tracks the currently-running operation per document.
   *  Multiple docs can have ops in flight - we use a Record, not a single
   *  string, so finishing doc A's preprocess does not clear doc B's classify. */
  const [runningOps, setRunningOps] = useState<Record<string, string>>({});
  const [iterations, setIterations] = useState<Record<string, number>>(() => {
    try {
      const raw = localStorage.getItem(`gt_iterations:${id ?? "none"}`);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  });

  // Per-doc agent state is derived PURELY from docs[].estado. PipelineAgents
  // receives agentDocCounts + eligibleDocCounts and computes canRun/done
  // internally. The only external signal is runningAgentIds (set on play,
  // cleared on finish). completedAgents persists only project-level agents.
  //
  // NO DB polling — document estados ARE the source of truth.
  useEffect(() => {
    // No-op: per-doc agent state is now derived from docs[].estado.
    // This useEffect remains as a placeholder to clear the interval refs
    // and to avoid breaking the dependency chain with [docs, id].
    // completedAgents is only for project-level agents (open_coding+),
    // not for data_management agents.
  }, [docs, id]);

  // Re-seed per-project state when the route changes: react-router reuses this
  // component for /projects/:id, so state would otherwise carry over from the
  // previously open project. Declared BEFORE the persist effects so it reads
  // the target key before they write to it.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(completedAgentsKey);
      setCompletedAgents(raw ? new Set(JSON.parse(raw)) : new Set());
    } catch {
      setCompletedAgents(new Set());
    }
    try {
      const raw = localStorage.getItem(iterationsKey);
      setIterations(raw ? JSON.parse(raw) : {});
    } catch {
      setIterations({});
    }
  }, [completedAgentsKey, iterationsKey]);

  // Persist completed agents to localStorage
  useEffect(() => {
    localStorage.setItem(
      completedAgentsKey,
      JSON.stringify([...completedAgents]),
    );
  }, [completedAgents, completedAgentsKey]);

  useEffect(() => {
    localStorage.setItem(iterationsKey, JSON.stringify(iterations));
  }, [iterations, iterationsKey]);

  // ── Running state derived from the server ──
  // Keeps spinners alive across reloads. The identity of the Set is preserved
  // when the content is unchanged so the polling effect below is not restarted
  // on every refresh.
  useEffect(() => {
    const server = pipelineLog?.summary?.running_agents ?? [];
    const next = new Set(server);
    setServerRunningAgentIds((prev) => {
      if (prev.size === next.size && [...next].every((a) => prev.has(a))) {
        return prev;
      }
      return next;
    });
  }, [pipelineLog]);

  // Agents the server finished successfully (last 4 h) count as completed, so
  // a reload in the middle of a manual run still yields ↻ instead of ▶.
  useEffect(() => {
    const succeeded = pipelineLog?.summary?.succeeded_agents ?? [];
    if (succeeded.length === 0) return;
    setCompletedAgents((prev) => {
      if (succeeded.every((a) => prev.has(a))) return prev;
      const next = new Set(prev);
      succeeded.forEach((a) => next.add(a));
      return next;
    });
  }, [pipelineLog]);

  // Poll only while something is in flight, so idle pages cost nothing.
  useEffect(() => {
    if (!id) return;
    if (
      runningAgentIds.size === 0 &&
      serverRunningAgentIds.size === 0 &&
      !phaseRunning
    )
      return;
    const timer = setInterval(() => {
      getPipelineLog(id)
        .then(setPipelineLog)
        .catch(() => {});
    }, 6000);
    return () => clearInterval(timer);
  }, [id, runningAgentIds, serverRunningAgentIds, phaseRunning]);

  // ── Step navigation (classify-first) ──
  // `globalStep` is the viewed step for EVERY interview in view. Absent = auto:
  // each interview shows its own last step with data (`completedThrough`).
  // Every card clamps it to [0, completedThrough + 1].
  const [globalStep, setGlobalStep] = useState<number | null>(null);
  /** Document whose inline "redo this step" confirmation panel is open. */
  const [redoConfirmFor, setRedoConfirmFor] = useState<string | null>(null);
  /** Panel list visibility. Collapsing keeps the header and its counter. */
  const [docsOpen, setDocsOpen] = useState(true);
  /** Documents ticked for the batch actions. */
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  /** Progress of the sequential batch run; `null` when idle. */
  const [batchRun, setBatchRun] = useState<{
    done: number;
    total: number;
  } | null>(null);
  /** Batch reset/delete in flight: disables those two buttons and keeps them
   *  in place while their own requests run. */
  const [docsBusy, setDocsBusy] = useState(false);
  /** Progress of the sequential batch reset; `null` when idle. */
  const [resetRun, setResetRun] = useState<{
    done: number;
    total: number;
  } | null>(null);

  // A deleted document leaves its id behind in the selection, and a ghost id
  // would keep the toolbar in batch mode with nothing to act on.
  useEffect(() => {
    setSelectedDocs((prev) => {
      if (prev.size === 0) return prev;
      const alive = new Set(docs.map((d) => d.id));
      const next = new Set([...prev].filter((docId) => alive.has(docId)));
      return next.size === prev.size ? prev : next;
    });
  }, [docs]);

  const hitlPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Runs que el servidor sigue dando por abiertos. Si además no hay nada en
   *  vuelo, son restos de un worker que murió sin cerrarlos: se ofrecen para
   *  cerrar a mano en vez de quedar como un "pipeline en ejecución" fantasma. */
  const hasStaleRun =
    (pipelineLog?.summary?.open_runs ?? 0) > 0 &&
    !entitiesLocked &&
    !batchRun &&
    !docsBusy;

  // ── Cleanup on unmount — clear local intervals ──
  useEffect(() => {
    return () => {
      if (logPollRef.current) clearInterval(logPollRef.current);
      if (agentPollRef.current) clearInterval(agentPollRef.current);
    };
  }, []);

  // Auto-scroll log panel al recibir nuevos logs
  useEffect(() => {
    if (
      logPanelRef.current &&
      sidebarViewMode === "logs" &&
      pipelineLiveLogs.length > 0
    ) {
      logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight;
    }
  }, [pipelineLiveLogs, sidebarViewMode]);

  useEffect(() => {
    if (!id) return;
    getProject(id)
      .then((p) => {
        setProject(p);
        // FIX 4: check for stale user entities after pipeline advances
        getStaleUserEntities(id, p.estado)
          .then(setStaleWarning)
          .catch(() => {});
      })
      .catch(console.error);
    refreshDocs();
    listCategories(id).then(setCats).catch(console.error);
    ping()
      .then((p) => setUserName(p.user_id.slice(0, 8)))
      .catch(() => {});
    getPipelineLog(id)
      .then(setPipelineLog)
      .catch(() => {});
    getAgentMemos(id)
      .then((r) => {
        console.log("MEMOS LOADED:", r.total, "families:", r.families?.length);
        setAgentMemos(r.memos || []);
      })
      .catch((e) => console.error("agent-memos failed:", e));
    getAgentLogs(id)
      .then((logs) => {
        setAgentLogs(logs);
        // agentStatuses is now derived from runningAgentIds, not from logs.
      })
      .catch(() => {});
  }, [id]);

  // ── Sync experimental mode state from project ──
  useEffect(() => {
    if (!project) return;
    setSelectedOOS(project.object_of_study || "concern");
    const pa = project.population_assumption;
    const label =
      pa && typeof pa === "object" && "custom_label" in pa
        ? String((pa as any).custom_label)
        : "";
    setCustomLabel(label);
  }, [project]);

  // ── Derive stageStatuses from pipelineLog (MERGE: never go backwards) ──
  useEffect(() => {
    if (!pipelineLog || pipelineRunning) return;
    const { summary } = pipelineLog;
    if (summary.total === 0) return;

    setStageStatuses((prev) => {
      const next = { ...prev };

      const setIfForward = (key: string, desired: StageStatus) => {
        const cur = next[key] || "pending";
        // Only allow pending→running→done; never go backwards
        if (cur === "pending" && (desired === "running" || desired === "done"))
          next[key] = desired;
        else if (cur === "running" && desired === "done") next[key] = "done";
        else if (cur === "error") {
          /* keep error */
        } else if (desired === "pending") {
          /* never reset to pending */
        } else if (desired === cur) {
          /* no change */
        }
      };

      // data_management: done once every doc is segmented, classified and has
      // its incidents extracted (segmentation alone is not enough).
      if (
        (summary.need_segment ?? 0) === 0 &&
        (summary.need_classify ?? 0) === 0 &&
        (summary.need_agents ?? 0) === 0 &&
        summary.total > 0
      )
        setIfForward("data_management", "done");

      // open_coding: done once nothing is left to segment, classify or delegate
      // to an agent (mirrors the data_management condition).
      if (
        (summary.need_segment ?? 0) === 0 &&
        (summary.need_classify ?? 0) === 0 &&
        (summary.need_agents ?? 0) === 0 &&
        summary.total > 0
      )
        setIfForward("open_coding", "done");

      // selective_coding: done if project_state in ['playground_ready','completed'] or playground_ready
      const ps = summary.project_state || "collecting";
      if (
        ["playground_ready", "completed"].includes(ps) ||
        summary.playground_ready
      )
        setIfForward("selective_coding", "done");

      // theoretical_coding: done if project_state === 'completed'
      if (ps === "completed") setIfForward("theoretical_coding", "done");

      // All done: every doc fully processed
      if (summary.done === summary.total && summary.total > 0) {
        PIPELINE_STAGES.forEach((stage) => {
          setIfForward(stage.key, "done");
        });
      }

      return next;
    });
  }, [pipelineLog, pipelineRunning]);

  // ── HITL: mark relevant stage as "running" when HITL is pending ──
  useEffect(() => {
    if (!pipelineLog || hitlPending.length === 0) return;
    const gate = hitlPending[0].gate_name;

    setStageStatuses((prev) => {
      const next = { ...prev };
      // Map gate → new stage key
      if (gate === "pattern_of_interest" || gate === "core_category")
        next.open_coding = "running";
      if (
        gate === "selective_reduction" ||
        gate === "core_saturation" ||
        gate === "database_a" ||
        gate === "database_b" ||
        gate === "global_saturation"
      )
        next.selective_coding = "running";
      return next;
    });
  }, [hitlPending]);

  // Retry once on mount if memos didn't load initially
  useEffect(() => {
    if (id && agentMemos.length === 0) {
      getAgentMemos(id)
        .then((r) => {
          console.log("MEMOS RETRY:", r.total);
          setAgentMemos(r.memos || []);
        })
        .catch((e) => console.error("retry failed:", e));
    }
  }, [id]); // ✅ only on mount / id change, not every render

  // ── Open-coding HITL status polling ──
  useEffect(() => {
    if (!id) return;
    const load = () =>
      getOpenCodingHitlStatus(id)
        .then(setOcHitl)
        .catch(() => {});
    load();
    const poll = setInterval(load, 30000);
    return () => clearInterval(poll);
  }, [id]);

  // ── Duplicate-hypotheses polling ──
  useEffect(() => {
    if (!id) return;
    const load = () =>
      getHypothesisDuplicates(id)
        .then((d) => {
          setDupClusters(d.clusters.length);
          setDupRedundant(d.redundant_count);
        })
        .catch(() => {});
    load();
    const poll = setInterval(load, 60000);
    return () => clearInterval(poll);
  }, [id]);

  // Al cerrar el gate refrescamos el aviso: dentro se pueden haber borrado
  // duplicados y el poll de 60 s llegaría tarde.
  useEffect(() => {
    if (!id || ocHitlOpen) return;
    getHypothesisDuplicates(id)
      .then((d) => {
        setDupClusters(d.clusters.length);
        setDupRedundant(d.redundant_count);
      })
      .catch(() => {});
  }, [ocHitlOpen, id]);

  // ── HITL polling ──
  useEffect(() => {
    if (!id) return;
    const poll = setInterval(() => {
      getPendingHitl(id)
        .then((items) => {
          setHitlPending(items);
          setShowHITLModal(items.length > 0);
        })
        .catch(() => {});
    }, 10000); // poll every 10s
    hitlPollRef.current = poll;
    return () => clearInterval(poll);
  }, [id]);

  function refreshDocs(): Promise<void> {
    if (!id) return Promise.resolve();
    return listDocuments(id)
      .then((list) => {
        setDocs(list);
      })
      .catch((e: any) => {
        console.error("[refreshDocs] failed:", e);
        showErrorToast(
          "No se pudo refrescar el estado de los documentos: " +
            (e?.message || "error de red"),
        );
      });
  }

  /** Refresca documentos Y log del pipeline.
   *
   * El chip de cada entrevista y los contadores del sidebar leen el log
   * (`segments_count`, `incidents_count`, `next_action`, `has_classification`),
   * así que refrescar sólo `docs` los dejaba congelados hasta recargar.
   */
  function refreshAll(): Promise<void> {
    const log = id
      ? getPipelineLog(id)
          .then(setPipelineLog)
          .catch(() => {})
      : Promise.resolve();
    return Promise.all([refreshDocs(), log]).then(() => undefined);
  }

  async function toggleSegments(docId: string) {
    if (expandedDoc === docId) {
      setExpandedDoc(null);
      return;
    }
    setExpandedDoc(docId);
    // Force a fresh segment fetch on expand; the lazy-load effect takes care of
    // whatever else the currently viewed step needs.
    loadSegments(docId);
  }

  /** Loaders currently in flight, keyed `<docId>:<kind>`. Without this the
   *  lazy-load effect can fire the same request twice while the first is still
   *  running (the pipeline log polls every 6 s and re-runs it). */
  const inFlightLoads = useRef<Set<string>>(new Set());

  /** Drop the cached payload of one document so the lazy-load effect refetches
   *  it. Used after any agent run that can change segments or incidents. */
  function invalidateDocCaches(docId: string) {
    setSegments((prev) => {
      if (!(docId in prev)) return prev;
      const n = { ...prev };
      delete n[docId];
      return n;
    });
  }

  /** Reload the segment cache for one document. */
  async function loadSegments(docId: string) {
    const key = `${docId}:segments`;
    if (inFlightLoads.current.has(key)) return;
    inFlightLoads.current.add(key);
    try {
      const segs = await listSegments(docId).catch(() => [] as Segment[]);
      setSegments((prev) => ({ ...prev, [docId]: segs }));
    } finally {
      inFlightLoads.current.delete(key);
    }
  }

  // The expanded card renders whatever step it is viewing: make sure that
  // step's data is in cache. Without this, a card that opens directly on
  // `incidents` (the default for a finished interview) would sit on "loading"
  // forever, because nothing else triggers the lazy load.
  useEffect(() => {
    if (!expandedDoc) return;
    const doc = docs.find((d) => d.id === expandedDoc);
    if (!doc) return;
    const step = viewedStepOf(doc);
    if (
      (step === "classified" || step === "segmented" || step === "incidents") &&
      !segments[doc.id]
    )
      loadSegments(doc.id);
    // The caches ARE deps on purpose: `viewedStepOf` reads them, so when the
    // segments arrive a card can move from `classified` to `incidents` and we
    // must re-run to load the incidents. No loop: the loader always writes a
    // value (`[]` on failure) and the in-flight guard blocks duplicates.
  }, [expandedDoc, docs, pipelineLog, globalStep, segments]);

  function hasSegments(doc: Document): boolean {
    // Check loaded segments first
    if (segments[doc.id] && segments[doc.id].length > 0) return true;
    // Check pipeline log (real DB state)
    const log = getDocLog(doc.id);
    if (log && log.segments_count > 0) return true;
    return false;
  }

  /** ¿Puede este documento alimentar al agente per-doc?
   *
   * Se basa en el material disponible, no en el `estado`: el clasificador Glaser
   * reutiliza los segmentos existentes (camino 1) y, si no los hay, segmenta el
   * texto preprocesado (camino 2). Comparar el estado estrictamente marcaba como
   * "no elegible" a los docs ya clasificados, y re-clasificar terminaba en 0/0.
   */
  function canProcessDoc(doc: Document, agentId: string): boolean {
    const hasText = !!(
      doc.texto_preprocesado ||
      doc.texto_original ||
      doc.texto_extraido
    );
    // El clasificador consume segmentos si existen; el texto es el respaldo.
    if (agentId === "fa_glaser_data_classifier")
      return hasSegments(doc) || hasText;
    // El extractor de incidentes trabaja sobre segmentos ya clasificados: el
    // worker no segmenta por su cuenta (`_ensure_segmented` lanza sin filas en
    // `segmentos`) y el backend rechaza el resto de estados con 409.
    if (agentId === "fa_document_pattern_extractor")
      return (
        hasSegments(doc) &&
        EXTRACTOR_STATES.includes(String(doc.estado ?? "").trim())
      );
    return hasText;
  }

  /** ¿Este documento todavía necesita al agente?
   *
   * Para el clasificador se usa el `next_action` del backend: un doc en
   * 'clasificado' cuyos segmentos siguen sin categoría vuelve a contar como
   * pendiente, aunque su `estado` ya sea el de salida. Sin ese dato se cae al
   * criterio por estado.
   */
  function needsAgent(doc: Document, agentId: string): boolean {
    const log = getDocLog(doc.id);
    if (agentId === "fa_glaser_data_classifier" && log) {
      // 'error' también cuenta: el doc es reintentable, no está terminado.
      if (log.next_action === "error") return true;
      return log.next_action === "classify";
    }
    const target = PER_DOC_AGENTS[agentId as keyof typeof PER_DOC_AGENTS];
    if (!target) return false;
    // Sólo un doc que YA alcanzó el estado de salida del agente deja de
    // necesitarlo. Contar como "terminado" uno que todavía no puede procesarse
    // (p. ej. en `crudo`, sin segmentos) inflaba el contador: la barra mostraba
    // "4/5" con cero incidentes extraídos.
    return !(BEYOND[target.output] || []).includes(doc.estado);
  }

  // Per-document view mode resolution removed: the viewed step is resolved by
  // `clampedStepIndex(doc)` from the single `globalStep`.

  // ── Preprocesar (puntuación) ────────────────────────────────────

  /** Convert MIME type to a short friendly label */
  function mimeLabel(mime: string | undefined | null): string {
    if (!mime) return "?";
    const map: Record<string, string> = {
      "application/pdf": "PDF",
      "text/plain": "TXT",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        "DOCX",
      "application/msword": "DOC",
      "application/vnd.oasis.opendocument.text": "ODT",
      "text/markdown": "MD",
      "text/csv": "CSV",
      "application/rtf": "RTF",
    };
    if (map[mime]) return map[mime];
    // fallback: strip to last segment and uppercase
    const last = mime.split("/").pop() || mime;
    return last.length <= 10
      ? last.toUpperCase()
      : last.slice(0, 8).toUpperCase();
  }

  /** API call + poll until Celery task completes. Keeps punctRunning alive.
   *  Returns the outcome so callers don't wipe a freshly-set docError. */
  async function punctuateSingleDoc(
    docId: string,
  ): Promise<"success" | "failed" | "cancelled"> {
    console.log("[punctuateSingleDoc] starting for", docId);
    setPunctStatus((prev) => ({
      ...prev,
      [docId]: t("project.preprocessingProcessing"),
    }));
    const doc = docs.find((d) => d.id === docId);
    if (doc?.texto_extraido) {
      originalTexts.current[docId] = doc.texto_extraido;
    }

    // Visible, retryable failure. Returns "failed" so callers keep docError.
    const fail = (message: string) => {
      setPunctStatus((prev) => ({ ...prev, [docId]: "❌ " + message }));
      setDocError((prev) => ({
        ...prev,
        [docId]: { action: "punctuate", message },
      }));
      showErrorToast(message);
      return "failed" as const;
    };

    try {
      const res = await punctuateDocument(docId);
      console.log("[punctuateSingleDoc] response for", docId, ":", res);
      if (abortRef.current) return "cancelled";

      if (res.status === "ok" && !res.task_id) {
        // Backend determined no punctuation needed — already well-punctuated.
        // Backend now sets estado='preprocesado' even without changes.
        refreshAll();
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingOK"),
        }));
        return "success";
      }

      if (res.task_id) {
        // Task dispatched — poll until completion
        punctTaskRef.current = res.task_id;
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingProcessing") + "…",
        }));
        // Ventana de sondeo global (ver `src/config/timeouts.ts`): antes eran
        // 60 x 2s = 2 min fijos, insuficientes en máquinas lentas.
        const maxPolls = Math.ceil(STEP_TIMEOUT_MS / 2000);
        for (let poll = 0; poll < maxPolls && !abortRef.current; poll++) {
          await new Promise((r) => setTimeout(r, 2000));
          try {
            const ts = await getTaskStatus(res.task_id);
            console.log(
              "[punctuateSingleDoc] poll",
              poll,
              "status:",
              ts.status,
            );
            if (ts.status === "SUCCESS") {
              const output = ts.result;
              if (
                output &&
                typeof output === "object" &&
                (output.status === "error" || output.status === "cancelled")
              ) {
                return fail(
                  "Error del preprocesado: " +
                    (output.error || output.reason || "el worker no completó"),
                );
              }
              const changed =
                output && typeof output === "object" && output.changes_made;
              setPunctStatus((prev) => ({
                ...prev,
                [docId]: changed
                  ? t("project.preprocessingImproved")
                  : t("project.preprocessingOK"),
              }));
              if (changed) {
                setSegments((prev) => {
                  const n = { ...prev };
                  delete n[docId];
                  return n;
                });
              }
              // The worker owns the estado transition (crudo -> preprocesado).
              // Always refetch, even when punctuation did not change, otherwise
              // the card keeps showing 'crudo' until a manual reload.
              await refreshAll();
              return "success";
            }
            if (ts.status === "FAILURE") {
              const detail =
                typeof ts.result === "string"
                  ? ts.result
                  : ts.result?.error || ts.result?.reason || "Fallo interno";
              return fail("Error del worker de preprocesado: " + detail);
            }
            // Still PENDING/STARTED — keep waiting
          } catch {
            // polling error, keep trying
          }
        }
        if (!abortRef.current) {
          return fail(
            `Timeout: el preprocesado no respondió en ${STEP_TIMEOUT_MINUTES} minutos`,
          );
        }
        return "cancelled";
      }

      // Fallback: old-style response
      if (res.status === "ok" && (res as any).changes_made) {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingImproved"),
        }));
        refreshAll();
        setSegments((prev) => {
          const n = { ...prev };
          delete n[docId];
          return n;
        });
        return "success";
      }
      if (res.status === "ok") {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingOK"),
        }));
        refreshAll();
        return "success";
      }
      return fail(
        "Error del preprocesado: " + (res.message || "respuesta no reconocida"),
      );
    } catch (err: any) {
      if (abortRef.current) return "cancelled";
      console.error("[punctuateSingleDoc] error for", docId, ":", err);
      return fail(
        "Error de API al preprocesar: " +
          (err?.message || "Sin respuesta del servidor"),
      );
    }
  }

  /** Preprocess all crudo documents that have text */
  async function handlePreprocessAll() {
    const toProcess = docs.filter(
      (d) =>
        d.estado === "crudo" &&
        !!((d as any).texto_original || d.texto_extraido),
    );
    if (toProcess.length === 0) return;

    abortRef.current = false;

    try {
      for (const doc of toProcess) {
        if (abortRef.current) break;
        console.log(
          "[preprocessAll] processing doc",
          doc.id,
          doc.original_filename,
        );
        setPunctRunning(doc.id);
        // Register the op so the cancel button works during a batch run too.
        runningOp.current = { docId: doc.id, op: "punctuate" };
        setPunctStatus((prev) => ({
          ...prev,
          [doc.id]: t("project.preprocessingStarting"),
        }));
        await punctuateSingleDoc(doc.id);
        runningOp.current = null;
        setPunctRunning(null);
      }
    } finally {
      setPunctRunning(null);
    }
  }

  /** Preprocess a single document (called from the per-doc button) */
  async function handlePunctuate(docId: string) {
    if (runningOps[docId]) {
      abortRef.current = true;
      setPunctStatus((prev) => ({
        ...prev,
        [docId]: t("project.preprocessingCancelled"),
      }));
      setRunningOps((prev) => {
        const n = { ...prev };
        delete n[docId];
        return n;
      });
      // Revocar el task de Celery (el endpoint cancela + rollback del estado)
      const taskId = punctTaskRef.current;
      punctTaskRef.current = null;
      if (taskId) {
        fetch(`/api/v1/admin/tasks/${taskId}/cancel`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        })
          .then(() => refreshAll())
          .catch(() => {});
      }
      return;
    }

    abortRef.current = false;
    setRunningOps((prev) => ({ ...prev, [docId]: "punctuate" }));
    runningOp.current = { docId, op: "punctuate" };
    setPunctStatus((prev) => ({
      ...prev,
      [docId]: t("project.preprocessingStarting"),
    }));

    try {
      const outcome = await punctuateSingleDoc(docId);
      if (outcome === "success") {
        markAgentDone("preprocesado");
        setDocError((prev) => {
          const n = { ...prev };
          delete n[docId];
          return n;
        });
      }
    } catch (e: any) {
      setDocError((prev) => ({
        ...prev,
        [docId]: {
          action: "punctuate",
          message: e.message || "Error desconocido",
        },
      }));
    } finally {
      runningOp.current = null;
      setPunctRunning(null);
      // Don't leave a stale op behind: a leftover entry would show the doc as
      // still preprocessing and turn the next click into a bogus cancel.
      setRunningOps((prev) => {
        if (!prev[docId]) return prev;
        const n = { ...prev };
        delete n[docId];
        return n;
      });
    }
  }

  /** Canonical Glaser classes (the only five the backend stores). */
  const GLASER_TAG_COLORS: Record<string, string> = {
    baseline_data: "#3FB950",
    properline_data: "#58A6FF",
    interpreted_data: "#A371F7",
    vague_data: "#8B949E",
    document_context: "#D29922",
  };

  /** Taxonomía vieja que aún puede aparecer en datos clasificados antes del renombrado. */
  const LEGACY_GLASER_ALIASES: Record<string, string> = {
    processual_data: "baseline_data",
    contextual_data: "vague_data",
    // `interviewer_context` era el nombre anterior de `document_context`.
    interviewer_context: "document_context",
  };

  function canonicalGlaserTag(tag: string): string {
    return LEGACY_GLASER_ALIASES[tag] || tag;
  }

  function escapeHtml(value: string): string {
    return value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /** Render one classified block (shared shape for XML and flattened blocks). */
  function renderGlaserBlockHtml(rawTag: string, inner: string): string {
    const tag = canonicalGlaserTag(rawTag);
    const color = GLASER_TAG_COLORS[tag] || "#8B949E";
    return (
      '<div style="margin:6px 0;padding:6px 8px;border-left:3px solid ' +
      color +
      ";background:" +
      color +
      '11;border-radius:0 4px 4px 0">' +
      '<div style="margin-bottom:3px">' +
      '<span style="font-size:9px;color:' +
      color +
      ';opacity:0.6;font-weight:600">' +
      tag +
      "</span>" +
      "</div>" +
      '<span style="color:' +
      color +
      ';line-height:1.6">' +
      inner +
      "</span>" +
      "</div>"
    );
  }

  /** Render the flattened `glaser_blocks` returned by the documents endpoint. */
  function renderGlaserBlocks(blocks: GlaserBlock[]): string {
    if (!blocks.length) {
      return '<span style="color:#484F58">Sin clasificacion</span>';
    }
    return blocks
      .map((block) =>
        renderGlaserBlockHtml(
          block.class,
          escapeHtml(block.text).replace(/\n/g, "<br>"),
        ),
      )
      .join("");
  }

  /** Render classified XML text: tags as tiny labels, content colored per type. */
  function renderClassifiedText(xmlText: string): string {
    if (!xmlText) return '<span style="color:#484F58">Sin clasificacion</span>';
    // Datos clasificados con la taxonomía vieja: se muestran como su categoría
    // canónica equivalente en vez de como tag crudo sin color.
    var normalizedXml = xmlText.replace(
      /<\/?(processual_data|contextual_data|interviewer_context)[^>]*>/g,
      (match, name: string) =>
        (match.indexOf("</") === 0 ? "</" : "<") +
        canonicalGlaserTag(name) +
        ">",
    );
    var escaped = normalizedXml
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    var tagNames = Object.keys(GLASER_TAG_COLORS);
    for (var i = 0; i < tagNames.length; i++) {
      var tag = tagNames[i];
      var openTag = "&lt;" + tag + "&gt;";
      var closeTag = "&lt;/" + tag + "&gt;";
      var parts = escaped.split(openTag);
      var result2 = parts[0];
      for (var j = 1; j < parts.length; j++) {
        var closeIdx = parts[j].indexOf(closeTag);
        if (closeIdx >= 0) {
          var inner = parts[j].substring(0, closeIdx);
          var after = parts[j].substring(closeIdx + closeTag.length);
          result2 += renderGlaserBlockHtml(tag, inner) + after;
        } else {
          result2 += openTag + parts[j];
        }
      }
      escaped = result2;
    }
    return escaped;
  }

  /** Prefer flattened blocks, fall back to parsing the classified XML. */
  function renderClassified(doc: Document): string {
    const blocks = doc.glaser_blocks;
    if (blocks && blocks.length) return renderGlaserBlocks(blocks);
    return renderClassifiedText(
      doc.texto_clasificado ||
        ((doc as any).metadatos && (doc as any).metadatos.texto_clasificado) ||
        "",
    );
  }

  /** Classify a single document via Glaser classifier (3-step + validator loop) */
  async function handleClassify(docId: string) {
    const doc = docs.find((x) => x.id === docId);
    const estado = String(doc?.estado ?? "").trim();

    // Single error exit: always visible and always retryable.
    const fail = (message: string) => {
      setPunctStatus((prev) => ({ ...prev, [docId]: "❌ " + message }));
      setDocError((prev) => ({
        ...prev,
        [docId]: { action: "classify", message },
      }));
      showErrorToast(message);
    };

    if (!doc) {
      fail(
        "No se encontró el documento en la lista. Recarga la página e intenta de nuevo.",
      );
      return;
    }
    // Classify-first: the classifier reads the preprocessed TEXT, so
    // `preprocesado` is a valid input state (segments are created afterwards).
    if (!["preprocesado", "segmentado", "clasificado"].includes(estado)) {
      fail(
        `No se puede clasificar: estado actual "${doc.estado}". El documento debe estar preprocesado primero (se esperaba "preprocesado").`,
      );
      return;
    }

    if (punctRunning === docId) {
      // Cancel: abort polling + revoke Celery task
      abortRef.current = true;
      setPunctRunning(null);
      const taskId = punctTaskRef.current;
      punctTaskRef.current = null;
      if (taskId) {
        fetch(`/api/v1/admin/tasks/${taskId}/cancel`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        })
          .then(() => refreshAll())
          .catch(() => {});
      }
      return;
    }

    abortRef.current = false;
    setPunctRunning(docId);
    setRunningOps((prev) => ({ ...prev, [docId]: "classify" }));
    runningOp.current = { docId, op: "classify" };
    setPunctStatus((prev) => ({ ...prev, [docId]: "Clasificando…" }));
    setDocError((prev) => {
      const n = { ...prev };
      delete n[docId];
      return n;
    });

    try {
      const token = `Bearer ${localStorage.getItem("access_token")}`;
      const resp = await fetch(`/api/v1/documents/${docId}/classify-glaser`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: token },
      });

      // HTTP-level failure (400 sin texto, 401, 404, 500…) is never assumed OK.
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
          const body = await resp.json();
          if (body?.detail) {
            detail =
              typeof body.detail === "string"
                ? body.detail
                : JSON.stringify(body.detail);
          }
        } catch {
          /* non-JSON error body */
        }
        fail(`Error al clasificar (${resp.status}): ${detail}`);
        return;
      }

      const res = await resp.json();

      if (res.task_id) {
        punctTaskRef.current = res.task_id;
        // Misma ventana global que el resto de pasos.
        const maxPolls = Math.ceil(STEP_TIMEOUT_MS / 2000);
        for (let poll = 0; poll < maxPolls && !abortRef.current; poll++) {
          await new Promise((r) => setTimeout(r, 2000));
          try {
            const ts = await getTaskStatus(res.task_id);
            if (ts.status === "SUCCESS") {
              if (ts.result?.status === "cancelled") return;
              if (ts.result?.status === "error") {
                fail(
                  "La clasificación falló: " +
                    (ts.result?.error ||
                      ts.result?.reason ||
                      "error interno del worker"),
                );
                return;
              }
              markAgentDone("clasificado");
              invalidateDocCaches(docId);
              await refreshAll();
              setPunctStatus((prev) => ({ ...prev, [docId]: "✓ Clasificado" }));
              return;
            }
            if (ts.status === "FAILURE") {
              const detail =
                typeof ts.result === "string"
                  ? ts.result
                  : ts.result?.error || ts.result?.reason || "fallo del worker";
              fail("Error de clasificación: " + detail);
              return;
            }
          } catch {
            /* polling hiccup, keep trying */
          }
        }
        if (!abortRef.current) {
          fail(
            `Timeout: la clasificación no respondió en ${STEP_TIMEOUT_MINUTES} minutos.`,
          );
        }
        return;
      }

      if (res.status === "error") {
        fail(
          "La clasificación falló: " +
            (res.error || res.reason || "error interno"),
        );
        return;
      }

      // Synchronous completion — no task_id
      markAgentDone("clasificado");
      invalidateDocCaches(docId);
      await refreshAll();
      setPunctStatus((prev) => ({ ...prev, [docId]: "✓ Clasificado" }));
    } catch (e: any) {
      if (!abortRef.current) {
        fail(
          "No se pudo enviar la solicitud de clasificación: " +
            (e?.message || "error de red"),
        );
      }
    } finally {
      runningOp.current = null;
      setPunctRunning(null);
      setRunningOps((prev) => {
        if (!prev[docId]) return prev;
        const n = { ...prev };
        delete n[docId];
        return n;
      });
    }
  }

  /** Synchronise completedAgents after a PROJECT-LEVEL agent succeeds.
   *  Per-doc agents (data_management) do NOT use completedAgents — their
   *  state is derived purely from docs[].estado. */
  function markAgentDone(estado: string) {
    // Per-doc agents: no-op. PipelineAgents derives state from docs.
  }

  /** Clear completedAgents downstream from a given estado (used on restore).
   *  Per-doc agents don't use completedAgents — no-op. */
  function clearAgentsFrom(estado: string) {
    // Per-doc agents: no-op.
  }

  /** Route action based on doc estado.
   *
   *  The card header no longer shows a "next step" button (the user moves with
   *  `<` / `>` and runs from the empty step). This remains as the retry/error
   *  entry point and as a fallback for the first missing step. */
  async function handleDocAction(docId: string) {
    const d = docs.find((x) => x.id === docId);
    if (!d) {
      showErrorToast("No se encontró el documento. Recarga la página.");
      return;
    }
    const estado = String(d.estado ?? "").trim();
    console.log("[handleDocAction] docId:", docId, "estado:", d.estado);

    // Error retry
    const err = docError[docId];
    if (err) {
      setDocError((prev) => {
        const n = { ...prev };
        delete n[docId];
        return n;
      });
      if (err.action === "punctuate") return handlePunctuate(docId);
      if (err.action === "classify") return handleClassify(docId);
      if (err.action === "segment") return handleSegment(docId);
      if (err.action === "extract") return handleExtractIncidents(docId);
      showErrorToast(err.message || "La acción anterior falló");
      return;
    }

    // A worker is already advancing this document: a second click must not
    // re-dispatch nor silently cancel the in-flight operation.
    if (IN_FLIGHT_DOC_STATES.includes(estado)) {
      console.log("[handleDocAction] ignoring click, in-flight:", estado);
      return;
    }

    // A document marked 'error' by the state machine has no retry path in the
    // pipeline; route to the restore flow instead of a no-op "✓ Completo".
    if (estado === "error") {
      return handleRestoreError(docId);
    }

    // Cancel running operation (modular)
    if (punctRunning === docId) {
      await cancelRunningOp(docId);
      return;
    }

    // Fallback: run the first step without data (classify-first order).
    const nextIdx = completedThrough(d) + 1;
    if (nextIdx < DOC_STEPS.length) return runStep(d, DOC_STEPS[nextIdx]);
    showErrorToast(`Acción no disponible para el estado "${d.estado}"`);
  }

  /** Trigger F2.3: extract patterns & incidents */
  async function handleExtractIncidents(docId: string) {
    abortRef.current = false;
    setPunctRunning(docId);
    runningOp.current = { docId, op: "extract" };
    try {
      const outcome = await runDocTask(
        docId,
        `/api/v1/projects/${id}/pipeline/run-agent/extract_patterns`,
        abortRef,
      );
      if (outcome === "failed") {
        const message =
          "La extracción de incidentes falló en el worker. Revisa los logs de worker-heavy.";
        setDocError((prev) => ({
          ...prev,
          [docId]: { action: "extract", message },
        }));
        setPunctStatus((prev) => ({ ...prev, [docId]: "❌ " + message }));
        showErrorToast(message);
      } else if (outcome === "timeout") {
        const message = `Timeout: la extracción de incidentes no respondió en ${STEP_TIMEOUT_MINUTES} minutos.`;
        setDocError((prev) => ({
          ...prev,
          [docId]: { action: "extract", message },
        }));
        setPunctStatus((prev) => ({ ...prev, [docId]: "❌ " + message }));
        showErrorToast(message);
      } else {
        // New incidents: drop the cache so an open panel refetches them.
        invalidateDocCaches(docId);
      }
    } catch (e: any) {
      if (!abortRef.current) showErrorToast("Error: " + (e.message || ""));
    } finally {
      runningOp.current = null;
      setPunctRunning(null);
    }
  }

  /** Segment a single document */
  async function handleSegment(docId: string) {
    console.log("[handleSegment] dispatching for", docId);
    abortRef.current = false;
    setPunctRunning(docId);
    setRunningAgentIds((prev) => new Set([...prev, "segmentar_documento"]));
    runningOp.current = { docId, op: "segment" };
    try {
      const outcome = await runDocTask(
        docId,
        `/api/v1/projects/${id}/pipeline/run-agent/segmentar_documento`,
        abortRef,
      );
      if (outcome === "failed" || outcome === "timeout") {
        const message =
          outcome === "timeout"
            ? `Timeout: la segmentación no respondió en ${STEP_TIMEOUT_MINUTES} minutos.`
            : "La segmentación falló en el worker. Revisa los logs de worker-nlp.";
        setDocError((prev) => ({
          ...prev,
          [docId]: { action: "segment", message },
        }));
        setPunctStatus((prev) => ({ ...prev, [docId]: "❌ " + message }));
        showErrorToast(message);
      } else {
        // Segments changed: drop the cache so the panel refetches them.
        invalidateDocCaches(docId);
      }
    } catch (e: any) {
      if (!abortRef.current) showErrorToast("Error: " + (e.message || ""));
    } finally {
      runningOp.current = null;
      setPunctRunning(null);
      setRunningAgentIds((prev) => {
        const next = new Set(prev);
        next.delete("segmentar_documento");
        return next;
      });
    }
  }

  /** Restore a document the state machine marked as `error`.
   *
   *  This is the error-recovery path only: it is reached from
   *  `handleDocAction` (and the header button) exclusively for
   *  `estado === "error"`. The general per-document ↻ restore was replaced by
   *  the per-state redo (`handleRedoStep`), which spells out what it erases.
   *  Chain (classify-first): crudo → preprocesado → clasificado → segmentado →
   *  incidentes. Each branch undoes exactly one layer. */
  async function handleRestoreError(docId: string) {
    if (!(await safeConfirm(t("project.restoreOriginalConfirm")))) return;
    try {
      const doc = docs.find((d) => d.id === docId);
      if (!doc) return;
      const token = `Bearer ${localStorage.getItem("access_token")}`;
      // Map estado -> rollback op (inverse of the chain)
      if (doc.estado === "preprocesado") {
        // Clear preprocessed text + progress, return to crudo
        await fetch(`/api/v1/documents/${docId}/restore-original`, {
          method: "POST",
          headers: { Authorization: token },
        }).catch(() => {});
        clearAgentsFrom("preprocesado");
      } else if (doc.estado === "clasificado") {
        // Classification lives in the text metadata (and later in the segment
        // tags, which do not exist yet at this point): back to preprocesado.
        await fetch(`/api/v1/documents/${docId}/classify-glaser`, {
          method: "DELETE",
          headers: { Authorization: token },
        }).catch(() => {});
        clearAgentsFrom("clasificado");
      } else if (doc.estado === "segmentado") {
        // Keep the Glaser tags: drop segments only, back to clasificado.
        await deleteDocumentSegments(docId, {
          keepClassification: true,
        }).catch(() => {});
        clearAgentsFrom("segmentado");
      } else if (
        doc.estado === "incidentes_extraidos" ||
        doc.estado === "procesado" ||
        doc.estado === "listo"
      ) {
        // For post-extraction states: restore to crudo (full reset)
        await restoreDocumentOriginal(docId);
        await deleteDocumentSegments(docId).catch(() => {});
        await fetch(`/api/v1/documents/${docId}/classify-glaser`, {
          method: "DELETE",
          headers: { Authorization: token },
        }).catch(() => {});
        // Per-doc agent state derives from docs[].estado — no state to clear.
      } else {
        // crudo or unknown -> restore to crudo
        await restoreDocumentOriginal(docId);
      }
      // Clear any error state for this document
      setDocError((prev) => {
        const n = { ...prev };
        delete n[docId];
        return n;
      });
      refreshAll();
    } catch (e: any) {
      showErrorToast("Error: " + (e.message || ""));
    }
  }

  function findLastCompletedIdx(): number {
    let last = -1;
    for (let i = 0; i < PIPELINE_STAGES.length; i++) {
      if ((stageStatuses[PIPELINE_STAGES[i].key] || "pending") === "done") {
        last = i;
      } else {
        break; // stop at first non-done — stages are sequential
      }
    }
    return last;
  }

  function restartFromStage(stageKey: string) {
    // Guard: refuse if no documents at all
    if (docs.length === 0) {
      console.log("[restartFromStage] BLOCKED: no docs, showing error");
      resetStages(); // force all stages back to pending
      setPipelineMsg(t("project.pipelineNoDocs"));
      setPipelineFailed(true);
      return;
    }
    console.log(
      "[restartFromStage] proceeding with",
      docs.length,
      "docs, stage:",
      stageKey,
    );
    const stageIdx = PIPELINE_STAGES.findIndex((s) => s.key === stageKey);
    // Mark previous stages as done, this one as running, later as pending
    PIPELINE_STAGES.forEach((s, i) => {
      if (i < stageIdx) updateStage(s.key, "done");
      else if (i === stageIdx) updateStage(s.key, "running");
      else updateStage(s.key, "pending");
    });
    // Run pipeline
    setPipelineRunning(true);
    runPipeline(false);
  }

  // ── Memo mutations ────────────────────────────

  /** Deep-set a value in an object using dot/bracket path notation.
   *  e.g. deepSet(obj, "items[0].name", "new") → cloned obj with nested update. */
  function deepSet(
    obj: Record<string, unknown>,
    path: string,
    value: unknown,
  ): Record<string, unknown> {
    const clone = JSON.parse(JSON.stringify(obj));
    // Parse path: "sampling_dimensions[0].name" → ["sampling_dimensions", "[0]", "name"]
    const parts: string[] = [];
    let cur = "";
    for (const ch of path) {
      if (ch === ".") {
        if (cur) {
          parts.push(cur);
          cur = "";
        }
      } else if (ch === "[") {
        if (cur) {
          parts.push(cur);
          cur = "";
        }
        cur = "[";
      } else if (ch === "]") {
        parts.push(cur + "]");
        cur = "";
      } else {
        cur += ch;
      }
    }
    if (cur) parts.push(cur);

    // Navigate to the target and set value
    let target: any = clone;
    for (let i = 0; i < parts.length - 1; i++) {
      const p = parts[i];
      target = p.startsWith("[") ? target[parseInt(p.slice(1, -1))] : target[p];
      if (target === undefined || target === null) return clone; // bail on bad path
    }
    const last = parts[parts.length - 1];
    if (last.startsWith("[")) {
      target[parseInt(last.slice(1, -1))] = value;
    } else {
      target[last] = value;
    }
    return clone;
  }

  /** 404 from `DELETE /agent-outputs/{id}`: someone else already removed it. */
  function memoAlreadyGone(e: any) {
    if (e?.status === 404) return true;
    return /no encontrado|not found/i.test(e?.message || "");
  }

  async function handleDeleteMemo(memoId: string) {
    if (!id) return;
    if (entitiesLocked) {
      showToast(t("memo.pipelineBusy"), "error");
      return;
    }
    try {
      await deleteAgentOutput(memoId);
      setAgentMemos((prev) => prev.filter((m) => m.id !== memoId));
      showToast(t("project.memoDeleted"));
      refreshMemos();
    } catch (e: any) {
      // Already gone (404): the end state is the one the user asked for.
      if (memoAlreadyGone(e)) {
        setAgentMemos((prev) => prev.filter((m) => m.id !== memoId));
        showToast(t("project.memoDeleted"));
        refreshMemos();
        return;
      }
      showToast(`${t("memo.deleteError")}: ${e?.message || ""}`, "error");
    }
  }

  /** Batch delete, one request per memo: one failure must not stop the rest. */
  async function handleDeleteMemos(memoIds: string[]) {
    if (!id) return;
    if (entitiesLocked) {
      showToast(t("memo.pipelineBusy"), "error");
      return;
    }
    const removed: string[] = [];
    for (const memoId of memoIds) {
      try {
        await deleteAgentOutput(memoId);
        removed.push(memoId);
      } catch (e: any) {
        // A memo someone else already deleted is not a failure.
        if (memoAlreadyGone(e)) removed.push(memoId);
        // Otherwise counted below; a failed memo stays in the list.
      }
    }
    if (removed.length > 0) {
      const gone = new Set(removed);
      setAgentMemos((prev) => prev.filter((m) => !gone.has(m.id)));
    }
    const failed = memoIds.length - removed.length;
    if (failed > 0) {
      showToast(
        `${t("memo.deleteError")}: ${failed}/${memoIds.length}`,
        "error",
      );
    } else {
      showToast(t("memo.deletedCount", { n: removed.length }));
    }
    refreshMemos();
  }

  /** Deletes every agent memo (all families) in one transactional call. */
  async function handleDeleteAllMemos() {
    if (!id) return;
    if (entitiesLocked) {
      showToast(t("memo.pipelineBusy"), "error");
      return;
    }
    try {
      const r = await deleteAgentMemos(id);
      setAgentMemos([]);
      refreshMemos();
      showToast(t("memo.deletedCount", { n: r.deleted }));
    } catch (e: any) {
      const msg = e?.message || "";
      if (/pipeline/i.test(msg)) showToast(t("memo.pipelineBusy"), "error");
      else showToast(`${t("memo.deleteError")}: ${msg}`, "error");
    }
  }

  async function handleUpdateMemo(
    memoId: string,
    field: string,
    value: string,
  ) {
    const token = localStorage.getItem("access_token");
    // Apply deep update on current memo data
    setAgentMemos((prev) => {
      const memo = prev.find((m) => m.id === memoId);
      if (!memo) return prev;
      const newData = deepSet(memo.data, field, value);
      // Send full data to server (backed by JSONB column)
      fetch(`/api/v1/agent-outputs/${memoId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ data: newData }),
      }).catch(() => {});
      return prev.map((m) => (m.id === memoId ? { ...m, data: newData } : m));
    });
    showToast(t("project.memoChangesPermanent"));
  }

  function showToast(msg: string, type: "info" | "error" = "info") {
    setToastMsg(msg);
    setToastType(type);
    setToastVisible(true);
  }

  function showErrorToast(msg: string) {
    showToast(msg, "error");
  }

  // ── Save edited document text ──
  async function saveDocText(docId: string) {
    const edit = textEdits[docId];
    if (!edit) return;
    setTextSaving((prev) => ({ ...prev, [docId]: true }));
    try {
      // The field follows the step the edit STARTED on, not the step being
      // viewed now: navigating away while editing must not misroute the write.
      const field =
        edit.step === "preprocessed" ? "texto_preprocesado" : "texto_original";
      const res = await fetch(`/api/v1/documents/${docId}/text`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({ [field]: edit.text }),
      });
      // `fetch` does not throw on 4xx: without this the save looked successful
      // while the backend had rejected the field.
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || `HTTP ${res.status}`);
      }
      setTextEdits((prev) => {
        const next = { ...prev };
        delete next[docId];
        return next;
      });
      await refreshAll();
    } catch (e: any) {
      showErrorToast(t("project.textSaveError") + ": " + (e?.message || ""));
    } finally {
      setTextSaving((prev) => ({ ...prev, [docId]: false }));
    }
  }

  // ── Modification callback ───────────────────

  /** Re-reads the memo list (the truth is the backend, not the local guess). */
  async function refreshMemos() {
    if (!id) return;
    try {
      const r = await getAgentMemos(id);
      setAgentMemos(r.memos || []);
    } catch {}
  }

  function handleMemoModified() {
    if (id) {
      getAgentMemos(id)
        .then((r) => {
          setAgentMemos(r.memos || []);
        })
        .catch(() => {});
    }
    showToast(t("project.memoModificationApplied"));
  }

  // ── Pipeline IA ──────────────────────────────────

  function resetStages(presets?: Record<string, StageStatus>) {
    const init: Record<string, StageStatus> = {};
    PIPELINE_STAGES.forEach(
      (s) => (init[s.key] = presets?.[s.key] || "pending"),
    );
    setStageStatuses(init);
  }

  function updateStage(key: string, status: StageStatus) {
    setStageStatuses((prev) => ({ ...prev, [key]: status }));
  }

  async function runPipeline(forceAll: boolean = false) {
    const auth = `Bearer ${localStorage.getItem("access_token")}`;
    abortRef.current = false;
    setPipelineRunning(true);
    setPipelineLiveLogs([]);
    // Start log polling
    if (logPollRef.current) clearInterval(logPollRef.current);
    let lastTs = Date.now() / 1000;
    logPollRef.current = setInterval(async () => {
      try {
        const r = await fetch(
          `/api/v1/projects/${id}/pipeline/tail?since=${lastTs}`,
        );
        const data = await r.json();
        if (data.logs?.length) {
          setPipelineLiveLogs((prev) => [...prev, ...data.logs].slice(-200));
          lastTs = Math.max(...data.logs.map((l: any) => l.ts), lastTs);
        }
      } catch {}
    }, 2000);

    // Start agent log polling
    if (agentPollRef.current) clearInterval(agentPollRef.current);
    agentPollRef.current = setInterval(async () => {
      try {
        const logs = await getAgentLogs(id!);
        setAgentLogs(logs);
        // agentStatuses is derived from runningAgentIds, not from logs.
      } catch {}
    }, 5000);

    // ── Check for work BEFORE starting workers ──
    // A classify-only project is also a continuation: segmentation is done but
    // data-management work remains, so this is not a fresh start.
    const isContinue =
      !forceAll &&
      docsNeedSegment === 0 &&
      (docsNeedClassify > 0 || docsNeedAgents > 0);

    // Fetch pipeline log first to determine work
    const freshLog = await getPipelineLog(id!).catch(() => null);
    if (freshLog) setPipelineLog(freshLog);

    // Compute which documents need processing
    const todo: Document[] = [];
    if (forceAll) {
      todo.push(...docs);
    } else if (freshLog) {
      for (const dl of freshLog.documents) {
        if (dl.next_action !== "done") {
          const doc = docs.find((d) => d.id === dl.document_id);
          if (doc) todo.push(doc);
        }
      }
    } else {
      todo.push(...docs.filter((d) => d.estado !== "listo"));
    }

    // Early exit: nothing to do
    if (todo.length === 0) {
      resetStages();
      setPipelineMsg(t("project.pipelineAllProcessed"));
      setPipelineFailed(false);
      setPipelineRunning(false);
      if (logPollRef.current) {
        clearInterval(logPollRef.current);
        logPollRef.current = null;
      }
      if (agentPollRef.current) {
        clearInterval(agentPollRef.current);
        agentPollRef.current = null;
      }
      return;
    }

    // ── Actually start workers and process ──
    if (isContinue) {
      resetStages({ workers: "done", data_management: "done" });
      updateStage("open_coding", "running");
      setPipelineMsg(t("project.pipelineContinuing"));
    } else {
      resetStages();
      updateStage("workers", "running");
      setPipelineMsg(t("project.pipelineStarting"));
      await fetch("/api/v1/admin/workers/nlp/start", {
        method: "POST",
        headers: { Authorization: auth },
      });
      await fetch("/api/v1/admin/workers/heavy/start", {
        method: "POST",
        headers: { Authorization: auth },
      });
      await new Promise((r) => setTimeout(r, 2000));
      updateStage("workers", "done");
    }

    // Call unified orchestrator (backend handles all docs)
    setPipelineMsg(t("project.pipelineOrchestrator"));
    if (stageStatuses.data_management !== "done") {
      updateStage("data_management", "running");
    }

    let pipelineOk = false;
    // Si el orquestador no despachó ninguna tarea nueva, no hay progreso que
    // esperar (todos los docs ya están en un estado terminal).
    let dispatched = false;
    setPipelineFailed(false);

    try {
      const response = await fetch(`/api/v1/projects/${id}/pipeline/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({ force: forceAll }),
      });

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(
          `Backend ${response.status}: ${text.slice(0, 200) || response.statusText}`,
        );
      }

      const res = await response.json();

      // ── Orchestrator returned a fatal error (segmentation/preprocessing failure) ──
      if (res.status === "error") {
        setPipelineMsg(
          `❌ ${res.message || "Pipeline blocked by fatal error"}`,
        );
        setPipelineFailed(true);
        updateStage("data_management", "error");
        updateStage("open_coding", "error");
        abortRef.current = true;
        showErrorToast(
          "Error de segmentacion: " +
            (res.message || "Fallo en worker — revisa los logs"),
        );
        // Clear fatal error signal so user can retry
        try {
          await fetch(`/api/v1/admin/projects/${id}/stop`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${localStorage.getItem("access_token")}`,
            },
          });
        } catch {}
        return;
      }

      pipelineOk = true;

      if (res.status === "no_docs") {
        setPipelineMsg(t("project.noDocuments"));
        updateStage("data_management", "done");
        updateStage("open_coding", "done");
      } else {
        setPipelineMsg(res.message || t("project.pipelineTriggered"));
        if (res.summary?.need_segment === 0)
          updateStage("data_management", "done");
        if (res.summary?.need_agents === 0) {
          if ((res.summary?.need_segment ?? 1) === 0) {
            updateStage("open_coding", "done");
          }
        } else {
          updateStage("open_coding", "running");
        }

        // Phase B (synthesis) detection → selective_coding is running
        if ((res as any).task_ids?.phase_b) {
          updateStage("selective_coding", "running");
          setPipelineMsg(t("project.pipelinePhaseB"));
        }

        dispatched =
          ((res.task_ids?.segment as unknown[])?.length ?? 0) > 0 ||
          ((res.task_ids?.agents as unknown[])?.length ?? 0) > 0 ||
          Boolean((res as any).task_ids?.phase_b);
        if (!dispatched) setPipelineMsg(t("project.pipelineAllProcessed"));

        // Poll until complete — mismo techo global que el resto de pasos.
        const maxPipelinePolls = Math.ceil(STEP_TIMEOUT_MS / 5000);
        for (
          let poll = 0;
          dispatched && poll < maxPipelinePolls && !abortRef.current;
          poll++
        ) {
          await new Promise((r) => setTimeout(r, 5000));
          const status = await getPipelineLog(id!).catch(() => null);
          if (status) {
            setPipelineLog(status);
          }
          if (status?.summary) {
            // ── Failure detection ──
            if (status.summary.failed > 0 || status.summary.failed_tasks > 0) {
              const errNames = (status.summary.errors || [])
                .map((e: { filename: string }) => e.filename)
                .join(", ");
              setPipelineMsg(
                t("project.pipelineFailed") +
                  (errNames || t("project.document")),
              );
              updateStage("data_management", "error");
              updateStage("open_coding", "error");
              updateStage("selective_coding", "error");
              setPipelineFailed(true);
              abortRef.current = true;
              showErrorToast(
                "Error de segmentacion en " +
                  (errNames || "documento") +
                  " — pipeline detenido",
              );
              break;
            }

            if (status.summary.need_segment === 0)
              updateStage("data_management", "done");
            if (
              status.summary.need_agents === 0 &&
              status.summary.need_segment === 0
            )
              updateStage("open_coding", "done");

            // Selective Coding completion: playground_ready
            if (status.summary.playground_ready) {
              updateStage("selective_coding", "done");
            }

            if (status.summary.done === status.summary.total) {
              setPipelineMsg(t("project.pipelineCompleted"));
            }
          }
          if (poll % 6 === 0)
            setPipelineMsg(t("project.pipelineProcessing") + ` (${poll * 5}s)`);
        }
      }
    } catch (e: any) {
      setPipelineMsg(`❌ ${e.message}`);
      showErrorToast(
        "Error del pipeline: " + (e.message || "Fallo inesperado"),
      );
    }

    if (abortRef.current) {
      // Stop workers + rollback
      if (logPollRef.current) {
        clearInterval(logPollRef.current);
        logPollRef.current = null;
      }
      if (agentPollRef.current) {
        clearInterval(agentPollRef.current);
        agentPollRef.current = null;
      }
      await stopProjectPipeline(id!).catch(() => {});
      if (pipelineFailed) {
        // Keep error states set during polling
        ["selective_coding", "theoretical_coding"].forEach((k) =>
          updateStage(k, "error"),
        );
      } else {
        resetStages();
        setPipelineMsg(t("project.pipelineCancelled"));
      }
    } else if (pipelineOk && dispatched) {
      // Pipeline completed normally
      updateStage("data_management", "done");
      updateStage("open_coding", "done");
      updateStage("selective_coding", "done");
      setPipelineMsg(t("project.pipelineCompleted"));
    }

    refreshDocs();
    listCategories(id!).then(setCats);
    getPipelineLog(id!)
      .then(setPipelineLog)
      .catch(() => {});
    getAgentMemos(id!)
      .then((r) => {
        setAgentMemos(r.memos || []);
      })
      .catch(() => {});
    setPipelineRunning(false);
  }

  // ── Upload ───────────────────────────────────────

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0 || !id) return;
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(id, file);
      }
      refreshDocs();
      getPipelineLog(id!)
        .then(setPipelineLog)
        .catch(() => {});
    } catch (err: any) {
      showErrorToast(err?.message || t("common.error"));
    }
    e.target.value = "";
  }

  /** Documents the batch actions apply to: the ticked ones, or all of them. */
  function batchTargets(): Document[] {
    if (selectedDocs.size === 0) return docs;
    return docs.filter((d) => selectedDocs.has(d.id));
  }

  /** The selection covers the whole list, so the project-wide endpoint is the
   *  exact equivalent of the per-document one. */
  function isFullSelection(): boolean {
    return selectedDocs.size > 0 && selectedDocs.size === docs.length;
  }

  /** True while this interview has a step in flight, whether the op was
   *  dispatched from this tab (`runningOps` / `punctRunning`) or the server
   *  reports it through `estado` after a reload. */
  function docRunning(doc: Document): boolean {
    return (
      punctRunning === doc.id ||
      !!runningOps[doc.id] ||
      IN_FLIGHT_DOC_STATES.includes(String(doc.estado ?? "").trim())
    );
  }

  /** True while ANY processing is in flight in the project: pipeline or phase
   *  runs, agent tasks on the server, a per-doc op, or the batch run.
   *  Destructive controls (redo, delete) hide until this goes quiet, otherwise
   *  they race with the worker that is writing the very data they erase. */
  function anyStepRunning(): boolean {
    return (
      entitiesLocked ||
      runningAgentIds.size > 0 ||
      punctRunning !== null ||
      Object.keys(runningOps).length > 0 ||
      batchRun !== null ||
      docsBusy
    );
  }

  /** `anyStepRunning` plus the interviews the SERVER still reports in flight.
   *  After a reload there is no local op state, so only `estado` remembers the
   *  worker. Batch destructive controls use this: they rewrite several
   *  documents at once, so one busy card is reason enough to stay away. */
  function anyDocProcessing(): boolean {
    return anyStepRunning() || docs.some((d) => docRunning(d));
  }

  /** Targets the batch-run button would actually fire on right now: the ticked
   *  documents (or all of them) that sit exactly on the viewed step and are
   *  not already running. */
  function runTargets(): Document[] {
    const step = DOC_STEPS[globalStepBase()];
    if (step === "original") return [];
    return batchTargets().filter(
      (d) =>
        isOnEmptyStep(d) &&
        viewedStepOf(d) === step &&
        punctRunning !== d.id &&
        !runningOps[d.id],
    );
  }

  /** Run the viewed step on every target sitting exactly on it.
   *
   *  Sequential on purpose: each step spawns worker tasks and firing them all
   *  at once floods the queue. Documents that already have the step, are behind
   *  it or have an op in flight are skipped without a word. */
  async function handleRunOnTargets() {
    if (batchRun) return;
    const step = DOC_STEPS[globalStepBase()];
    if (step === "original") return;
    const targets = runTargets();
    if (targets.length === 0) return;
    setBatchRun({ done: 0, total: targets.length });
    try {
      for (const doc of targets) {
        try {
          await runStep(doc, step);
        } catch {
          // `runStep` reports its own error: one failure must not stop the batch.
        }
        setBatchRun((prev) => (prev ? { ...prev, done: prev.done + 1 } : prev));
      }
    } finally {
      setBatchRun(null);
    }
  }

  /** Undo, on every target document, only its LAST completed step.
   *
   *  This is the batch form of the per-card ↺ redo (`handleRedoStep`): each
   *  interview walks back exactly one layer, so a mixed selection stays mixed
   *  — a segmented document goes back to `clasificado`, a classified one to
   *  `preprocesado` — instead of every card collapsing to `crudo`.
   *  Documents that only have the uploaded file are skipped: `original` is the
   *  one step that cannot be undone. */
  async function handleResetLastStep() {
    if (!id || anyDocProcessing()) return;
    const targets = batchTargets()
      .map((doc) => ({ doc, step: DOC_STEPS[completedThrough(doc)] }))
      .filter((t) => t.step !== "original");
    if (targets.length === 0) {
      showToast(t("project.resetNothingToUndo"));
      return;
    }
    const question = isFullSelection()
      ? t("project.resetDocsConfirm")
      : t("project.resetSelectedConfirm", { count: targets.length });
    if (!(await safeConfirm(question))) return;
    setDocsBusy(true);
    setResetRun({ done: 0, total: targets.length });
    let failed = 0;
    try {
      // Sequential on purpose: one erase per document, same as the per-card ↺.
      for (const { doc, step } of targets) {
        try {
          await eraseStep(doc, step);
        } catch {
          failed += 1; // one failure must not stop the batch
        }
        setResetRun((prev) => (prev ? { ...prev, done: prev.done + 1 } : prev));
      }
      // Drop the caches that no longer reflect the server state.
      const touched = new Set(targets.map(({ doc }) => doc.id));
      setSegments((prev) => {
        const n = { ...prev };
        touched.forEach((docId) => delete n[docId]);
        return n;
      });
      setDocError((prev) => {
        const n = { ...prev };
        touched.forEach((docId) => delete n[docId]);
        return n;
      });
      await refreshAll();
      getPipelineLog(id)
        .then(setPipelineLog)
        .catch(() => {});
      if (failed > 0)
        showErrorToast(
          `${t("project.resetDocsError")} (${failed}/${targets.length})`,
        );
      else showToast(t("project.resetDocsSuccess", { count: targets.length }));
    } catch (e: any) {
      showErrorToast(
        t("project.resetDocsError") + (e?.message ? ": " + e.message : ""),
      );
    } finally {
      setResetRun(null);
      setDocsBusy(false);
    }
  }

  async function handleDeleteSelected() {
    // Re-read at click time: a run may have started after this render.
    if (!id || anyDocProcessing()) return;
    const all = isFullSelection();
    const count = all ? docs.length : selectedDocs.size;
    const question = all
      ? t("project.deleteAllDocsConfirm")
      : t("project.deleteSelectedConfirm", { count });
    if (!(await safeConfirm(question))) return;
    setDocsBusy(true);
    try {
      if (all) {
        await deleteAllDocuments(id);
        resetStages();
      } else {
        for (const docId of [...selectedDocs]) await deleteDocument(docId);
      }
      setSelectedDocs(new Set());
      setGlobalStep(null);
      await refreshAll();
      showToast(t("project.deleteAllDocsSuccess", { count }));
    } catch (e: any) {
      showErrorToast(t("projects.deleteError") + (e?.message ? e.message : ""));
    } finally {
      setDocsBusy(false);
    }
  }

  function handleLogout() {
    clearToken();
    navigate("/login");
  }

  // ── Population config handlers ──────────────

  async function handleGeneratePop() {
    if (!id) return;
    setPopGenerating(true);
    try {
      const result = await generatePopulationGeneralization(id);
      // Refresh project to get the new population_assumption
      const updated = await getProject(id);
      setProject(updated);
      showToast(t("project.populationGenerated"));
    } catch (err: any) {
      showToast(
        `❌ ${t("project.populationGenerateError")}: ${err.message || err}`,
      );
    } finally {
      setPopGenerating(false);
    }
  }

  async function handleSavePop() {
    if (!id || !popEditValue.trim()) return;
    setEditingPop(false);
    try {
      await updatePopulationAssumption(id, {
        population_description: popEditValue.trim(),
      });
      // Refresh project to get updated data
      const updated = await getProject(id);
      setProject(updated);
      showToast("✅ Population description updated.");
    } catch (err: any) {
      showToast(`❌ ${err.message || err}`);
    }
  }

  function handleStartEditPop(currentValue: string) {
    setPopEditValue(currentValue);
    setEditingPop(true);
  }

  // ── Frame label translation helpers ─────────

  function spatialFrameLabel(frame: string): string {
    const map: Record<string, string> = {
      cohabiting_group: "Cohabiting group",
      sparse: "Sparse",
      high_diversity: "High diversity",
    };
    return map[frame] || frame;
  }

  function temporalFrameLabel(frame: string): string {
    const map: Record<string, string> = {
      present_continuous: "Present continuous",
      retrospective: "Retrospective",
      prospective: "Prospective",
      longitudinal: "Longitudinal",
    };
    return map[frame] || frame;
  }

  async function handleSwitchPattern() {
    if (!id || !selectedOOS) return;
    setSwitchingPattern(true);
    try {
      const payload: any = { object_of_study: selectedOOS };
      if (selectedOOS === "custom" && customLabel.trim()) {
        payload.custom_label = customLabel.trim();
      }
      await updateProject(id, payload);
      // Refresh project data to get updated estado, object_of_study, etc.
      const updated = await getProject(id);
      setProject(updated);
      showToast(t("project.experimentalModeSuccess"));
      setExpModeOpen(false);
    } catch (err: any) {
      showToast(`❌ ${err.message || err}`);
    } finally {
      setSwitchingPattern(false);
    }
  }

  // ── Derived state (from real pipeline log) ─────

  const logSummary = pipelineLog?.summary;
  const docsNeedSegment = logSummary?.need_segment ?? 0;
  const docsNeedClassify = logSummary?.need_classify ?? 0;
  const docsNeedAgents = logSummary?.need_agents ?? 0;
  const docsDone = logSummary?.done ?? 0;
  const docsPendientes = docsNeedSegment + docsNeedClassify + docsNeedAgents;
  const pipelineParcial = docsDone > 0 && docsPendientes > 0;
  const playgroundReady = logSummary?.playground_ready ?? cats.length > 0;

  // Next pipeline stage (dynamic, from PIPELINE_STAGES). Classification is a
  // data_management task, so docs that only need classify keep it selected.
  const nextStageKey =
    docsNeedSegment > 0 || docsNeedClassify > 0
      ? "data_management"
      : "open_coding";
  const nextStage = PIPELINE_STAGES.find((s) => s.key === nextStageKey)!;
  const nextStageCount =
    nextStageKey === "data_management"
      ? docsNeedSegment + docsNeedClassify
      : docsNeedAgents;

  function getDocLog(docId: string): ExtendedDocLog | undefined {
    return pipelineLog?.documents.find((d) => d.document_id === docId) as
      ExtendedDocLog | undefined;
  }

  // ── Per-interview step model (classify-first) ─────────────────
  // Steps: original → preprocessed → classified → segmented → incidents.
  // A missing step stops the chain: that gap is what the project-level
  // inconsistency banner surfaces.

  /** Human label for a step, in the active locale. */
  function stepLabel(step: DocStepKey): string {
    return t(STEP_LABEL_KEYS[step]);
  }

  /** ¿Existe dato para este paso de esta entrevista? */
  function hasStep(doc: Document, step: DocStepKey): boolean {
    const log = getDocLog(doc.id);
    const estado = String(doc.estado ?? "").trim();
    switch (step) {
      case "original":
        return true;
      case "preprocessed":
        // The automatic pipeline can segment straight from `crudo`, so a doc
        // past preprocessing counts even without `texto_preprocesado` (the
        // view falls back to the extracted text).
        return (
          !!(doc as any).texto_preprocesado ||
          PREPROCESSED_ESTADOS.includes(estado)
        );
      case "classified":
        // Backend flag wins; otherwise derive from the stored classification.
        return (
          log?.has_classification ??
          (!!doc.glaser_blocks?.length ||
            !!(doc as any).texto_clasificado ||
            // Classification may live only in `segmentos.tipo_dato_glaser`.
            !!segments[doc.id]?.some((s) => !!s.tipo_dato_glaser))
        );
      case "segmented":
        return hasSegments(doc);
      case "incidents":
        return (
          (log?.incidents_count ?? 0) > 0 ||
          INCIDENT_TERMINAL_ESTADOS.includes(estado)
        );
    }
  }

  /** Highest step index such that steps 0..i are ALL present.
   *  A gap stops progress — that is what makes inconsistencies visible. */
  function completedThrough(doc: Document): number {
    let last = 0;
    for (let i = 0; i < DOC_STEPS.length; i++) {
      if (!hasStep(doc, DOC_STEPS[i])) return i - 1;
      last = i;
    }
    return last;
  }

  /** Clamp the shared override to [0, completedThrough + 1]. */
  function clampedStepIndex(doc: Document): number {
    const through = completedThrough(doc);
    const maxIdx = Math.min(through + 1, DOC_STEPS.length - 1);
    const raw = globalStep ?? through;
    return Math.max(0, Math.min(raw, maxIdx));
  }

  /** Step currently shown for this interview (last run step by default). */
  function viewedStepOf(doc: Document): DocStepKey {
    return DOC_STEPS[clampedStepIndex(doc)];
  }

  /** True when the user moved past the last step that has data: the only
   *  place where the run button is allowed to appear. */
  function isOnEmptyStep(doc: Document): boolean {
    return clampedStepIndex(doc) === completedThrough(doc) + 1;
  }

  /** Editable text of one of the two plain-text steps. */
  function stepTextRaw(doc: Document, step: DocStepKey): string {
    if (step === "preprocessed")
      return (doc as any).texto_preprocesado || doc.texto_extraido || "";
    return (doc as any).texto_original || doc.texto_extraido || "";
  }

  /** Raw text of a text step, escaped for `dangerouslySetInnerHTML`. */
  function stepTextHtml(doc: Document, step: DocStepKey): string {
    const raw = stepTextRaw(doc, step);
    if (!raw)
      return `<span style="color:#484F58">${escapeHtml(t("project.noTextAvailable"))}</span>`;
    return escapeHtml(raw).replace(/\n/g, "<br>");
  }

  /** The only step whose text the editor owns: the LAST of the two text steps
   *  that has data. Editing the raw text after preprocessing would leave a
   *  second, stale copy behind, so the older one stays read-only. */
  function textEditStepOf(doc: Document): "original" | "preprocessed" {
    return hasStep(doc, "preprocessed") ? "preprocessed" : "original";
  }

  /** Why the editor may not open right now, or `null` when it may.
   *
   *  The editor belongs to the two steps that precede classification. Once the
   *  text is classified, `glaser_blocks` carries character offsets into this
   *  very string: editing underneath them would silently invalidate the
   *  classification, so the supported way back is the ↺ redo of that step. */
  function textEditBlockedReason(doc: Document): string | null {
    if (hasStep(doc, "classified"))
      return t("project.textEditLockedClassified");
    if (docRunning(doc)) return t("project.textEditLockedRunning");
    return null;
  }

  /** Highest step index reachable in the current view. Per-document chains are
   *  clamped to their own `completedThrough + 1`, so the global navigator must
   *  not promise a step that no card can actually display. */
  function globalStepMax(): number {
    const last = DOC_STEPS.length - 1;
    if (docs.length === 0) return last;
    return Math.max(
      ...docs.map((d) => Math.min(completedThrough(d) + 1, last)),
    );
  }

  /** Step index the global navigator points at. In auto mode it is the MOST
   *  advanced interview: then `<` and `>` never move a card against the arrow. */
  function globalStepBase(): number {
    const max = globalStepMax();
    const base =
      globalStep !== null
        ? globalStep
        : docs.length === 0
          ? 0
          : Math.max(...docs.map((d) => clampedStepIndex(d)));
    return Math.max(0, Math.min(base, max));
  }

  /** Move the viewed step of ALL interviews at once (panel-level navigator).
   *  Each card still clamps to its own chain, so a document that is behind
   *  lands on its first empty step — which is exactly where its run button is. */
  function stepNavAll(delta: number) {
    const next = Math.max(
      0,
      Math.min(globalStepBase() + delta, globalStepMax()),
    );
    setGlobalStep(next);
    const step = DOC_STEPS[next];
    if (step !== "classified" && step !== "segmented" && step !== "incidents")
      return;
    // Show the data: stepping through implies looking at it.
    docs.forEach((d) => {
      if (!segments[d.id]) loadSegments(d.id);
    });
  }

  /** Run the agent that produces a given step for one interview. */
  function runStep(doc: Document, step: DocStepKey) {
    if (step === "preprocessed") return handlePunctuate(doc.id);
    if (step === "classified") return handleClassify(doc.id);
    if (step === "segmented") return handleSegment(doc.id);
    if (step === "incidents") return handleExtractIncidents(doc.id);
    return undefined;
  }

  /** Erase the data produced by `step`, and implicitly everything derived from
   *  it: the chain is linear, so a single call walks the document back one
   *  layer. This is the ONLY place that spells out what "undo a step" means;
   *  the per-card ↺ (`handleRedoStep`) and the batch reset both go through it,
   *  so the two can never drift apart again. */
  async function eraseStep(doc: Document, step: DocStepKey) {
    if (step === "preprocessed") {
      // Wipes everything: back to `crudo`.
      return restoreDocumentOriginal(doc.id);
    }
    if (step === "classified") {
      // Default DELETE also strips the classification: back to `preprocesado`.
      return deleteDocumentSegments(doc.id);
    }
    if (step === "segmented") {
      // Keep the Glaser tags: back to `clasificado`.
      return deleteDocumentSegments(doc.id, { keepClassification: true });
    }
    if (step === "incidents") return deleteDocumentIncidents(doc.id);
    return undefined;
  }

  /** Erase this interview's last step, i.e. the redo of that step.
   *  Only one layer goes away: the erase itself cascades downstream. */
  async function handleRedoStep(doc: Document, step: DocStepKey) {
    if (step === "original") return; // the uploaded file is not regenerable
    // Never race a worker that is writing the data this erases.
    if (anyStepRunning()) return;
    try {
      await eraseStep(doc, step);
    } catch (e: any) {
      showErrorToast("Error al rehacer el paso: " + (e?.message || ""));
      return;
    }
    // Drop the caches that no longer reflect the server state.
    setSegments((prev) => {
      const n = { ...prev };
      delete n[doc.id];
      return n;
    });
    setRedoConfirmFor(null);
    setDocError((prev) => {
      const n = { ...prev };
      delete n[doc.id];
      return n;
    });
    await refreshAll();
    if (id)
      getPipelineLog(id)
        .then(setPipelineLog)
        .catch(() => {});
  }

  /** Inconsistency codes for one interview.
   *
   * Backend codes win; if the log lacks the field we derive the two cheap
   * ones client-side (segmented but unclassified, terminal without segments). */
  function docInconsistencies(doc: Document): string[] {
    const log = getDocLog(doc.id);
    if (Array.isArray(log?.inconsistencies))
      return log!.inconsistencies!.map(String);
    const out: string[] = [];
    const segmented = hasSegments(doc);
    const estado = String(doc.estado ?? "").trim();
    if (segmented && !hasStep(doc, "classified"))
      out.push("missing_classified");
    if (INCIDENT_TERMINAL_ESTADOS.includes(estado) && !segmented)
      out.push("missing_segmented");
    return out;
  }

  /** Segments of a document whose Glaser tag is missing or not `baseline_data`. */
  // ── Memo builder (legacy, replaced by agent-memos API) ──

  function buildMemosFromLog(
    log: PipelineLog | null,
    docsList: Document[],
  ): MemoEntry[] {
    if (!log) return [];
    const memos: MemoEntry[] = [];
    for (const dl of log.documents) {
      const doc = docsList.find((d) => d.id === dl.document_id);
      const docName = doc?.original_filename || dl.filename || dl.document_id;
      if (dl.steps.agents_done) {
        memos.push({
          id: `${dl.document_id}-agents`,
          family: "inductive_data",
          agentId: "A1-A3",
          isFinal: true,
          documentName: docName,
          timestamp: new Date().toLocaleTimeString(),
          data: {
            estado: dl.estado,
            segmentos: dl.segments_count,
            códigos: dl.codes_count,
            "texto extraído": dl.steps.text_extracted,
            segmentado: dl.steps.segmented,
            codificado: dl.steps.coded,
          },
        });
      }
      if (dl.segments_count > 0) {
        memos.push({
          id: `${dl.document_id}-segment`,
          family: "descriptive_data",
          agentId: "NLP",
          isFinal: true,
          documentName: docName,
          timestamp: new Date().toLocaleTimeString(),
          data: {
            "segmentos generados": dl.segments_count,
            "códigos asignados": dl.codes_count,
            "siguiente acción": dl.next_action,
          },
        });
      }
    }
    return memos;
  }

  function getEstadoBadge(doc: Document): {
    text: string;
    color: string;
    bg: string;
  } {
    const activeOp =
      runningOps[doc.id] ??
      (punctRunning === doc.id ? (runningOp.current?.op ?? "punctuate") : null);
    if (activeOp) {
      const op = activeOp;
      if (op === "classify") {
        return { text: "Clasificando…", color: "#3FB950", bg: "#3FB95022" };
      }
      if (op === "segment") {
        return { text: "Segmentando…", color: "#58A6FF", bg: "#58A6FF22" };
      }
      if (op === "extract") {
        return {
          text: t("project.statusExtracting"),
          color: "#D29922",
          bg: "#D2992222",
        };
      }
      return {
        text: t("project.statusPreprocessing"),
        color: "#A371F7",
        bg: "#A371F722",
      };
    }
    if (punctStatus[doc.id]?.startsWith("\u274C")) {
      return {
        text: t("project.statusError"),
        color: "#F85149",
        bg: "#F8514922",
      };
    }
    switch (doc.estado) {
      case "crudo":
        return {
          text: t("project.statusRaw"),
          color: "#8B949E",
          bg: "#8B949E22",
        };
      case "preprocesando":
        return {
          text: t("project.statusPreprocessing"),
          color: "#A371F7",
          bg: "#A371F722",
        };
      case "preprocesado":
        return {
          text: t("project.statusPreprocessed"),
          color: "#A371F7",
          bg: "#A371F722",
        };
      case "clasificando":
        return {
          text: t("project.statusClassifying"),
          color: "#3FB950",
          bg: "#3FB95022",
        };
      case "clasificado":
        return {
          text: t("project.statusClassified"),
          color: "#3FB950",
          bg: "#3FB95022",
        };
      case "segmentando":
        return {
          text: t("project.statusSegmenting"),
          color: "#58A6FF",
          bg: "#58A6FF22",
        };
      case "segmentado":
        return {
          text: t("project.statusSegmented"),
          color: "#58A6FF",
          bg: "#58A6FF22",
        };
      case "procesando":
        return {
          text: t("project.statusExtracting"),
          color: "#D29922",
          bg: "#D2992222",
        };
      case "extrayendo":
        return {
          text: t("project.statusExtracting"),
          color: "#D29922",
          bg: "#D2992222",
        };
      case "incidentes_extraidos":
        return {
          text: t("project.statusIncidentsExtracted"),
          color: "#D29922",
          bg: "#D2992222",
        };
      case "procesado":
        return {
          text: t("project.statusIncidentsExtracted"),
          color: "#D29922",
          bg: "#D2992222",
        };
      case "codificando":
        return {
          text: t("project.statusCoding"),
          color: "#A371F7",
          bg: "#A371F722",
        };
      case "codificado":
        return {
          text: t("project.statusCoded"),
          color: "#3FB950",
          bg: "#3FB95022",
        };
      case "listo":
        return {
          text: t("project.statusReady"),
          color: "#3FB950",
          bg: "#3FB95022",
        };
      case "resumiendo":
        return {
          text: t("project.statusSummarizing"),
          color: "#8B949E",
          bg: "#8B949E22",
        };
      case "resumido":
        return {
          text: t("project.statusSummarized"),
          color: "#8B949E",
          bg: "#8B949E22",
        };
      case "sintetizado":
        return {
          text: t("project.statusSynthesized"),
          color: "#3FB950",
          bg: "#3FB95022",
        };
      case "error":
        return {
          text: t("project.statusError"),
          color: "#F85149",
          bg: "#F8514922",
        };
      default:
        return {
          text: doc.estado || t("project.statusRaw"),
          color: "#8B949E",
          bg: "#8B949E22",
        };
    }
  }

  if (!project)
    return (
      <p style={{ padding: 40, color: "#8B949E" }}>{t("project.loading")}</p>
    );

  const hasCats = cats.length > 0;

  // ── Chain inconsistencies per interview (classify-first) ──
  // Driven by the log's `inconsistencies` codes, falling back to a local
  // derivation when the field is absent. Grouped by reason so the banner lists
  // every affected interview next to the step it is missing.
  const inconsistentDocs = docs
    .map((doc) => ({ doc, codes: docInconsistencies(doc) }))
    .filter((x) => x.codes.length > 0);
  // Known codes first (stable order), then any unexpected code the backend may
  // still report — dropping those would hide an inconsistency we cannot label.
  const inconsistencyCodes = Array.from(
    new Set([
      ...Object.keys(INCONSISTENCY_LABEL_KEYS),
      ...inconsistentDocs.flatMap((x) => x.codes),
    ]),
  );
  const inconsistencyGroups = inconsistencyCodes
    .map((code) => ({
      code,
      docs: inconsistentDocs
        .filter((x) => x.codes.includes(code))
        .map((x) => x.doc),
    }))
    .filter((group) => group.docs.length > 0);

  // El gate de codificación abierta está disponible en cuanto hay documentos
  // procesados y todavía nadie fijó el concern principal.
  const ocHitlReady =
    !!ocHitl &&
    !ocHitl.chosen_concern &&
    (ocHitl.total_docs ?? 0) > 0 &&
    (ocHitl.docs_processed ?? 0) > 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row-reverse",
        background: "#0D1117",
        minHeight: "100vh",
        color: "#E6EDF3",
      }}
    >
      {/* ── Left: Main Content ── */}
      <div style={{ flex: 1, minWidth: 0, padding: "0 24px 40px" }}>
        {/* ── Navbar ────────────────────────────────── */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "8px 24px",
            background: "#161B22",
            borderBottom: "1px solid #21262D",
            margin: "0 -24px 20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <Link
              to="/projects"
              style={{ color: "#58A6FF", fontSize: 13, textDecoration: "none" }}
            >
              ← {t("project.backToProjects")}
            </Link>
            <span style={{ fontSize: 15, fontWeight: 600 }}>
              {project.nombre}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={() => setOcHitlOpen(true)}
              title="Decisión HITL de codificación abierta: concern principal, población y categorías centrales"
              style={{
                ...btnSmall,
                fontSize: 11,
                border: `1px solid ${ocHitlReady ? "#D29922" : "#21262D"}`,
                color: ocHitlReady ? "#D29922" : "#8B949E",
              }}
            >
              {ocHitlReady ? "◆ HITL" : "◇ HITL"}
            </button>
            <span
              style={{
                fontSize: 11,
                padding: "2px 8px",
                borderRadius: 999,
                background: "#8B949E22",
                color: "#8B949E",
              }}
            >
              {docs.length} docs · {cats.length} cats
            </span>

            <span style={{ fontSize: 11, color: "#8B949E" }}>{userName}</span>
            <button
              onClick={handleLogout}
              style={{ ...btnSmall, fontSize: 11 }}
            >
              {t("project.signOut")}
            </button>
          </div>
        </div>

        {/* ── HITL Decision Banner ── */}
        {hitlPending.length > 0 && (
          <div
            style={{
              padding: "10px 16px",
              marginBottom: 12,
              borderRadius: 8,
              background: "#D2992218",
              border: "1px solid #D2992244",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: 13, color: "#D29922" }}>
              🛑 {t("project.decisionRequired")}{" "}
              <strong>
                {hitlPending[0].gate_name === "pattern_of_interest"
                  ? t("project.mainConcern")
                  : hitlPending[0].gate_name === "core_category"
                    ? t("project.coreCategory")
                    : hitlPending[0].gate_name === "selective_reduction"
                      ? t("project.selectiveReduction")
                      : hitlPending[0].gate_name === "core_saturation"
                        ? t("project.coreSaturation")
                        : hitlPending[0].gate_name === "database_a"
                          ? t("project.databaseANodes")
                          : hitlPending[0].gate_name === "database_b"
                            ? t("project.databaseBEdges")
                            : hitlPending[0].gate_name}
              </strong>
            </span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                onClick={() => setShowHITLModal(true)}
                style={{
                  padding: "6px 16px",
                  borderRadius: 6,
                  border: "none",
                  background: "#D29922",
                  color: "#0D1117",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t("project.resolveButton")}
              </button>
              <button
                onClick={() => setSidebarViewMode("hitl")}
                title={t("hitlCrud.title")}
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "1px solid #D2992244",
                  background: "transparent",
                  color: "#D29922",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                ⚖
              </button>
            </div>
          </div>
        )}

        {/* ── Open Coding HITL Banner ── */}
        {ocHitlReady && hitlPending.length === 0 && (
          <div
            style={{
              padding: "10px 16px",
              marginBottom: 12,
              borderRadius: 8,
              background: "#A371F718",
              border: "1px solid #A371F744",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: 13, color: "#A371F7" }}>
              ◆ Decisión HITL pendiente: concern principal, población y
              categorías centrales.
            </span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                onClick={() => setOcHitlOpen(true)}
                style={{
                  padding: "6px 16px",
                  borderRadius: 6,
                  border: "none",
                  background: "#A371F7",
                  color: "#0D1117",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Revisar
              </button>
              <button
                onClick={() => setSidebarViewMode("hitl")}
                title={t("hitlCrud.title")}
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "1px solid #A371F744",
                  background: "transparent",
                  color: "#A371F7",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                ⚖
              </button>
            </div>
          </div>
        )}

        {/* ── Stale User Entities Warning (FIX 4) ── */}
        {staleWarning && staleWarning.count > 0 && (
          <div
            style={{
              padding: "10px 16px",
              marginBottom: 12,
              borderRadius: 8,
              background: "#D2992218",
              border: "1px solid #D2992244",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: 13, color: "#D29922" }}>
              ⚠️{" "}
              {t("project.staleEntitiesWarning", {
                count: staleWarning.count,
                stages: staleWarning.affected_stages.join(", "),
              })}
            </span>
            <button
              onClick={() => setStaleWarning(null)}
              style={{ ...btnSmall, color: "#D29922" }}
            >
              {t("project.understoodButton")}
            </button>
          </div>
        )}

        {/* ── Playground Ready Banner ── */}
        {pipelineLog?.summary?.project_state === "playground_ready" &&
          hitlPending.length === 0 && (
            <div
              style={{
                padding: "10px 16px",
                marginBottom: 12,
                borderRadius: 8,
                background: "#2EA04318",
                border: "1px solid #2EA04344",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span style={{ fontSize: 13, color: "#2EA043" }}>
                {t("project.playgroundReady")}
              </span>
              <Link
                to={`/projects/${id}/theory`}
                style={{
                  padding: "6px 16px",
                  borderRadius: 6,
                  border: "none",
                  background: "#2EA043",
                  color: "#0D1117",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  textDecoration: "none",
                }}
              >
                {t("project.enterButton")}
              </Link>
            </div>
          )}

        {/* ── UNIFIED HEADER ── */}
        <div
          style={{
            marginBottom: 16,
            padding: "14px 16px",
            background: "#161B22",
            borderRadius: 10,
            border: "1px solid #21262D",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          {/* Row 1: project meta + view switch + log toggle */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <span style={{ fontSize: 12, color: "#8B949E" }}>
                {project.ruta_de_codificacion} · {project.estado}
              </span>
              {/* Status pills inline */}
              {docsNeedSegment > 0 && (
                <span
                  style={{
                    fontSize: 10,
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: "#D2992222",
                    color: "#D29922",
                    border: "1px solid #D2992233",
                  }}
                >
                  ✂️ {docsNeedSegment}{" "}
                  {t("project.toSegmentCount").replace(
                    "{n}",
                    String(docsNeedSegment),
                  )}
                </span>
              )}
              {docsNeedAgents > 0 && (
                <span
                  style={{
                    fontSize: 10,
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: "#A371F722",
                    color: "#A371F7",
                    border: "1px solid #A371F733",
                  }}
                >
                  🧠 {docsNeedAgents}{" "}
                  {t("project.toAgentsCount").replace(
                    "{n}",
                    String(docsNeedAgents),
                  )}
                </span>
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {/* Global view switch */}

              {/* Delete all segments */}
              <button
                onClick={async () => {
                  if (
                    !(await safeConfirm(t("project.deleteAllSegmentsConfirm")))
                  )
                    return;
                  const auth = `Bearer ${localStorage.getItem("access_token")}`;
                  await fetch(`/api/v1/documents/project/${id}/segments`, {
                    method: "DELETE",
                    headers: { Authorization: auth },
                  });
                  refreshAll();
                  setSegments({});
                  getPipelineLog(id!)
                    .then(setPipelineLog)
                    .catch(() => {});
                }}
                title={t("project.deleteAllSegmentsTitle")}
                style={{
                  padding: "3px 8px",
                  borderRadius: 6,
                  border: "1px solid #F8514944",
                  background: "transparent",
                  color: "#F85149",
                  fontSize: 10,
                  cursor: "pointer",
                  opacity: 0.7,
                }}
              >
                {t("project.deleteSegmentsButton")}
              </button>

              {/* Playground link */}
              <Link
                to={`/projects/${id}/theory`}
                onClick={(e) => {
                  if (!playgroundReady) e.preventDefault();
                }}
                title={
                  playgroundReady
                    ? t("project.exploreModelTitle")
                    : t("project.needPipelineFirstTitle")
                }
                style={{
                  padding: "3px 10px",
                  borderRadius: 6,
                  border: "1px solid #21262D",
                  background: playgroundReady ? "#3FB95022" : "#D2992222",
                  color: playgroundReady ? "#3FB950" : "#D29922",
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: playgroundReady ? "pointer" : "not-allowed",
                  textDecoration: "none",
                  opacity: playgroundReady ? 1 : 0.6,
                }}
              >
                {playgroundReady
                  ? t("project.goPlayground")
                  : t("project.playgroundLockedShort")}
              </Link>

              {/* Project Config button */}
              <button
                onClick={() => setShowConfigPanel(true)}
                title={t("project.configTitle")}
                style={{
                  padding: "3px 10px",
                  borderRadius: 6,
                  border: "1px solid #A371F744",
                  background: "#A371F718",
                  color: "#A371F7",
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t("project.configButton")}
              </button>

              {/* Status pills inline */}
              {/* Log toggle */}
            </div>
          </div>

          {/* ── Population Configuration ──────────────── */}
          {(project?.supuesto_poblacional ||
            project?.population_assumption) && (
            <div
              style={{
                marginBottom: 20,
                padding: "14px 16px",
                background: "#161B22",
                borderRadius: 10,
                border: "1px solid #21262D",
              }}
            >
              <div
                onClick={() => setPopConfigOpen(!popConfigOpen)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  cursor: "pointer",
                  userSelect: "none",
                }}
              >
                <span
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: "#E6EDF3",
                  }}
                >
                  {t("project.populationConfig")}
                </span>
                <span style={{ color: "#8B949E", fontSize: 12 }}>
                  {popConfigOpen ? "▲" : "▼"}
                </span>
              </div>
              {popConfigOpen && (
                <div style={{ marginTop: 14 }}>
                  {/* Original population description */}
                  {project.supuesto_poblacional && (
                    <div style={{ marginBottom: 12 }}>
                      <div
                        style={{
                          fontSize: 11,
                          color: "#8B949E",
                          marginBottom: 4,
                          textTransform: "uppercase",
                          letterSpacing: "0.5px",
                        }}
                      >
                        {t("project.populationOriginal")}
                      </div>
                      <div
                        style={{
                          fontSize: 13,
                          color: "#C9D1D9",
                          padding: "8px 12px",
                          background: "#0D1117",
                          borderRadius: 6,
                          border: "1px solid #30363D",
                          lineHeight: 1.5,
                        }}
                      >
                        {project.supuesto_poblacional}
                      </div>
                    </div>
                  )}
                  {/* Generalized population */}
                  {(() => {
                    const pa = project.population_assumption;
                    const genPop =
                      pa && typeof pa === "object"
                        ? String(
                            (pa as any).generalized_population ||
                              (pa as any).population_description ||
                              "",
                          )
                        : "";
                    const hasGenPop = !!(
                      pa &&
                      typeof pa === "object" &&
                      (pa as any).generalized_population
                    );

                    return (
                      <>
                        <div style={{ marginBottom: 12 }}>
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              marginBottom: 4,
                            }}
                          >
                            <span
                              style={{
                                fontSize: 11,
                                color: "#8B949E",
                                textTransform: "uppercase",
                                letterSpacing: "0.5px",
                              }}
                            >
                              {t("project.populationGeneralized")}
                            </span>
                            {hasGenPop && !editingPop && (
                              <button
                                onClick={() => handleStartEditPop(genPop)}
                                style={{
                                  padding: "2px 10px",
                                  borderRadius: 4,
                                  border: "1px solid #30363D",
                                  background: "#21262D",
                                  color: "#8B949E",
                                  fontSize: 11,
                                  cursor: "pointer",
                                }}
                              >
                                {t("project.populationEdit")}
                              </button>
                            )}
                          </div>

                          {editingPop ? (
                            <div style={{ display: "flex", gap: 8 }}>
                              <input
                                type="text"
                                value={popEditValue}
                                onChange={(e) =>
                                  setPopEditValue(e.target.value)
                                }
                                style={{
                                  flex: 1,
                                  padding: "8px 12px",
                                  borderRadius: 6,
                                  background: "#0D1117",
                                  border: "1px solid #58A6FF",
                                  color: "#E6EDF3",
                                  fontSize: 13,
                                  fontFamily: "monospace",
                                }}
                              />
                              <button
                                onClick={handleSavePop}
                                style={{
                                  padding: "6px 14px",
                                  borderRadius: 6,
                                  border: "none",
                                  background: "#238636",
                                  color: "#FFF",
                                  fontSize: 12,
                                  fontWeight: 600,
                                  cursor: "pointer",
                                }}
                              >
                                {t("project.populationSave")}
                              </button>
                              <button
                                onClick={() => setEditingPop(false)}
                                style={{
                                  padding: "6px 14px",
                                  borderRadius: 6,
                                  border: "1px solid #30363D",
                                  background: "#21262D",
                                  color: "#8B949E",
                                  fontSize: 12,
                                  cursor: "pointer",
                                }}
                              >
                                {t("common.cancel")}
                              </button>
                            </div>
                          ) : hasGenPop ? (
                            <div
                              style={{
                                fontSize: 14,
                                fontWeight: 600,
                                color: "#A371F7",
                                padding: "8px 12px",
                                background: "#A371F712",
                                borderRadius: 6,
                                border: "1px solid #A371F733",
                                lineHeight: 1.5,
                              }}
                            >
                              {genPop}
                            </div>
                          ) : (
                            <div
                              style={{
                                padding: "10px 12px",
                                background: "#D2992218",
                                borderRadius: 6,
                                border: "1px solid #D2992233",
                                fontSize: 12,
                                color: "#D29922",
                              }}
                            >
                              No generalization yet.
                            </div>
                          )}
                        </div>

                        {/* Generate button */}
                        {!hasGenPop && project.supuesto_poblacional && (
                          <div style={{ marginBottom: 12 }}>
                            <button
                              onClick={handleGeneratePop}
                              disabled={popGenerating}
                              style={{
                                padding: "6px 16px",
                                borderRadius: 6,
                                border: "none",
                                background: popGenerating
                                  ? "#30363D"
                                  : "#A371F7",
                                color: popGenerating ? "#484F58" : "#FFF",
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: popGenerating
                                  ? "not-allowed"
                                  : "pointer",
                              }}
                            >
                              {popGenerating
                                ? t("project.populationGenerating")
                                : t("project.populationGenerate")}
                            </button>
                          </div>
                        )}

                        {/* Frame details & confidence */}
                        {hasGenPop && pa && typeof pa === "object" && (
                          <>
                            <div
                              style={{
                                display: "flex",
                                gap: 12,
                                marginBottom: 10,
                              }}
                            >
                              <div
                                style={{
                                  flex: 1,
                                  padding: "8px 12px",
                                  background: "#0D1117",
                                  borderRadius: 6,
                                  border: "1px solid #30363D",
                                }}
                              >
                                <span
                                  style={{
                                    fontSize: 10,
                                    color: "#8B949E",
                                    display: "block",
                                    marginBottom: 2,
                                    textTransform: "uppercase",
                                  }}
                                >
                                  {t("project.populationSpatialFrame")}
                                </span>
                                <span
                                  style={{
                                    fontSize: 13,
                                    color: "#E6EDF3",
                                    fontWeight: 600,
                                  }}
                                >
                                  {spatialFrameLabel(
                                    String((pa as any).spatial_frame || ""),
                                  )}
                                </span>
                              </div>
                              <div
                                style={{
                                  flex: 1,
                                  padding: "8px 12px",
                                  background: "#0D1117",
                                  borderRadius: 6,
                                  border: "1px solid #30363D",
                                }}
                              >
                                <span
                                  style={{
                                    fontSize: 10,
                                    color: "#8B949E",
                                    display: "block",
                                    marginBottom: 2,
                                    textTransform: "uppercase",
                                  }}
                                >
                                  {t("project.populationTemporalFrame")}
                                </span>
                                <span
                                  style={{
                                    fontSize: 13,
                                    color: "#E6EDF3",
                                    fontWeight: 600,
                                  }}
                                >
                                  {temporalFrameLabel(
                                    String((pa as any).temporal_frame || ""),
                                  )}
                                </span>
                              </div>
                            </div>

                            {/* Confidence bar */}
                            {(() => {
                              const conf = Number(
                                (pa as any).generalizer_confidence,
                              );
                              if (isNaN(conf)) return null;
                              const pct = Math.round(conf * 100);
                              return (
                                <div style={{ marginBottom: 10 }}>
                                  <div
                                    style={{
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "space-between",
                                      marginBottom: 4,
                                    }}
                                  >
                                    <span
                                      style={{
                                        fontSize: 10,
                                        color: "#8B949E",
                                        textTransform: "uppercase",
                                      }}
                                    >
                                      {t("project.populationConfidence")}
                                    </span>
                                    <span
                                      style={{
                                        fontSize: 12,
                                        fontWeight: 600,
                                        color:
                                          pct >= 80
                                            ? "#3FB950"
                                            : pct >= 50
                                              ? "#D29922"
                                              : "#F85149",
                                      }}
                                    >
                                      {pct}%
                                    </span>
                                  </div>
                                  <div
                                    style={{
                                      width: "100%",
                                      height: 6,
                                      borderRadius: 3,
                                      background: "#21262D",
                                      overflow: "hidden",
                                    }}
                                  >
                                    <div
                                      style={{
                                        width: `${pct}%`,
                                        height: "100%",
                                        borderRadius: 3,
                                        background:
                                          pct >= 80
                                            ? "#3FB950"
                                            : pct >= 50
                                              ? "#D29922"
                                              : "#F85149",
                                        transition: "width 0.3s ease",
                                      }}
                                    />
                                  </div>
                                </div>
                              );
                            })()}

                            {/* Rationale */}
                            {(pa as any).generalizer_rationale && (
                              <div style={{ marginBottom: 4 }}>
                                <span
                                  style={{
                                    fontSize: 10,
                                    color: "#8B949E",
                                    display: "block",
                                    marginBottom: 4,
                                    textTransform: "uppercase",
                                  }}
                                >
                                  {t("project.populationRationale")}
                                </span>
                                <div
                                  style={{
                                    fontSize: 12,
                                    color: "#8B949E",
                                    padding: "8px 12px",
                                    background: "#0D1117",
                                    borderRadius: 6,
                                    border: "1px solid #30363D",
                                    lineHeight: 1.6,
                                    fontStyle: "italic",
                                  }}
                                >
                                  {(pa as any).generalizer_rationale}
                                </div>
                              </div>
                            )}
                          </>
                        )}
                      </>
                    );
                  })()}
                </div>
              )}
            </div>
          )}

          {/* ── Experimental Mode ─────────────────────── */}
          <div
            style={{
              marginBottom: 20,
              padding: "14px 16px",
              background: "#161B22",
              borderRadius: 10,
              border: "1px solid #21262D",
            }}
          >
            <div
              onClick={() => setExpModeOpen(!expModeOpen)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
                userSelect: "none",
              }}
            >
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "#E6EDF3",
                }}
              >
                {t("project.experimentalMode")}
              </span>
              <span style={{ color: "#8B949E", fontSize: 12 }}>
                {expModeOpen ? "▲" : "▼"}
              </span>
            </div>
            {expModeOpen && (
              <div style={{ marginTop: 14 }}>
                {/* Current pattern type display */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 14,
                  }}
                >
                  <span style={{ fontSize: 11, color: "#8B949E" }}>
                    {t("project.experimentalModeCurrent")}:
                  </span>
                  <span
                    style={{
                      padding: "3px 10px",
                      borderRadius: 999,
                      background: "#A371F722",
                      color: "#A371F7",
                      fontSize: 11,
                      fontWeight: 600,
                      border: "1px solid #A371F733",
                    }}
                  >
                    {(() => {
                      const oos = project?.object_of_study || "concern";
                      const label = t(`config.${oos}`);
                      let suffix = "";
                      if (oos === "custom") {
                        const pa = project?.population_assumption;
                        const cl =
                          pa && typeof pa === "object" && "custom_label" in pa
                            ? (pa as any).custom_label || "custom"
                            : "custom";
                        suffix = t("projects.patternSuffix.custom", {
                          label: cl,
                        });
                      } else {
                        suffix = t(`projects.patternSuffix.${oos}`);
                      }
                      return label + suffix;
                    })()}
                  </span>
                </div>

                {/* Description */}
                <p
                  style={{
                    fontSize: 12,
                    color: "#8B949E",
                    margin: "0 0 14px 0",
                    lineHeight: 1.5,
                  }}
                >
                  {t("project.experimentalModeDesc")}
                </p>

                {/* Dropdown */}
                <div style={{ marginBottom: 10 }}>
                  <select
                    value={selectedOOS}
                    onChange={(e) => setSelectedOOS(e.target.value)}
                    style={{
                      padding: "6px 12px",
                      borderRadius: 6,
                      background: "#0D1117",
                      border: "1px solid #30363D",
                      color: "#E6EDF3",
                      fontSize: 14,
                      cursor: "pointer",
                      minWidth: 200,
                    }}
                  >
                    <option value="concern">{t("config.concern")}</option>
                    <option value="emotion">{t("config.emotion")}</option>
                    <option value="behavior">{t("config.behavior")}</option>
                    <option value="discourse">{t("config.discourse")}</option>
                    <option value="identity">{t("config.identity")}</option>
                    <option value="custom">{t("config.custom")}</option>
                  </select>
                </div>

                {/* Custom label input */}
                {selectedOOS === "custom" && (
                  <div style={{ marginBottom: 10 }}>
                    <input
                      type="text"
                      value={customLabel}
                      onChange={(e) => setCustomLabel(e.target.value)}
                      placeholder={t("projects.customLabelPlaceholder")}
                      style={{
                        width: "100%",
                        padding: "6px 12px",
                        borderRadius: 6,
                        background: "#0D1117",
                        border: "1px solid #30363D",
                        color: "#E6EDF3",
                        fontSize: 14,
                        fontFamily: "monospace",
                      }}
                    />
                  </div>
                )}

                {/* Warning */}
                <div
                  style={{
                    padding: "10px 14px",
                    borderRadius: 6,
                    background: "#D2992218",
                    border: "1px solid #D2992233",
                    marginBottom: 12,
                  }}
                >
                  <span style={{ fontSize: 12, color: "#D29922" }}>
                    ⚠️ {t("project.experimentalModeWarning")}
                  </span>
                </div>

                {/* Switch button */}
                <button
                  onClick={handleSwitchPattern}
                  disabled={
                    switchingPattern || selectedOOS === project?.object_of_study
                  }
                  style={{
                    padding: "8px 20px",
                    borderRadius: 6,
                    border: "none",
                    background:
                      switchingPattern ||
                      selectedOOS === project?.object_of_study
                        ? "#30363D"
                        : "#D29922",
                    color:
                      switchingPattern ||
                      selectedOOS === project?.object_of_study
                        ? "#484F58"
                        : "#0D1117",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor:
                      switchingPattern ||
                      selectedOOS === project?.object_of_study
                        ? "not-allowed"
                        : "pointer",
                  }}
                >
                  {switchingPattern
                    ? `${t("common.saving")}…`
                    : t("project.experimentalModeSwitch")}
                </button>
              </div>
            )}
          </div>

          {/* ── Upload ─────────────────────────────────── */}
          <div style={{ marginBottom: 20 }}>
            {docs.length === 0 && (
              <div
                style={{
                  fontSize: 12,
                  color: "#D29922",
                  marginBottom: 12,
                  padding: "8px 12px",
                  background: "#D2992218",
                  borderRadius: 6,
                  border: "1px solid #D2992233",
                  lineHeight: 1.5,
                }}
              >
                ⚠️ {t("project.noDocsMessage")}
              </div>
            )}
            <label
              style={{
                display: "inline-block",
                padding: "8px 20px",
                borderRadius: 6,
                background: "#1C2333",
                border: "1px dashed #30363D",
                color: "#E6EDF3",
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              {t("project.uploadDocument")}
              <input
                type="file"
                accept=".pdf,.txt,.docx"
                multiple
                style={{ display: "none" }}
                onChange={handleUpload}
              />
            </label>
          </div>

          {/* ── Documents ──────────────────────────────── */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 12,
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button
                onClick={() => setDocsOpen((open) => !open)}
                aria-expanded={docsOpen}
                title={
                  docsOpen
                    ? t("project.docsCollapseTitle")
                    : t("project.docsExpandTitle")
                }
                style={{
                  ...btnSmall,
                  padding: "2px 7px",
                  lineHeight: 1,
                  background: "transparent",
                  border: "0px solid #30363D",
                }}
              >
                {docsOpen ? "\u25BE" : "\u25B8"}
              </button>

              {/* ── Global step navigator ──
                  ONE control for every interview in view: `<` / `>` move
                  the viewed step of all cards at once. Each card clamps to
                  its own chain, so the document that is behind stops on
                  its first empty step (where its run button lives). */}
              {/* Only without a selection: with one, the panel works on the
                  ticked documents instead of moving everybody. */}
              {docs.length > 0 &&
                (() => {
                  const base = globalStepBase();
                  const step = DOC_STEPS[base];
                  const color = STEP_COLORS[step];
                  const canPrev = base > 0;
                  const canNext = base < globalStepMax();
                  const navStyle: React.CSSProperties = {
                    ...btnSmall,
                    padding: "2px 7px",
                    lineHeight: 1,
                    background: "transparent",
                    border: "1px solid #30363D",
                  };
                  return (
                    <>
                      <button
                        onClick={() => stepNavAll(-1)}
                        disabled={!canPrev}
                        title={
                          canPrev
                            ? t("project.stepNavAllPrev")
                            : t("project.stepAtFirst")
                        }
                        style={{
                          ...navStyle,
                          color: canPrev ? "#E6EDF3" : "#484F58",
                          cursor: canPrev ? "pointer" : "not-allowed",
                        }}
                      >
                        {"<"}
                      </button>
                      <span
                        title={t("project.stepNavAllTitle", {
                          step: stepLabel(step),
                          index: base + 1,
                          total: DOC_STEPS.length,
                          count: docs.length,
                        })}
                        style={{
                          fontSize: 10,
                          padding: "2px 8px",
                          borderRadius: 999,
                          background: `${color}22`,
                          color,
                          border: `1px solid ${color}44`,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {STEP_ICONS[step]} {stepLabel(step)}
                      </span>
                      <button
                        onClick={() => stepNavAll(1)}
                        disabled={!canNext}
                        title={
                          canNext
                            ? t("project.stepNavAllNext")
                            : t("project.stepAtLast")
                        }
                        style={{
                          ...navStyle,
                          color: canNext ? "#E6EDF3" : "#484F58",
                          cursor: canNext ? "pointer" : "not-allowed",
                        }}
                      >
                        {">"}
                      </button>
                    </>
                  );
                })()}

              {/* {docs.length > 0 && (
                <input
                  type="checkbox"
                  checked={isFullSelection()}
                  ref={(el) => {
                    if (el)
                      el.indeterminate =
                        selectedDocs.size > 0 && !isFullSelection();
                  }}
                  onChange={(e) =>
                    setSelectedDocs(
                      e.target.checked
                        ? new Set(docs.map((d) => d.id))
                        : new Set(),
                    )
                  }
                  title={t("project.selectAllDocs")}
                  aria-label={t("project.selectAllDocs")}
                  style={{
                    margin: 0,
                    cursor: "pointer",
                    accentColor: "#A371F7",
                  }}
                />
              )}
              <h3 style={{ margin: 0 }}>
                {t("project.documentsHeading", { count: docs.length })}
              </h3> */}
            </div>
            <div
              style={{
                display: "flex",
                gap: 6,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              {docs.length > 0 && (
                <>
                  {selectedDocs.size > 0 && (
                    <>
                      {(!anyDocProcessing() || resetRun !== null) &&
                        (() => {
                          // The navigator can sit on a step nobody has produced
                          // yet (the panel moved past every card's last step).
                          // Undo there would silently reach back into the
                          // previous step, so the header offers only the run
                          // button. Never applies to its own progress counter.
                          if (
                            resetRun === null &&
                            !batchTargets().some((d) =>
                              hasStep(d, DOC_STEPS[globalStepBase()]),
                            )
                          )
                            return null;
                          // Only documents with a completed step change; the
                          // rest would be skipped, so they do not count here.
                          const undoable = batchTargets().filter(
                            (d) => completedThrough(d) > 0,
                          ).length;
                          // Every target is still `crudo`: undo would do nothing.
                          if (undoable === 0 && resetRun === null) return null;
                          return (
                            <button
                              onClick={handleResetLastStep}
                              disabled={docsBusy}
                              style={{
                                background: "#D2992218",
                                border: "1px solid #D2992233",
                                borderRadius: 6,
                                color: "#D29922",
                                fontSize: 11,
                                fontWeight: 600,
                                padding: "3px 10px",
                                cursor: docsBusy ? "not-allowed" : "pointer",
                                opacity: docsBusy ? 0.6 : 1,
                              }}
                              title={t(
                                isFullSelection()
                                  ? "project.resetDocsTitle"
                                  : "project.resetSelectedTitle",
                              )}
                            >
                              {resetRun
                                ? `${resetRun.done}/${resetRun.total}`
                                : `${t("project.resetDocsButton")} (${undoable})`}
                            </button>
                          );
                        })()}
                      {(!anyDocProcessing() || docsBusy) && (
                        <button
                          onClick={handleDeleteSelected}
                          disabled={docsBusy}
                          style={{
                            background: "#F8514918",
                            border: "1px solid #F8514933",
                            borderRadius: 6,
                            color: "#F85149",
                            fontSize: 11,
                            fontWeight: 600,
                            padding: "3px 10px",
                            cursor: docsBusy ? "not-allowed" : "pointer",
                            opacity: docsBusy ? 0.6 : 1,
                          }}
                          title={t(
                            isFullSelection()
                              ? "project.deleteAllDocsTitle"
                              : "project.deleteSelectedTitle",
                          )}
                        >
                          {`${t("project.deleteAllDocsButton")} (${selectedDocs.size})`}
                        </button>
                      )}
                    </>
                  )}
                </>
              )}
              {/* Always visible: runs the viewed step on the targets that
                  sit exactly on it, one after another. */}
              {(() => {
                const step = DOC_STEPS[globalStepBase()];
                const color = STEP_COLORS[step];
                // Documents the batch would really fire on. In auto mode
                // (`globalStep === null`) every card clamps to its own last
                // step with data, so none of them sits on an empty step and
                // this is 0 until the navigator moves the view onto one.
                const runnableCount =
                  batchRun === null ? runTargets().length : 0;
                const canRun = runnableCount > 0;
                return (
                  <button
                    onClick={handleRunOnTargets}
                    disabled={!canRun}
                    title={
                      runnableCount > 0
                        ? t("project.stepRun", { step: stepLabel(step) })
                        : t("project.stepRunNone", { step: stepLabel(step) })
                    }
                    style={{
                      ...btnSmall,
                      background: canRun ? color : "#30363D",
                      color: canRun ? "#FFF" : "#484F58",
                      border: "none",
                      cursor: canRun ? "pointer" : "not-allowed",
                    }}
                  >
                    {batchRun
                      ? `${batchRun.done}/${batchRun.total}`
                      : runnableCount > 0
                        ? `▶ ${t("project.stepRunBatch", {
                            count: runnableCount,
                          })}`
                        : `▶ ${t("project.stepRun", {
                            step: stepLabel(step),
                          })}`}
                  </button>
                );
              })()}
            </div>
          </div>

          {/* ── Project-level inconsistency warning ──
              One line per missing step, listing the interviews affected. */}
          {inconsistencyGroups.length > 0 && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                borderRadius: 6,
                background: "#D2992218",
                border: "1px solid #D2992233",
                color: "#D29922",
                fontSize: 12,
                lineHeight: 1.6,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                ⚠️ {t("project.stepInconsistent")}
              </div>
              {inconsistencyGroups.map((group) => (
                <div key={group.code}>
                  <strong>
                    {t(INCONSISTENCY_LABEL_KEYS[group.code] ?? group.code)}:
                  </strong>{" "}
                  {group.docs.map((doc) => doc.original_filename).join(", ")}
                </div>
              ))}
            </div>
          )}

          <ul
            style={{
              listStyle: "none",
              padding: 0,
              display: docsOpen ? undefined : "none",
            }}
          >
            {docs.map((d) => {
              return (
                <li
                  key={d.id}
                  draggable
                  onDragStart={(e) => {
                    dragDoc.current = d.id;
                    (e.target as HTMLElement).style.opacity = "0.5";
                  }}
                  onDragEnd={(e) => {
                    dragDoc.current = null;
                    (e.target as HTMLElement).style.opacity = "1";
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    (e.target as HTMLElement).style.borderTop =
                      "2px solid #A371F7";
                  }}
                  onDragLeave={(e) => {
                    (e.target as HTMLElement).style.borderTop = "";
                  }}
                  onDrop={async (e) => {
                    e.preventDefault();
                    (e.target as HTMLElement).style.borderTop = "";
                    (e.target as HTMLElement).style.opacity = "1";
                    const fromId = dragDoc.current;
                    if (!fromId || fromId === d.id) return;
                    const fromIdx = docs.findIndex((x) => x.id === fromId);
                    const toIdx = docs.findIndex((x) => x.id === d.id);
                    if (fromIdx === -1 || toIdx === -1) return;
                    const reordered = [...docs];
                    const [moved] = reordered.splice(fromIdx, 1);
                    reordered.splice(toIdx, 0, moved);
                    setDocs(reordered);
                    // Save using reordered array, not stale state
                    const order = reordered.map((d, i) => ({
                      id: d.id,
                      sort_order: i + 1,
                    }));
                    fetch(`/api/v1/documents/project/${id}/reorder`, {
                      method: "POST",
                      headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                      },
                      body: JSON.stringify({ order }),
                    }).catch(() => {});
                  }}
                  onClick={(e) => {
                    // Only toggle if click was on the card itself, not a button/input
                    const tag = (e.target as HTMLElement).tagName;
                    if (tag === "BUTTON" || tag === "SELECT" || tag === "INPUT")
                      return;
                    toggleSegments(d.id);
                  }}
                  style={{
                    marginBottom: 8,
                    padding: "10px 14px",
                    background: "#161B22",
                    borderRadius: 8,
                    border: "1px solid #21262D",
                    cursor: "pointer",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        flexWrap: "wrap",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedDocs.has(d.id)}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) =>
                          setSelectedDocs((prev) => {
                            const next = new Set(prev);
                            if (e.target.checked) next.add(d.id);
                            else next.delete(d.id);
                            return next;
                          })
                        }
                        title={t("project.selectDoc")}
                        aria-label={t("project.selectDoc")}
                        style={{
                          margin: 0,
                          cursor: "pointer",
                          accentColor: "#A371F7",
                        }}
                      />
                      <strong style={{ color: "#E6EDF3" }}>
                        {d.original_filename}
                      </strong>

                      <span style={{ fontSize: 11, color: "#8B949E" }}>
                        {mimeLabel(d.mime_type)}
                      </span>
                      {/* Estado badge from log */}
                      {(() => {
                        const badge = getEstadoBadge(d);
                        const warning = (d as any).preprocess_warning;
                        return (
                          <>
                            <span
                              style={{
                                fontSize: 10,
                                padding: "2px 8px",
                                borderRadius: 999,
                                background: badge.bg,
                                color: badge.color,
                                border: `1px solid ${badge.color}33`,
                              }}
                            >
                              {badge.text}
                            </span>
                            {warning && (
                              <span
                                style={{
                                  fontSize: 9,
                                  padding: "2px 8px",
                                  borderRadius: 999,
                                  background: "#D2992218",
                                  color: "#D29922",
                                  border: "1px solid #D2992233",
                                  maxWidth: 200,
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                                title={warning}
                              >
                                {"⚠️ "}
                                {warning.length > 30
                                  ? warning.slice(0, 30) + "…"
                                  : warning}
                              </span>
                            )}
                          </>
                        );
                      })()}
                    </div>
                    <div
                      style={{ display: "flex", gap: 6, alignItems: "center" }}
                    >
                      {/* ── Step navigator: ONE pill for the whole interview ──
                          Shows the step being viewed (by default the LAST run
                          step). `<` / `>` move through the chain and reveal
                          that step's data; the run button only exists on the
                          empty step reached by pressing `>`. */}
                      {(() => {
                        const through = completedThrough(d);
                        const idx = clampedStepIndex(d);
                        const step = DOC_STEPS[idx];
                        const isEmpty = idx === through + 1;
                        // Both sources matter: handlePunctuate records the op in
                        // runningOps, while classify/segment set punctRunning;
                        // after a reload only the server-reported `estado` knows.
                        const isRunning = docRunning(d);
                        // Only a locally-tracked op can be revoked from here.
                        const canCancel =
                          punctRunning === d.id || !!runningOps[d.id];
                        const err = docError[d.id];
                        const isError =
                          String(d.estado ?? "").trim() === "error";
                        const hasText = !!(
                          (d as any).texto_original || d.texto_extraido
                        );
                        const color = STEP_COLORS[step];
                        const runDisabled = step === "preprocessed" && !hasText;
                        // Destructive controls wait for the project to go idle.
                        const canRedo = !isRunning && !anyStepRunning();
                        return (
                          <>
                            {/*<span
                              title={`${stepLabel(step)} (${idx + 1}/${DOC_STEPS.length})`}
                              style={{
                                fontSize: 10,
                                padding: "2px 8px",
                                borderRadius: 999,
                                background: `${color}22`,
                                color,
                                border: `1px solid ${color}44`,
                                whiteSpace: "nowrap",
                              }}
                            >
                              {STEP_ICONS[step]} {stepLabel(step)}
                            </span>*/}
                            {/* Per-state redo: the card header keeps exactly one
                                destructive control. Erases THIS step and every
                                step downstream of it. */}
                            {!isEmpty && step !== "original" && canRedo && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setRedoConfirmFor(d.id);
                                  if (expandedDoc !== d.id)
                                    setExpandedDoc(d.id);
                                }}
                                title={t("project.stepRedoTitle")}
                                style={{
                                  ...btnSmall,
                                  background: "#D2992218",
                                  color: "#D29922",
                                  border: "1px solid #D2992233",
                                  fontSize: 11,
                                  padding: "2px 8px",
                                }}
                              >
                                {"\u21BA "}
                                {t("project.stepRedo")}
                              </button>
                            )}
                            {/* Run button: ONLY on the empty step. Hidden while
                                expanded — the panel renders it inside the step. */}
                            {/*{isEmpty &&
                              !isRunning &&
                              !isError &&
                              !err &&
                              expandedDoc !== d.id && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    runStep(d, step);
                                  }}
                                  disabled={runDisabled}
                                  title={t("project.stepRun", {
                                    step: stepLabel(step),
                                  })}
                                  style={{
                                    ...btnSmall,
                                    background: runDisabled ? "#30363D" : color,
                                    color: runDisabled ? "#484F58" : "#FFF",
                                    border: "none",
                                    cursor: runDisabled
                                      ? "not-allowed"
                                      : "pointer",
                                  }}
                                >
                                  {t("project.stepRun", {
                                    step: stepLabel(step),
                                  })}
                                </button>
                              )}*/}
                            {isRunning && canCancel && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  cancelRunningOp(d.id);
                                }}
                                title={t("project.cancelPreprocess")}
                                style={{
                                  ...btnSmall,
                                  background: "transparent",
                                  color: "#F85149",
                                  border: "1px solid #F8514955",
                                  fontSize: 14,
                                  padding: "2px 8px",
                                  lineHeight: 1,
                                  cursor: "pointer",
                                }}
                              >
                                {"\u23F9"}
                              </button>
                            )}
                            {isRunning && !canCancel && (
                              <span
                                style={{
                                  ...btnSmall,
                                  background: "#21262D",
                                  color: "#8B949E",
                                  border: "none",
                                  cursor: "default",
                                }}
                              >
                                {t("project.statusInProgress")}
                              </span>
                            )}
                            {/* Error recovery — the only consumer of the old ↻ */}
                            {!isRunning && (err || isError) && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDocAction(d.id);
                                }}
                                title={t("project.stepRecoverError")}
                                style={{
                                  ...btnSmall,
                                  background: "#F85149",
                                  color: "#FFF",
                                  border: "none",
                                  cursor: "pointer",
                                }}
                              >
                                {"\u26A0 "}
                                {t("project.stepRetry")}
                              </button>
                            )}
                          </>
                        );
                      })()}
                      {/*{punctRunning !== d.id && originalTexts.current[d.id] && (
                        <button
                          onClick={async () => {
                            const orig = originalTexts.current[d.id];
                            if (
                              !orig ||
                              !(await safeConfirm(
                                t("project.restoreOriginalConfirm"),
                              ))
                            )
                              return;
                            await fetch(
                              `/api/v1/documents/${d.id}/undo-punctuate`,
                              {
                                method: "POST",
                                headers: {
                                  "Content-Type": "application/json",
                                  Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                                },
                                body: JSON.stringify({ original_text: orig }),
                              },
                            );
                            delete originalTexts.current[d.id];
                            setPunctStatus((prev) => ({
                              ...prev,
                              [d.id]: t("project.restored"),
                            }));
                            refreshAll();
                            setSegments((prev) => {
                              const n = { ...prev };
                              delete n[d.id];
                              return n;
                            });
                          }}
                          style={{ ...btnSmall, color: "#D29922" }}
                        >
                          {t("project.undo")}
                        </button>
                      )}*/}
                      {/* Destructive control: visible but locked while any
                          step is processing, here or elsewhere, so it keeps its
                          place in the header and can explain the lock. */}
                      {(() => {
                        const locked = docRunning(d) || anyStepRunning();
                        return (
                          // A disabled button swallows pointer events in most
                          // browsers, so the hint has to live on a wrapper.
                          <span
                            title={
                              locked
                                ? t("project.deleteBlockedTitle")
                                : undefined
                            }
                          >
                            <button
                              onClick={async () => {
                                // Re-read at click time: a run may have started
                                // after this render.
                                if (docRunning(d) || anyStepRunning()) return;
                                if (
                                  !(await safeConfirm(
                                    t("project.deleteConfirm"),
                                  ))
                                )
                                  return;
                                try {
                                  await deleteDocument(d.id);
                                  refreshAll();
                                } catch (e: any) {
                                  showErrorToast(
                                    "Error al eliminar: " + (e.message || ""),
                                  );
                                }
                              }}
                              disabled={locked}
                              style={{
                                ...btnSmall,
                                color: "#F85149",
                                opacity: locked ? 0.4 : 1,
                                cursor: locked ? "not-allowed" : "pointer",
                              }}
                            >
                              {t("project.deleteIcon")}
                            </button>
                          </span>
                        );
                      })()}
                    </div>
                  </div>

                  {/* Per-document error fallback (visible without reload) */}
                  {docError[d.id] && (
                    <div
                      style={{
                        marginTop: 8,
                        padding: "6px 10px",
                        background: "#F8514914",
                        border: "1px solid #F8514933",
                        borderRadius: 6,
                        color: "#F85149",
                        fontSize: 11,
                        lineHeight: 1.5,
                        display: "flex",
                        gap: 6,
                        alignItems: "flex-start",
                      }}
                    >
                      <span>⚠</span>
                      <span style={{ flex: 1 }}>{docError[d.id].message}</span>
                      <button
                        onClick={() => {
                          setDocError((prev) => {
                            const n = { ...prev };
                            delete n[d.id];
                            return n;
                          });
                        }}
                        title="Descartar"
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#F85149",
                          cursor: "pointer",
                          fontSize: 12,
                          lineHeight: 1,
                          padding: 0,
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  )}

                  {/* ── Expanded step viewer ── */}
                  {expandedDoc === d.id && (
                    <div style={{ marginTop: 8 }}>
                      {/* Inline confirmation (a list, so `safeConfirm` — a
                          single-line bar — cannot render it). */}
                      {redoConfirmFor === d.id &&
                        !isOnEmptyStep(d) &&
                        viewedStepOf(d) !== "original" &&
                        !anyStepRunning() &&
                        (() => {
                          const idx = clampedStepIndex(d);
                          const step = DOC_STEPS[idx];
                          const eraseLabels = DOC_STEPS.slice(idx)
                            .map((s) => stepLabel(s))
                            .join(", ");
                          return (
                            <div
                              onClick={(e) => e.stopPropagation()}
                              style={{
                                marginBottom: 8,
                                padding: "8px 10px",
                                borderRadius: 6,
                                background: "#F8514912",
                                border: "1px solid #F8514933",
                                color: "#F85149",
                                fontSize: 11,
                                lineHeight: 1.6,
                              }}
                            >
                              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                                {"\u26A0 "}
                                {t("project.stepRedoConfirmTitle", {
                                  step: stepLabel(step),
                                })}
                              </div>
                              <div>
                                {t("project.stepRedoWillErase", {
                                  steps: eraseLabels,
                                })}
                              </div>
                              <div style={{ marginBottom: 6 }}>
                                {t("project.stepRedoIrreversible")}
                              </div>
                              <div style={{ display: "flex", gap: 6 }}>
                                <button
                                  onClick={() => handleRedoStep(d, step)}
                                  style={{
                                    ...btnSmall,
                                    background: "#F85149",
                                    color: "#FFF",
                                    border: "none",
                                  }}
                                >
                                  {t("project.stepRedoConfirmButton")}
                                </button>
                                <button
                                  onClick={() => setRedoConfirmFor(null)}
                                  style={{
                                    ...btnSmall,
                                    background: "transparent",
                                    color: "#8B949E",
                                  }}
                                >
                                  {t("common.cancel")}
                                </button>
                              </div>
                            </div>
                          );
                        })()}

                      {/* Empty step: this is the ONLY place the run button lives. */}
                      {isOnEmptyStep(d) &&
                        (() => {
                          const idx = clampedStepIndex(d);
                          const step = DOC_STEPS[idx];
                          const stepColor = STEP_COLORS[step];
                          const isRunning =
                            punctRunning === d.id ||
                            !!runningOps[d.id] ||
                            IN_FLIGHT_DOC_STATES.includes(
                              String(d.estado ?? "").trim(),
                            );
                          const hasText = !!(
                            (d as any).texto_original || d.texto_extraido
                          );
                          const runDisabled =
                            step === "preprocessed" && !hasText;
                          return (
                            <div
                              onClick={(e) => e.stopPropagation()}
                              style={{
                                marginBottom: 8,
                                padding: "10px 12px",
                                borderRadius: 6,
                                background: "#1C2333",
                                border: "1px dashed #30363D",
                                fontSize: 12,
                                color: "#8B949E",
                                lineHeight: 1.6,
                              }}
                            >
                              <div
                                style={{
                                  fontWeight: 600,
                                  color: "#E6EDF3",
                                  marginBottom: 4,
                                }}
                              >
                                {STEP_ICONS[step]}{" "}
                                {t("project.stepEmptyTitle", {
                                  step: stepLabel(step),
                                })}
                              </div>
                              <div style={{ marginBottom: 8 }}>
                                {t("project.stepEmptyHint")}
                              </div>
                              {/* Cancelling lives in the header navigator, so
                                  this box only reports that the step is in
                                  flight — otherwise the ⏹ would appear twice. */}
                              {isRunning ? (
                                <span
                                  style={{
                                    ...btnSmall,
                                    background: "#21262D",
                                    color: "#8B949E",
                                    border: "none",
                                    cursor: "default",
                                  }}
                                >
                                  {t("project.statusInProgress")}
                                </span>
                              ) : (
                                <button
                                  onClick={() => runStep(d, step)}
                                  disabled={runDisabled}
                                  style={{
                                    ...btnSmall,
                                    background: runDisabled
                                      ? "#30363D"
                                      : stepColor,
                                    color: runDisabled ? "#484F58" : "#FFF",
                                    border: "none",
                                    cursor: runDisabled
                                      ? "not-allowed"
                                      : "pointer",
                                  }}
                                >
                                  {"\u25B6 "}
                                  {t("project.stepRun", {
                                    step: stepLabel(step),
                                  })}
                                </button>
                              )}
                            </div>
                          );
                        })()}
                      {/* Text viewer — only for the steps that ARE text. */}
                      {/* While processing, the text is 50% transparent and
                          non-interactive so it cannot be edited mid-run. */}
                      {!isOnEmptyStep(d) &&
                        viewedStepOf(d) !== "segmented" &&
                        viewedStepOf(d) !== "incidents" && (
                          <div
                            style={{
                              opacity:
                                punctRunning === d.id || runningOps[d.id]
                                  ? 0.5
                                  : 1,
                              pointerEvents:
                                punctRunning === d.id || runningOps[d.id]
                                  ? "none"
                                  : "auto",
                              transition: "opacity .2s",
                            }}
                          >
                            {(() => {
                              const step = textEditStepOf(d);
                              // Only on its own step, and only while idle.
                              if (textEdits[d.id] !== undefined) return null;
                              if (viewedStepOf(d) !== step) return null;
                              const blocked = textEditBlockedReason(d);
                              return (
                                <div
                                  style={{
                                    display: "flex",
                                    justifyContent: "flex-end",
                                    marginBottom: 6,
                                  }}
                                >
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      if (blocked) {
                                        showToast(blocked);
                                        return;
                                      }
                                      const text = stepTextRaw(d, step);
                                      setTextEdits((prev) => ({
                                        ...prev,
                                        [d.id]: { text, step },
                                      }));
                                    }}
                                    title={
                                      blocked ?? t("project.editTextTitle")
                                    }
                                    style={{
                                      ...btnSmall,
                                      background: "#D2992218",
                                      color: "#D29922",
                                      border: "1px solid #D2992233",
                                      fontSize: 10,
                                      padding: "2px 8px",
                                      opacity: blocked ? 0.5 : 1,
                                      cursor: blocked
                                        ? "not-allowed"
                                        : "pointer",
                                    }}
                                  >
                                    {t("project.editText")}
                                  </button>
                                </div>
                              );
                            })()}
                            {textEdits[d.id] !== undefined ? (
                              <textarea
                                disabled={
                                  punctRunning === d.id || !!runningOps[d.id]
                                }
                                onClick={(e) => e.stopPropagation()}
                                onChange={(e) =>
                                  setTextEdits((prev) => ({
                                    ...prev,
                                    [d.id]: {
                                      ...prev[d.id],
                                      text: e.target.value,
                                    },
                                  }))
                                }
                                style={{
                                  width: "100%",
                                  minHeight: 150,
                                  fontFamily: "monospace",
                                  fontSize: 13,
                                  background: "#0D1117",
                                  color: "#E6EDF3",
                                  border: "1px solid #D29922",
                                  borderRadius: 6,
                                  padding: 8,
                                  resize: "vertical",
                                }}
                                value={textEdits[d.id]?.text ?? ""}
                              />
                            ) : viewedStepOf(d) === "classified" &&
                              (d.glaser_blocks?.length ?? 0) > 0 ? (
                              /* El paso clasificado se edita bloque por bloque:
                                 cambiar una categoría re-deriva la etiqueta de
                                 los segmentos, así que es una escritura real. */
                              <ClassifiedBlockEditor
                                documentId={d.id}
                                blocks={d.glaser_blocks ?? []}
                                canEdit={!docRunning(d)}
                                onSaved={(blocks, textoClasificado) => {
                                  setDocs((prev) =>
                                    prev.map((item) =>
                                      item.id === d.id
                                        ? {
                                            ...item,
                                            glaser_blocks: blocks,
                                            texto_clasificado: textoClasificado,
                                          }
                                        : item,
                                    ),
                                  );
                                  // Los segmentos heredaron etiquetas nuevas.
                                  invalidateDocCaches(d.id);
                                }}
                                onError={showErrorToast}
                              />
                            ) : (
                              <div
                                onClick={(e) => e.stopPropagation()}
                                style={{
                                  width: "100%",
                                  minHeight: 150,
                                  maxHeight: "55vh",
                                  fontFamily: "monospace",
                                  fontSize: 13,
                                  background: "#0D1117",
                                  color: "#E6EDF3",
                                  border: "1px solid #21262D",
                                  borderRadius: 6,
                                  padding: 8,
                                  overflow: "auto",
                                  whiteSpace: "pre-wrap",
                                  wordBreak: "break-word",
                                }}
                                dangerouslySetInnerHTML={{
                                  __html:
                                    viewedStepOf(d) === "classified"
                                      ? renderClassified(d)
                                      : stepTextHtml(d, viewedStepOf(d)),
                                }}
                              />
                            )}
                          </div>
                        )}
                      {textEdits[d.id] !== undefined && (
                        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                          <button
                            onClick={() => saveDocText(d.id)}
                            disabled={textSaving[d.id]}
                            style={{
                              padding: "4px 12px",
                              borderRadius: 4,
                              border: "none",
                              background: textSaving[d.id]
                                ? "#30363D"
                                : "#3FB950",
                              color: "#FFF",
                              fontSize: 11,
                              fontWeight: 600,
                              cursor: textSaving[d.id]
                                ? "not-allowed"
                                : "pointer",
                            }}
                          >
                            {textSaving[d.id]
                              ? t("project.textSaving")
                              : t("project.textSave")}
                          </button>
                          <button
                            onClick={() =>
                              setTextEdits((prev) => {
                                const next = { ...prev };
                                delete next[d.id];
                                return next;
                              })
                            }
                            style={{
                              padding: "4px 12px",
                              borderRadius: 4,
                              border: "1px solid #30363D",
                              background: "transparent",
                              color: "#8B949E",
                              fontSize: 11,
                              cursor: "pointer",
                            }}
                          >
                            {t("project.textDiscard")}
                          </button>
                        </div>
                      )}

                      {/* ── Classified: audit surface for the inheritance step ── */}
                      {!isOnEmptyStep(d) &&
                        viewedStepOf(d) === "classified" && (
                          <div
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              marginTop: 8,
                              padding: "8px 10px",
                              borderRadius: 6,
                              background: "#3FB95010",
                              border: "1px solid #3FB95033",
                              fontSize: 11,
                              lineHeight: 1.6,
                            }}
                          >
                            <div
                              style={{
                                fontWeight: 600,
                                color: "#3FB950",
                                marginBottom: 4,
                              }}
                            >
                              {t("project.classifiedUntaggedHeading")} (
                              {
                                (segments[d.id] ?? []).filter(
                                  (s) => !s.tipo_dato_glaser,
                                ).length
                              }
                              )
                            </div>
                            {(segments[d.id] ?? []).filter(
                              (s) => !s.tipo_dato_glaser,
                            ).length === 0 ? (
                              <div style={{ color: "#8B949E" }}>
                                {t("project.segmentsEmpty")}
                              </div>
                            ) : (
                              (segments[d.id] ?? [])
                                .filter((s) => !s.tipo_dato_glaser)
                                .map((s) => (
                                  <div key={s.id} style={{ color: "#8B949E" }}>
                                    <span style={{ color: "#F85149" }}>
                                      #{s.posicion}
                                    </span>{" "}
                                    {shorten(s.texto, 120)}
                                  </div>
                                ))
                            )}
                          </div>
                        )}

                      {/* ── Segmented: cada segmento, con borrado/fusión ── */}
                      {!isOnEmptyStep(d) && viewedStepOf(d) === "segmented" && (
                        <SegmentsMergeList
                          documentId={d.id}
                          segments={segments[d.id] ?? []}
                          canEdit={!docRunning(d)}
                          onChanged={(next) =>
                            setSegments((prev) => ({ ...prev, [d.id]: next }))
                          }
                          onError={showErrorToast}
                          onNotify={showToast}
                        />
                      )}

                      {/* ── Incidentes: curación manual ── */}
                      {!isOnEmptyStep(d) &&
                        viewedStepOf(d) === "incidents" &&
                        (() => {
                          const estado = String(d.estado ?? "").trim();
                          const incidentsRunning =
                            punctRunning === d.id ||
                            !!runningOps[d.id] ||
                            IN_FLIGHT_DOC_STATES.includes(estado);
                          return (
                            <IncidentsPanel
                              documentId={d.id}
                              canEdit={!incidentsRunning}
                              // Cambia cuando el documento gana/pierde datos:
                              // es lo que fuerza al panel a releer en vez de
                              // quedar mostrando el payload viejo.
                              reloadToken={`${d.id}:${estado}:${
                                segments[d.id]?.length ?? 0
                              }:${getDocLog(d.id)?.incidents_count ?? 0}`}
                              onRunExtraction={() => runStep(d, "incidents")}
                              // La categoría de una cita no se reclasifica acá:
                              // el único lugar con autoridad sobre el texto es
                              // el paso `classified`, así que el enlace lleva
                              // al visor de ese paso.
                              onEditClassification={() => {
                                const index = DOC_STEPS.indexOf("classified");
                                if (index >= 0) setGlobalStep(index);
                              }}
                            />
                          );
                        })()}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          <hr style={{ borderColor: "#21262D", margin: "24px 0" }} />

          {/* ── HITL Modal ── */}
          {hitlPending.length > 0 && id && (
            <HITLModal
              open={showHITLModal}
              projectId={id}
              gateName={hitlPending[0].gate_name}
              onClose={() => setShowHITLModal(false)}
              onDecided={() => {
                setShowHITLModal(false);
                getPendingHitl(id)
                  .then(setHitlPending)
                  .catch(() => {});
              }}
            />
          )}

          {/* ── Add Memo Modal ── */}
          {showAddMemo && id && (
            <AddMemoModal
              projectId={id}
              onClose={() => setShowAddMemo(false)}
              onCreated={() => {
                setShowAddMemo(false);
                refreshAll();
              }}
            />
          )}

          {/* ── Open-coding HITL Modal ── */}
          {id && (
            <OpenCodingHITLModal
              open={ocHitlOpen}
              projectId={id}
              onClose={() => setOcHitlOpen(false)}
              onDecided={() => {
                setOcHitlOpen(false);
                getOpenCodingHitlStatus(id)
                  .then(setOcHitl)
                  .catch(() => {});
                refreshAll();
              }}
            />
          )}

          {/* ── Project Config Panel ── */}
          {id && (
            <ProjectConfigPanel
              open={showConfigPanel}
              projectId={id}
              onClose={() => setShowConfigPanel(false)}
            />
          )}

          {/* ── Memo History ── */}
          <div
            style={{
              marginTop: 24,
              paddingTop: 20,
              borderTop: "1px solid #21262D",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 12,
              }}
            >
              <span style={{ fontSize: 14, fontWeight: 600, color: "#E6EDF3" }}>
                {t("project.memoHistory")}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "#484F58" }}>
                  {pipelineLog?.documents?.length || 0} {t("common.docs")} ·{" "}
                  {agentMemos.length} {t("common.memos")}
                </span>
                {!pipelineRunning && (
                  <button
                    onClick={() => setShowAddMemo(true)}
                    style={{
                      background: "#3FB95018",
                      border: "1px solid #3FB95044",
                      borderRadius: 6,
                      color: "#3FB950",
                      fontSize: 10,
                      fontWeight: 600,
                      padding: "3px 10px",
                      cursor: "pointer",
                    }}
                  >
                    {t("project.addMemo")}
                  </button>
                )}
                {agentMemos.length > 0 && (
                  <ConfirmDeleteButton
                    label={t("project.deleteAllMemos")}
                    title={
                      entitiesLocked
                        ? t("memo.pipelineBusy")
                        : t("project.deleteAllMemos")
                    }
                    confirmText={t("memo.deleteAllConfirm")}
                    disabled={entitiesLocked}
                    onConfirm={handleDeleteAllMemos}
                  />
                )}
              </div>
            </div>

            <MemoHistory
              memos={agentMemos}
              activeFilter={memoFilter}
              onFilterChange={setMemoFilter}
              onDeleteMemo={handleDeleteMemo}
              onDeleteMemos={handleDeleteMemos}
              deleteDisabled={entitiesLocked}
              onUpdateMemo={handleUpdateMemo}
              projectId={id!}
              originalPrompt={project.ruta_de_codificacion || ""}
              onMemoModified={handleMemoModified}
            />
          </div>
        </div>

        {/* ── End Right Column ── */}
      </div>

      {/* ── Left: Pipeline Flow Panel ── */}
      <div
        style={{
          width: 340,
          flexShrink: 0,
          borderRight: "1px solid #21262D",
          background: "#0D1117",
          padding: "16px 14px 40px",
          height: "100vh",
          overflowY: "auto",
          position: "sticky",
          top: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* ── Header Row ── */}
        <div
          style={{
            flexShrink: 0,
            borderBottom: "1px solid #21262D",
            paddingBottom: 12,
            marginBottom: 12,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 5,
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 600, color: "#8B949E" }}>
              {sidebarViewMode === "logs"
                ? "Logs"
                : sidebarViewMode === "agents"
                  ? "Agentes"
                  : sidebarViewMode === "hitl"
                    ? "Decisiones HITL"
                    : "Etapas"}
            </span>

            {!pipelineRunning ? (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <button
                  onClick={() => restartFromStage("selective_coding")}
                  disabled={docs.length === 0 || docsDone === 0}
                  title={
                    docsDone === 0
                      ? "Run pipeline first"
                      : "Restart from Selective Coding"
                  }
                  style={{
                    background:
                      docs.length === 0 || docsDone === 0
                        ? "#21262D"
                        : "#1C2333",
                    border: "1px solid #30363D",
                    borderRadius: 6,
                    color:
                      docs.length === 0 || docsDone === 0
                        ? "#484F58"
                        : "#58A6FF",
                    fontSize: 14,
                    fontWeight: 600,
                    padding: "4px 10px",
                    cursor:
                      docs.length === 0 || docsDone === 0
                        ? "not-allowed"
                        : "pointer",
                    lineHeight: 1,
                  }}
                >
                  {"\u21BB"}
                </button>
                <button
                  onClick={() => runPipeline(false)}
                  disabled={docs.length === 0}
                  style={{
                    background:
                      docs.length === 0
                        ? "#21262D"
                        : "linear-gradient(135deg, #A371F7, #3FB950)",
                    border: "none",
                    borderRadius: 6,
                    color: docs.length === 0 ? "#484F58" : "#FFF",
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "4px 12px",
                    cursor: docs.length === 0 ? "not-allowed" : "pointer",
                  }}
                >
                  ▶ {t("project.runPipeline")}
                </button>
                {hasStaleRun && (
                  <button
                    onClick={async () => {
                      await closeIdlePipelineRuns(id!).catch(() => {});
                      getPipelineLog(id!)
                        .then(setPipelineLog)
                        .catch(() => {});
                    }}
                    title={t("project.closeStaleRunTitle")}
                    style={{
                      background: "#D2992218",
                      border: "1px solid #D2992233",
                      borderRadius: 6,
                      color: "#D29922",
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "4px 10px",
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}
                  >
                    ⏹ {t("project.closeStaleRun")}
                  </button>
                )}
              </div>
            ) : (
              <button
                onClick={async () => {
                  abortRef.current = true;
                  if (logPollRef.current) {
                    clearInterval(logPollRef.current);
                    logPollRef.current = null;
                  }
                  if (agentPollRef.current) {
                    clearInterval(agentPollRef.current);
                    agentPollRef.current = null;
                  }
                  await fetch(`/api/v1/admin/projects/${id}/stop`, {
                    method: "POST",
                    headers: {
                      Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                    },
                  }).catch(() => {});
                  setPipelineRunning(false);
                  setPipelineMsg(t("project.pipelineCancelled"));
                  resetStages();
                  getPipelineLog(id!)
                    .then(setPipelineLog)
                    .catch(() => {});
                }}
                style={{
                  background: "#D2992222",
                  border: "1px solid #D2992244",
                  borderRadius: 6,
                  color: "#D29922",
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "4px 12px",
                  cursor: "pointer",
                }}
              >
                ⏸ {t("project.pausePipeline")}
              </button>
            )}
          </div>
        </div>

        {/* ── Content Area ── */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
          }}
        >
          {/* View toggle buttons — 2 tabs */}
          <div
            style={{
              display: "flex",
              marginBottom: 12,
              borderRadius: 6,
              overflow: "hidden",
              border: "1px solid #30363D",
              flexShrink: 0,
            }}
          >
            <button
              onClick={() => setSidebarViewMode("agents")}
              style={{
                flex: 1,
                padding: "6px 12px",
                border: "none",
                cursor: "pointer",
                fontSize: 11,
                fontWeight: 600,
                background:
                  sidebarViewMode === "agents" ? "#A371F7" : "transparent",
                color: sidebarViewMode === "agents" ? "#fff" : "#8B949E",
              }}
            >
              🤖 Agentes
            </button>
            <button
              onClick={() => setSidebarViewMode("stages")}
              style={{
                flex: 1,
                padding: "6px 12px",
                border: "none",
                cursor: "pointer",
                fontSize: 11,
                fontWeight: 600,
                background:
                  sidebarViewMode === "stages" ? "#A371F7" : "transparent",
                color: sidebarViewMode === "stages" ? "#fff" : "#8B949E",
              }}
            >
              📋 Etapas
            </button>
            <button
              onClick={() => setSidebarViewMode("logs")}
              style={{
                flex: 1,
                padding: "6px 12px",
                border: "none",
                cursor: "pointer",
                fontSize: 11,
                fontWeight: 600,
                background:
                  sidebarViewMode === "logs" ? "#A371F7" : "transparent",
                color: sidebarViewMode === "logs" ? "#fff" : "#8B949E",
              }}
            >
              📋 Logs
            </button>
            <button
              onClick={() => setSidebarViewMode("hitl")}
              style={{
                flex: 1,
                padding: "6px 12px",
                border: "none",
                cursor: "pointer",
                fontSize: 11,
                fontWeight: 600,
                background:
                  sidebarViewMode === "hitl" ? "#A371F7" : "transparent",
                color: sidebarViewMode === "hitl" ? "#fff" : "#8B949E",
              }}
            >
              {t("hitlCrud.title")}
            </button>
          </div>

          {pipelineMsg && (
            <div
              style={{
                fontSize: 11,
                color: pipelineFailed ? "#F85149" : "#8B949E",
                padding: "6px 10px",
                background: pipelineFailed ? "#F8514922" : "#21262D",
                borderRadius: 6,
                border: `1px solid ${pipelineFailed ? "#F8514944" : "#30363D"}`,
                marginBottom: 12,
              }}
            >
              {pipelineMsg}
            </div>
          )}

          {sidebarViewMode === "logs" ? (
            <div
              ref={logPanelRef}
              style={{
                background: "#0D1117",
                borderRadius: 6,
                border: "1px solid #21262D",
                padding: 8,
                flex: 1,
                overflowY: "auto",
                fontSize: 10,
                fontFamily: "monospace",
                minHeight: 0,
              }}
            >
              {pipelineLiveLogs.length === 0 && (
                <span style={{ color: "#484F58" }}>{t("project.noLogs")}</span>
              )}
              {pipelineLiveLogs.map((l, i) => {
                const msg = l.msg || "";
                const isError = /\[ERROR\]|❌|failed|error/i.test(msg);
                const isActive =
                  /A[123]:|C0?6:|B[123]:|B2\.5:|\[COREF\]|\[SegText\]|Agent \w|LLM:|Phase B|Pipeline log/i.test(
                    msg,
                  );
                const color = isError
                  ? "#F85149"
                  : isActive
                    ? "#58A6FF"
                    : "#8B949E";
                return (
                  <div key={i} style={{ padding: "1px 0", color }}>
                    <span style={{ color: "#484F58" }}>
                      {new Date(l.ts * 1000).toLocaleTimeString()}
                    </span>{" "}
                    {msg}
                  </div>
                );
              })}
            </div>
          ) : sidebarViewMode === "hitl" ? (
            <HitlDecisionsPanel projectId={id} />
          ) : sidebarViewMode === "agents" ? (
            <PipelineAgents
              agentStatuses={agentStatuses}
              onRunAgent={async (agentId) => {
                console.log("[PipelineAgents] run", agentId);
                const auth = `Bearer ${localStorage.getItem("access_token")}`;
                const perDocAgents = new Set([
                  "util_punctuator",
                  "segmentar_documento",
                  "fa_glaser_data_classifier",
                  "fa_document_pattern_extractor",
                ]);
                if (perDocAgents.has(agentId)) {
                  // ── Helper: clear previous work and restart ──
                  const clearAndRestart = async (
                    agent: string,
                    targetIds: Set<string>,
                  ) => {
                    // Clear HITL
                    await fetch(`/api/v1/projects/${id}/hitl/reset`, {
                      method: "POST",
                      headers: {
                        Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                      },
                    }).catch(() => {});
                    // Preprocessor: revert only the confirmed docs, so re-running
                    // a subset does not strand the ones left at 'preprocesado'.
                    if (agent === "util_punctuator") {
                      const preprocessed = docs.filter(
                        (d) =>
                          d.estado === "preprocesado" && targetIds.has(d.id),
                      );
                      for (const d of preprocessed) {
                        await fetch(
                          `/api/v1/documents/${d.id}/restore-original`,
                          {
                            method: "POST",
                            headers: {
                              Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                            },
                          },
                        ).catch(() => {});
                      }
                    }
                    // Delete segments only when re-running punctuation or
                    // segmentation; the classifier consumes existing segments.
                    if (
                      agent === "util_punctuator" ||
                      agent === "segmentar_documento"
                    ) {
                      await fetch(`/api/v1/documents/project/${id}/segments`, {
                        method: "DELETE",
                        headers: {
                          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                        },
                      }).catch(() => {});
                    }
                    // Fresh docs AFTER reverts
                    const freshDocs = await listDocuments(id!).catch(
                      () => docs,
                    );
                    setDocs(freshDocs);
                    setCompletedAgents((prev) => {
                      const next = new Set(prev);
                      next.delete(agent);
                      // Also clear downstream agents
                      const agentOrder = [
                        "util_punctuator",
                        "fa_glaser_data_classifier",
                        "segmentar_documento",
                        "fa_document_pattern_extractor",
                      ];
                      const idx = agentOrder.indexOf(agent);
                      if (idx >= 0) {
                        for (let i = idx; i < agentOrder.length; i++) {
                          next.delete(agentOrder[i]);
                        }
                      }
                      return next;
                    });
                    // Se procesan exactamente los docs confirmados (el conjunto
                    // puede menguar si alguno perdió material al revertir), no
                    // todo lo que parezca elegible ahora.
                    const resetEligible = freshDocs.filter(
                      (d) => targetIds.has(d.id) && canProcessDoc(d, agent),
                    );
                    dispatchAgentLoop(resetEligible);
                  };

                  // ── Build a single confirmation message ──
                  // 1. What layers will be wiped?
                  const agentOrder = [
                    "util_punctuator",
                    "fa_glaser_data_classifier",
                    "segmentar_documento",
                    "fa_document_pattern_extractor",
                  ];
                  const myIdx = agentOrder.indexOf(agentId);
                  const wipedAgents = myIdx >= 0 ? agentOrder.slice(myIdx) : [];
                  const wipeLabels: string[] = [];
                  // Classify-first: the segmenter deletes the segments (and with
                  // them the inherited tags); the classifier only rewrites the
                  // classified text over the preprocessed one.
                  if (wipedAgents.includes("segmentar_documento"))
                    wipeLabels.push("segmentos");
                  if (
                    wipedAgents.includes("fa_glaser_data_classifier") &&
                    // Re-running the segmenter already reports the segments.
                    !wipedAgents.includes("segmentar_documento")
                  )
                    wipeLabels.push("texto clasificado");
                  if (wipedAgents.includes("util_punctuator"))
                    wipeLabels.push("texto preprocesado");

                  // 2. Docs con material y docs que aún necesitan este agente.
                  const reprocessableDocs = docs.filter((d) =>
                    canProcessDoc(d, agentId),
                  );
                  const pendingDocs = reprocessableDocs.filter((d) =>
                    needsAgent(d, agentId),
                  );
                  const missingPrereq = docs.length - reprocessableDocs.length;

                  // Si queda trabajo pendiente se procesa sólo eso (▶). Si no
                  // queda nada pendiente, el click es un re-run (↻) y se
                  // reprocesa todo lo que tenga material.
                  //
                  // Excepción: el borrado de segmentos es por proyecto, así que
                  // segmentar un subconjunto dejaría sin segmentos al resto. Ahí
                  // el click siempre reprocesa todos los docs con material.
                  const wipesAll = agentId === "segmentar_documento";
                  const isRerun = pendingDocs.length === 0;
                  const eligible =
                    isRerun || wipesAll ? reprocessableDocs : pendingDocs;

                  // 3. Build message
                  let confirmMsg2 = "";
                  if (wipeLabels.length > 0) {
                    confirmMsg2 +=
                      "Se eliminarán: " + wipeLabels.join(", ") + ". ";
                  }
                  // El extractor no borra capas previas: el worker reescribe los
                  // incidentes y patrones (`replace_existing`) y recalcula A1/A2/A3.
                  if (agentId === "fa_document_pattern_extractor") {
                    confirmMsg2 +=
                      "Los incidentes y patrones previos se reemplazarán. ";
                  }
                  if (missingPrereq > 0) {
                    confirmMsg2 +=
                      missingPrereq +
                      " de " +
                      docs.length +
                      " docs no tienen material para procesar y se omitirán. ";
                  }
                  let targetSuffix = "";
                  if (isRerun) targetSuffix = " (ya procesados)";
                  else if (wipesAll)
                    targetSuffix = ` (${pendingDocs.length} pendiente(s); el borrado de segmentos es por proyecto)`;
                  confirmMsg2 +=
                    (isRerun ? "Re-procesar " : "Procesar ") +
                    eligible.length +
                    " documento(s)" +
                    targetSuffix +
                    ". ¿Continuar?";
                  if (eligible.length === 0) {
                    showErrorToast(
                      "Ningún documento tiene texto ni segmentos para procesar.",
                    );
                    return;
                  }
                  const ok = await safeConfirm(confirmMsg2);
                  if (!ok) return;

                  // ── Wipe downstream layers before running ──
                  const targetIds = new Set(eligible.map((d) => d.id));
                  await clearAndRestart(agentId, targetIds);

                  async function dispatchAgentLoop(
                    docsToProcess: typeof eligible,
                  ) {
                    abortRef.current = false;
                    setRunningAgentIds((prev) => new Set([...prev, agentId]));
                    try {
                      for (const doc of docsToProcess) {
                        if (abortRef.current) break;
                        await runDocTask(
                          doc.id,
                          `/api/v1/projects/${id}/pipeline/run-agent/${agentId}`,
                          abortRef,
                        );
                      }
                    } catch (e: any) {
                      showErrorToast(e?.message || String(e));
                    } finally {
                      // El badge siempre vuelve a su estado real: sin `finally`,
                      // un fetch fallido dejaba el spinner colgado para siempre.
                      // PipelineAgents recomputa canRun/done desde docs[].estado.
                      runningTaskRef.current = null;
                      setRunningAgentIds((prev) => {
                        const next = new Set(prev);
                        next.delete(agentId);
                        return next;
                      });
                      refreshAll();
                    }
                  }
                } else {
                  // Project-level agent
                  setRunningAgentIds((prev) => new Set([...prev, agentId]));
                  const clearRunning = () =>
                    setRunningAgentIds((prev) => {
                      const next = new Set(prev);
                      next.delete(agentId);
                      return next;
                    });
                  try {
                    const res = await fetch(
                      `/api/v1/projects/${id}/pipeline/run-agent/${agentId}`,
                      {
                        method: "POST",
                        headers: {
                          "Content-Type": "application/json",
                          Authorization: auth,
                        },
                        body: JSON.stringify({}),
                      },
                    );
                    if (!res.ok) {
                      let detail = `HTTP ${res.status}`;
                      try {
                        const body = await res.json();
                        if (body?.detail) {
                          detail =
                            typeof body.detail === "string"
                              ? body.detail
                              : JSON.stringify(body.detail);
                        }
                      } catch {
                        /* non-JSON error body */
                      }
                      throw new Error(detail);
                    }
                    const { task_id: taskId } = await res.json();
                    // Poll until terminal so the badge matches the real outcome.
                    if (taskId) {
                      const pollInterval = 3000;
                      const maxPolls = Math.ceil(
                        STEP_TIMEOUT_MS / pollInterval,
                      );
                      let outcome: "success" | "failed" | "timeout" = "timeout";
                      for (let i = 0; i < maxPolls; i++) {
                        await new Promise((r) => setTimeout(r, pollInterval));
                        try {
                          const ts = await getTaskStatus(taskId);
                          if (ts.status === "SUCCESS") {
                            outcome = "success";
                            break;
                          }
                          if (
                            ts.status === "FAILURE" ||
                            ts.status === "REVOKED"
                          ) {
                            outcome = "failed";
                            break;
                          }
                        } catch {
                          /* polling error, keep trying */
                        }
                      }
                      if (outcome === "success") {
                        setCompletedAgents(
                          (prev) => new Set([...prev, agentId]),
                        );
                      } else if (outcome === "failed") {
                        showErrorToast(
                          `El agente "${agentId}" falló o fue cancelado.`,
                        );
                      } else {
                        showErrorToast(
                          `El agente "${agentId}" no terminó a tiempo.`,
                        );
                      }
                    } else {
                      setCompletedAgents((prev) => new Set([...prev, agentId]));
                    }
                  } catch (e: any) {
                    showErrorToast(
                      "Error al ejecutar agente: " +
                        (e?.message || "error de red"),
                    );
                  } finally {
                    clearRunning();
                    refreshAll();
                  }
                }
              }}
              onStopAgent={(agentId) => {
                console.log("[PipelineAgents] stop", agentId);
                abortRef.current = true;
                runningTaskRef.current = null;
                // Single robust stop: kills all tasks + rolls back estados
                fetch(`/api/v1/admin/projects/${id}/stop`, {
                  method: "POST",
                  headers: {
                    Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                  },
                })
                  .then(() => refreshAll())
                  .catch(() => {});
                setRunningAgentIds((prev) => {
                  const next = new Set(prev);
                  next.delete(agentId);
                  return next;
                });
              }}
              pipelineRunning={pipelineRunning || phaseRunning}
              completedAgents={completedAgents}
              iterations={iterations}
              agentDocCounts={Object.fromEntries(
                Object.entries(PER_DOC_AGENTS).map(([agentId]) => [
                  agentId,
                  {
                    // `done` espeja `eligible`: un doc en el estado de salida
                    // cuyos segmentos siguen sin categoría no está terminado.
                    done: docs.filter((d) => !needsAgent(d, agentId)).length,
                    total: docs.length,
                  },
                ]),
              )}
              eligibleDocCounts={Object.fromEntries(
                Object.entries(PER_DOC_AGENTS).map(([agentId]) => [
                  agentId,
                  docs.filter(
                    (d) => canProcessDoc(d, agentId) && needsAgent(d, agentId),
                  ).length,
                ]),
              )}
              upstreamDocCounts={Object.fromEntries(
                Object.entries(PER_DOC_AGENTS).map(([agentId, { output }]) => [
                  agentId,
                  docs.filter((d) => (BEYOND[output] || []).includes(d.estado))
                    .length,
                ]),
              )}
              stages={PIPELINE_STAGES}
            />
          ) : (
            <>
              {PIPELINE_STAGES.map((stage, idx) => {
                const status = stageStatuses[stage.key] || "pending";
                const isLast = idx === PIPELINE_STAGES.length - 1;
                const lastDone = findLastCompletedIdx();
                const isNextPending =
                  docs.length > 0 &&
                  status === "pending" &&
                  idx === lastDone + 1;
                // True while any agent of this stage is executing, even when the
                // stage's own status has not been flipped to "running" (manual
                // runs). Must be computed before isClickable: a finished stage
                // stays "done" while one of its agents is re-run, so a click here
                // would restart/wipe the stage mid-flight.
                const isStageRunning =
                  status === "running" ||
                  stage.agents.some((a) => isAgentRunning(a.id)) ||
                  runningPhases.has(stage.key);

                const isClickable =
                  !pipelineRunning &&
                  !isStageRunning &&
                  (status === "done" || status === "error" || isNextPending);

                const circleBg = isStageRunning
                  ? "#A371F722"
                  : status === "done"
                    ? "#3FB95022"
                    : status === "error"
                      ? "#F8514922"
                      : isNextPending
                        ? "#A371F711"
                        : "#161B22";
                const circleBorder = isStageRunning
                  ? "2px solid #A371F7"
                  : status === "done"
                    ? "2px solid #3FB950"
                    : status === "error"
                      ? "2px solid #F85149"
                      : isNextPending
                        ? "2px dashed #A371F755"
                        : "2px solid #21262D";
                const labelColor = isStageRunning
                  ? "#E6EDF3"
                  : status === "done"
                    ? "#3FB950"
                    : status === "error"
                      ? "#F85149"
                      : isNextPending
                        ? "#A371F7"
                        : "#8B949E";

                return (
                  <div key={stage.key}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 12,
                        padding: "10px 12px",
                        margin: "2px 0",
                        borderRadius: 8,
                        opacity:
                          status === "pending" &&
                          !isNextPending &&
                          !pipelineRunning &&
                          !isStageRunning
                            ? 0.4
                            : 1,
                        background: isStageRunning
                          ? "#A371F708"
                          : "transparent",
                        transition: "all 0.2s ease",
                      }}
                    >
                      {/* Status circle — clickeable */}
                      <div
                        onClick={async (e) => {
                          e.stopPropagation();
                          if (!isClickable) return;
                          if (status === "error") {
                            restartFromStage(stage.key);
                            return;
                          }
                          if (isNextPending) {
                            restartFromStage(stage.key);
                            return;
                          }
                          if (idx === lastDone) {
                            restartFromStage(stage.key);
                          } else if (idx < lastDone) {
                            if (
                              !(await safeConfirm(
                                t("project.restartFromConfirm", {
                                  stage: t(stage.label),
                                }),
                              ))
                            )
                              return;
                            restartFromStage(stage.key);
                          }
                        }}
                        style={{
                          width: 32,
                          height: 32,
                          minWidth: 32,
                          borderRadius: "50%",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 14,
                          background: circleBg,
                          border: circleBorder,
                          cursor: isClickable ? "pointer" : "default",
                          animation: isStageRunning
                            ? "stagePulse 1.5s ease-in-out infinite"
                            : "none",
                        }}
                      >
                        {/* isStageRunning wins over "done": a completed stage
                            whose agent is being re-run must show the spinner,
                            otherwise the play/redo buttons give no feedback. */}
                        {isStageRunning ? (
                          <span
                            className="spinner"
                            style={{ width: 16, height: 16 }}
                          />
                        ) : status === "done" ? (
                          t("project.stageCheckmark")
                        ) : status === "error" ? (
                          t("project.stageCross")
                        ) : isNextPending ? (
                          <span style={{ color: "#A371F7", fontSize: 12 }}>
                            {t("project.stagePlay")}
                          </span>
                        ) : (
                          <span style={{ fontSize: 16 }}>{stage.icon}</span>
                        )}
                      </div>

                      {/* Label + chain info */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: status === "running" ? 600 : 500,
                            color: labelColor,
                            lineHeight: 1.3,
                          }}
                        >
                          {t(stage.label)}
                        </div>
                        {/* Chain descriptions */}
                        {stage.agents && stage.agents.length > 0 && (
                          <div style={{ marginTop: 4 }}>
                            <span style={{ fontSize: 9, color: "#484F58" }}>
                              {
                                stage.agents.filter(
                                  (a) =>
                                    (agentStatuses[a.id] || "pending") ===
                                    "running",
                                ).length
                              }{" "}
                              activos · {stage.agents.length} agentes
                            </span>
                          </div>
                        )}
                        {/* Special indicators per stage */}
                        {stage.key === "data_management" && (
                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: 4,
                              marginTop: 4,
                            }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <span
                              style={{
                                fontSize: 9,
                                padding: "1px 6px",
                                borderRadius: 999,
                                background:
                                  docsNeedSegment > 0
                                    ? "#D2992218"
                                    : "#3FB95018",
                                color:
                                  docsNeedSegment > 0 ? "#D29922" : "#3FB950",
                                border:
                                  docsNeedSegment > 0
                                    ? "1px solid #D2992233"
                                    : "1px solid #3FB95033",
                              }}
                            >
                              ✂️{" "}
                              {(logSummary?.total ?? docs.length) -
                                docsNeedSegment}
                              /{logSummary?.total ?? docs.length}
                            </span>
                            {docs.length > 0 && (
                              <button
                                onClick={async () => {
                                  if (
                                    !(await safeConfirm(
                                      t("project.deleteAllSegmentsConfirm"),
                                    ))
                                  )
                                    return;
                                  const auth = `Bearer ${localStorage.getItem("access_token")}`;
                                  await fetch(
                                    `/api/v1/documents/project/${id}/segments`,
                                    {
                                      method: "DELETE",
                                      headers: { Authorization: auth },
                                    },
                                  );
                                  refreshAll();
                                  setSegments({});
                                  getPipelineLog(id!)
                                    .then(setPipelineLog)
                                    .catch(() => {});
                                }}
                                style={{
                                  fontSize: 9,
                                  padding: "1px 6px",
                                  borderRadius: 999,
                                  background: "transparent",
                                  color: "#F85149",
                                  border: "1px solid #F8514933",
                                  cursor: "pointer",
                                }}
                              >
                                ✕ Segs
                              </button>
                            )}
                          </div>
                        )}
                        {stage.key === "open_coding" && (
                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: 4,
                              marginTop: 4,
                            }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <span
                              style={{
                                fontSize: 9,
                                padding: "1px 6px",
                                borderRadius: 999,
                                background:
                                  cats.length > 0 ? "#3FB95018" : "#8B949E18",
                                color: cats.length > 0 ? "#3FB950" : "#8B949E",
                                border:
                                  cats.length > 0
                                    ? "1px solid #3FB95033"
                                    : "1px solid #8B949E33",
                              }}
                            >
                              📁 {cats.length}
                            </span>
                            {cats.length > 0 && (
                              <button
                                onClick={async () => {
                                  if (
                                    !(await safeConfirm(
                                      t("project.deleteAllCatsConfirm"),
                                    ))
                                  )
                                    return;
                                  const auth = `Bearer ${localStorage.getItem("access_token")}`;
                                  await fetch(
                                    `/api/v1/projects/${id}/categories`,
                                    {
                                      method: "DELETE",
                                      headers: { Authorization: auth },
                                    },
                                  );
                                  setCats([]);
                                }}
                                style={{
                                  fontSize: 9,
                                  padding: "1px 6px",
                                  borderRadius: 999,
                                  background: "transparent",
                                  color: "#F85149",
                                  border: "1px solid #F8514933",
                                  cursor: "pointer",
                                }}
                              >
                                ✕ Cats
                              </button>
                            )}
                            {docs.some(
                              (d) => d.estado === "incidentes_extraidos",
                            ) &&
                              !docs.some((d) => d.estado === "codificando") && (
                                <button
                                  disabled={openCodingRunning}
                                  onClick={async (e) => {
                                    e.stopPropagation();
                                    setOpenCodingRunning(true);
                                    try {
                                      const auth = `Bearer ${localStorage.getItem("access_token")}`;
                                      const res = await fetch(
                                        `/api/v1/projects/${id}/pipeline/run-stage/cross_doc`,
                                        {
                                          method: "POST",
                                          headers: { Authorization: auth },
                                        },
                                      );
                                      if (!res.ok) {
                                        let detail = `HTTP ${res.status}`;
                                        try {
                                          const body = await res.json();
                                          if (body?.detail) {
                                            detail =
                                              typeof body.detail === "string"
                                                ? body.detail
                                                : JSON.stringify(body.detail);
                                          }
                                        } catch {
                                          /* non-JSON error body */
                                        }
                                        throw new Error(detail);
                                      }
                                      await refreshAll();
                                      // Refresca el log de inmediato para que la
                                      // etapa muestre el spinner sin esperar 6 s.
                                      getPipelineLog(id!)
                                        .then(setPipelineLog)
                                        .catch(() => {});
                                      showToast("Codificación en curso");
                                    } catch (err: any) {
                                      showErrorToast(
                                        "No se pudo iniciar la codificación: " +
                                          (err?.message || "error de red"),
                                      );
                                    } finally {
                                      setOpenCodingRunning(false);
                                    }
                                  }}
                                  style={{
                                    fontSize: 9,
                                    padding: "1px 6px",
                                    borderRadius: 999,
                                    background: "#58A6FF18",
                                    color: "#58A6FF",
                                    border: "1px solid #58A6FF33",
                                    cursor: openCodingRunning
                                      ? "not-allowed"
                                      : "pointer",
                                    opacity: openCodingRunning ? 0.5 : 1,
                                  }}
                                >
                                  ▶ Codificar
                                </button>
                              )}
                            <button
                              onClick={() => setOcHitlOpen(true)}
                              title="Decisión HITL: concern principal, población y categorías centrales"
                              style={{
                                fontSize: 9,
                                padding: "1px 6px",
                                borderRadius: 999,
                                background: ocHitlReady
                                  ? "#D2992218"
                                  : "#8B949E18",
                                color: ocHitlReady ? "#D29922" : "#8B949E",
                                border: ocHitlReady
                                  ? "1px solid #D2992244"
                                  : "1px solid #8B949E33",
                                cursor: "pointer",
                              }}
                            >
                              ◆ HITL
                            </button>
                            {dupRedundant > 0 && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setOcHitlOpen(true);
                                }}
                                title={`Hipótesis casi idénticas sin revisar (${dupRedundant} sobrantes en ${dupClusters} grupo(s)) — abrí el gate HITL para revisarlas y borrarlas`}
                                style={{
                                  fontSize: 9,
                                  padding: "1px 6px",
                                  borderRadius: 999,
                                  background: "#D2992218",
                                  color: "#D29922",
                                  border: "1px solid #D2992244",
                                  cursor: "pointer",
                                }}
                              >
                                ⚠ {dupRedundant} dupl.
                              </button>
                            )}
                          </div>
                        )}
                        {stage.key === "selective_coding" &&
                          (cats.some((c) => c.es_central) ||
                            dupRedundant > 0) && (
                            <div
                              style={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: 4,
                                marginTop: 4,
                              }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {cats.some((c) => c.es_central) && (
                                <span
                                  style={{
                                    fontSize: 9,
                                    padding: "1px 6px",
                                    borderRadius: 999,
                                    background: "#58A6FF18",
                                    color: "#58A6FF",
                                    border: "1px solid #58A6FF33",
                                  }}
                                >
                                  {cats.filter((c) => c.es_central).length} core
                                </span>
                              )}
                              {dupRedundant > 0 && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setOcHitlOpen(true);
                                  }}
                                  title={`Hipótesis duplicadas sin resolver (${dupRedundant} sobrantes en ${dupClusters} grupo(s)): revisalas antes de pasar a codificación selectiva`}
                                  style={{
                                    fontSize: 9,
                                    padding: "1px 6px",
                                    borderRadius: 999,
                                    background: "#D2992218",
                                    color: "#D29922",
                                    border: "1px solid #D2992244",
                                    cursor: "pointer",
                                  }}
                                >
                                  ⚠ {dupRedundant} dupl.
                                </button>
                              )}
                            </div>
                          )}
                        {stage.key === "theoretical_coding" &&
                          playgroundReady && (
                            <div style={{ marginTop: 4 }}>
                              <Link
                                to={`/projects/${id}/theory`}
                                style={{
                                  fontSize: 9,
                                  padding: "1px 6px",
                                  borderRadius: 999,
                                  background: "#3FB95018",
                                  color: "#3FB950",
                                  border: "1px solid #3FB95033",
                                  textDecoration: "none",
                                }}
                              >
                                🧪 Open
                              </Link>
                            </div>
                          )}
                      </div>
                    </div>
                    {/* Connector line to next stage */}
                    {!isLast && (
                      <div style={{ display: "flex", paddingLeft: 27 }}>
                        <div
                          style={{
                            width: 2,
                            height: 20,
                            background:
                              status === "done" ? "#3FB95044" : "#21262D",
                            borderRadius: 1,
                          }}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          )}
          <div style={{ padding: 12 }}> </div>
        </div>
      </div>
      <Toast
        message={toastMsg}
        visible={toastVisible}
        type={toastType}
        onDone={() => setToastVisible(false)}
      />
      {/* Floating confirmation bar */}
      {confirmMsg && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 1000,
            padding: "12px 24px",
            borderRadius: 10,
            background: "#161B22",
            border: "1px solid #A371F7",
            boxShadow: "0 8px 32px rgba(163,113,247,0.3)",
            display: "flex",
            alignItems: "center",
            gap: 16,
            maxWidth: "90vw",
          }}
        >
          <span style={{ color: "#E6EDF3", fontSize: 13, fontWeight: 500 }}>
            {confirmMsg}
          </span>
          <button
            onClick={() => resolveConfirm(true)}
            style={{
              padding: "6px 16px",
              borderRadius: 6,
              border: "none",
              background: "#A371F7",
              color: "#FFF",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            OK
          </button>
          <button
            onClick={() => resolveConfirm(false)}
            style={{
              padding: "6px 16px",
              borderRadius: 6,
              border: "1px solid #30363D",
              background: "transparent",
              color: "#8B949E",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
        </div>
      )}
      {createPortal(
        <AgentModal
          open={agentModalOpen}
          agentId={selectedAgentId}
          agentLabel={selectedAgentLabel}
          agentLogs={agentLogs}
          onClose={() => setAgentModalOpen(false)}
        />,
        document.body,
      )}
    </div>
  );
}
