/** Vocabulario Glaser canónico y sus colores.
 *
 * Vive también en `projects.GLASER_TAGS` y `segment_classifier.CLASSES_GLASER`
 * (backend). Los cinco valores son los únicos que el backend escribe; los
 * alias existen solo por datos viejos clasificados antes del renombrado.
 */

export const GLASER_TAGS = [
  "baseline_data",
  "properline_data",
  "interpreted_data",
  "vague_data",
  "document_context",
] as const;

export type GlaserTag = (typeof GLASER_TAGS)[number];

export const GLASER_TAG_COLORS: Record<string, string> = {
  baseline_data: "#3FB950",
  properline_data: "#58A6FF",
  interpreted_data: "#A371F7",
  vague_data: "#8B949E",
  document_context: "#D29922",
};

/** Taxonomía vieja que aún puede aparecer en datos ya clasificados. */
export const LEGACY_GLASER_ALIASES: Record<string, string> = {
  processual_data: "baseline_data",
  contextual_data: "vague_data",
  interviewer_context: "document_context",
};

export function canonicalGlaserTag(tag: string): string {
  return LEGACY_GLASER_ALIASES[tag] || tag;
}

export function glaserColor(tag: string | null | undefined): string {
  if (!tag) return "#8B949E";
  return GLASER_TAG_COLORS[canonicalGlaserTag(String(tag))] || "#8B949E";
}
