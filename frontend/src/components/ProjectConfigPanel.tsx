import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  getProjectConfig,
  getProjectConfigHistory,
  updateMutationPolicy,
  updatePopulationAssumption,
  getResearchQuestion,
  generateResearchQuestion,
  type ProjectConfig,
  type ConfigHistoryEntry,
  type ConfigSuggestion,
  type ResearchQuestionResponse,
} from "../api/client";
import { useI18n } from "../i18n";

/* ── Types ─────────────────────────────────────────────────────────── */

interface Props {
  open: boolean;
  projectId: string;
  onClose: () => void;
}

type TabKey = "config" | "history" | "suggestions" | "policy";

/* ── Key maps (backend field / trigger / level → i18n key) ────────── */

const FIELD_KEYS: Record<string, string> = {
  "population_assumption.population_description":
    "projectConfig.fieldPopulationDescription",
  "population_assumption.temporal_frame": "projectConfig.fieldTimeframe",
  "population_assumption.spatial_frame": "projectConfig.fieldSpatialScope",
  "population_assumption.object_of_study": "projectConfig.fieldStudyObject",
  "population_assumption.gerundio_esperado":
    "projectConfig.fieldExpectedGerund",
  population_description: "projectConfig.fieldPopulationDescription",
  temporal_frame: "projectConfig.fieldTimeframe",
  spatial_frame: "projectConfig.fieldSpatialScope",
  object_of_study: "projectConfig.fieldStudyObject",
  pattern_of_interest: "projectConfig.fieldPatternOfInterest",
  coding_styles: "projectConfig.fieldCodingStyles",
  gerundio_esperado: "projectConfig.fieldExpectedGerund",
  segmentation_config: "projectConfig.fieldSegmentation",
};

const LEVEL_KEYS: Record<string, { key: string; color: string }> = {
  auto: { key: "projectConfig.auto", color: "#3FB950" },
  suggest: { key: "projectConfig.suggest", color: "#D29922" },
  require_approval: { key: "projectConfig.requireApproval", color: "#F85149" },
  locked: { key: "projectConfig.locked", color: "#8B949E" },
};

const TRIGGER_KEYS: Record<string, string> = {
  user: "projectConfig.sourceResearcher",
  system: "projectConfig.sourceSystem",
  population_generalizer: "projectConfig.sourcePopulationGeneralizer",
  core_pattern_verifier: "projectConfig.sourceCorePatternVerifier",
};

/* ── Helpers (receive t so they can translate) ─────────────────────── */

function triggerLabel(t: (key: string) => string, trig: string) {
  return t(TRIGGER_KEYS[trig] || trig);
}

function fieldLabel(t: (key: string) => string, f: string) {
  return t(FIELD_KEYS[f] || f);
}

function levelBadge(t: (key: string) => string, level: string | null) {
  if (!level) return null;
  const info = LEVEL_KEYS[level];
  if (!info) return null;
  return <span style={{ color: info.color, fontSize: 11 }}>{t(info.key)}</span>;
}

function tryParseJson(v: string | null): string {
  if (!v) return "—";
  try {
    const parsed = JSON.parse(v);
    if (typeof parsed === "string") return parsed;
    return JSON.stringify(parsed, null, 2);
  } catch {
    return v;
  }
}

function timeAgo(t: (key: string) => string, iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return t("projectConfig.timeAgoNow");
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}

/* ── Styles ────────────────────────────────────────────────────────── */

const OVERLAY: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(0,0,0,0.6)",
};

const MODAL: CSSProperties = {
  background: "#161B22",
  borderRadius: 12,
  border: "1px solid #21262D",
  width: 720,
  maxHeight: "85vh",
  display: "flex",
  flexDirection: "column",
  boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
};

const HEADER: CSSProperties = {
  padding: "16px 20px",
  borderBottom: "1px solid #21262D",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  flexShrink: 0,
};

const TAB_ROW: CSSProperties = {
  display: "flex",
  borderBottom: "1px solid #21262D",
  padding: "0 16px",
  flexShrink: 0,
  overflowX: "auto",
};

