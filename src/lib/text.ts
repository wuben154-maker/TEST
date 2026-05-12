// Small text helpers used across UI

/**
 * Normalize multiline text coming from backend.
 * Some backends double-escape newlines ("\\n") which would otherwise render as literal characters.
 */
export function normalizeMultilineText(input?: string | null): string {
  if (!input) return '';

  // Normalize CRLF first
  let out = input.replace(/\r\n/g, '\n');

  // Convert escaped sequences into real newlines/tabs
  out = out.replace(/\\n/g, '\n').replace(/\\t/g, '\t');

  return out;
}
