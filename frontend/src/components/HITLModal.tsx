import { useEffect, useState } from "react";
import { decideHitl, getHitlDetail } from "../api/client";

interface HITLModalProps {
  open: boolean;
  projectId: string;
  gateName: string;
  onClose: () => void;
  onDecided?: (decision: "accept" | "modify" | "reject") => void;
}

const GATE_LABELS: Record<string, string> = {
  main_concern: "🎯 Patrón de Interés",
  core_emergence: "Core Category Emergence",
  selective_reduction: "Selective Reduction",
  core_saturation: "Core Saturation",
  database_a: "Database A — Nodes",
  database_b: "Database B — Edges",
  global_saturation: "Global Saturation Check",
};

const VERDICT_COLORS: Record<string, string> = {
  SAT: "#2EA043",
  MOD: "#D29922",
  FORCED: "#F85149",
  AGREE: "#2EA043",
  DISAGREE: "#F85149",
};

function renderProposal(gate: string, p: Record<string, unknown>) {
  const s: React.CSSProperties = {
    margin: "8px 0 0 0",
    fontSize: 12,
    color: "#C9D1D9",
    lineHeight: 1.6,
  };
  const labelStyle: React.CSSProperties = {
    color: "#8B949E",
    fontSize: 11,
    fontWeight: 600,
  };
  const valStyle: React.CSSProperties = { color: "#E6EDF3" };

  if (gate === "main_concern") {
    return (
      <div style={s}>
        <div>
          <span style={labelStyle}>Patron de Interes: </span>
          <span style={{ ...valStyle, fontSize: 14, fontWeight: 600 }}>
            {(p.main_concern as string) || "?"}
          </span>
        </div>
        <div style={{ marginTop: 4 }}>
          <span style={labelStyle}>Confianza: </span>
          <span style={valStyle}>{p.confidence as string}</span>
        </div>
        {(p.recurring_problems as string[])?.length > 0 && (
          <div style={{ marginTop: 4 }}>
            <span style={labelStyle}>Problemas recurrentes:</span>
            <ul style={{ margin: "2px 0 0 16px", padding: 0 }}>
              {(p.recurring_problems as string[]).map((rp, i) => (
                <li key={i} style={{ color: "#C9D1D9" }}>
                  {rp}
                </li>
              ))}
            </ul>
          </div>
        )}
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
          {(p.rationale as string) || ""}
        </div>
      </div>
    );
  }

  if (gate === "core_emergence") {
    const candidates =
      (p.core_category_candidates as Array<Record<string, unknown>>) || [];
    return (
      <div style={s}>
        {candidates.map((c, i) => (
          <div
            key={i}
            style={{
              marginBottom: 6,
              padding: "6px 8px",
              background: "#1C2333",
              borderRadius: 4,
            }}
          >
            <div>
              <span style={labelStyle}>Candidate {i + 1}: </span>
              <span style={{ ...valStyle, fontWeight: 600 }}>
                {c.code_name as string}
              </span>
            </div>
            <div style={{ marginTop: 2, fontSize: 11 }}>
              <span style={{ color: "#8B949E" }}>
                Centrality: {((c.centrality_score as number) || 0).toFixed(1)} ·
                Explanatory: {((c.explanatory_power as number) || 0).toFixed(1)}
              </span>
            </div>
            <div style={{ marginTop: 2, color: "#8B949E", fontSize: 11 }}>
              {c.theoretical_grab as string}
            </div>
          </div>
        ))}
        {p.no_core_detected && (
          <div style={{ color: "#F85149" }}>⚠️ No core category detected</div>
        )}
      </div>
    );
  }

  if (gate === "selective_reduction") {
    const kept = (p.kept_codes as string[]) || [];
    const merged = (p.merged_codes as Array<Record<string, unknown>>) || [];
    const discarded =
      (p.discarded_codes as Array<Record<string, unknown>>) || [];
    return (
      <div style={s}>
        <div style={{ display: "flex", gap: 12 }}>
          <span style={{ color: "#2EA043" }}>✓ {kept.length} kept</span>
          <span style={{ color: "#D29922" }}>↔ {merged.length} merged</span>
          <span style={{ color: "#F85149" }}>
            ✗ {discarded.length} discarded
          </span>
        </div>
        {discarded.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {discarded.slice(0, 5).map((d, i) => (
              <div
                key={i}
                style={{ fontSize: 11, color: "#F85149", padding: "2px 0" }}
              >
                ✗ {d.code_name as string}:{" "}
                {(d.discard_rationale as string)?.slice(0, 80)}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Default: compact JSON for other gates
  return (
    <pre
      style={{
        margin: "8px 0 0 0",
        fontSize: 11,
        color: "#C9D1D9",
        whiteSpace: "pre-wrap",
        fontFamily: "monospace",
        maxHeight: 120,
        overflow: "auto",
      }}
    >
      {JSON.stringify(p, null, 2)}
    </pre>
  );
}

export default function HITLModal({
  open,
  projectId,
  gateName,
  onClose,
  onDecided,
}: HITLModalProps) {
  const [decision, setDecision] = useState<
    "accept" | "modify" | "reject" | null
  >(null);
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [proposal, setProposal] = useState<Record<string, unknown>>({});
  const [criticVerdict, setCriticVerdict] = useState<Record<string, unknown>>(
    {},
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!open || !projectId || !gateName) return;
    setLoading(true);
    setDecision(null);
    setNote("");
    setFeedback("");
    getHitlDetail(projectId, gateName)
      .then((detail) => {
        setProposal(detail.proposal || {});
        setCriticVerdict(detail.critic_verdict || {});
      })
      .catch(() => {
        setProposal({ error: "Failed to load decision details" });
        setCriticVerdict({ verdict: "UNKNOWN" });
      })
      .finally(() => setLoading(false));
  }, [open, projectId, gateName]);

  if (!open) return null;

  const cv = criticVerdict as Record<string, unknown>;
  const verdict = (cv.verdict as string) || "SAT";
  const rationale = (cv.rationale as string) || "";
  const suggestions = (cv.suggestions as string[]) || [];
  const grounding = cv.grounding_score as number | undefined;
  const coverage = cv.coverage_score as number | undefined;
  const abstraction = cv.abstraction_score as number | undefined;
  const agreement = cv.agreement_percentage as number | undefined;
  const verdictColor = VERDICT_COLORS[verdict] || "#30363D";

  const handleSubmit = async () => {
    if (!decision) return;
    setSubmitting(true);
    try {
      await decideHitl(
        projectId,
        gateName,
        decision,
        note,
        decision === "modify" ? feedback : undefined,
      );
      onDecided?.(decision);
    } catch (err) {
      console.error("HITL decision failed:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.7)",
      }}
    >
      <div
        style={{
          background: "#161B22",
          borderRadius: 12,
          border: "1px solid #30363D",
          width: 640,
          maxHeight: "85vh",
          overflow: "auto",
          padding: 24,
          color: "#E6EDF3",
        }}
      >
        <h2 style={{ margin: "0 0 4px 0", fontSize: 18 }}>
          🛑 HITL Decision Required
        </h2>
        <p style={{ margin: "0 0 16px 0", color: "#8B949E", fontSize: 13 }}>
          Gate: <strong>{GATE_LABELS[gateName] || gateName}</strong>
        </p>

        {loading ? (
          <div
            style={{
              padding: 40,
              textAlign: "center",
              color: "#8B949E",
              fontSize: 14,
            }}
          >
            Loading decision details...
          </div>
        ) : (
          <>
            {/* Critic Verdict */}
            <div
              style={{
                padding: "12px 16px",
                borderRadius: 8,
                marginBottom: 16,
                background: "#1C2333",
                border: `1px solid ${verdictColor}`,
              }}
            >
              <span
                style={{ fontWeight: 700, fontSize: 14, color: verdictColor }}
              >
                Critic Verdict: {verdict}
              </span>
              {rationale && (
                <p
                  style={{
                    margin: "8px 0 0 0",
                    fontSize: 13,
                    color: "#8B949E",
                    lineHeight: 1.5,
                  }}
                >
                  {rationale}
                </p>
              )}
              {suggestions.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <strong style={{ fontSize: 12, color: "#D29922" }}>
                    Suggestions:
                  </strong>
                  <ul
                    style={{
                      margin: "4px 0 0 0",
                      paddingLeft: 20,
                      fontSize: 12,
                      color: "#8B949E",
                    }}
                  >
                    {suggestions.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
              {grounding !== undefined && (
                <div
                  style={{
                    marginTop: 8,
                    display: "flex",
                    gap: 16,
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: "#8B949E" }}>
                    Grounding: {(grounding * 100).toFixed(0)}%
                  </span>
                  <span style={{ color: "#8B949E" }}>
                    Coverage: {((coverage || 0) * 100).toFixed(0)}%
                  </span>
                  <span style={{ color: "#8B949E" }}>
                    Abstraction: {((abstraction || 0) * 100).toFixed(0)}%
                  </span>
                </div>
              )}
              {agreement !== undefined && (
                <div style={{ marginTop: 4, fontSize: 12, color: "#8B949E" }}>
                  Agreement: {agreement.toFixed(0)}%
                </div>
              )}
            </div>

            {/* Proposal */}
            <div
              style={{
                padding: "12px 16px",
                borderRadius: 8,
                marginBottom: 16,
                background: "#0D1117",
                border: "1px solid #21262D",
                maxHeight: 220,
                overflow: "auto",
              }}
            >
              <strong style={{ fontSize: 12, color: "#58A6FF" }}>
                Proposer Output:
              </strong>
              {renderProposal(gateName, proposal)}
            </div>

            {/* Decision buttons */}
            <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
              {(["accept", "modify", "reject"] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setDecision(d)}
                  style={{
                    flex: 1,
                    padding: "10px 0",
                    borderRadius: 8,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: "pointer",
                    background:
                      decision === d
                        ? d === "accept"
                          ? "#1F6FEB"
                          : d === "modify"
                            ? "#9E6A03"
                            : "#DA3633"
                        : "#21262D",
                    color: decision === d ? "#FFF" : "#8B949E",
                    border: decision === d ? "none" : "1px solid #30363D",
                  }}
                >
                  {d === "accept"
                    ? "✓ ACCEPT"
                    : d === "modify"
                      ? "✎ MODIFY"
                      : "✗ REJECT"}
                </button>
              ))}
            </div>

            {/* Note */}
            <div style={{ marginBottom: 12 }}>
              <label
                style={{
                  fontSize: 12,
                  color: "#8B949E",
                  display: "block",
                  marginBottom: 4,
                }}
              >
                Note{" "}
                {decision === "reject"
                  ? "(required — explain why)"
                  : "(optional)"}
                :
              </label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder={
                  decision === "reject"
                    ? "Why are you rejecting this proposal?"
                    : "Any observations for the methodology log..."
                }
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: 6,
                  background: "#0D1117",
                  border: "1px solid #30363D",
                  color: "#E6EDF3",
                  fontSize: 12,
                  resize: "vertical",
                  fontFamily: "inherit",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Feedback for MODIFY */}
            {decision === "modify" && (
              <div style={{ marginBottom: 12 }}>
                <label
                  style={{
                    fontSize: 12,
                    color: "#D29922",
                    display: "block",
                    marginBottom: 4,
                  }}
                >
                  Feedback for re-execution (what should the proposer do
                  differently?):
                </label>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={3}
                  placeholder="Be specific: what should change in the proposal?"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    borderRadius: 6,
                    background: "#0D1117",
                    border: "1px solid #D29922",
                    color: "#E6EDF3",
                    fontSize: 12,
                    resize: "vertical",
                    fontFamily: "inherit",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            )}

            {/* Actions */}
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              <button
                onClick={onClose}
                style={{
                  padding: "8px 16px",
                  borderRadius: 6,
                  border: "1px solid #30363D",
                  background: "#21262D",
                  color: "#E6EDF3",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={
                  !decision ||
                  (decision === "reject" && !note.trim()) ||
                  submitting
                }
                style={{
                  padding: "8px 16px",
                  borderRadius: 6,
                  border: "none",
                  background: !decision ? "#21262D" : "#1F6FEB",
                  color: !decision ? "#484F58" : "#FFF",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: !decision || submitting ? "not-allowed" : "pointer",
                }}
              >
                {submitting ? "Submitting..." : "Submit Decision"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
