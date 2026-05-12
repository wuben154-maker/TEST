import { describe, expect, it } from 'vitest';
import {
  collapseSyntheticConclusionMirrorBlock,
  timelineSuggestsWorkspaceReportTab,
} from './collapseSyntheticConclusionMirrorBlock';
import type { AnalysisTimelineEntry, TaskPlan, WorkspaceBlock } from '@/types/analysis';
import type { ConversationMessage } from '@/types/project';

describe('timelineSuggestsWorkspaceReportTab', () => {
  it('is false for reasoning + conclusion only', () => {
    const tl: AnalysisTimelineEntry[] = [
      { type: 'reasoning', seq: 1, content: 'think' } as AnalysisTimelineEntry,
      { type: 'conclusion', seq: 2, content: 'answer' } as AnalysisTimelineEntry,
    ];
    expect(timelineSuggestsWorkspaceReportTab(tl)).toBe(false);
  });

  it('is true for deep research step', () => {
    const tl: AnalysisTimelineEntry[] = [
      { type: 'step', seq: 1, id: 'open-deep-research-start' } as AnalysisTimelineEntry,
      { type: 'conclusion', seq: 2, content: 'report' } as AnalysisTimelineEntry,
    ];
    expect(timelineSuggestsWorkspaceReportTab(tl)).toBe(true);
  });

  it('is true for read_file tool_call', () => {
    const tl: AnalysisTimelineEntry[] = [
      { type: 'tool_call', seq: 1, id: 'tc1', toolName: 'read_file' } as AnalysisTimelineEntry,
    ];
    expect(timelineSuggestsWorkspaceReportTab(tl)).toBe(true);
  });
});

describe('collapseSyntheticConclusionMirrorBlock', () => {
  it('removes single full-analysis block for chat-only turns (no workspace signals)', () => {
    const msg: ConversationMessage = {
      id: 'a1',
      type: 'assistant',
      content: 'Hello from conclusion.',
      timestamp: new Date(),
      timeline: [],
      blocks: [
        {
          type: 'analysis',
          id: 'full-analysis',
          content: 'Hello from conclusion.',
          title: 'Report',
        },
      ],
    };
    const out = collapseSyntheticConclusionMirrorBlock(msg);
    expect(out.blocks).toEqual([]);
    expect(out.content).toBe('Hello from conclusion.');
  });

  it('does not remove legacy-analysis rows (ambiguous without timeline)', () => {
    const msg: ConversationMessage = {
      id: 'a2',
      type: 'assistant',
      content: 'Legacy body',
      timestamp: new Date(),
      blocks: [
        {
          type: 'analysis',
          id: 'legacy-analysis-uuid',
          content: 'Legacy body',
          title: '🔍 Analysis Report',
        },
      ],
    };
    const out = collapseSyntheticConclusionMirrorBlock(msg);
    expect(out.blocks?.length).toBe(1);
  });

  it('keeps full-analysis when timeline shows deep research', () => {
    const msg: ConversationMessage = {
      id: 'a-dr',
      type: 'assistant',
      content: 'Short summary',
      timestamp: new Date(),
      timeline: [
        { type: 'step', seq: 1, id: 'open-deep-research-start' } as AnalysisTimelineEntry,
        { type: 'conclusion', seq: 2, content: 'Long report…' } as AnalysisTimelineEntry,
      ],
      blocks: [
        {
          type: 'analysis',
          id: 'full-analysis',
          content: 'Long report…',
          title: 'Report',
        },
      ],
    };
    const out = collapseSyntheticConclusionMirrorBlock(msg);
    expect(out.blocks?.length).toBe(1);
  });

  it('keeps full-analysis when taskPlan is present', () => {
    const taskPlan: TaskPlan = {
      id: 'p1',
      isSingleTask: true,
      totalDurationMs: 0,
      status: 'success',
      createdAt: '',
      tasks: [
        {
          id: 't1',
          title: 'T',
          description: '',
          taskType: 'security',
          priority: 1,
          status: 'success',
          durationMs: 0,
          steps: [],
        },
      ],
    };
    const msg: ConversationMessage = {
      id: 'a-tp',
      type: 'assistant',
      content: '',
      timestamp: new Date(),
      taskPlan,
      blocks: [
        {
          type: 'analysis',
          id: 'full-analysis',
          content: 'Workspace body',
          title: 'Report',
        },
      ],
    };
    const out = collapseSyntheticConclusionMirrorBlock(msg);
    expect(out.blocks?.length).toBe(1);
  });

  it('keeps real multi-block workspace payloads', () => {
    const blocks: WorkspaceBlock[] = [
      { type: 'text', id: 't1', content: 'A' },
      { type: 'text', id: 't2', content: 'B' },
    ];
    const msg: ConversationMessage = {
      id: 'a3',
      type: 'assistant',
      content: 'Summary',
      timestamp: new Date(),
      blocks,
    };
    const out = collapseSyntheticConclusionMirrorBlock(msg);
    expect(out.blocks?.length).toBe(2);
  });

  it('keeps single analysis block with non-mirror id', () => {
    const msg: ConversationMessage = {
      id: 'a4',
      type: 'assistant',
      content: 'Chat line',
      timestamp: new Date(),
      blocks: [
        {
          type: 'analysis',
          id: 'custom-report',
          content: 'Long workspace report',
          title: 'Report',
        },
      ],
    };
    const out = collapseSyntheticConclusionMirrorBlock(msg);
    expect(out.blocks?.length).toBe(1);
  });
});
