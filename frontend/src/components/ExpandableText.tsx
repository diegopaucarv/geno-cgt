import { useState } from "react";
import type { CSSProperties, MouseEvent } from "react";
import { useI18n } from "../i18n";
import { isTruncated, shorten } from "./incidents/shorten";

interface Props {
  /** Texto completo tal como llega del backend (nunca truncado). */
  text: string;
  /** Longitud del preview colapsado. */
  max?: number;
  style?: CSSProperties;
  /**
   * Estado controlado de la expansión. Se usa cuando toda la fila (y no solo
   * el texto) debe poder disparar el toggle: la fila guarda el estado y lo
   * pasa junto con `onToggle`.
   */
  expanded?: boolean;
  /** Notifica el toggle; su presencia activa el modo controlado. */
  onToggle?: () => void;
}

/**
 * Preview de una línea que puede expandirse al texto completo con un clic.
 *
 * Colapsado se ve igual que `shorten(text, max)`; si el texto ya entra entero
 * no es interactivo ni muestra cursor de acción. Sin `onToggle` el estado vive
 * dentro del propio componente (el llamador debe dar una `key` estable en
 * listas); con `onToggle` lo controla la fila contenedora.
 */
export function ExpandableText({
  text,
  max = 220,
  style,
  expanded: expandedProp,
  onToggle,
}: Props) {
  const { t } = useI18n();
  const [uncontrolled, setUncontrolled] = useState(false);

  const controlled = onToggle !== undefined;
  const expanded = controlled ? !!expandedProp : uncontrolled;
  const truncated = isTruncated(text, max);

  if (!truncated) return <span style={style}>{shorten(text, max)}</span>;

  const handleClick = (e: MouseEvent) => {
    // Evita que el clic burbujee al contenedor (p. ej. toggle de la tarjeta).
    e.stopPropagation();
    if (controlled) onToggle();
    else setUncontrolled((v) => !v);
  };

  return (
    <span
      onClick={handleClick}
      title={
        expanded ? t("project.segmentViewLess") : t("project.segmentViewFull")
      }
      style={{
        cursor: "pointer",
        ...style,
        ...(expanded
          ? { whiteSpace: "pre-wrap", wordBreak: "break-word" }
          : {}),
      }}
    >
      {expanded ? String(text ?? "").trim() : shorten(text, max)}
    </span>
  );
}
