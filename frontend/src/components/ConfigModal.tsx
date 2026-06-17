import { useEffect, useState, useCallback } from "react";
import { getToken, clearToken } from "../api/client";
import { useI18n } from "../i18n";

/* ── Types ─────────────────────────────────────────────────────────── */

interface LLMConfig {
  model_pro: string;
  model_pro_max_tokens: number;
  model_pro_temperature: number;
  model_flash: string;
  model_flash_max_tokens: number;
  model_flash_temperature: number;
  model_flash_repetition_penalty: number;
  model_flash_top_p: number;
  env_overrides: Record<string, string>;
}

interface SegmentationConfig {
  mode: string;
  reinert: boolean;
  spacy_model: string;
  nlp_concurrency: number;
  env_overrides: Record<string, string>;
}

interface CodingStyle {
  key: string;
  name: string;
  saldana_category: string;
  examples: string[];
}

interface CGTConfig {
  population_assumption: string;
  object_of_study: string;
  coding_styles: string[];
  available_styles: CodingStyle[];
  env_overrides: Record<string, string>;
}

interface SystemConfig {
  environment: string;
  orchestration_mode: string;
  use_gpu: boolean;
  env_overrides: Record<string, string>;
}

interface FullConfig {
  llm: LLMConfig;
  segmentation: SegmentationConfig;
  cgt: CGTConfig;
  system: SystemConfig;
  auth: { algorithm: string; token_type: string };
  _runtime_overrides: Record<string, string>;
}

interface UserInfo {
  user_id: string;
  email?: string;
  name?: string;
}

/* ── Styles ────────────────────────────────────────────────────────── */

const OVERLAY: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.65)",
  zIndex: 1000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const MODAL: React.CSSProperties = {
  background: "#161B22",
  border: "1px solid #30363D",
  borderRadius: 14,
  width: 800,
  height: 600,
  maxHeight: "85vh",
  display: "flex",
  flexDirection: "column",
  boxShadow: "0 12px 60px rgba(0,0,0,0.6)",
};

const HEADER: React.CSSProperties = {
  padding: "12px 20px",
  borderBottom: "1px solid #21262D",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  flexShrink: 0,
};

const MAIN_ROW: React.CSSProperties = {
  display: "flex",
  flex: 1,
  overflow: "hidden",
};

// ── Sidebar ──

const SIDEBAR: React.CSSProperties = {
  width: 200,
  flexShrink: 0,
  borderRight: "1px solid #21262D",
  padding: "10px 0",
  display: "flex",
  flexDirection: "column",
  gap: 2,
};

const NAV_ITEM: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "10px 16px",
  margin: "0 6px",
  borderRadius: 8,
  fontSize: 13,
  cursor: "pointer",
  color: "#8B949E",
  background: "transparent",
  border: "none",
  textAlign: "left",
  transition: "all 0.15s",
  width: "calc(100% - 12px)",
};

const NAV_ITEM_ACTIVE: React.CSSProperties = {
  ...NAV_ITEM,
  color: "#E6EDF3",
  background: "#A371F712",
  fontWeight: 600,
};

const NAV_ICON: React.CSSProperties = {
  fontSize: 16,
  width: 24,
  textAlign: "center",
  flexShrink: 0,
};

const BODY: React.CSSProperties = {
  padding: "16px 20px",
  overflowY: "auto",
  flex: 1,
};

const FOOTER: React.CSSProperties = {
  padding: "12px 20px",
  borderTop: "1px solid #21262D",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  flexShrink: 0,
};

const SECT: React.CSSProperties = { marginBottom: 18 };

const SECT_TITLE: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.8px",
  color: "#A371F7",
  marginBottom: 10,
};

const FIELD: React.CSSProperties = { marginBottom: 12 };

const LABEL: React.CSSProperties = {
  fontSize: 12,
  color: "#8B949E",
  marginBottom: 4,
  display: "block",
};

const INPUT: React.CSSProperties = {
  width: "100%",
  padding: "7px 10px",
  borderRadius: 6,
  background: "#0D1117",
  border: "1px solid #21262D",
  color: "#E6EDF3",
  fontSize: 13,
  fontFamily: "monospace",
};

const SELECT: React.CSSProperties = {
  ...INPUT,
  cursor: "pointer",
};

