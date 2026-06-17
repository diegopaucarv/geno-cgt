import { usePlayground } from "./PlaygroundContext";
import { useI18n } from "../../i18n";

export default function RecommendationGuide() {
  const pg = usePlayground();
  const { t } = useI18n();
  const recs = pg.recommendations;

  const grouped: Record<string, typeof recs> = {
    [t("theory.suggestedConnections")]: recs.filter(
      (r) => r.action_type === "connect",
    ),
    [t("theory.ghostBlobs")]: recs.filter(
      (r) => r.action_type === "absorb_ghost",
    ),
    [t("theory.suggestedRenames")]: recs.filter(
      (r) => r.action_type === "rename",
    ),
    [t("theory.fogZones")]: recs.filter((r) => r.action_type === "sample"),
    [t("theory.tensions")]: recs.filter(
      (r) => r.action_type === "resolve_tension",
    ),
  };

  return (
    <div style={{ height: "100%", overflow: "auto" }}>
      {Object.entries(grouped).map(([label, items]) =>
        items.length > 0 ? (
          <div key={label}>
            <div
              style={{
                padding: "8px 16px",
                fontSize: 11,
                fontWeight: 500,
                color: "#484F58",
                textTransform: "uppercase",
              }}
            >
              {t("theory.expandIndicator")}
              {label} ({items.length})
            </div>
            {items.slice(0, 3).map((r, i) => (
              <div key={i} style={itemStyle}>
                <div
                  style={{ fontSize: 12, color: "#E6EDF3", lineHeight: 1.4 }}
                >
                  {r.title}
                </div>
                <div style={{ fontSize: 11, color: "#8B949E", marginTop: 2 }}>
                  {r.description}
                </div>
                {r.action_type === "connect" && (
                  <button style={actionBtn}>{t("theory.connectAction")}</button>
                )}
                {r.action_type === "rename" && (
                  <button style={actionBtn}>{t("theory.renameAction")}</button>
                )}
              </div>
            ))}
          </div>
        ) : null,
      )}

      {recs.length === 0 && (
        <div
          style={{
            padding: 16,
            fontSize: 12,
            color: "#484F58",
            textAlign: "center",
          }}
        >
          {t("theory.noRecommendations")}
        </div>
      )}
    </div>
  );
}

const panelStyle: React.CSSProperties = {
  background: "#161B22",
  borderRadius: 8,
  border: "1px solid #21262D",
  height: "100%",
  overflow: "auto",
};

const itemStyle: React.CSSProperties = {
  padding: "10px 16px",
  borderTop: "1px solid #21262D15",
  position: "relative",
};

const actionBtn: React.CSSProperties = {
  position: "absolute",
  right: 12,
  top: 10,
  background: "none",
  border: "none",
  color: "#58A6FF",
  cursor: "pointer",
  fontSize: 12,
};
