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
  { key: "find_cc", icon: "🎯", label: "Core Category Detection" },
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
  const [showPipelineOverlay, setShowPipelineOverlay] = useState(false);
  const [stoppingWorkers, setStoppingWorkers] = useState(false);

  // ── Global view switch ──
  const [globalViewMode, setGlobalViewMode] = useState<ViewMode>("original");
  // Per-doc overrides (only used when user explicitly toggles a doc)
  const [viewModeOverride, setViewModeOverride] = useState<
    Record<string, ViewMode>
  >({});

  // ── Execution log ──
  const [showLog, setShowLog] = useState(false);
  const [pipelineLiveLogs, setPipelineLiveLogs] = useState<
    Array<{ ts: number; msg: string }>
  >([]);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
  }, [id]);

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
    setShowPipelineOverlay(true);
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
    let pipelineFailed = false;

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

        // Poll until complete
        for (let poll = 0; poll < 120 && !abortRef.current; poll++) {
          await new Promise((r) => setTimeout(r, 5000));
          const status = await getPipelineLog(id!).catch(() => null);
          if (status) {
            setPipelineLog(status);
          }
          if (status?.summary) {
            // ── Failure detection ──
            if (status.summary.failed > 0) {
              const errNames = (status.summary.errors || [])
                .map((e: { filename: string }) => e.filename)
                .join(", ");
              setPipelineMsg(`❌ Falló: ${errNames || "documento"}`);
              updateStage("segment", "error");
              updateStage("agents", "error");
              pipelineFailed = true;
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
        updateStage("categories", "error");
        updateStage("done", "error");
      } else {
        resetStages();
        setPipelineMsg("⏹ Pipeline cancelado — DB restaurada.");
      }
    } else if (pipelineOk) {
      // Pipeline completed normally
      updateStage("segment", "done");
      updateStage("agents", "done");
      updateStage("categories", "done");
      updateStage("done", "done");
      setPipelineMsg("✅ Pipeline completado.");
    }

    refreshDocs();
    listCategories(id!).then(setCats);
    getPipelineLog(id!)
      .then(setPipelineLog)
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
        maxWidth: 960,
        margin: "0 auto",
        padding: "0 24px 40px",
        background: "#0D1117",
        minHeight: "100vh",
        color: "#E6EDF3",
        position: "relative",
      }}
    >
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
          <button onClick={handleLogout} style={{ ...btnSmall, fontSize: 11 }}>
            Salir
          </button>
        </div>
      </div>

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
                    globalViewMode === "segmented" ? "#A371F7" : "transparent",
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

            {/* Re-open pipeline overlay */}
            {!showPipelineOverlay && pipelineLiveLogs.length > 0 && (
              <button
                onClick={() => setShowPipelineOverlay(true)}
                title="Ver último log del pipeline"
                style={{
                  padding: "3px 8px",
                  borderRadius: 6,
                  border: "1px solid #A371F744",
                  background: "#A371F722",
                  color: "#A371F7",
                  fontSize: 11,
                  cursor: "pointer",
                }}
              >
                📜 Log
              </button>
            )}

            {/* Log toggle */}
            <button
              onClick={() => setShowLog(!showLog)}
              style={{
                padding: "3px 10px",
                borderRadius: 6,
                border: "1px solid #21262D",
                background: showLog ? "#A371F722" : "#1C2333",
                color: showLog ? "#A371F7" : "#8B949E",
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              📋 {docs.length > 0 ? `(${docsDone}/${docs.length})` : ""}
            </button>
          </div>
        </div>

        {/* Row 2: Log (collapsible) */}
        {showLog && docs.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 3,
              paddingTop: 4,
              borderTop: "1px solid #21262D",
            }}
          >
            {docs.map((d) => {
              const badge = getEstadoBadge(d);
              const log = getDocLog(d.id);
              return (
                <div
                  key={d.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "3px 6px",
                    borderRadius: 3,
                    background: "#0D1117",
                    fontSize: 11,
                  }}
                >
                  <span
                    style={{
                      color: "#E6EDF3",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      flex: 1,
                      marginRight: 8,
                    }}
                  >
                    {d.original_filename}
                  </span>
                  <span
                    style={{ display: "flex", gap: 4, alignItems: "center" }}
                  >
                    {log?.segments_count ? (
                      <span style={{ fontSize: 9, color: "#8B949E" }}>
                        {log.segments_count} seg
                      </span>
                    ) : null}
                    {log?.codes_count ? (
                      <span style={{ fontSize: 9, color: "#8B949E" }}>
                        {log.codes_count} cod
                      </span>
                    ) : null}
                    <span
                      style={{
                        fontSize: 9,
                        padding: "1px 6px",
                        borderRadius: 999,
                        background: badge.bg,
                        color: badge.color,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {badge.text}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Row 3: Pipeline buttons */}
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            flexWrap: "wrap",
            justifyContent: "flex-start",
            paddingTop: 4,
            borderTop: "1px solid #21262D",
          }}
        >
          {pipelineRunning ? (
            <button
              onClick={() => {
                abortRef.current = true;
                setStageStatuses((prev) => {
                  const n = { ...prev };
                  Object.keys(n).forEach((k) => {
                    if (n[k] === "running") n[k] = "error";
                  });
                  return n;
                });
                setPipelineRunning(false);
                setShowPipelineOverlay(false);
                setPipelineMsg("⏹ Cancelado.");
                if (logPollRef.current) {
                  clearInterval(logPollRef.current);
                  logPollRef.current = null;
                }
              }}
              style={{
                padding: "8px 20px",
                borderRadius: 6,
                border: "1px solid #F8514944",
                background: "#F8514922",
                color: "#F85149",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              ⏹ Cancelar pipeline
            </button>
          ) : docsNeedAgents > 0 ? (
            <>
              <button
                onClick={() => runPipeline(false)}
                disabled={docs.length === 0}
                style={{
                  padding: "10px 24px",
                  borderRadius: 6,
                  border: "none",
                  cursor: "pointer",
                  background: "linear-gradient(135deg, #3FB950, #58A6FF)",
                  color: "#FFF",
                  fontSize: 14,
                  fontWeight: 600,
                  boxShadow: "0 2px 12px rgba(63,185,80,0.3)",
                }}
              >
                {`▶ ${nextStage.icon} ${nextStage.label} (${nextStageCount} doc${nextStageCount !== 1 ? "s" : ""})`}
              </button>
              <button
                onClick={() => {
                  if (confirm("¿Re-ejecutar TODO desde cero?"))
                    runPipeline(true);
                }}
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "1px solid #F8514944",
                  background: "transparent",
                  color: "#F85149",
                  fontSize: 11,
                  cursor: "pointer",
                }}
              >
                🔄 Forzar todo
              </button>
            </>
          ) : (
            <>
              {docs.length > 0 && (
                <button
                  onClick={() => runPipeline(false)}
                  disabled={docs.length === 0}
                  style={{
                    padding: "10px 24px",
                    borderRadius: 6,
                    border: "none",
                    cursor: "pointer",
                    background: "linear-gradient(135deg, #A371F7, #3FB950)",
                    color: "#FFF",
                    fontSize: 14,
                    fontWeight: 600,
                    boxShadow: "0 4px 24px rgba(163,113,247,0.3)",
                  }}
                >
                  🧠 Ejecutar Pipeline IA
                </button>
              )}
              {docsDone > 0 && (
                <button
                  onClick={() => {
                    if (confirm("¿Re-ejecutar desde cero?")) runPipeline(true);
                  }}
                  style={{
                    padding: "6px 12px",
                    borderRadius: 6,
                    border: "1px solid #F8514944",
                    background: "transparent",
                    color: "#F85149",
                    fontSize: 11,
                    cursor: "pointer",
                  }}
                >
                  🔄 Re-ejecutar
                </button>
              )}
            </>
          )}
          {pipelineMsg && pipelineRunning && (
            <span style={{ fontSize: 11, color: "#A371F7" }}>
              {pipelineMsg}
            </span>
          )}
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
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <button onClick={() => toggleSegments(d.id)} style={btnSmall}>
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
                            currentView === "original" ? "#A371F7" : "#1C2333",
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
                            currentView === "segmented" ? "#A371F7" : "#1C2333",
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

      {/* ══════════════════════════════════════════════════════════════
          ── PIPELINE STAGE OVERLAY (Vercel v0 style) ───────────────
          ══════════════════════════════════════════════════════════════ */}
      {showPipelineOverlay && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0,0,0,0.7)",
            backdropFilter: "blur(4px)",
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget && !pipelineRunning) {
              setShowPipelineOverlay(false);
            }
          }}
        >
          <div
            style={{
              display: "flex",
              gap: 16,
              maxWidth: 900,
              maxHeight: "80vh",
            }}
          >
            <div
              style={{
                background: "#161B22",
                border: "1px solid #21262D",
                borderRadius: 16,
                padding: "32px 40px",
                minWidth: 420,
                maxWidth: 500,
                boxShadow: "0 16px 48px rgba(0,0,0,0.5)",
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                }}
              >
                <h2
                  style={{
                    margin: "0 0 8px",
                    fontSize: 18,
                    fontWeight: 700,
                    color: "#E6EDF3",
                    textAlign: "center",
                    flex: 1,
                  }}
                >
                  {pipelineRunning
                    ? "Ejecutando Pipeline IA"
                    : pipelineMsg.includes("✅")
                      ? "Pipeline Completado"
                      : pipelineMsg.includes("⏹")
                        ? "Pipeline Detenido"
                        : "Pipeline Finalizado"}
                </h2>
                {!pipelineRunning && (
                  <button
                    onClick={() => setShowPipelineOverlay(false)}
                    style={{
                      padding: "2px 8px",
                      borderRadius: 4,
                      border: "1px solid #30363D",
                      background: "transparent",
                      color: "#8B949E",
                      fontSize: 16,
                      cursor: "pointer",
                      lineHeight: 1,
                    }}
                  >
                    ✕
                  </button>
                )}
              </div>
              <p
                style={{
                  margin: "0 0 24px",
                  fontSize: 12,
                  color: "#8B949E",
                  textAlign: "center",
                }}
              >
                {pipelineMsg}
              </p>

              <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                {PIPELINE_STAGES.map((stage, idx) => {
                  const status = stageStatuses[stage.key] || "pending";
                  const isLast = idx === PIPELINE_STAGES.length - 1;
                  return (
                    <div key={stage.key}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 14,
                          padding: "12px 0",
                        }}
                      >
                        <div
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: "50%",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 16,
                            flexShrink: 0,
                            background:
                              status === "done"
                                ? "#3FB95022"
                                : status === "running"
                                  ? "#A371F722"
                                  : status === "error"
                                    ? "#F8514922"
                                    : "#21262D",
                            border:
                              status === "running"
                                ? "2px solid #A371F7"
                                : status === "done"
                                  ? "2px solid #3FB950"
                                  : status === "error"
                                    ? "2px solid #F85149"
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
                                width: 12,
                                height: 12,
                                borderRadius: "50%",
                                background: "#A371F7",
                              }}
                            />
                          ) : (
                            <span style={{ color: "#8B949E", fontSize: 14 }}>
                              {stage.icon}
                            </span>
                          )}
                        </div>

                        <div style={{ flex: 1 }}>
                          <div
                            style={{
                              fontSize: 14,
                              fontWeight: status === "running" ? 600 : 400,
                              color:
                                status === "done"
                                  ? "#3FB950"
                                  : status === "running"
                                    ? "#E6EDF3"
                                    : status === "error"
                                      ? "#F85149"
                                      : "#8B949E",
                            }}
                          >
                            {stage.label}
                          </div>
                        </div>

                        <span
                          style={{
                            fontSize: 11,
                            color:
                              status === "done"
                                ? "#3FB950"
                                : status === "running"
                                  ? "#A371F7"
                                  : status === "error"
                                    ? "#F85149"
                                    : "#484F58",
                          }}
                        >
                          {status === "done"
                            ? "Completado"
                            : status === "running"
                              ? "En progreso…"
                              : status === "error"
                                ? "Error"
                                : "Pendiente"}
                        </span>
                      </div>

                      {!isLast && (
                        <div style={{ display: "flex", paddingLeft: 15 }}>
                          <div
                            style={{
                              width: 2,
                              height: 16,
                              background:
                                status === "done"
                                  ? "#3FB950"
                                  : status === "running"
                                    ? "linear-gradient(to bottom, #A371F7, #21262D)"
                                    : "#21262D",
                              borderRadius: 1,
                            }}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {pipelineRunning ? (
                <div style={{ textAlign: "center", marginTop: 24 }}>
                  <button
                    onClick={async () => {
                      setStoppingWorkers(true);
                      abortRef.current = true;
                      // Clear polling
                      if (logPollRef.current) {
                        clearInterval(logPollRef.current);
                        logPollRef.current = null;
                      }
                      if (id) {
                        await stopProjectPipeline(id).catch(() => {});
                      }
                      // Reset ALL stages — DB was rolled back
                      resetStages();
                      setPipelineRunning(false);
                      setStoppingWorkers(false);
                      setPipelineMsg("⏹ Pipeline detenido — DB restaurada.");
                    }}
                    disabled={stoppingWorkers}
                    style={{
                      padding: "10px 28px",
                      borderRadius: 8,
                      border: "1px solid #F8514944",
                      background: stoppingWorkers ? "#F8514910" : "#F8514922",
                      color: "#F85149",
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: stoppingWorkers ? "wait" : "pointer",
                      opacity: stoppingWorkers ? 0.6 : 1,
                    }}
                  >
                    {stoppingWorkers
                      ? "⏳ Deteniendo…"
                      : "⏹ Detener todos los workers"}
                  </button>
                </div>
              ) : (
                <div style={{ textAlign: "center", marginTop: 24 }}>
                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      justifyContent: "center",
                      flexWrap: "wrap",
                    }}
                  >
                    <button
                      onClick={() => setShowPipelineOverlay(false)}
                      style={{
                        padding: "8px 24px",
                        borderRadius: 6,
                        border: "1px solid #21262D",
                        background: "#1C2333",
                        color: "#E6EDF3",
                        fontSize: 13,
                        cursor: "pointer",
                      }}
                    >
                      Cerrar
                    </button>
                    <button
                      onClick={async () => {
                        if (!id) return;
                        if (
                          !confirm(
                            "¿Reintentar todas las tareas fallidas del último pipeline?",
                          )
                        )
                          return;
                        await restartFailedTasks(id).catch(() => {});
                        setPipelineMsg("🔄 Reintentando tareas fallidas…");
                        refreshDocs();
                        getPipelineLog(id!)
                          .then(setPipelineLog)
                          .catch(() => {});
                      }}
                      style={{
                        padding: "8px 16px",
                        borderRadius: 6,
                        border: "1px solid #D2992233",
                        background: "#D2992222",
                        color: "#D29922",
                        fontSize: 12,
                        cursor: "pointer",
                      }}
                    >
                      🔄 Reintentar fallidas
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Live log panel */}
            {pipelineLiveLogs.length > 0 && (
              <div
                style={{
                  background: "#0D1117",
                  border: "1px solid #21262D",
                  borderRadius: 16,
                  padding: "16px 20px",
                  minWidth: 280,
                  maxWidth: 380,
                  boxShadow: "0 16px 48px rgba(0,0,0,0.5)",
                  display: "flex",
                  flexDirection: "column",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "#8B949E",
                    marginBottom: 8,
                  }}
                >
                  📋 Log en vivo
                </div>
                <div
                  style={{
                    flex: 1,
                    overflowY: "auto",
                    fontSize: 11,
                    fontFamily: "monospace",
                    color: "#8B949E",
                    maxHeight: "60vh",
                  }}
                >
                  {pipelineLiveLogs.map((l, i) => (
                    <div
                      key={i}
                      style={{
                        padding: "2px 0",
                        borderBottom: "1px solid #21262D22",
                      }}
                    >
                      <span style={{ color: "#484F58" }}>
                        {new Date(l.ts * 1000).toLocaleTimeString()}
                      </span>{" "}
                      {l.msg}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

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
          proposal={{ pending: hitlPending[0].proposal_summary }}
          criticVerdict={{ verdict: hitlPending[0].critic_verdict }}
          onClose={() => setShowHITLModal(false)}
          onDecided={() => {
            setShowHITLModal(false);
            getPendingHitl(id)
              .then(setHitlPending)
              .catch(() => {});
          }}
        />
      )}
    </div>
  );
}
