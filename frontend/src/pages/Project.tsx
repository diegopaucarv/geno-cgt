import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getProject,
  listDocuments,
  listCategories,
  listSegments,
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
          <> · Docs: {project.num_documentos} · Cats: {project.num_categorias}</>
        )}
      </p>

      <hr />

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
              {expandedDoc === d.id ? "Ocultar" : "Segmentos"}
            </button>
            {expandedDoc === d.id && (
              <ul style={{ marginTop: 6 }}>
                {segments[d.id]?.map((s) => (
                  <li key={s.id} style={{ fontSize: 13, color: "#555" }}>
                    [{s.posicion}] {s.texto.slice(0, 120)}…
                  </li>
                ))}
              </ul>
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
