import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  getProject,
  listDocuments,
  listCategories,
  listSegments,
  uploadDocument,
  punctuateDocument,
  deleteDocument,
  getPipelineLog,
  getAgentMemos,
  getPendingHitl,
  decideHitl,
  ping,
  clearToken,
  stopProjectPipeline,
  restartFailedTasks,
  Project,
  Document,
  Category,
  Segment,
  PipelineLog,
  DocPipelineLog,
  HitlPendingItem,
} from "../api/client";
import { MemoHistory, type MemoEntry } from "../components/MemoHistory";
import { Toast } from "../components/Toast";
import HITLModal from "../components/HITLModal";

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

// ── Pipeline stage definitions ────────────────────────────────────

interface StageDef {
  key: string;
  icon: string;
  label: string;
}

const PIPELINE_STAGES: StageDef[] = [
  { key: "segment", icon: "✂️", label: "Segmentación" },
  { key: "agents", icon: "🧠", label: "Open Coding (Agentes A)" },
  { key: "synthesis", icon: "🔗", label: "Síntesis Cross-Doc (Phase B)" },
  { key: "maturity", icon: "🔍", label: "Verificando madurez" },
  { key: "find_cc", icon: "🎯", label: "Patrón de Interés + Core Cat." },
  { key: "reduce", icon: "✂️", label: "Selective Reduction" },
  { key: "saturate", icon: "🔄", label: "Core Saturation" },
  { key: "build_db", icon: "🗄️", label: "Database A/B" },
  { key: "playground", icon: "🎨", label: "Theoretical Playground" },
];

type StageStatus = "pending" | "running" | "done" | "error";
type ViewMode = "original" | "segmented";

