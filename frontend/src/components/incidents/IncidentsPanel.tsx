import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useI18n } from "../../i18n";
import {
  type IncidentPayload,
  type IncidentMutationResult,
  type IncidentsPayload,
  type UnassignedPayload,
  type UnassignedSegmentPayload,
  attachIncidentSegments,
  createIncident,
  deleteIncident,
  detachIncidentSegment,
  listDocumentIncidents,
  listUnassignedSegments,
  patchIncident,
  patchIncidentSegment,
} from "../../api/client";
import { AssignQuoteModal, type AssignContext } from "./AssignQuoteModal";
import { canonicalGlaserTag, glaserColor } from "./glaser";
import { shorten } from "./shorten";
import { btnTiny, chipStyle, panelCard } from "./styles";

/** `btnTiny` no distingue el estado deshabilitado: un botón muerto se ve igual
 *  que uno vivo y el click se pierde sin explicación. */
const dim: CSSProperties = { opacity: 0.4, cursor: "not-allowed" };

interface Props {
  documentId: string;
  /** Cualquier cambio aquí dispara una recarga (estado del doc, conteos). */
  reloadToken?: string;
  /** Falso mientras el pipeline trabaja: se muestra en modo lectura. */
  canEdit: boolean;
  /** `runStep` de la página, para el botón del estado vacío. */
  onRunExtraction?: () => void;
  /** Lleva el visor al paso `classified`, que es donde vive la categoría real. */
  onEditClassification?: () => void;
  /** Avisa a la página de que los incidentes cambiaron. */
  onChanged?: () => void;
}

/**
 * Panel de incidentes extraídos, con curación manual.
 *
 * `incident_segmentos` (vía `GET .../incidents`) es la única fuente de verdad:
 * este componente no deriva citas de `segment_refs` ni del orden de los
 * segmentos. El pool "sin asignar" también viene del backend, porque es una
 * consulta negativa (`NOT EXISTS`) y duplicarla en el cliente garantiza que se
 * desincronice justo cuando importa.
 */
