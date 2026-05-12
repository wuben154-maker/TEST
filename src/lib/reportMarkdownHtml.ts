import { marked } from 'marked';

/**
 * Report / workspace markdown (GFM tables, fences, etc.) → HTML for docx-export + PDF.
 */
export function reportMarkdownToExportHtml(markdown: string): string {
  const trimmed = markdown.trim();
  const src = trimmed.length > 0 ? markdown : ' ';
  const out = marked.parse(src, { async: false });
  return typeof out === 'string' ? out : '';
}
