import { describe, expect, it } from 'vitest';
import { formatInlineStyles, parseMarkdownToHtml } from './documentWorkspaceMarkdown';

describe('documentWorkspaceMarkdown', () => {
  it('escapes script-like content inside inline code so HTML is not truncated', () => {
    const line =
      '| **技术原理** | 使用 `<script language=\\"php\\">` 替代 `<?php` |';
    const html = formatInlineStyles(line);
    expect(html).toContain('&lt;script');
    expect(html).toContain('</code>');
    expect(html).not.toMatch(/<script[\s>]/i);
  });

  it('parseMarkdownToHtml preserves content after a markdown table row with inline code', () => {
    const md = [
      '### 变体7',
      '',
      '| A | B |',
      '|---|---|',
      '| **技术原理** | 使用 `<script>x</script>` end |',
      '',
      '### 变体8',
      'Tail paragraph.',
    ].join('\n');
    const html = parseMarkdownToHtml(md);
    expect(html).toContain('变体8');
    expect(html).toContain('Tail paragraph');
    expect(html).toContain('&lt;script&gt;x&lt;/script&gt;');
  });

  it('escapes fenced code blocks', () => {
    const md = '```\n</textarea><script>evil</script>\n```';
    const html = parseMarkdownToHtml(md);
    expect(html).toContain('&lt;/textarea&gt;');
    expect(html).not.toMatch(/<script[\s>]/i);
  });
});
