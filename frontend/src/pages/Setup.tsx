import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useI18n } from "../i18n";
import {
  getSetupStatus,
  initializeSetup,
  getSetupProgress,
} from "../api/client";

const BG = "#0D1117";
const CARD = "#161B22";
const BORDER = "#30363D";
const TEXT = "#E6EDF3";
const MUTED = "#8B949E";
const PURPLE = "#A371F7";
const GREEN = "#3FB950";
const RED = "#F85149";

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "de", label: "Deutsch" },
  { value: "pt", label: "Português" },
];

/** Convert 0–1 progress into a set of completed phases for the visual bar. */
function phaseProgress(progress: number) {
  const phases = [
    { key: "spacy", labelKey: "setup.downloadingSpacy" as const },
    { key: "stanza", labelKey: "setup.downloadingStanza" as const },
  ];
  const completed = Math.round(progress * phases.length);
  return phases.map((p, i) => ({ ...p, done: i < completed }));
}

export default function Setup() {
  const { t, language: i18nLang } = useI18n();
  const navigate = useNavigate();

  const [language, setLanguage] = useState(i18nLang);
  const [status, setStatus] = useState<
    "checking" | "downloading" | "ready" | "error"
  >("checking");
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [initialized, setInitialized] = useState(false);

  const doCheck = useCallback(async () => {
    try {
      const s = await getSetupStatus();
      if (s.spacy_ready && s.stanza_ready) {
        setStatus("ready");
        return;
      }
      // Not ready — show language picker, wait for user to click Start
      setStatus("checking");
    } catch (err: any) {
      setStatus("error");
      setErrorMsg(err.message || t("setup.error"));
    }
  }, [t]);

  // Initial status check
  useEffect(() => {
    doCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll progress while downloading
  useEffect(() => {
    if (status !== "downloading") return;
    const id = setInterval(async () => {
      try {
        const p = await getSetupProgress();
        setProgress(p.progress);
        setMessage(p.message);
        if (p.status === "done") {
          setStatus("ready");
          clearInterval(id);
        }
      } catch (err: any) {
        setStatus("error");
        setErrorMsg(err.message || t("setup.error"));
        clearInterval(id);
      }
    }, 2000);
    return () => clearInterval(id);
  }, [status, t]);

  // Auto-redirect to projects after 3s when ready
  useEffect(() => {
    if (status === "ready") {
      const t = setTimeout(() => navigate("/projects"), 3000);
      return () => clearTimeout(t);
    }
  }, [status, navigate]);

  async function handleStart() {
    setStatus("downloading");
    setErrorMsg("");
    try {
      await initializeSetup(language);
      setInitialized(true);
    } catch (err: any) {
      setStatus("error");
      setErrorMsg(err.message || t("setup.error"));
    }
  }

  async function handleRetry() {
    setStatus("checking");
    setErrorMsg("");
    setProgress(0);
    setInitialized(false);
    doCheck();
  }

  const phases = phaseProgress(progress);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: BG,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <div
        style={{
          width: 440,
          padding: "40px 32px",
          background: CARD,
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        }}
      >
        {/* Icon */}
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              background: `linear-gradient(135deg, ${PURPLE}, #7C3AED)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
              fontSize: 24,
            }}
          >
            ⚙️
          </div>
          <h1
            style={{
              color: TEXT,
              fontSize: 22,
              fontWeight: 700,
              margin: 0,
              marginBottom: 8,
            }}
          >
            {t("setup.title")}
          </h1>
        </div>

        {/* Language selector */}
        <div style={{ marginBottom: 24 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              color: MUTED,
              marginBottom: 6,
              fontWeight: 500,
            }}
          >
            {t("setup.languageLabel")}
          </label>
          <select
            value={language}
            onChange={(e) => {
              setLanguage(e.target.value);
              setInitialized(false);
            }}
            disabled={status === "downloading"}
            style={{
              width: "100%",
              padding: "10px 14px",
              background: BG,
              border: `1px solid ${BORDER}`,
              borderRadius: 8,
              color: TEXT,
              fontSize: 14,
              boxSizing: "border-box",
              outline: "none",
              cursor: status === "downloading" ? "not-allowed" : "pointer",
              opacity: status === "downloading" ? 0.6 : 1,
            }}
          >
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>

          {/* Start button — only in initial state */}
          {status === "checking" && (
            <button
              onClick={handleStart}
              style={{
                width: "100%",
                padding: "12px 16px",
                marginTop: 16,
                background: PURPLE,
                border: "none",
                borderRadius: 8,
                color: "#FFF",
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {t("setup.start") || "Start Setup"}
            </button>
          )}
        </div>

        {/* Progress bar */}
        {status !== "error" && (
          <div style={{ marginBottom: 24 }}>
            <div
              style={{
                height: 6,
                borderRadius: 3,
                background: BORDER,
                overflow: "hidden",
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${Math.round(progress * 100)}%`,
                  background: `linear-gradient(90deg, ${PURPLE}, ${GREEN})`,
                  borderRadius: 3,
                  transition: "width 0.5s ease",
                }}
              />
            </div>

            {/* Phase indicators */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {phases.map((p) => (
                <div
                  key={p.key}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: 13,
                    color: p.done ? GREEN : MUTED,
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 18,
                      height: 18,
                      borderRadius: "50%",
                      background: p.done ? GREEN : BORDER,
                      color: p.done ? BG : MUTED,
                      fontSize: 10,
                      fontWeight: 700,
                    }}
                  >
                    {p.done ? "✓" : "○"}
                  </span>
                  {t(p.labelKey)}
                </div>
              ))}
            </div>

            {message && (
              <div
                style={{
                  marginTop: 12,
                  fontSize: 12,
                  color: MUTED,
                  textAlign: "center",
                }}
              >
                {message}
              </div>
            )}
          </div>
        )}

        {/* Ready state */}
        {status === "ready" && (
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                padding: "12px 16px",
                marginBottom: 16,
                background: "rgba(63,185,80,0.1)",
                border: `1px solid ${GREEN}33`,
                borderRadius: 8,
                color: GREEN,
                fontSize: 14,
              }}
            >
              {t("setup.ready")}
            </div>
            <button
              onClick={() => navigate("/projects")}
              style={{
                width: "100%",
                padding: "12px 16px",
                background: GREEN,
                border: "none",
                borderRadius: 8,
                color: "#FFF",
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {t("setup.continue")}
            </button>
          </div>
        )}

        {/* Error state */}
        {status === "error" && (
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                padding: "12px 16px",
                marginBottom: 16,
                background: "rgba(248,81,73,0.1)",
                border: `1px solid ${RED}33`,
                borderRadius: 8,
                color: RED,
                fontSize: 14,
              }}
            >
              {errorMsg || t("setup.error")}
            </div>
            <button
              onClick={handleRetry}
              style={{
                width: "100%",
                padding: "12px 16px",
                background: PURPLE,
                border: "none",
                borderRadius: 8,
                color: "#FFF",
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {t("setup.retry")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
