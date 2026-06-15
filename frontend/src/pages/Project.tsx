import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  getProject,
  listDocuments,
  listCategories,
  listSegments,
  uploadDocument,
  punctuateDocument,
  deleteDocument,
  getTaskStatus,
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
  const [processing, setProcessing] = useState<string | null>(null);
  const [punctStatus, setPunctStatus] = useState<Record<string, string>>({});
  const [punctFix, setPunctFix] = useState<Record<string, boolean>>({});
  const [userName, setUserName] = useState("");

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

  async function handlePunctuate(docId: string) {
    setProcessing(docId);
    setPunctStatus((prev) => ({
      ...prev,
      [docId]: "⏳ Mejorando puntuación…",
    }));
    try {
      const res = await punctuateDocument(docId);

      if (!res.punctuation_fix) {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: res.message || "✅ Puntuación OK",
        }));
        setProcessing(null);
        return;
      }

      if (res.task_id) {
        // Poll for completion
        let done = false;
        let attempts = 0;
        while (!done && attempts < 30) {
          attempts++;
          await new Promise((r) => setTimeout(r, 2000));
          const status = await getTaskStatus(res.task_id);
          setPunctStatus((prev) => ({
            ...prev,
            [docId]: `⏳ ${status.status} (${attempts}/30)`,
          }));
          if (status.status === "SUCCESS" || status.status === "success") {
            setPunctStatus((prev) => ({
              ...prev,
              [docId]: "✅ Puntuación mejorada",
            }));
            done = true;
          } else if (
            status.status === "FAILURE" ||
            status.status === "failure"
          ) {
            throw new Error("Falló la mejora de puntuación");
          }
        }
        if (!done) {
          setPunctStatus((prev) => ({
            ...prev,
            [docId]: "⚠️ Timeout",
          }));
        }
      } else {
        setPunctStatus((prev) => ({
          ...prev,
          [docId]: "✅ Puntuación mejorada",
        }));
      }

      // Refresh to get updated text
      refreshDocs();
      setPunctFix((prev) => ({ ...prev, [docId]: true }));
    } catch (err: any) {
      setPunctStatus((prev) => ({ ...prev, [docId]: "❌ " + err.message }));
    } finally {
      setProcessing(null);
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !id) return;
    try {
      const res = await uploadDocument(id, file);
      if (res.punctuation_fix) {
        setPunctFix((p) => ({ ...p, [res.id]: true }));
      }
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
      {/* ── Navigation Bar ─────────────────────────── */}
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
            style={{
              color: "#58A6FF",
              fontSize: 13,
              textDecoration: "none",
            }}
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
            title={
              hasCats
                ? "Ir al Theoretical Playground"
                : "Procesa documentos para generar categorías"
            }
          >
            🧪 Playground
          </Link>
          <span style={{ fontSize: 11, color: "#8B949E" }}>{userName}</span>
          <button onClick={handleLogout} style={{ ...btnSmall, fontSize: 11 }}>
            Salir
          </button>
        </div>
      </div>

      {/* ── Project Meta ───────────────────────────── */}
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
                {punctFix[d.id] && (
                  <span
                    style={{
                      marginLeft: 8,
                      padding: "1px 6px",
                      borderRadius: 999,
                      fontSize: 10,
                      background: "#A371F722",
                      color: "#A371F7",
                    }}
                  >
                    puntuación mejorada
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                {punctStatus[d.id] && (
                  <span style={{ fontSize: 11, color: "#8B949E" }}>
                    {punctStatus[d.id]}
                  </span>
                )}
                <button onClick={() => toggleSegments(d.id)} style={btnSmall}>
                  {expandedDoc === d.id ? "Ocultar texto" : "Ver texto"}
                </button>
                <button
                  onClick={() => handlePunctuate(d.id)}
                  disabled={processing === d.id}
                  style={{
                    ...btnSmall,
                    background: processing === d.id ? "#1C2333" : "#A371F7",
                    color: "#FFF",
                  }}
                  title="Mejorar puntuación del texto con LLM"
                >
                  {processing === d.id ? "⏳" : "✨"} Procesar
                </button>
                <button
                  onClick={async () => {
                    if (!confirm("¿Eliminar este documento?")) return;
                    await deleteDocument(d.id);
                    refreshDocs();
                  }}
                  style={{ ...btnSmall, color: "#F85149" }}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Expanded text view */}
            {expandedDoc === d.id && (
              <textarea
                readOnly
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
          Sin categorías aún. Sube y procesa documentos para generarlas
          automáticamente con el pipeline.
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

      {/* ── Quick action: go to Playground ─────────── */}
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
