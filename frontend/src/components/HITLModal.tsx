import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { decideHitl, getHitlDetail } from "../api/client";
import { useI18n } from "../i18n";

interface HITLModalProps {
  open: boolean;
  projectId: string;
  gateName: string;
  onClose: () => void;
  onDecided?: (decision: "accept" | "modify" | "reject") => void;
}

const GATE_LABELS: Record<string, string> = {
  pattern_of_interest: "hitl.gatePatternOfInterest",
  pattern_convergence: "hitl.gatePatternConvergence",
  core_category: "hitl.gateCoreEmergence",
  selective_reduction: "hitl.gateSelectiveReduction",
  core_saturation: "hitl.gateCoreSaturation",
  database_a: "hitl.gateDatabaseA",
  database_b: "hitl.gateDatabaseB",
  global_saturation: "hitl.gateGlobalSaturation",
};

const VERDICT_COLORS: Record<string, string> = {
  SAT: "#3FB950",
  MOD: "#D29922",
  FORCED: "#F85149",
  AGREE: "#3FB950",
  DISAGREE: "#F85149",
  // El crítico de convergencia emite confianza, no SAT/MOD/FORCED: sin estas
  // claves el veredicto del gate de lote salía siempre gris.
  HIGH: "#3FB950",
  MEDIUM: "#D29922",
  LOW: "#F85149",
};

type TFunc = (
  key: string,
  replacements?: Record<string, string | number>,
) => string;

// ── Tokens ──────────────────────────────────────────────────────────
const labelStyle: CSSProperties = {
  color: "#8B949E",
  fontSize: 11,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};
const valueStyle: CSSProperties = { color: "#E6EDF3" };
const cardStyle: CSSProperties = {
  marginBottom: 8,
  padding: "8px 10px",
  background: "#161B22",
  borderRadius: 6,
  border: "1px solid #21262D",
};
const listStyle: CSSProperties = {
  margin: "2px 0 0 16px",
  padding: 0,
  fontSize: 12,
  color: "#C9D1D9",
  lineHeight: 1.5,
};
const sectionStyle: CSSProperties = { marginTop: 12 };

function Chip({ color, text }: { color: string; text: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "1px 8px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        background: `${color}22`,
        color,
        border: `1px solid ${color}44`,
      }}
    >
      {text}
    </span>
  );
}

function looksLikeConvergence(p: Record<string, unknown>): boolean {
  return (
    p.convergence_assessment !== undefined ||
    p.diverging !== undefined ||
    p.converging !== undefined
  );
}

