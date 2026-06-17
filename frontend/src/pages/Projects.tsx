import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listProjects,
  createProject,
  deleteProject,
  Project,
} from "../api/client";

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [nombre, setNombre] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!nombre.trim()) return;
    const p = await createProject({ nombre });
    setProjects((prev) => [p, ...prev]);
    setNombre("");
  }

  async function handleDelete(projectId: string, projectName: string) {
    if (
      !confirm(
        `¿Eliminar "${projectName}" y todos sus datos? Esta acción no se puede deshacer.`,
      )
    )
      return;
    setDeleting(projectId);
    try {
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
    } catch (e) {
      alert("Error al eliminar: " + e);
    } finally {
      setDeleting(null);
    }
  }

  if (loading)
    return <p style={{ padding: 24, color: "#C9D1D9" }}>Cargando proyectos…</p>;

  return (
    <div style={{ maxWidth: 700, margin: "40px auto", padding: 24 }}>
      <h2 style={{ color: "#E6EDF3" }}>Mis Proyectos</h2>

      <form onSubmit={handleCreate} style={{ marginBottom: 24 }}>
        <input
          placeholder="Nombre del nuevo proyecto"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          style={{ padding: 8, width: 300, marginRight: 8 }}
        />
        <button type="submit" style={{ padding: 8 }}>
          Crear
        </button>
      </form>

      {projects.length === 0 && (
        <p style={{ color: "#8B949E" }}>No hay proyectos aún.</p>
      )}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {projects.map((p) => (
          <li
            key={p.id}
            style={{
              marginBottom: 10,
              padding: "12px 16px",
              background: "#161B22",
              border: "1px solid #21262D",
              borderRadius: 8,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  navigate(`/projects/${p.id}`);
                }}
                style={{
                  fontSize: 16,
                  color: "#58A6FF",
                  textDecoration: "none",
                  fontWeight: 500,
                }}
              >
                {p.nombre}
              </a>
              <div style={{ fontSize: 12, color: "#8B949E", marginTop: 2 }}>
                {p.estado} · {p.ruta_de_codificacion}
                {p.num_documentos != null && ` · ${p.num_documentos} docs`}
                {p.num_categorias != null && ` · ${p.num_categorias} cats`}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => navigate(`/projects/${p.id}`)}
                style={{
                  padding: "4px 12px",
                  borderRadius: 6,
                  border: "1px solid #30363D",
                  background: "#21262D",
                  color: "#C9D1D9",
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                Abrir
              </button>
              <button
                onClick={() => handleDelete(p.id, p.nombre)}
                disabled={deleting === p.id}
                style={{
                  padding: "4px 12px",
                  borderRadius: 6,
                  border: "1px solid #F8514933",
                  background: "#F8514918",
                  color: "#F85149",
                  fontSize: 12,
                  cursor: deleting === p.id ? "not-allowed" : "pointer",
                  opacity: deleting === p.id ? 0.5 : 1,
                }}
              >
                {deleting === p.id ? "..." : "Eliminar"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