const tabBase: CSSProperties = {
  padding: "10px 16px",
  fontSize: 12,
  cursor: "pointer",
  borderBottom: "2px solid transparent",
  background: "transparent",
  color: "#8B949E",
  transition: "all 0.15s",
  whiteSpace: "nowrap",
  fontWeight: 500,
};

const BODY: CSSProperties = {
  padding: "16px 20px",
  overflowY: "auto",
  flex: 1,
  minHeight: 0,
};

const FOOTER: CSSProperties = {
  padding: "12px 20px",
  borderTop: "1px solid #21262D",
  display: "flex",
  justifyContent: "flex-end",
  alignItems: "center",
  flexShrink: 0,
  gap: 8,
};

const FIELD_ROW: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  padding: "8px 0",
  borderBottom: "1px solid #21262D33",
};

const FIELD_KEY: CSSProperties = {
  fontSize: 11,
  color: "#8B949E",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  minWidth: 160,
};

const FIELD_VAL: CSSProperties = {
  fontSize: 13,
  color: "#E6EDF3",
  wordBreak: "break-word",
  textAlign: "right",
  flex: 1,
};

const BADGE: CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: 999,
  fontSize: 10,
  fontWeight: 600,
};

const HISTORY_ENTRY: CSSProperties = {
  padding: "10px 0",
  borderBottom: "1px solid #21262D44",
};

const BTN_PRIMARY: CSSProperties = {
  padding: "8px 16px",
  borderRadius: 6,
  border: "none",
  background: "#A371F7",
  color: "#FFF",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
};

const BTN_SECONDARY: CSSProperties = {
  padding: "8px 16px",
  borderRadius: 6,
  border: "1px solid #30363D",
  background: "#21262D",
  color: "#C9D1D9",
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
};