export default function IncidentsPanel({
  documentId,
  reloadToken,
  canEdit,
  onRunExtraction,
  onEditClassification,
  onChanged,
}: Props) {
  const { t } = useI18n();
  const [data, setData] = useState<IncidentsPayload | null>(null);
  const [pool, setPool] = useState<UnassignedPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  /** Etiqueta de la mutación en vuelo; bloquea la UI mientras dura. */
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [assign, setAssign] = useState<AssignContext | null>(null);
  const [jotFor, setJotFor] = useState<string | null>(null);
  const [jotDraft, setJotDraft] = useState("");
  const [confirmFor, setConfirmFor] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [inc, un] = await Promise.all([
        listDocumentIncidents(documentId),
        listUnassignedSegments(documentId),
      ]);
      setData(inc);
      setPool(un);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  const incidents = data?.incidents ?? [];
  const poolSegments = pool?.segments ?? [];
  const poolBaseline = useMemo(
    () => poolSegments.filter((s) => s.tipo_dato_glaser === "baseline_data"),
    [poolSegments],
  );
  const poolExcluded = useMemo(
    () => poolSegments.filter((s) => s.tipo_dato_glaser !== "baseline_data"),
    [poolSegments],
  );
  const assignedCount = pool
    ? Math.max(0, pool.counts.total - pool.counts.unassigned)
    : 0;

  /** Aplica una mutación y escribe el payload devuelto en el estado.
   *  Devuelve si salió bien, para no cerrar un editor cuando falló. */
  async function mutate(
    label: string,
    fn: () => Promise<IncidentMutationResult>,
    onOk?: (res: any) => void,
  ): Promise<boolean> {
    if (!canEdit || busy) return false;
    setBusy(label);
    setError("");
    try {
      const res = await fn();
      setData({
        incidents: res.incidents,
        prime_mover: res.prime_mover,
        prime_mover_confidence: res.prime_mover_confidence,
      });
      onOk?.(res);
      // El pool es derivado en el backend: hay que releerlo.
      const fresh = await listUnassignedSegments(documentId).catch(() => null);
      if (fresh) setPool(fresh);
      setSelected(new Set());
      onChanged?.();
      return true;
    } catch (e: any) {
      setError(e?.message || t("project.incidentsMutationFailed"));
      return false;
    } finally {
      setBusy(null);
    }
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submitAssign(
    payload:
      | {
          type: "create";
          segmentIds: string[];
          jot: string;
          tag: string | null;
        }
      | {
          type: "attach";
          incidentId: string;
          segmentIds: string[];
          tag: string | null;
        },
  ) {
    if (payload.type === "create") {
      const created = await createIncident(documentId, {
        segmentos: payload.segmentIds.map((id) => ({
          segmento_id: id,
          tipo_dato_glaser: payload.tag,
        })),
        jot_text: payload.jot || null,
      });
      return created;
    }
    return attachIncidentSegments(payload.incidentId, {
      segmentos: payload.segmentIds.map((id) => ({
        segmento_id: id,
        tipo_dato_glaser: payload.tag,
      })),
      mode: "add",
    });
  }

  if (loading && !data) {
    return <div style={panelCard}>{t("common.loading")}</div>;
  }

  const locked = !canEdit;

  return (
    <div
      style={panelCard}
      onClick={(e) => e.stopPropagation()}
      data-testid="incidents-panel"
    >
      {/* ── Cabecera ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
          marginBottom: 6,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: "#D29922" }}>
          {t("project.incidentsHeading")} ({incidents.length})
        </span>
        <span style={{ fontSize: 11, color: "#6E7681" }}>
          {t("project.incidentsCoverage", {
            assigned: String(assignedCount),
            total: String(pool?.counts.total ?? 0),
          })}
        </span>
        {data?.prime_mover && (
          <span style={{ fontSize: 11, color: "#6E7681" }}>
            {t("project.incidentsPrimeMover", {
              value: data.prime_mover,
              confidence: data.prime_mover_confidence ?? "—",
            })}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {onEditClassification && (
          <button
            style={{ ...btnTiny, fontSize: 9 }}
            onClick={onEditClassification}
            title={t("project.incidentsEditClassificationTitle")}
          >
            {t("project.incidentsEditClassification")}
          </button>
        )}
        <button
          style={btnTiny}
          onClick={() => void load()}
          disabled={busy !== null}
          title={t("project.incidentsReload")}
        >
          {"\u21BB"}
        </button>
      </div>

      {locked && (
        <div style={{ fontSize: 11, color: "#D29922", marginBottom: 6 }}>
          {t("project.incidentsLockedByRun")}
        </div>
      )}
      {error && (
        <div
          style={{
            fontSize: 11,
            color: "#F85149",
            background: "#F8514912",
            border: "1px solid #F8514933",
            borderRadius: 4,
            padding: "4px 6px",
            marginBottom: 6,
          }}
        >
          {error}
        </div>
      )}

      {/* ── Incidentes ── */}
      {incidents.length === 0 ? (
        <>
          <div style={{ fontSize: 12, color: "#6E7681" }}>
            {t("project.incidentsEmpty")}
          </div>
          {/* Un estado terminal sin incidentes deja inalcanzable el botón del
              paso vacío: este es el único camino de vuelta al extractor. */}
          {canEdit && onRunExtraction && (
            <button
              onClick={onRunExtraction}
              title={t("project.incidentsRun")}
              style={{
                ...btnTiny,
                marginTop: 8,
                padding: "3px 10px",
                fontSize: 11,
                background: "#D2992222",
                color: "#D29922",
                border: "1px solid #D2992255",
              }}
            >
              {"\u25B6 "}
              {t("project.incidentsRun")}
            </button>
          )}
        </>
      ) : (
        incidents.map((inc, i) => (
          <IncidentCard
            key={inc.id}
            index={i + 1}
            incident={inc}
            busy={busy}
            locked={locked}
            jotOpen={jotFor === inc.id}
            jotDraft={jotDraft}
            confirmOpen={confirmFor === inc.id}
            onStartJot={() => {
              setJotFor(inc.id);
              setJotDraft(inc.jot_text ?? "");
            }}
            onJotChange={setJotDraft}
            onCancelJot={() => setJotFor(null)}
            onSaveJot={async () => {
              const ok = await mutate(`jot:${inc.id}`, () =>
                patchIncident(inc.id, { jot_text: jotDraft.trim() }),
              );
              if (ok) setJotFor(null);
            }}
            onAddQuote={() =>
              setAssign({ kind: "incident", incidentId: inc.id })
            }
            onAskDelete={() => setConfirmFor(inc.id)}
            onCancelDelete={() => setConfirmFor(null)}
            onDelete={() => {
              setConfirmFor(null);
              void mutate(`delete:${inc.id}`, () => deleteIncident(inc.id));
            }}
            onRetag={(segmentId, tag) =>
              void mutate(`tag:${inc.id}:${segmentId}`, () =>
                patchIncidentSegment(inc.id, segmentId, {
                  tipo_dato_glaser: tag,
                }),
              )
            }
            onUnlink={(segmentId) =>
              void mutate(`unlink:${inc.id}:${segmentId}`, () =>
                detachIncidentSegment(inc.id, segmentId),
              )
            }
          />
        ))
      )}

      {/* ── Pool de citas sin asignar ── */}
      <div
        style={{
          marginTop: 14,
          paddingTop: 8,
          borderTop: "1px solid #21262D",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            marginBottom: 4,
          }}
        >
          <span style={{ fontSize: 11, fontWeight: 600, color: "#8B949E" }}>
            {t("project.incidentsUnassignedHeading", {
              count: String(poolSegments.length),
            })}
          </span>
          {selected.size > 0 && (
            <>
              <button
                style={{
                  ...btnTiny,
                  color: "#3FB950",
                  borderColor: "#3FB95055",
                }}
                disabled={locked || busy !== null}
                onClick={() =>
                  setAssign({ kind: "segments", segmentIds: [...selected] })
                }
              >
                {t("project.incidentsAssignSelected", {
                  count: String(selected.size),
                })}
              </button>
              <button style={btnTiny} onClick={() => setSelected(new Set())}>
                {t("project.incidentsClearSelection")}
              </button>
            </>
          )}
        </div>

        {poolSegments.length === 0 ? (
          <div style={{ fontSize: 11, color: "#6E7681" }}>
            {t("project.incidentsUnassignedEmpty")}
          </div>
        ) : (
          <>
            <PoolGroup
              heading={t("project.incidentsUnassignedBaseline")}
              items={poolBaseline}
              selected={selected}
              locked={locked || busy !== null}
              onToggle={toggleSelected}
              onAssign={(id) =>
                setAssign({ kind: "segments", segmentIds: [id] })
              }
            />
            <PoolGroup
              heading={t("project.incidentsUnassignedExcluded")}
              items={poolExcluded}
              selected={selected}
              locked={locked || busy !== null}
              onToggle={toggleSelected}
              onAssign={(id) =>
                setAssign({ kind: "segments", segmentIds: [id] })
              }
            />
          </>
        )}
      </div>

      {assign && (
        <AssignQuoteModal
          context={assign}
          incidents={incidents}
          pool={poolSegments}
          busy={busy !== null}
          onClose={() => setAssign(null)}
          onSubmit={async (payload) => {
            const ok = await mutate("assign", () => submitAssign(payload));
            if (ok) setAssign(null);
          }}
        />
      )}
    </div>
  );
}

// ── Sub-componentes ──────────────────────────────────────────────────

function PoolGroup({
  heading,
  items,
  selected,
  locked,
  onToggle,
  onAssign,
}: {
  heading: string;
  items: UnassignedSegmentPayload[];
  selected: Set<string>;
  locked: boolean;
  onToggle: (id: string) => void;
  onAssign: (id: string) => void;
}) {
  const { t } = useI18n();
  if (items.length === 0) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ fontSize: 10, color: "#6E7681", marginBottom: 2 }}>
        {heading} ({items.length})
      </div>
      {items.map((s) => {
        const tag = s.tipo_dato_glaser
          ? canonicalGlaserTag(s.tipo_dato_glaser)
          : null;
        const color = glaserColor(tag);
        return (
          <div
            key={s.id}
            style={{
              display: "flex",
              gap: 6,
              alignItems: "flex-start",
              fontSize: 11,
              color: "#8B949E",
              padding: "3px 0",
            }}
          >
            <input
              type="checkbox"
              checked={selected.has(s.id)}
              disabled={locked}
              onChange={() => onToggle(s.id)}
              style={{ marginTop: 2 }}
            />
            <span style={{ color: "#484F58", minWidth: 34 }}>
              #{s.posicion}
            </span>
            <span style={chipStyle(color)}>{tag || "—"}</span>
            <span style={{ flex: 1 }}>{shorten(s.texto)}</span>
            <button
              style={btnTiny}
              disabled={locked}
              onClick={() => onAssign(s.id)}
              title={t("project.incidentsAssign")}
            >
              {t("project.incidentsAssign")}
            </button>
          </div>
        );
      })}
    </div>
  );
}

