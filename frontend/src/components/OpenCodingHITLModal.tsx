import { useEffect, useRef, useState } from "react";
import {
  bulkDeleteHypotheses,
  createHypothesis,
  decideOpenCodingHitl,
  deleteHypothesis,
  getHypothesesByProject,
  getHypothesisDuplicates,
  getOpenCodingHitlStatus,
  updateHypothesis,
  type HypothesisDuplicatesResponse,
  type HypothesisItem,
  type OpenCodingHitlStatus,
} from "../api/client";

/**
 * HITL gate de codificación abierta.
 *
 * A diferencia de los gates del pipeline selectivo, este no espera a que un
 * worker inserte una fila en hitl_decisions: el investigador puede abrirlo en
 * cualquier momento para fijar el concern principal, la población y las
 * categorías centrales. Se alimenta de /hitl/open-coding/status, que agrega
 * los outputs de A1 (population_contexts), de B2/C (categorias) y de las
 * hipótesis.
 */

interface Props {
  open: boolean;
  projectId: string;
  onClose: () => void;
  onDecided?: (confirmed: boolean) => void;
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 11,
  fontWeight: 600,
  color: "#8B949E",
  marginBottom: 6,
  textTransform: "uppercase",
  letterSpacing: 0.4,
};

const boxStyle: React.CSSProperties = {
  background: "#0D1117",
  border: "1px solid #21262D",
  borderRadius: 6,
  padding: 10,
  marginBottom: 16,
};

const optionStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  alignItems: "flex-start",
  padding: "6px 8px",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 12,
  color: "#C9D1D9",
  lineHeight: 1.5,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "7px 10px",
  borderRadius: 6,
  background: "#0D1117",
  border: "1px solid #30363D",
  color: "#E6EDF3",
  fontSize: 12,
  boxSizing: "border-box",
  fontFamily: "inherit",
};

const hintStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#6E7681",
  fontStyle: "italic",
  marginTop: 4,
};

const buttonStyle: React.CSSProperties = {
  padding: "7px 14px",
  borderRadius: 6,
  border: "1px solid #30363D",
  background: "transparent",
  color: "#C9D1D9",
  fontSize: 12,
  cursor: "pointer",
};

const dangerButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  border: "1px solid #F8514944",
  color: "#F85149",
};

const primaryButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  border: "none",
  background: "#A371F7",
  color: "#0D1117",
  fontWeight: 600,
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  width: "auto",
  padding: "6px 8px",
};

