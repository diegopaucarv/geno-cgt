/** Colapsa espacios y recorta los extremos: base común de los previews. */
function normalize(text: string): string {
  return String(text ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Single-line, length-capped preview for compact quote lists. */
export function shorten(text: string, max = 220): string {
  const clean = normalize(text);
  return clean.length > max ? clean.slice(0, max) + "…" : clean;
}

/** True si `shorten(text, max)` recortaría el texto (o sea: hay más que ver). */
export function isTruncated(text: string, max = 220): boolean {
  return normalize(text).length > max;
}
