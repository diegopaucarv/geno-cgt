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
  ping,
  clearToken,
  Project,
  Document,
  Category,
  Segment,
} from "../api/client";

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

  useEffect(() => {
    if (!id) return;
    getProject(id).then(setProject).catch(console.error);
    refreshDocs();
    listCategories(id).then(setCats).catch(console.error);
    ping()
      .then((p) => setUserName(p.user_id.slice(0, 8)))
      .catch(() => {});
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
    if (!segments[docId]) {
      const segs = await listSegments(docId).catch(() => []);
      setSegments((prev) => ({ ...prev, [docId]: segs }));
    }
  }

  // ── Preprocesar (puntuación) ────────────────────────────────────

  async function handlePunctuate(docId: string) {
    // Si ya está corriendo, cancelar
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
    try {
      const res = await punctuateDocument(docId);
      if (abortRef.current) return;
      if (res.status === "ok" && res.changes_made) {
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

  // ── Pipeline IA (todos los docs) ────────────────────────────────

  async function runPipeline() {
    const auth = `Bearer ${localStorage.getItem("access_token")}`;
    abortRef.current = false;
    setPipelineRunning(true);
    setPipelineMsg("⏳ Arrancando workers…");
    await fetch("/api/v1/admin/workers/nlp/start", {
      method: "POST",
      headers: { Authorization: auth },
    });
    await fetch("/api/v1/admin/workers/heavy/start", {
      method: "POST",
      headers: { Authorization: auth },
    });
    await new Promise((r) => setTimeout(r, 2000));
    const todo = docs.filter((d) => d.estado !== "listo");
    if (todo.length === 0) {
      setPipelineMsg("Todos los documentos ya están procesados.");
      setPipelineRunning(false);
      return;
    }

    for (let i = 0; i < todo.length; i++) {
      if (abortRef.current) break;
      const d = todo[i];
      setPipelineMsg(
        `🧠 Procesando ${i + 1}/${todo.length}: ${d.original_filename}…`,
      );

      try {
        setPipelineMsg(
          `🧠 Procesando ${i + 1}/${todo.length}: ${d.original_filename}…`,
        );
        const res = await fetch(`/api/v1/documents/${d.id}/process`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({ steps: ["segment", "agents"] }),
        }).then((r) => r.json());

        const agentResult = res.steps?.agents;
        if (agentResult?.status === "done") {
          setPipelineMsg(`🧠 ${d.original_filename}: ✅ completado`);
        } else if (agentResult?.status === "error") {
          setPipelineMsg(
            `🧠 ${d.original_filename}: ❌ ${agentResult.message}`,
          );
        }
      } catch (e: any) {
        setPipelineMsg(`❌ Error en ${d.original_filename}: ${e.message}`);
      }
    }

    setPipelineMsg(
      abortRef.current ? "⏹ Pipeline cancelado." : "✅ Pipeline completado.",
    );
    if (abortRef.current) {
      await fetch("/api/v1/admin/workers/heavy/stop", {
        method: "POST",
        headers: { Authorization: auth },
      }).catch(() => {});
      await fetch("/api/v1/admin/workers/nlp/stop", {
        method: "POST",
        headers: { Authorization: auth },
      }).catch(() => {});
    }
    refreshDocs();
    listCategories(id!).then(setCats);
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
          <Link
            to={`/projects/${id}/theory`}
            style={{
              padding: "6px 16px",
              borderRadius: 6,
              background: hasCats
                ? "linear-gradient(135deg, #A371F7, #58A6FF)"
                : "#1C2333",
              border: hasCats ? "none" : "1px solid #21262D",
              color: "#FFF",
              fontSize: 13,
              fontWeight: 600,
              textDecoration: "none",
              opacity: hasCats ? 1 : 0.5,
            }}
          >
            🧪 Playground
          </Link>
          <span style={{ fontSize: 11, color: "#8B949E" }}>{userName}</span>
          <button onClick={handleLogout} style={{ ...btnSmall, fontSize: 11 }}>
            Salir
          </button>
        </div>
      </div>

      {/* ── Pipeline button ───────────────────────── */}
      <div
        style={{
          marginBottom: 20,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <button
          onClick={runPipeline}
          disabled={pipelineRunning || docs.length === 0}
          style={{
            padding: "8px 20px",
            borderRadius: 6,
            border: "none",
            cursor: "pointer",
            background: pipelineRunning
              ? "#1C2333"
              : "linear-gradient(135deg, #A371F7, #3FB950)",
            color: "#FFF",
            fontSize: 13,
            fontWeight: 600,
            opacity: docs.length === 0 ? 0.4 : 1,
          }}
        >
          {pipelineRunning ? "⏳ Ejecutando…" : "🧠 Ejecutar Pipeline IA"}
        </button>
        {pipelineRunning && (
          <button
            onClick={() => {
              abortRef.current = true;
              setPipelineRunning(false);
              setPipelineMsg("⏹ Cancelado.");
            }}
            style={{ ...btnSmall, color: "#F85149" }}
          >
            ⏹ Cancelar
          </button>
        )}
        {pipelineMsg && (
          <span style={{ fontSize: 12, color: "#8B949E" }}>{pipelineMsg}</span>
        )}
      </div>

      {/* ── Project meta ──────────────────────────── */}
      <p style={{ margin: "0 0 20px", color: "#8B949E", fontSize: 13 }}>
        Ruta: {project.ruta_de_codificacion} · Estado: {project.estado}
      </p>

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
        {docs.map((d) => (
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
              <div>
                <strong style={{ color: "#E6EDF3" }}>
                  {d.original_filename}
                </strong>
                <span style={{ marginLeft: 8, fontSize: 11, color: "#8B949E" }}>
                  {d.mime_type}
                </span>
                {punctStatus[d.id] && (
                  <span
                    style={{
                      marginLeft: 8,
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
                  style={{
                    ...btnSmall,
                    background: punctRunning === d.id ? "#F85149" : "#A371F7",
                    color: "#FFF",
                  }}
                >
                  {punctRunning === d.id ? "⏹ Cancelar" : "✨ Preprocesar"}
                </button>
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
            {expandedDoc === d.id && (
              <textarea
                readOnly
                disabled={punctRunning === d.id}
                style={{
                  width: "100%",
                  marginTop: 8,
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
                  segments[d.id]?.length
                    ? segments[d.id]!.map(
                        (s) => `[${s.posicion}] ${s.texto}`,
                      ).join("\n\n")
                    : d.texto_extraido || "(sin texto disponible)"
                }
              />
            )}
          </li>
        ))}
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

      {hasCats && (
        <div style={{ textAlign: "center", marginTop: 32 }}>
          <Link
            to={`/projects/${id}/theory`}
            style={{
              display: "inline-block",
              padding: "10px 28px",
              borderRadius: 8,
              background: "linear-gradient(135deg, #A371F7, #58A6FF)",
              color: "#FFF",
              fontSize: 14,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            🧪 Abrir Theoretical Playground →
          </Link>
        </div>
      )}
    </div>
  );
}
