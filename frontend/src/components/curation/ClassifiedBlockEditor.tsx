import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useI18n } from "../../i18n";
import {
  patchDocumentClassification,
  type GlaserBlock,
} from "../../api/client";
import {
  GLASER_TAGS,
  canonicalGlaserTag,
  glaserColor,
} from "../incidents/glaser";

/**
 * Editor del paso **clasificado**: cada bloque del texto clasificado expone su
 * categoría Glaser y se puede cambiar o borrar.
 *
 * Por qué guarda solo: editar la clasificación re-deriva la etiqueta de los
 * segmentos en el backend, así que cada cambio es una escritura real, no una
 * vista previa. No hay botón "guardar" porque el investigador corrige bloque
 * por bloque y una cola de cambios pendientes sería otro estado que mantener.
 *
 * Concurrencia: se encola **un** request a la vez y se envía lo que haya
 * pendiente al terminar. Si el usuario cambia tres bloques seguidos, la UI no
 * dispara tres PATCH que se pisen entre sí.
 */

interface Props {
  documentId: string;
  blocks: GlaserBlock[];
  /** false mientras el documento tiene un paso en vuelo. */
  canEdit: boolean;
  onSaved: (blocks: GlaserBlock[], textoClasificado: string) => void;
  onError: (message: string) => void;
}

/** `class` puede ser null: es un bloque sin categoría. */
type EditableBlock = Omit<GlaserBlock, "class"> & { class: string | null };

const FLUSH_DELAY_MS = 350;

export default function ClassifiedBlockEditor({
  documentId,
  blocks,
  canEdit,
  onSaved,
  onError,
}: Props) {
  const { t } = useI18n();
  const [local, setLocal] = useState<EditableBlock[]>(
    () => blocks as EditableBlock[],
  );
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  /** Cambios pendientes por índice. Indexar por bloque (y no por "lista de
   *  cambios") colapsa dos ediciones del mismo bloque en una sola. */
  const dirty = useRef(new Map<number, string | null>());
  const inFlight = useRef(false);
  const timer = useRef<number | null>(null);
  const flushRef = useRef<() => Promise<void>>(async () => {});

  // Los callbacks se leen desde un ref para que el flush diferido nunca use una
  // versión vieja de `onSaved` / `documentId`.
  const latest = useRef({ blocks, onSaved, onError });
  latest.current = { blocks, onSaved, onError };

  // Un refetch del padre no debe pisar una edición todavía no guardada.
  useEffect(() => {
    if (dirty.current.size === 0 && !inFlight.current) {
      setLocal(blocks as EditableBlock[]);
    }
  }, [blocks]);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  useEffect(() => {
    flushRef.current = async () => {
      if (inFlight.current) return;
      const entries = Array.from(dirty.current.entries());
      if (!entries.length) return;

      inFlight.current = true;
      setSaving(true);
      try {
        const res = await patchDocumentClassification(
          documentId,
          entries.map(([index, value]) => ({ index, class: value })),
        );
        // Sólo se descarta lo enviado: si el usuario tocó otro bloque mientras
        // viajaba la petición, ese cambio sigue pendiente.
        for (const [index, value] of entries) {
          if (dirty.current.get(index) === value) dirty.current.delete(index);
        }
        setLocal(res.blocks as EditableBlock[]);
        setFailed(false);
        latest.current.onSaved(res.blocks, res.texto_clasificado);
      } catch (error: any) {
        dirty.current.clear();
        setLocal(latest.current.blocks as EditableBlock[]);
        setFailed(true);
        latest.current.onError(error?.message || String(error));
      } finally {
        inFlight.current = false;
        setSaving(false);
        if (dirty.current.size > 0) {
          timer.current = window.setTimeout(() => flushRef.current(), 0);
        }
      }
    };
  });

  function enqueue(index: number, value: string | null) {
    if (!canEdit) return;
    dirty.current.set(index, value);
    setLocal((prev) =>
      prev.map((block, i) => (i === index ? { ...block, class: value } : block)),
    );
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => flushRef.current(), FLUSH_DELAY_MS);
  }

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      style={{
        width: "100%",
        minHeight: 150,
        maxHeight: "55vh",
        fontSize: 13,
        background: "#0D1117",
        color: "#E6EDF3",
        border: "1px solid #21262D",
        borderRadius: 6,
        padding: 8,
        overflow: "auto",
        wordBreak: "break-word",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 10,
          color: "#8B949E",
          marginBottom: 6,
        }}
      >
        <span style={{ flex: 1 }}>
          {canEdit
            ? t("project.classifiedEditHint")
            : t("project.classifiedEditLocked")}
        </span>
        {saving && <span style={{ color: "#D29922" }}>{"⟳"}</span>}
        {failed && <span style={{ color: "#F85149" }}>{"⚠"}</span>}
      </div>

      {local.map((block, index) => {
        const raw = block.class ? String(block.class) : "";
        const tag = raw ? canonicalGlaserTag(raw) : "";
        const color = tag ? glaserColor(tag) : "#8B949E";
        const known =
          tag === "" || (GLASER_TAGS as readonly string[]).includes(tag);
        return (
          <div
            key={index}
            style={{
              margin: "6px 0",
              padding: "6px 8px",
              borderLeft: `3px solid ${color}`,
              background: `${color}11`,
              borderRadius: "0 4px 4px 0",
            }}
          >
            <div style={{ marginBottom: 3 }}>
              {canEdit ? (
                <select
                  value={tag}
                  onChange={(e) => enqueue(index, e.target.value || null)}
                  title={t("project.classifiedBlockSelectTitle")}
                  style={selectChip(color)}
                >
                  <option value="">{t("project.classifiedBlockClear")}</option>
                  {GLASER_TAGS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                  {/* Etiqueta rara que ya estaba en los datos: se muestra en vez
                      de fingir que el bloque no tiene categoría. */}
                  {!known && <option value={tag}>{tag}</option>}
                </select>
              ) : (
                <span style={chip(color)}>
                  {tag || t("project.classifiedBlockClear")}
                </span>
              )}
            </div>
            <span
              style={{
                color,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                fontFamily: "monospace",
              }}
            >
              {block.text}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function chip(color: string): CSSProperties {
  return {
    display: "inline-block",
    fontSize: 9,
    padding: "1px 6px",
    borderRadius: 999,
    background: `${color}22`,
    color,
    border: `1px solid ${color}44`,
    whiteSpace: "nowrap",
    fontWeight: 600,
  };
}

/** El select tiene la forma de la pastilla de categoría del visor. */
function selectChip(color: string): CSSProperties {
  return {
    fontSize: 9,
    padding: "1px 4px",
    borderRadius: 999,
    background: `${color}22`,
    color,
    border: `1px solid ${color}44`,
    fontWeight: 600,
    cursor: "pointer",
  };
}
