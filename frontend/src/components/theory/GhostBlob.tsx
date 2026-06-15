import { usePlayground } from "./PlaygroundContext";

interface Props {
  ghost: { id: string; content: string; type: string };
  x: number; y: number;
}

export default function GhostBlob({ ghost, x, y }: Props) {
  const pg = usePlayground();

  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData("application/ghost", ghost.id);
    e.dataTransfer.effectAllowed = "link";
    pg.setDragState({ fromId: ghost.id, toId: null, type: "ghost" });
  };

  const preview = ghost.content.slice(0, 60);

  return (
    <g transform={`translate(${x}, ${y})`} opacity={0.25} style={{ cursor: "grab" }}>
      <circle r={20} fill="#8B949E" stroke="#8B949E"
        strokeWidth={1} strokeDasharray="2 6" />
      <text y={30} textAnchor="middle" fill="#E6EDF3" fontSize="9"
        fontFamily="Inter, sans-serif">
        {preview}…
      </text>
    </g>
  );
}
