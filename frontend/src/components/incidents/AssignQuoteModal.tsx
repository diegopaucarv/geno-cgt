import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../i18n";
import type { IncidentPayload, UnassignedSegmentPayload } from "../../api/client";
import { GLASER_TAGS, canonicalGlaserTag, glaserColor } from "./glaser";
import {
  btnTiny,
  chipStyle,
  fieldLabel,
  modalCard,
  overlay,
  selectInput,
  textInput,
} from "./styles";
import { shorten } from "./shorten";

/** Qué está disparando el modal. */
export type AssignContext =
  /** Citas ya elegidas (desde el pool); falta decidir a qué incidente van. */
  | { kind: "segments"; segmentIds: string[] }
  /** Incidente ya elegido; falta elegir qué citas se le suman. */
  | { kind: "incident"; incidentId: string };

/** Resultado que el panel traduce a llamadas de API. */
export type AssignPayload =
  | { type: "create"; segmentIds: string[]; jot: string; tag: string | null }
  | {
      type: "attach";
      incidentId: string;
      segmentIds: string[];
      tag: string | null;
    };

interface Props {
  context: AssignContext;
  incidents: IncidentPayload[];
  pool: UnassignedSegmentPayload[];
  busy: boolean;
  onClose: () => void;
  onSubmit: (payload: AssignPayload) => void;
}

/**
 * Un solo modal para las dos direcciones del vínculo.
 *
 * - `context.kind === "segments"`: las citas son fijas; se elige entre crear un
 *   incidente nuevo o colgarlas de uno existente.
 * - `context.kind === "incident"`: el incidente es fijo; se eligen las citas
 *   del pool que se le suman.
 *
 * La categoría es opcional y, si se omite, la cita hereda la del segmento: es
 * la misma regla que aplica el backend, así que acá no se inventa un default.
 */
