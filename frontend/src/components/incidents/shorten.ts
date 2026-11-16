/** Single-line, length-capped preview for compact quote lists. */
export function shorten(text: string, max = 220): string {
  const clean = String(text ?? "")
    .replace(/\s+/g, " ")
    .trim();
  return clean.length > max ? clean.slice(0, max) + "…" : clean;
}
