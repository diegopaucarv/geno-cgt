import { usePlayground } from "./PlaygroundContext";
import { getRenameSuggestions, getDefinitionHistory, applyRename } from "../../api/client";
import styles from "./CategoryBlob.module.css";

interface Props {
  blob: {
    id: string; name: string; saturation: string; is_core: boolean;
    relevance: number; version: number;
  };
  x: number;
  y: number;
}

const LAYER_COLORS: Record<string, string> = {
  core: "#FF6B35", process: "#4ECDC4", conditions: "#45B7D1",
  variation: "#96CEB4", consequences: "#DDA0DD", action: "#F7DC6F",
  fusion: "#D3D3D3", undefined: "#E8E8E8",
};

function blobRadius(relevance: number, isCore: boolean): number {
  if (isCore) return 68;
  if (relevance >= 4) return 52;
  if (relevance >= 2) return 40;
  return 32;
}

export default function CategoryBlob({ blob, x, y }: Props) {
  const pg = usePlayground();
  const isSelected = pg.selectedBlob?.id === blob.id;
  const isRenamePending = pg.renameTarget?.id === blob.id;
  const r = blobRadius(blob.relevance, blob.is_core);
  const color = LAYER_COLORS[blob.is_core ? "core" : "variation"];

  const handleClick = async () => {
    pg.selectBlob(blob as any);
    try {
      const [sug, hist] = await Promise.all([
        getRenameSuggestions(pg.projectId, blob.id),
        getDefinitionHistory(pg.projectId, blob.id),
      ]);
      if (sug.needs_rename) pg.openRename(blob as any);
    } catch { /* silent */ }
  };

  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData("text/plain", blob.id);
    e.dataTransfer.effectAllowed = "link";
  };

  const stateClass = isRenamePending ? styles.shimmer
    : isSelected ? styles.selected
    : blob.saturation === "ABIERTO" ? styles.pulsing
    : "";

  return (
    <g
      transform={`translate(${x}, ${y})`}
      onClick={handleClick}
      style={{ cursor: "pointer" }}
    >
      <defs>
        <radialGradient id={`grad-${blob.id}`} cx="30%" cy="30%">
          <stop offset="0%" stopColor={color} stopOpacity="0.9" />
          <stop offset="70%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="0.1" />
        </radialGradient>
        <filter id={`glow-${blob.id}`}>
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <circle
        className={`${styles.blob} ${stateClass}`}
        r={r}
        fill={`url(#grad-${blob.id})`}
        stroke={color}
        strokeWidth={isSelected ? 3 : 1.5}
        opacity={blob.relevance >= 4 ? 0.9 : 0.6}
        filter={isSelected ? `url(#glow-${blob.id})` : undefined}
        draggable
        onDragStart={handleDragStart}
      />

      {blob.is_core && (
        <circle r={r + 8} fill="none" stroke={color} strokeWidth="1"
          strokeDasharray="4 8" opacity="0.3" />
      )}

      <text y={r + 18} textAnchor="middle" fill="#E6EDF3" fontSize="11"
        fontFamily="Inter, sans-serif" fontWeight={500}>
        {blob.name.length > 25 ? blob.name.slice(0, 22) + "…" : blob.name}
      </text>
    </g>
  );
}
