import type { CSSProperties } from "react";

/** Contenedor del panel de incidentes (mismo look que el visor de segmentos). */
export const panelCard: CSSProperties = {
  width: "100%",
  minHeight: 150,
  maxHeight: "55vh",
  overflow: "auto",
  fontSize: 13,
  background: "#0D1117",
  color: "#E6EDF3",
  border: "1px solid #21262D",
  borderRadius: 6,
  padding: 8,
  wordBreak: "break-word",
  boxSizing: "border-box",
};

/** Botón de acción mínima dentro del panel. */
export const btnTiny: CSSProperties = {
  padding: "1px 6px",
  borderRadius: 4,
  fontSize: 10,
  fontWeight: 500,
  cursor: "pointer",
  border: "1px solid #30363D",
  background: "transparent",
  color: "#8B949E",
  lineHeight: 1.6,
};

/** Pastilla de categoría Glaser / estado. */
export function chipStyle(color: string): CSSProperties {
  return {
    fontSize: 9,
    padding: "1px 6px",
    borderRadius: 999,
    background: `${color}22`,
    color,
    border: `1px solid ${color}44`,
    whiteSpace: "nowrap",
  };
}

export const overlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(0,0,0,0.6)",
};

export const modalCard: CSSProperties = {
  background: "#161B22",
  borderRadius: 12,
  border: "1px solid #21262D",
  width: 560,
  maxWidth: "92vw",
  maxHeight: "85vh",
  overflow: "auto",
  padding: 16,
  color: "#E6EDF3",
};

export const fieldLabel: CSSProperties = {
  display: "block",
  fontSize: 10,
  fontWeight: 600,
  color: "#8B949E",
  textTransform: "uppercase",
  letterSpacing: 0.4,
  margin: "10px 0 4px",
};

export const textInput: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: 6,
  borderRadius: 4,
  background: "#0D1117",
  border: "1px solid #30363D",
  color: "#E6EDF3",
  fontSize: 12,
  fontFamily: "inherit",
};

export const selectInput: CSSProperties = { ...textInput };
