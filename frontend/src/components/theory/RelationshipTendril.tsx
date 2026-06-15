import { usePlayground } from "./PlaygroundContext";
import { getRelationship } from "../../api/client";

interface Props {
  tendril: {
    id: string; category_ids: string[]; code_id: string;
    status: string; converging: number; diverging: number;
    fit: number; layer: string; tension: number;
  };
  fromX: number; fromY: number;
  toX: number; toY: number;
}

const LAYER_COLORS: Record<string, string> = {
  process: "#4ECDC4", conditions: "#45B7D1", variation: "#96CEB4",
  consequences: "#DDA0DD", action: "#F7DC6F", fusion: "#D3D3D3",
};

export default function RelationshipTendril({ tendril, fromX, fromY, toX, toY }: Props) {
  const pg = usePlayground();
  const color = LAYER_COLORS[tendril.layer] || "#8B949E";
  const isSelected = pg.selectedTendril?.id === tendril.id;
  const isEmerging = tendril.status === "emerging";
  const hasDivergence = tendril.diverging > 0 && tendril.tension > 0;

  // Bézier control point
  const midX = (fromX + toX) / 2;
  const midY = (fromY + toY) / 2;
  const dx = toX - fromX;
  const dy = toY - fromY;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const perpX = -dy / len * (len * 0.15);
  const perpY = dx / len * (len * 0.15);
  const cx = midX + perpX;
  const cy = midY + perpY;

  const path = `M ${fromX} ${fromY} Q ${cx} ${cy} ${toX} ${toY}`;
  const thickness = Math.max(1, Math.min(8, tendril.converging * 1.5));

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (hasDivergence) {
      // Elaborar divergencia — abrir detalle
    }
    pg.selectTendril(tendril as any);
    try {
      const detail = await getRelationship(pg.projectId, tendril.id);
    } catch { /* silent */ }
  };

  return (
    <g onClick={handleClick} style={{ cursor: "pointer" }}>
      {/* Sombra suave */}
      <path
        d={path} fill="none"
        stroke={color} strokeWidth={thickness + 2}
        opacity={0.15}
      />

      {/* Tendril principal */}
      <path
        d={path} fill="none"
        stroke={color} strokeWidth={isSelected ? thickness + 2 : thickness}
        opacity={isEmerging ? 0.35 : 0.75}
        strokeDasharray={isEmerging ? "6 4" : undefined}
        strokeLinecap="round"
      />

      {/* Fisuras (divergencia) */}
      {hasDivergence && (
        <path
          d={path} fill="none"
          stroke="#FFD700" strokeWidth={2}
          strokeDasharray="3 6"
          opacity={tendril.tension * 0.8}
          strokeLinecap="round"
        />
      )}

      {/* Indicador de fisura */}
      {hasDivergence && (
        <circle
          cx={fromX + (toX - fromX) * 0.55}
          cy={fromY + (toY - fromY) * 0.55}
          r={4} fill="#FFD700" opacity={0.6}
        />
      )}
    </g>
  );
}
