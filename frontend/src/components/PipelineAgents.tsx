import { useState } from "react";
import type { StageDef, AgentDef } from "../config/pipelineChains";
import { FAMILY_COLORS } from "../config/pipelineChains";
import { useI18n } from "../i18n";

// ── Props ──────────────────────────────────────────────────────────

interface PipelineAgentsProps {
  agentStatuses: Record<string, "pending" | "running" | "done" | "error">;
  onRunAgent: (agentId: string) => void | Promise<void>;
  onStopAgent: (agentId: string) => void;
  pipelineRunning: boolean;
  completedAgents: Set<string>;
  iterations: Record<string, number>;
  agentDocCounts: Record<string, { done: number; total: number }>;
  eligibleDocCounts: Record<string, number>;
  upstreamDocCounts: Record<string, number>;
  stages?: StageDef[];
}

// ── Helpers ────────────────────────────────────────────────────────

function statusIcon(s: string): string {
  switch (s) {
    case "done":
      return "\u2713";
    case "running":
      return "\u25CF";
    case "error":
      return "\u2715";
    default:
      return "\u25CB";
  }
}

function statusColor(s: string): string {
  switch (s) {
    case "done":
      return "#3FB950";
    case "running":
      return "#A371F7";
    case "error":
      return "#F85149";
    default:
      return "#484F58";
  }
}

// ── Component ──────────────────────────────────────────────────────

