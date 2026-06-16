import { useState } from "react";
import { decideHitl } from "../api/client";

// ── Types ─────────────────────────────────────────────────────────

interface HITLModalProps {
  open: boolean;
  projectId: string;
  gateName: string;
  proposal: Record<string, unknown>;
  criticVerdict: {
    verdict: string;
    rationale?: string;
    suggestions?: string[];
    grounding_score?: number;
    coverage_score?: number;
    abstraction_score?: number;
    agreement_percentage?: number;
  };
  onClose: () => void;
  onDecided?: (decision: "accept" | "modify" | "reject") => void;
}

const GATE_LABELS: Record<string, string> = {
  main_concern: "Main Concern Detection",
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

// ── Component ─────────────────────────────────────────────────────

export default function HITLModal({
  open,
  projectId,
  gateName,
  proposal,
  criticVerdict,
  onClose,
  onDecided,
}: HITLModalProps) {
  const [decision, setDecision] = useState<
    "accept" | "modify" | "reject" | null
  >(null);
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

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

  const gateLabel = GATE_LABELS[gateName] || gateName;
  const verdictColor =
    VERDICT_COLORS[criticVerdict.verdict] || "#30363D";

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
        {/* Header */}
        <h2 style={{ margin: "0 0 4px 0", fontSize: 18 }}>
          🛑 HITL Decision Required
        </h2>
        <p
          style={{
            margin: "0 0 16px 0",
            color: "#8B949E",
            fontSize: 13,
          }}
        >
          Gate: <strong>{gateLabel}</strong>
        </p>

        {/* Critic Verdict Banner */}
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
            style={{
              fontWeight: 700,
              fontSize: 14,
              color: verdictColor,
            }}
          >
            Critic Verdict: {criticVerdict.verdict}
          </span>
          {criticVerdict.rationale && (
            <p
              style={{
                margin: "8px 0 0 0",
                fontSize: 13,
                color: "#8B949E",
                lineHeight: 1.5,
              }}
            >
              {criticVerdict.rationale}
            </p>
          )}
          {criticVerdict.suggestions &&
            criticVerdict.suggestions.length > 0 && (
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
                  {criticVerdict.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          {/* Scores for main_concern gate */}
          {criticVerdict.grounding_score !== undefined && (
            <div
              style={{
                marginTop: 8,
                display: "flex",
                gap: 16,
                fontSize: 12,
              }}
            >
              <span style={{ color: "#8B949E" }}>
                Grounding:{" "}
                {(criticVerdict.grounding_score * 100).toFixed(0)}%
              </span>
              <span style={{ color: "#8B949E" }}>
                Coverage:{" "}
                {(criticVerdict.coverage_score! * 100).toFixed(0)}%
              </span>
              <span style={{ color: "#8B949E" }}>
                Abstraction:{" "}
                {(criticVerdict.abstraction_score! * 100).toFixed(0)}%
              </span>
            </div>
          )}
          {criticVerdict.agreement_percentage !== undefined && (
            <div style={{ marginTop: 4, fontSize: 12, color: "#8B949E" }}>
              Agreement: {criticVerdict.agreement_percentage.toFixed(0)}%
            </div>
          )}
        </div>

        {/* Proposal Summary */}
        <div
          style={{
            padding: "12px 16px",
            borderRadius: 8,
            marginBottom: 16,
            background: "#0D1117",
            border: "1px solid #21262D",
            maxHeight: 200,
            overflow: "auto",
          }}
        >
          <strong style={{ fontSize: 12, color: "#58A6FF" }}>
            Proposer Output:
          </strong>
          <pre
            style={{
              margin: "8px 0 0 0",
              fontSize: 12,
              color: "#C9D1D9",
              whiteSpace: "pre-wrap",
              fontFamily: "monospace",
            }}
          >
            {JSON.stringify(proposal, null, 2)}
          </pre>
        </div>

        {/* Decision Buttons */}
        <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
          {(["accept", "modify", "reject"] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDecision(d)}
              style={{
                flex: 1,
                padding: "10px 0",
                borderRadius: 8,
                border: "none",
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
                border:
                  decision === d ? "none" : "1px solid #30363D",
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

        {/* Feedback (only for MODIFY) */}
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
              Feedback for re-execution (what should the proposer
              do differently?):
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
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
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
              cursor:
                !decision || submitting
                  ? "not-allowed"
                  : "pointer",
            }}
          >
            {submitting ? "Submitting..." : "Submit Decision"}
          </button>
        </div>
      </div>
    </div>
  );
}
