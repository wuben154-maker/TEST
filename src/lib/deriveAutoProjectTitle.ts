/** Aligned with useProjects PROJECT_TITLE_MAX_LENGTH */
export const AUTO_PROJECT_TITLE_MAX_LEN = 50;

function collapseWhitespace(s: string): string {
  return s.replace(/\s+/g, ' ').trim();
}

function basenameOnly(name: string): string {
  const t = name.replace(/\\/g, '/').split('/').pop() ?? name;
  return t.trim() || name;
}

function clampTitleSegment(s: string, max: number): string {
  if (s.length <= max) return s;
  const cut = s.slice(0, max);
  const lastSpace = cut.lastIndexOf(' ');
  if (lastSpace > max * 0.5) return cut.slice(0, lastSpace);
  return `${cut.slice(0, max - 1)}…`;
}

/** Compact attachment list for suffix after user text (within maxHint). */
function attachmentHint(names: string[], maxHint: number): string {
  const b = names.map(basenameOnly).filter(Boolean);
  if (b.length === 0) return '';
  if (b.length === 1) return clampTitleSegment(b[0]!, maxHint);
  const two = `${b[0]}, ${b[1]}`;
  if (b.length === 2 && two.length <= maxHint) return two;
  const withEllipsis = `${b[0]}, ${b[1]}…`;
  if (withEllipsis.length <= maxHint) return withEllipsis;
  const one = b[0]!;
  if (one.length + 1 <= maxHint) return b.length > 1 ? `${one}…` : one;
  return clampTitleSegment(one, maxHint);
}

/**
 * Derives a short project title from the first user message line and/or attachment names.
 * When both text and files exist, leads with text and appends " · " + file hint so names stay visible.
 * Used when auto-creating a project on the transition page (no manual naming).
 */
export function deriveAutoProjectTitle(options: {
  userText: string;
  fileNames: string[];
  /** Shown when both text and files are empty (should be rare). */
  fallbackLabel: string;
  maxLen?: number;
}): string {
  const max = options.maxLen ?? AUTO_PROJECT_TITLE_MAX_LEN;
  const raw = (options.userText || '').replace(/\r\n/g, '\n');
  const firstLine = raw.split('\n').map((l) => l.trim()).find((l) => l.length > 0) ?? '';
  const fromText = collapseWhitespace(firstLine);
  const names = options.fileNames.map(basenameOnly).filter(Boolean);

  let base = '';
  if (fromText.length > 0) {
    if (names.length === 0) {
      base = fromText;
    } else {
      const sep = ' · ';
      const minTextChars = 6;
      let hintMax = max - sep.length - minTextChars;
      if (hintMax < 6) hintMax = 6;
      const hint = attachmentHint(names, hintMax);
      const suffix = sep + hint;
      if (fromText.length + suffix.length <= max) {
        base = fromText + suffix;
      } else {
        const textBudget = Math.max(4, max - suffix.length);
        base = clampTitleSegment(fromText, textBudget) + suffix;
        if (base.length > max) base = clampTitleSegment(base, max);
      }
    }
  } else if (names.length > 0) {
    if (names.length === 1) {
      base = names[0]!;
    } else {
      base = names.slice(0, 3).join(', ');
      if (base.length > max) {
        base = `${base.slice(0, max - 1)}…`;
      }
    }
  } else {
    base = (options.fallbackLabel || '—').trim() || '—';
  }

  if (base.length <= max) return base;
  return clampTitleSegment(base, max);
}