const BTN_ACCEPT: CSSProperties = {
  padding: "4px 12px",
  borderRadius: 6,
  border: "1px solid #3FB95044",
  background: "#3FB95018",
  color: "#3FB950",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

const BTN_REJECT: CSSProperties = {
  padding: "4px 12px",
  borderRadius: 6,
  border: "1px solid #F8514944",
  background: "#F8514918",
  color: "#F85149",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

/* ── Component ─────────────────────────────────────────────────────── */

export default function ProjectConfigPanel({
  open,
  projectId,
  onClose,
}: Props) {
  const { t } = useI18n();

  const [tab, setTab] = useState<TabKey>("config");
  const [config, setConfig] = useState<ProjectConfig | null>(null);
  const [history, setHistory] = useState<ConfigHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // Editable policy state
  const [policy, setPolicy] = useState<Record<string, string>>({});

  // ── Research Question state ──
  const [rqData, setRqData] = useState<ResearchQuestionResponse | null>(null);
  const [rqLoading, setRqLoading] = useState(false);
  const [rqMsg, setRqMsg] = useState("");
  const [rqGenerating, setRqGenerating] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError("");
    getProjectConfig(projectId)
      .then((c) => {
        setConfig(c);
        setPolicy({ ...(c.mutation_policy || {}) });
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

    getProjectConfigHistory(projectId)
      .then((h) => setHistory(h.entries || []))
      .catch(() => {});

    // ── Fetch research question ──
    setRqLoading(true);
    setRqMsg("");
    getResearchQuestion(projectId)
      .then((rq) => setRqData(rq))
      .catch(() => {})
      .finally(() => setRqLoading(false));
  }, [open, projectId]);

  function switchTab(tab: TabKey) {
    setTab(tab);
    if (tab === "history") {
      getProjectConfigHistory(projectId)
        .then((h) => setHistory(h.entries || []))
        .catch(() => {});
    }
  }

  function handlePolicyChange(key: string, level: string) {
    setPolicy((prev) => ({ ...prev, [key]: level }));
  }

  async function handleSavePolicy() {
    if (!config) return;
    setSaving(true);
    setSaveMsg("");
    try {
      await updateMutationPolicy(projectId, policy);
      setSaveMsg(t("projectConfig.policySaved"));
      // Refresh config
      const c = await getProjectConfig(projectId);
      setConfig(c);
      setPolicy({ ...(c.mutation_policy || {}) });
    } catch (e: any) {
      setSaveMsg("❌ " + e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerateResearchQuestion() {
    setRqGenerating(true);
    setRqMsg("");
    try {
      await generateResearchQuestion(projectId);
      setRqMsg(t("projectConfig.generateSuccess"));
      // Poll for result after a short delay
      setTimeout(async () => {
        try {
          const rq = await getResearchQuestion(projectId);
          setRqData(rq);
        } catch {}
      }, 8000);
    } catch (e: any) {
      setRqMsg("❌ " + (e.message || t("projectConfig.generateError")));
    } finally {
      setRqGenerating(false);
    }
  }

  async function handleAcceptSuggestion(s: ConfigSuggestion) {
    // Apply the suggestion by calling the appropriate endpoint
    try {
      if (s.field.startsWith("population_assumption.")) {
        const key = s.field.replace("population_assumption.", "");
        const val = JSON.parse(s.new_value);
        await updatePopulationAssumption(projectId, { [key]: val });
      }
      setSaveMsg(t("projectConfig.suggestionApplied"));
      // Refresh
      const c = await getProjectConfig(projectId);
      setConfig(c);
      getProjectConfigHistory(projectId)
        .then((h) => setHistory(h.entries || []))
        .catch(() => {});
    } catch (e: any) {
      setSaveMsg("❌ " + e.message);
    }
  }

  if (!open) return null;

  /* ── Render helpers ──────────────────────────────────────────── */

  const renderConfigTab = () => {
    if (!config)
      return <p style={{ color: "#8B949E" }}>{t("common.loading")}</p>;

    const pa = config.population_assumption || {};
    const seg = config.config_segmentacion || {};

    return (
      <div>
        <SectionTitle title={t("projectConfig.generalConfig")} />
        <FieldRow label={t("projectConfig.fieldName")} value={config.nombre} />
        <FieldRow
          label={t("projectConfig.fieldStatus")}
          value={config.estado}
        />
        <FieldRow
          label={t("projectConfig.fieldCodingPath")}
          value={config.ruta_de_codificacion}
        />

        <SectionTitle title={t("projectConfig.epistemologicalConfig")} />
        <FieldRow
          label={t("projectConfig.fieldPopulationAssumption")}
          value={config.supuesto_poblacional || "—"}
        />
        <FieldRow
          label={t("projectConfig.fieldStudyObject")}
          value={config.object_of_study}
        />
        <FieldRow
          label={t("projectConfig.fieldPopulationDescription")}
          value={pa.population_description || "—"}
        />
        <FieldRow
          label={t("projectConfig.fieldTimeframe")}
          value={pa.temporal_frame || "—"}
        />
        <FieldRow
          label={t("projectConfig.fieldSpatialScope")}
          value={pa.spatial_frame || "—"}
        />
        <FieldRow
          label={t("projectConfig.fieldExpectedGerund")}
          value={pa.gerundio_esperado || t("projectConfig.defaultGerund")}
        />

        {/* ── Research Question (Nemotrón) ── */}
        <SectionTitle title={t("projectConfig.researchQuestionSection")} />
        {rqLoading ? (
          <p style={{ color: "#8B949E", fontSize: 12, padding: "8px 0" }}>
            {t("common.loading")}
          </p>
        ) : rqData?.research_question ? (
          <>
            <FieldRow
              label={t("projectConfig.fieldResearchQuestion")}
              value={rqData.research_question || "—"}
            />
            <FieldRow
              label={t("projectConfig.fieldOperationalQuestion")}
              value={rqData.operational_question || "—"}
            />
            {rqData.rationale && (
              <FieldRow
                label={t("projectConfig.fieldRQRationale")}
                value={rqData.rationale || "—"}
              />
            )}
            {rqData.key_dimensions && rqData.key_dimensions.length > 0 && (
              <FieldRow
                label={t("projectConfig.fieldKeyDimensions")}
                value={rqData.key_dimensions
                  .map((d: any) => d.dimension)
                  .join(", ")}
              />
            )}
            {rqData.generated_at && (
              <FieldRow
                label={t("projectConfig.fieldGeneratedAt")}
                value={new Date(rqData.generated_at).toLocaleString()}
              />
            )}
            {/* Regenerate button */}
            {!rqGenerating && (
              <div style={{ padding: "8px 0" }}>
                <button
                  onClick={handleGenerateResearchQuestion}
                  style={{ ...BTN_SECONDARY, fontSize: 11 }}
                >
                  {t("projectConfig.generateButton")}
                </button>
                {rqMsg && (
                  <p
                    style={{
                      color: rqMsg.startsWith("✅") ? "#3FB950" : "#F85149",
                      fontSize: 12,
                      marginTop: 8,
                    }}
                  >
                    {rqMsg}
                  </p>
                )}
              </div>
            )}
          </>
        ) : (
          <div style={{ padding: "8px 0" }}>
            <p
              style={{
                color: "#8B949E",
                fontSize: 12,
                margin: "0 0 8px 0",
              }}
            >
              {t("projectConfig.noResearchQuestion")}
            </p>
            <p
              style={{
                color: "#6E7681",
                fontSize: 11,
                margin: "0 0 10px 0",
                lineHeight: 1.5,
              }}
            >
              {t("projectConfig.noResearchQuestionHelp")}
            </p>
            <button
              onClick={handleGenerateResearchQuestion}
              disabled={rqGenerating}
              style={{
                ...BTN_PRIMARY,
                opacity: rqGenerating ? 0.6 : 1,
                cursor: rqGenerating ? "not-allowed" : "pointer",
              }}
            >
              {rqGenerating
                ? t("projectConfig.generating")
                : t("projectConfig.generateButton")}
            </button>
            {rqMsg && (
              <p
                style={{
                  color: rqMsg.startsWith("✅") ? "#3FB950" : "#F85149",
                  fontSize: 12,
                  marginTop: 8,
                }}
              >
                {rqMsg}
              </p>
            )}
          </div>
        )}

        <SectionTitle title={t("projectConfig.codingStylesSection")} />
        <FieldRow
          label={t("projectConfig.fieldCompiledInstruction")}
          value={config.coding_style_instruction || "—"}
        />
        <FieldRow
          label={t("projectConfig.fieldActiveStyles")}
          value={
            Array.isArray(pa.coding_styles)
              ? pa.coding_styles.join(", ")
              : t("projectConfig.defaultCodingStyles")
          }
        />

        <SectionTitle title={t("projectConfig.segmentationSection")} />
        <FieldRow
          label={t("projectConfig.fieldWindowSize")}
          value={
            seg.window_size != null
              ? String(seg.window_size)
              : t("projectConfig.defaultWindowSize")
          }
        />
        <FieldRow
          label={t("projectConfig.fieldSimilarityThreshold")}
          value={
            seg.similarity_threshold != null
              ? String(seg.similarity_threshold)
              : t("projectConfig.defaultSimilarityThreshold")
          }
        />
        <FieldRow
          label={t("projectConfig.fieldMaxTokens")}
          value={
            seg.max_tokens != null
              ? String(seg.max_tokens)
              : t("projectConfig.defaultMaxTokens")
          }
        />
        <FieldRow
          label={t("projectConfig.fieldReinertMicro")}
          value={
            seg.reinert_micro != null
              ? String(seg.reinert_micro)
              : t("projectConfig.defaultReinertMicro")
          }
        />
      </div>
    );
  };

  const renderHistoryTab = () => {
    if (history.length === 0) {
      return (
        <p style={{ color: "#484F58", textAlign: "center", padding: 40 }}>
          {t("projectConfig.noChanges")}
        </p>
      );
    }

    return (
      <div>
        {history.map((entry) => (
          <div key={entry.id} style={HISTORY_ENTRY}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 4,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{ fontSize: 12, fontWeight: 600, color: "#E6EDF3" }}
                >
                  {fieldLabel(t, entry.field)}
                </span>
                {entry.mutation_level && (
                  <span>{levelBadge(t, entry.mutation_level)}</span>
                )}
              </div>
              <span style={{ fontSize: 10, color: "#484F58" }}>
                {timeAgo(t, entry.timestamp)}
              </span>
            </div>

            <div
              style={{
                display: "flex",
                gap: 8,
                fontSize: 11,
                marginTop: 4,
              }}
            >
              <span style={{ color: "#8B949E" }}>
                {triggerLabel(t, entry.triggered_by)}
              </span>
              {entry.confidence != null && (
                <span style={{ color: "#484F58" }}>
                  {t("projectConfig.confidenceLabel")}
                  {(entry.confidence * 100).toFixed(0)}%
                </span>
              )}
            </div>

            <div
              style={{
                display: "flex",
                gap: 16,
                marginTop: 6,
                fontSize: 11,
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ color: "#484F58", marginBottom: 2 }}>
                  {t("projectConfig.columnPrevious")}
                </div>
                <code
                  style={{
                    display: "block",
                    padding: "4px 6px",
                    background: "#0D1117",
                    borderRadius: 4,
                    color: entry.old_value ? "#F85149" : "#484F58",
                    fontSize: 10,
                    wordBreak: "break-all",
                    maxHeight: 60,
                    overflow: "auto",
                  }}
                >
                  {entry.old_value
                    ? tryParseJson(entry.old_value)
                    : t("projectConfig.creationPlaceholder")}
                </code>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ color: "#484F58", marginBottom: 2 }}>
                  {t("projectConfig.columnNew")}
                </div>
                <code
                  style={{
                    display: "block",
                    padding: "4px 6px",
                    background: "#0D1117",
                    borderRadius: 4,
                    color: "#3FB950",
                    fontSize: 10,
                    wordBreak: "break-all",
                    maxHeight: 60,
                    overflow: "auto",
                  }}
                >
                  {tryParseJson(entry.new_value)}
                </code>
              </div>
            </div>

            {entry.rationale && (
              <div
                style={{
                  marginTop: 6,
                  padding: "6px 8px",
                  background: "#1C2333",
                  borderRadius: 4,
                  fontSize: 11,
                  color: "#8B949E",
                  fontStyle: "italic",
                }}
              >
                {entry.rationale}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderSuggestionsTab = () => {
    const suggestions = config?.pending_suggestions || [];

    if (suggestions.length === 0) {
      return (
        <div style={{ textAlign: "center", padding: 40 }}>
          <p style={{ color: "#484F58", fontSize: 13 }}>
            {t("projectConfig.noSuggestions")}
          </p>
          <p style={{ color: "#484F58", fontSize: 11, marginTop: 4 }}>
            {t("projectConfig.noSuggestionsHelp")}
          </p>
        </div>
      );
    }

    return (
      <div>
        {suggestions.map((s) => (
          <div
            key={s.id}
            style={{
              ...HISTORY_ENTRY,
              borderLeft: "3px solid #D29922",
              paddingLeft: 12,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 4,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{ fontSize: 12, fontWeight: 600, color: "#D29922" }}
                >
                  💡 {fieldLabel(t, s.field)}
                </span>
              </div>
              <span style={{ fontSize: 10, color: "#484F58" }}>
                {timeAgo(t, s.timestamp)}
              </span>
            </div>

            <div style={{ fontSize: 11, color: "#8B949E", marginTop: 4 }}>
              {triggerLabel(t, s.triggered_by)}
              {s.confidence != null && (
                <span style={{ marginLeft: 8, color: "#484F58" }}>
                  {t("projectConfig.confidenceLabel")}
                  {(s.confidence * 100).toFixed(0)}%
                </span>
              )}
            </div>

            <div
              style={{
                display: "flex",
                gap: 16,
                marginTop: 6,
                fontSize: 11,
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ color: "#484F58", marginBottom: 2 }}>
                  {t("projectConfig.columnCurrent")}
                </div>
                <code style={codeStyle}>{tryParseJson(s.old_value)}</code>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ color: "#484F58", marginBottom: 2 }}>
                  {t("projectConfig.columnProposed")}
                </div>
                <code style={{ ...codeStyle, color: "#D29922" }}>
                  {tryParseJson(s.new_value)}
                </code>
              </div>
            </div>

            {s.rationale && (
              <div
                style={{
                  marginTop: 6,
                  padding: "6px 8px",
                  background: "#1C2333",
                  borderRadius: 4,
                  fontSize: 11,
                  color: "#8B949E",
                  fontStyle: "italic",
                }}
              >
                {s.rationale}
              </div>
            )}

            <div
              style={{
                marginTop: 8,
                display: "flex",
                gap: 8,
                justifyContent: "flex-end",
              }}
            >
              <button
                style={BTN_REJECT}
                onClick={() => {
                  /* TODO: reject suggestion endpoint */
                }}
              >
                {t("projectConfig.rejectButton")}
              </button>
              <button
                style={BTN_ACCEPT}
                onClick={() => handleAcceptSuggestion(s)}
              >
                {t("projectConfig.acceptButton")}
              </button>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderPolicyTab = () => {
    if (!config) return null;

    const keys = Object.keys(config.mutation_policy || {});

    return (
      <div>
        <p
          style={{
            fontSize: 12,
            color: "#8B949E",
            marginBottom: 16,
            lineHeight: 1.6,
          }}
        >
          {t("projectConfig.policyHelp")}
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: "8px 12px",
            alignItems: "center",
          }}
        >
          {keys.map((key) => {
            const current = policy[key] || "suggest";
            return (
              <>
                <div style={{ fontSize: 12, color: "#E6EDF3" }}>
                  {fieldLabel(t, key)}
                </div>
                <select
                  value={current}
                  onChange={(e) => handlePolicyChange(key, e.target.value)}
                  style={selectStyle}
                >
                  <option value="auto">
                    {t("projectConfig.policyLevelAuto")}
                  </option>
                  <option value="suggest">
                    {t("projectConfig.policyLevelSuggest")}
                  </option>
                  <option value="require_approval">
                    {t("projectConfig.policyLevelRequireApproval")}
                  </option>
                  <option value="locked">
                    {t("projectConfig.policyLevelLocked")}
                  </option>
                </select>
              </>
            );
          })}
        </div>

        {saveMsg && (
          <div
            style={{
              marginTop: 12,
              fontSize: 12,
              color: saveMsg.startsWith("✅") ? "#3FB950" : "#F85149",
            }}
          >
            {saveMsg}
          </div>
        )}

        <div style={{ marginTop: 16, textAlign: "right" }}>
          <button
            onClick={handleSavePolicy}
            disabled={saving}
            style={{
              ...BTN_PRIMARY,
              opacity: saving ? 0.6 : 1,
              cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            {saving ? t("projectConfig.saving") : t("projectConfig.savePolicy")}
          </button>
        </div>

        {/* Legend */}
        <div
          style={{
            marginTop: 20,
            padding: "10px 12px",
            background: "#1C2333",
            borderRadius: 8,
            border: "1px solid #21262D",
          }}
        >
          <div style={{ fontSize: 11, color: "#8B949E", marginBottom: 8 }}>
            {t("projectConfig.legendTitle")}
          </div>
          {Object.entries(LEVEL_KEYS).map(([lvl, info]) => (
            <div
              key={lvl}
              style={{
                fontSize: 11,
                color: "#C9D1D9",
                marginBottom: 4,
                display: "flex",
                gap: 8,
              }}
            >
              <span style={{ color: info.color }}>{t(info.key)}</span>
              <span style={{ color: "#484F58" }}>
                {lvl === "auto"
                  ? t("projectConfig.legendAuto")
                  : lvl === "suggest"
                    ? t("projectConfig.legendSuggest")
                    : lvl === "require_approval"
                      ? t("projectConfig.legendRequireApproval")
                      : t("projectConfig.legendLocked")}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  /* ── Main render ─────────────────────────────────────────────── */

  if (loading) {
    return (
      <div style={OVERLAY}>
        <div
          style={{
            ...MODAL,
            alignItems: "center",
            justifyContent: "center",
            minHeight: 300,
          }}
        >
          <p style={{ color: "#8B949E" }}>{t("projectConfig.loading")}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={OVERLAY}>
        <div
          style={{
            ...MODAL,
            alignItems: "center",
            justifyContent: "center",
            minHeight: 300,
          }}
        >
          <p style={{ color: "#F85149" }}>
            {t("projectConfig.errorPrefix")}
            {error}
          </p>
          <button style={BTN_SECONDARY} onClick={onClose}>
            {t("projectConfig.closeButton")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={OVERLAY} onClick={onClose}>
      <div style={MODAL} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={HEADER}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 16, fontWeight: 600, color: "#E6EDF3" }}>
              {t("projectConfig.title")}
            </span>
            <span
              style={{
                ...BADGE,
                background: "#A371F722",
                color: "#A371F7",
                border: "1px solid #A371F733",
              }}
            >
              {config?.nombre || projectId.slice(0, 8)}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#8B949E",
              fontSize: 18,
              cursor: "pointer",
              padding: "4px 8px",
            }}
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div style={TAB_ROW}>
          {(
            [
              ["config", t("projectConfig.tabConfig")],
              ["history", t("projectConfig.tabHistory")],
              ["suggestions", t("projectConfig.tabSuggestions")],
              ["policy", t("projectConfig.tabPolicy")],
            ] as [TabKey, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => switchTab(key)}
              style={{
                ...tabBase,
                borderBottomColor: tab === key ? "#A371F7" : "transparent",
                color: tab === key ? "#E6EDF3" : "#8B949E",
              }}
            >
              {label}
              {key === "suggestions" &&
                (config?.pending_suggestions?.length || 0) > 0 && (
                  <span
                    style={{
                      marginLeft: 6,
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: "#D29922",
                      color: "#0D1117",
                      fontSize: 10,
                      fontWeight: 700,
                    }}
                  >
                    {config!.pending_suggestions.length}
                  </span>
                )}
            </button>
          ))}
        </div>

        {/* Body */}
        <div style={BODY}>
          {tab === "config" && renderConfigTab()}
          {tab === "history" && renderHistoryTab()}
          {tab === "suggestions" && renderSuggestionsTab()}
          {tab === "policy" && renderPolicyTab()}
        </div>

        {/* Footer */}
        <div style={FOOTER}>
          <span style={{ fontSize: 11, color: "#484F58", flex: 1 }}>
            {tab === "history"
              ? `${history.length}${t("projectConfig.footerChanges")}`
              : tab === "suggestions"
                ? `${config?.pending_suggestions?.length || 0}${t("projectConfig.footerSuggestions")}`
                : `${t("projectConfig.footerStatus")}${config?.estado || "—"}`}
          </span>
          <button style={BTN_SECONDARY} onClick={onClose}>
            {t("projectConfig.closeButton")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Mini components ───────────────────────────────────────────────── */

function SectionTitle({ title }: { title: string }) {
  return (
    <div
      style={{
        fontSize: 12,
        fontWeight: 600,
        color: "#A371F7",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        marginTop: 20,
        marginBottom: 8,
        borderTop: "1px solid #21262D",
        paddingTop: 12,
      }}
    >
      {title}
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={FIELD_ROW}>
      <span style={FIELD_KEY}>{label}</span>
      <span style={FIELD_VAL}>{value}</span>
    </div>
  );
}

const codeStyle: CSSProperties = {
  display: "block",
  padding: "4px 6px",
  background: "#0D1117",
  borderRadius: 4,
  color: "#C9D1D9",
  fontSize: 10,
  wordBreak: "break-all",
  maxHeight: 60,
  overflow: "auto",
};

const selectStyle: CSSProperties = {
  padding: "4px 8px",
  borderRadius: 6,
  background: "#0D1117",
  border: "1px solid #21262D",
  color: "#E6EDF3",
  fontSize: 11,
  cursor: "pointer",
  minWidth: 160,
};
