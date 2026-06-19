import { useI18n } from "../i18n";

// ── Agent definition map ───────────────────────────────────────────

interface AgentDef {
  stage: string;
  family: "PRO" | "FLASH" | "NLP";
  label: string;
}

const AGENT_MAP: Record<string, AgentDef> = {
  // ── Stage: segment ──
  segmentar_documento: {
    stage: "segment",
    family: "NLP",
    label: "Segmentar documento",
  },

  // ── Stage: agents ──
  fa_document_pattern_extractor: {
    stage: "agents",
    family: "FLASH",
    label: "FA: Document Pattern Extractor",
  },
  fa_gerund_sweep: {
    stage: "agents",
    family: "FLASH",
    label: "FA: Gerund Sweep",
  },
  fa_recontextualize_code: {
    stage: "agents",
    family: "FLASH",
    label: "FA: Recontextualize Code",
  },
  pro_a1_initial_coding: {
    stage: "agents",
    family: "PRO",
    label: "PRO: A1 – Initial Coding",
  },
  pro_a2_focused_coding: {
    stage: "agents",
    family: "PRO",
    label: "PRO: A2 – Focused Coding",
  },
  pro_a3_axial_coding: {
    stage: "agents",
    family: "PRO",
    label: "PRO: A3 – Axial Coding",
  },
  pro_a14_core_emergence: {
    stage: "agents",
    family: "PRO",
    label: "PRO: A14 – Core Emergence",
  },

  // ── Stage: synthesis ──
  pro_b1_cross_document_merge: {
    stage: "synthesis",
    family: "PRO",
    label: "PRO: B1 – Cross-Document Merge",
  },
  pro_b2_property_dimension: {
    stage: "synthesis",
    family: "PRO",
    label: "PRO: B2 – Property/Dimension",
  },
  pro_b25_selective_coding: {
    stage: "synthesis",
    family: "PRO",
    label: "PRO: B2.5 – Selective Coding",
  },
  pro_b3_theoretical_integration: {
    stage: "synthesis",
    family: "PRO",
    label: "PRO: B3 – Theoretical Integration",
  },
  fa_cross_doc_pattern_linker: {
    stage: "synthesis",
    family: "FLASH",
    label: "FA: Cross-Doc Pattern Linker",
  },
  fa_b1_cluster_auditor: {
    stage: "synthesis",
    family: "FLASH",
    label: "FA: B1 – Cluster Auditor",
  },

  // ── Stage: find_cc ──
  pro_cc_core_category_verifier: {
    stage: "find_cc",
    family: "PRO",
    label: "PRO: CC – Core Category Verifier",
  },
  fa_cc_pattern_ranker: {
    stage: "find_cc",
    family: "FLASH",
    label: "FA: CC – Pattern Ranker",
  },
  fa_cc_saturation_checker: {
    stage: "find_cc",
    family: "FLASH",
    label: "FA: CC – Saturation Checker",
  },

  // ── Stage: reduce ──
  pro_selective_reduction: {
    stage: "reduce",
    family: "PRO",
    label: "PRO: Selective Reduction",
  },
  fa_selective_reduction_critic: {
    stage: "reduce",
    family: "FLASH",
    label: "FA: Selective Reduction Critic",
  },

  // ── Stage: saturate ──
  pro_core_saturation: {
    stage: "saturate",
    family: "PRO",
    label: "PRO: Core Saturation",
  },
  fa_core_saturation_critic: {
    stage: "saturate",
    family: "FLASH",
    label: "FA: Core Saturation Critic",
  },

  // ── Stage: build_db ──
  pro_database_a_builder: {
    stage: "build_db",
    family: "PRO",
    label: "PRO: Database A Builder",
  },
  fa_database_a_critic: {
    stage: "build_db",
    family: "FLASH",
    label: "FA: Database A Critic",
  },
  pro_database_b_builder: {
    stage: "build_db",
    family: "PRO",
    label: "PRO: Database B Builder",
  },
  fa_database_b_critic: {
    stage: "build_db",
    family: "FLASH",
    label: "FA: Database B Critic",
  },
};

// ── Pipeline stage definitions (mirrors Project.tsx PIPELINE_STAGES) ──

interface StageDef {
  key: string;
  icon: string;
  label: string;
}

