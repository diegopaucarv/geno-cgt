import { usePlayground } from "./PlaygroundContext";
import { useI18n } from "../../i18n";

export default function ElaborationPanel() {
  const pg = usePlayground();
  const { selectedBlob, selectedTendril } = pg;

  if (selectedBlob) return <BlobDetail blob={selectedBlob} />;
  if (selectedTendril) return <TendrilDetail tendril={selectedTendril} />;
  return <EmptyState />;
}

function BlobDetail({ blob }: { blob: any }) {
  const { t } = useI18n();

  return (
    <div style={panelStyle}>
      <div style={sectionStyle}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ fontWeight: 600, fontSize: 15, color: "#E6EDF3" }}>
            {blob.name || t("theory.emptyName")}
          </span>
          <span
            style={{
              padding: "2px 10px",
              borderRadius: 999,
              fontSize: 11,
              background: blob.is_core ? "#FF6B3522" : "#45B7D122",
              color: blob.is_core ? "#FF6B35" : "#45B7D1",
            }}
          >
            {blob.is_core
              ? t("theory.coreBadge")
              : `${t("theory.versionBadge")}${blob.version}`}
          </span>
        </div>
      </div>

      <div style={sectionStyle}>
        <div style={labelStyle}>{t("theory.definitionHeading")}</div>
        <p
          style={{ fontSize: 13, color: "#8B949E", margin: 0, lineHeight: 1.5 }}
        >
          {blob.definition || t("theory.noDefinition")}
        </p>
      </div>

      <div style={sectionStyle}>
        <div style={labelStyle}>
          {t("theory.saturationHeading")}
          <span
            style={{
              color:
                blob.saturation === t("theory.saturatedState")
                  ? "#3FB950"
                  : "#D29922",
              fontSize: 11,
            }}
          >
            {blob.saturation}
          </span>
        </div>
      </div>

      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid #21262D",
          display: "flex",
          gap: 8,
        }}
      >
        <button style={btnStyle}>{t("theory.suggestRename")}</button>
        <button style={{ ...btnStyle, background: "#21262D" }}>
          {t("theory.viewIncidents")}
        </button>
      </div>
    </div>
  );
}

function TendrilDetail({ tendril }: { tendril: any }) {
  const { t } = useI18n();

  return (
    <div style={panelStyle}>
      <div style={sectionStyle}>
        <div style={{ fontWeight: 600, fontSize: 15, color: "#E6EDF3" }}>
          {t("theory.relationshipHeading")}
        </div>
        <div style={{ fontSize: 12, color: "#8B949E", marginTop: 4 }}>
          {t("theory.codePrefix")}
          {tendril.code_id?.slice(0, 8)}…
        </div>
      </div>

      <div style={sectionStyle}>
        <div style={labelStyle}>{t("theory.evidenceHeading")}</div>
        <div style={{ display: "flex", gap: 16, marginTop: 4 }}>
          <span style={{ color: "#3FB950", fontSize: 13 }}>
            ✓ {tendril.converging}
            {t("theory.docsConverge")}
          </span>
          {tendril.diverging > 0 && (
            <span style={{ color: "#F85149", fontSize: 13 }}>
              ↗ {tendril.diverging}
              {t("theory.docsDiverge")}
            </span>
          )}
        </div>
      </div>

      <div style={sectionStyle}>
        <div style={labelStyle}>{t("theory.conceptualAdjustment")}</div>
        <div
          style={{
            height: 4,
            background: "#21262D",
            borderRadius: 2,
            marginTop: 6,
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${(tendril.fit || 0) * 100}%`,
              background:
                tendril.fit > 0.7
                  ? "#3FB950"
                  : tendril.fit > 0.4
                    ? "#D29922"
                    : "#F85149",
              borderRadius: 2,
              transition: "width 0.5s",
            }}
          />
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  const { t } = useI18n();

  return (
    <div
      style={{
        ...panelStyle,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: 300,
      }}
    >
      <div style={{ textAlign: "center", color: "#484F58" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>◉</div>
        <div style={{ fontSize: 13 }}>{t("theory.dragInstruction1")}</div>
        <div style={{ fontSize: 13 }}>{t("theory.dragInstruction2")}</div>
      </div>
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

const sectionStyle: React.CSSProperties = {
  padding: "12px 16px",
  borderBottom: "1px solid #21262D",
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  color: "#8B949E",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  marginBottom: 4,
};

const btnStyle: React.CSSProperties = {
  padding: "6px 14px",
  borderRadius: 6,
  border: "1px solid #21262D",
  background: "#1C2333",
  color: "#E6EDF3",
  fontSize: 12,
  cursor: "pointer",
};