/** Número finito a partir de un valor que puede venir como string o null. */
function toNum(v: unknown): number | undefined {
  if (typeof v === "number") return Number.isFinite(v) ? v : undefined;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

/** Porcentaje `0–100` ya redondeado, o `null` si el valor no es usable.
 *  `scale` = 100 para valores fraccionarios (0–1), 1 si ya viene en %. */
function pct(v: unknown, scale: 1 | 100 = 100): number | null {
  const n = toNum(v);
  if (n === undefined) return null;
  return Math.max(0, Math.min(100, Math.round(n * scale)));
}

// ── Cuerpos por gate ────────────────────────────────────────────────
// `gate_name → componente`. Antes había un único `renderProposal` con if/else
// encadenados y el gate de convergencia terminaba pintado como un concern
// vacío (el payload de F2.5 no trae `candidates`).

function ConvergenceBody({ p, t }: { p: Record<string, unknown>; t: TFunc }) {
  const converging = (p.converging as Array<Record<string, unknown>>) || [];
  const diverging = (p.diverging as Array<Record<string, unknown>>) || [];
  const assessment = (p.convergence_assessment as string) || "";
  const recommendation = (p.recommendation as string) || "";
  const suggested = (p.suggested_shared_pattern as string) || "";

  const tone = /converg/i.test(assessment)
    ? "#3FB950"
    : /diverg/i.test(assessment)
      ? "#F85149"
      : "#D29922";

  const hasAny = !!assessment || converging.length > 0 || diverging.length > 0;
  if (!hasAny) {
    return (
      <div style={{ fontSize: 12, color: "#8B949E" }}>
        {t("hitl.noConvergenceData")}
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, rowGap: 6 }}>
        {assessment && <Chip color={tone} text={assessment} />}
        {converging.length > 0 && (
          <Chip
            color="#3FB950"
            text={`${t("hitl.convergingLabel")} ${converging.length}`}
          />
        )}
        {diverging.length > 0 && (
          <Chip
            color="#F85149"
            text={`${t("hitl.divergingLabel")} ${diverging.length}`}
          />
        )}
        {recommendation && <Chip color="#58A6FF" text={recommendation} />}
      </div>

      {converging.length > 0 && (
        <div style={sectionStyle}>
          <div style={labelStyle}>{t("hitl.convergingLabel")}</div>
          <ul style={listStyle}>
            {converging.map((c, i) => (
              <li key={i} style={{ color: "#3FB950" }}>
                {(c.element as string) || JSON.stringify(c)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {diverging.length > 0 && (
        <div style={sectionStyle}>
          <div style={labelStyle}>{t("hitl.divergingLabel")}</div>
          <ul style={listStyle}>
            {diverging.map((d, i) => (
              <li key={i} style={{ color: "#F85149" }}>
                {(d.element as string) || JSON.stringify(d)}
                {!!(d.explanation as string) && (
                  <div style={{ color: "#8B949E", fontSize: 11 }}>
                    {d.explanation as string}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {suggested && (
        <div style={sectionStyle}>
          <div style={labelStyle}>{t("hitl.suggestedPatternLabel")}</div>
          <div style={{ ...valueStyle, fontStyle: "italic" }}>{suggested}</div>
        </div>
      )}
    </div>
  );
}

function PatternOfInterestBody({
  p,
  t,
}: {
  p: Record<string, unknown>;
  t: TFunc;
}) {
  // El proposer emite `candidates[]` (statement / supporting_codes / …), no un
  // `core_concern` único: leer el campo equivocado dejaba el modal vacío.
  const candidates = (p.candidates as Array<Record<string, unknown>>) || [];
  if (candidates.length === 0) {
    return (
      <div>
        <div style={{ color: "#F85149", fontSize: 13 }}>
          {t("hitl.noClearConcern")}
        </div>
        {!!p.no_concern_rationale && (
          <div style={{ fontSize: 12, color: "#8B949E", marginTop: 6 }}>
            {p.no_concern_rationale as string}
          </div>
        )}
      </div>
    );
  }
  return (
    <div>
      {candidates.map((c, i) => {
        const supporting = (c.supporting_codes as string[]) || [];
        const orphans = (c.orphan_codes as string[]) || [];
        return (
          <div key={i} style={cardStyle}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={labelStyle}>
                {t("hitl.candidateLabel")}
                {i + 1}
              </span>
              <span style={{ ...valueStyle, fontWeight: 600, fontSize: 13 }}>
                {(c.statement as string) || "—"}
              </span>
              {!!c.is_latent && (
                <Chip color="#A371F7" text={t("hitl.latentBadge")} />
              )}
            </div>
            <div style={{ marginTop: 4, fontSize: 11, color: "#8B949E" }}>
              {t("hitl.supportingCodesLabel")} {supporting.length}
              {" · "}
              {t("hitl.orphanCodesLabel")} {orphans.length}
            </div>
            {!!c.rationale && (
              <div style={{ marginTop: 4, fontSize: 12, color: "#C9D1D9" }}>
                {c.rationale as string}
              </div>
            )}
          </div>
        );
      })}
      {!!p.rationale && (
        <div
          style={{
            marginTop: 4,
            fontSize: 11,
            color: "#8B949E",
            fontStyle: "italic",
          }}
        >
          {p.rationale as string}
        </div>
      )}
    </div>
  );
}

function CoreCategoryBody({ p, t }: { p: Record<string, unknown>; t: TFunc }) {
  const candidates =
    (p.core_category_candidates as Array<Record<string, unknown>>) || [];
  return (
    <div>
      {candidates.map((c, i) => (
        <div key={i} style={cardStyle}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span style={labelStyle}>
              {t("hitl.candidateLabel")}
              {i + 1}
            </span>
            <span style={{ ...valueStyle, fontWeight: 600 }}>
              {c.category_label as string}
            </span>
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: "#C9D1D9" }}>
            {t("hitl.centrality")}
            {(c.is_central as boolean) ? "✓" : "✗"}
            {t("hitl.explanatory")}
            {(c.has_explanatory_power as boolean) ? "✓" : "✗"}
            {" · Theoretical Grab: "}
            {(c.has_theoretical_grab as boolean) ? "✓" : "✗"}
          </div>
          {!!c.centrality_rationale && (
            <div style={{ marginTop: 4, color: "#8B949E", fontSize: 11 }}>
              {c.centrality_rationale as string}
            </div>
          )}
        </div>
      ))}
      {(p.no_core_detected as boolean) && (
        <div style={{ color: "#F85149", fontSize: 13 }}>
          {t("hitl.noCoreDetected")}
        </div>
      )}
    </div>
  );
}

function SelectiveReductionBody({
  p,
  t,
}: {
  p: Record<string, unknown>;
  t: TFunc;
}) {
  const kept = (p.kept_codes as string[]) || [];
  const merged = (p.merged_codes as Array<Record<string, unknown>>) || [];
  const discarded = (p.discarded_codes as Array<Record<string, unknown>>) || [];
  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <Chip
          color="#3FB950"
          text={`✓ ${kept.length} ${t("hitl.keptBadge")}`}
        />
        <Chip
          color="#D29922"
          text={`↔ ${merged.length} ${t("hitl.mergedBadge")}`}
        />
        <Chip
          color="#F85149"
          text={`✗ ${discarded.length} ${t("hitl.discardedBadge")}`}
        />
      </div>
      {discarded.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {discarded.slice(0, 5).map((d, i) => (
            <div
              key={i}
              style={{ fontSize: 11, color: "#F85149", padding: "2px 0" }}
            >
              ✗ {d.code_name as string}:{" "}
              {(d.discard_rationale as string)?.slice(0, 90)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function GenericBody({ p }: { p: Record<string, unknown> }) {
  return (
    <pre
      style={{
        margin: 0,
        fontSize: 11,
        color: "#C9D1D9",
        whiteSpace: "pre-wrap",
        fontFamily: "monospace",
        maxHeight: 200,
        overflow: "auto",
      }}
    >
      {JSON.stringify(p, null, 2)}
    </pre>
  );
}

const GATE_BODIES: Record<
  string,
  (props: { p: Record<string, unknown>; t: TFunc }) => ReactNode
> = {
  pattern_of_interest: PatternOfInterestBody,
  pattern_convergence: ConvergenceBody,
  core_category: CoreCategoryBody,
  selective_reduction: SelectiveReductionBody,
};

export default function HITLModal({
  open,
  projectId,
  gateName,
  onClose,
  onDecided,
}: HITLModalProps) {
  const { t } = useI18n();
  const [decision, setDecision] = useState<
    "accept" | "modify" | "reject" | null
  >(null);
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [proposal, setProposal] = useState<Record<string, unknown>>({});
  const [criticVerdict, setCriticVerdict] = useState<Record<string, unknown>>(
    {},
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !projectId || !gateName) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setSubmitError(null);
    setDecision(null);
    setNote("");
    setFeedback("");
    getHitlDetail(projectId, gateName)
      .then((detail) => {
        if (cancelled) return;
        setProposal(detail.proposal || {});
        setCriticVerdict(detail.critic_verdict || {});
      })
      .catch((err) => {
        if (cancelled) return;
        setProposal({});
        setCriticVerdict({});
        setLoadError(err?.message || String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId, gateName]);

  if (!open) return null;

  // Gate de lote: la misma `pattern_convergence` que emite F2.5 cada N docs.
  // Se detecta también por forma para cubrir filas antiguas guardadas bajo
  // `pattern_of_interest`.
  const isBatchGate =
    gateName === "pattern_convergence" || looksLikeConvergence(proposal);

  const docsProcessed = toNum(proposal.docs_processed) ?? 0;
  const totalDocs = toNum(proposal.total_docs) ?? 0;
  const hasProgress = totalDocs > 0;
  // Fila antigua (o gate sin progreso inyectado): no se puede mostrar "N de
  // M" sin inventarse el total, así que se usa un texto genérico.
  const hasCounts =
    proposal.docs_processed !== undefined && proposal.total_docs !== undefined;

  const cv = criticVerdict as Record<string, unknown>;
  const verdict = (cv.verdict as string) || (cv.confidence as string) || "";
  const verdictColor = VERDICT_COLORS[verdict] || "#8B949E";
  const rationale = (cv.rationale as string) || "";
  const suggestions = (cv.suggestions as string[]) || [];
  const populationConcerns = (cv.population_concerns as string[]) || [];
  const groundingPct = pct(cv.grounding_score);
  const coveragePct = pct(cv.coverage_score);
  const abstractionPct = pct(cv.abstraction_score);
  const agreementPct = pct(cv.agreement_percentage, 1);
  const hasMetrics =
    groundingPct !== null ||
    coveragePct !== null ||
    abstractionPct !== null ||
    agreementPct !== null;

  const canSubmit =
    !!decision &&
    (decision !== "reject" || isBatchGate || !!note.trim()) &&
    !submitting;

  const handleSubmit = async (dec?: "accept" | "modify" | "reject") => {
    const finalDecision = dec ?? decision;
    if (!finalDecision || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await decideHitl(
        projectId,
        gateName,
        finalDecision,
        note,
        finalDecision === "modify" ? feedback : undefined,
      );
      onDecided?.(finalDecision);
      // `onDecided` es opcional: sin este fallback el modal se quedaba abierto
      // y bloqueado tras decidir.
      if (!onDecided) onClose();
    } catch (err: any) {
      // Sin feedback visible el usuario solo veía que "no pasaba nada".
      console.error("HITL decision failed:", err);
      setSubmitError(err?.message || String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const Body = GATE_BODIES[gateName] ?? null;
  const isConvergenceShaped = looksLikeConvergence(proposal);

  const primaryBtn = (color: string): CSSProperties => ({
    padding: "9px 18px",
    borderRadius: 6,
    border: "none",
    background: color,
    color: "#0D1117",
    fontSize: 13,
    fontWeight: 700,
    cursor: submitting ? "not-allowed" : "pointer",
    opacity: submitting ? 0.6 : 1,
  });

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.72)",
        padding: 16,
      }}
      onMouseDown={(e) => {
        // Cerrar al hacer click fuera: el gate pendiente sigue visible como
        // badge en el botón HITL, así que cerrar nunca pierde la decisión.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: "#161B22",
          borderRadius: 12,
          border: "1px solid #30363D",
          width: 680,
          maxWidth: "100%",
          maxHeight: "88vh",
          display: "flex",
          flexDirection: "column",
          color: "#E6EDF3",
          boxShadow: "0 24px 48px rgba(0,0,0,0.5)",
        }}
      >
        {/* ── Header ── */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
            padding: "16px 20px",
            borderBottom: "1px solid #21262D",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>
              {isBatchGate ? t("hitl.batchTitle") : t("hitl.title")}
            </h2>
            <div style={{ marginTop: 4, color: "#8B949E", fontSize: 12 }}>
              {t("hitl.gateLabel")}{" "}
              <strong style={{ color: "#C9D1D9" }}>
                {t(GATE_LABELS[gateName] || gateName)}
              </strong>
            </div>
          </div>
          <button
            onClick={onClose}
            title={t("hitl.closeButton")}
            aria-label={t("hitl.closeButton")}
            style={{
              flex: "0 0 auto",
              width: 30,
              height: 30,
              borderRadius: 6,
              border: "1px solid #30363D",
              background: "#21262D",
              color: "#C9D1D9",
              fontSize: 14,
              lineHeight: 1,
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* ── Body ── */}
        <div style={{ padding: "16px 20px", overflow: "auto", flex: 1 }}>
          {loading ? (
            <div
              style={{
                padding: 32,
                textAlign: "center",
                color: "#8B949E",
                fontSize: 13,
              }}
            >
              {t("hitl.loadingDetails")}
            </div>
          ) : loadError ? (
            <div style={{ color: "#F85149", fontSize: 13 }}>
              {t("hitl.failedToLoad")}: {loadError}
            </div>
          ) : (
            <>
              {/* Prompt de lote: "N de M documentos procesados. ¿Continuar?" */}
              {isBatchGate && (
                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 8,
                    background: "#D2992214",
                    border: "1px solid #D2992244",
                    marginBottom: 14,
                  }}
                >
                  <div
                    style={{ fontSize: 14, fontWeight: 600, color: "#E6EDF3" }}
                  >
                    {hasProgress
                      ? t("hitl.batchPrompt", {
                          n: docsProcessed,
                          m: totalDocs,
                        })
                      : hasCounts
                        ? t("hitl.batchPromptUnknown", { n: docsProcessed })
                        : t("hitl.batchPromptGeneric")}
                  </div>
                  {hasProgress && (
                    <div
                      style={{
                        marginTop: 10,
                        height: 6,
                        borderRadius: 999,
                        background: "#21262D",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${Math.max(
                            0,
                            Math.min(
                              100,
                              Math.round((docsProcessed / totalDocs) * 100),
                            ),
                          )}%`,
                          height: "100%",
                          background: "#D29922",
                          transition: "width 0.3s ease",
                        }}
                      />
                    </div>
                  )}
                  <div
                    style={{
                      marginTop: 10,
                      fontSize: 11,
                      color: "#8B949E",
                      lineHeight: 1.5,
                    }}
                  >
                    {t("hitl.batchHint")}
                  </div>
                </div>
              )}

              {/* Veredicto del crítico (sólo si aporta algo) */}
              {(verdict ||
                rationale ||
                suggestions.length > 0 ||
                populationConcerns.length > 0 ||
                hasMetrics) && (
                <div
                  style={{
                    padding: "12px 14px",
                    borderRadius: 8,
                    marginBottom: 14,
                    background: "#0D1117",
                    border: `1px solid ${verdictColor}55`,
                  }}
                >
                  {verdict && (
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: 13,
                        color: verdictColor,
                      }}
                    >
                      {t("hitl.criticVerdict")} {verdict}
                    </div>
                  )}
                  {rationale && (
                    <p
                      style={{
                        margin: "6px 0 0 0",
                        fontSize: 12,
                        color: "#8B949E",
                        lineHeight: 1.55,
                      }}
                    >
                      {rationale}
                    </p>
                  )}
                  {suggestions.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ ...labelStyle, color: "#D29922" }}>
                        {t("hitl.suggestions")}
                      </div>
                      <ul style={listStyle}>
                        {suggestions.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {populationConcerns.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ ...labelStyle, color: "#D29922" }}>
                        {t("hitl.populationConcerns")}
                      </div>
                      <ul style={listStyle}>
                        {populationConcerns.map((c, i) => (
                          <li key={i}>{c}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {hasMetrics && (
                    <div
                      style={{
                        marginTop: 8,
                        display: "flex",
                        gap: 16,
                        fontSize: 11,
                        color: "#8B949E",
                        flexWrap: "wrap",
                      }}
                    >
                      {groundingPct !== null && (
                        <span>
                          {t("hitl.grounding")} {groundingPct}%
                        </span>
                      )}
                      {coveragePct !== null && (
                        <span>
                          {t("hitl.coverage")} {coveragePct}%
                        </span>
                      )}
                      {abstractionPct !== null && (
                        <span>
                          {t("hitl.abstraction")} {abstractionPct}%
                        </span>
                      )}
                      {agreementPct !== null && (
                        <span>
                          {t("hitl.agreement")} {agreementPct}%
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Salida del proposer según el gate */}
              <div style={{ ...cardStyle, background: "#0D1117" }}>
                <div
                  style={{
                    ...labelStyle,
                    color: "#58A6FF",
                    marginBottom: 6,
                  }}
                >
                  {t("hitl.proposerOutput")}
                </div>
                {isConvergenceShaped ? (
                  <ConvergenceBody p={proposal} t={t} />
                ) : Body ? (
                  <Body p={proposal} t={t} />
                ) : (
                  <GenericBody p={proposal} />
                )}
              </div>
            </>
          )}
        </div>

        {/* ── Footer ── */}
        {!loading && loadError && (
          <div
            style={{
              padding: "14px 20px",
              borderTop: "1px solid #21262D",
              display: "flex",
              justifyContent: "flex-end",
            }}
          >
            <button
              onClick={onClose}
              style={{
                padding: "8px 16px",
                borderRadius: 6,
                border: "1px solid #30363D",
                background: "transparent",
                color: "#8B949E",
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              {t("hitl.closeButton")}
            </button>
          </div>
        )}
        {!loading && !loadError && (
          <div
            style={{
              padding: "14px 20px",
              borderTop: "1px solid #21262D",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {/* Nota metodológica (siempre disponible) */}
            <div>
              <div style={{ ...labelStyle, marginBottom: 4 }}>
                {t("hitl.noteLabel")}{" "}
                <span style={{ textTransform: "none", fontWeight: 400 }}>
                  {decision === "reject" && !isBatchGate
                    ? t("hitl.noteRequired")
                    : t("hitl.noteOptional")}
                </span>
              </div>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder={
                  decision === "reject" && !isBatchGate
                    ? t("hitl.rejectPlaceholder")
                    : t("hitl.notePlaceholder")
                }
                style={{
                  width: "100%",
                  padding: "8px 10px",
                  borderRadius: 6,
                  background: "#0D1117",
                  border: "1px solid #30363D",
                  color: "#E6EDF3",
                  fontSize: 12,
                  resize: "vertical",
                  fontFamily: "inherit",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Feedback extra cuando la decisión es MODIFY */}
            {decision === "modify" && (
              <div>
                <div
                  style={{ ...labelStyle, color: "#D29922", marginBottom: 4 }}
                >
                  {t("hitl.feedbackLabel")}
                </div>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={2}
                  placeholder={t("hitl.feedbackPlaceholder")}
                  style={{
                    width: "100%",
                    padding: "8px 10px",
                    borderRadius: 6,
                    background: "#0D1117",
                    border: "1px solid #D29922",
                    color: "#E6EDF3",
                    fontSize: 12,
                    resize: "vertical",
                    fontFamily: "inherit",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            )}

            {/* Acciones */}
            {submitError && (
              <div
                style={{
                  fontSize: 12,
                  color: "#F85149",
                  background: "#F8514912",
                  border: "1px solid #F8514933",
                  borderRadius: 6,
                  padding: "8px 10px",
                }}
              >
                {t("hitl.submitFailed")}: {submitError}
              </div>
            )}
            {isBatchGate ? (
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: 8,
                  flexWrap: "wrap",
                }}
              >
                <button
                  onClick={onClose}
                  style={{
                    padding: "9px 16px",
                    borderRadius: 6,
                    border: "1px solid #30363D",
                    background: "transparent",
                    color: "#8B949E",
                    fontSize: 13,
                    cursor: "pointer",
                  }}
                >
                  {t("hitl.laterButton")}
                </button>
                <button
                  onClick={() => handleSubmit("reject")}
                  disabled={submitting}
                  title={t("hitl.stopButton")}
                  style={{
                    padding: "9px 16px",
                    borderRadius: 6,
                    border: "1px solid #F85149",
                    background: "#F8514918",
                    color: "#F85149",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: submitting ? "not-allowed" : "pointer",
                    opacity: submitting ? 0.6 : 1,
                  }}
                >
                  {t("hitl.stopButton")}
                </button>
                <button
                  onClick={() => handleSubmit("accept")}
                  disabled={submitting}
                  title={t("hitl.continueButton")}
                  style={primaryBtn("#3FB950")}
                >
                  {submitting ? t("hitl.submitting") : t("hitl.continueButton")}
                </button>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 10 }}>
                  {(["accept", "modify", "reject"] as const).map((d) => (
                    <button
                      key={d}
                      onClick={() => setDecision(d)}
                      style={{
                        flex: 1,
                        padding: "9px 0",
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: 700,
                        cursor: "pointer",
                        background:
                          decision === d
                            ? d === "accept"
                              ? "#1F6FEB"
                              : d === "modify"
                                ? "#9E6A03"
                                : "#DA3633"
                            : "#21262D",
                        color: decision === d ? "#FFF" : "#8B949E",
                        border: decision === d ? "none" : "1px solid #30363D",
                      }}
                    >
                      {d === "accept"
                        ? t("hitl.acceptButton")
                        : d === "modify"
                          ? t("hitl.modifyButton")
                          : t("hitl.rejectButton")}
                    </button>
                  ))}
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    gap: 8,
                  }}
                >
                  <button
                    onClick={onClose}
                    style={{
                      padding: "8px 16px",
                      borderRadius: 6,
                      border: "1px solid #30363D",
                      background: "transparent",
                      color: "#8B949E",
                      fontSize: 13,
                      cursor: "pointer",
                    }}
                  >
                    {t("hitl.closeButton")}
                  </button>
                  <button
                    onClick={() => handleSubmit()}
                    disabled={!canSubmit}
                    style={{
                      padding: "8px 18px",
                      borderRadius: 6,
                      border: "none",
                      background: canSubmit ? "#1F6FEB" : "#21262D",
                      color: canSubmit ? "#FFF" : "#484F58",
                      fontSize: 13,
                      fontWeight: 700,
                      cursor: canSubmit ? "pointer" : "not-allowed",
                    }}
                  >
                    {submitting ? t("hitl.submitting") : t("hitl.submitButton")}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
