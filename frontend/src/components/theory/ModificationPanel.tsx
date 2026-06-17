import { useState, useRef, useEffect, useCallback } from "react";
import { useI18n } from "../../i18n";

// ── Types ─────────────────────────────────────────────────────────

interface ModificationResult {
  valid_request: boolean;
  filter_reason: string;
  suggested_questions: string[];
  recommended: boolean | null;
  recommendation_reason: string;
  modified_memo: any;
  impact_summary: string;
  evidence_sufficient: boolean;
  wiped_tables: string[];
  pipeline_restarted_from: string;
}

interface Props {
  projectId: string;
  agentId: string;
  currentMemo: any;
  memoId: string;
  originalPrompt?: string;
  agentFamily?: string;
  onClose?: () => void;
  onApplied?: () => void;
}

// ── API ──────────────────────────────────────────────────────────

async function requestMod(
  projectId: string,
  body: any,
): Promise<ModificationResult> {
  const token = localStorage.getItem("access_token");
  const res = await fetch(
    `/api/v1/projects/${projectId}/modification/request`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function applyMod(projectId: string, body: any) {
  const token = localStorage.getItem("access_token");
  const res = await fetch(`/api/v1/projects/${projectId}/modification/apply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── @-search ──────────────────────────────────────────────────────

interface RefItem {
  id: string;
  type: "segment" | "document" | "memo";
  label: string;
}

async function searchRefs(
  projectId: string,
  query: string,
): Promise<RefItem[]> {
  const token = localStorage.getItem("access_token");
  const res = await fetch(
    `/api/v1/rag/search?q=${encodeURIComponent(query)}&proyecto_id=${projectId}&top_k=5&fusion=rrf`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!res.ok) return [];
  const data = await res.json();
  return (data || []).map((r: any) => ({
    id: r.segmento_id || r.documento_id || "",
    type: "segment",
    label: (r.texto || "").slice(0, 60),
  }));
}

// ── Placeholders ──────────────────────────────────────────────────

const PLACEHOLDERS: Record<string, string> = {
  inductive_data: "theory.placeholderInductiveData",
  inductive_concepts: "theory.placeholderInductiveConcepts",
  descriptive_data: "theory.placeholderDescriptiveData",
  evaluative: "theory.placeholderEvaluative",
  structural: "theory.placeholderStructural",
  elaborative: "theory.placeholderElaborative",
};

// ── Component ─────────────────────────────────────────────────────

export default function ModificationPanel({
  projectId,
  agentId,
  currentMemo,
  memoId,
  originalPrompt,
  agentFamily = "inductive_data",
  onClose,
  onApplied,
}: Props) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<"idle" | "loading" | "done" | "error">(
    "idle",
  );
  const [result, setResult] = useState<ModificationResult | null>(null);
  const [error, setError] = useState("");
  const [pipelineRunning, setPipelineRunning] = useState(false);

  // @-search state
  const [atOpen, setAtOpen] = useState(false);
  const [atQuery, setAtQuery] = useState("");
  const [atItems, setAtItems] = useState<RefItem[]>([]);
  const [atIdx, setAtIdx] = useState(0);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Detect @ in text
  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const val = e.target.value;
      setText(val);
      const cursor = e.target.selectionStart || 0;
      const before = val.slice(0, cursor);
      const atPos = before.lastIndexOf("@");
      if (atPos >= 0 && (atPos === 0 || before[atPos - 1] === " ")) {
        const q = before.slice(atPos + 1);
        setAtQuery(q);
        setAtOpen(true);
        setAtIdx(0);
        if (q.length >= 1) {
          searchRefs(projectId, q).then(setAtItems);
        } else {
          setAtItems([]);
        }
      } else {
        setAtOpen(false);
      }
    },
    [projectId],
  );

  const insertRef = (item: RefItem) => {
    const cursor = taRef.current?.selectionStart || text.length;
    const before = text.slice(0, cursor);
    const atPos = before.lastIndexOf("@");
    const after = text.slice(cursor);
    const ref = `@${item.type}:${item.id.slice(0, 8)}`;
    const newText = text.slice(0, atPos) + ref + " " + after;
    setText(newText);
    setAtOpen(false);
    taRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!atOpen || atItems.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAtIdx((i) => Math.min(i + 1, atItems.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setAtIdx((i) => Math.max(i - 1, 0));
    }
    if (e.key === "Enter") {
      e.preventDefault();
      insertRef(atItems[atIdx]);
    }
    if (e.key === "Escape") {
      setAtOpen(false);
    }
  };

  // ── Actions ──────────────────────────────────────────────────

  const handleVerify = async () => {
    if (!text.trim()) return;
    setPhase("loading");
    setError("");
    try {
      const r = await requestMod(projectId, {
        agent_id: agentId,
        user_request: text,
        current_memo: currentMemo,
        memo_id: memoId,
        original_prompt: originalPrompt || "",
      });
      setResult(r);
      setPhase("done");
    } catch (e: any) {
      setError(e.message);
      setPhase("error");
    }
  };

  const handleApply = async () => {
    if (!result?.evidence_sufficient) return;
    setPipelineRunning(true);
    try {
      await applyMod(projectId, {
        agent_id: agentId,
        memo_id: memoId,
        new_content: result.modified_memo || currentMemo,
        user_request: text,
        recommended: result.recommended,
        current_memo: currentMemo,
        evidence_collected: [],
        verification_plan: null,
      });
      setResult(null);
      setPhase("idle");
      setPipelineRunning(false);
      onApplied?.();
    } catch (e: any) {
      setError(e.message);
      setPipelineRunning(false);
    }
  };

  const handleReset = () => {
    setResult(null);
    setPhase("idle");
    setError("");
  };

  const tint =
    result?.recommended === true
      ? greenTint
      : result?.recommended === false
        ? redTint
        : {};

  return (
    <div style={panel}>
      {/* ── Input permanente ────────────────────────────────── */}
      <div style={inputRow}>
        {onClose && (
          <button
            onClick={onClose}
            title={t("theory.closePanel")}
            style={{
              background: "transparent",
              border: "1px solid #30363D",
              borderRadius: 4,
              color: "#8B949E",
              fontSize: 12,
              padding: "4px 8px",
              cursor: "pointer",
              flexShrink: 0,
            }}
          >
            {t("theory.closeIcon")}
          </button>
        )}
        <textarea
          ref={taRef}
          style={inlineInput}
          placeholder={
            t(PLACEHOLDERS[agentFamily]) || t("theory.placeholderFallback")
          }
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          rows={1}
        />
        <button
          style={{ ...btn, flexShrink: 0, opacity: text.trim() ? 1 : 0.4 }}
          disabled={!text.trim() || phase === "loading"}
          onClick={handleVerify}
        >
          {phase === "loading" ? t("theory.loading") : t("theory.submitArrow")}
        </button>

        {/* @-search popup */}
        {atOpen && atItems.length > 0 && (
          <div style={atPopup}>
            {atItems.map((item, i) => (
              <div
                key={item.id}
                style={{
                  ...atRow,
                  background: i === atIdx ? "#1C2333" : "transparent",
                }}
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertRef(item);
                }}
              >
                <span
                  style={{ color: "#484F58", fontSize: 10, marginRight: 6 }}
                >
                  {item.type === "segment"
                    ? t("theory.segmentIcon")
                    : t("theory.folderIcon")}
                </span>
                <span style={{ color: "#E6EDF3", fontSize: 11 }}>
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div style={{ padding: "8px 16px", background: "#F8514911" }}>
          <span style={{ color: "#F85149", fontSize: 11 }}>{error}</span>
        </div>
      )}

      {/* ── Resultado ───────────────────────────────────────── */}
      {phase === "done" && result && (
        <div style={{ ...resultPanel, ...tint }}>
          {/* Pedido original (scrollable, 1 linea) */}
          <div style={userReqLine}>{text}</div>

          {!result.valid_request ? (
            /* Invalid */
            <>
              <div style={resultSection}>
                <div
                  style={{ color: "#D29922", fontSize: 12, lineHeight: 1.5 }}
                >
                  {result.filter_reason}
                </div>
              </div>
              {result.suggested_questions.length > 0 && (
                <div style={resultSection}>
                  <div style={label}>{t("theory.acceptedQuestions")}</div>
                  <ul style={qList}>
                    {result.suggested_questions.map((q, i) => (
                      <li key={i} style={qItem}>
                        {q}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div style={resultActions}>
                <button style={btnSecondary} onClick={handleReset}>
                  {t("theory.closeButton")}
                </button>
              </div>
            </>
          ) : (
            /* Valid */
            <>
              {/* Preview */}
              <div style={resultSection}>
                <div style={memoPreview}>
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 600,
                      color: "#E6EDF3",
                      marginBottom: 4,
                    }}
                  >
                    {result.modified_memo?.code_name ||
                      result.modified_memo?.nombre ||
                      currentMemo?.code_name ||
                      currentMemo?.nombre ||
                      t("theory.emptyName")}
                  </div>
                  <div
                    style={{ fontSize: 12, color: "#8B949E", lineHeight: 1.5 }}
                  >
                    {result.modified_memo?.definition ||
                      result.modified_memo?.text ||
                      currentMemo?.definition ||
                      currentMemo?.text ||
                      t("theory.emptyDefinition")}
                  </div>
                </div>
              </div>

              {/* Razon */}
              {result.recommendation_reason && (
                <div style={resultSection}>
                  <div
                    style={{
                      fontSize: 12,
                      color: "#8B949E",
                      lineHeight: 1.5,
                      fontStyle: "italic",
                    }}
                  >
                    {result.recommendation_reason}
                  </div>
                </div>
              )}

              {/* Impacto */}
              {result.impact_summary && (
                <div style={{ ...resultSection, background: "#D2992211" }}>
                  <div
                    style={{ fontSize: 11, color: "#D29922", marginBottom: 4 }}
                  >
                    ⚠ {t("theory.impactHeading")}
                  </div>
                  <div
                    style={{ fontSize: 11, color: "#8B949E", lineHeight: 1.4 }}
                  >
                    {result.impact_summary}
                  </div>
                </div>
              )}

              {/* Acciones */}
              <div
                style={{ ...resultActions, justifyContent: "space-between" }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    color: result.recommended ? "#3FB950" : "#F85149",
                  }}
                >
                  {result.recommended
                    ? t("theory.recommended")
                    : t("theory.notRecommended")}
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <button style={btnSecondary} onClick={handleReset}>
                    {t("theory.closeButton")}
                  </button>
                  {result.evidence_sufficient && (
                    <button
                      style={{
                        ...btn,
                        background: result.recommended ? "#238636" : "#21262D",
                        border: result.recommended
                          ? "1px solid #238636"
                          : "1px solid #30363D",
                        opacity: pipelineRunning ? 0.6 : 1,
                      }}
                      onClick={handleApply}
                      disabled={pipelineRunning}
                    >
                      {pipelineRunning
                        ? t("theory.loading")
                        : t("theory.applyButton")}
                    </button>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────

const panel: React.CSSProperties = {
  background: "#161B22",
  borderRadius: 8,
  border: "1px solid #21262D",
  overflow: "hidden",
};

// Input row
const inputRow: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: 8,
  padding: "8px 12px",
  position: "relative",
};
const inlineInput: React.CSSProperties = {
  flex: 1,
  background: "#0D1117",
  border: "1px solid #21262D",
  borderRadius: 6,
  color: "#E6EDF3",
  fontSize: 13,
  padding: "7px 10px",
  resize: "none",
  fontFamily: "inherit",
  outline: "none",
  lineHeight: 1.5,
  minHeight: 34,
  overflow: "hidden",
};

// @-search popup
const atPopup: React.CSSProperties = {
  position: "absolute",
  bottom: "100%",
  left: 12,
  right: 54,
  marginBottom: 4,
  background: "#161B22",
  border: "1px solid #21262D",
  borderRadius: 6,
  maxHeight: 160,
  overflow: "auto",
  zIndex: 10,
  boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
};
const atRow: React.CSSProperties = {
  padding: "6px 10px",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  borderBottom: "1px solid #21262D",
};

// Result panel
const resultPanel: React.CSSProperties = { transition: "background 0.3s" };
const greenTint: React.CSSProperties = { background: "#16281D" };
const redTint: React.CSSProperties = { background: "#281616" };
const userReqLine: React.CSSProperties = {
  padding: "6px 16px",
  fontSize: 11,
  color: "#484F58",
  borderBottom: "1px solid #21262D",
  whiteSpace: "nowrap",
  overflow: "auto",
  fontStyle: "italic",
};
const resultSection: React.CSSProperties = {
  padding: "10px 16px",
  borderBottom: "1px solid #21262D",
};
const resultActions: React.CSSProperties = {
  padding: "10px 16px",
  display: "flex",
  gap: 8,
  justifyContent: "flex-end",
};

// Shared
const label: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  color: "#8B949E",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  marginBottom: 4,
};
const memoPreview: React.CSSProperties = {
  background: "#0D1117",
  border: "1px solid #21262D",
  borderRadius: 6,
  padding: "10px 12px",
};
const btn: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid #21262D",
  background: "#1C2333",
  color: "#E6EDF3",
  fontSize: 12,
  cursor: "pointer",
};
const btnSecondary: React.CSSProperties = { ...btn, background: "#21262D" };
const qList: React.CSSProperties = {
  margin: "4px 0 0",
  paddingLeft: 16,
  listStyle: "none",
};
const qItem: React.CSSProperties = {
  fontSize: 12,
  color: "#58A6FF",
  lineHeight: 1.6,
  cursor: "pointer",
  padding: "2px 0",
};