function IncidentCard({
  index,
  incident,
  busy,
  locked,
  jotOpen,
  jotDraft,
  confirmOpen,
  onStartJot,
  onJotChange,
  onCancelJot,
  onSaveJot,
  onAddQuote,
  onAskDelete,
  onCancelDelete,
  onDelete,
  onRetag,
  onUnlink,
}: {
  index: number;
  incident: IncidentPayload;
  busy: string | null;
  locked: boolean;
  jotOpen: boolean;
  jotDraft: string;
  confirmOpen: boolean;
  onStartJot: () => void;
  onJotChange: (v: string) => void;
  onCancelJot: () => void;
  onSaveJot: () => void;
  onAddQuote: () => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
  onRetag: (segmentId: string, tag: string | null) => void;
  onUnlink: (segmentId: string) => void;
}) {
  const { t } = useI18n();
  const answers = (incident.preguntas_glaser_json ?? {}) as Record<string, any>;
  const title = incident.jot_text || answers.what_is_this_about || `#${index}`;
  const quotes = incident.segments ?? [];
  const isBusy = busy !== null;
  const off = locked || isBusy ? dim : {};

  // El panel del documento es el que scrollea (`panelCard`), no la página: el
  // "¿seguro?" se dibuja junto al título, así que al pedirlo desde la última
  // cita del final de la tarjeta queda fuera de vista y parece que el click no
  // hizo nada. `nearest` sólo mueve si de verdad está oculto, así que el botón
  // ✕ de la cabecera no provoca ningún salto.
  const confirmRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!confirmOpen) return;
    confirmRef.current?.scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: "smooth",
    });
  }, [confirmOpen]);

  return (
    <div
      style={{
        marginBottom: 10,
        paddingBottom: 8,
        borderBottom: "1px solid #21262D",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 6,
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: 2,
        }}
      >
        <span style={{ fontSize: 10, color: "#484F58" }}>{index}.</span>
        {incident.mixto && (
          <span style={chipStyle("#A371F7")}>
            {t("project.incidentsMixed")}
          </span>
        )}
        {incident.origen === "manual" && (
          <span style={chipStyle("#D29922")}>
            {t("project.incidentsManual")}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {!jotOpen && !confirmOpen && (
          <>
            <button
              style={btnTiny}
              disabled={locked || isBusy}
              onClick={onStartJot}
              title={t("project.incidentsEditJot")}
            >
              {"\u270E"}
            </button>
            <button
              style={btnTiny}
              disabled={locked || isBusy}
              onClick={onAddQuote}
              title={t("project.incidentsAddQuote")}
            >
              {"+ "}
              {t("project.incidentsAddQuote")}
            </button>
            <button
              style={{ ...btnTiny, color: "#F85149", borderColor: "#F8514955" }}
              disabled={locked || isBusy}
              onClick={onAskDelete}
              title={t("project.incidentsDeleteOne")}
            >
              {"\u2715"}
            </button>
          </>
        )}
      </div>

      {confirmOpen ? (
        <div
          ref={confirmRef}
          style={{
            background: "#F8514912",
            border: "1px solid #F8514933",
            borderRadius: 4,
            padding: 6,
            margin: "4px 0",
            fontSize: 11,
            color: "#E6EDF3",
          }}
        >
          <div style={{ marginBottom: 6 }}>
            {t("project.incidentsDeleteOneConfirm")}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              style={{ ...btnTiny, color: "#F85149", borderColor: "#F8514955" }}
              onClick={onDelete}
            >
              {t("common.confirm")}
            </button>
            <button style={btnTiny} onClick={onCancelDelete}>
              {t("common.cancel")}
            </button>
          </div>
        </div>
      ) : jotOpen ? (
        <div style={{ margin: "4px 0" }}>
          <textarea
            value={jotDraft}
            onChange={(e) => onJotChange(e.target.value)}
            rows={2}
            placeholder={t("project.incidentsJotPlaceholder")}
            style={{
              width: "100%",
              boxSizing: "border-box",
              background: "#0D1117",
              color: "#E6EDF3",
              border: "1px solid #30363D",
              borderRadius: 4,
              fontSize: 12,
              padding: 5,
              resize: "vertical",
              fontFamily: "inherit",
            }}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <button
              style={btnTiny}
              disabled={isBusy || !jotDraft.trim()}
              onClick={onSaveJot}
            >
              {t("common.save")}
            </button>
            <button style={btnTiny} onClick={onCancelJot}>
              {t("common.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ color: "#E6EDF3", fontSize: 12 }}>{title}</div>
      )}

      {answers.what_is_happening && !jotOpen && (
        <div style={{ fontSize: 11, color: "#8B949E", marginTop: 1 }}>
          {answers.what_is_happening}
        </div>
      )}

      {/* Citas: cada una con su propia categoría */}
      <div style={{ marginTop: 4 }}>
        <div style={{ fontSize: 10, color: "#6E7681", marginBottom: 2 }}>
          {t("project.incidentsQuotes", { count: String(quotes.length) })}
        </div>
        {quotes.length === 0 && (
          <div style={{ fontSize: 11, color: "#F85149" }}>
            {t("project.incidentsNoQuotes")}
          </div>
        )}
        {quotes.map((q) => {
          const tag = q.categoria ? canonicalGlaserTag(q.categoria) : null;
          const color = glaserColor(tag);
          const lastOne = quotes.length === 1;
          return (
            <div
              key={q.segmento_id}
              style={{
                display: "flex",
                gap: 6,
                alignItems: "flex-start",
                fontSize: 11,
                padding: "3px 0",
                borderLeft: `2px solid ${color}66`,
                paddingLeft: 6,
                marginBottom: 2,
              }}
            >
              <span style={{ color: "#484F58", minWidth: 30 }}>
                #{q.posicion}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: "#C9D1D9" }}>{shorten(q.texto, 260)}</div>
                <div
                  style={{
                    display: "flex",
                    gap: 4,
                    alignItems: "center",
                    marginTop: 2,
                    flexWrap: "wrap",
                  }}
                >
                  {tag ? (
                    <span
                      style={chipStyle(color)}
                      title={t("project.incidentsRetagHint")}
                    >
                      {tag}
                    </span>
                  ) : (
                    <span
                      style={chipStyle("#8B949E")}
                      title={t("project.incidentsRetagHint")}
                    >
                      {t("project.stepSegmentsUnclassified")}
                    </span>
                  )}
                  {/* La categoría del texto se edita en `clasificado`: acá solo
                      se anota o se deshace la anotación de ESTA cita. */}
                  {q.categoria_origen === "segment" ? (
                    <span style={{ fontSize: 9, color: "#484F58" }}>
                      {t("project.incidentsInheritedTag")}
                    </span>
                  ) : (
                    <button
                      style={{
                        ...btnTiny,
                        fontSize: 9,
                        padding: "0 4px",
                        ...off,
                      }}
                      disabled={locked || isBusy}
                      onClick={() => onRetag(q.segmento_id, null)}
                      title={t("project.incidentsRevertOverride")}
                    >
                      {"\u21BA "}
                      {t("project.incidentsOverrideTag")}
                    </button>
                  )}
                  {q.primario && (
                    <span style={{ fontSize: 9, color: "#3FB950" }}>
                      {t("project.incidentsPrimaryTag")}
                    </span>
                  )}
                  <span style={{ flex: 1 }} />
                  {/* La última cita no se puede desvincular: en su lugar se
                      ofrece la única acción válida entonces (borrar el
                      incidente, que devuelve la cita al pool). */}
                  {lastOne ? (
                    <button
                      style={{
                        ...btnTiny,
                        fontSize: 9,
                        padding: "0 4px",
                        color: "#F85149",
                        borderColor: "#F8514955",
                        ...off,
                      }}
                      disabled={locked || isBusy}
                      onClick={onAskDelete}
                      title={t("project.incidentsLastQuoteHint")}
                    >
                      {t("project.incidentsDeleteOne")}
                    </button>
                  ) : (
                    <button
                      style={{
                        ...btnTiny,
                        fontSize: 9,
                        padding: "0 4px",
                        ...off,
                      }}
                      disabled={locked || isBusy}
                      onClick={() => onUnlink(q.segmento_id)}
                      title={t("project.incidentsRemoveQuote")}
                    >
                      {t("project.incidentsRemoveQuote")}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