const TOGGLE_ROW: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
};

const TOGGLE: React.CSSProperties = {
  width: 40,
  height: 22,
  borderRadius: 11,
  border: "none",
  cursor: "pointer",
  position: "relative",
  transition: "background 0.2s",
};

const TOGGLE_KNOB: React.CSSProperties = {
  width: 16,
  height: 16,
  borderRadius: "50%",
  background: "#fff",
  position: "absolute",
  top: 3,
  transition: "left 0.2s",
};

const BTN_PRIMARY: React.CSSProperties = {
  padding: "7px 20px",
  borderRadius: 6,
  border: "none",
  background: "#A371F7",
  color: "#fff",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const BTN_DANGER: React.CSSProperties = {
  padding: "7px 20px",
  borderRadius: 6,
  border: "1px solid #F8514933",
  background: "#F8514918",
  color: "#F85149",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const BADGE: React.CSSProperties = {
  padding: "1px 6px",
  borderRadius: 999,
  fontSize: 10,
  fontWeight: 600,
};

const FLOAT_BTN: React.CSSProperties = {
  position: "fixed",
  bottom: 20,
  right: 20,
  zIndex: 999,
  width: 44,
  height: 44,
  borderRadius: "50%",
  background: "#A371F7",
  border: "none",
  color: "#fff",
  fontSize: 20,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "0 2px 16px rgba(163,113,247,0.4)",
  transition: "all 0.2s",
};

/* ── Floating Button ───────────────────────────────────────────────── */

export function ConfigButton({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();
  return (
    <button
      onClick={onClick}
      style={FLOAT_BTN}
      title={t("config.configTooltip")}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "scale(1.08)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "scale(1)";
      }}
    >
      ⚙
    </button>
  );
}

/* ── Toggle Component ──────────────────────────────────────────────── */

function ToggleSwitch({
  on,
  onChange,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!on)}
      style={{ ...TOGGLE, background: on ? "#2EA043" : "#30363D" }}
    >
      <span style={{ ...TOGGLE_KNOB, left: on ? 21 : 3 }} />
    </button>
  );
}

/* ── Field Components ──────────────────────────────────────────────── */

