import { useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { PlaygroundProvider, usePlayground } from "../components/theory/PlaygroundContext";
import EcosystemCanvas from "../components/theory/EcosystemCanvas";
import ElaborationPanel from "../components/theory/ElaborationPanel";
import RecommendationGuide from "../components/theory/RecommendationGuide";
import RenameModal from "../components/theory/RenameModal";

function PlaygroundInner() {
  const pg = usePlayground();
  const { id } = useParams<{ id: string }>();

  useEffect(() => {
    if (id) pg.setProjectId(id);
  }, [id]);

  const coreBlob = pg.blobs.find(b => b.is_core);
  const totalGaps = pg.recommendations.length;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "#0D1117" }}>
      {/* Top Bar */}
      <div style={{
        padding: "12px 24px", borderBottom: "1px solid #21262D",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        background: "#161B22",
      }}>
        <div>
          <Link to={`/projects/${id}`} style={{ color: "#58A6FF", fontSize: 13, textDecoration: "none" }}>
            ← Volver al proyecto
          </Link>
          <span style={{ color: "#E6EDF3", fontSize: 15, fontWeight: 600, marginLeft: 16 }}>
            Theoretical Playground
          </span>
        </div>
        {coreBlob && (
          <span style={{
            padding: "4px 12px", borderRadius: 999, fontSize: 12,
            background: "#FF6B3522", color: "#FF6B35",
          }}>
            {coreBlob.name}
          </span>
        )}
      </div>

      {/* Main Layout */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Left Panel */}
        <div style={{ width: 280, padding: "12px 8px 12px 12px", overflow: "hidden" }}>
          <RecommendationGuide />
        </div>

        {/* Center */}
        <div style={{ flex: 1, padding: 12 }}>
          <EcosystemCanvas />
        </div>

        {/* Right Panel */}
        <div style={{ width: 340, padding: "12px 12px 12px 8px", overflow: "hidden" }}>
          <ElaborationPanel />
        </div>
      </div>

      {/* Bottom Bar */}
      <div style={{
        padding: "8px 24px", borderTop: "1px solid #21262D",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        background: "#161B22", fontSize: 12, color: "#8B949E",
      }}>
        <span>
          {pg.blobs.length} categorías · {pg.tendrils.length} relaciones · {totalGaps} gaps · Fase 6b
        </span>
        <button onClick={pg.refreshEcosystem} style={{
          padding: "4px 12px", borderRadius: 6, border: "1px solid #21262D",
          background: "#1C2333", color: "#E6EDF3", fontSize: 12, cursor: "pointer",
        }}>
          Sync gaps
        </button>
      </div>

      {/* Modal */}
      <RenameModal />
    </div>
  );
}

export default function PlaygroundPage() {
  return (
    <PlaygroundProvider>
      <PlaygroundInner />
    </PlaygroundProvider>
  );
}