export function AssignQuoteModal({
  context,
  incidents,
  pool,
  busy,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useI18n();
  const fixedSegments = context.kind === "segments" ? context.segmentIds : null;
  const fixedIncident = context.kind === "incident" ? context.incidentId : null;

  const [tab, setTab] = useState<"create" | "existing">("create");
  const [picked, setPicked] = useState<Set<string>>(
    () => new Set(fixedSegments ?? []),
  );
  const [target, setTarget] = useState<string>(fixedIncident ?? "");
  const [jot, setJot] = useState("");
  const [tag, setTag] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const byId = useMemo(() => {
    const m = new Map<string, UnassignedSegmentPayload>();
    for (const s of pool) m.set(s.id, s);
    return m;
  }, [pool]);

  const chosen = useMemo(
    () => [...picked].map((id) => byId.get(id)).filter(Boolean) as UnassignedSegmentPayload[],
    [picked, byId],
  );

  const filteredIncidents = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return incidents;
    return incidents.filter((i) =>
      (i.jot_text ?? "").toLowerCase().includes(q),
    );
  }, [incidents, query]);

  const canSubmit =
    !busy &&
    picked.size > 0 &&
    (fixedIncident !== null || tab === "create" || target !== "");

  function submit() {
    if (!canSubmit) return;
    const segmentIds = [...picked];
    if (fixedIncident) {
      onSubmit({
        type: "attach",
        incidentId: fixedIncident,
        segmentIds,
        tag: tag || null,
      });
      return;
    }
    if (tab === "create") {
      onSubmit({ type: "create", segmentIds, jot: jot.trim(), tag: tag || null });
      return;
    }
    onSubmit({
      type: "attach",
      incidentId: target,
      segmentIds,
      tag: tag || null,
    });
  }

  const title = fixedIncident
    ? t("project.incidentsAssignTitleIncident")
    : t("project.incidentsAssignTitle");

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modalCard} onClick={(e) => e.stopPropagation()}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            marginBottom: 4,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
          <span style={{ flex: 1 }} />
          <button style={btnTiny} onClick={onClose}>
            {t("common.close")}
          </button>
        </div>

        {/* ── Citas elegidas ── */}
        <div style={fieldLabel}>
          {t("project.incidentsAssignQuotesLabel", {
            count: String(chosen.length),
          })}
        </div>
        <div
          style={{
            maxHeight: 140,
            overflow: "auto",
            border: "1px solid #21262D",
            borderRadius: 4,
            padding: 4,
            background: "#0D1117",
          }}
        >
          {chosen.length === 0 ? (
            <div style={{ fontSize: 11, color: "#6E7681", padding: 4 }}>
              {t("project.incidentsAssignPickEmpty")}
            </div>
          ) : (
            chosen.map((s) => (
              <div
                key={s.id}
                style={{ fontSize: 11, color: "#C9D1D9", padding: "2px 0" }}
              >
                <span style={{ color: "#484F58" }}>#{s.posicion}</span>{" "}
                <span
                  style={chipStyle(
                    glaserColor(
                      s.tipo_dato_glaser
                        ? canonicalGlaserTag(s.tipo_dato_glaser)
                        : null,
                    ),
                  )}
                >
                  {s.tipo_dato_glaser || "—"}
                </span>{" "}
                {shorten(s.texto, 160)}
                {!fixedSegments && (
                  <button
                    style={{ ...btnTiny, marginLeft: 6 }}
                    onClick={() =>
                      setPicked((prev) => {
                        const n = new Set(prev);
                        n.delete(s.id);
                        return n;
                      })
                    }
                  >
                    {t("common.delete")}
                  </button>
                )}
              </div>
            ))
          )}
        </div>

        {/* ── Elegir citas (solo cuando el incidente ya está fijado) ── */}
        {fixedIncident && (
          <>
            <div style={fieldLabel}>
              {t("project.incidentsAssignPickTitle")}
            </div>
            <input
              style={{ ...textInput, marginBottom: 4 }}
              placeholder={t("project.incidentsAssignSearch")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div
              style={{
                maxHeight: 220,
                overflow: "auto",
                border: "1px solid #21262D",
                borderRadius: 4,
                padding: 4,
              }}
            >
              {pool.length === 0 ? (
                <div style={{ fontSize: 11, color: "#6E7681" }}>
                  {t("project.incidentsAssignPickEmpty")}
                </div>
              ) : (
                pool
                  .filter((s) => {
                    const q = query.trim().toLowerCase();
                    return (
                      !q ||
                      s.texto.toLowerCase().includes(q) ||
                      String(s.posicion) === q.replace("#", "")
                    );
                  })
                  .map((s) => (
                    <label
                      key={s.id}
                      style={{
                        display: "flex",
                        gap: 6,
                        alignItems: "flex-start",
                        fontSize: 11,
                        color: "#C9D1D9",
                        padding: "2px 0",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={picked.has(s.id)}
                        onChange={() =>
                          setPicked((prev) => {
                            const n = new Set(prev);
                            if (n.has(s.id)) n.delete(s.id);
                            else n.add(s.id);
                            return n;
                          })
                        }
                        style={{ marginTop: 2 }}
                      />
                      <span style={{ color: "#484F58", minWidth: 30 }}>
                        #{s.posicion}
                      </span>
                      <span
                        style={chipStyle(
                          glaserColor(
                            s.tipo_dato_glaser
                              ? canonicalGlaserTag(s.tipo_dato_glaser)
                              : null,
                          ),
                        )}
                      >
                        {s.tipo_dato_glaser || "—"}
                      </span>
                      <span style={{ flex: 1 }}>{shorten(s.texto, 140)}</span>
                    </label>
                  ))
              )}
            </div>
          </>
        )}

        {/* ── Destino (solo cuando las citas ya están fijadas) ── */}
        {!fixedIncident && (
          <>
            <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
              <button
                style={{
                  ...btnTiny,
                  padding: "3px 10px",
                  fontSize: 11,
                  color: tab === "create" ? "#E6EDF3" : "#8B949E",
                  borderColor: tab === "create" ? "#3FB95066" : "#30363D",
                  background: tab === "create" ? "#3FB95018" : "transparent",
                }}
                onClick={() => setTab("create")}
              >
                {t("project.incidentsAssignCreateTab")}
              </button>
              <button
                style={{
                  ...btnTiny,
                  padding: "3px 10px",
                  fontSize: 11,
                  color: tab === "existing" ? "#E6EDF3" : "#8B949E",
                  borderColor: tab === "existing" ? "#58A6FF66" : "#30363D",
                  background: tab === "existing" ? "#58A6FF18" : "transparent",
                }}
                onClick={() => setTab("existing")}
              >
                {t("project.incidentsAssignExistingTab")}
              </button>
            </div>

            {tab === "create" ? (
              <>
                <label style={fieldLabel}>
                  {t("project.incidentsAssignJotLabel")}
                </label>
                <textarea
                  rows={2}
                  style={textInput}
                  value={jot}
                  placeholder={t("project.incidentsAssignJotPlaceholder")}
                  onChange={(e) => setJot(e.target.value)}
                />
              </>
            ) : (
              <>
                <label style={fieldLabel}>
                  {t("project.incidentsAssignExistingTab")}
                </label>
                {incidents.length === 0 ? (
                  <div style={{ fontSize: 11, color: "#6E7681" }}>
                    {t("project.incidentsAssignNoIncidents")}
                  </div>
                ) : (
                  <>
                    {incidents.length > 6 && (
                      <input
                        style={{ ...textInput, marginBottom: 4 }}
                        placeholder={t("project.incidentsAssignSearch")}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    )}
                    <div
                      style={{
                        maxHeight: 200,
                        overflow: "auto",
                        border: "1px solid #21262D",
                        borderRadius: 4,
                        padding: 4,
                      }}
                    >
                      {filteredIncidents.map((inc) => (
                        <label
                          key={inc.id}
                          style={{
                            display: "flex",
                            gap: 6,
                            alignItems: "flex-start",
                            fontSize: 11,
                            color: "#C9D1D9",
                            padding: "3px 0",
                            cursor: "pointer",
                            borderLeft:
                              target === inc.id
                                ? "2px solid #58A6FF"
                                : "2px solid transparent",
                            paddingLeft: 6,
                          }}
                        >
                          <input
                            type="radio"
                            name="assign-target"
                            checked={target === inc.id}
                            onChange={() => setTarget(inc.id)}
                            style={{ marginTop: 2 }}
                          />
                          <span style={{ flex: 1 }}>
                            {shorten(
                              inc.jot_text ||
                                String(
                                  (inc.preguntas_glaser_json as any)
                                    ?.what_is_this_about ?? "",
                                ) ||
                                inc.id,
                              140,
                            )}
                          </span>
                          <span style={{ color: "#6E7681", whiteSpace: "nowrap" }}>
                            {t("project.incidentsQuotes", {
                              count: String(inc.segments?.length ?? 0),
                            })}
                          </span>
                        </label>
                      ))}
                    </div>
                  </>
                )}
              </>
            )}
          </>
        )}

        {/* ── Categoría de la cita (opcional) ── */}
        <label style={fieldLabel}>
          {t("project.incidentsAssignCategoryLabel")}
        </label>
        <select
          style={selectInput}
          value={tag}
          onChange={(e) => setTag(e.target.value)}
        >
          <option value="">{t("project.incidentsAssignCategoryInherit")}</option>
          {GLASER_TAGS.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>

        {/* ── Acciones ── */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 6,
            marginTop: 14,
          }}
        >
          <button style={btnTiny} onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </button>
          <button
            style={{
              ...btnTiny,
              padding: "4px 12px",
              fontSize: 11,
              fontWeight: 600,
              color: "#0D1117",
              background: canSubmit ? "#3FB950" : "#21262D",
              borderColor: "transparent",
              cursor: canSubmit ? "pointer" : "not-allowed",
            }}
            disabled={!canSubmit}
            onClick={submit}
          >
            {fixedIncident || tab === "existing"
              ? t("project.incidentsAssignSubmitAttach")
              : t("project.incidentsAssignSubmitCreate")}
          </button>
        </div>
      </div>
    </div>
  );
}
