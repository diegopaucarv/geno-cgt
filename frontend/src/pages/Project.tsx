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
  resetDocsToCrudo,
  restoreDocumentOriginal,
  getPipelineLog,
  getAgentMemos,
  getPendingHitl,
  decideHitl,
  ping,
  clearToken,
  stopProjectPipeline,
  restartFailedTasks,
  updateProject,
  updatePopulationAssumption,
  generatePopulationGeneralization,
  getStaleUserEntities,
  Project,
  Document,
  Category,
  Segment,
  PipelineLog,
  DocPipelineLog,
  HitlPendingItem,
} from "../api/client";
import {
  MemoHistory,
  type MemoEntry,
  DeleteByTypeButton,
} from "../components/MemoHistory";
import { Toast } from "../components/Toast";
import HITLModal from "../components/HITLModal";
import AddMemoModal from "../components/AddMemoModal";
import ProjectConfigPanel from "../components/ProjectConfigPanel";
import PipelineAgents from "../components/PipelineAgents";
import AgentModal from "../components/AgentModal";
import { getAgentLogs, type AgentLogEntry } from "../api/client";
import { PIPELINE_STAGES, FAMILY_COLORS } from "../config/pipelineChains";

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
type ViewMode = "original" | "segmented";

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
    op: "punctuate" | "classify" | "segment";
  } | null>(null);

  // ── Modular cancel: each operation reverts ONLY its own step ──
  // punctuate: restore → crudo
  // classify:  clear classified text → preprocesado
  // segment:   delete segs → clasificado
  const OP_ROLLBACK: Record<
    string,
    Array<"restore" | "deleteSegs" | "clearClassified">
  > = {
    punctuate: ["restore"],
    classify: ["clearClassified"],
    segment: ["deleteSegs"],
  };

  // ── Unified agent state definitions ──
  // Each per-doc agent: input estado (what it consumes), output estado (what it produces).
  // canRun = docs exist in input state. done = no docs in input state AND some docs at output+.
  const PER_DOC_AGENTS = {
    util_punctuator: { input: "crudo", output: "preprocesado" },
    fa_glaser_data_classifier: { input: "preprocesado", output: "clasificado" },
    segmentar_documento: { input: "clasificado", output: "segmentado" },
  } as const;

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
    const t = punctTaskRef.current;
    setPunctRunning(null);
    punctTaskRef.current = null;
    if (t) {
      await fetch(`/api/v1/admin/tasks/${t}/cancel`, {
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
    refreshDocs();
  }

  /** Unified task dispatch + poll + refresh. All per-doc handlers and the
   *  sidebar dispatchAgentLoop delegate to this. */
  async function runDocTask(
    docId: string,
    endpoint: string,
    signal: { current: boolean },
  ): Promise<"success" | "failed" | "aborted" | "timeout"> {
    console.log("[runDocTask] POST", endpoint, "docId:", docId);
    const token = `Bearer ${localStorage.getItem("access_token")}`;
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: token,
      },
      body: JSON.stringify({ document_id: docId }),
    }).then((r) => r.json());

    const taskId = res.task_id;
    punctTaskRef.current = taskId;
    if (!taskId) {
      refreshDocs();
      return "success";
    }

    for (let i = 0; i < 60 && !signal.current; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const ts = await getTaskStatus(taskId);
        if (ts.status === "SUCCESS") {
          refreshDocs();
          return "success";
        }
        if (ts.status === "FAILURE") return "failed";
      } catch {
        /* polling error, keep trying */
      }
    }
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
    // Try native confirm first
    const start = performance.now();
    const ok = window.confirm(msg);
    if (ok || performance.now() - start > 100) {
      return Promise.resolve(ok);
    }
    // Native confirm blocked — show floating bar
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

  // ── Global view switch ──
  const [globalViewMode, setGlobalViewMode] = useState<ViewMode>("original");
  // Per-doc overrides (only used when user explicitly toggles a doc)
  const [viewModeOverride, setViewModeOverride] = useState<
    Record<string, ViewMode>
  >({});

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
    "stages" | "agents" | "logs"
  >("agents");
  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([]);
  /** Ephemeral: agent IDs currently executing (pulse animation).
   *  Set on play, cleared on finish/abort. NOT derived from docs. */
  const [runningAgentIds, setRunningAgentIds] = useState<Set<string>>(
    new Set(),
  );
  /** Synthesized: "running" if in runningAgentIds, else "pending".
   *  PipelineAgents derives done/canRun from agentDocCounts internally. */
  const agentStatuses: Record<
    string,
    "pending" | "running" | "done" | "error"
  > = {};
  for (const agentId of Object.keys(PER_DOC_AGENTS)) {
    agentStatuses[agentId] = runningAgentIds.has(agentId)
      ? "running"
      : "pending";
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
  const [textEdits, setTextEdits] = useState<Record<string, string>>({});
  const [textSaving, setTextSaving] = useState<Record<string, boolean>>({});

  // ── Per-document error state (for routing retries) ──
  const [docError, setDocError] = useState<
    Record<string, { action: string; message: string }>
  >({});

  // ── Drag-and-drop state ──
  const dragDoc = useRef<string | null>(null);

  // ── Agent execution state ──
  const [completedAgents, setCompletedAgents] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem("gt_completed_agents");
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
      const raw = localStorage.getItem("gt_iterations");
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

  // Persist completed agents to localStorage
  useEffect(() => {
    localStorage.setItem(
      "gt_completed_agents",
      JSON.stringify([...completedAgents]),
    );
  }, [completedAgents]);

  useEffect(() => {
    localStorage.setItem("gt_iterations", JSON.stringify(iterations));
  }, [iterations]);

  // ── Text view mode (original / preprocesado / clasificado / segmented / incidents) ──
  const [textViewMode, setTextViewMode] = useState<
    "original" | "preprocessed" | "classified" | "segmented" | "incidents"
  >("original");

  const hitlPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

      // data_management: done if no docs need segmentation
      if (summary.need_segment === 0 && summary.total > 0)
        setIfForward("data_management", "done");

      // open_coding: done if need_agents === 0 && need_segment === 0
      if (
        summary.need_agents === 0 &&
        summary.need_segment === 0 &&
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

  function refreshDocs() {
    if (!id) return;
    listDocuments(id).then(setDocs).catch(console.error);
  }

  async function toggleSegments(docId: string) {
    if (expandedDoc === docId) {
      setExpandedDoc(null);
      return;
    }
    setExpandedDoc(docId);
    // Always reload segments when expanding
    const segs = await listSegments(docId).catch(() => []);
    setSegments((prev) => ({ ...prev, [docId]: segs }));
  }

  function hasSegments(doc: Document): boolean {
    // Check loaded segments first
    if (segments[doc.id] && segments[doc.id].length > 0) return true;
    // Check pipeline log (real DB state)
    const log = getDocLog(doc.id);
    if (log && log.segments_count > 0) return true;
    return false;
  }

  // Resolve view mode for a specific document
  function docViewMode(doc: Document): ViewMode {
    if (viewModeOverride[doc.id]) return viewModeOverride[doc.id];
    if (globalViewMode === "segmented" && !hasSegments(doc)) return "original";
    return globalViewMode;
  }

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

  /** API call + poll until Celery task completes. Keeps punctRunning alive. */
  async function punctuateSingleDoc(docId: string) {
    console.log("[punctuateSingleDoc] starting for", docId);
    setPunctStatus((prev) => ({
      ...prev,
      [docId]: t("project.preprocessingProcessing"),
    }));
    const doc = docs.find((d) => d.id === docId);
    if (doc?.texto_extraido) {
      originalTexts.current[docId] = doc.texto_extraido;
    }
    try {
      const res = await punctuateDocument(docId);
      console.log("[punctuateSingleDoc] response for", docId, ":", res);
      if (abortRef.current) return;

      if (res.status === "ok" && !res.task_id) {
        // Backend determined no punctuation needed — already well-punctuated.
        // Backend now sets estado='preprocesado' even without changes.
        refreshDocs();
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingOK"),
        }));
        return;
      }

      if (res.task_id) {
        // Task dispatched — poll until completion
        punctTaskRef.current = res.task_id;
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingProcessing") + "…",
        }));
        for (let poll = 0; poll < 60 && !abortRef.current; poll++) {
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
              const changed =
                output && typeof output === "object" && output.changes_made;
              if (changed) {
                setPunctStatus((prev) => ({
                  ...prev,
                  [docId]: t("project.preprocessingImproved"),
                }));
                refreshDocs();
                setSegments((prev) => {
                  const n = { ...prev };
                  delete n[docId];
                  return n;
                });
              } else {
                setPunctStatus((prev) => ({
                  ...prev,
                  [docId]: t("project.preprocessingOK"),
                }));
              }
              return;
            }
            if (ts.status === "FAILURE") {
              setPunctStatus((prev) => ({
                ...prev,
                [docId]:
                  t("project.preprocessingError") + (ts.result?.error || ""),
              }));
              showErrorToast(
                "Error del worker de preprocesado: " +
                  (ts.result?.error || "Fallo interno"),
              );
              return;
            }
            // Still PENDING/STARTED — keep waiting
          } catch {
            // polling error, keep trying
          }
        }
        // Timeout after 120s
        if (!abortRef.current) {
          setPunctStatus((prev) => ({
            ...prev,
            [docId]: t("project.preprocessingError") + "Timeout",
          }));
          showErrorToast("Timeout: el preprocesado no respondio en 120s");
        }
        return;
      }

      // Fallback: old-style response
      if (res.status === "ok" && (res as any).changes_made) {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingImproved"),
        }));
        refreshDocs();
        setSegments((prev) => {
          const n = { ...prev };
          delete n[docId];
          return n;
        });
      } else if (res.status === "ok") {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingOK"),
        }));
      } else {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingError") + (res.message || ""),
        }));
      }
    } catch (err: any) {
      if (!abortRef.current) {
        console.error("[punctuateSingleDoc] error for", docId, ":", err);
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: t("project.preprocessingError") + (err.message || ""),
        }));
        showErrorToast(
          "Error de API al preprocesar: " +
            (err.message || "Sin respuesta del servidor"),
        );
      }
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
        setPunctStatus((prev) => ({
          ...prev,
          [doc.id]: t("project.preprocessingStarting"),
        }));
        await punctuateSingleDoc(doc.id);
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
          .then(() => refreshDocs())
          .catch(() => {});
      }
      return;
    }

    abortRef.current = false;
    setRunningOps((prev) => ({ ...prev, [docId]: "punctuate" }));
    setPunctStatus((prev) => ({
      ...prev,
      [docId]: t("project.preprocessingStarting"),
    }));

    try {
      await punctuateSingleDoc(docId);
      markAgentDone("preprocesado");
      setDocError((prev) => {
        const n = { ...prev };
        delete n[docId];
        return n;
      });
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
    }
  }

  /** Render classified XML text: tags as tiny labels, content colored per type. */
  function renderClassifiedText(xmlText: string): string {
    if (!xmlText) return '<span style="color:#484F58">Sin clasificacion</span>';
    var tagColors: Record<string, string> = {
      baseline_data: "#3FB950",
      interviewer_context: "#D29922",
      processual_data: "#58A6FF",
      contextual_data: "#8B949E",
    };
    var escaped = xmlText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    var tagNames = Object.keys(tagColors);
    for (var i = 0; i < tagNames.length; i++) {
      var tag = tagNames[i];
      var color = tagColors[tag];
      var openTag = "&lt;" + tag + "&gt;";
      var closeTag = "&lt;/" + tag + "&gt;";
      var tagLabel =
        '<span style="font-size:9px;color:' +
        color +
        ';opacity:0.6;font-weight:600">' +
        tag +
        "</span>";
      var parts = escaped.split(openTag);
      var result2 = parts[0];
      for (var j = 1; j < parts.length; j++) {
        var closeIdx = parts[j].indexOf(closeTag);
        if (closeIdx >= 0) {
          var inner = parts[j].substring(0, closeIdx);
          var after = parts[j].substring(closeIdx + closeTag.length);
          result2 +=
            '<div style="margin:6px 0;padding:6px 8px;border-left:3px solid ' +
            color +
            ";background:" +
            color +
            '11;border-radius:0 4px 4px 0">' +
            '<div style="margin-bottom:3px">' +
            tagLabel +
            "</div>" +
            '<span style="color:' +
            color +
            ';line-height:1.6">' +
            inner +
            "</span>" +
            "</div>" +
            after;
        } else {
          result2 += openTag + parts[j];
        }
      }
      escaped = result2;
    }
    return escaped;
  }

  /** Classify a single document via Glaser classifier (3-step + validator loop) */
  async function handleClassify(docId: string) {
    const doc = docs.find((x) => x.id === docId);
    if (!doc || doc.estado !== "preprocesado") return;
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
          .then(() => refreshDocs())
          .catch(() => {});
      }
      return;
    }

    abortRef.current = false;
    setPunctRunning(docId);
    runningOp.current = { docId, op: "classify" };
    setPunctStatus((prev) => ({ ...prev, [docId]: "Clasificando…" }));

    try {
      const token = `Bearer ${localStorage.getItem("access_token")}`;
      const res = await fetch(`/api/v1/documents/${docId}/classify-glaser`, {
        method: "POST",
        headers: { Authorization: token },
      }).then((r) => r.json());

      if (res.task_id) {
        punctTaskRef.current = res.task_id;
        for (let poll = 0; poll < 60 && !abortRef.current; poll++) {
          await new Promise((r) => setTimeout(r, 2000));
          try {
            const ts = await getTaskStatus(res.task_id);
            if (ts.status === "SUCCESS") {
              markAgentDone("clasificado");
              // ── Final refresh after completion ──
              refreshDocs();
              setPunctStatus((prev) => ({ ...prev, [docId]: "✓ Clasificado" }));
              return;
            }
            if (ts.status === "FAILURE") {
              setPunctStatus((prev) => ({
                ...prev,
                [docId]: "Error de clasificación",
              }));
              return;
            }
          } catch {}
        }
        if (!abortRef.current) {
          showErrorToast("Timeout: clasificación no respondió en 120s");
        }
      } else {
        // Synchronous completion — no task_id
        markAgentDone("clasificado");
        refreshDocs();
        setPunctStatus((prev) => ({ ...prev, [docId]: "✓ Clasificado" }));
      }
    } catch (e: any) {
      if (!abortRef.current) {
        showErrorToast("Error: " + (e.message || ""));
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: "Error: " + (e.message || ""),
        }));
      }
    } finally {
      runningOp.current = null;
      setPunctRunning(null);
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

  /** Route action based on doc estado */
  async function handleDocAction(docId: string) {
    console.log("[handleDocAction] docId:", docId, "estado:", docs.find((x) => x.id === docId)?.estado);
    const d = docs.find((x) => x.id === docId);
    if (!d) return;

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
      return;
    }

    // Cancel running operation (modular)
    if (punctRunning === docId) {
      await cancelRunningOp(docId);
      return;
    }

    // Route action based on document estado
    switch (d.estado) {
      case "crudo":
        return handlePunctuate(docId);
      case "preprocesado":
        return handleClassify(docId);
      case "clasificado":
        return handleSegment(docId);
      case "segmentado":
        // Trigger incident extraction (F2.3) via the pipeline orchestrator
        return handleExtractIncidents(docId);
      default:
        return;
    }
  }

  /** Trigger F2.3: extract patterns & incidents */
  async function handleExtractIncidents(docId: string) {
    abortRef.current = false;
    setPunctRunning(docId);
    runningOp.current = { docId, op: "segment" as const };
    try {
      await runDocTask(
        docId,
        `/api/v1/projects/${id}/pipeline/run-agent/extract_patterns`,
        abortRef,
      );
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
      await runDocTask(
        docId,
        `/api/v1/projects/${id}/pipeline/run-agent/segmentar_documento`,
        abortRef,
      );
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

  /** Restore one step back based on current estado.
   *  Chain: crudo -> preprocesado -> clasificado -> segmentado -> ...
   *  Each step undoes exactly one layer, clears stage_progress, and
   *  syncs the sidebar agent status. */
  async function handleRestoreStep(docId: string) {
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
        await fetch(`/api/v1/documents/${docId}/classify-glaser`, {
          method: "DELETE",
          headers: { Authorization: token },
        }).catch(() => {});
        clearAgentsFrom("clasificado");
      } else if (doc.estado === "segmentado") {
        await deleteDocumentSegments(docId).catch(() => {});
        clearAgentsFrom("segmentado");
      } else if (
        doc.estado === "incidentes_extraidos" ||
        doc.estado === "procesado" ||
        doc.estado === "listo"
      ) {
        // For post-segmentation states: restore to crudo (full reset)
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
      refreshDocs();
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

  async function handleDeleteMemo(memoId: string) {
    const token = localStorage.getItem("access_token");
    await fetch(`/api/v1/agent-outputs/${memoId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    setAgentMemos((prev) => prev.filter((m) => m.id !== memoId));
    showToast(t("project.memoDeleted"));
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
    const newText = textEdits[docId];
    if (newText === undefined) return;
    setTextSaving((prev) => ({ ...prev, [docId]: true }));
    try {
      var field = "texto_original";
      if (textViewMode === "preprocessed") field = "texto_preprocesado";
      else if (textViewMode === "classified") field = "texto_clasificado";
      await fetch(`/api/v1/documents/${docId}/text`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({ [field]: newText }),
      });
      setTextEdits((prev) => {
        const next = { ...prev };
        delete next[docId];
        return next;
      });
      refreshDocs();
    } catch (e: any) {
      showErrorToast("Error al guardar: " + (e.message || ""));
    } finally {
      setTextSaving((prev) => ({ ...prev, [docId]: false }));
    }
  }

  // ── Modification callback ───────────────────

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
    const isContinue = !forceAll && docsNeedSegment === 0 && docsNeedAgents > 0;

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

        // Poll until complete
        for (let poll = 0; poll < 120 && !abortRef.current; poll++) {
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
    } else if (pipelineOk) {
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
      alert(err.message);
    }
    e.target.value = "";
  }

  async function handleDeleteAllDocs() {
    if (!id) return;
    if (!(await safeConfirm(t("project.deleteAllDocsConfirm")))) return;
    try {
      const result = await deleteAllDocuments(id);
      showToast(t("project.deleteAllDocsSuccess", { count: result.count }));
      refreshDocs();
      resetStages();
    } catch (err: any) {
      alert(err.message);
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
  const docsNeedAgents = logSummary?.need_agents ?? 0;
  const docsDone = logSummary?.done ?? 0;
  const docsPendientes = docsNeedSegment + docsNeedAgents;
  const pipelineParcial = docsDone > 0 && docsPendientes > 0;
  const playgroundReady = logSummary?.playground_ready ?? cats.length > 0;

  // Next pipeline stage (dynamic, from PIPELINE_STAGES)
  const nextStageKey = docsNeedSegment > 0 ? "data_management" : "open_coding";
  const nextStage = PIPELINE_STAGES.find((s) => s.key === nextStageKey)!;
  const nextStageCount =
    nextStageKey === "data_management" ? docsNeedSegment : docsNeedAgents;

  function getDocLog(docId: string): DocPipelineLog | undefined {
    return pipelineLog?.documents.find((d) => d.document_id === docId);
  }

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
    if (runningOps[doc.id]) {
      const op = runningOps[doc.id];
      if (op === "classify") {
        return { text: "Clasificando…", color: "#3FB950", bg: "#3FB95022" };
      }
      if (op === "segment") {
        return { text: "Segmentando…", color: "#58A6FF", bg: "#58A6FF22" };
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
                  refreshDocs();
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
            <h3 style={{ margin: 0 }}>
              {t("project.documentsHeading", { count: docs.length })}
            </h3>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {docs.length > 0 && (
                <>
                  <button
                    onClick={async () => {
                      if (!(await safeConfirm(t("project.resetDocsConfirm"))))
                        return;
                      resetDocsToCrudo(id!).then(() => refreshDocs());
                    }}
                    style={{
                      background: "#D2992218",
                      border: "1px solid #D2992233",
                      borderRadius: 6,
                      color: "#D29922",
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "3px 10px",
                      cursor: "pointer",
                    }}
                    title={t("project.resetDocsTitle")}
                  >
                    {t("project.resetDocsButton")}
                  </button>
                  <button
                    onClick={handleDeleteAllDocs}
                    style={{
                      background: "#F8514918",
                      border: "1px solid #F8514933",
                      borderRadius: 6,
                      color: "#F85149",
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "3px 10px",
                      cursor: "pointer",
                    }}
                    title={t("project.deleteAllDocsTitle")}
                  >
                    {t("project.deleteAllDocsButton")}
                  </button>
                </>
              )}
            </div>
          </div>
          <ul style={{ listStyle: "none", padding: 0 }}>
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
                      {/* Unified per-document action button */}
                      {(() => {
                        const isRunning = punctRunning === d.id;
                        const estado = d.estado;
                        const err = docError[d.id];
                        const hasText = !!(
                          (d as any).texto_original || d.texto_extraido
                        );
                        const isCrudo = estado === "crudo";
                        const isProcesado =
                          estado === "incidentes_extraidos" ||
                          estado === "procesado" ||
                          estado === "listo";
                        const isCodificado = estado === "codificado";

                        const label = err
                          ? "\u26A0 Reintentar"
                          : isRunning
                            ? t("project.cancelPreprocess")
                            : isCrudo
                              ? t("project.preprocessButton")
                              : estado === "preprocesado"
                                ? "Clasificar"
                                : estado === "clasificado"
                                  ? "Segmentar"
                                  : estado === "segmentado"
                                    ? "Extraer incidentes"
                                    : isProcesado
                                      ? "\u2713 Incidentes extra\u00eddos"
                                      : isCodificado
                                        ? "\u2713 Codificado"
                                        : "\u2713 Completo";
                        const bg = err
                          ? "#F85149"
                          : isRunning
                            ? "#F85149"
                            : isCrudo
                              ? hasText
                                ? "#A371F7"
                                : "#30363D"
                              : estado === "preprocesado"
                                ? "#3FB950"
                                : estado === "clasificado"
                                  ? "#58A6FF"
                                  : estado === "segmentado"
                                    ? "#D29922"
                                    : "#3FB950";
                        const disabled =
                          !err &&
                          ((isCrudo && !hasText && !isRunning) ||
                            isProcesado ||
                            isCodificado);

                        return (
                          <button
                            onClick={() => handleDocAction(d.id)}
                            disabled={disabled}
                            style={{
                              ...btnSmall,
                              background: bg,
                              color: "#FFF",
                              border: "none",
                              cursor: disabled ? "not-allowed" : "pointer",
                            }}
                          >
                            {label}
                          </button>
                        );
                      })()}
                      {/* Restore: hidden while running; same rollback as cancel but at rest */}
                      {d.estado !== "crudo" && punctRunning !== d.id && (
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            await handleRestoreStep(d.id);
                          }}
                          title="Restaurar a estado original"
                          style={{
                            ...btnSmall,
                            background: "transparent",
                            color: "#D29922",
                            border: "1px solid #D2992244",
                            fontSize: 14,
                            padding: "2px 8px",
                            lineHeight: 1,
                          }}
                        >
                          {"\u21BB"}
                        </button>
                      )}
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
                            refreshDocs();
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
                      <button
                        onClick={async () => {
                          if (!(await safeConfirm(t("project.deleteConfirm"))))
                            return;
                          try {
                            await deleteDocument(d.id);
                            refreshDocs();
                          } catch (e: any) {
                            showErrorToast(
                              "Error al eliminar: " + (e.message || ""),
                            );
                          }
                        }}
                        style={{ ...btnSmall, color: "#F85149" }}
                      >
                        {t("project.deleteIcon")}
                      </button>
                    </div>
                  </div>

                  {/* ── Expanded text view ── */}
                  {expandedDoc === d.id && (
                    <div style={{ marginTop: 8 }}>
                      {
                        <div
                          onClick={(e) => {
                            e.stopPropagation();
                          }}
                          style={{ display: "flex", gap: 4, marginBottom: 4 }}
                        >
                          {(
                            [
                              "original",
                              "preprocessed",
                              "classified",
                              "segmented",
                              "incidents",
                            ] as const
                          ).map((mode) => {
                            const hasIt =
                              mode === "original"
                                ? true
                                : mode === "preprocessed"
                                  ? !!(d as any).texto_preprocesado
                                  : mode === "classified"
                                    ? !!(d as any).texto_clasificado
                                    : mode === "segmented"
                                      ? !!(
                                          segments[d.id] &&
                                          segments[d.id].length > 0
                                        )
                                      : !!(
                                          (d as any).metadatos &&
                                          (d as any).metadatos.document_signals
                                        );
                            const isActive = textViewMode === mode;
                            const lbl =
                              mode === "original"
                                ? "\uD83D\uDCC4 Original"
                                : mode === "preprocessed"
                                  ? "\uD83D\uDCDD Preprocesado"
                                  : mode === "classified"
                                    ? "\uD83C\uDFF7\uFE0F Clasificado"
                                    : mode === "segmented"
                                      ? "\u2702\uFE0F Segmentado"
                                      : "\uD83D\uDD0D Incidentes";
                            return (
                              <span
                                key={mode}
                                onClick={() => hasIt && setTextViewMode(mode)}
                                style={{
                                  fontSize: 10,
                                  padding: "2px 8px",
                                  borderRadius: 10,
                                  cursor: hasIt ? "pointer" : "not-allowed",
                                  background: isActive ? "#A371F7" : "#1C2333",
                                  color: isActive
                                    ? "#FFF"
                                    : hasIt
                                      ? "#8B949E"
                                      : "#484F58",
                                  border:
                                    "1px solid " +
                                    (isActive ? "#A371F7" : "#30363D"),
                                  opacity: hasIt ? 1 : 0.4,
                                  userSelect: "none",
                                  transition: "all 0.15s",
                                }}
                              >
                                {lbl}
                              </span>
                            );
                          })}
                        </div>
                      }
                      {/* Unified text viewer — same style for all modes */}
                      {textEdits[d.id] !== undefined ? (
                        <textarea
                          disabled={punctRunning === d.id}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) =>
                            setTextEdits((prev) => ({
                              ...prev,
                              [d.id]: e.target.value,
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
                          value={textEdits[d.id]}
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
                              textViewMode === "classified"
                                ? renderClassifiedText(
                                    (d as any).texto_clasificado ||
                                      ((d as any).metadatos &&
                                        (d as any).metadatos
                                          .texto_clasificado) ||
                                      "",
                                  )
                                : textViewMode === "segmented" &&
                                    segments[d.id]?.length
                                  ? segments[d.id]!.map(
                                      (s) => `[${s.posicion}] ${s.texto}`,
                                    )
                                      .join("\n\n")
                                      .replace(/&/g, "&amp;")
                                      .replace(/</g, "&lt;")
                                      .replace(/>/g, "&gt;")
                                  : textViewMode === "preprocessed"
                                    ? (
                                        (d as any).texto_preprocesado ||
                                        d.texto_extraido ||
                                        ""
                                      )
                                        .replace(/&/g, "&amp;")
                                        .replace(/</g, "&lt;")
                                        .replace(/>/g, "&gt;")
                                    : (
                                        (d as any).texto_original ||
                                        d.texto_extraido ||
                                        ""
                                      )
                                        .replace(/&/g, "&amp;")
                                        .replace(/</g, "&lt;")
                                        .replace(/>/g, "&gt;")
                                        .replace(/\n/g, "<br>"),
                          }}
                        />
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
                            {textSaving[d.id] ? "Guardando…" : "✓ Guardar"}
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
                            Descartar
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          <hr style={{ borderColor: "#21262D", margin: "24px 0" }} />

          {/* ── HITL Modal ── */}
          <style>{`
        body {
          background: #0D1117;
          margin: 0;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        @keyframes stagePulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(163,113,247,0.4); }
          50% { opacity: 0.5; box-shadow: 0 0 0 6px rgba(163,113,247,0); }
        }
      `}</style>

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
                refreshDocs();
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
                {/* Delete buttons */}
                {memoFilter !== "all" && (
                  <DeleteByTypeButton
                    projectId={id!}
                    tipo={memoFilter}
                    onDeleted={() => setMemoFilter("all")}
                  />
                )}
                {memoFilter === "all" && agentMemos.length > 0 && (
                  <DeleteByTypeButton
                    projectId={id!}
                    tipo="all"
                    label={t("project.deleteAllMemos")}
                    onDeleted={() => {}}
                  />
                )}
              </div>
            </div>

            <MemoHistory
              memos={agentMemos}
              activeFilter={memoFilter}
              onFilterChange={setMemoFilter}
              onDeleteMemo={handleDeleteMemo}
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
          ) : sidebarViewMode === "agents" ? (
            <PipelineAgents
              agentStatuses={agentStatuses}
              onRunAgent={async (agentId) => {
                console.log("[PipelineAgents] run", agentId);
                const auth = `Bearer ${localStorage.getItem("access_token")}`;
                const perDocAgents = new Set([
                  "util_punctuator",
                  "fa_glaser_data_classifier",
                  "segmentar_documento",
                ]);
                if (perDocAgents.has(agentId)) {
                  // ── Helper: clear previous work and restart ──
                  const clearAndRestart = async (agent: string) => {
                    // Clear HITL
                    await fetch(`/api/v1/projects/${id}/hitl/reset`, {
                      method: "POST",
                      headers: {
                        Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                      },
                    }).catch(() => {});
                    // Preprocessor: revert all preprocessed docs BEFORE filtering
                    if (agent === "util_punctuator") {
                      const preprocessed = docs.filter(
                        (d) => d.estado === "preprocesado",
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
                    // Delete segments if segmenter or downstream
                    if (agent !== "util_punctuator") {
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
                      ];
                      const idx = agentOrder.indexOf(agent);
                      if (idx >= 0) {
                        for (let i = idx; i < agentOrder.length; i++) {
                          next.delete(agentOrder[i]);
                        }
                      }
                      return next;
                    });
                    // Re-filter: all docs not yet at or beyond this agent's output
                    const out = PER_DOC_AGENTS[agent].output;
                    const resetEligible = freshDocs.filter((d) => {
                      const hasText = !!(
                        (d as any).texto_preprocesado ||
                        (d as any).texto_original ||
                        d.texto_extraido
                      );
                      return (
                        hasText &&
                        !(BEYOND[out] || []).includes(d.estado)
                      );
                    });
                    dispatchAgentLoop(resetEligible);
                  };

                  // Determine which docs are eligible = all docs not yet at or beyond output
                  const eligible = docs.filter((d) => {
                    return !(BEYOND[PER_DOC_AGENTS[agentId].output] || []).includes(
                      d.estado,
                    );
                  });

                  // ── Build a single confirmation message ──
                  // 1. What layers will be wiped?
                  const agentOrder = [
                    "util_punctuator",
                    "fa_glaser_data_classifier",
                    "segmentar_documento",
                  ];
                  const myIdx = agentOrder.indexOf(agentId);
                  const wipedAgents =
                    myIdx >= 0 ? agentOrder.slice(myIdx) : [];
                  const wipeLabels: string[] = [];
                  if (wipedAgents.includes("segmentar_documento"))
                    wipeLabels.push("segmentos");
                  if (wipedAgents.includes("fa_glaser_data_classifier"))
                    wipeLabels.push("texto clasificado");
                  if (wipedAgents.includes("util_punctuator"))
                    wipeLabels.push("texto preprocesado");

                  // 2. How many docs need the prerequisite?
                  const missingPrereq = docs.filter(
                    (d) => d.estado !== PER_DOC_AGENTS[agentId].input,
                  ).length;

                  // 3. Build message
                  let confirmMsg2 = "";
                  if (wipeLabels.length > 0) {
                    confirmMsg2 +=
                      "Se eliminaran: " + wipeLabels.join(", ") + ". ";
                  }
                  if (missingPrereq > 0) {
                    const fallbackLabel =
                      agentId === "fa_glaser_data_classifier"
                        ? "texto original"
                        : agentId === "segmentar_documento"
                          ? "texto preprocesado u original"
                          : "sin procesar";
                    confirmMsg2 +=
                      missingPrereq +
                      " de " +
                      docs.length +
                      " docs no estan en estado '" +
                      PER_DOC_AGENTS[agentId].input +
                      "'. Se usara " +
                      fallbackLabel +
                      ". ";
                  }
                  confirmMsg2 +=
                    "Se procesaran " +
                    eligible.length +
                    " documento(s). Continuar?";
                  const ok = await safeConfirm(confirmMsg2);
                  if (!ok) return;

                  // ── Wipe downstream layers before running ──
                  await clearAndRestart(agentId);

async function dispatchAgentLoop(
                    docsToProcess: typeof eligible,
                  ) {
                    abortRef.current = false;
                    setRunningAgentIds((prev) => new Set([...prev, agentId]));
                    for (const doc of docsToProcess) {
                      if (abortRef.current) break;
                      await runDocTask(
                        doc.id,
                        `/api/v1/projects/${id}/pipeline/run-agent/${agentId}`,
                        abortRef,
                      );
                    }
                    // Per-doc agent finished its loop — clear running state.
                    // PipelineAgents will recompute canRun/done from docs[].estado.
                    runningTaskRef.current = null;
                    setRunningAgentIds((prev) => {
                      const next = new Set(prev);
                      next.delete(agentId);
                      return next;
                    });
                    refreshDocs();
                  }
                } else {
                  // Project-level agent
                  setRunningAgentIds((prev) => new Set([...prev, agentId]));
                  fetch(
                    `/api/v1/projects/${id}/pipeline/run-agent/${agentId}`,
                    {
                      method: "POST",
                      headers: {
                        "Content-Type": "application/json",
                        Authorization: auth,
                      },
                      body: JSON.stringify({}),
                    },
                  )
                    .then(() => {
                      setRunningAgentIds((prev) => {
                        const next = new Set(prev);
                        next.delete(agentId);
                        return next;
                      });
                      setCompletedAgents((prev) => new Set([...prev, agentId]));
                    })
                    .catch((e) =>
                      showErrorToast("Error al ejecutar agente: " + e.message),
                    );
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
                  .then(() => refreshDocs())
                  .catch(() => {});
                setRunningAgentIds((prev) => {
                  const next = new Set(prev);
                  next.delete(agentId);
                  return next;
                });
              }}
              pipelineRunning={pipelineRunning}
              completedAgents={completedAgents}
              iterations={iterations}
              agentDocCounts={Object.fromEntries(
                Object.entries(PER_DOC_AGENTS).map(
                  ([agentId, { input, output }]) => [
                    agentId,
                    {
                      done: docs.filter((d) =>
                        (BEYOND[output] || []).includes(d.estado),
                      ).length,
                      total: docs.length,
                    },
                  ],
                ),
              )}
              eligibleDocCounts={Object.fromEntries(
                Object.entries(PER_DOC_AGENTS).map(([agentId, { output }]) => [
                  agentId,
                  docs.filter(
                    (d) => !(BEYOND[output] || []).includes(d.estado),
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
                const isClickable =
                  !pipelineRunning &&
                  (status === "done" || status === "error" || isNextPending);

                const circleBg =
                  status === "done"
                    ? "#3FB95022"
                    : status === "running"
                      ? "#A371F722"
                      : status === "error"
                        ? "#F8514922"
                        : isNextPending
                          ? "#A371F711"
                          : "#161B22";
                const circleBorder =
                  status === "running"
                    ? "2px solid #A371F7"
                    : status === "done"
                      ? "2px solid #3FB950"
                      : status === "error"
                        ? "2px solid #F85149"
                        : isNextPending
                          ? "2px dashed #A371F755"
                          : "2px solid #21262D";
                const labelColor =
                  status === "done"
                    ? "#3FB950"
                    : status === "running"
                      ? "#E6EDF3"
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
                          !pipelineRunning
                            ? 0.4
                            : 1,
                        background:
                          status === "running" ? "#A371F708" : "transparent",
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
                          animation:
                            status === "running"
                              ? "stagePulse 1.5s ease-in-out infinite"
                              : "none",
                        }}
                      >
                        {status === "done" ? (
                          t("project.stageCheckmark")
                        ) : status === "error" ? (
                          t("project.stageCross")
                        ) : status === "running" ? (
                          <span
                            style={{
                              display: "inline-block",
                              width: 10,
                              height: 10,
                              borderRadius: "50%",
                              background: "#A371F7",
                            }}
                          />
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
                                  refreshDocs();
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
                          </div>
                        )}
                        {stage.key === "selective_coding" &&
                          cats.some((c) => c.es_central) && (
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
                                  background: "#58A6FF18",
                                  color: "#58A6FF",
                                  border: "1px solid #58A6FF33",
                                }}
                              >
                                {cats.filter((c) => c.es_central).length} core
                              </span>
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
