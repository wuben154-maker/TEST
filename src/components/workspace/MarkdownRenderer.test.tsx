import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownRenderer } from './MarkdownRenderer';

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({
      svg: '<svg xmlns="http://www.w3.org/2000/svg" role="img" data-testid="mermaid-svg"><path d="M0 0"/></svg>',
    })),
  },
}));

describe('MarkdownRenderer', () => {
  it('renders report markdown with headings, links, blockquotes, and code blocks', () => {
    render(
      <MarkdownRenderer
        markdown={[
          '## Executive Summary',
          '',
          'See [reference](https://example.com).',
          '',
          '> Evidence-backed conclusion',
          '',
          '```bash',
          'whoami',
          '```',
        ].join('\n')}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Executive Summary' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'reference' }).getAttribute('href')).toBe(
      'https://example.com',
    );
    expect(screen.getByText('Evidence-backed conclusion')).toBeTruthy();
    expect(screen.getByText('whoami')).toBeTruthy();
  });

  it('renders fenced mermaid blocks via MermaidBlock', async () => {
    render(
      <MarkdownRenderer markdown={['```mermaid', 'flowchart LR', '  a --> b', '```'].join('\n')} />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-svg')).toBeTruthy();
    });
  });

  it('renders GFM pipe tables', () => {
    const md = ['| Vendor | Segment |', '| --- | --- |', '| A | SOC |'].join('\n');
    render(<MarkdownRenderer markdown={md} />);
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Vendor' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: 'SOC' })).toBeTruthy();
  });
});
