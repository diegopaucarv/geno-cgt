import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getProject,
  listDocuments,
  listCategories,
  listSegments,
  uploadDocument,
  segmentDocument,
  deleteDocument,
  getTaskStatus,
  saveTaskSegments,
  Project,
  Document,
  Category,
  Segment,
} from "../api/client";

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [segments, setSegments] = useState<Record<string, Segment[]>>({});
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
  const [segmenting, setSegmenting] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getProject(id).then(setProject).catch(console.error);
    listDocuments(id).then(setDocs).catch(console.error);
    listCategories(id).then(setCats).catch(console.error);
  }, [id]);

  async function toggleSegments(docId: string) {
    if (expandedDoc === docId) {
      setExpandedDoc(null);
      return;
    }
    setExpandedDoc(docId);
    if (!segments[docId]) {
      const segs = await listSegments(docId);
      setSegments((prev) => ({ ...prev, [docId]: segs }));
    }
  }

  if (!project) return <p>Cargando…</p>;

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <h2>{project.nombre}</h2>
      <p>
        Estado: {project.estado} · Ruta: {project.ruta_de_codificacion}
        {project.num_documentos != null && (
          <>
            {" "}
            · Docs: {project.num_documentos} · Cats: {project.num_categorias}
          </>
        )}
      </p>

      <input
        type="file"
        accept=".pdf,.txt,.docx"
        style={{ marginBottom: 20 }}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file || !id) return;
          try {
            await uploadDocument(id, file);
            listDocuments(id).then(setDocs);
          } catch (err: any) {
            alert(err.message);
          }
        }}
      />

      <h3>Documentos ({docs.length})</h3>
      {docs.length === 0 && <p>Sin documentos.</p>}
      <ul>
        {docs.map((d) => (
          <li key={d.id} style={{ marginBottom: 8 }}>
            <strong>{d.original_filename}</strong> ({d.mime_type})
            <button
              onClick={() => toggleSegments(d.id)}
              style={{ marginLeft: 12, fontSize: 12 }}
            >
              {expandedDoc === d.id ? "Ocultar texto" : "Ver texto"}
            </button>
            <button
              onClick={async () => {
                setSegmenting(d.id);
                try {
                  const res = await segmentDocument(d.id);
                  if (res.status === "dispatched" && res.task_id) {
                    let done = false;
                    while (!done) {
                      await new Promise((r) => setTimeout(r, 2000));
                      const status = await getTaskStatus(res.task_id);
                      console.log("Poll:", status.status, status.result);
                      if (
                        status.status === "SUCCESS" ||
                        status.status === "success"
                      ) {
                        await saveTaskSegments(d.id, res.task_id);
                        done = true;
                      } else if (
                        status.status === "FAILURE" ||
                        status.status === "failure"
                      ) {
                        throw new Error(
                          "Segmentación falló: " +
                            JSON.stringify(status.result),
                        );
                      }
                    }
                  }
                  const segs = await listSegments(d.id);
                  setSegments((prev) => ({ ...prev, [d.id]: segs }));
                  setExpandedDoc(d.id);
                } catch (err: any) {
                  alert(err.message);
                } finally {
                  setSegmenting(null);
                }
              }}
              disabled={segmenting === d.id}
              style={{ marginLeft: 6, fontSize: 12 }}
            >
              {segmenting === d.id ? "⏳" : "Segmentar"}
            </button>
            <button
              onClick={async () => {
                if (!confirm(`¿Eliminar "${d.original_filename}"?`)) return;
                try {
                  await deleteDocument(d.id);
                  setSegments((prev) => {
                    const next = { ...prev };
                    delete next[d.id];
                    return next;
                  });
                  setExpandedDoc(null);
                  listDocuments(id!).then(setDocs);
                } catch (err: any) {
                  alert(err.message);
                }
              }}
              style={{ marginLeft: 6, fontSize: 12, color: "red" }}
            >
              ✕
            </button>
            {expandedDoc === d.id && (
              <textarea
                readOnly
                style={{
                  width: "100%",
                  marginTop: 8,
                  minHeight: 150,
                  fontFamily: "monospace",
                  fontSize: 13,
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

      <hr />

      <h3>Categorías ({cats.length})</h3>
      {cats.length === 0 && <p>Sin categorías.</p>}
      <ul>
        {cats.map((c) => (
          <li key={c.id} style={{ marginBottom: 8 }}>
            <strong>{c.nombre}</strong>
            {c.es_central && " ⭐"}
            <br />
            <span style={{ fontSize: 13, color: "#666" }}>{c.definicion}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
