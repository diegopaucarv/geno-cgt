import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { useParams, Link } from "react-router-dom";
import {
  PlaygroundProvider,
  usePlayground,
} from "../components/theory/PlaygroundContext";
import EcosystemCanvas from "../components/theory/EcosystemCanvas";
import ElaborationPanel from "../components/theory/ElaborationPanel";
import RecommendationGuide from "../components/theory/RecommendationGuide";
import RenameModal from "../components/theory/RenameModal";
import PlaygroundDataPanel from "../components/theory/PlaygroundDataPanel";
import { getPipelineLog } from "../api/client";

/* ── Shared card style (matches Project.tsx visual language) ── */
const CARD: CSSProperties = {
  background: "#161B22",
  border: "1px solid #21262D",
  borderRadius: 10,
  overflow: "hidden",
};

const CARD_HEADER: CSSProperties = {
  padding: "10px 14px",
  borderBottom: "1px solid #21262D",
  fontSize: 12,
  fontWeight: 600,
  color: "#E6EDF3",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
};

function PlaygroundInner() {
  const pg = usePlayground();
  const { id } = useParams<{ id: string }>();
  const [newDocsCount, setNewDocsCount] = useState(0);

  useEffect(() => {
    if (id) pg.setProjectId(id);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const check = () => {
      getPipelineLog(id)
        .then((log) => {
          setNewDocsCount(log.summary.need_synthesis || 0);
        })
        .catch(() => {});
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, [id]);

  const coreBlob = pg.blobs.find((b) => b.is_core);
  const totalGaps = pg.recommendations.length;

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "#0D1117",
        color: "#E6EDF3",
      }}
    >
      {/* ═══════════════ Top Bar ═══════════════ */}
      <div
        style={{
          padding: "10px 24px",
          borderBottom: "1px solid #21262D",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#161B22",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Link
            to={`/projects/${id}`}
            style={{ color: "#58A6FF", fontSize: 13, textDecoration: "none" }}
          >
            ← Proyectos
          </Link>
          <span style={{ fontSize: 15, fontWeight: 600 }}>
            Theoretical Playground
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {coreBlob && (
            <span
              style={{
                padding: "3px 12px",
                borderRadius: 999,
                fontSize: 11,
                background: "#FF6B3522",
                color: "#FF6B35",
                border: "1px solid #FF6B3533",
              }}
            >
              {coreBlob.name}
            </span>
          )}
          <button
            onClick={pg.refreshEcosystem}
            style={{
              padding: "5px 14px",
              borderRadius: 6,
              border: "1px solid #A371F744",
              background: "#A371F718",
              color: "#A371F7",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Sync gaps
          </button>
        </div>
      </div>

      {/* ═══════════════ New Data Banner ═══════════════ */}
      {newDocsCount > 0 && (
        <div
          style={{
            padding: "8px 24px",
            background: "#A371F718",
            borderBottom: "1px solid #A371F744",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 12, color: "#A371F7" }}>
            📄 {newDocsCount} documento{newDocsCount > 1 ? "s" : ""} nuevo
            {newDocsCount > 1 ? "s" : ""} — el análisis puede expandirse
          </span>
          <Link
            to={`/projects/${id}`}
            style={{
              padding: "4px 12px",
              borderRadius: 6,
              border: "1px solid #A371F744",
              background: "#A371F722",
              color: "#A371F7",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              textDecoration: "none",
            }}
          >
            Expandir análisis
          </Link>
        </div>
      )}

      {/* ═══════════════ Main Layout ═══════════════ */}
      <div
        style={{
          flex: 1,
          display: "flex",
          overflow: "hidden",
          padding: 12,
          gap: 12,
          minHeight: 0,
        }}
      >
        {/* ── Left Panel (300px) ── */}
        <div
          style={{
            width: 300,
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            overflowY: "auto",
          }}
        >
          {/* Pipeline Decisions */}
          {id && <PlaygroundDataPanel projectId={id} />}

          {/* Recommendations */}
          <div style={CARD}>
            <div style={CARD_HEADER}>💡 Recommendations</div>
            <div style={{ padding: "0 0 4px 0" }}>
              <RecommendationGuide />
            </div>
          </div>
        </div>

        {/* ── Center: Canvas ── */}
        <div
          style={{
            flex: 1,
            minWidth: 0,
            ...CARD,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <EcosystemCanvas />
        </div>

        {/* ── Right Panel (360px) ── */}
        <div
          style={{
            width: 360,
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            overflowY: "auto",
          }}
        >
          {/* Detail Panel */}
          <div style={CARD}>
            <div style={CARD_HEADER}>🔍 Detail</div>
            <div style={{ padding: 4 }}>
              <ElaborationPanel />
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════ Bottom Bar ═══════════════ */}
      <div
        style={{
          padding: "8px 24px",
          borderTop: "1px solid #21262D",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#161B22",
          fontSize: 12,
          color: "#8B949E",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span>
            <span style={{ color: "#E6EDF3", fontWeight: 500 }}>
              {pg.blobs.length}
            </span>{" "}
            categorías
          </span>
          <span style={{ color: "#21262D" }}>·</span>
          <span>
            <span style={{ color: "#E6EDF3", fontWeight: 500 }}>
              {pg.tendrils.length}
            </span>{" "}
            relaciones
          </span>
          <span style={{ color: "#21262D" }}>·</span>
          <span>
            <span
              style={{
                color: totalGaps > 0 ? "#D29922" : "#2EA043",
                fontWeight: 500,
              }}
            >
              {totalGaps}
            </span>{" "}
            gaps
          </span>
          <span style={{ color: "#21262D" }}>·</span>
          <span>Fase 6b</span>
        </div>
        <span style={{ fontSize: 11, color: "#484F58" }}>
          {coreBlob ? `Core: ${coreBlob.name}` : "Sin core category"}
        </span>
      </div>

      {/* ═══════════════ Modal ═══════════════ */}
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
