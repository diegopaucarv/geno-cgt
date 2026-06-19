import { useState, useMemo, useEffect, useCallback } from "react";
import { useI18n } from "../i18n";
import type { AgentLogEntry } from "../api/client";

// ── Public interface (unchanged) ─────────────────────────────────────

interface AgentModalProps {
  open: boolean;
  agentId: string;
  agentLabel: string;
  agentLogs: AgentLogEntry[];
  onClose: () => void;
}

type TabKey = "prompt" | "response" | "schema" | "error";

// ── Internal types ───────────────────────────────────────────────────

interface Iteration {
  num: number;
  sent: AgentLogEntry;
  response: AgentLogEntry | null;
}

interface SidebarEntry {
  key: string;
  entry: AgentLogEntry;
  iteration: number;
  hasResponse: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────

function promptLineColor(line: string): string {
  if (/^[A-Z][A-Z ]+:/.test(line)) return "#E6EDF3";
  if (/^###/.test(line)) return "#E6EDF3";
  if (/^---/.test(line)) return "#E6EDF3";
  if (/^\[/.test(line)) return "#E6EDF3";
  return "#D29922";
}

function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

/** Pair sequential prompt_sent → prompt_response into iterations. */
function buildIterations(logs: AgentLogEntry[]): Iteration[] {
  const sorted = [...logs].sort((a, b) => a.ts - b.ts);
  const its: Iteration[] = [];
  let n = 1;
  for (let i = 0; i < sorted.length; i++) {
    if (sorted[i].type === "prompt_sent") {
      const sent = sorted[i];
      let resp: AgentLogEntry | null = null;
      for (let j = i + 1; j < sorted.length; j++) {
        if (sorted[j].type === "prompt_response") {
          resp = sorted[j];
          i = j; // consume the response in the outer loop
          break;
        } else if (sorted[j].type === "prompt_sent") {
          break; // no response before the next prompt
        }
      }
      its.push({ num: n++, sent, response: resp });
    }
  }
  return its;
}

// ── Tokens badge ─────────────────────────────────────────────────────

function TokensBadge({ tokens, label }: { tokens?: number; label: string }) {
  if (tokens == null) return null;
  return (
    <span
      style={{
        fontSize: 10,
        color: "#8B949E",
        background: "#21262D",
        borderRadius: 4,
        padding: "1px 6px",
        marginLeft: 6,
        fontWeight: 500,
      }}
    >
      🧮 {tokens.toLocaleString()} {label}
    </span>
  );
}

// ── Component ────────────────────────────────────────────────────────

export default function AgentModal({
  open,
  agentId,
  agentLabel,
  agentLogs,
  onClose,
}: AgentModalProps) {
  const { t } = useI18n();
  const [rawTab, setTab] = useState<TabKey>("prompt");
  const [selectedKey, setSelectedKey] = useState("");

  // ── Build iterations (newest first) ──────────────────────────────
  const iterations = useMemo(() => {
    const mine = agentLogs.filter((e) => e.agent_id === agentId);
    return buildIterations(mine).reverse();
  }, [agentLogs, agentId]);

  // ── Flatten for sidebar ──────────────────────────────────────────
  const sidebarEntries = useMemo<SidebarEntry[]>(() => {
    const entries: SidebarEntry[] = [];
    for (const iter of iterations) {
      entries.push({
        key: `s-${iter.sent.ts}`,
        entry: iter.sent,
        iteration: iter.num,
        hasResponse: !!iter.response,
      });
      if (iter.response) {
        entries.push({
          key: `r-${iter.response.ts}`,
          entry: iter.response,
          iteration: iter.num,
          hasResponse: true,
        });
      }
    }
    return entries;
  }, [iterations]);

  // ── Reset selection when entries change ──────────────────────────
  useEffect(() => {
    if (sidebarEntries.length > 0) {
      // Keep the current key if it still exists
      if (!sidebarEntries.some((e) => e.key === selectedKey)) {
        const firstKey = sidebarEntries[0].key;
        setSelectedKey(firstKey);
        // Auto-pick best tab for the first entry
        const first = sidebarEntries[0];
        if (first.entry.type === "prompt_sent" && !first.hasResponse) {
          setTab("error");
        } else if (first.entry.type === "prompt_response") {
          setTab("response");
        } else {
          setTab("prompt");
        }
      }
    } else {
      setSelectedKey("");
      setTab("prompt");
    }
    // Only run when entries identity changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sidebarEntries]);

  // ── Selected entry & iteration ───────────────────────────────────
  const selected =
    sidebarEntries.find((e) => e.key === selectedKey) ?? sidebarEntries[0];
  const selectedIter = iterations.find(
    (iter) => iter.num === selected?.iteration,
  );

  const showErrorTab =
    selected?.entry.type === "prompt_sent" && !selected?.hasResponse;

  // ── Tab definitions ──────────────────────────────────────────────
  const tabDefs = useMemo<Array<{ key: TabKey; label: string }>>(() => {
    const defs: Array<{ key: TabKey; label: string }> = [
      { key: "prompt", label: "🤖 " + t("project.agentPromptTab") },
      { key: "response", label: "📤 " + t("project.agentResponseTab") },
      { key: "schema", label: "📋 " + t("project.agentSchemaTab") },
    ];
    if (showErrorTab) {
      defs.push({ key: "error", label: "⚠️ Error" });
    }
    return defs;
  }, [t, showErrorTab]);

  // Ensure current tab is valid; fall back to "prompt"
  const tab: TabKey = tabDefs.some((d) => d.key === rawTab) ? rawTab : "prompt";

  // If rawTab became invalid, sync it (avoids stale state)
  useEffect(() => {
    if (!tabDefs.some((d) => d.key === rawTab)) {
      setTab("prompt");
    }
  }, [tabDefs, rawTab]);

  // ── Handlers ─────────────────────────────────────────────────────
  const handleSidebarClick = useCallback((entry: SidebarEntry) => {
    setSelectedKey(entry.key);
    if (entry.entry.type === "prompt_sent" && !entry.hasResponse) {
      setTab("error");
    } else if (entry.entry.type === "prompt_response") {
      setTab("response");
    } else {
      setTab("prompt");
    }
  }, []);

  // ── Status helper ────────────────────────────────────────────────
  function getStatus(entryType: string, hasResp: boolean) {
    if (entryType === "prompt_response") {
      return { icon: "✓", color: "#3FB950" };
    }
    if (hasResp) {
      return { icon: "✓", color: "#3FB950" };
    }
    return { icon: "⏳", color: "#D29922" };
  }

  // ── Early return (after all hooks) ───────────────────────────────
  if (!open) return null;

  const isEmpty = sidebarEntries.length === 0;

  // ── Shared tab button style ──────────────────────────────────────
  const tabBtnStyle = (isActive: boolean): React.CSSProperties => ({
    padding: "6px 14px",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    background: isActive ? "#A371F722" : "transparent",
    color: isActive ? "#A371F7" : "#8B949E",
    whiteSpace: "nowrap",
  });

  // ── Content renderers ────────────────────────────────────────────

  function renderPrompt() {
    const text = selected?.entry.prompt || "";
    if (!text) {
      return <div style={emptyContentStyle}>No prompt data for this call.</div>;
    }
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

  function renderResponse() {
    const raw = selectedIter?.response?.response;
    if (!raw) {
      return (
        <div style={emptyContentStyle}>
          No response available for this call.
        </div>
      );
    }
    let formatted = "";
    try {
      const parsed = JSON.parse(raw);
      formatted = JSON.stringify(parsed, null, 2);
    } catch {
      formatted = raw;
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
        {formatted}
      </pre>
    );
  }

  function renderSchema() {
    const schemaText = selected?.entry.schema;
    if (!schemaText) {
      return <div style={emptyContentStyle}>No schema data for this call.</div>;
    }
    let formatted = "";
    try {
      const parsed = JSON.parse(schemaText);
      formatted = JSON.stringify(parsed, null, 2);
    } catch {
      formatted = schemaText;
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
        {formatted}
      </pre>
    );
  }

  function renderError() {
    return (
      <div style={{ padding: "24px 0", textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
        <div
          style={{
            color: "#F85149",
            fontSize: 14,
            fontWeight: 600,
            marginBottom: 8,
          }}
        >
          No response received
        </div>
        <div style={{ color: "#8B949E", fontSize: 13, lineHeight: 1.7 }}>
          The agent may have failed, timed out, or is still processing.
          <br />
          Check the pipeline logs for more details.
        </div>
      </div>
    );
  }

  function renderContent() {
    if (isEmpty) {
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
    if (!selected) return null;

    switch (tab) {
      case "prompt":
        return renderPrompt();
      case "response":
        return renderResponse();
      case "schema":
        return renderSchema();
      case "error":
        return renderError();
    }
  }

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 2000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(1,4,9,0.85)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#161B22",
          border: "1px solid #30363D",
          borderRadius: 12,
          width: "92%",
          maxWidth: 1100,
          maxHeight: "85vh",
          display: "flex",
          flexDirection: "column",
          color: "#E6EDF3",
          boxShadow: "0 0 40px rgba(163,113,247,0.15)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Title bar ──────────────────────────────────────────── */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "16px 24px 12px",
            flexShrink: 0,
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

        {/* ── Network-error / empty-data banner ──────────────────── */}
        {isEmpty && (
          <div
            style={{
              margin: "0 24px 12px",
              padding: "10px 14px",
              borderRadius: 6,
              background: "#F8514922",
              border: "1px solid #F8514944",
              color: "#F85149",
              fontSize: 12,
              lineHeight: 1.5,
              display: "flex",
              alignItems: "flex-start",
              gap: 8,
            }}
          >
            <span style={{ flexShrink: 0, marginTop: 1 }}>⚠️</span>
            <span>
              No agent execution data available. The agent logs may be empty due
              to a network error or no data has been recorded yet.
            </span>
          </div>
        )}

        {/* ── Body (sidebar + content) ───────────────────────────── */}
        <div
          style={{
            display: "flex",
            flex: 1,
            overflow: "hidden",
            minHeight: 0,
          }}
        >
          {/* ── Left Sidebar (30 %) ─────────────────────────────── */}
          <div
            style={{
              width: "30%",
              minWidth: 220,
              maxWidth: 320,
              borderRight: "1px solid #30363D",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              background: "#0D1117",
            }}
          >
            <div
              style={{
                padding: "10px 14px",
                fontSize: 11,
                fontWeight: 600,
                color: "#8B949E",
                textTransform: "uppercase",
                letterSpacing: "0.6px",
                borderBottom: "1px solid #30363D",
                flexShrink: 0,
              }}
            >
              Call History
            </div>
            <div
              style={{
                flex: 1,
                overflow: "auto",
                padding: "4px 0",
              }}
            >
              {isEmpty ? (
                <div
                  style={{
                    padding: "24px 14px",
                    color: "#484F58",
                    fontSize: 12,
                    textAlign: "center",
                  }}
                >
                  No calls recorded
                </div>
              ) : (
                /* Group by iteration */
                (() => {
                  const seenIters = new Set<number>();
                  const rows: React.ReactNode[] = [];
                  sidebarEntries.forEach((item) => {
                    const isFirstInIter = !seenIters.has(item.iteration);
                    if (isFirstInIter) {
                      seenIters.add(item.iteration);
                      rows.push(
                        <div
                          key={`iter-hdr-${item.iteration}`}
                          style={{
                            padding: "6px 14px 2px",
                            fontSize: 10,
                            fontWeight: 700,
                            color: "#A371F7",
                            textTransform: "uppercase",
                            letterSpacing: "0.5px",
                          }}
                        >
                          Iteration {item.iteration}
                        </div>,
                      );
                    }

                    const isSelected = item.key === selectedKey;
                    const { icon, color } = getStatus(
                      item.entry.type,
                      item.hasResponse,
                    );

                    rows.push(
                      <div
                        key={item.key}
                        onClick={() => handleSidebarClick(item)}
                        style={{
                          padding: "7px 14px 8px",
                          cursor: "pointer",
                          background: isSelected ? "#A371F71A" : "transparent",
                          borderLeft: isSelected
                            ? "3px solid #A371F7"
                            : "3px solid transparent",
                          transition: "background 0.12s, border-color 0.12s",
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected)
                            (e.currentTarget as HTMLElement).style.background =
                              "#1C2128";
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected)
                            (e.currentTarget as HTMLElement).style.background =
                              "transparent";
                        }}
                      >
                        {/* Row 1: icon + type badge + status */}
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                          }}
                        >
                          <span style={{ fontSize: 12 }}>
                            {item.entry.type === "prompt_sent" ? "📤" : "📥"}
                          </span>
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: 600,
                              color: "#E6EDF3",
                            }}
                          >
                            {item.entry.type === "prompt_sent"
                              ? "Sent"
                              : "Response"}
                          </span>
                          <span
                            style={{
                              marginLeft: "auto",
                              fontSize: 11,
                              color,
                              fontWeight: 700,
                            }}
                          >
                            {icon}
                          </span>
                        </div>

                        {/* Row 2: timestamp */}
                        <div
                          style={{
                            fontSize: 10,
                            color: "#484F58",
                            marginTop: 3,
                          }}
                        >
                          {formatTs(item.entry.ts)}
                        </div>

                        {/* Row 3: token count */}
                        {item.entry.tokens != null && (
                          <div style={{ marginTop: 2 }}>
                            <TokensBadge
                              tokens={item.entry.tokens}
                              label={
                                item.entry.type === "prompt_sent"
                                  ? "tokens"
                                  : "tokens"
                              }
                            />
                          </div>
                        )}
                      </div>,
                    );
                  });
                  return rows;
                })()
              )}
            </div>
          </div>

          {/* ── Right Content Area (70 %) ────────────────────────── */}
          <div
            style={{
              width: "70%",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              padding: "0 20px 16px",
            }}
          >
            {/* Tab bar */}
            <div
              style={{
                display: "flex",
                borderBottom: "1px solid #30363D",
                padding: "8px 0",
                marginBottom: 16,
                gap: 4,
                flexShrink: 0,
              }}
            >
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

            {/* Tab content */}
            <div
              style={{
                flex: 1,
                overflow: "auto",
                minHeight: 0,
              }}
            >
              {renderContent()}
            </div>

            {/* ── Tokens footer ──────────────────────────────────── */}
            {selected && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 20,
                  padding: "10px 0 0",
                  borderTop: "1px solid #30363D",
                  marginTop: 12,
                  flexShrink: 0,
                  flexWrap: "wrap",
                }}
              >
                {/* Current entry's tokens */}
                <div
                  style={{
                    fontSize: 11,
                    color: "#8B949E",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <span>
                    {selected.entry.type === "prompt_sent"
                      ? "📤 Prompt"
                      : "📥 Response"}
                    :
                  </span>
                  <span style={{ color: "#E6EDF3", fontWeight: 600 }}>
                    {selected.entry.tokens != null
                      ? selected.entry.tokens.toLocaleString()
                      : "—"}
                  </span>
                  <span>tokens</span>
                </div>

                {/* Paired entry's tokens (show the other side) */}
                {selected.entry.type === "prompt_sent" &&
                  selectedIter?.response?.tokens != null && (
                    <div
                      style={{
                        fontSize: 11,
                        color: "#8B949E",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                    >
                      <span>📥 Response:</span>
                      <span style={{ color: "#E6EDF3", fontWeight: 600 }}>
                        {selectedIter.response.tokens.toLocaleString()}
                      </span>
                      <span>tokens</span>
                    </div>
                  )}

                {selected.entry.type === "prompt_response" &&
                  selectedIter?.sent?.tokens != null && (
                    <div
                      style={{
                        fontSize: 11,
                        color: "#8B949E",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                    >
                      <span>📤 Prompt:</span>
                      <span style={{ color: "#E6EDF3", fontWeight: 600 }}>
                        {selectedIter.sent.tokens.toLocaleString()}
                      </span>
                      <span>tokens</span>
                    </div>
                  )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Shared inline style ──────────────────────────────────────────────

const emptyContentStyle: React.CSSProperties = {
  padding: "40px 0",
  textAlign: "center",
  color: "#8B949E",
  fontSize: 14,
};
