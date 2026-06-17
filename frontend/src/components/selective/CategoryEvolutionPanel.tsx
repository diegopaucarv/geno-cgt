import { useEffect, useState } from "react";
import { getDefinitionHistory, type DefinitionVersion } from "../../api/client";
import { useI18n } from "../../i18n";

interface Props {
  categoryId: string;
  categoryName: string;
  projectId: string;
}

export default function CategoryEvolutionPanel({
  categoryId,
  categoryName,
  projectId,
}: Props) {
  const { t } = useI18n();
  const [history, setHistory] = useState<DefinitionVersion[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDefinitionHistory(projectId, categoryId)
      .then(setHistory)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [categoryId, projectId]);

  if (loading)
    return (
      <div style={panelStyle}>
        <p style={{ color: "#8B949E", fontSize: 13, padding: 16 }}>
          {t("theory.loadingHistory")}
        </p>
      </div>
    );

  const triggerLabels: Record<string, string> = {
    incident_converged: t("theory.triggerConverged"),
    incident_diverged_property: t("theory.triggerDivergedProperty"),
    incident_diverged_dimension: t("theory.triggerDivergedDimension"),
    ghost_absorbed: t("theory.triggerGhostAbsorbed"),
    rename_applied: t("theory.triggerRenameApplied"),
    manual_edit: t("theory.triggerManualEdit"),
  };

  return (
    <div style={panelStyle}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #21262D" }}>
        <span style={{ fontWeight: 600, fontSize: 14, color: "#E6EDF3" }}>
          {t("theory.evolutionHeading")}
          {categoryName}
        </span>
        <span style={{ fontSize: 11, color: "#8B949E", marginLeft: 8 }}>
          {history.length}
          {t("theory.versionsSuffix")}
        </span>
      </div>

      {history.length === 0 ? (
        <p style={{ padding: 16, fontSize: 13, color: "#484F58" }}>
          {t("theory.noHistory")}
        </p>
      ) : (
        <div style={{ padding: "8px 0" }}>
          {history.map((v, i) => (
            <div
              key={v.version}
              style={{
                padding: "10px 16px",
                borderLeft: "3px solid",
                borderColor: i === history.length - 1 ? "#A371F7" : "#21262D",
                marginLeft: 12,
                position: "relative",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: -7,
                  top: 12,
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: i === history.length - 1 ? "#A371F7" : "#484F58",
                }}
              />
              <div style={{ fontSize: 13, fontWeight: 500, color: "#E6EDF3" }}>
                {t("common.version")}
                {v.version}: {v.name}
              </div>
              <div style={{ fontSize: 11, color: "#8B949E", marginTop: 2 }}>
                {v.definition.slice(0, 120)}
                {v.definition.length > 120 ? "…" : ""}
              </div>
              <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
                <span style={pillStyle}>
                  {triggerLabels[v.trigger] || v.trigger}
                </span>
                <span style={{ fontSize: 11, color: "#484F58" }}>
                  {new Date(v.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const panelStyle: React.CSSProperties = {
  background: "#161B22",
  borderRadius: 8,
  border: "1px solid #21262D",
  overflow: "auto",
};

const pillStyle: React.CSSProperties = {
  padding: "1px 8px",
  borderRadius: 999,
  fontSize: 10,
  background: "#A371F722",
  color: "#A371F7",
};
