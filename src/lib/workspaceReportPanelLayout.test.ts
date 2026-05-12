import { describe, expect, it } from 'vitest';
import type { Project } from '@/types/project';
import {
  panelUserDraggedStorageKey,
  projectShouldExpandReportPanel,
} from './workspaceReportPanelLayout';
import type { WorkspaceBlock, TaskPlan } from '@/types/analysis';

function emptyProject(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    title: 'T',
    messages: [],
    blocks: [],
    analysisResults: [],
    tasks: [],
    decisions: [],
    resolvedDecisions: {},
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides,
  };
}

describe('panelUserDraggedStorageKey', () => {
  it('includes project id', () => {
    expect(panelUserDraggedStorageKey('abc')).toContain('abc');
  });
});

describe('projectShouldExpandReportPanel', () => {
  it('returns false when no tabs anywhere', () => {
    expect(projectShouldExpandReportPanel(emptyProject())).toBe(false);
  });

  it('returns true when project has top-level blocks', () => {
    const p = emptyProject({
      blocks: [{ type: 'text', id: 'b1', content: 'x' }],
    });
    expect(projectShouldExpandReportPanel(p)).toBe(true);
  });

  it('returns true when a result has workspace tabs', () => {
    const p = emptyProject({
      analysisResults: [
        {
          id: 'r1',
          title: 'x',
          userInput: 'u',
          blocks: [],
          timestamp: new Date(),
          status: 'done',
          stats: {},
          workspaceTabs: [
            {
              id: 't1',
              type: 'report',
              label: 'Report',
              icon: 'file-text',
              instanceKey: 'ik1',
              data: { kind: 'placeholder', message: '' },
            },
          ],
        },
      ],
    });
    expect(projectShouldExpandReportPanel(p)).toBe(true);
  });

  it('returns true when a result has report blocks but no workspace tabs', () => {
    const block: WorkspaceBlock = { type: 'text', id: 'b1', content: 'Hi' };
    const p = emptyProject({
      analysisResults: [
        {
          id: 'r1',
          title: 'x',
          userInput: 'u',
          blocks: [block],
          timestamp: new Date(),
          status: 'done',
          stats: {},
          workspaceTabs: [],
        },
      ],
    });
    expect(projectShouldExpandReportPanel(p)).toBe(true);
  });

  it('returns true when an assistant message has workspace tabs', () => {
    const p = emptyProject({
      messages: [
        {
          id: 'm1',
          type: 'assistant',
          content: '',
          timestamp: new Date(),
          workspaceTabs: [
            {
              id: 't1',
              type: 'report',
              label: 'Report',
              icon: 'file-text',
              instanceKey: 'ik1',
              data: { kind: 'placeholder', message: '' },
            },
          ],
        },
      ],
    });
    expect(projectShouldExpandReportPanel(p)).toBe(true);
  });

  it('returns false for HITL-aborted assistant turn (running taskPlan, no tool calls, no blocks)', () => {
    // Realistic HITL scenario: agent planned, entered T1 (status='running'), emitted
    // parameter_request, user replied conversationally → turn ended without producing
    // anything observable. The next user message must NOT auto-expand the report panel.
    const runningOnlyPlan: TaskPlan = {
      id: 'plan-running',
      tasks: [
        {
          id: 't1',
          title: 'T',
          description: '',
          taskType: 'security',
          priority: 0,
          status: 'running',
          durationMs: 0,
          steps: [],
        },
      ],
      isSingleTask: true,
      totalDurationMs: 0,
      status: 'running',
      createdAt: '',
    };
    const p = emptyProject({
      messages: [
        {
          id: 'u1',
          type: 'user',
          content: '帮我分析二进制文件',
          timestamp: new Date(),
        },
        {
          id: 'm1',
          type: 'assistant',
          content: '请上传相关内容后我再进行分析。',
          reasoning: '',
          blocks: [],
          timestamp: new Date(),
          taskPlan: runningOnlyPlan,
          workspaceTabs: [],
          stats: {},
          timeline: [],
        },
      ],
    });
    expect(projectShouldExpandReportPanel(p)).toBe(false);
  });

  it('returns false when an assistant message only has tool calls (no blocks, no workspace tabs)', () => {
    // Tool calls alone are not enough — the backend only produces user-facing output
    // via blocks or workspace tabs. Matches assistantMessageYieldsAnalysisTab gate.
    const p = emptyProject({
      messages: [
        {
          id: 'm1',
          type: 'assistant',
          content: '请您上传需要分析的二进制文件。',
          reasoning: '',
          blocks: [],
          timestamp: new Date(),
          workspaceTabs: [],
          stats: { toolCallCount: 2 },
          timeline: [],
        },
      ],
    });
    expect(projectShouldExpandReportPanel(p)).toBe(false);
  });

  it('expands on live taskKind=security even before persistence', () => {
    // During streaming, persisted project data is still empty; live SSE has
    // delivered a TaskStatsMeta with taskKind='security'. The panel must
    // expand immediately so the report pane can render as conclusion arrives.
    const p = emptyProject();
    expect(
      projectShouldExpandReportPanel(p, { taskKind: 'security' }),
    ).toBe(true);
  });

  it('expands on live taskKind=research even before persistence', () => {
    const p = emptyProject();
    expect(
      projectShouldExpandReportPanel(p, { taskKind: 'research' }),
    ).toBe(true);
  });

  it('expands on live blocks / workspaceTabs even without taskKind', () => {
    const p = emptyProject();
    expect(projectShouldExpandReportPanel(p, { blocksCount: 1 })).toBe(true);
    expect(
      projectShouldExpandReportPanel(p, { workspaceTabsCount: 1 }),
    ).toBe(true);
  });

  it('does NOT expand on live hints of nothing material', () => {
    const p = emptyProject();
    expect(
      projectShouldExpandReportPanel(p, {
        taskKind: undefined,
        blocksCount: 0,
        workspaceTabsCount: 0,
      }),
    ).toBe(false);
  });

  it('ignores user messages for tabs', () => {
    const p = emptyProject({
      messages: [
        {
          id: 'm1',
          type: 'user',
          content: 'hi',
          timestamp: new Date(),
          workspaceTabs: [
            {
              id: 't1',
              type: 'report',
              label: 'Report',
              icon: 'file-text',
              instanceKey: 'ik1',
              data: { kind: 'placeholder', message: '' },
            },
          ],
        },
      ],
    });
    expect(projectShouldExpandReportPanel(p)).toBe(false);
  });
});
