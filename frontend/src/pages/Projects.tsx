import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listProjects,
  createProject,
  deleteProject,
  Project,
} from "../api/client";
import { useI18n } from "../i18n";

const VALID_OBJECTS_OF_STUDY = [
  "concern",
  "emotion",
  "behavior",
  "discourse",
  "identity",
  "custom",
] as const;

const STUDY_OBJECT_HINTS: Record<string, string> = {
  concern: "projects.hintConcern",
  emotion: "projects.hintEmotion",
  behavior: "projects.hintBehavior",
  discourse: "projects.hintDiscourse",
  identity: "projects.hintIdentity",
  custom: "projects.hintCustom",
};

const DEFAULT_VERB_BY_OBJECT: Record<string, string> = {
  concern: "resolve",
  emotion: "regulate",
  behavior: "adapt",
  discourse: "deploy",
  identity: "negotiate",
  custom: "process",
};

function makeGerund(verb: string): string {
  if (!verb) return "";
  // Simple English gerund: drop trailing 'e' then add 'ing'
  if (verb.endsWith("e")) return verb.slice(0, -1) + "ing";
  return verb + "ing";
}

export default function Projects() {
  const { t } = useI18n();
  const [projects, setProjects] = useState<Project[]>([]);
  const [nombre, setNombre] = useState("");
  const [supuesto, setSupuesto] = useState("");
  const [objectOfStudy, setObjectOfStudy] = useState<string>("concern");
  const [customLabel, setCustomLabel] = useState("");
  const [processingVerb, setProcessingVerb] = useState(
    DEFAULT_VERB_BY_OBJECT["concern"],
  );
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
    const verb = processingVerb.trim();
    const p = await createProject({
      nombre: nombre.trim(),
      supuesto_poblacional: supuesto.trim() || undefined,
      object_of_study: objectOfStudy,
      ...(objectOfStudy === "custom" && customLabel.trim()
        ? { custom_label: customLabel.trim() }
        : {}),
      ...(verb
        ? { processing_verb: verb, processing_gerund: makeGerund(verb) }
        : {}),
    });
    setProjects((prev) => [p, ...prev]);
    setNombre("");
    setSupuesto("");
    setCustomLabel("");
    setProcessingVerb(DEFAULT_VERB_BY_OBJECT["concern"]);
  }

  async function handleDelete(projectId: string, projectName: string) {
    if (!confirm(t("projects.confirmDelete", { name: projectName }))) return;
    setDeleting(projectId);
    try {
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
    } catch (e) {
      alert(t("projects.deleteError") + e);
    } finally {
      setDeleting(null);
    }
  }

  if (loading)
    return (
      <p style={{ padding: 24, color: "#C9D1D9" }}>{t("projects.loading")}</p>
    );

  const studyObjectOptions = [
    { value: "concern", label: t("config.concern") },
    { value: "emotion", label: t("config.emotion") },
    { value: "behavior", label: t("config.behavior") },
    { value: "discourse", label: t("config.discourse") },
    { value: "identity", label: t("config.identity") },
    { value: "custom", label: t("config.custom") },
  ];

  return (
    <div style={{ maxWidth: 700, margin: "40px auto", padding: 24 }}>
      <h2 style={{ color: "#E6EDF3" }}>{t("projects.title")}</h2>

      <form
        onSubmit={handleCreate}
        style={{
          marginBottom: 24,
          padding: 20,
          background: "#161B22",
          border: "1px solid #21262D",
          borderRadius: 8,
        }}
      >
        <div style={{ marginBottom: 12 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              color: "#8B949E",
              marginBottom: 4,
            }}
          >
            {t("projects.newProjectPlaceholder")}
          </label>
          <input
            placeholder={t("projects.newProjectPlaceholder")}
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            style={{ padding: 8, width: "100%", boxSizing: "border-box" }}
            required
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              color: "#8B949E",
              marginBottom: 4,
            }}
          >
            {t("projects.populationLabel")}
          </label>
          <input
            placeholder={t("projects.populationPlaceholder")}
            value={supuesto}
            onChange={(e) => setSupuesto(e.target.value)}
            style={{ padding: 8, width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              color: "#8B949E",
              marginBottom: 4,
            }}
          >
            {t("projects.studyObjectLabel")}
          </label>
          <select
            value={objectOfStudy}
            onChange={(e) => {
              const val = e.target.value;
              setObjectOfStudy(val);
              setProcessingVerb(DEFAULT_VERB_BY_OBJECT[val] || "");
            }}
            style={{
              padding: 8,
              width: "100%",
              boxSizing: "border-box",
              background: "#0D1117",
              color: "#C9D1D9",
              border: "1px solid #30363D",
              borderRadius: 4,
            }}
          >
            {studyObjectOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div style={{ fontSize: 11, color: "#484F58", marginTop: 4 }}>
            {t(STUDY_OBJECT_HINTS[objectOfStudy])}
          </div>
        </div>

        {objectOfStudy === "custom" && (
          <div style={{ marginBottom: 16 }}>
            <label
              style={{
                display: "block",
                fontSize: 12,
                color: "#8B949E",
                marginBottom: 4,
              }}
            >
              {t("projects.customLabelPlaceholder")}
            </label>
            <input
              placeholder={t("projects.customLabelPlaceholder")}
              value={customLabel}
              onChange={(e) => setCustomLabel(e.target.value)}
              style={{ padding: 8, width: "100%", boxSizing: "border-box" }}
            />
          </div>
        )}

        <div style={{ marginBottom: 12 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              color: "#8B949E",
              marginBottom: 4,
            }}
          >
            {t("projects.processingVerbLabel")}
          </label>
          <input
            placeholder={t("projects.processingVerbPlaceholder")}
            value={processingVerb}
            onChange={(e) => setProcessingVerb(e.target.value)}
            style={{ padding: 8, width: "100%", boxSizing: "border-box" }}
          />
          <div style={{ fontSize: 11, color: "#484F58", marginTop: 4 }}>
            {t("projects.processingVerbHint")}
          </div>
        </div>

        {supuesto.trim() && objectOfStudy && processingVerb.trim() && (
          <div
            style={{
              marginBottom: 16,
              padding: 12,
              background: "#0D1117",
              border: "1px solid #21262D",
              borderRadius: 6,
            }}
          >
            <div
              style={{
                fontSize: 11,
                color: "#8B949E",
                marginBottom: 6,
                textTransform: "uppercase",
                letterSpacing: "0.5px",
              }}
            >
              {t("projects.rqPreview")}
            </div>
            <div
              style={{ fontSize: 14, color: "#C9D1D9", fontStyle: "italic" }}
            >
              "What is the{" "}
              {studyObjectOptions
                .find((o) => o.value === objectOfStudy)
                ?.label.toLowerCase() || objectOfStudy}{" "}
              of {supuesto.trim() || "…"} and how do they continuously{" "}
              {processingVerb.trim() || "…"} it?"
            </div>
            {processingVerb.trim() && (
              <div style={{ fontSize: 11, color: "#484F58", marginTop: 6 }}>
                Gerund: {makeGerund(processingVerb.trim())}
              </div>
            )}
          </div>
        )}

        <button type="submit" style={{ padding: "8px 24px" }}>
          {t("projects.createButton")}
        </button>
      </form>

      {projects.length === 0 && (
        <p style={{ color: "#8B949E" }}>{t("projects.noProjects")}</p>
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
                {t("projects.openButton")}
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
                {deleting === p.id ? "..." : t("projects.deleteButton")}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
