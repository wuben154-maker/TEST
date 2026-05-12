/**
 * Drop leading English/thinking paragraphs before a clear CJK report body.
 * Mirrors python-agent-service `strip_leading_preface_before_cjk_report_body`.
 */
const CJK_CHARS = /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]/g;

export function stripLeadingPrefaceBeforeCjkReportBody(
  text: string,
  minCjkInParagraph: number = 10,
): string {
  const t = text.trim();
  if (!t) return t;
  const parts = t.split(/\n\s*\n+/);
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i].trim();
    if (!p) continue;
    const m = p.match(CJK_CHARS);
    const cjkN = m ? m.length : 0;
    if (cjkN >= minCjkInParagraph) {
      return parts
        .slice(i)
        .map((x) => x.trim())
        .filter(Boolean)
        .join('\n\n')
        .trim();
    }
  }
  return t;
}
