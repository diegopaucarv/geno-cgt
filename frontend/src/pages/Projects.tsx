import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects, createProject, Project } from "../api/client";

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [nombre, setNombre] = useState("");
  const [loading, setLoading] = useState(true);
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

  if (loading) return <p>Cargando proyectos…</p>;

  return (
    <div style={{ maxWidth: 700, margin: "40px auto", padding: 24 }}>
      <h2>Mis Proyectos</h2>

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

      {projects.length === 0 && <p>No hay proyectos aún.</p>}

      <ul>
        {projects.map((p) => (
          <li key={p.id} style={{ marginBottom: 12 }}>
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                navigate(`/projects/${p.id}`);
              }}
              style={{ fontSize: 18 }}
            >
              {p.nombre}
            </a>
            <span style={{ marginLeft: 12, color: "#888", fontSize: 14 }}>
              {p.estado} · {p.ruta_de_codificacion}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