const PIPELINE_STAGES: StageDef[] = [
  { key: "segment", icon: "✂️", label: "project.stageSegmentation" },
  { key: "agents", icon: "🧠", label: "project.stageOpenCoding" },
  { key: "synthesis", icon: "🔗", label: "project.stageCrossDoc" },
  { key: "maturity", icon: "🔍", label: "project.stageVerifyingMaturity" },
  { key: "find_cc", icon: "🎯", label: "project.stagePatternOfInterest" },
  { key: "reduce", icon: "✂️", label: "project.stageSelectiveReduction" },
  { key: "saturate", icon: "🔄", label: "project.stageCoreSaturation" },
  { key: "build_db", icon: "🗄️", label: "project.stageDatabaseA" },
  {
    key: "playground",
    icon: "🎨",
    label: "project.stageTheoreticalPlayground",
  },
];

// ── Family colors ──────────────────────────────────────────────────

const FAMILY_COLORS: Record<string, string> = {
  PRO: "#A371F7",
  FLASH: "#3FB950",
  NLP: "#58A6FF",
};

// ── Props ──────────────────────────────────────────────────────────

interface PipelineAgentsProps {
  agentStatuses: Record<string, "pending" | "running" | "done" | "error">;
  onAgentClick: (agentId: string, agentLabel: string) => void;
  pipelineRunning: boolean;
  agentOutputCounts?: Record<string, number>;
  onEraseStageOutputs?: (stageKey: string) => void;
  onEraseAgentOutputs?: (agentId: string) => void;
  agentLatencies?: Record<string, number>;
}

// ── Helpers ────────────────────────────────────────────────────────

