import { useState, useEffect } from "react";
import type { CSSProperties } from "react";
import { getAvailableMemoTypes, createMemo } from "../api/client";
import { useI18n } from "../i18n";

// ── Types ───────────────────────────────────────────────────────────

interface MemoType {
  key: string;
  label: string;
  icon: string;
  color: string;
  description: string;
  requires_agent?: string;
  agent_status?: "not_run" | "completed";
}

interface StructuredFields {
  // TEORICO
  family?: string;
  layer?: string;
  visualization_hint?: string;
  // DATABASE_NODE
  entity_type?: string;
  is_core?: boolean;
  // DATABASE_EDGE
  relationship_type?: string;
  direction?: string;
  strength?: number;
}

interface AddMemoModalProps {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;
}

// ── Option constants ───────────────────────────────────────────────

const FAMILIES = [
  "Causes",
  "Consequences",
  "Conditions",
  "Process",
  "Degree",
  "Dimension",
  "Type",
  "Strategy",
  "Structural",
  "Functional",
  "Interaction",
  "Identity",
] as const;

const LAYERS = ["core", "intermediate", "surface"] as const;

const ENTITY_TYPES = [
  "PROCESS",
  "ACTOR",
  "CONDITION",
  "CONSEQUENCE",
  "CONTEXT",
  "STRATEGY",
] as const;

const RELATIONSHIP_TYPES = [
  "PROCESSES",
  "LEADS_TO",
  "IS_A_STRATEGY_FOR",
  "IS_A_CONSEQUENCE_OF",
  "IS_A_CONDITION_FOR",
  "VARIES_WITH",
  "CO_OCCURS_WITH",
] as const;

const DIRECTIONS = ["unidirectional", "bidirectional"] as const;

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

const INPUT: CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  background: "#0D1117",
  border: "1px solid #21262D",
  color: "#E6EDF3",
  fontSize: 13,
  boxSizing: "border-box",
};

const CHECKBOX_ROW: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  marginTop: 10,
  fontSize: 12,
  color: "#E6EDF3",
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

const SF_SECTION: CSSProperties = {
  marginTop: 8,
  padding: "10px 12px",
  borderRadius: 8,
  background: "#0D1117",
  border: "1px solid #21262D",
};

const SF_TITLE: CSSProperties = {
  fontSize: 10,
  color: "#8B949E",
  fontWeight: 600,
  textTransform: "uppercase",
  marginBottom: 6,
  letterSpacing: "0.5px",
};

// ── ColorBadge ────────────────────────────────────────────────────────

function ColorBadge(mt: MemoType) {
  const s: CSSProperties = {
    marginTop: 8,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "3px 10px",
    borderRadius: 999,
    background: mt.color + "18",
    border: "1px solid " + mt.color + "44",
    fontSize: 10,
    color: mt.color,
    fontWeight: 600,
  };
  return (
    <div style={s}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: mt.color,
        }}
      >
        {" "}
        {mt.label}
      </span>
    </div>
  );
}

function InfoBoxCategoria(t: (key: string) => string) {
  return (
    <div style={INFOBOX}>
      <strong>{t("memo.willCreate")}</strong> {t("memo.categoryInEntityTable")}
      <br />
      <strong>{t("memo.willNotCreate")}</strong>{" "}
      {t("memo.noSegmentAssignments")}
    </div>
  );
}

