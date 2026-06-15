import { useRef, useEffect, useCallback } from "react";
import { usePlayground } from "./PlaygroundContext";
import CategoryBlob from "./CategoryBlob";
import RelationshipTendril from "./RelationshipTendril";
import GhostBlob from "./GhostBlob";
import { elaborateRelationship } from "../../api/client";

const WIDTH = 800;
const HEIGHT = 600;

export default function EcosystemCanvas() {
  const pg = usePlayground();
  const svgRef = useRef<SVGSVGElement>(null);
  const animationRef = useRef<number>(0);

  // Posiciones: usar layout guardado o distribuir en espiral
  const positions = useRef<Record<string, { x: number; y: number }>>({});

  useEffect(() => {
    const pos: Record<string, { x: number; y: number }> = {};
    const cx = WIDTH / 2;
    const cy = HEIGHT / 2;

    pg.blobs.forEach((b, i) => {
      if (pg.blobs.length === 1) {
        pos[b.id] = { x: cx, y: cy };
      } else {
        const angle = (2 * Math.PI * i) / pg.blobs.length - Math.PI / 2;
        const radius = Math.min(WIDTH, HEIGHT) * 0.35;
        pos[b.id] = {
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
        };
      }
    });
    positions.current = pos;
  }, [pg.blobs]);

  const getPos = useCallback((id: string) => {
    return positions.current[id] || { x: WIDTH / 2, y: HEIGHT / 2 };
  }, []);

  // Drag & drop para proponer relaciones
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const ghostId = e.dataTransfer.getData("application/ghost");
    const blobId = e.dataTransfer.getData("text/plain");
    const targetEl = document.elementFromPoint(e.clientX, e.clientY);
    const targetSvg = targetEl?.closest("g");
    if (!targetSvg) return;

    // Buscar blob destino por posición
    const blobDroppedOn = pg.blobs.find(b => {
      const p = getPos(b.id);
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return false;
      const sx = p.x + rect.left;
      const sy = p.y + rect.top;
      return Math.abs(e.clientX - sx) < 60 && Math.abs(e.clientY - sy) < 60;
    });

    if (ghostId && blobDroppedOn) {
      // TODO: abrir confirmación de absorción
      pg.setDragState(null);
    } else if (blobId && blobDroppedOn && blobId !== blobDroppedOn.id) {
      // Proponer relación entre dos blobs
      pg.setDragState({ fromId: blobId, toId: blobDroppedOn.id, type: "blob" });
    }
  };

  return (
    <svg
      ref={svgRef}
      width="100%"
      height="100%"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      style={{ background: "#0D1117", borderRadius: 8, minHeight: 500 }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      {/* Fondo sutil */}
      <rect width={WIDTH} height={HEIGHT} fill="#0D1117" />
      <defs>
        <radialGradient id="bg-glow" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#1C2333" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#0D1117" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx={WIDTH / 2} cy={HEIGHT / 2} r={300} fill="url(#bg-glow)" />

      {/* Tendriles (debajo de los blobs) */}
      {pg.tendrils.map((t) => {
        const ids = t.category_ids || [];
        if (ids.length < 2) return null;
        const from = getPos(ids[0]);
        const to = getPos(ids[1]);
        return (
          <RelationshipTendril
            key={t.id}
            tendril={t}
            fromX={from.x} fromY={from.y}
            toX={to.x} toY={to.y}
          />
        );
      })}

      {/* Blobs */}
      {pg.blobs.map((b) => {
        const p = getPos(b.id);
        return <CategoryBlob key={b.id} blob={b} x={p.x} y={p.y} />;
      })}

      {/* Ghost-blobs (margen derecho) */}
      {pg.ghosts.map((g, i) => (
        <GhostBlob
          key={g.id}
          ghost={g}
          x={WIDTH - 60 - (i % 3) * 40}
          y={80 + Math.floor(i / 3) * 50}
        />
      ))}
    </svg>
  );
}
