import type { ChainRunItem, AgentRunItem } from "../api/client";

// ── Props ────────────────────────────────────────────────────────────

interface ChainTimelineProps {
  chainRuns: ChainRunItem[];
  /** Optional: filter to a specific chain_id */
  chainFilter?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────

function statusIcon(status: ChainRunItem["status"]): string {
  switch (status) {
    case "running":
      return "↻";
    case "completed":
      return "✓";
    case "aborted":
      return "✗";
    case "paused_hitl":
      return "🛑";
  }
}

function agentActionLabel(action: AgentRunItem["orchestrator_action"]): string {
  switch (action) {
    case "proceed":
      return "✓";
    case "force_proceed":
      return "⚡";
    case "skip":
      return "⏭";
  }
}

// ── Component ────────────────────────────────────────────────────────

export default function ChainTimeline({
  chainRuns,
  chainFilter,
}: ChainTimelineProps) {
  const filtered = chainFilter
    ? chainRuns.filter((cr) => cr.chain_id === chainFilter)
    : chainRuns;

  if (filtered.length === 0) {
    return (
      <div style={{ padding: 16, color: "#8B949E", fontSize: 13 }}>
        No chain runs recorded yet.
      </div>
    );
  }

  return (
    <div style={{ padding: 12 }}>
      {/* ── Placeholder: Chain History — Coming Soon ── */}
      <div
        style={{
          padding: "16px 20px",
          borderRadius: 8,
          border: "1px dashed #30363D",
          background: "#161B22",
          color: "#E6EDF3",
          fontSize: 14,
        }}
      >
        <strong style={{ fontSize: 16 }}>
          🔗 Chain History — Coming Soon
        </strong>
        <div
          style={{ marginTop: 8, color: "#8B949E", fontFamily: "monospace", fontSize: 12 }}
        >
          Data loaded: {filtered.length} chain run(s)
        </div>
        <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.6 }}>
          {filtered.map((cr) => (
            <div
              key={cr.id}
              style={{
                marginBottom: 10,
                padding: "8px 12px",
                borderRadius: 6,
                background: "#0D1117",
                border: "1px solid #21262D",
              }}
            >
              <div style={{ fontWeight: 600 }}>
                {statusIcon(cr.status)} Chain: {cr.chain_id}{" "}
                <span
                  style={{
                    fontSize: 11,
                    color: "#8B949E",
                    fontWeight: 400,
                  }}
                >
                  (status: {cr.status})
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#6E7681", marginTop: 2 }}>
                Tokens: {cr.total_tokens.toLocaleString()} · Retries:{" "}
                {cr.total_retries} · Started: {cr.started_at || "—"}
              </div>
              {cr.agent_runs && cr.agent_runs.length > 0 && (
                <div style={{ marginTop: 6 }}>
                  {cr.agent_runs.map((ar) => (
                    <div
                      key={`${cr.id}-${ar.agent_id}`}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "3px 0",
                        fontSize: 12,
                        color: "#C9D1D9",
                      }}
                    >
                      <span>{agentActionLabel(ar.orchestrator_action)}</span>
                      <span style={{ fontWeight: 500 }}>
                        {ar.agent_id}
                      </span>
                      <span style={{ color: "#8B949E" }}>
                        ({ar.attempt_number} intento,{" "}
                        {ar.tokens_used.toLocaleString()} tokens)
                      </span>
                      {ar.retry_count > 0 && (
                        <span style={{ color: "#D29922" }}>
                          ↺ {ar.retry_count} retries
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/*
        ═══════════════════════════════════════════════════════════════
        FULL TIMELINE RENDERING — PSEUDOCODE (future implementation)
        ═══════════════════════════════════════════════════════════════

        This is the target rendering once the ChainOrchestrator v3 is
        producing data. Each ChainRun is rendered as a bordered panel
        showing every agent step with status icons, retry information,
        and branching context.

        ┌─ Chain: open_coding_main ─────────────────────────────┐
        │ ✓ fb_incident_grouper    (1 intento,  12K tokens)     │
        │ ✓ fb_code_generator       (1 intento,  18K tokens)     │
        │ ↻ fb_label_critic         (2 intentos, 8K tokens)      │
        │   └─ retry 1: "Label 'managing' too vague"             │
        │ ✓ fd_category_synthesizer (1 intento,  15K tokens)     │
        │ 🛑 fc_main_concern_proposer (escalated to HITL)        │
        └────────────────────────────────────────────────────────┘

        Implementation plan:
        1. Group chainRuns by chain_id (multiple runs = branches)
        2. For each chain_id, render the latest run by default
        3. Show parent_chain_run_id as a "branched from" indicator
        4. Each agent_runs entry maps to a row with:
           - Status icon (proceed = ✓, retrying = ↻, paused_hitl = 🛑)
           - Agent label (from pipelineChains.ts config)
           - Attempt number and tokens
           - Retry count with expandable detail
        5. Expand retries to show conversation_history excerpts
        6. "Retry from here" button on each row (future branching UX)
        7. Color-code by status:
           - completed = green
           - running = yellow/animated
           - aborted = red
           - paused_hitl = purple

        Pseudocode:
        ```
        const grouped = groupBy(filtered, "chain_id");

        grouped.forEach((runs, chainId) => {
          const latest = runs[0]; // sorted DESC by created_at

          <ChainPanel key={chainId} chainId={chainId}>
            <ChainHeader status={latest.status} ... />
            {latest.agent_runs?.map(ar => (
              <AgentRow
                key={ar.agent_id}
                agent={ar}
                onRetryFromHere={() => handleRetryFromHere(chainId, ar.agent_id)}
              >
                {ar.retry_count > 0 && <RetryExpandPanel retries={ar.retries} />}
              </AgentRow>
            ))}
            {latest.status === "paused_hitl" && (
              <HITLPrompt chainId={chainId} onResolve={...} />
            )}
          </ChainPanel>
        });
        ```
        ═══════════════════════════════════════════════════════════════
      */}
    </div>
  );
}
