/**
 * Styled HTML fragment → PDF via html2pdf.js (offline, print-safe light palette).
 */

export function applyPrintFriendlyPdfTypography(root: HTMLElement): void {
  root.style.cssText = `
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    color: #1a1a1a;
    padding: 40px;
    max-width: 800px;
    margin: 0 auto;
  `;

  root.querySelectorAll('h1').forEach((el) => {
    (el as HTMLElement).style.cssText =
      'font-size: 28px; font-weight: 700; margin: 24px 0 16px 0; color: #0a0a0a;';
  });
  root.querySelectorAll('h2').forEach((el) => {
    (el as HTMLElement).style.cssText =
      'font-size: 22px; font-weight: 600; margin: 20px 0 12px 0; color: #0a0a0a;';
  });
  root.querySelectorAll('h3').forEach((el) => {
    (el as HTMLElement).style.cssText =
      'font-size: 18px; font-weight: 500; margin: 16px 0 8px 0; color: #0a0a0a;';
  });
  root.querySelectorAll('p').forEach((el) => {
    (el as HTMLElement).style.cssText = 'margin: 8px 0; color: #333;';
  });
  root.querySelectorAll('ul, ol').forEach((el) => {
    (el as HTMLElement).style.cssText = 'margin: 8px 0; padding-left: 24px; color: #333;';
  });
  root.querySelectorAll('li').forEach((el) => {
    (el as HTMLElement).style.cssText = 'margin: 4px 0;';
  });
  root.querySelectorAll('pre').forEach((el) => {
    (el as HTMLElement).style.cssText =
      'background: #f5f5f5; padding: 16px; border-radius: 8px; overflow-x: auto; font-family: monospace; font-size: 13px;';
  });
  root.querySelectorAll('code').forEach((el) => {
    if ((el as HTMLElement).closest('pre')) return;
    (el as HTMLElement).style.cssText =
      'background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px;';
  });
  root.querySelectorAll('blockquote').forEach((el) => {
    (el as HTMLElement).style.cssText =
      'border-left: 4px solid #ddd; padding-left: 16px; margin: 16px 0; color: #666; font-style: italic;';
  });
  root.querySelectorAll('table').forEach((el) => {
    (el as HTMLElement).style.cssText =
      'width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px;';
  });
  root.querySelectorAll('th, td').forEach((el) => {
    (el as HTMLElement).style.cssText = 'border: 1px solid #ccc; padding: 8px; text-align: left;';
  });
  root.querySelectorAll('th').forEach((el) => {
    (el as HTMLElement).style.backgroundColor = '#f5f5f5';
    (el as HTMLElement).style.fontWeight = '600';
  });
  root.querySelectorAll('a').forEach((el) => {
    (el as HTMLElement).style.cssText =
      'color: #163c9c; text-decoration: underline; text-underline-offset: 2px;';
  });
  root.querySelectorAll('strong').forEach((el) => {
    (el as HTMLElement).style.cssText = 'font-weight: 700;';
  });
}

export async function exportHtmlFragmentToPdf(
  innerHtml: string,
  filenameBase: string,
): Promise<void> {
  const html2pdf = (await import('html2pdf.js')).default;

  const container = document.createElement('div');
  container.innerHTML = innerHtml;
  applyPrintFriendlyPdfTypography(container);

  const opt = {
    margin: [15, 15, 15, 15] as [number, number, number, number],
    filename: `${filenameBase}.pdf`,
    image: { type: 'jpeg' as const, quality: 0.98 },
    html2canvas: {
      scale: 2,
      useCORS: true,
      logging: false,
    },
    jsPDF: {
      unit: 'mm' as const,
      format: 'a4' as const,
      orientation: 'portrait' as const,
    },
  };

  await html2pdf().set(opt).from(container).save();
}
