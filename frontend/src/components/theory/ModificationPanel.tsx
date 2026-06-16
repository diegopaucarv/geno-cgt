import { useState } from "react";

// ── API ──────────────────────────────────────────────────────────

async function requestModification(
  projectId: string,
  agentId: string,
  userRequest: string,
  currentMemo: any,
  memoId: string,
  originalPrompt?: string,
) {
  const token = localStorage.getItem("access_token");
  const res = await fetch(
    `/api/v1/projects/${projectId}/modification/request`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        agent_id: agentId,
        user_request: userRequest,
        current_memo: currentMemo,
        memo_id: memoId,
        original_prompt: originalPrompt || "",
      }),
    },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function applyModification(
  projectId: string,
  agentId: string,
  memoId: string,
  newContent: any,
  userRequest: string,
  recommended: boolean | null,
  currentMemo: any,
  evidenceCollected: any[],
  verificationPlan: any,
) {
  const token = localStorage.getItem("access_token");
  const res = await fetch(`/api/v1/projects/${projectId}/modification/apply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      agent_id: agentId,
      memo_id: memoId,
      new_content: newContent,
      user_request: userRequest,
      recommended,
      current_memo: currentMemo,
      evidence_collected: evidenceCollected,
      verification_plan: verificationPlan,
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Types ─────────────────────────────────────────────────────────

type Phase =
  | "idle"
  | "filtering"
  | "planning"
  | "executing"
  | "evaluating"
  | "done"
  | "applying"
  | "applied"
  | "error";

interface ModificationState {
  phase: Phase;
  userRequest: string;
  // Response fields
  validRequest: boolean | null;
  filterReason: string;
  suggestedQuestions: string[];
  recommended: boolean | null;
  recommendationReason: string;
  recommendationConfidence: number;
  evidenceSufficient: boolean;
  modifiedMemo: any;
  impactSummary: string;
  missingEvidence: string;
  wipedTables: string[];
  pipelineRestartedFrom: string;
  error: string | null;
}

// ── Props ─────────────────────────────────────────────────────────

interface Props {
  projectId: string;
  agentId: string;
  currentMemo: any;
  memoId: string;
  originalPrompt?: string;
  /** Etiqueta del agente, ej: "Código CGT (B2b)" */
  agentLabel?: string;
  /** Familia del agente, para el placeholder */
  agentFamily?: string;
}

// ── Component ─────────────────────────────────────────────────────

export default function ModificationPanel({
  projectId,
  agentId,
  currentMemo,
  memoId,
  originalPrompt,
  agentLabel = "Memo",
  agentFamily = "inductive_data",
}: Props) {
  const [state, setState] = useState<ModificationState>({
    phase: "idle",
    userRequest: "",
    validRequest: null,
    filterReason: "",
    suggestedQuestions: [],
    recommended: null,
    recommendationReason: "",
    recommendationConfidence: 0,
    evidenceSufficient: false,
    modifiedMemo: null,
    impactSummary: "",
    missingEvidence: "",
    wipedTables: [],
    pipelineRestartedFrom: "",
    error: null,
  });

  const handleSubmit = async () => {
    if (!state.userRequest.trim()) return;

    setState((s) => ({ ...s, phase: "filtering", error: null }));
    try {
      const result = await requestModification(
        projectId,
        agentId,
        state.userRequest,
        currentMemo,
        memoId,
        originalPrompt,
      );

      setState((s) => ({
        ...s,
        phase: "done",
        validRequest: result.valid_request,
        filterReason: result.filter_reason,
        suggestedQuestions: result.suggested_questions || [],
        recommended: result.recommended,
        recommendationReason: result.recommendation_reason,
        recommendationConfidence: result.recommendation_confidence,
        evidenceSufficient: result.evidence_sufficient,
        modifiedMemo: result.modified_memo,
        impactSummary: result.impact_summary,
        missingEvidence: result.missing_evidence,
      }));
    } catch (e: any) {
      setState((s) => ({ ...s, phase: "error", error: e.message }));
    }
  };

  const handleApply = async () => {
    setState((s) => ({ ...s, phase: "applying" }));
    try {
      await applyModification(
        projectId,
        agentId,
        memoId,
        state.modifiedMemo || currentMemo,
        state.userRequest,
        state.recommended,
        currentMemo,
        [],
        null,
      );
      setState((s) => ({
        ...s,
        phase: "applied",
        wipedTables: s.wipedTables,
        pipelineRestartedFrom: s.pipelineRestartedFrom,
      }));
    } catch (e: any) {
      setState((s) => ({ ...s, phase: "error", error: e.message }));
    }
  };

  const handleReset = () => {
    setState({
      phase: "idle",
      userRequest: "",
      validRequest: null,
      filterReason: "",
      suggestedQuestions: [],
      recommended: null,
      recommendationReason: "",
      recommendationConfidence: 0,
      evidenceSufficient: false,
      modifiedMemo: null,
      impactSummary: "",
      missingEvidence: "",
      wipedTables: [],
      pipelineRestartedFrom: "",
      error: null,
    });
  };

  const placeholder = getPlaceholder(agentFamily);

  return (
    <div style={panel}>
      {/* Header */}
      <div style={section}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={title}>{agentLabel}</span>
          {state.phase === "done" && state.recommended !== null && (
            <span
              style={{
                ...badge,
                background: state.recommended ? "#3FB95022" : "#F8514922",
                color: state.recommended ? "#3FB950" : "#F85149",
              }}
            >
              {state.recommended ? "✓ RECOMENDADO" : "✗ NO RECOMENDADO"}
            </span>
          )}
        </div>
      </div>

      {/* Idle / Input */}
      {(state.phase === "idle" || state.phase === "error") && (
        <>
          <div style={section}>
            <div style={label}>Solicitar modificación</div>
            <p style={hint}>{placeholder}</p>
            <textarea
              style={textarea}
              placeholder={placeholder}
              value={state.userRequest}
              onChange={(e) =>
                setState((s) => ({ ...s, userRequest: e.target.value }))
              }
              rows={3}
            />
          </div>

          {state.error && (
            <div style={{ ...section, background: "#F8514911" }}>
              <span style={{ color: "#F85149", fontSize: 12 }}>
                {state.error}
              </span>
            </div>
          )}

          <div style={actions}>
            <button
              style={{ ...btn, opacity: state.userRequest.trim() ? 1 : 0.4 }}
              onClick={handleSubmit}
              disabled={!state.userRequest.trim()}
            >
              Verificar modificación
            </button>
          </div>
        </>
      )}

      {/* Loading */}
      {["filtering", "planning", "executing", "evaluating"].includes(
        state.phase,
      ) && (
        <div style={section}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={spinner} />
            <span style={{ color: "#8B949E", fontSize: 13 }}>
              {state.phase === "filtering" && "Analizando pedido..."}
              {state.phase === "planning" && "Planificando verificación..."}
              {state.phase === "executing" && "Buscando evidencia..."}
              {state.phase === "evaluating" && "Evaluando resultado..."}
            </span>
          </div>
        </div>
      )}

      {/* Invalid request */}
      {state.phase === "done" && state.validRequest === false && (
        <>
          <div style={section}>
            <div style={{ color: "#D29922", fontSize: 13, lineHeight: 1.5 }}>
              {state.filterReason}
            </div>
          </div>
          {state.suggestedQuestions.length > 0 && (
            <div style={section}>
              <div style={label}>Preguntas que este agente sí acepta</div>
              <ul style={questionList}>
                {state.suggestedQuestions.map((q, i) => (
                  <li key={i} style={questionItem}>
                    {q}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div style={actions}>
            <button style={btnSecondary} onClick={handleReset}>
              Nueva consulta
            </button>
          </div>
        </>
      )}

      {/* Result */}
      {state.phase === "done" && state.validRequest === true && (
        <>
          {/* Recommendation reason */}
          <div
            style={{
              ...section,
              borderLeft: `3px solid ${state.recommended ? "#3FB950" : state.recommended === false ? "#F85149" : "#484F58"}`,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 500,
                color: state.recommended
                  ? "#3FB950"
                  : state.recommended === false
                    ? "#F85149"
                    : "#8B949E",
                marginBottom: 6,
              }}
            >
              {state.recommended === true && "Modificación recomendada"}
              {state.recommended === false && "Modificación no recomendada"}
              {state.recommended === null && "Información insuficiente"}
            </div>
            <p
              style={{
                fontSize: 13,
                color: "#8B949E",
                margin: 0,
                lineHeight: 1.5,
              }}
            >
              {state.recommendationReason}
            </p>
            {state.recommendationConfidence > 0 && (
              <div style={{ marginTop: 8 }}>
                <div
                  style={{ fontSize: 11, color: "#484F58", marginBottom: 4 }}
                >
                  Confianza: {Math.round(state.recommendationConfidence * 100)}%
                </div>
                <div style={progressBar}>
                  <div
                    style={{
                      ...progressFill,
                      width: `${state.recommendationConfidence * 100}%`,
                      background:
                        state.recommendationConfidence > 0.7
                          ? "#3FB950"
                          : state.recommendationConfidence > 0.4
                            ? "#D29922"
                            : "#F85149",
                    }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Modified memo preview */}
          {state.modifiedMemo && (
            <div style={section}>
              <div style={label}>
                {state.recommended
                  ? "Versión propuesta"
                  : "Versión original (sin cambios)"}
              </div>
              <div style={memoPreview}>{formatMemo(state.modifiedMemo)}</div>
            </div>
          )}

          {/* Impact */}
          {state.impactSummary && (
            <div style={{ ...section, background: "#D2992211" }}>
              <div style={{ fontSize: 11, color: "#D29922", marginBottom: 4 }}>
                ⚠ Impacto en el sistema
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: "#8B949E",
                  margin: 0,
                  lineHeight: 1.4,
                }}
              >
                {state.impactSummary}
              </p>
            </div>
          )}

          {/* Missing evidence */}
          {!state.evidenceSufficient && state.missingEvidence && (
            <div style={{ ...section, background: "#484F5822" }}>
              <div style={{ fontSize: 11, color: "#484F58", marginBottom: 4 }}>
                Información insuficiente
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: "#8B949E",
                  margin: 0,
                  lineHeight: 1.4,
                }}
              >
                {state.missingEvidence}
              </p>
            </div>
          )}

          {/* Actions */}
          <div style={actions}>
            <button style={btnSecondary} onClick={handleReset}>
              Nueva consulta
            </button>
            {state.evidenceSufficient && (
              <button
                style={{
                  ...btn,
                  background: state.recommended ? "#238636" : "#21262D",
                  border: state.recommended
                    ? "1px solid #238636"
                    : "1px solid #30363D",
                }}
                onClick={handleApply}
              >
                {state.recommended
                  ? "Aplicar modificación"
                  : "Aplicar de todos modos"}
              </button>
            )}
          </div>
        </>
      )}

      {/* Applied confirmation */}
      {state.phase === "applied" && (
        <>
          <div style={{ ...section, background: "#3FB95011" }}>
            <div
              style={{
                fontSize: 13,
                color: "#3FB950",
                fontWeight: 500,
                marginBottom: 4,
              }}
            >
              ✓ Modificación aplicada
            </div>
            {state.wipedTables.length > 0 && (
              <p style={{ fontSize: 12, color: "#8B949E", margin: "4px 0 0" }}>
                Tablas reiniciadas: {state.wipedTables.join(", ")}
              </p>
            )}
            {state.pipelineRestartedFrom && (
              <p style={{ fontSize: 12, color: "#8B949E", margin: "2px 0 0" }}>
                Pipeline reiniciado desde: {state.pipelineRestartedFrom}
              </p>
            )}
          </div>
          <div style={actions}>
            <button style={btnSecondary} onClick={handleReset}>
              Nueva consulta
            </button>
          </div>
        </>
      )}

      {/* Applying spinner */}
      {state.phase === "applying" && (
        <div style={section}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={spinner} />
            <span style={{ color: "#8B949E", fontSize: 13 }}>
              Aplicando cambios...
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────

function getPlaceholder(family: string): string {
  const examples: Record<string, string> = {
    inductive_data:
      "Ej: \"Creo que el gerundio debería ser 'Desafiando límites' en vez de 'Negociando límites'\"",
    inductive_concepts:
      "Ej: \"Esta hipótesis debería relacionar también el código 'Evadiendo control'\"",
    descriptive_data:
      'Ej: "El proceso identificado es más sobre adaptación que sobre negociación"',
    evaluative:
      'Ej: "El critic marcó MOD pero creo que debería ser SAT porque los indicadores coinciden"',
    structural:
      'Ej: "Esta relación debería ser bidireccional, no unidireccional"',
    elaborative:
      'Ej: "Este incidente no expande la categoría, es una variante ya cubierta"',
  };
  return examples[family] || "Describí qué modificarías del memo y por qué...";
}

function formatMemo(memo: any): React.ReactNode {
  if (!memo) return <span style={{ color: "#484F58" }}>—</span>;

  // If it has a name + definition (category output)
  if (memo.code_name || memo.nombre) {
    return (
      <div>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "#E6EDF3",
            marginBottom: 4,
          }}
        >
          {memo.code_name || memo.nombre}
        </div>
        <div style={{ fontSize: 12, color: "#8B949E", lineHeight: 1.5 }}>
          {memo.definition || memo.definicion || memo.text || ""}
        </div>
      </div>
    );
  }

  // If it has text (hypothesis output)
  if (memo.text) {
    return (
      <div>
        <div style={{ fontSize: 12, color: "#8B949E", lineHeight: 1.5 }}>
          {memo.text}
        </div>
        {memo.level && (
          <span
            style={{
              ...badge,
              display: "inline-block",
              marginTop: 6,
              background: "#45B7D122",
              color: "#45B7D1",
            }}
          >
            {memo.level}
          </span>
        )}
      </div>
    );
  }

  // Fallback: JSON
  return (
    <pre
      style={{
        fontSize: 11,
        color: "#8B949E",
        margin: 0,
        whiteSpace: "pre-wrap",
        fontFamily: "monospace",
      }}
    >
      {JSON.stringify(memo, null, 2)}
    </pre>
  );
}

// ── Styles ────────────────────────────────────────────────────────

const panel: React.CSSProperties = {
  background: "#161B22",
  borderRadius: 8,
  border: "1px solid #21262D",
  overflow: "hidden",
};

const section: React.CSSProperties = {
  padding: "12px 16px",
  borderBottom: "1px solid #21262D",
};

const actions: React.CSSProperties = {
  padding: "12px 16px",
  display: "flex",
  gap: 8,
  justifyContent: "flex-end",
};

const title: React.CSSProperties = {
  fontWeight: 600,
  fontSize: 14,
  color: "#E6EDF3",
};

const label: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  color: "#8B949E",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  marginBottom: 6,
};

const hint: React.CSSProperties = {
  fontSize: 12,
  color: "#484F58",
  margin: "0 0 8px",
  lineHeight: 1.4,
  fontStyle: "italic",
};

const badge: React.CSSProperties = {
  padding: "2px 10px",
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 500,
};

const textarea: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  background: "#0D1117",
  border: "1px solid #21262D",
  borderRadius: 6,
  color: "#E6EDF3",
  fontSize: 13,
  padding: "8px 10px",
  resize: "vertical",
  fontFamily: "inherit",
  outline: "none",
  lineHeight: 1.5,
};

const memoPreview: React.CSSProperties = {
  background: "#0D1117",
  border: "1px solid #21262D",
  borderRadius: 6,
  padding: "10px 12px",
  marginTop: 4,
};

const btn: React.CSSProperties = {
  padding: "6px 14px",
  borderRadius: 6,
  border: "1px solid #21262D",
  background: "#1C2333",
  color: "#E6EDF3",
  fontSize: 12,
  cursor: "pointer",
};

const btnSecondary: React.CSSProperties = {
  ...btn,
  background: "#21262D",
};

const progressBar: React.CSSProperties = {
  height: 4,
  background: "#21262D",
  borderRadius: 2,
};

const progressFill: React.CSSProperties = {
  height: "100%",
  borderRadius: 2,
  transition: "width 0.5s",
};

const questionList: React.CSSProperties = {
  margin: "4px 0 0",
  paddingLeft: 16,
  listStyle: "none",
};

const questionItem: React.CSSProperties = {
  fontSize: 12,
  color: "#58A6FF",
  lineHeight: 1.6,
  cursor: "pointer",
  padding: "2px 0",
};

const spinner: React.CSSProperties = {
  display: "inline-block",
  width: 14,
  height: 14,
  border: "2px solid #21262D",
  borderTop: "2px solid #58A6FF",
  borderRadius: "50%",
  animation: "spin 0.8s linear infinite",
};