function formatLatency(seconds: number): string {
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)}ms`;
  }
  return `${seconds.toFixed(1)}s`;
}

// ── Component ──────────────────────────────────────────────────────

export default function PipelineAgents({
  agentStatuses,
  onAgentClick,
  pipelineRunning,
  agentOutputCounts,
  onEraseStageOutputs,
  onEraseAgentOutputs,
  agentLatencies,
}: PipelineAgentsProps) {
  const { t } = useI18n();

  // Group agents by stage
  const agentsByStage: Record<
    string,
    Array<{ id: string; def: AgentDef }>
  > = {};
  for (const [agentId, def] of Object.entries(AGENT_MAP)) {
    if (!agentsByStage[def.stage]) agentsByStage[def.stage] = [];
    agentsByStage[def.stage].push({ id: agentId, def });
  }

  // Total output count for all agents in a stage
  const stageOutputCount = (stageKey: string): number => {
    const agents = agentsByStage[stageKey];
    if (!agents || !agentOutputCounts) return 0;
    return agents.reduce(
      (sum, { id }) => sum + (agentOutputCounts[id] || 0),
      0,
    );
  };

  // Pulsing animation keyframes
  const pulseKeyframes = `
    @keyframes agentPulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
  `;

  return (
    <>
      <style>{pulseKeyframes}</style>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {PIPELINE_STAGES.map((stage) => {
          const agents = agentsByStage[stage.key];
          const stageHasOutputs = stageOutputCount(stage.key) > 0;

          return (
            <div key={stage.key}>
              {/* Stage header */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 12px",
                  borderRadius: 6,
                  cursor: "default",
                }}
              >
                <span style={{ fontSize: 14 }}>{stage.icon}</span>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: "#8B949E",
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  {t(stage.label)}
                </span>
              </div>

              {/* Agent nodes */}
              {agents && agents.length > 0 && (
                <div style={{ paddingLeft: 20 }}>
                  {agents.map(({ id, def }, agentIdx) => {
                    const status = agentStatuses[id] || "pending";
                    const familyColor = FAMILY_COLORS[def.family] || "#8B949E";
                    const isLast = agentIdx === agents.length - 1;
                    const outputCount = agentOutputCounts?.[id] || 0;
                    const latency = agentLatencies?.[id];

                    return (
                      <div key={id}>
                        {/* Connecting line */}
                        <div
                          style={{
                            width: 2,
                            height: 8,
                            marginLeft: 13,
                            background: isLast ? "transparent" : "#21262D",
                          }}
                        />

                        {/* Agent node */}
                        <div
                          onClick={() => onAgentClick(id, def.label)}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            padding: "6px 8px",
                            borderRadius: 6,
                            cursor: "pointer",
                            transition: "background 0.15s",
                          }}
                          onMouseEnter={(e) => {
                            (
                              e.currentTarget as HTMLDivElement
                            ).style.background = "#1C2333";
                          }}
                          onMouseLeave={(e) => {
                            (
                              e.currentTarget as HTMLDivElement
                            ).style.background = "transparent";
                          }}
                        >
                          {/* Agent circle */}
                          <div
                            style={{
                              width: 28,
                              height: 28,
                              minWidth: 28,
                              borderRadius: "50%",
                              border: `2px solid ${familyColor}`,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontSize: 11,
                              background:
                                status === "done"
                                  ? `${familyColor}22`
                                  : status === "running"
                                    ? `${familyColor}11`
                                    : "transparent",
                            }}
                          >
                            {status === "done" ? (
                              <span
                                style={{ color: "#3FB950", fontWeight: 700 }}
                              >
                                ✓
                              </span>
                            ) : status === "error" ? (
                              <span
                                style={{ color: "#F85149", fontWeight: 700 }}
                              >
                                ✗
                              </span>
                            ) : status === "running" ? (
                              <span
                                style={{
                                  display: "inline-block",
                                  width: 10,
                                  height: 10,
                                  borderRadius: "50%",
                                  background: familyColor,
                                  animation:
                                    "agentPulse 1.5s ease-in-out infinite",
                                }}
                              />
                            ) : (
                              <span
                                style={{
                                  fontSize: 9,
                                  color: familyColor,
                                  opacity: 0.7,
                                  fontFamily: "monospace",
                                }}
                              >
                                {def.family.slice(0, 1)}
                              </span>
                            )}
                          </div>

                          {/* Agent label + info */}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 6,
                                minWidth: 0,
                              }}
                            >
                              <span
                                style={{
                                  fontSize: 11,
                                  fontWeight: status === "running" ? 600 : 400,
                                  color:
                                    status === "done"
                                      ? "#E6EDF3"
                                      : status === "running"
                                        ? "#E6EDF3"
                                        : status === "error"
                                          ? "#F85149"
                                          : "#8B949E",
                                  lineHeight: 1.4,
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                  flex: 1,
                                  minWidth: 0,
                                }}
                              >
                                {def.label}
                              </span>
                              {outputCount > 0 && (
                                <span
                                  style={{
                                    fontSize: 10,
                                    fontWeight: 600,
                                    color: "#E6EDF3",
                                    background: "#30363D",
                                    borderRadius: 10,
                                    padding: "0px 6px",
                                    lineHeight: "16px",
                                    whiteSpace: "nowrap",
                                    flexShrink: 0,
                                  }}
                                >
                                  {outputCount}
                                </span>
                              )}
                            </div>
                            <div
                              style={{
                                fontSize: 9,
                                color: familyColor,
                                opacity: 0.7,
                                fontFamily: "monospace",
                                marginTop: 1,
                              }}
                            >
                              {def.family}
                              {latency !== undefined && (
                                <span
                                  style={{
                                    marginLeft: 6,
                                    color: "#8B949E",
                                    fontFamily: "monospace",
                                  }}
                                >
                                  {formatLatency(latency)}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Per-agent erase button */}
                          {outputCount > 0 && onEraseAgentOutputs && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onEraseAgentOutputs(id);
                              }}
                              title={`Erase ${def.label} outputs`}
                              style={{
                                background: "transparent",
                                border: "1px solid #F8514933",
                                color: "#F85149",
                                cursor: "pointer",
                                fontSize: 12,
                                padding: "2px 6px",
                                borderRadius: 4,
                                lineHeight: "16px",
                                opacity: 0.7,
                                transition: "opacity 0.15s, background 0.15s",
                                flexShrink: 0,
                              }}
                              onMouseEnter={(e) => {
                                (
                                  e.currentTarget as HTMLButtonElement
                                ).style.opacity = "1";
                                (
                                  e.currentTarget as HTMLButtonElement
                                ).style.background = "#F8514911";
                              }}
                              onMouseLeave={(e) => {
                                (
                                  e.currentTarget as HTMLButtonElement
                                ).style.opacity = "0.7";
                                (
                                  e.currentTarget as HTMLButtonElement
                                ).style.background = "transparent";
                              }}
                            >
                              ✕
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {/* Stage erase outputs button */}
                  {stageHasOutputs && onEraseStageOutputs && (
                    <div style={{ marginTop: 4, marginBottom: 4 }}>
                      <button
                        onClick={() => onEraseStageOutputs(stage.key)}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          background: "transparent",
                          border: "1px solid #F8514933",
                          color: "#F85149",
                          cursor: "pointer",
                          fontSize: 10,
                          padding: "3px 8px",
                          borderRadius: 4,
                          opacity: 0.7,
                          transition: "opacity 0.15s, background 0.15s",
                        }}
                        onMouseEnter={(e) => {
                          const el = e.currentTarget as HTMLButtonElement;
                          el.style.opacity = "1";
                          el.style.background = "#F8514911";
                        }}
                        onMouseLeave={(e) => {
                          const el = e.currentTarget as HTMLButtonElement;
                          el.style.opacity = "0.7";
                          el.style.background = "transparent";
                        }}
                      >
                        🗑 Erase outputs
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
