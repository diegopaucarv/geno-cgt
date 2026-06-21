import { useState } from "react";
import type { StageDef, AgentDef } from "../config/pipelineChains";
import { FAMILY_COLORS, canRunAgent } from "../config/pipelineChains";
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
  /** Per-agent count of documents actually eligible (in the correct estado for this agent).
   *  If 0, the agent button is disabled regardless of dependency status. */
  eligibleDocCounts: Record<string, number>;
  stages?: StageDef[];
}

// ── Helpers ────────────────────────────────────────────────────────

function statusIcon(s: string): string {
  switch (s) {
    case "done":
      return "✓";
    case "running":
      return "●";
    case "error":
      return "✕";
    default:
      return "○";
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
          {/* Stage header */}
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

          {/* Group agents by chain */}
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

            // Sort chains by their first agent's chainOrder
            const sortedChains = [...chains.entries()].sort((a, b) => {
              const aOrder = a[1][0]?.chainOrder ?? 99;
              const bOrder = b[1][0]?.chainOrder ?? 99;
              return aOrder - bOrder;
            });

            return (
              <>
                {/* Independent agents */}
                {independents.map((agent) => renderAgent(agent))}

                {/* Chain groups */}
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
                            ×{iterCount}
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

  function renderAgent(agent: AgentDef) {
    const docCount = agentDocCounts[agent.id];
    const totalDocs = docCount?.total ?? 0;
    const eligible = (eligibleDocCounts[agent.id] ?? 0) > 0;
    // Agent shows ✓ only when NO docs remain to process AND all have passed this stage
    const status =
      totalDocs > 0 && docCount.done >= totalDocs && eligible === false
        ? "done"
        : agentStatuses[agent.id] || "pending";
    const depsMet = canRunAgent(agent.id, completedAgents);
    const canRun = depsMet && eligible && !pipelineRunning;
    const isHovered = hoveredAgent === agent.id;
    const isRunning = status === "running";
    const tierColor = FAMILY_COLORS[agent.tier] || "#8B949E";
    const depsUnmet = agent.dependencies.filter((d) => !completedAgents.has(d));

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
        {/* Status dot */}
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

        {/* Tier indicator */}
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: tierColor,
            flexShrink: 0,
          }}
        />

        {/* Label */}
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

        {/* Play/Pause button on hover */}
        {isHovered && !isRunning && canRun && (
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

        {/* Error retry */}
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
