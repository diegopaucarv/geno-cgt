import { useEffect, useState } from "react";
import { getPipelineDecisions } from "../../api/client";
import { useI18n } from "../../i18n";

interface PipelineDecisions {
  project_id: string;
  decisions: Array<{
    gate: string;
    proposal: Record<string, unknown>;
    critic_verdict: Record<string, unknown>;
    status: string;
    decision: string;
    note: string;
    decided_at: string | null;
  }>;
  saturation: Record<
    string,
    { no_expansion_count: number; saturated: boolean }
  >;
}

const GATE_ICONS: Record<string, string> = {
  pattern_of_interest: "🎯",
  core_emergence: "⭐",
  selective_reduction: "✂️",
  core_saturation: "🔄",
  database_a: "🗄️",
  database_b: "🔗",
  global_saturation: "✅",
};

const GATE_LABELS: Record<string, string> = {
  pattern_of_interest: "theory.gateMainConcern",
  core_emergence: "theory.gateCoreCategory",
  selective_reduction: "theory.gateSelectiveReduction",
  core_saturation: "theory.gateSaturation",
  database_a: "theory.gateDatabaseA",
  database_b: "theory.gateDatabaseB",
  global_saturation: "theory.gateGlobalCheck",
};

export default function PlaygroundDataPanel({
  projectId,
}: {
  projectId: string;
}) {
  const { t } = useI18n();
  const [data, setData] = useState<PipelineDecisions | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    getPipelineDecisions(projectId)
      .then(setData)
      .catch(() => {});
  }, [projectId]);

  function formatProposal(gate: string, p: Record<string, unknown>): string {
    if (gate === "pattern_of_interest") {
      return `"${(p.core_concern as string) || "?"}" (${(p.confidence as string) || "?"})`;
    }
    if (gate === "core_emergence") {
      const candidates = p.core_category_candidates as
        | Array<Record<string, unknown>>
        | undefined;
      if (candidates && candidates.length > 0) {
        return candidates.map((c) => c.code_name as string).join(", ");
      }
      return "?";
    }
    if (gate === "selective_reduction") {
      const kept = (p.kept_codes as string[]) || [];
      const merged = (p.merged_codes as Array<Record<string, unknown>>) || [];
      const discarded =
        (p.discarded_codes as Array<Record<string, unknown>>) || [];
      return `${kept.length}${t("theory.keptSuffix")}, ${merged.length}${t("theory.mergedSuffix")}, ${discarded.length}${t("theory.discardedSuffix")}`;
    }
    if (gate === "core_saturation") {
      const sc = p.saturated_categories as number | undefined;
      return sc ? `${sc}${t("theory.categoriesSaturatedSuffix")}` : "?";
    }
    if (gate === "database_a") {
      const nodes = (p.nodes as Array<Record<string, unknown>>) || [];
      return `${nodes.length}${t("theory.nodesSuffix")}`;
    }
    if (gate === "database_b") {
      const edges = (p.edges as Array<Record<string, unknown>>) || [];
      return `${edges.length}${t("theory.edgesSuffix")}`;
    }
    if (gate === "global_saturation") {
      return (p.all_conditions_met as boolean)
        ? t("theory.allMet")
        : t("theory.pending");
    }
    return JSON.stringify(p).slice(0, 80);
  }

  if (!data || data.decisions.length === 0) return null;

  return (
    <div
      style={{
        background: "#161B22",
        border: "1px solid #21262D",
        borderRadius: 10,
        overflow: "hidden",
        fontSize: 12,
        color: "#8B949E",
      }}
    >
      <div
        style={{
          padding: "10px 14px",
          borderBottom: collapsed ? "none" : "1px solid #21262D",
          fontSize: 12,
          fontWeight: 600,
          color: "#E6EDF3",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span style={{ fontWeight: 600, color: "#E6EDF3", fontSize: 13 }}>
          📋 {t("theory.pipelineDecisions")}
        </span>
        <span style={{ color: "#8B949E", fontSize: 16 }}>
          {collapsed ? t("theory.collapsed") : t("theory.expanded")}
        </span>
      </div>

      {!collapsed && (
        <div style={{ padding: "0 12px 10px" }}>
          {data.decisions.map((d) => (
            <div
              key={d.gate}
              style={{
                padding: "6px 8px",
                marginBottom: 4,
                borderRadius: 4,
                background: "#0D1117",
                border: "1px solid #21262D",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span>{GATE_ICONS[d.gate] || "📌"}</span>
                <span style={{ color: "#E6EDF3", fontWeight: 500 }}>
                  {t(GATE_LABELS[d.gate]) || d.gate}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    borderRadius: 999,
                    background: "#2EA04322",
                    color: "#2EA043",
                    marginLeft: "auto",
                  }}
                >
                  ✓
                </span>
              </div>
              <div style={{ marginTop: 2, color: "#58A6FF", fontSize: 11 }}>
                {formatProposal(d.gate, d.proposal)}
              </div>
            </div>
          ))}

          {/* Saturation summary */}
          {Object.keys(data.saturation).length > 0 && (
            <div
              style={{
                marginTop: 6,
                paddingTop: 6,
                borderTop: "1px solid #21262D",
              }}
            >
              <div
                style={{ fontWeight: 500, color: "#E6EDF3", marginBottom: 4 }}
              >
                🔄 {t("theory.saturationStatus")}
              </div>
              {Object.entries(data.saturation).map(([name, s]) => (
                <div
                  key={name}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: 11,
                    padding: "2px 0",
                  }}
                >
                  <span style={{ color: "#C9D1D9" }}>{name}</span>
                  <span
                    style={{
                      color: s.saturated ? "#2EA043" : "#D29922",
                      fontWeight: 500,
                    }}
                  >
                    {s.saturated
                      ? `${t("theory.saturatedPrefix")} (${s.no_expansion_count})`
                      : `${s.no_expansion_count}${t("theory.saturationDenominator")}`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