function withDisabled(
  base: React.CSSProperties,
  disabled: boolean,
): React.CSSProperties {
  return {
    ...base,
    opacity: disabled ? 0.5 : 1,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

function badgeStyle(color: string): React.CSSProperties {
  return {
    fontSize: 9,
    padding: "1px 6px",
    borderRadius: 999,
    border: `1px solid ${color}44`,
    background: `${color}18`,
    color,
    fontWeight: 600,
    letterSpacing: 0.3,
    textTransform: "uppercase",
    whiteSpace: "nowrap",
  };
}

const STATUS_COLOR: Record<string, string> = {
  candidate: "#58A6FF",
  accepted: "#3FB950",
  rejected: "#F85149",
  split: "#D29922",
};

const LEVELS: string[] = ["general", "specific", "emergent"];

/**
 * Pre-selección de borrado: todo lo que no esté marcado como «conservar»
 * queda tildado, de modo que el investigador solo confirma lo obvio.
 */
function defaultDupSelection(
  dups: HypothesisDuplicatesResponse | null,
): Set<string> {
  const next = new Set<string>();
  for (const cluster of dups?.clusters ?? []) {
    for (const item of cluster.items) {
      if (!item.is_suggested_keep) next.add(item.id);
    }
  }
  return next;
}

/**
 * Resuelve los ids realmente borrables y protege los grupos: si el usuario
 * tildó todas las filas de un grupo se conserva una (la sugerida o la de
 * mayor confianza) para no vaciarlo.
 */
function computeDupPlan(
  dups: HypothesisDuplicatesResponse | null,
  selection: Set<string>,
): { ids: string[]; keptBack: number } {
  const ids = new Set(selection);
  let keptBack = 0;
  for (const cluster of dups?.clusters ?? []) {
    if (cluster.items.length === 0) continue;
    if (!cluster.items.every((item) => ids.has(item.id))) continue;
    const keep =
      cluster.items.find((item) => item.is_suggested_keep) ??
      cluster.items.reduce(
        (best, item) => (item.confidence > best.confidence ? item : best),
        cluster.items[0],
      );
    ids.delete(keep.id);
    keptBack += 1;
  }
  return { ids: [...ids], keptBack };
}

export default function OpenCodingHITLModal({
  open,
  projectId,
  onClose,
  onDecided,
}: Props) {
  const [status, setStatus] = useState<OpenCodingHitlStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [concern, setConcern] = useState("");
  const [population, setPopulation] = useState("");
  const [coreIds, setCoreIds] = useState<Set<string>>(new Set());
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState<"save" | "confirm" | null>(null);
  const [hyps, setHyps] = useState<HypothesisItem[]>([]);
  const [dups, setDups] = useState<HypothesisDuplicatesResponse | null>(null);
  const [showDups, setShowDups] = useState(false);
  const [dupSelection, setDupSelection] = useState<Set<string>>(new Set());
  const [dupDeleting, setDupDeleting] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [editLevel, setEditLevel] = useState("general");
  const [editSaving, setEditSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // Selección múltiple de la lista general (distinta de la de duplicados).
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newText, setNewText] = useState("");
  const [newLevel, setNewLevel] = useState("general");
  const [creating, setCreating] = useState(false);

  // Confirmación dentro de la app: los diálogos nativos (window.confirm) se
  // pueden bloquear desde el navegador y entonces todas las acciones devolvían
  // "cancelar" en silencio.
  const [confirmReq, setConfirmReq] = useState<{
    message: string;
    confirmLabel: string;
    danger: boolean;
  } | null>(null);
  const confirmResolveRef = useRef<((ok: boolean) => void) | null>(null);

  function askConfirm(
    message: string,
    opts: { confirmLabel?: string; danger?: boolean } = {},
  ): Promise<boolean> {
    return new Promise((resolve) => {
      confirmResolveRef.current = resolve;
      setConfirmReq({
        message,
        confirmLabel: opts.confirmLabel ?? "Confirmar",
        danger: opts.danger ?? true,
      });
    });
  }

  function resolveConfirm(ok: boolean) {
    setConfirmReq(null);
    confirmResolveRef.current?.(ok);
    confirmResolveRef.current = null;
  }

  useEffect(() => {
    if (!open || !projectId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setEditId(null);
    setShowCreate(false);
    setNewText("");
    setSelected(new Set());
    // Si quedó una confirmación pendiente de una apertura anterior, se anula.
    setConfirmReq(null);
    confirmResolveRef.current?.(false);
    confirmResolveRef.current = null;
    Promise.all([
      getOpenCodingHitlStatus(projectId),
      getHypothesesByProject(projectId),
      getHypothesisDuplicates(projectId, 0.8),
    ])
      .then(([s, hypList, dupResponse]) => {
        if (cancelled) return;
        setStatus(s);
        setConcern(s.chosen_concern ?? s.concern_candidates[0]?.label ?? "");
        setPopulation(
          s.chosen_population ?? s.population_proposals[0]?.description ?? "",
        );
        setCoreIds(
          new Set(
            s.unified_categories
              .filter((c) => c.is_core_candidate)
              .map((c) => c.id),
          ),
        );
        setHyps(hypList.items);
        setDups(dupResponse);
        setDupSelection(defaultDupSelection(dupResponse));
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(
            e instanceof Error ? e.message : "No se pudo cargar el gate HITL",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId]);

  const ready = concern.trim().length > 0 && population.trim().length > 0;
  const alreadyDecided = Boolean(status?.chosen_concern);
  const dupPlan = computeDupPlan(dups, dupSelection);

  // Solo cuentan los ids que siguen existiendo tras editar/borrar/recargar.
  const selectedIds = hyps.filter((h) => selected.has(h.id)).map((h) => h.id);
  const allSelected = hyps.length > 0 && selectedIds.length === hyps.length;

  async function submit(confirmed: boolean) {
    if (!ready || submitting) return;
    if (confirmed) {
      const ok = await askConfirm(
        alreadyDecided
          ? "Se guardará una nueva decisión y se re-disparará la codificación selectiva. ¿Continuar?"
          : "Confirmar dispara la generalización de población y la codificación selectiva. ¿Continuar?",
        { confirmLabel: "Confirmar y avanzar" },
      );
      if (!ok) return;
    }
    setSubmitting(confirmed ? "confirm" : "save");
    setError(null);
    try {
      await decideOpenCodingHitl(projectId, {
        chosen_concern: concern.trim(),
        chosen_population: population.trim(),
        core_category_ids: [...coreIds],
        confirmed,
        researcher_note: note.trim(),
      });
      onDecided?.(confirmed);
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "No se pudo guardar la decisión",
      );
    } finally {
      setSubmitting(null);
    }
  }

  function toggleCore(categoryId: string) {
    setCoreIds((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  }

  function toggleSelected(hypothesisId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(hypothesisId)) next.delete(hypothesisId);
      else next.add(hypothesisId);
      return next;
    });
  }

  function toggleDup(hypothesisId: string) {
    setDupSelection((prev) => {
      const next = new Set(prev);
      if (next.has(hypothesisId)) next.delete(hypothesisId);
      else next.add(hypothesisId);
      return next;
    });
  }

  async function reloadDups(): Promise<void> {
    try {
      const response = await getHypothesisDuplicates(projectId, 0.8);
      setDups(response);
      setDupSelection(defaultDupSelection(response));
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "No se pudieron revisar los duplicados",
      );
    }
  }

  async function reloadAll(): Promise<void> {
    try {
      const [hypList, dupResponse] = await Promise.all([
        getHypothesesByProject(projectId),
        getHypothesisDuplicates(projectId, 0.8),
      ]);
      setHyps(hypList.items);
      setDups(dupResponse);
      setDupSelection(defaultDupSelection(dupResponse));
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "No se pudieron recargar las hipótesis",
      );
    }
  }

  function startEdit(hypothesis: HypothesisItem) {
    setEditId(hypothesis.id);
    setEditText(hypothesis.text);
    setEditLevel(hypothesis.level || "general");
  }

  async function saveEdit(hypothesis: HypothesisItem): Promise<void> {
    const text = editText.trim();
    if (editSaving || text.length < 10) return;
    if (text === hypothesis.text && editLevel === hypothesis.level) return;
    setEditSaving(true);
    setError(null);
    try {
      const updated = await updateHypothesis(hypothesis.id, {
        text,
        level: editLevel,
      });
      setHyps((prev) =>
        prev.map((item) => (item.id === hypothesis.id ? updated : item)),
      );
      setEditId(null);
      await reloadDups();
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "No se pudo actualizar la hipótesis",
      );
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDelete(hypothesis: HypothesisItem): Promise<void> {
    if (deletingId || editSaving) return;
    if (
      !(await askConfirm(
        "¿Borrar esta hipótesis? Esta acción no se puede deshacer.",
        { confirmLabel: "Borrar" },
      ))
    )
      return;
    setDeletingId(hypothesis.id);
    setError(null);
    try {
      await deleteHypothesis(hypothesis.id);
      setHyps((prev) => prev.filter((item) => item.id !== hypothesis.id));
      if (editId === hypothesis.id) setEditId(null);
      await reloadDups();
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "No se pudo borrar la hipótesis",
      );
    } finally {
      setDeletingId(null);
    }
  }

  async function handleCreate(): Promise<void> {
    const text = newText.trim();
    if (creating || text.length < 10) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createHypothesis({
        project_id: projectId,
        text,
        level: newLevel,
      });
      setHyps((prev) => [...prev, created]);
      setNewText("");
      setShowCreate(false);
      await reloadDups();
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "No se pudo crear la hipótesis",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleBulkDelete(): Promise<void> {
    if (dupDeleting) return;
    const { ids, keptBack } = dupPlan;
    if (ids.length === 0) return;
    const keepNote =
      keptBack > 0
        ? ` Se conservará 1 hipótesis en ${keptBack} grupo(s) para no vaciarlo(s).`
        : "";
    if (
      !(await askConfirm(
        `Se borrarán ${ids.length} hipótesis duplicadas. Esta acción no se puede deshacer.${keepNote}`,
        { confirmLabel: `Borrar ${ids.length}` },
      ))
    )
      return;
    setDupDeleting(true);
    setError(null);
    try {
      await bulkDeleteHypotheses(ids);
      await reloadAll();
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "No se pudieron borrar las hipótesis duplicadas",
      );
    } finally {
      setDupDeleting(false);
    }
  }

  async function handleBulkDeleteSelected(): Promise<void> {
    if (bulkDeleting || dupDeleting) return;
    if (selectedIds.length === 0) return;
    if (
      !(await askConfirm(
        `Se borrarán ${selectedIds.length} hipótesis. Esta acción no se puede deshacer.`,
        { confirmLabel: `Borrar ${selectedIds.length}` },
      ))
    )
      return;
    setBulkDeleting(true);
    setError(null);
    try {
      await bulkDeleteHypotheses(selectedIds);
      const gone = new Set(selectedIds);
      setHyps((prev) => prev.filter((item) => !gone.has(item.id)));
      if (editId && gone.has(editId)) setEditId(null);
      setSelected(new Set());
      await reloadDups();
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "No se pudieron borrar las hipótesis",
      );
    } finally {
      setBulkDeleting(false);
    }
  }

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.7)",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#161B22",
          borderRadius: 12,
          border: "1px solid #30363D",
          width: 720,
          maxHeight: "88vh",
          overflow: "auto",
          padding: 24,
          color: "#E6EDF3",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: 4,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18 }}>
            Decisión HITL · Codificación abierta
          </h2>
          <button
            onClick={onClose}
            aria-label="Cerrar"
            style={{
              background: "none",
              border: "none",
              color: "#8B949E",
              fontSize: 18,
              cursor: "pointer",
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        </div>
        <p style={{ margin: "0 0 16px 0", color: "#8B949E", fontSize: 12 }}>
          Fija el concern principal, la población y las categorías centrales
          antes de pasar a codificación selectiva.
          {status && (
            <>
              {" "}
              · {status.docs_processed}/{status.total_docs} documentos · lote{" "}
              {status.batch_number}
            </>
          )}
        </p>

        {error && (
          <div
            style={{
              padding: "8px 10px",
              marginBottom: 12,
              borderRadius: 6,
              background: "#F8514918",
              border: "1px solid #F8514944",
              color: "#F85149",
              fontSize: 12,
            }}
          >
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ padding: 32, textAlign: "center" }}>
            <span className="spinner" style={{ width: 20, height: 20 }} />
          </div>
        ) : (
          <>
            {/* ── Población ── */}
            <label style={labelStyle}>Población</label>
            <div style={boxStyle}>
              {status?.population_proposals.length ? (
                status.population_proposals.map((p, i) => (
                  <label
                    key={i}
                    style={{
                      ...optionStyle,
                      background:
                        population === p.description
                          ? "#A371F718"
                          : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name="oc-population"
                      checked={population === p.description}
                      onChange={() => setPopulation(p.description)}
                      style={{ marginTop: 2 }}
                    />
                    <span
                      style={{
                        maxHeight: 96,
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {p.description}
                    </span>
                  </label>
                ))
              ) : (
                <div style={hintStyle}>
                  Aún no hay propuesta de población (se genera en el contexto
                  poblacional, agente A1). Escribe una a mano.
                </div>
              )}
              <textarea
                value={population}
                onChange={(e) => setPopulation(e.target.value)}
                rows={3}
                placeholder="Población del estudio…"
                style={{ ...inputStyle, marginTop: 8, resize: "vertical" }}
              />
            </div>

            {/* ── Concern principal ── */}
            <label style={labelStyle}>Concern principal</label>
            <div style={boxStyle}>
              {status?.concern_candidates.length ? (
                status.concern_candidates.map((c) => (
                  <label
                    key={c.label}
                    style={{
                      ...optionStyle,
                      background:
                        concern === c.label ? "#A371F718" : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name="oc-concern"
                      checked={concern === c.label}
                      onChange={() => setConcern(c.label)}
                      style={{ marginTop: 2 }}
                    />
                    <span>
                      <strong>{c.label}</strong>
                      {c.supporting_codes.length > 0 && (
                        <span style={{ color: "#6E7681" }}>
                          {" "}
                          · {c.supporting_codes.length} códigos
                        </span>
                      )}
                      {c.rationale && (
                        <span
                          style={{
                            display: "block",
                            color: "#8B949E",
                            fontSize: 11,
                          }}
                        >
                          {c.rationale}
                        </span>
                      )}
                    </span>
                  </label>
                ))
              ) : (
                <div style={hintStyle}>
                  Aún no hay candidatos de concern (los propone el agente C tras
                  la codificación). Escribe uno a mano.
                </div>
              )}
              <input
                value={concern}
                onChange={(e) => setConcern(e.target.value)}
                placeholder="Concern principal en gerundio, p. ej. “gestionando la incertidumbre”"
                style={{ ...inputStyle, marginTop: 8 }}
              />
            </div>

            {/* ── Categorías centrales ── */}
            <label style={labelStyle}>
              Categorías centrales ({coreIds.size} seleccionadas)
            </label>
            <div style={boxStyle}>
              {status?.unified_categories.length ? (
                status.unified_categories.map((c) => (
                  <label key={c.id} style={optionStyle}>
                    <input
                      type="checkbox"
                      checked={coreIds.has(c.id)}
                      onChange={() => toggleCore(c.id)}
                      style={{ marginTop: 2 }}
                    />
                    <span>
                      <strong>{c.label}</strong>
                      {c.definition && (
                        <span
                          style={{
                            display: "block",
                            color: "#8B949E",
                            fontSize: 11,
                          }}
                        >
                          {c.definition}
                        </span>
                      )}
                    </span>
                  </label>
                ))
              ) : (
                <div style={hintStyle}>
                  Aún no hay categorías en el proyecto.
                </div>
              )}
            </div>

            {/* ── Hipótesis (CRUD + duplicados) ── */}
            <label style={labelStyle}>Hipótesis ({hyps.length})</label>
            <div style={boxStyle}>
              {dups && dups.redundant_count > 0 && (
                <div
                  style={{
                    background: "#D2992218",
                    border: "1px solid #D2992244",
                    borderRadius: 6,
                    padding: "8px 10px",
                    marginBottom: 10,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: "#D29922",
                      }}
                    >
                      ⚠ {dups.redundant_count} hipótesis parecen duplicadas
                    </span>
                    <button
                      onClick={() => setShowDups((v) => !v)}
                      style={buttonStyle}
                    >
                      {showDups ? "Ocultar duplicados" : "Revisar duplicados"}
                    </button>
                  </div>
                  <div style={{ fontSize: 11, color: "#8B949E", marginTop: 4 }}>
                    Hay {dups.clusters.length} grupo(s) con texto casi idéntico.
                    Revisá y borrá las sobrantes antes de confirmar.
                  </div>

                  {showDups && (
                    <div style={{ marginTop: 10 }}>
                      {dups.clusters.map((cluster) => (
                        <div
                          key={cluster.cluster_id}
                          style={{
                            background: "#0D1117",
                            border: "1px solid #21262D",
                            borderRadius: 6,
                            padding: "6px 8px",
                            marginBottom: 8,
                          }}
                        >
                          <div
                            style={{
                              fontSize: 10,
                              fontWeight: 600,
                              color: "#8B949E",
                              textTransform: "uppercase",
                              letterSpacing: 0.4,
                              marginBottom: 4,
                            }}
                          >
                            Grupo {cluster.cluster_id} · {cluster.size}{" "}
                            hipótesis
                          </div>
                          {cluster.items.map((item) => (
                            <label key={item.id} style={optionStyle}>
                              <input
                                type="checkbox"
                                checked={dupSelection.has(item.id)}
                                onChange={() => toggleDup(item.id)}
                                style={{ marginTop: 2 }}
                              />
                              <span style={{ flex: 1, minWidth: 0 }}>
                                <span
                                  style={{
                                    display: "flex",
                                    gap: 6,
                                    alignItems: "center",
                                    flexWrap: "wrap",
                                    marginBottom: 2,
                                  }}
                                >
                                  <span style={badgeStyle("#58A6FF")}>
                                    {(item.similarity * 100).toFixed(0)}%
                                  </span>
                                  <span
                                    style={badgeStyle(
                                      STATUS_COLOR[item.status] ?? "#8B949E",
                                    )}
                                  >
                                    {item.status}
                                  </span>
                                  {item.is_suggested_keep && (
                                    <span style={badgeStyle("#3FB950")}>
                                      conservar
                                    </span>
                                  )}
                                </span>
                                <span
                                  style={{
                                    display: "block",
                                    maxHeight: 64,
                                    overflow: "auto",
                                    whiteSpace: "pre-wrap",
                                  }}
                                >
                                  {item.text}
                                </span>
                              </span>
                            </label>
                          ))}
                        </div>
                      ))}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                        }}
                      >
                        <button
                          onClick={() => void handleBulkDelete()}
                          disabled={dupDeleting || dupPlan.ids.length === 0}
                          style={withDisabled(
                            dangerButtonStyle,
                            dupDeleting || dupPlan.ids.length === 0,
                          )}
                        >
                          {dupDeleting
                            ? "Borrando…"
                            : `Borrar seleccionadas (${dupPlan.ids.length})`}
                        </button>
                        {dupDeleting && (
                          <span
                            className="spinner"
                            style={{ width: 14, height: 14 }}
                          />
                        )}
                      </div>
                      {dupPlan.keptBack > 0 && (
                        <div style={hintStyle}>
                          Se conservará automáticamente 1 hipótesis en{" "}
                          {dupPlan.keptBack} grupo(s) para no vaciarlo(s).
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {hyps.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: "wrap",
                    paddingBottom: 8,
                    marginBottom: 2,
                    borderBottom: "1px solid #21262D",
                  }}
                >
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      fontSize: 12,
                      color: "#C9D1D9",
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={() =>
                        setSelected(
                          allSelected
                            ? new Set()
                            : new Set(hyps.map((h) => h.id)),
                        )
                      }
                      style={{ marginTop: 1 }}
                    />
                    {selectedIds.length > 0
                      ? `${selectedIds.length} seleccionadas`
                      : "Seleccionar todas"}
                  </label>
                  {selectedIds.length > 0 && (
                    <button
                      onClick={() => setSelected(new Set())}
                      disabled={bulkDeleting}
                      style={withDisabled(buttonStyle, bulkDeleting)}
                    >
                      Quitar selección
                    </button>
                  )}
                  <button
                    onClick={() => void handleBulkDeleteSelected()}
                    disabled={selectedIds.length === 0 || bulkDeleting}
                    style={withDisabled(
                      dangerButtonStyle,
                      selectedIds.length === 0 || bulkDeleting,
                    )}
                  >
                    {bulkDeleting
                      ? "Borrando…"
                      : `Borrar seleccionadas (${selectedIds.length})`}
                  </button>
                  {bulkDeleting && (
                    <span
                      className="spinner"
                      style={{ width: 14, height: 14 }}
                    />
                  )}
                </div>
              )}

              {hyps.length === 0 ? (
                <div style={hintStyle}>
                  Aún no hay hipótesis en este proyecto. Podés añadir una abajo.
                </div>
              ) : (
                hyps.map((h) => {
                  const dimmed =
                    h.status === "rejected" || h.status === "split";
                  const isEditing = editId === h.id;
                  return (
                    <div
                      key={h.id}
                      style={{
                        borderTop: "1px solid #21262D",
                        padding: "8px 0",
                        opacity: dimmed ? 0.55 : 1,
                      }}
                    >
                      {isEditing ? (
                        <>
                          <textarea
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            rows={3}
                            style={{ ...inputStyle, resize: "vertical" }}
                          />
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                              marginTop: 6,
                            }}
                          >
                            <select
                              value={editLevel}
                              onChange={(e) => setEditLevel(e.target.value)}
                              style={selectStyle}
                            >
                              {(LEVELS.includes(editLevel)
                                ? LEVELS
                                : [editLevel, ...LEVELS]
                              ).map((level) => (
                                <option
                                  key={level}
                                  value={level}
                                  style={{
                                    background: "#0D1117",
                                    color: "#E6EDF3",
                                  }}
                                >
                                  {level}
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={() => void saveEdit(h)}
                              disabled={
                                editSaving ||
                                editText.trim().length < 10 ||
                                (editText.trim() === h.text &&
                                  editLevel === h.level)
                              }
                              style={withDisabled(
                                primaryButtonStyle,
                                editSaving ||
                                  editText.trim().length < 10 ||
                                  (editText.trim() === h.text &&
                                    editLevel === h.level),
                              )}
                            >
                              Guardar
                            </button>
                            <button
                              onClick={() => setEditId(null)}
                              disabled={editSaving}
                              style={withDisabled(buttonStyle, editSaving)}
                            >
                              Cancelar
                            </button>
                            {editSaving && (
                              <span
                                className="spinner"
                                style={{ width: 14, height: 14 }}
                              />
                            )}
                          </div>
                          {editText.trim().length < 10 && (
                            <div style={hintStyle}>
                              La hipótesis necesita al menos 10 caracteres.
                            </div>
                          )}
                        </>
                      ) : (
                        <>
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              flexWrap: "wrap",
                              marginBottom: 4,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={selected.has(h.id)}
                              onChange={() => toggleSelected(h.id)}
                              title="Seleccionar para acciones en lote"
                              aria-label={`Seleccionar hipótesis ${h.id}`}
                              style={{ marginRight: 2 }}
                            />
                            <span
                              style={badgeStyle(
                                STATUS_COLOR[h.status] ?? "#8B949E",
                              )}
                            >
                              {h.status}
                            </span>
                            <span style={badgeStyle("#A371F7")}>{h.level}</span>
                            <span style={{ fontSize: 10, color: "#6E7681" }}>
                              conf. {(h.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div
                            style={{
                              fontSize: 12,
                              color: "#C9D1D9",
                              whiteSpace: "pre-wrap",
                              maxHeight: 96,
                              overflow: "auto",
                            }}
                          >
                            {h.text}
                          </div>
                          <div
                            style={{ display: "flex", gap: 8, marginTop: 6 }}
                          >
                            <button
                              onClick={() => startEdit(h)}
                              disabled={editId !== null || deletingId !== null}
                              style={withDisabled(
                                buttonStyle,
                                editId !== null || deletingId !== null,
                              )}
                            >
                              Editar
                            </button>
                            <button
                              onClick={() => void handleDelete(h)}
                              disabled={deletingId !== null || editSaving}
                              style={withDisabled(
                                dangerButtonStyle,
                                deletingId !== null || editSaving,
                              )}
                            >
                              {deletingId === h.id ? "Borrando…" : "Borrar"}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  );
                })
              )}

              <div
                style={{
                  borderTop: "1px solid #21262D",
                  marginTop: 8,
                  paddingTop: 8,
                }}
              >
                {!showCreate ? (
                  <button
                    onClick={() => setShowCreate(true)}
                    disabled={editId !== null || creating}
                    style={withDisabled(
                      buttonStyle,
                      editId !== null || creating,
                    )}
                  >
                    ＋ Añadir hipótesis
                  </button>
                ) : (
                  <>
                    <textarea
                      value={newText}
                      onChange={(e) => setNewText(e.target.value)}
                      rows={3}
                      placeholder="Nueva hipótesis…"
                      style={{ ...inputStyle, resize: "vertical" }}
                    />
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginTop: 6,
                      }}
                    >
                      <select
                        value={newLevel}
                        onChange={(e) => setNewLevel(e.target.value)}
                        style={selectStyle}
                      >
                        {LEVELS.map((level) => (
                          <option
                            key={level}
                            value={level}
                            style={{ background: "#0D1117", color: "#E6EDF3" }}
                          >
                            {level}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => void handleCreate()}
                        disabled={creating || newText.trim().length < 10}
                        style={withDisabled(
                          primaryButtonStyle,
                          creating || newText.trim().length < 10,
                        )}
                      >
                        Crear
                      </button>
                      <button
                        onClick={() => {
                          setShowCreate(false);
                          setNewText("");
                        }}
                        disabled={creating}
                        style={withDisabled(buttonStyle, creating)}
                      >
                        Cancelar
                      </button>
                      {creating && (
                        <span
                          className="spinner"
                          style={{ width: 14, height: 14 }}
                        />
                      )}
                    </div>
                    <div style={hintStyle}>
                      Mínimo 10 caracteres. Se añade a la lista de hipótesis del
                      proyecto.
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* ── Nota metodológica ── */}
            <label style={labelStyle}>Nota metodológica (opcional)</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Por qué se elige este concern / esta población…"
              style={{ ...inputStyle, marginBottom: 16, resize: "vertical" }}
            />
          </>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            paddingTop: 12,
            borderTop: "1px solid #21262D",
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: "7px 14px",
              borderRadius: 6,
              border: "1px solid #30363D",
              background: "transparent",
              color: "#C9D1D9",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Cancelar
          </button>
          <button
            onClick={() => submit(false)}
            disabled={!ready || submitting !== null}
            style={{
              padding: "7px 14px",
              borderRadius: 6,
              border: "1px solid #30363D",
              background: "#1C2333",
              color: "#E6EDF3",
              fontSize: 12,
              cursor: !ready || submitting ? "not-allowed" : "pointer",
              opacity: !ready || submitting ? 0.5 : 1,
            }}
          >
            {submitting === "save" ? "Guardando…" : "Guardar sin confirmar"}
          </button>
          <button
            onClick={() => submit(true)}
            disabled={!ready || submitting !== null}
            style={{
              padding: "7px 14px",
              borderRadius: 6,
              border: "none",
              background: "#A371F7",
              color: "#0D1117",
              fontSize: 12,
              fontWeight: 600,
              cursor: !ready || submitting ? "not-allowed" : "pointer",
              opacity: !ready || submitting ? 0.5 : 1,
            }}
          >
            {submitting === "confirm" ? "Confirmando…" : "Confirmar y avanzar"}
          </button>
        </div>
      </div>

      {confirmReq && (
        <div
          onClick={(e) => {
            e.stopPropagation();
            resolveConfirm(false);
          }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0,0,0,0.6)",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            role="alertdialog"
            aria-modal="true"
            style={{
              background: "#161B22",
              border: "1px solid #30363D",
              borderRadius: 10,
              padding: 20,
              width: 420,
              maxWidth: "92vw",
              boxShadow: "0 12px 32px rgba(0,0,0,0.5)",
            }}
          >
            <div
              style={{
                fontSize: 13,
                color: "#E6EDF3",
                lineHeight: 1.5,
                marginBottom: 16,
                whiteSpace: "pre-wrap",
              }}
            >
              {confirmReq.message}
            </div>
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              <button onClick={() => resolveConfirm(false)} style={buttonStyle}>
                Cancelar
              </button>
              <button
                onClick={() => resolveConfirm(true)}
                autoFocus
                style={
                  confirmReq.danger ? dangerButtonStyle : primaryButtonStyle
                }
              >
                {confirmReq.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
