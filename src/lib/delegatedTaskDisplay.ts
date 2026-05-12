/**
 * Format `task(...)` tool `description` for end-user UI.
 * Deep-research delegations use a layered wire format (ORIGINAL_QUERY + ---CONTEXT---);
 * users should only see the original question, not routing markers or explore context.
 */
const CONTEXT_SEPARATOR = '---CONTEXT---';

export function formatDelegatedTaskForDisplay(raw: string, maxLen = 400): string {
  const trimmed = raw.trim();
  if (!trimmed) return '';

  let original: string;
  if (trimmed.includes(CONTEXT_SEPARATOR)) {
    original = trimmed.split(CONTEXT_SEPARATOR, 1)[0]!.trim();
  } else {
    original = trimmed;
  }

  original = original.replace(/^ORIGINAL_QUERY:\s*/i, '').trim();

  const base = original.length > 0 ? original : trimmed.split(CONTEXT_SEPARATOR, 1)[0]!.trim();
  if (!base) return '';

  return base.length > maxLen ? `${base.slice(0, maxLen)}…` : base;
}