function InfoBoxTeorico(t: (key: string) => string) {
  return (
    <div style={INFOBOX}>
      <strong>{t("memo.willCreate")}</strong> {t("memo.customTheoreticalCode")}
      <br />
      <strong>{t("memo.willNotCreate")}</strong>{" "}
      {t("memo.noConceptualRelations")}
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

// ── Helper: build structured_fields payload, dropping empty values ──

function buildStructuredPayload(
  tipo: string,
  sd: StructuredFields,
): Record<string, unknown> | undefined {
  const result: Record<string, unknown> = {};

  if (tipo === "TEORICO") {
    if (sd.family) result.family = sd.family;
    if (sd.layer) result.layer = sd.layer;
    if (sd.visualization_hint) result.visualization_hint = sd.visualization_hint;
    return Object.keys(result).length > 0 ? result : undefined;
  }

  if (tipo === "DATABASE_NODE") {
    if (sd.entity_type) result.entity_type = sd.entity_type;
    result.is_core = sd.is_core === true; // always send boolean
    return Object.keys(result).length > 0 ? result : undefined;
  }

  if (tipo === "DATABASE_EDGE") {
    if (sd.relationship_type) result.relationship_type = sd.relationship_type;
    if (sd.direction) result.direction = sd.direction;
    if (sd.strength !== undefined) result.strength = sd.strength;
    return Object.keys(result).length > 0 ? result : undefined;
  }

  return undefined;
}

// ── Main Component ───────────────────────────────────────────────────

export default function AddMemoModal({
  projectId,
  onClose,
  onCreated,
}: AddMemoModalProps) {
  const { t } = useI18n();
  const [types, setTypes] = useState<MemoType[]>([]);
  const [selectedType, setSelectedType] = useState("");
  const [content, setContent] = useState("");
  const [isConfidential, setIsConfidential] = useState(false);
  const [stage, setStage] = useState("");
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [structuredData, setStructuredData] = useState<StructuredFields>({});

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
      .catch((e) => setError(e.message || t("memo.errorLoadingTypes")))
      .finally(() => setLoading(false));
  }, [projectId, t]);

  // Reset structured fields when type changes
  useEffect(() => {
    setStructuredData({});
  }, [selectedType]);

  const handleSubmit = async () => {
    if (!selectedType || !content.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const sf = buildStructuredPayload(selectedType, structuredData);
      await createMemo(projectId, {
        tipo: selectedType,
        contenido: content,
        es_confidencial: isConfidential,
        ...(sf && { structured_fields: sf }),
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message || t("memo.errorSaving"));
    } finally {
      setSubmitting(false);
    }
  };

  const selected = types.find((mt) => mt.key === selectedType);

  // ── Helpers to update structured fields ──
  const setField = (field: keyof StructuredFields, value: unknown) => {
    setStructuredData((prev) => ({ ...prev, [field]: value }));
  };

  if (loading) {
    return (
      <div style={OVERLAY}>
        <div style={CARD}>
          <span style={{ color: "#8B949E" }}>{t("memo.loading")}</span>
        </div>
      </div>
    );
  }

  if (pipelineRunning) {
    return (
      <div style={OVERLAY} onClick={onClose}>
        <div style={CARD} onClick={(e) => e.stopPropagation()}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>
            {t("memo.pipelineRunning")}
          </div>
          <div style={{ fontSize: 13, color: "#8B949E", lineHeight: 1.5 }}>
            {t("memo.pipelineRunningMsg")}
          </div>
          <div style={BUTTON_ROW}>
            <button
              onClick={onClose}
              style={{ ...btnBase, background: "#21262D", color: "#E6EDF3" }}
            >
              {t("memo.closeButton")}
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
          {t("memo.addMemoTitle")}
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
            {t("memo.stageLabel")}
            {stage}
          </span>
        </div>

        {/* Type selector */}
        <div style={LABEL}>{t("memo.entityType")}</div>
        <select
          style={SELECT}
          value={selectedType}
          onChange={(e) => setSelectedType(e.target.value)}
        >
          {types.map((mt) => (
            <option key={mt.key} value={mt.key}>
              {mt.icon} {mt.label}
              {mt.agent_status === "not_run" ? " ⚠️" : ""}
            </option>
          ))}
        </select>
        {selected && <div style={DESCRIPTION}>{selected.description}</div>}

        {/* Color indicator */}
        {selected && ColorBadge(selected)}

        {/* Agent not-run warning (FIX 5) */}
        {selected && selected.agent_status === "not_run" && (
          <div
            style={{
              marginTop: 12,
              padding: "8px 12px",
              borderRadius: 6,
              background: "#D2992218",
              border: "1px solid #D2992244",
              color: "#D29922",
              fontSize: 12,
              lineHeight: 1.5,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span style={{ fontSize: 16 }}>⚠️</span>
            <span>
              {t("memo.agentNotRunWarning")}
            </span>
          </div>
        )}

        {/* Content */}
        <div style={LABEL}>{t("memo.content")}</div>
        <textarea
          style={TEXTAREA}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={t("memo.contentPlaceholder")}
          rows={8}
        />

        {/* ── Structured Fields (conditional by tipo) ── */}

        {selectedType === "TEORICO" && (
          <div style={SF_SECTION}>
            <div style={SF_TITLE}>Structured Fields — Código Teórico</div>

            <div style={LABEL}>Family</div>
            <select
              style={SELECT}
              value={structuredData.family || ""}
              onChange={(e) => setField("family", e.target.value)}
            >
              <option value="">— Select family —</option>
              {FAMILIES.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>

            <div style={LABEL}>Layer</div>
            <select
              style={SELECT}
              value={structuredData.layer || ""}
              onChange={(e) => setField("layer", e.target.value)}
            >
              <option value="">— Select layer —</option>
              {LAYERS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>

            <div style={LABEL}>Visualization Hint</div>
            <input
              style={INPUT}
              type="text"
              value={structuredData.visualization_hint || ""}
              onChange={(e) => setField("visualization_hint", e.target.value)}
              placeholder="e.g. tendril, matrix, arrow_diagram"
            />
          </div>
        )}

        {selectedType === "DATABASE_NODE" && (
          <div style={SF_SECTION}>
            <div style={SF_TITLE}>Structured Fields — Database Node</div>

            <div style={LABEL}>Entity Type</div>
            <select
              style={SELECT}
              value={structuredData.entity_type || ""}
              onChange={(e) => setField("entity_type", e.target.value)}
            >
              <option value="">— Select entity type —</option>
              {ENTITY_TYPES.map((et) => (
                <option key={et} value={et}>
                  {et}
                </option>
              ))}
            </select>

            <label style={CHECKBOX_ROW}>
              <input
                type="checkbox"
                checked={structuredData.is_core === true}
                onChange={(e) => setField("is_core", e.target.checked)}
              />
              Is Core Category?
            </label>
          </div>
        )}

        {selectedType === "DATABASE_EDGE" && (
          <div style={SF_SECTION}>
            <div style={SF_TITLE}>Structured Fields — Database Edge</div>

            <div style={LABEL}>Relationship Type</div>
            <select
              style={SELECT}
              value={structuredData.relationship_type || ""}
              onChange={(e) => setField("relationship_type", e.target.value)}
            >
              <option value="">— Select relationship type —</option>
              {RELATIONSHIP_TYPES.map((rt) => (
                <option key={rt} value={rt}>
                  {rt}
                </option>
              ))}
            </select>

            <div style={LABEL}>Direction</div>
            <select
              style={SELECT}
              value={structuredData.direction || ""}
              onChange={(e) => setField("direction", e.target.value)}
            >
              <option value="">— Select direction —</option>
              {DIRECTIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>

            <div style={LABEL}>Strength</div>
            <input
              style={INPUT}
              type="number"
              min={0}
              max={1}
              step={0.1}
              value={structuredData.strength ?? ""}
              onChange={(e) => {
                const val = e.target.value === "" ? undefined : parseFloat(e.target.value);
                setField("strength", val);
              }}
              placeholder="0.0 – 1.0"
            />
          </div>
        )}

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
          {t("memo.confidential")}
        </label>

        {/* Info box */}
        {selectedType === "CATEGORIA" && InfoBoxCategoria(t)}
        {selectedType === "TEORICO" && InfoBoxTeorico(t)}

        {/* Error */}
        {error && ErrorBox(error)}

        {/* Buttons */}
        <div style={BUTTON_ROW}>
          <button
            onClick={onClose}
            style={{ ...btnBase, background: "#21262D", color: "#E6EDF3" }}
          >
            {t("memo.cancelButton")}
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
            {submitting ? t("memo.saving") : t("memo.saveButton")}
          </button>
        </div>
      </div>
    </div>
  );
}
