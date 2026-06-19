import { useState, useMemo } from "react";
import { useI18n } from "../i18n";
import type { AgentLogEntry } from "../api/client";

interface AgentModalProps {
  open: boolean;
  agentId: string;
  agentLabel: string;
  agentLogs: AgentLogEntry[];
  onClose: () => void;
}

type TabKey = "prompt" | "response" | "schema";

// ── Color-coded prompt line rendering ──────────────────────────────

function promptLineColor(line: string): string {
  // Headers / section titles / delimiters → white
  if (/^[A-Z][A-Z ]+:/.test(line)) return "#E6EDF3";
  if (/^###/.test(line)) return "#E6EDF3";
  if (/^---/.test(line)) return "#E6EDF3";
  if (/^\[/.test(line)) return "#E6EDF3";
  // Everything else → amber
  return "#D29922";
}

// ── Component ──────────────────────────────────────────────────────

export default function AgentModal({
  open,
  agentId,
  agentLabel,
  agentLogs,
  onClose,
}: AgentModalProps) {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabKey>("prompt");

  if (!open) return null;

  const promptEntry = useMemo(
    () => agentLogs.find((e) => e.agent_id === agentId && e.type === "prompt_sent"),
    [agentLogs, agentId],
  );

  const responseEntry = useMemo(
    () =>
      agentLogs.find((e) => e.agent_id === agentId && e.type === "prompt_response"),
    [agentLogs, agentId],
  );

  const hasData = !!promptEntry;

  // ── Tab bar ──
  const tabDefs: Array<{ key: TabKey; label: string }> = [
    { key: "prompt", label: "🤖 " + t("project.agentPromptTab") },
    { key: "response", label: "📤 " + t("project.agentResponseTab") },
    { key: "schema", label: "📋 " + t("project.agentSchemaTab") },
  ];

  const tabBarStyle: React.CSSProperties = {
    display: "flex",
    borderBottom: "1px solid #30363D",
    padding: "8px 0",
    marginBottom: 16,
    gap: 0,
  };

  const tabBtnStyle = (isActive: boolean): React.CSSProperties => ({
    padding: "6px 14px",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    background: isActive ? "#A371F722" : "transparent",
    color: isActive ? "#A371F7" : "#8B949E",
  });

  // ── Content ──

  function renderContent() {
    if (!hasData) {
      return (
        <div
          style={{
            padding: "40px 0",
            textAlign: "center",
            color: "#8B949E",
            fontSize: 14,
          }}
        >
          {t("project.agentNoData")}
        </div>
      );
    }

    if (tab === "prompt") {
      const text = promptEntry?.prompt || "";
      const lines = text.split("\n");
      return (
        <pre
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            lineHeight: 1.6,
            color: "#D29922",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}
        >
          {lines.map((line, i) => (
            <span key={i} style={{ color: promptLineColor(line) }}>
              {line}
              {i < lines.length - 1 && "\n"}
            </span>
          ))}
        </pre>
      );
    }

    if (tab === "response") {
      let formatted = "";
      try {
        if (responseEntry?.response) {
          const parsed = JSON.parse(responseEntry.response);
          formatted = JSON.stringify(parsed, null, 2);
        }
      } catch {
        formatted = responseEntry?.response || "";
      }
      return (
        <pre
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            lineHeight: 1.6,
            color: "#E6EDF3",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}
        >
          {formatted || t("project.agentNoData")}
        </pre>
      );
    }

    // schema tab
    let schemaFormatted = "";
    try {
      if (promptEntry?.schema) {
        const parsed = JSON.parse(promptEntry.schema);
        schemaFormatted = JSON.stringify(parsed, null, 2);
      }
    } catch {
      schemaFormatted = promptEntry?.schema || "";
    }
    return (
      <pre
        style={{
          fontFamily: "monospace",
          fontSize: 13,
          lineHeight: 1.6,
          color: "#58A6FF",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          margin: 0,
        }}
      >
        {schemaFormatted || t("project.agentNoData")}
      </pre>
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 2000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.7)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#161B22",
          border: "1px solid #30363D",
          borderRadius: 12,
          maxWidth: 800,
          width: "90%",
          maxHeight: "85vh",
          overflow: "auto",
          padding: 24,
          color: "#E6EDF3",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title row */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 12,
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: 16,
              fontWeight: 600,
              color: "#E6EDF3",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "80%",
            }}
          >
            🧠 {agentLabel}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "#8B949E",
              fontSize: 20,
              cursor: "pointer",
              padding: "0 4px",
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div style={tabBarStyle}>
          {tabDefs.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              style={tabBtnStyle(tab === key)}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div
          style={{
            flex: 1,
            overflow: "auto",
            maxHeight: "60vh",
          }}
        >
          {renderContent()}
        </div>
      </div>
    </div>
  );
}
