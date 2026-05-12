import type { ReactElement } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { LanguageProvider } from '@/contexts/LanguageContext';
import { ReActTimelineView } from '@/components/reasoning/ReActTimelineView';
import type { ReActBlock } from '@/lib/buildReActTimeline';
import { getTranslations } from '@/i18n';

vi.mock('@/lib/liveElapsedSeconds', () => ({
  useLiveElapsedSeconds: () => null,
}));

function renderWithLang(ui: ReactElement) {
  return render(<LanguageProvider>{ui}</LanguageProvider>);
}

describe('ReActTimelineView — research task list', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('en');
  });

  it('subagent_task running uses shimmer row without spinner', () => {
    const blocks: ReActBlock[] = [
      {
        kind: 'step',
        label: 'task',
        status: 'running',
        stepVariant: 'subagent_task',
        detail: 'web-security',
      },
    ];

    const { container } = renderWithLang(<ReActTimelineView blocks={blocks} isStreaming />);

    expect(screen.getByTestId('subagent-delegation-running')).toBeTruthy();
    expect(container.querySelector('.animate-spin')).toBeNull();
  });

  it('generic step running uses same shimmer; success has no running test id', () => {
    const runningBlocks: ReActBlock[] = [
      { kind: 'step', label: 'Collect evidence', status: 'running', stepVariant: 'generic' },
    ];
    const { unmount, container } = renderWithLang(
      <ReActTimelineView blocks={runningBlocks} isStreaming />,
    );
    expect(screen.getByTestId('react-step-running')).toBeTruthy();
    expect(container.querySelector('.animate-shimmer')).toBeTruthy();
    unmount();

    const successBlocks: ReActBlock[] = [
      { kind: 'step', label: 'Collect evidence', status: 'success', stepVariant: 'generic' },
    ];
    renderWithLang(<ReActTimelineView blocks={successBlocks} isStreaming />);
    expect(screen.queryByTestId('react-step-running')).toBeNull();
  });

  it('renders ConductResearch-style list heading and topic title', () => {
    const blocks: ReActBlock[] = [
      {
        kind: 'task_list',
        bucketKey: 'test-bucket',
        listVariant: 'research',
        items: [{ id: 'cr-1', title: 'Short topic title', done: false }],
      },
    ];

    renderWithLang(<ReActTimelineView blocks={blocks} />);

    const t = getTranslations('en');
    expect(screen.getByText(new RegExp(t.reasoning.researchTaskList))).toBeTruthy();
    expect(screen.getByText('Short topic title')).toBeTruthy();
  });

  it('expanded tool output shows copy control and writes full text to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    const blocks: ReActBlock[] = [
      {
        kind: 'tool_execution',
        children: [
          {
            toolCallId: 'tc-copy',
            toolName: 'detect_web_attack',
            detail: '',
            done: true,
            toolOutput: 'payload-from-tool',
            isError: false,
          },
        ],
      },
    ];

    renderWithLang(<ReActTimelineView blocks={blocks} isStreaming={false} />);

    fireEvent.click(screen.getByRole('button', { expanded: false }));
    fireEvent.click(screen.getByTestId('react-tool-output-copy'));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('payload-from-tool');
    });
  });
});