// ── Component ─────────────────────────────────────────────────────

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [segments, setSegments] = useState<Record<string, Segment[]>>({});
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
  const [punctStatus, setPunctStatus] = useState<Record<string, string>>({});
  const [punctRunning, setPunctRunning] = useState<string | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState("");
  const [userName, setUserName] = useState("");
  const abortRef = useRef(false);
  const originalTexts = useRef<Record<string, string>>({});

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
  const [showLog, setShowLog] = useState(false);
  const [pipelineFailed, setPipelineFailed] = useState(false);
  const [memoFilter, setMemoFilter] = useState("all");
  const [agentMemos, setAgentMemos] = useState<any[]>([]);
  const [agentFamilies, setAgentFamilies] = useState<any[]>([]);
  const [showIntermediates, setShowIntermediates] = useState(false);
  const [toastMsg, setToastMsg] = useState("");
  const [toastVisible, setToastVisible] = useState(false);
  const [pipelineLiveLogs, setPipelineLiveLogs] = useState<
    Array<{ ts: number; msg: string }>
  >([]);
  const logPanelRef = useRef<HTMLDivElement>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Auto-scroll log panel
  useEffect(() => {
    if (logPanelRef.current && showLog && pipelineLiveLogs.length > 0) {
      logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight;
    }
  }, [pipelineLiveLogs, showLog]);

  // ── HITL state ──
  const [hitlPending, setHitlPending] = useState<HitlPendingItem[]>([]);
  const [showHITLModal, setShowHITLModal] = useState(false);
  const hitlPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!id) return;
    getProject(id).then(setProject).catch(console.error);
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
        setAgentFamilies(r.families || []);
      })
      .catch((e) => console.error("agent-memos failed:", e));
  }, [id]);

  // ── Derive stage statuses from pipeline log on load ──
  useEffect(() => {
    if (!pipelineLog || pipelineRunning) return;
    const s = pipelineLog.summary;
    if (s.total === 0) return;

    setStageStatuses((prev) => {
      const next = { ...prev };

      // Segment done if no docs need segmentation
      if (s.need_segment === 0) next.segment = "done";

      // Agents done only if BOTH segment and agents are complete
      if (s.need_agents === 0 && s.need_segment === 0) {
        next.agents = "done";
      }

      // Synthesis and downstream stages done if playground_ready
      if (s.playground_ready) {
        next.synthesis = "done";
        next.find_cc = "done";
        next.reduce = "done";
        next.saturate = "done";
        next.build_db = "done";
        next.playground = "done";
      }

      // All done: every doc fully processed
      if (s.done === s.total && s.total > 0) {
        PIPELINE_STAGES.forEach((stage) => {
          next[stage.key] = "done";
        });
      }

      return next;
    });
  }, [pipelineLog, pipelineRunning]);

  // Debug: force fetch on every render if empty
  useEffect(() => {
    if (id && agentMemos.length === 0 && agentFamilies.length === 0) {
      getAgentMemos(id)
        .then((r) => {
          console.log("MEMOS RETRY:", r.total);
          setAgentMemos(r.memos || []);
          setAgentFamilies(r.families || []);
        })
        .catch((e) => console.error("retry failed:", e));
    }
  });

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

  // ── Compute stageStatuses from pipelineLog ──
  useEffect(() => {
    if (!pipelineLog) return;
    const s: Record<string, StageStatus> = {};
    const { summary } = pipelineLog;

    s.segment =
      summary.need_segment === 0 && summary.total > 0 ? "done" : "pending";
    s.agents =
      summary.need_agents === 0 && summary.total > 0 ? "done" : "pending";
    s.synthesis =
      summary.sintetizados > 0 && summary.need_synthesis === 0
        ? "done"
        : "pending";

    const ps = summary.project_state || "collecting";
    s.find_cc = [
      "finding_cc",
      "reducing",
      "saturating",
      "building_db",
      "playground_ready",
      "completed",
    ].includes(ps)
      ? "done"
      : "pending";
    s.reduce = [
      "reducing",
      "saturating",
      "building_db",
      "playground_ready",
      "completed",
    ].includes(ps)
      ? "done"
      : "pending";
    s.saturate = [
      "saturating",
      "building_db",
      "playground_ready",
      "completed",
    ].includes(ps)
      ? "done"
      : "pending";
    s.build_db = ["building_db", "playground_ready", "completed"].includes(ps)
      ? "done"
      : "pending";
    s.playground = ["playground_ready", "completed"].includes(ps)
      ? "done"
      : "pending";

    // Mark running if HITL pending for a gate
    if (hitlPending.length > 0) {
      const gate = hitlPending[0].gate_name;
      if (gate === "main_concern" || gate === "core_emergence")
        s.find_cc = "running";
      if (gate === "selective_reduction") s.reduce = "running";
      if (gate === "core_saturation") s.saturate = "running";
      if (
        gate === "database_a" ||
        gate === "database_b" ||
        gate === "global_saturation"
      )
        s.build_db = "running";
    }

    setStageStatuses(s);
  }, [pipelineLog, hitlPending]);

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
    // Per-doc override takes priority
    if (viewModeOverride[doc.id]) return viewModeOverride[doc.id];
    // If global is "segmented" but doc has no segments, fall back to original
    if (globalViewMode === "segmented" && !hasSegments(doc)) return "original";
    return globalViewMode;
  }

  // ── Preprocesar (puntuación) ────────────────────────────────────

  async function handlePunctuate(docId: string) {
    if (punctRunning === docId) {
      abortRef.current = true;
      setPunctStatus((prev) => ({ ...prev, [docId]: "⏹ Cancelado" }));
      setPunctRunning(null);
      await fetch("/api/v1/admin/workers/fast/stop", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      }).catch(() => {});
      return;
    }

    const auth = `Bearer ${localStorage.getItem("access_token")}`;
    abortRef.current = false;
    setPunctRunning(docId);
    setPunctStatus((prev) => ({ ...prev, [docId]: "⏳ Arrancando worker…" }));
    await fetch("/api/v1/admin/workers/fast/start", {
      method: "POST",
      headers: { Authorization: auth },
    });
    await new Promise((r) => setTimeout(r, 1500));
    setPunctStatus((prev) => ({ ...prev, [docId]: "⏳ Procesando…" }));
    const doc = docs.find((d) => d.id === docId);
    if (doc?.texto_extraido) {
      originalTexts.current[docId] = doc.texto_extraido;
    }
    try {
      const res = await punctuateDocument(docId);
      if (abortRef.current) return;
      if (res.status === "ok" && (res as any).changes_made) {
        setPunctStatus((prev) => ({ ...prev, [docId]: "✅ Mejorada" }));
        refreshDocs();
        setSegments((prev) => {
          const n = { ...prev };
          delete n[docId];
          return n;
        });
      } else if (res.status === "ok") {
        setPunctStatus((prev) => ({ ...prev, [docId]: "✅ OK" }));
      } else {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: "❌ " + (res.message || "Error"),
        }));
      }
    } catch (err: any) {
      if (!abortRef.current)
        setPunctStatus((prev) => ({ ...prev, [docId]: "❌ " + err.message }));
    } finally {
      if (abortRef.current)
        setPunctStatus((prev) => ({ ...prev, [docId]: "⏹ Cancelado" }));
      setPunctRunning(null);
    }
  }

  // ── Stage restart ──────────────────────────────

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
    showToast("Eliminado permanentemente.");
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
    showToast("Los cambios realizados son permanentes.");
  }

  function showToast(msg: string) {
    setToastMsg(msg);
    setToastVisible(true);
  }

  // ── Modification callback ───────────────────

  function handleMemoModified() {
    if (id) {
      getAgentMemos(id)
        .then((r) => {
          setAgentMemos(r.memos || []);
          setAgentFamilies(r.families || []);
        })
        .catch(() => {});
    }
    showToast("Modificación aplicada. Memos actualizados.");
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

    // Determine mode from pipeline log
    const isContinue = !forceAll && docsNeedSegment === 0 && docsNeedAgents > 0;

    if (isContinue) {
      resetStages({ workers: "done", segment: "done" });
      updateStage("agents", "running");
      setPipelineMsg("Continuando: solo agentes…");
    } else {
      resetStages();
      updateStage("workers", "running");
      setPipelineMsg("Iniciando workers…");
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

    // Refresh pipeline log to get current DB state
    const freshLog = await getPipelineLog(id!).catch(() => null);
    if (freshLog) setPipelineLog(freshLog);

    // Use pipeline log to determine which docs need processing
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

    if (todo.length === 0) {
      if (!isContinue) {
        updateStage("segment", "done");
      }
      updateStage("agents", "done");
      updateStage("categories", "done");
      updateStage("done", "done");
      setPipelineMsg("Todos los documentos ya están procesados.");
      setPipelineRunning(false);
      if (logPollRef.current) {
        clearInterval(logPollRef.current);
        logPollRef.current = null;
      }
      return;
    }

    // Call unified orchestrator (backend handles all docs)
    setPipelineMsg("🎯 Orquestador analizando DB…");
    if (stageStatuses.segment !== "done") {
      updateStage("segment", "running");
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

      pipelineOk = true;

      if (res.status === "no_docs") {
        setPipelineMsg("No hay documentos.");
        updateStage("segment", "done");
        updateStage("agents", "done");
      } else {
        setPipelineMsg(res.message || "Pipeline disparado");
        if (res.summary?.need_segment === 0) updateStage("segment", "done");
        if (res.summary?.need_agents === 0) {
          if ((res.summary?.need_segment ?? 1) === 0) {
            updateStage("agents", "done");
          }
        } else {
          updateStage("agents", "running");
        }

        // Phase B (synthesis) detection
        if ((res as any).task_ids?.phase_b) {
          updateStage("synthesis", "running");
          setPipelineMsg("🔗 Phase B: Síntesis cross-documento…");
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
              setPipelineMsg(`❌ Falló: ${errNames || "documento"}`);
              updateStage("segment", "error");
              updateStage("agents", "error");
              updateStage("synthesis", "error");
              setPipelineFailed(true);
              abortRef.current = true;
              break;
            }

            if (status.summary.need_segment === 0)
              updateStage("segment", "done");
            if (
              status.summary.need_agents === 0 &&
              status.summary.need_segment === 0
            )
              updateStage("agents", "done");

            // Synthesis (Phase B) completion: playground_ready = codes assigned to segments
            if (status.summary.playground_ready) {
              updateStage("synthesis", "done");
            }

            if (status.summary.done === status.summary.total) {
              setPipelineMsg("✅ Pipeline completado.");
              break;
            }
          }
          if (poll % 6 === 0) setPipelineMsg(`⏳ Procesando... (${poll * 5}s)`);
        }
      }
    } catch (e: any) {
      setPipelineMsg(`❌ ${e.message}`);
    }

    if (abortRef.current) {
      // Stop workers + rollback
      if (logPollRef.current) {
        clearInterval(logPollRef.current);
        logPollRef.current = null;
      }
      await stopProjectPipeline(id!).catch(() => {});
      if (pipelineFailed) {
        // Keep error states set during polling
        [
          "synthesis",
          "find_cc",
          "reduce",
          "saturate",
          "build_db",
          "playground",
        ].forEach((k) => updateStage(k, "error"));
      } else {
        resetStages();
        setPipelineMsg("⏹ Pipeline cancelado — DB restaurada.");
      }
    } else if (pipelineOk) {
      // Pipeline completed normally
      updateStage("segment", "done");
      updateStage("agents", "done");
      updateStage("synthesis", "done");
      updateStage("categories", "done");
      updateStage("done", "done");
      setPipelineMsg("✅ Pipeline completado.");
    }

    refreshDocs();
    listCategories(id!).then(setCats);
    getPipelineLog(id!)
      .then(setPipelineLog)
      .catch(() => {});
    getAgentMemos(id!)
      .then((r) => {
        setAgentMemos(r.memos || []);
        setAgentFamilies(r.families || []);
      })
      .catch(() => {});
    setPipelineRunning(false);
  }

  // ── Upload ───────────────────────────────────────

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !id) return;
    try {
      await uploadDocument(id, file);
      refreshDocs();
    } catch (err: any) {
      alert(err.message);
    }
    e.target.value = "";
  }

  function handleLogout() {
    clearToken();
    navigate("/login");
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
  const nextStageKey = docsNeedSegment > 0 ? "segment" : "agents";
  const nextStage = PIPELINE_STAGES.find((s) => s.key === nextStageKey)!;
  const nextStageCount =
    nextStageKey === "segment" ? docsNeedSegment : docsNeedAgents;

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
    const log = getDocLog(doc.id);
    if (!log) {
      // Fallback
      switch (doc.estado) {
        case "listo":
          return { text: "✓ Listo", color: "#3FB950", bg: "#3FB95022" };
        case "segmentado":
          return { text: "✂️ Segmentado", color: "#3FB950", bg: "#3FB95022" };
        case "error":
          return { text: "✕ Error", color: "#F85149", bg: "#F8514922" };
        default:
          return { text: "⬜ Crudo", color: "#8B949E", bg: "#8B949E22" };
      }
    }
    // Use real log data
    if (log.steps.agents_done && log.steps.coded)
      return { text: "✓ Listo", color: "#3FB950", bg: "#3FB95022" };
    if (log.steps.segmented && !log.steps.coded)
      return { text: "✂️ Segmentado", color: "#D29922", bg: "#D2992222" };
    if (log.steps.segmented)
      return { text: "✂️ Segmentado", color: "#3FB950", bg: "#3FB95022" };
    if (log.steps.text_extracted)
      return { text: "📄 Con texto", color: "#58A6FF", bg: "#58A6FF22" };
    return { text: "⬜ Crudo", color: "#8B949E", bg: "#8B949E22" };
  }

  if (!project)
    return <p style={{ padding: 40, color: "#8B949E" }}>Cargando…</p>;

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
              ← Proyectos
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
              Salir
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
              🛑 Decisión requerida:{" "}
              <strong>
                {hitlPending[0].gate_name === "main_concern"
                  ? "Main Concern"
                  : hitlPending[0].gate_name === "core_emergence"
                    ? "Core Category"
                    : hitlPending[0].gate_name === "selective_reduction"
                      ? "Selective Reduction"
                      : hitlPending[0].gate_name === "core_saturation"
                        ? "Core Saturation"
                        : hitlPending[0].gate_name === "database_a"
                          ? "Database A — Nodes"
                          : hitlPending[0].gate_name === "database_b"
                            ? "Database B — Edges"
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
              Resolver
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
                🎨 Theoretical Playground listo — el modelo teórico está
                completo
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
                Entrar
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
              <span
                style={{
                  fontSize: 10,
                  padding: "2px 8px",
                  borderRadius: 999,
                  background:
                    docsDone === docs.length && docs.length > 0
                      ? "#3FB95022"
                      : "#8B949E22",
                  color:
                    docsDone === docs.length && docs.length > 0
                      ? "#3FB950"
                      : "#8B949E",
                  border: `1px solid ${docsDone === docs.length && docs.length > 0 ? "#3FB95033" : "#8B949E33"}`,
                }}
              >
                ✓ {docsDone} listo{docsDone !== 1 ? "s" : ""}
              </span>
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
                  ✂️ {docsNeedSegment} por segmentar
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
                  🧠 {docsNeedAgents} por agentes
                </span>
              )}
              <span
                style={{
                  fontSize: 10,
                  padding: "2px 8px",
                  borderRadius: 999,
                  background: cats.length > 0 ? "#A371F722" : "#8B949E22",
                  color: cats.length > 0 ? "#A371F7" : "#8B949E",
                  border: `1px solid ${cats.length > 0 ? "#A371F733" : "#8B949E33"}`,
                }}
              >
                🏷️ {cats.length}
              </span>
              <span
                style={{
                  fontSize: 10,
                  padding: "2px 8px",
                  borderRadius: 999,
                  fontWeight: 600,
                  background: playgroundReady ? "#3FB95022" : "#D2992222",
                  color: playgroundReady ? "#3FB950" : "#D29922",
                  border: `1px solid ${playgroundReady ? "#3FB95033" : "#D2992233"}`,
                }}
              >
                {playgroundReady ? "✅ Playground" : "🔒 Sin cats"}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {/* Global view switch */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0,
                  background: "#0D1117",
                  borderRadius: 6,
                  border: "1px solid #21262D",
                  overflow: "hidden",
                }}
              >
                <button
                  onClick={() => {
                    setGlobalViewMode("original");
                    setViewModeOverride({});
                  }}
                  style={{
                    padding: "3px 10px",
                    border: "none",
                    fontSize: 11,
                    cursor: "pointer",
                    background:
                      globalViewMode === "original" ? "#A371F7" : "transparent",
                    color: globalViewMode === "original" ? "#FFF" : "#8B949E",
                  }}
                >
                  📄 Orig
                </button>
                <button
                  onClick={() => {
                    setGlobalViewMode("segmented");
                    setViewModeOverride({});
                  }}
                  style={{
                    padding: "3px 10px",
                    border: "none",
                    fontSize: 11,
                    cursor: "pointer",
                    background:
                      globalViewMode === "segmented"
                        ? "#A371F7"
                        : "transparent",
                    color: globalViewMode === "segmented" ? "#FFF" : "#8B949E",
                  }}
                >
                  ✂️ Seg
                </button>
              </div>

              {/* Delete all segments */}
              <button
                onClick={async () => {
                  if (
                    !confirm(
                      "¿Eliminar TODOS los segmentos del proyecto? Los docs volverán a estado crudo.",
                    )
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
                title="Eliminar todos los segmentos y resetear docs"
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
                🗑️ Segs
              </button>

              {/* Playground link */}
              <Link
                to={`/projects/${id}/theory`}
                onClick={(e) => {
                  if (!playgroundReady) e.preventDefault();
                }}
                title={
                  playgroundReady
                    ? "Explorar el modelo teórico"
                    : "Necesitás ejecutar el pipeline primero"
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
                {playgroundReady ? "🧪 Playground →" : "🔒 Playground"}
              </Link>

              {/* Status pills inline */}
              {/* Log toggle */}
            </div>
          </div>

          {/* ── Upload ─────────────────────────────────── */}
          <div style={{ marginBottom: 20 }}>
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
              📎 Subir documento (PDF, TXT, DOCX)
              <input
                type="file"
                accept=".pdf,.txt,.docx"
                style={{ display: "none" }}
                onChange={handleUpload}
              />
            </label>
          </div>

          {/* ── Documents ──────────────────────────────── */}
          <h3 style={{ marginBottom: 12 }}>Documentos ({docs.length})</h3>
          {docs.length === 0 && (
            <p style={{ color: "#8B949E", fontSize: 13 }}>
              Sin documentos. Subí un archivo para empezar.
            </p>
          )}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {docs.map((d) => {
              const docHasSegs = hasSegments(d);
              const currentView = docViewMode(d);
              return (
                <li
                  key={d.id}
                  style={{
                    marginBottom: 8,
                    padding: "10px 14px",
                    background: "#161B22",
                    borderRadius: 8,
                    border: "1px solid #21262D",
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
                        {d.mime_type}
                      </span>
                      {/* Estado badge from log */}
                      {(() => {
                        const badge = getEstadoBadge(d);
                        return (
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
                        );
                      })()}
                      {punctStatus[d.id] && (
                        <span
                          style={{
                            fontSize: 11,
                            color: punctStatus[d.id].startsWith("✅")
                              ? "#3FB950"
                              : "#8B949E",
                          }}
                        >
                          {punctStatus[d.id]}
                        </span>
                      )}
                    </div>
                    <div
                      style={{ display: "flex", gap: 6, alignItems: "center" }}
                    >
                      <button
                        onClick={() => toggleSegments(d.id)}
                        style={btnSmall}
                      >
                        {expandedDoc === d.id ? "Ocultar texto" : "Ver texto"}
                      </button>
                      <button
                        onClick={() => handlePunctuate(d.id)}
                        disabled={d.estado !== "crudo" && punctRunning !== d.id}
                        title={
                          d.estado !== "crudo"
                            ? "No se puede preprocesar después de segmentar"
                            : "Mejorar puntuación del texto"
                        }
                        style={{
                          ...btnSmall,
                          background:
                            d.estado !== "crudo" && punctRunning !== d.id
                              ? "#21262D"
                              : punctRunning === d.id
                                ? "#F85149"
                                : "#A371F7",
                          color:
                            d.estado !== "crudo" && punctRunning !== d.id
                              ? "#484F58"
                              : "#FFF",
                          cursor:
                            d.estado !== "crudo" && punctRunning !== d.id
                              ? "not-allowed"
                              : "pointer",
                        }}
                      >
                        {punctRunning === d.id
                          ? "⏹ Cancelar"
                          : d.estado !== "crudo"
                            ? "✨ Preprocesar"
                            : "✨ Preprocesar"}
                      </button>
                      {punctRunning !== d.id && originalTexts.current[d.id] && (
                        <button
                          onClick={async () => {
                            const orig = originalTexts.current[d.id];
                            if (!orig || !confirm("¿Restaurar texto original?"))
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
                              [d.id]: "↩ Restaurado",
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
                          ↩ Deshacer
                        </button>
                      )}
                      <button
                        onClick={async () => {
                          if (!confirm("¿Eliminar?")) return;
                          await deleteDocument(d.id);
                          refreshDocs();
                        }}
                        style={{ ...btnSmall, color: "#F85149" }}
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* ── Expanded text view ── */}
                  {expandedDoc === d.id && (
                    <div style={{ marginTop: 8 }}>
                      {/* Per-doc override toggle (shows when doc has segments) */}
                      {docHasSegs && (
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            marginBottom: 8,
                          }}
                        >
                          <span style={{ fontSize: 11, color: "#8B949E" }}>
                            Este documento:
                          </span>
                          <button
                            onClick={() =>
                              setViewModeOverride((prev) => ({
                                ...prev,
                                [d.id]: "original",
                              }))
                            }
                            style={{
                              padding: "3px 10px",
                              borderRadius: 4,
                              border: "1px solid #21262D",
                              background:
                                currentView === "original"
                                  ? "#A371F7"
                                  : "#1C2333",
                              color: "#E6EDF3",
                              fontSize: 11,
                              cursor: "pointer",
                            }}
                          >
                            Original
                          </button>
                          <button
                            onClick={() =>
                              setViewModeOverride((prev) => ({
                                ...prev,
                                [d.id]: "segmented",
                              }))
                            }
                            style={{
                              padding: "3px 10px",
                              borderRadius: 4,
                              border: "1px solid #21262D",
                              background:
                                currentView === "segmented"
                                  ? "#A371F7"
                                  : "#1C2333",
                              color: "#E6EDF3",
                              fontSize: 11,
                              cursor: "pointer",
                            }}
                          >
                            Segmentos ({segments[d.id]?.length || "?"})
                          </button>
                          {viewModeOverride[d.id] && (
                            <button
                              onClick={() =>
                                setViewModeOverride((prev) => {
                                  const n = { ...prev };
                                  delete n[d.id];
                                  return n;
                                })
                              }
                              style={{
                                fontSize: 10,
                                color: "#8B949E",
                                background: "none",
                                border: "none",
                                cursor: "pointer",
                                textDecoration: "underline",
                              }}
                            >
                              usar global
                            </button>
                          )}
                        </div>
                      )}
                      <textarea
                        readOnly
                        disabled={punctRunning === d.id}
                        style={{
                          width: "100%",
                          minHeight: 150,
                          fontFamily: "monospace",
                          fontSize: 13,
                          background: "#0D1117",
                          color: "#E6EDF3",
                          border: "1px solid #21262D",
                          borderRadius: 6,
                          padding: 8,
                          resize: "vertical",
                        }}
                        value={
                          currentView === "segmented" && segments[d.id]?.length
                            ? segments[d.id]!.map(
                                (s) => `[${s.posicion}] ${s.texto}`,
                              ).join("\n\n")
                            : d.texto_extraido || "(sin texto disponible)"
                        }
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          <hr style={{ borderColor: "#21262D", margin: "24px 0" }} />

          {/* ── Categories ─────────────────────────────── */}
          <h3 style={{ marginBottom: 12 }}>Categorías ({cats.length})</h3>
          {cats.length === 0 && (
            <p style={{ color: "#8B949E", fontSize: 13 }}>
              Sin categorías aún. Ejecutá el Pipeline IA para generarlas.
            </p>
          )}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {cats.map((c) => (
              <li
                key={c.id}
                style={{
                  marginBottom: 8,
                  padding: "10px 14px",
                  background: "#161B22",
                  borderRadius: 8,
                  border: "1px solid #21262D",
                }}
              >
                <strong>
                  {c.nombre}
                  {c.es_central && " ⭐"}
                </strong>
                <br />
                <span style={{ fontSize: 13, color: "#8B949E" }}>
                  {c.definicion}
                </span>
              </li>
            ))}
          </ul>

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
                📝 Historial de Memos
              </span>
              <span style={{ fontSize: 11, color: "#484F58" }}>
                {pipelineLog?.documents?.length || 0} docs · {agentMemos.length}{" "}
                memos · {agentFamilies.length} familias
              </span>
            </div>

            <MemoHistory
              memos={agentMemos}
              families={agentFamilies}
              activeFilter={memoFilter}
              showIntermediates={showIntermediates}
              onFilterChange={setMemoFilter}
              onToggleIntermediates={setShowIntermediates}
              onDeleteMemo={handleDeleteMemo}
              onUpdateMemo={handleUpdateMemo}
              projectId={id!}
              originalPrompt={project.ruta_de_codificacion || ""}
              onMemoModified={handleMemoModified}
            />
          </div>
        </div>

        {/* ── End Left Column ── */}
      </div>

      {/* ── Left: Pipeline Flow Panel ── */}
      <div
        style={{
          width: 340,
          flexShrink: 0,
          borderRight: "1px solid #21262D",
          background: "#161B22",
          padding: "16px 14px",
          overflowY: "auto",
          maxHeight: "100vh",
          position: "sticky",
          top: 0,
        }}
      >
        {/* Pipeline Flow — inline */}
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 14,
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 600, color: "#8B949E" }}>
              {showLog ? "📋 Logs" : "🔄 Flujo del Pipeline"}
            </span>
            <button
              onClick={() => setShowLog(!showLog)}
              style={{
                background: "#21262D",
                border: "1px solid #30363D",
                borderRadius: 6,
                color: "#8B949E",
                fontSize: 11,
                padding: "3px 8px",
                cursor: "pointer",
              }}
            >
              {showLog ? "📊 Diagrama" : "📋 Logs"}
            </button>
            {!pipelineRunning && (
              <button
                onClick={() => runPipeline(false)}
                disabled={docs.length === 0}
                style={{
                  background: "linear-gradient(135deg, #A371F7, #3FB950)",
                  border: "none",
                  borderRadius: 6,
                  color: "#FFF",
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "4px 12px",
                  cursor: docs.length === 0 ? "not-allowed" : "pointer",
                  opacity: docs.length === 0 ? 0.5 : 1,
                }}
              >
                ▶
              </button>
            )}
            {pipelineRunning && (
              <button
                onClick={() => {
                  abortRef.current = true;
                  if (logPollRef.current) {
                    clearInterval(logPollRef.current);
                    logPollRef.current = null;
                  }
                }}
                style={{
                  background: "#F8514922",
                  border: "1px solid #F8514944",
                  borderRadius: 6,
                  color: "#F85149",
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "4px 8px",
                  cursor: "pointer",
                }}
              >
                ⏹
              </button>
            )}
          </div>

          {pipelineMsg && (
            <div
              style={{
                fontSize: 11,
                color: pipelineFailed ? "#F85149" : "#8B949E",
                marginBottom: 12,
                padding: "6px 10px",
                background: pipelineFailed ? "#F8514922" : "#21262D",
                borderRadius: 6,
                border: `1px solid ${pipelineFailed ? "#F8514944" : "#30363D"}`,
              }}
            >
              {pipelineMsg}
            </div>
          )}

          {showLog ? (
            /* ── Live Log Panel ── */
            <div
              ref={logPanelRef}
              style={{
                background: "#0D1117",
                borderRadius: 6,
                border: "1px solid #21262D",
                padding: 8,
                maxHeight: 400,
                overflowY: "auto",
                fontSize: 10,
                fontFamily: "monospace",
                marginBottom: 12,
              }}
            >
              {pipelineLiveLogs.length === 0 && (
                <span style={{ color: "#484F58" }}>Sin logs aún…</span>
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
                  <div
                    key={i}
                    style={{
                      padding: "1px 0",
                      color,
                    }}
                  >
                    <span style={{ color: "#484F58" }}>
                      {new Date(l.ts * 1000).toLocaleTimeString()}
                    </span>{" "}
                    {msg}
                  </div>
                );
              })}
            </div>
          ) : (
            <>
              {PIPELINE_STAGES.map((stage, idx) => {
                const status = stageStatuses[stage.key] || "pending";
                const isLast = idx === PIPELINE_STAGES.length - 1;
                const lastDone = findLastCompletedIdx();
                const isNextPending =
                  status === "pending" && idx === lastDone + 1;
                const isClickable =
                  !pipelineRunning &&
                  (status === "done" || status === "error" || isNextPending);
                return (
                  <div key={stage.key}>
                    <div
                      onClick={() => {
                        if (!isClickable) return;
                        if (status === "error") {
                          restartFromStage(stage.key);
                          return;
                        }
                        if (isNextPending) {
                          // Next pending after last done → start from here
                          restartFromStage(stage.key);
                          return;
                        }
                        // status === "done"
                        if (idx === lastDone) {
                          // Clicking last completed: restart from here
                          restartFromStage(stage.key);
                        } else if (idx < lastDone) {
                          // Clicking earlier completed: warn
                          if (
                            !confirm(
                              `¿Reiniciar desde "${stage.label}"? Se eliminarán datos de etapas posteriores.`,
                            )
                          )
                            return;
                          restartFromStage(stage.key);
                        }
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        padding: "8px 0",
                        cursor: isClickable ? "pointer" : "default",
                        opacity:
                          status === "pending" &&
                          !isNextPending &&
                          !pipelineRunning
                            ? 0.5
                            : 1,
                      }}
                    >
                      <div
                        style={{
                          width: 24,
                          height: 24,
                          borderRadius: "50%",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 12,
                          flexShrink: 0,
                          background:
                            status === "done"
                              ? "#3FB95022"
                              : status === "running"
                                ? "#A371F722"
                                : status === "error"
                                  ? "#F8514922"
                                  : isNextPending
                                    ? "#A371F711"
                                    : "#21262D",
                          border:
                            status === "running"
                              ? "2px solid #A371F7"
                              : status === "done"
                                ? "2px solid #3FB950"
                                : status === "error"
                                  ? "2px solid #F85149"
                                  : isNextPending
                                    ? "2px dashed #A371F755"
                                    : "2px solid #30363D",
                          animation:
                            status === "running"
                              ? "pulse 1.5s ease-in-out infinite"
                              : "none",
                        }}
                      >
                        {status === "done" ? (
                          "✓"
                        ) : status === "error" ? (
                          "✕"
                        ) : status === "running" ? (
                          <span
                            style={{
                              display: "inline-block",
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: "#A371F7",
                            }}
                          />
                        ) : isNextPending ? (
                          <span style={{ color: "#A371F7", fontSize: 10 }}>
                            ▶
                          </span>
                        ) : (
                          <span style={{ color: "#8B949E", fontSize: 11 }}>
                            {stage.icon}
                          </span>
                        )}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: 12,
                            fontWeight: status === "running" ? 600 : 400,
                            color:
                              status === "done"
                                ? "#3FB950"
                                : status === "running"
                                  ? "#E6EDF3"
                                  : status === "error"
                                    ? "#F85149"
                                    : isNextPending
                                      ? "#A371F7"
                                      : "#8B949E",
                          }}
                        >
                          {stage.label}
                        </div>
                      </div>
                      <span
                        style={{
                          fontSize: 9,
                          color:
                            status === "done"
                              ? "#3FB950"
                              : status === "running"
                                ? "#A371F7"
                                : status === "error"
                                  ? "#F85149"
                                  : isNextPending
                                    ? "#A371F7"
                                    : "#484F58",
                        }}
                      >
                        {status === "done"
                          ? "✓"
                          : status === "running"
                            ? "…"
                            : status === "error"
                              ? "✕"
                              : isNextPending
                                ? "▶"
                                : "○"}
                      </span>
                    </div>
                    {!isLast && (
                      <div style={{ display: "flex", paddingLeft: 11 }}>
                        <div
                          style={{
                            width: 1,
                            height: 10,
                            background:
                              status === "done" ? "#3FB950" : "#21262D",
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
        </div>
      </div>
      <Toast
        message={toastMsg}
        visible={toastVisible}
        onDone={() => setToastVisible(false)}
      />
    </div>
  );
}
