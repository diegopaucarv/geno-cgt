import { usePlayground } from "./PlaygroundContext";

export default function RecommendationGuide() {
  const pg = usePlayground();
  const recs = pg.recommendations;

  const grouped: Record<string, typeof recs> = {
    "Conexiones sugeridas": recs.filter((r) => r.action_type === "connect"),
    "Ghost-blobs": recs.filter((r) => r.action_type === "absorb_ghost"),
    "Renombres sugeridos": recs.filter((r) => r.action_type === "rename"),
    "Zonas de neblina": recs.filter((r) => r.action_type === "sample"),
    Tensiones: recs.filter((r) => r.action_type === "resolve_tension"),
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
              ▼ {label} ({items.length})
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
                  <button style={actionBtn}>[→]</button>
                )}
                {r.action_type === "rename" && (
                  <button style={actionBtn}>[✦]</button>
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
          Sin recomendaciones aún.
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
