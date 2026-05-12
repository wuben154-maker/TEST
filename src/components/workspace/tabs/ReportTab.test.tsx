/**
 * Bug #1 regression: the report tab was showing its "generating" skeleton
 * while status==='running', even after blocks had already streamed in. That
 * caused the 1–2s gap between summary-in-chat and report-panel content.
 * The fix: once there is any block or editedText, render the content; keep
 * the skeleton only for the truly empty-while-running state.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { WorkspaceBlock } from '@/types/analysis';
import { ReportTab } from './ReportTab';

vi.mock('@/contexts/LanguageContext', () => ({
  useLanguage: () => ({
    t: {
      workspace: {
        smartCanvas: 'Smart canvas',
        empty: 'Empty',
        taskPanel: {
          noReport: 'No report',
          doubleClickToEdit: 'Double click to edit',
        },
      },
    },
  }),
}));

const sampleBlock: WorkspaceBlock = {
  type: 'text',
  id: 'b1',
  content: 'Hello from conclusion',
};

const sampleAnalysisBlock: WorkspaceBlock = {
  type: 'analysis',
  id: 'analysis-1',
  title: 'Detailed analysis',
  content: '## Executive Summary\n\nA professional report body.',
};

describe('ReportTab', () => {
  it('shows skeleton when running AND no blocks', () => {
    render(<ReportTab status="running" blocks={[]} />);
    expect(screen.getByTestId('report-skeleton')).toBeTruthy();
  });

  it('renders blocks as soon as they arrive even if status is still running', () => {
    render(<ReportTab status="running" blocks={[sampleBlock]} />);
    expect(screen.queryByTestId('report-skeleton')).toBeNull();
    expect(screen.getByText(/Hello from conclusion/)).toBeTruthy();
  });

  it('renders editedText as soon as it exists even if status is still running', () => {
    render(<ReportTab status="running" blocks={[]} editedText="streaming body" />);
    expect(screen.queryByTestId('report-skeleton')).toBeNull();
    expect(screen.getByText(/streaming body/)).toBeTruthy();
  });

  it('renders report sections and markdown analysis body for completed report blocks', () => {
    render(
      <ReportTab
        status="done"
        blocks={[sampleAnalysisBlock]}
        title="Suspicious upload analysis"
        generatedAt="2026-04-25T09:00:00.000Z"
      />,
    );

    expect(screen.queryByTestId('report-cover')).toBeNull();
    expect(
      screen.queryByRole('heading', { name: 'Suspicious upload analysis', level: 1 }),
    ).toBeNull();
    expect(screen.getByRole('heading', { name: 'Executive Summary' })).toBeTruthy();
    expect(screen.getByText('A professional report body.')).toBeTruthy();
  });

  it('shows empty state when done but no blocks produced', () => {
    render(<ReportTab status="done" blocks={[]} />);
    expect(screen.queryByTestId('report-skeleton')).toBeNull();
    expect(screen.getByText('No report')).toBeTruthy();
  });
});
