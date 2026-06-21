import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listProjects,
  createProject,
  deleteProject,
  previewResearchQuestionStandalone,
  clearToken,
  ping,
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
  "meaning",
] as const;

const DEFAULT_VERB_KEYS: Record<string, string> = {
  concern: "projects.defaultVerbConcern",
  emotion: "projects.defaultVerbEmotion",
  behavior: "projects.defaultVerbBehavior",
  discourse: "projects.defaultVerbDiscourse",
  identity: "projects.defaultVerbIdentity",
  custom: "projects.defaultVerbCustom",
  meaning: "projects.defaultVerbMeaning",
};

function makeGerund(verb: string): string {
  if (!verb) return "";
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
    t("projects.defaultVerbConcern"),
  );
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [rqPreview, setRqPreview] = useState<any>(null);
  const [rqError, setRqError] = useState(false);
  const [userName, setUserName] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(console.error)
      .finally(() => setLoading(false));
    ping()
      .then((p) => setUserName(p.user_id.slice(0, 8)))
      .catch(() => {});
  }, []);

  // Debounced backend preview using spaCy conjugation
  useEffect(() => {
    const pop = supuesto.trim();
    if (!pop || !processingVerb.trim()) {
      setRqPreview(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        setRqError(false);
        const r = await previewResearchQuestionStandalone({
          population: pop,
          object_of_study: objectOfStudy,
          processing_verb: processingVerb.trim(),
          ...(objectOfStudy === "custom" && customLabel.trim()
            ? { custom_label: customLabel.trim() }
            : {}),
        });
        setRqPreview(r);
      } catch {
        setRqPreview(null);
        setRqError(true);
      }
    }, 2000);
    return () => clearTimeout(timer);
  }, [supuesto, objectOfStudy, processingVerb, customLabel]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canCreate) return;
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
    setProcessingVerb(t(DEFAULT_VERB_KEYS["concern"]));
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

  const canCreate =
    !!nombre.trim() &&
    !!supuesto.trim() &&
    !!processingVerb.trim() &&
    rqPreview?.population_number === "plural";

  const studyObjectOptions = [
    { value: "concern", label: t("config.concern") },
    { value: "emotion", label: t("config.emotion") },
    { value: "behavior", label: t("config.behavior") },
    { value: "discourse", label: t("config.discourse") },
    { value: "identity", label: t("config.identity") },
    { value: "meaning", label: t("config.meaning") },
    { value: "custom", label: t("config.custom") },
  ];

  const inputStyle: React.CSSProperties = {
    padding: 8,
    width: "100%",
    boxSizing: "border-box",
    background: "#0D1117",
    color: "#C9D1D9",
    border: "1px solid #30363D",
    borderRadius: 4,
    fontSize: 13,
    outline: "none",
  };

  function handleLogout() {
    clearToken();
    navigate("/login");
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0D1117" }}>
      {/* ── Top Bar ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 24px",
          background: "#161B22",
          borderBottom: "1px solid #21262D",
        }}
      >
        <span style={{ fontSize: 14, fontWeight: 600, color: "#E6EDF3" }}>
          GT · Grounded Theory
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {userName && (
            <span style={{ fontSize: 11, color: "#8B949E" }}>{userName}</span>
          )}
          <button
            onClick={handleLogout}
            style={{
              padding: "5px 12px",
              borderRadius: 6,
              border: "1px solid #21262D",
              background: "#1C2333",
              color: "#E6EDF3",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            {t("project.signOut")}
          </button>
        </div>
      </div>

      {/* ── Main Content ── */}
      <div
        style={{
          maxWidth: 1100,
          margin: "40px auto",
          padding: "0 24px",
          display: "flex",
          gap: 32,
        }}
      >
      {/* ── Left: Create Project Form ── */}
      <div style={{ flex: "0 0 420px", minWidth: 0 }}>
        <h2 style={{ color: "#E6EDF3", marginTop: 0 }}>
          {t("projects.title")}
        </h2>

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
          {/* Project name */}
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
              style={inputStyle}
              required
            />
          </div>

          {/* Population */}
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
              style={inputStyle}
            />
            <div
              style={{
                fontSize: 11,
                color: "#8B949E",
                marginTop: 4,
                fontStyle: "italic",
              }}
            >
              {t("projects.popHelpNote")}
            </div>
          </div>

          {/* Pattern type */}
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
                const verbKey = DEFAULT_VERB_KEYS[val];
                setProcessingVerb(verbKey ? t(verbKey) : "");
              }}
              style={{ ...inputStyle, cursor: "pointer" }}
            >
              {studyObjectOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <div
              style={{
                fontSize: 11,
                color: "#8B949E",
                marginTop: 4,
                fontStyle: "italic",
              }}
            >
              {t("projects.studyObjectHelpNote")}
            </div>
          </div>

          {/* Custom label — only for "custom" type, NOT meaning */}
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
                style={inputStyle}
              />
            </div>
          )}

          {/* Processing verb */}
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
              style={inputStyle}
            />
            <div
              style={{
                fontSize: 11,
                color: "#8B949E",
                marginTop: 4,
                fontStyle: "italic",
              }}
            >
              {t("projects.processingVerbHint")}
            </div>
          </div>

          {/* ── RQ + OQ Preview (powered by backend spaCy) ── */}
          {rqPreview?.population_number === "singular" && (
            <span style={{ color: "#F85149", fontSize: 14 }}>
              {t("projects.rqPreviewSingular")}
            </span>
          )}
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
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>
                {rqError ? (
                  <span style={{ color: "#F85149" }}>
                    {t("projects.rqPreviewError") ||
                      "Preview unavailable — backend may be starting up."}
                  </span>
                ) : !rqPreview ? (
                  <span style={{ color: "#8b9199" }}>
                    {t("projects.rqPreviewLoading") || "Generating preview…"}
                  </span>
                ) : (
                  (() => {
                    const isSing = rqPreview.population_number === "singular";
                    const dim = isSing ? {} : {};
                    const badge = isSing
                      ? {
                          color: "#8b9199",
                          background: "#21262D",
                          padding: "1px 6px",
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          marginRight: 6,
                        }
                      : {};
                    const badgeRQ = isSing
                      ? badge
                      : {
                          color: "#0D1117",
                          background: "#D29922",
                          padding: "1px 6px",
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          marginRight: 6,
                        };
                    const badgeDisc = isSing
                      ? badge
                      : {
                          color: "#0D1117",
                          background: "#58A6FF",
                          padding: "1px 6px",
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          marginRight: 6,
                        };
                    const badgeSel = isSing
                      ? badge
                      : {
                          color: "#0D1117",
                          background: "#3FB950",
                          padding: "1px 6px",
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          marginRight: 6,
                        };
                    const badgeTheo = isSing
                      ? badge
                      : {
                          color: "#0D1117",
                          background: "#A371F7",
                          padding: "1px 6px",
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          marginRight: 6,
                        };
                    return (
                      <>
                        <div
                          style={{
                            color: isSing ? "#8b9199" : "#D29922",
                            marginBottom: 8,
                            padding: "6px 8px",
                            background: isSing ? "#D2992208" : "#D2992210",
                            borderLeft: `3px solid ${isSing ? "#30363D" : "#D29922"}`,
                            borderRadius: 4,
                            ...dim,
                          }}
                        >
                          <span style={badgeRQ}>RQ</span>
                          {rqPreview.research_question}
                        </div>
                        <div
                          style={{
                            fontSize: 10,
                            color: isSing ? "#30363D" : "#8b9199",
                            textTransform: "uppercase",
                            letterSpacing: 1,
                            marginBottom: 4,
                            marginTop: 2,
                            ...dim,
                          }}
                        >
                          {t("projects.oqSectionLabel") || "Operational"}
                        </div>
                        <div
                          style={{
                            color: isSing ? "#8b9199" : "#58A6FF",
                            marginBottom: 2,
                            ...dim,
                          }}
                        >
                          <span style={badgeDisc}>
                            {t("projects.oqStageDiscovery")}
                          </span>
                          {rqPreview.oq_discovery ||
                            rqPreview.operational_question}
                        </div>
                        <div
                          style={{
                            color: isSing ? "#8b9199" : "#3FB950",
                            marginBottom: 2,
                            ...dim,
                          }}
                        >
                          <span style={badgeSel}>
                            {t("projects.oqStageSelective")}
                          </span>
                          {rqPreview.oq_selective}
                        </div>
                        <div
                          style={{
                            color: isSing ? "#8b9199" : "#A371F7",
                            ...dim,
                          }}
                        >
                          <span style={badgeTheo}>
                            {t("projects.oqStageTheoretical")}
                          </span>
                          {rqPreview.oq_theoretical}
                        </div>
                      </>
                    );
                  })()
                )}
              </div>
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              type="submit"
              disabled={!canCreate}
              style={{
                padding: "8px 24px",
                background: !canCreate ? "#21262D" : "#238636",
                border: "none",
                borderRadius: 6,
                color: !canCreate ? "#8b9199" : "#FFF",
                fontSize: 13,
                fontWeight: 600,
                cursor: !canCreate ? "not-allowed" : "pointer",
              }}
            >
              {t("projects.createButton")}
            </button>
            {!canCreate && supuesto.trim() && processingVerb.trim() && (
              <span style={{ color: "#8B949E", fontSize: 11 }}>
                {!supuesto.trim()
                  ? t("projects.fillAllFields") || "Fill all fields"
                  : rqPreview?.population_number === "singular"
                    ? t("projects.rqPreviewSingular")
                    : t("projects.rqPreviewLoading")}
              </span>
            )}
          </div>
        </form>
      </div>

      {/* ── Right: Project List ── */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3
          style={{
            color: "#8B949E",
            fontSize: 13,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            marginBottom: 16,
            marginTop: 0,
          }}
        >
          {t("projects.title")} ({projects.length})
        </h3>

        {/* Project list */}
        {projects.length === 0 ? (
          <p style={{ color: "#8B949E", textAlign: "center" }}>
            {t("projects.noProjects")}
          </p>
        ) : (
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
        )}
      </div>
      </div>
    </div>
  );
}
