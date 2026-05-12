/**
 * Best-effort repairs for malformed GFM pipe tables from LLMs.
 * Applies only outside ``` fenced blocks (~~~ treated as normal text).
 */

function transformOutsideTripleBacktickFences(payload: string, fn: (s: string) => string): string {
  const out: string[] = [];
  let pos = 0;
  while (pos < payload.length) {
    const start = payload.indexOf('```', pos);
    if (start === -1) {
      out.push(fn(payload.slice(pos)));
      break;
    }
    out.push(fn(payload.slice(pos, start)));
    const end = payload.indexOf('```', start + 3);
    if (end === -1) {
      out.push(payload.slice(start));
      break;
    }
    out.push(payload.slice(start, end + 3));
    pos = end + 3;
  }
  return out.join('');
}

/**
 * Fix: `… [196] | | 深信服 | …` (missing newline between rows) → `… [196]\n| 深信服 | …`
 */
export function fixCitationPipeRowGlue(text: string): string {
  return text.replace(/\]\s*\|\s+\|\s+/g, ']\n| ');
}

/** Normalizer for workspace/report markdown before ReactMarkdown. */
export function normalizeMarkdownForWorkspace(markdown: string): string {
  return transformOutsideTripleBacktickFences(markdown, fixCitationPipeRowGlue);
}
