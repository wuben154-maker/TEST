/**
 * Unwrap single-field JSON envelopes (e.g. research_brief) into plain prompt text.
 * Mirrors python-agent-service app.middleware.user_input_unwrap.
 */

const UNWRAP_KEYS = new Set([
  'research_brief',
  'brief',
  'query',
  'prompt',
  'message',
  'user_message',
  'instruction',
]);

const FENCE_RE = /^```(?:json)?\s*\r?\n([\s\S]*?)\r?\n```\s*$/i;

export function unwrapStructuredUserPrompt(text: unknown): string {
  if (text == null) return '';
  if (typeof text !== 'string') return '';

  const original = text;
  let s = text.trim();
  if (!s) return '';

  const fence = FENCE_RE.exec(s);
  if (fence) {
    s = fence[1].trim();
    if (!s) return original.trim();
  }

  if (!s.startsWith('{') || !s.endsWith('}')) {
    return original.trim();
  }

  let data: unknown;
  try {
    data = JSON.parse(s) as unknown;
  } catch {
    return original.trim();
  }

  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    return original.trim();
  }

  const entries = Object.entries(data as Record<string, unknown>);
  if (entries.length !== 1) {
    return original.trim();
  }

  const [key, val] = entries[0];
  if (!UNWRAP_KEYS.has(key)) {
    return original.trim();
  }
  if (typeof val !== 'string') {
    return original.trim();
  }
  const inner = val.trim();
  if (!inner) {
    return original.trim();
  }
  return inner;
}
