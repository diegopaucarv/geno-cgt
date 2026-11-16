import { useEffect, useState } from "react";
import { useI18n } from "../../i18n";
import { deleteDocumentSegment, type Segment } from "../../api/client";
import { canonicalGlaserTag, glaserColor } from "../incidents/glaser";
import { panelCard } from "../incidents/styles";

/**
 * Visor del paso **segmentado**, con borrado por segmento.
 *
 * Regla (la misma que aplica el backend): borrar un segmento lo **fusiona** con
 * el siguiente cuando comparten categoría; si no, desaparece. La fusión es la
 * operación útil para el investigador —limpia el corte sin perder texto— y el
 * botón lo dice antes de que haga click, así nadie borra evidencia pensando que
 * fusiona.
 *
 * El servidor devuelve la lista ya recomputada (posiciones recompactadas), así
 * que se reemplaza la caché del padre con esa respuesta en vez de releer.
 */

interface Props {
  documentId: string;
  segments: Segment[];
  /** false mientras el documento tiene un paso en vuelo. */
  canEdit: boolean;
  onChanged: (segments: Segment[]) => void;
  onError: (message: string) => void;
  onNotify: (message: string) => void;
}

export default function SegmentsMergeList({
  documentId,
  segments,
  canEdit,
  onChanged,
  onError,
  onNotify,
}: Props) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Una lista nueva (otro documento, un refetch) no puede dejar armado un
  // "¿seguro?" sobre un segmento que ya no está en pantalla.
  useEffect(() => {
    setConfirming(null);
  }, [segments]);

  function tagOf(segment: Segment): string {
    return segment.tipo_dato_glaser
      ? canonicalGlaserTag(String(segment.tipo_dato_glaser))
      : "";
  }

  /** El siguiente segmento comparte categoría ⇒ el borrado es una fusión. */
  function mergesWithNext(index: number): boolean {
    const next = segments[index + 1];
    if (!next) return false;
    return tagOf(segments[index]) === tagOf(next);
  }

  async function erase(segment: Segment) {
    setBusy(segment.id);
    try {
      const res = await deleteDocumentSegment(documentId, segment.id);
      onChanged(res.segments);
      if (res.incidents_deleted > 0) {
        onNotify(
          t("project.segmentEraseIncidents", { count: res.incidents_deleted }),
        );
      } else if (res.action === "merged") {
        onNotify(t("project.segmentMerged"));
      } else {
        onNotify(t("project.segmentDeleted"));
      }
    } catch (error: any) {
      onError(error?.message || String(error));
    } finally {
      setBusy(null);
      setConfirming(null);
    }
  }

  return (
    <div onClick={(e) => e.stopPropagation()} style={panelCard}>
      {canEdit && segments.length > 0 && (
        <div style={{ fontSize: 10, color: "#8B949E", marginBottom: 6 }}>
          {t("project.segmentEraseHint")}
        </div>
      )}

      {segments.length === 0 ? (
        <span style={{ color: "#484F58" }}>{t("project.segmentsEmpty")}</span>
      ) : (
        segments.map((segment, index) => {
          const tag = tagOf(segment);
          const color = tag ? glaserColor(tag) : "#8B949E";
          const merges = mergesWithNext(index);
          const next = segments[index + 1];
          const isConfirming = confirming === segment.id;
          const isBusy = busy === segment.id;
          return (
            <div
              key={segment.id}
              style={{
                marginBottom: 8,
                paddingBottom: 8,
                borderBottom: "1px solid #21262D",
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "center",
                  marginBottom: 2,
                }}
              >
                <span style={{ fontSize: 10, color: "#484F58" }}>
                  #{segment.posicion}
                </span>
                {tag ? (
                  <span
                    style={{
                      fontSize: 9,
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: `${color}22`,
                      color,
                      border: `1px solid ${color}44`,
                    }}
                  >
                    {tag}
                  </span>
                ) : (
                  <span
                    style={{
                      fontSize: 9,
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: "#F8514918",
                      color: "#F85149",
                      border: "1px solid #F8514933",
                    }}
                  >
                    {t("project.stepSegmentsUnclassified")}
                  </span>
                )}

                {canEdit && (
                  <span style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                    {isConfirming ? (
                      <>
                        <button
                          onClick={() => erase(segment)}
                          disabled={isBusy}
                          style={{
                            padding: "1px 6px",
                            borderRadius: 4,
                            border: "none",
                            background: merges ? "#1F6FEB" : "#F85149",
                            color: "#fff",
                            fontSize: 9,
                            fontWeight: 600,
                            cursor: isBusy ? "not-allowed" : "pointer",
                            opacity: isBusy ? 0.6 : 1,
                          }}
                        >
                          {isBusy
                            ? t("project.segmentEraseBusy")
                            : t("project.segmentEraseConfirmYes")}
                        </button>
                        <button
                          onClick={() => setConfirming(null)}
                          style={{
                            padding: "1px 6px",
                            borderRadius: 4,
                            border: "none",
                            background: "#21262D",
                            color: "#8B949E",
                            fontSize: 9,
                            cursor: "pointer",
                          }}
                        >
                          {t("project.segmentEraseConfirmNo")}
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setConfirming(segment.id)}
                        title={
                          merges && next
                            ? t("project.segmentMergeTitle", {
                                pos: next.posicion,
                              })
                            : t("project.segmentEraseTitle")
                        }
                        style={{
                          padding: "1px 6px",
                          borderRadius: 999,
                          border: `1px solid ${
                            merges ? "#1F6FEB33" : "#F8514933"
                          }`,
                          background: merges ? "#1F6FEB18" : "#F8514918",
                          color: merges ? "#58A6FF" : "#F85149",
                          fontSize: 9,
                          lineHeight: 1.6,
                          cursor: "pointer",
                        }}
                      >
                        {merges
                          ? `⇥ ${t("project.segmentMerge")}`
                          : t("project.segmentErase")}
                      </button>
                    )}
                  </span>
                )}
              </div>
              <div
                style={{
                  whiteSpace: "pre-wrap",
                  fontFamily: "monospace",
                }}
              >
                {segment.texto}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