export default function PipelineAgents({
  agentStatuses,
  onRunAgent,
  onStopAgent,
  pipelineRunning,
  completedAgents,
  iterations,
  agentDocCounts,
  eligibleDocCounts,
  upstreamDocCounts,
  stages,
}: PipelineAgentsProps) {
  const { t } = useI18n();
  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);

  if (!stages || stages.length === 0) {
    return (
      <div style={{ padding: 12, color: "#8B949E", fontSize: 11 }}>
        No hay etapas configuradas
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {stages.map((stage) => (
        <div key={stage.key}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 6,
              padding: "4px 0",
              borderBottom: "1px solid #21262D",
            }}
          >
            <span style={{ fontSize: 13 }}>{stage.icon}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#E6EDF3" }}>
              {t(stage.label)}
            </span>
            <span style={{ fontSize: 10, color: "#484F58" }}>
              {stage.agents.filter((a) => completedAgents.has(a.id)).length}/
              {stage.agents.length}
            </span>
          </div>

          {(() => {
            const chains = new Map<string, AgentDef[]>();
            const independents: AgentDef[] = [];

            for (const agent of stage.agents) {
              if (agent.chain) {
                const existing = chains.get(agent.chain) || [];
                existing.push(agent);
                chains.set(agent.chain, existing);
              } else {
                independents.push(agent);
              }
            }

            const sortedChains = [...chains.entries()].sort((a, b) => {
              const aOrder = a[1][0]?.chainOrder ?? 99;
              const bOrder = b[1][0]?.chainOrder ?? 99;
              return aOrder - bOrder;
            });

            return (
              <>
                {independents.map((agent) => renderAgent(agent))}

                {sortedChains.map(([chainLabel, agents]) => {
                  const sorted = [...agents].sort(
                    (a, b) => (a.chainOrder ?? 0) - (b.chainOrder ?? 0),
                  );
                  const iterKey = sorted[0]?.iterationKey;
                  const iterCount = iterKey ? iterations[iterKey] || 0 : 0;

                  return (
                    <div key={chainLabel} style={{ marginTop: 4 }}>
                      <div
                        style={{
                          fontSize: 9,
                          color: "#8B949E",
                          textTransform: "uppercase",
                          letterSpacing: "0.5px",
                          paddingLeft: 14,
                          marginBottom: 2,
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <span>{chainLabel}</span>
                        {iterCount > 0 && (
                          <span style={{ color: "#A371F7", fontWeight: 600 }}>
                            x{iterCount}
                          </span>
                        )}
                      </div>
                      {sorted.map((agent) => renderAgent(agent))}
                    </div>
                  );
                })}
              </>
            );
          })()}
        </div>
      ))}
    </div>
  );

  function depsSatisfied(_agentId: string, agent: AgentDef): boolean {
    for (const dep of agent.dependencies) {
      const upCount = upstreamDocCounts[dep];
      if (upCount !== undefined) {
        if (upCount === 0) return false;
        continue;
      }
      if (!completedAgents.has(dep)) return false;
    }
    return true;
  }

  function renderAgent(agent: AgentDef) {
    const docCount = agentDocCounts[agent.id];
    const doneCount = docCount?.done ?? 0;
    const totalDocs = docCount?.total ?? 0;
    const hasWork = totalDocs > 0;
    const eligible = (eligibleDocCounts[agent.id] ?? 0) > 0;

    const isExternallyRunning =
      (agentStatuses[agent.id] || "pending") === "running";
    const allDone = hasWork && doneCount >= totalDocs && !eligible;
    const status: string = allDone
      ? "done"
      : isExternallyRunning
        ? "running"
        : "pending";

    const depsMet = depsSatisfied(agent.id, agent);
    // canRun = deps satisfied AND not pipeline-running.
    // eligible only controls whether the play button shows (there's work to do).
    // An agent with depsMet but no eligible docs still shows as clickable
    // because its dependency already produced output — downstream agents
    // can see it as "passed".
    const canRun = depsMet && !pipelineRunning;
    const isHovered = hoveredAgent === agent.id;
    const isRunning = isExternallyRunning;
    const tierColor = FAMILY_COLORS[agent.tier] || "#8B949E";
    const depsUnmet = agent.dependencies.filter((d) => {
      const upCount = upstreamDocCounts[d];
      if (upCount !== undefined) return upCount === 0;
      return !completedAgents.has(d);
    });

    return (
      <div
        key={agent.id}
        onMouseEnter={() => setHoveredAgent(agent.id)}
        onMouseLeave={() => setHoveredAgent(null)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "3px 8px",
          borderRadius: 4,
          marginLeft: agent.chain ? 16 : 4,
          cursor: canRun || isRunning ? "pointer" : "default",
          background: isHovered ? "#A371F708" : "transparent",
          transition: "background 0.15s",
          opacity: canRun || isRunning || status === "done" ? 1 : 0.5,
        }}
        title={
          depsUnmet.length > 0
            ? `Dependencias pendientes: ${depsUnmet.join(", ")}`
            : t(agent.label)
        }
      >
        <span
          style={{
            fontSize: 8,
            color: statusColor(status),
            minWidth: 12,
            textAlign: "center",
          }}
        >
          {isRunning ? (
            <span
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "#A371F7",
                animation: "stagePulse 1.5s ease-in-out infinite",
              }}
            />
          ) : (
            statusIcon(status)
          )}
        </span>

        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: tierColor,
            flexShrink: 0,
          }}
        />

        <span
          style={{
            fontSize: 10,
            color:
              status === "done"
                ? "#3FB950"
                : status === "error"
                  ? "#F85149"
                  : "#C9D1D9",
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {t(agent.label)}
          {agentDocCounts[agent.id] && (
            <span
              style={{
                fontSize: 9,
                color: "#484F58",
                marginLeft: 4,
                whiteSpace: "nowrap",
              }}
            >
              {agentDocCounts[agent.id].done}/{agentDocCounts[agent.id].total}
            </span>
          )}
        </span>

        {/* Play: canRun + eligible = run new docs. canRun + !eligible = re-run. */}
        {isHovered && !isRunning && canRun && eligible && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRunAgent(agent.id);
            }}
            style={{
              background: "none",
              border: "none",
              color: "#3FB950",
              cursor: "pointer",
              fontSize: 12,
              padding: "0 2px",
              lineHeight: 1,
            }}
            title="Ejecutar agente"
          >
            ▶
          </button>
        )}
        {/* Re-run: all done (nothing left to process) but user may want to redo */}
        {isHovered && !isRunning && canRun && !eligible && allDone && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRunAgent(agent.id);
            }}
            style={{
              background: "none",
              border: "none",
              color: "#D29922",
              cursor: "pointer",
              fontSize: 11,
              padding: "0 2px",
              lineHeight: 1,
            }}
            title="Re-ejecutar agente"
          >
            ↻
          </button>
        )}
        {isHovered && isRunning && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onStopAgent(agent.id);
            }}
            style={{
              background: "none",
              border: "none",
              color: "#F85149",
              cursor: "pointer",
              fontSize: 12,
              padding: "0 2px",
              lineHeight: 1,
            }}
            title="Detener agente"
          >
            ⏹
          </button>
        )}
        {!isHovered && isRunning && (
          <span style={{ fontSize: 8, color: "#A371F7" }}>●</span>
        )}

        {status === "error" && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRunAgent(agent.id);
            }}
            style={{
              background: "none",
              border: "none",
              color: "#D29922",
              cursor: "pointer",
              fontSize: 10,
              padding: "0 2px",
            }}
            title="Reintentar"
          >
            ↻
          </button>
        )}
      </div>
    );
  }
}
