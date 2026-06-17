import { useState, useEffect } from "react";
import type { CSSProperties } from "react";
import { getAvailableMemoTypes, createMemo } from "../api/client";

// ── Types ───────────────────────────────────────────────────────────

interface MemoType {
  key: string;
  label: string;
  icon: string;
  color: string;
  description: string;
}

interface AddMemoModalProps {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;
}

// ── Styles ──────────────────────────────────────────────────────────

const OVERLAY: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(0,0,0,0.6)",
};

const CARD: CSSProperties = {
  background: "#161B22",
  borderRadius: 12,
  border: "1px solid #21262D",
  width: 480,
  maxHeight: "85vh",
  overflow: "auto",
  padding: 20,
  color: "#E6EDF3",
};

const LABEL: CSSProperties = {
  fontSize: 11,
  color: "#8B949E",
  marginBottom: 4,
  marginTop: 14,
  fontWeight: 600,
  textTransform: "uppercase",
};

const SELECT: CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  background: "#0D1117",
  border: "1px solid #21262D",
  color: "#E6EDF3",
  fontSize: 13,
};

const TEXTAREA: CSSProperties = {
  width: "100%",
  padding: "10px",
  borderRadius: 6,
  background: "#0D1117",
  border: "1px solid #21262D",
  color: "#E6EDF3",
  fontSize: 13,
  resize: "vertical",
  fontFamily: "inherit",
  boxSizing: "border-box",
};

const BUTTON_ROW: CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: 8,
  marginTop: 18,
};

const btnBase: CSSProperties = {
  padding: "7px 16px",
  borderRadius: 6,
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  border: "none",
};

const DESCRIPTION: CSSProperties = {
  fontSize: 11,
  color: "#8B949E",
  marginTop: 4,
  fontStyle: "italic",
};

const INFOBOX: CSSProperties = {
  marginTop: 14,
  padding: "10px 14px",
  borderRadius: 8,
  background: "#58A6FF10",
  border: "1px solid #58A6FF22",
  fontSize: 12,
  color: "#58A6FF",
  lineHeight: 1.5,
};

// ── ColorBadge ────────────────────────────────────────────────────────

function ColorBadge(t: MemoType) {
  const s: CSSProperties = {
    marginTop: 8,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "3px 10px",
    borderRadius: 999,
    background: t.color + "18",
    border: "1px solid " + t.color + "44",
    fontSize: 10,
    color: t.color,
    fontWeight: 600,
  };
  return (
    <div style={s}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: t.color,
        }}
      >
        {" "}
        {t.label}
      </span>
    </div>
  );
}

function InfoBoxCategoria() {
  return (
    <div style={INFOBOX}>
      <strong>Se creara:</strong> Una categoria en la tabla de entidades del
      proyecto.
      <br />
      <strong>No se creara:</strong> Asignaciones a segmentos.
    </div>
  );
}

function InfoBoxTeorico() {
  return (
    <div style={INFOBOX}>
      <strong>Se creara:</strong> Un codigo teorico personalizado disponible en
      el Playground.
      <br />
      <strong>No se creara:</strong> Relaciones conceptuales.
    </div>
  );
}

function ErrorBox(msg: string) {
  return (
    <div
      style={{
        marginTop: 12,
        padding: "8px 12px",
        borderRadius: 6,
        background: "#F8514922",
        border: "1px solid #F8514944",
        color: "#F85149",
        fontSize: 12,
      }}
    >
      {msg}
    </div>
  );
}

export default function AddMemoModal({
  projectId,
  onClose,
  onCreated,
}: AddMemoModalProps) {
  const [types, setTypes] = useState<MemoType[]>([]);
  const [selectedType, setSelectedType] = useState("");
  const [content, setContent] = useState("");
  const [isConfidential, setIsConfidential] = useState(false);
  const [stage, setStage] = useState("");
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getAvailableMemoTypes(projectId)
      .then((data) => {
        setTypes(data.available_types);
        setStage(data.stage);
        setPipelineRunning(data.pipeline_running);
        if (data.available_types.length > 0) {
          setSelectedType(data.available_types[0].key);
        }
      })
      .catch((e) => setError(e.message || "Error al cargar tipos"))
      .finally(() => setLoading(false));
  }, [projectId]);

  const handleSubmit = async () => {
    if (!selectedType || !content.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await createMemo(projectId, {
        tipo: selectedType,
        contenido: content,
        es_confidencial: isConfidential,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message || "Error al guardar");
    } finally {
      setSubmitting(false);
    }
  };

  const selected = types.find((t) => t.key === selectedType);

  if (loading) {
    return (
      <div style={OVERLAY}>
        <div style={CARD}>
          <span style={{ color: "#8B949E" }}>Cargando...</span>
        </div>
      </div>
    );
  }

  if (pipelineRunning) {
    return (
      <div style={OVERLAY} onClick={onClose}>
        <div style={CARD} onClick={(e) => e.stopPropagation()}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>
            🚫 Pipeline en ejecución
          </div>
          <div style={{ fontSize: 13, color: "#8B949E", lineHeight: 1.5 }}>
            Pausá el pipeline antes de añadir entidades manualmente.
          </div>
          <div style={BUTTON_ROW}>
            <button
              onClick={onClose}
              style={{ ...btnBase, background: "#21262D", color: "#E6EDF3" }}
            >
              Cerrar
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={OVERLAY} onClick={onClose}>
      <div style={CARD} onClick={(e) => e.stopPropagation()}>
        {/* Title */}
        <div
          style={{
            fontSize: 15,
            fontWeight: 600,
            marginBottom: 4,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          ➕ Add Memo
          <span
            style={{
              fontSize: 10,
              color: "#8B949E",
              fontWeight: 400,
              padding: "2px 8px",
              borderRadius: 999,
              background: "#21262D",
            }}
          >
            Etapa: {stage}
          </span>
        </div>

        {/* Type selector */}
        <div style={LABEL}>Tipo de entidad</div>
        <select
          style={SELECT}
          value={selectedType}
          onChange={(e) => setSelectedType(e.target.value)}
        >
          {types.map((t) => (
            <option key={t.key} value={t.key}>
              {t.icon} {t.label}
            </option>
          ))}
        </select>
        {selected && <div style={DESCRIPTION}>{selected.description}</div>}

        {/* Color indicator */}
        {selected && ColorBadge(selected)}

        {/* Content */}
        <div style={LABEL}>Contenido</div>
        <textarea
          style={TEXTAREA}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Escribí el contenido del memo..."
          rows={8}
        />

        {/* Confidential toggle */}
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            marginTop: 12,
            fontSize: 12,
            color: "#8B949E",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={isConfidential}
            onChange={(e) => setIsConfidential(e.target.checked)}
          />
          🔒 Confidencial
        </label>

        {/* Info box */}
        {selectedType === "CATEGORIA" && InfoBoxCategoria()}
        {selectedType === "TEORICO" && InfoBoxTeorico()}

        {/* Error */}
        {error && ErrorBox(error)}

        {/* Buttons */}
        <div style={BUTTON_ROW}>
          <button
            onClick={onClose}
            style={{ ...btnBase, background: "#21262D", color: "#E6EDF3" }}
          >
            Cancelar
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !content.trim()}
            style={{
              ...btnBase,
              background: submitting ? "#21262D" : "#3FB950",
              color: submitting ? "#8B949E" : "#fff",
              opacity: submitting || !content.trim() ? 0.5 : 1,
            }}
          >
            {submitting ? "Guardando..." : "Guardar Memo"}
          </button>
        </div>
      </div>
    </div>
  );
}