function TextField({
  label,
  value,
  onChange,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
}) {
  return (
    <div style={FIELD}>
      <span style={LABEL}>{label}</span>
      <input
        style={{ ...INPUT, fontFamily: mono ? "monospace" : undefined }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div style={FIELD}>
      <span style={LABEL}>{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        style={INPUT}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      />
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div style={FIELD}>
      <span style={LABEL}>{label}</span>
      <select
        style={SELECT}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function TextareaField({
  label,
  value,
  onChange,
  rows,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <div style={FIELD}>
      <span style={LABEL}>{label}</span>
      <textarea
        style={{
          ...INPUT,
          resize: "vertical",
          minHeight: rows ? rows * 20 : 60,
          fontFamily: "sans-serif",
        }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows || 3}
      />
    </div>
  );
}

function ToggleField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  return (
    <div style={FIELD}>
      <div style={TOGGLE_ROW}>
        <ToggleSwitch on={value} onChange={onChange} />
        <span style={{ fontSize: 13, color: "#E6EDF3" }}>{label}</span>
      </div>
      {hint && (
        <span
          style={{
            fontSize: 11,
            color: "#484F58",
            marginTop: 2,
            display: "block",
          }}
        >
          {hint}
        </span>
      )}
    </div>
  );
}

function EnvOverrideBadge({
  overrides,
  blockedLabel,
}: {
  overrides: Record<string, string>;
  blockedLabel: string;
}) {
  const keys = Object.keys(overrides);
  if (keys.length === 0) return null;
  return (
    <div
      style={{
        marginTop: 4,
        fontSize: 10,
        color: "#D29922",
        background: "#D2992211",
        padding: "4px 8px",
        borderRadius: 4,
        border: "1px solid #D2992233",
      }}
    >
      {blockedLabel}
      {keys.join(", ")}
    </div>
  );
}

/* ── Main Modal ────────────────────────────────────────────────────── */

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ConfigModal({ open, onClose }: Props) {
  const { t, language, setLanguage } = useI18n();
  const [tab, setTab] = useState<
    "llm" | "segmentation" | "cgt" | "system" | "session"
  >("llm");
  const [config, setConfig] = useState<FullConfig | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [error, setError] = useState("");

  // ── Editable state ──────────────────────────────────────────────
  const [llm, setLlm] = useState<LLMConfig | null>(null);
  const [seg, setSeg] = useState<SegmentationConfig | null>(null);
  const [cgt, setCgt] = useState<CGTConfig | null>(null);
  const [sys, setSys] = useState<SystemConfig | null>(null);

  const token = getToken();

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/v1/config");
      if (!res.ok) throw new Error(t("config.backendUnavailable"));
      const data: FullConfig = await res.json();
      setConfig(data);
      setLlm(data.llm);
      setSeg(data.segmentation);
      setCgt(data.cgt);
      setSys(data.system);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [t]);

  const fetchSession = useCallback(async () => {
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const res = await fetch("/api/v1/ping", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setUser({ user_id: d.user_id, email: d.email, name: d.name });
      }
    } catch {
      /* */
    }
  }, [token]);

  useEffect(() => {
    if (!open) return;
    fetchConfig();
    fetchSession();
  }, [open, fetchConfig, fetchSession]);

  async function handleSave() {
    setSaving(true);
    setSaveMsg("");
    try {
      const body: any = {};
      if (llm)
        body.llm = {
          model_pro: llm.model_pro,
          model_pro_max_tokens: llm.model_pro_max_tokens,
          model_pro_temperature: llm.model_pro_temperature,
          model_flash: llm.model_flash,
          model_flash_max_tokens: llm.model_flash_max_tokens,
          model_flash_temperature: llm.model_flash_temperature,
          model_flash_repetition_penalty: llm.model_flash_repetition_penalty,
          model_flash_top_p: llm.model_flash_top_p,
        };
      if (seg)
        body.segmentation = {
          mode: seg.mode,
          reinert: seg.reinert,
          spacy_model: seg.spacy_model,
          nlp_concurrency: seg.nlp_concurrency,
        };
      if (cgt)
        body.cgt = {
          population_assumption: cgt.population_assumption,
          object_of_study: cgt.object_of_study,
          coding_styles: cgt.coding_styles,
        };
      if (sys)
        body.system = {
          environment: sys.environment,
          orchestration_mode: sys.orchestration_mode,
          use_gpu: sys.use_gpu,
        };

      const res = await fetch("/api/v1/config", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        setSaveMsg(data.message || t("config.saved"));
        if (data.blocked_by_env) {
          setSaveMsg(
            (data.message || t("config.savedMessage")) +
              t("config.savedBlockedMessage"),
          );
        }
        // Refresh config to get updated values
        await fetchConfig();
      } else {
        setSaveMsg(
          t("config.saveErrorPrefix") +
            (data.detail || t("config.saveErrorFallback")),
        );
      }
    } catch (e: any) {
      setSaveMsg(t("config.saveErrorPrefix") + e.message);
    } finally {
      setSaving(false);
    }
  }

  function handleLogout() {
    clearToken();
    onClose();
    window.location.href = "/login";
  }

  if (!open) return null;

  const envBadge = (env: string) =>
    env === "dev"
      ? { ...BADGE, background: "#D2992222", color: "#D29922" }
      : env === "prod"
        ? { ...BADGE, background: "#2EA04322", color: "#2EA043" }
        : { ...BADGE, background: "#8B949E22", color: "#8B949E" };

  return (
    <div style={OVERLAY} onClick={onClose}>
      <div style={MODAL} onClick={(e) => e.stopPropagation()}>
        {/* ── Header ── */}
        <div style={HEADER}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: "#E6EDF3" }}>
              {t("config.title")}
            </span>
            {config && (
              <span style={envBadge(config.system.environment)}>
                {config.system.environment}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#8B949E",
              fontSize: 18,
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* ── Main row: Sidebar + Content ── */}
        <div style={MAIN_ROW}>
          {/* ── Sidebar ── */}
          <div style={SIDEBAR}>
            {(
              [
                [
                  "session",
                  token ? "🔐" : "🔓",
                  token
                    ? t("config.tabSession")
                    : t("config.tabSessionLoggedOut"),
                ],
                ["system", "💻", t("config.tabSystem")],
                ["llm", "🧠", t("config.tabLLM")],
                ["segmentation", "📝", t("config.tabSegmentation")],
                ["cgt", "📐", t("config.tabCGT")],
              ] as const
            ).map(([k, icon, label]) => (
              <button
                key={k}
                style={tab === k ? NAV_ITEM_ACTIVE : NAV_ITEM}
                onClick={() => setTab(k)}
              >
                <span style={NAV_ICON}>{icon}</span>
                {label}
              </button>
            ))}
          </div>

          {/* ── Body ── */}
          <div style={BODY}>
            {loading && (
              <p style={{ color: "#8B949E", fontSize: 13 }}>
                {t("config.loading")}
              </p>
            )}
            {error && <p style={{ color: "#F85149", fontSize: 13 }}>{error}</p>}

            {/* ─── LLM ──────────────────────────────────────────── */}
            {tab === "llm" && llm && (
              <>
                <div style={SECT}>
                  <div style={SECT_TITLE}>{t("config.modelPro")}</div>
                  <TextField
                    label={t("config.modelId")}
                    value={llm.model_pro}
                    onChange={(v) => setLlm({ ...llm, model_pro: v })}
                    mono
                  />
                  <NumberField
                    label={t("config.maxTokens")}
                    value={llm.model_pro_max_tokens}
                    onChange={(v) =>
                      setLlm({ ...llm, model_pro_max_tokens: v })
                    }
                    min={256}
                    max={65536}
                  />
                  <NumberField
                    label={t("config.temperature")}
                    value={llm.model_pro_temperature}
                    onChange={(v) =>
                      setLlm({ ...llm, model_pro_temperature: v })
                    }
                    min={0}
                    max={2}
                    step={0.05}
                  />
                  <EnvOverrideBadge
                    overrides={llm.env_overrides}
                    blockedLabel={t("config.blockedByEnv")}
                  />
                </div>
                <div style={SECT}>
                  <div style={SECT_TITLE}>{t("config.modelFlash")}</div>
                  <TextField
                    label={t("config.modelId")}
                    value={llm.model_flash}
                    onChange={(v) => setLlm({ ...llm, model_flash: v })}
                    mono
                  />
                  <NumberField
                    label={t("config.maxTokens")}
                    value={llm.model_flash_max_tokens}
                    onChange={(v) =>
                      setLlm({ ...llm, model_flash_max_tokens: v })
                    }
                    min={256}
                    max={65536}
                  />
                  <NumberField
                    label={t("config.temperature")}
                    value={llm.model_flash_temperature}
                    onChange={(v) =>
                      setLlm({ ...llm, model_flash_temperature: v })
                    }
                    min={0}
                    max={2}
                    step={0.05}
                  />
                  <NumberField
                    label={t("config.repetitionPenalty")}
                    value={llm.model_flash_repetition_penalty}
                    onChange={(v) =>
                      setLlm({ ...llm, model_flash_repetition_penalty: v })
                    }
                    min={0}
                    max={2}
                    step={0.05}
                  />
                  <NumberField
                    label={t("config.topP")}
                    value={llm.model_flash_top_p}
                    onChange={(v) => setLlm({ ...llm, model_flash_top_p: v })}
                    min={0}
                    max={1}
                    step={0.05}
                  />
                  <EnvOverrideBadge
                    overrides={llm.env_overrides}
                    blockedLabel={t("config.blockedByEnv")}
                  />
                </div>
              </>
            )}

            {/* ─── Segmentation ──────────────────────────────────── */}
            {tab === "segmentation" && seg && (
              <div style={SECT}>
                <div style={SECT_TITLE}>{t("config.segmentationPipeline")}</div>
                <SelectField
                  label={t("config.mode")}
                  value={seg.mode}
                  options={[
                    { value: "spacy", label: t("config.modeSpaCy") },
                    {
                      value: "progressive",
                      label: t("config.modeProgressive"),
                    },
                    {
                      value: "reinert",
                      label: t("config.modeReinert"),
                    },
                  ]}
                  onChange={(v) => setSeg({ ...seg, mode: v })}
                />
                <ToggleField
                  label={t("config.useReinert")}
                  value={seg.reinert}
                  onChange={(v) => setSeg({ ...seg, reinert: v })}
                />
                <TextField
                  label={t("config.spacyModel")}
                  value={seg.spacy_model}
                  onChange={(v) => setSeg({ ...seg, spacy_model: v })}
                  mono
                />
                <NumberField
                  label={t("config.nlpConcurrency")}
                  value={seg.nlp_concurrency}
                  onChange={(v) => setSeg({ ...seg, nlp_concurrency: v })}
                  min={1}
                  max={8}
                />
                <EnvOverrideBadge
                  overrides={seg.env_overrides}
                  blockedLabel={t("config.blockedByEnv")}
                />
              </div>
            )}

            {/* ─── CGT ───────────────────────────────────────────── */}
            {tab === "cgt" && cgt && (
              <>
                <div style={SECT}>
                  <div style={SECT_TITLE}>{t("config.codingStyles")}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {cgt.available_styles.map((s) => {
                      const active = cgt.coding_styles.includes(s.key);
                      return (
                        <button
                          key={s.key}
                          onClick={() => {
                            const next = active
                              ? cgt.coding_styles.filter((k) => k !== s.key)
                              : [...cgt.coding_styles, s.key];
                            setCgt({
                              ...cgt,
                              coding_styles: next.length ? next : ["gerundio"],
                            });
                          }}
                          style={{
                            padding: "4px 10px",
                            borderRadius: 999,
                            fontSize: 11,
                            border: active
                              ? "1px solid #A371F7"
                              : "1px solid #21262D",
                            background: active ? "#A371F718" : "transparent",
                            color: active ? "#A371F7" : "#8B949E",
                            cursor: "pointer",
                            transition: "all 0.15s",
                          }}
                          title={s.saldana_category}
                        >
                          {s.name} {active ? "✓" : ""}
                        </button>
                      );
                    })}
                  </div>
                  <EnvOverrideBadge
                    overrides={cgt.env_overrides}
                    blockedLabel={t("config.blockedByEnv")}
                  />
                </div>
                <div style={SECT}>
                  <div style={SECT_TITLE}>{t("config.cgtMethodology")}</div>
                  <SelectField
                    label={t("config.studyObject")}
                    value={cgt.object_of_study}
                    options={[
                      {
                        value: "concern",
                        label: t("config.concern"),
                      },
                      { value: "emotion", label: t("config.emotion") },
                      { value: "behavior", label: t("config.behavior") },
                      { value: "discourse", label: t("config.discourse") },
                      { value: "identity", label: t("config.identity") },
                      { value: "custom", label: t("config.custom") },
                    ]}
                    onChange={(v) => setCgt({ ...cgt, object_of_study: v })}
                  />
                  <TextareaField
                    label={t("config.populationAssumption")}
                    value={cgt.population_assumption}
                    onChange={(v) =>
                      setCgt({ ...cgt, population_assumption: v })
                    }
                    rows={4}
                  />
                  <EnvOverrideBadge
                    overrides={cgt.env_overrides}
                    blockedLabel={t("config.blockedByEnv")}
                  />
                </div>
              </>
            )}

            {/* ─── System ────────────────────────────────────────── */}
            {tab === "system" && sys && (
              <div style={SECT}>
                <div style={SECT_TITLE}>{t("config.systemDeployment")}</div>
                <SelectField
                  label={t("config.environment")}
                  value={sys.environment}
                  options={[
                    { value: "dev", label: t("config.envDev") },
                    { value: "staging", label: t("config.envStaging") },
                    { value: "prod", label: t("config.envProd") },
                  ]}
                  onChange={(v) => setSys({ ...sys, environment: v })}
                />
                <SelectField
                  label={t("config.orchestrationMode")}
                  value={sys.orchestration_mode}
                  options={[
                    { value: "celery", label: t("config.orchCelery") },
                    { value: "sync", label: t("config.orchSync") },
                  ]}
                  onChange={(v) => setSys({ ...sys, orchestration_mode: v })}
                />
                <ToggleField
                  label={t("config.useGPU")}
                  value={sys.use_gpu}
                  onChange={(v) => setSys({ ...sys, use_gpu: v })}
                />
                <EnvOverrideBadge
                  overrides={sys.env_overrides}
                  blockedLabel={t("config.blockedByEnv")}
                />

                {config &&
                  Object.keys(config._runtime_overrides).length > 0 && (
                    <div
                      style={{
                        marginTop: 12,
                        padding: 10,
                        background: "#0D1117",
                        borderRadius: 6,
                        border: "1px solid #21262D",
                      }}
                    >
                      <div style={{ ...SECT_TITLE, color: "#484F58" }}>
                        {t("config.activeOverrides")}
                      </div>
                      {Object.entries(config._runtime_overrides).map(
                        ([k, v]) => (
                          <div
                            key={k}
                            style={{
                              fontSize: 11,
                              fontFamily: "monospace",
                              color: "#8B949E",
                              padding: "1px 0",
                            }}
                          >
                            <span style={{ color: "#A371F7" }}>{k}</span> = {v}
                          </div>
                        ),
                      )}
                    </div>
                  )}
              </div>
            )}

            {/* ─── Session ────────────────────────────────────────── */}
            {tab === "session" && (
              <>
                {!token ? (
                  <div style={{ textAlign: "center", padding: "30px 0" }}>
                    <p style={{ fontSize: 36, marginBottom: 12 }}>🔓</p>
                    <p style={{ color: "#8B949E", fontSize: 13 }}>
                      {t("config.notLoggedIn")}
                    </p>
                  </div>
                ) : (
                  <div style={SECT}>
                    <div style={SECT_TITLE}>{t("config.userSection")}</div>
                    {user ? (
                      <>
                        <div style={{ ...FIELD }}>
                          <span style={LABEL}>{t("config.userId")}</span>
                          <code style={{ fontSize: 12, color: "#E6EDF3" }}>
                            {user.user_id.slice(0, 12)}…
                          </code>
                        </div>
                        {user.email && (
                          <div style={FIELD}>
                            <span style={LABEL}>{t("config.email")}</span>
                            <span style={{ fontSize: 13, color: "#E6EDF3" }}>
                              {user.email}
                            </span>
                          </div>
                        )}
                        {user.name && (
                          <div style={FIELD}>
                            <span style={LABEL}>{t("config.name")}</span>
                            <span style={{ fontSize: 13, color: "#E6EDF3" }}>
                              {user.name}
                            </span>
                          </div>
                        )}
                      </>
                    ) : (
                      <p style={{ color: "#8B949E", fontSize: 13 }}>
                        {t("config.loading")}
                      </p>
                    )}
                    {/* ── Language selector ── */}
                    <div style={{ ...FIELD, marginTop: 12 }}>
                      <span style={LABEL}>{t("config.language")}</span>
                      <select
                        value={language}
                        onChange={(e) => setLanguage(e.target.value as any)}
                        style={{
                          ...INPUT,
                          width: "100%",
                          cursor: "pointer",
                        }}
                      >
                        <option value="en">{t("config.langEn")}</option>
                        <option value="es">{t("config.langEs")}</option>
                        <option value="de">{t("config.langDe")}</option>
                        <option value="pt">{t("config.langPt")}</option>
                      </select>
                    </div>
                    <div style={{ ...FIELD, marginTop: 12 }}>
                      <span style={LABEL}>{t("config.jwtToken")}</span>
                      <div
                        style={{
                          padding: 6,
                          background: "#0D1117",
                          borderRadius: 4,
                          border: "1px solid #21262D",
                          fontSize: 10,
                          fontFamily: "monospace",
                          color: "#484F58",
                          wordBreak: "break-all",
                          maxHeight: 40,
                          overflow: "hidden",
                        }}
                      >
                        {token.slice(0, 50)}…
                      </div>
                    </div>
                    <div style={{ marginTop: 16 }}>
                      <button onClick={handleLogout} style={BTN_DANGER}>
                        {t("config.signOut")}
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        {/* /MAIN_ROW */}

        {/* ── Footer ── */}
        <div style={FOOTER}>
          <div
            style={{
              fontSize: 12,
              color: saveMsg.includes("❌") ? "#F85149" : "#2EA043",
            }}
          >
            {saveMsg}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                ...BTN_PRIMARY,
                background: "#21262D",
                color: "#8B949E",
              }}
            >
              {t("config.closeButton")}
            </button>
            {tab !== "session" && (
              <button
                onClick={handleSave}
                disabled={saving}
                style={BTN_PRIMARY}
              >
                {saving ? t("common.saving") : t("config.saveButton")}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
