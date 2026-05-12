import { Document, Paragraph, TextRun, HeadingLevel, AlignmentType, Packer, BorderStyle, ExternalHyperlink } from 'docx';
import { saveAs } from 'file-saver';

interface ParsedElement {
  type: 'heading' | 'paragraph' | 'list' | 'blockquote' | 'code' | 'hr';
  level?: 1 | 2 | 3;
  content: ParsedTextRun[];
  alignment?: 'left' | 'center' | 'right';
  listType?: 'bullet' | 'ordered';
  listItems?: ParsedElement[];
}

interface ParsedTextRun {
  text: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  strike?: boolean;
  code?: boolean;
}

function parseHtmlToElements(html: string): ParsedElement[] {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const elements: ParsedElement[] = [];

  function parseTextContent(node: Node): ParsedTextRun[] {
    const runs: ParsedTextRun[] = [];
    
    function processNode(n: Node, styles: Partial<ParsedTextRun> = {}): void {
      if (n.nodeType === Node.TEXT_NODE) {
        const text = n.textContent || '';
        if (text) {
          runs.push({ text, ...styles });
        }
        return;
      }

      if (n.nodeType === Node.ELEMENT_NODE) {
        const el = n as Element;
        const tagName = el.tagName.toLowerCase();
        const newStyles = { ...styles };

        switch (tagName) {
          case 'strong':
          case 'b':
            newStyles.bold = true;
            break;
          case 'em':
          case 'i':
            newStyles.italic = true;
            break;
          case 'u':
            newStyles.underline = true;
            break;
          case 's':
          case 'del':
            newStyles.strike = true;
            break;
          case 'code':
            newStyles.code = true;
            break;
        }

        el.childNodes.forEach(child => processNode(child, newStyles));
      }
    }

    node.childNodes.forEach(child => processNode(child));
    return runs;
  }

  function getAlignment(el: Element): 'left' | 'center' | 'right' | undefined {
    const style = el.getAttribute('style') || '';
    if (style.includes('text-align: center')) return 'center';
    if (style.includes('text-align: right')) return 'right';
    if (style.includes('text-align: left')) return 'left';
    return undefined;
  }

  doc.body.childNodes.forEach(node => {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    
    const el = node as Element;
    const tagName = el.tagName.toLowerCase();

    switch (tagName) {
      case 'h1':
        elements.push({
          type: 'heading',
          level: 1,
          content: parseTextContent(el),
          alignment: getAlignment(el),
        });
        break;
      case 'h2':
        elements.push({
          type: 'heading',
          level: 2,
          content: parseTextContent(el),
          alignment: getAlignment(el),
        });
        break;
      case 'h3':
        elements.push({
          type: 'heading',
          level: 3,
          content: parseTextContent(el),
          alignment: getAlignment(el),
        });
        break;
      case 'p':
        elements.push({
          type: 'paragraph',
          content: parseTextContent(el),
          alignment: getAlignment(el),
        });
        break;
      case 'ul':
        el.querySelectorAll('li').forEach(li => {
          elements.push({
            type: 'list',
            listType: 'bullet',
            content: parseTextContent(li),
          });
        });
        break;
      case 'ol':
        el.querySelectorAll('li').forEach(li => {
          elements.push({
            type: 'list',
            listType: 'ordered',
            content: parseTextContent(li),
          });
        });
        break;
      case 'blockquote':
        el.childNodes.forEach(child => {
          if (child.nodeType === Node.ELEMENT_NODE) {
            elements.push({
              type: 'blockquote',
              content: parseTextContent(child),
            });
          }
        });
        break;
      case 'pre':
        elements.push({
          type: 'code',
          content: [{ text: el.textContent || '', code: true }],
        });
        break;
      case 'hr':
        elements.push({
          type: 'hr',
          content: [],
        });
        break;
    }
  });

  return elements;
}

function createTextRuns(runs: ParsedTextRun[]): TextRun[] {
  return runs.map(run => {
    return new TextRun({
      text: run.text,
      bold: run.bold,
      italics: run.italic,
      underline: run.underline ? {} : undefined,
      strike: run.strike,
      font: run.code ? 'Courier New' : undefined,
    });
  });
}

function getDocxAlignment(alignment?: 'left' | 'center' | 'right') {
  switch (alignment) {
    case 'center':
      return AlignmentType.CENTER;
    case 'right':
      return AlignmentType.RIGHT;
    case 'left':
      return AlignmentType.LEFT;
    default:
      return undefined;
  }
}

function getHeadingLevel(level?: 1 | 2 | 3) {
  switch (level) {
    case 1:
      return HeadingLevel.HEADING_1;
    case 2:
      return HeadingLevel.HEADING_2;
    case 3:
      return HeadingLevel.HEADING_3;
    default:
      return HeadingLevel.HEADING_1;
  }
}

export async function exportToDocx(html: string, filename: string = 'document'): Promise<void> {
  const blob = await htmlToDocxBlob(html);
  saveAs(blob, `${filename}.docx`);
}

/** Build a .docx blob without downloading (e.g. knowledge base upload). */
export async function htmlToDocxBlob(html: string): Promise<Blob> {
  const elements = parseHtmlToElements(html);
  const children: Paragraph[] = [];

  elements.forEach(element => {
    switch (element.type) {
      case 'heading':
        children.push(
          new Paragraph({
            children: createTextRuns(element.content),
            heading: getHeadingLevel(element.level),
            alignment: getDocxAlignment(element.alignment),
          })
        );
        break;
      case 'paragraph':
        children.push(
          new Paragraph({
            children: createTextRuns(element.content),
            alignment: getDocxAlignment(element.alignment),
          })
        );
        break;
      case 'list':
        children.push(
          new Paragraph({
            children: createTextRuns(element.content),
            bullet: element.listType === 'bullet' ? { level: 0 } : undefined,
            numbering: element.listType === 'ordered' ? { reference: 'default-numbering', level: 0 } : undefined,
          })
        );
        break;
      case 'blockquote':
        children.push(
          new Paragraph({
            children: createTextRuns(element.content),
            indent: { left: 720 },
            border: {
              left: {
                color: 'CCCCCC',
                space: 8,
                style: BorderStyle.SINGLE,
                size: 6,
              },
            },
          })
        );
        break;
      case 'code':
        children.push(
          new Paragraph({
            children: createTextRuns(element.content),
            shading: { fill: 'F5F5F5' },
          })
        );
        break;
      case 'hr':
        children.push(
          new Paragraph({
            children: [],
            border: {
              bottom: {
                color: 'CCCCCC',
                space: 1,
                style: BorderStyle.SINGLE,
                size: 6,
              },
            },
          })
        );
        break;
    }
  });

  // Add empty paragraph if no content
  if (children.length === 0) {
    children.push(new Paragraph({ children: [] }));
  }

  const doc = new Document({
    numbering: {
      config: [
        {
          reference: 'default-numbering',
          levels: [
            {
              level: 0,
              format: 'decimal',
              text: '%1.',
              alignment: AlignmentType.START,
            },
          ],
        },
      ],
    },
    sections: [
      {
        children,
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  return blob;
}

export function htmlToPlainText(html: string): string {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  return doc.body.textContent || '';
}
