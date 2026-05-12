/**
 * Minimal markdown → HTML for DocumentWorkspace (TipTap initial content).
 * All user text must be escaped before injection into HTML; otherwise strings
 * like `<script...>` inside inline code become real HTML tags and truncate the document.
 */

export function escapeHtmlText(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Escape angle brackets etc., then apply **bold**, *italic*, `code`. */
export function formatInlineStyles(text: string): string {
  const escaped = escapeHtmlText(text);
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

export function parseMarkdownToHtml(content: string): string {
  const lines = content.split('\n');
  let html = '';
  let inList = false;
  let listType = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) {
      if (inList) {
        html += listType === 'ul' ? '</ul>' : '</ol>';
        inList = false;
      }
      continue;
    }

    if (line.startsWith('### ')) {
      if (inList) {
        html += listType === 'ul' ? '</ul>' : '</ol>';
        inList = false;
      }
      html += `<h3>${formatInlineStyles(line.slice(4))}</h3>`;
    } else if (line.startsWith('## ')) {
      if (inList) {
        html += listType === 'ul' ? '</ul>' : '</ol>';
        inList = false;
      }
      html += `<h2>${formatInlineStyles(line.slice(3))}</h2>`;
    } else if (line.startsWith('# ')) {
      if (inList) {
        html += listType === 'ul' ? '</ul>' : '</ol>';
        inList = false;
      }
      html += `<h1>${formatInlineStyles(line.slice(2))}</h1>`;
    } else if (/^\d+\.\s/.test(line)) {
      if (!inList || listType !== 'ol') {
        if (inList) html += listType === 'ul' ? '</ul>' : '</ol>';
        html += '<ol>';
        inList = true;
        listType = 'ol';
      }
      const li = line.replace(/^\d+\.\s/, '');
      html += `<li>${formatInlineStyles(li)}</li>`;
    } else if (line.startsWith('* ') || line.startsWith('- ')) {
      if (!inList || listType !== 'ul') {
        if (inList) html += listType === 'ul' ? '</ul>' : '</ol>';
        html += '<ul>';
        inList = true;
        listType = 'ul';
      }
      const li = line.slice(2);
      html += `<li>${formatInlineStyles(li)}</li>`;
    } else if (line.startsWith('> ')) {
      if (inList) {
        html += listType === 'ul' ? '</ul>' : '</ol>';
        inList = false;
      }
      html += `<blockquote><p>${formatInlineStyles(line.slice(2))}</p></blockquote>`;
    } else if (line.startsWith('```')) {
      if (inList) {
        html += listType === 'ul' ? '</ul>' : '</ol>';
        inList = false;
      }
      let codeContent = '';
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeContent += lines[i] + '\n';
        i++;
      }
      html += `<pre><code>${escapeHtmlText(codeContent.trim())}</code></pre>`;
    } else {
      if (inList) {
        html += listType === 'ul' ? '</ul>' : '</ol>';
        inList = false;
      }
      html += `<p>${formatInlineStyles(line)}</p>`;
    }
  }

  if (inList) {
    html += listType === 'ul' ? '</ul>' : '</ol>';
  }

  return html;
}
