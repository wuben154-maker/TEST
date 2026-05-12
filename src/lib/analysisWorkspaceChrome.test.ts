import { describe, it, expect } from 'vitest';
import {
  inferUseWorkspaceTaskPanelFromSnapshot,
  inferUseWorkspaceTaskPanelFromMessage,
  taskPlanHasStartedExecution,
} from '@/lib/analysisWorkspaceChrome';
import type { ConversationMessage } from '@/types/project';

describe('taskPlanHasStartedExecution', () => {
  it('is false when plan is null/undefined', () => {
    expect(taskPlanHasStartedExecution(null)).toBe(false);
    expect(taskPlanHasStartedExecution(undefined)).toBe(false);
  });

  it('is false when plan has no tasks', () => {
    expect(taskPlanHasStartedExecution({ tasks: [] })).toBe(false);
  });

  it('is false when every task is still pending (HITL-abort / not started yet)', () => {
    expect(
      taskPlanHasStartedExecution({
        tasks: [{ status: 'pending' }, { status: 'pending' }],
      }),
    ).toBe(false);
  });

  it('is true when at least one task left the pending state', () => {
    expect(
      taskPlanHasStartedExecution({
        tasks: [{ status: 'pending' }, { status: 'running' }],
      }),
    ).toBe(true);
    expect(taskPlanHasStartedExecution({ tasks: [{ status: 'success' }] })).toBe(true);
    expect(taskPlanHasStartedExecution({ tasks: [{ status: 'error' }] })).toBe(true);
    expect(taskPlanHasStartedExecution({ tasks: [{ status: 'skipped' }] })).toBe(true);
  });
});

describe('analysisWorkspaceChrome', () => {
  it('is true when task plan has at least one started task (running / success / error)', () => {
    expect(
      inferUseWorkspaceTaskPanelFromSnapshot({
        toolCallCount: 0,
        workspaceTabs: [],
        sandboxRunCount: 0,
        taskPlanMain: { tasks: [{ status: 'success' }] },
        taskPlansSubagent: {},
      }),
    ).toBe(true);
  });

  it('is false when task plan exists but every task is pending (HITL-aborted turn)', () => {
    // Agent built the plan then hit a HITL parameter_request and the user
    // replied conversationally — no task ever ran. Treat as a plain chat reply.
    expect(
      inferUseWorkspaceTaskPanelFromSnapshot({
        toolCallCount: 0,
        workspaceTabs: [],
        sandboxRunCount: 0,
        taskPlanMain: { tasks: [{ status: 'pending' }] },
        taskPlansSubagent: {},
      }),
    ).toBe(false);
  });

  it('is false for empty snapshot', () => {
    expect(
      inferUseWorkspaceTaskPanelFromSnapshot({
        toolCallCount: 0,
        workspaceTabs: [],
        sandboxRunCount: 0,
        taskPlanMain: null,
        taskPlansSubagent: {},
      }),
    ).toBe(false);
  });

  it('reads from conversation message taskPlan and requires at least one started task', () => {
    const running = {
      type: 'assistant',
      taskPlan: { tasks: [{ id: '1', title: 't', status: 'running' }] },
    } as unknown as ConversationMessage;
    expect(inferUseWorkspaceTaskPanelFromMessage(running)).toBe(true);

    const pendingOnly = {
      type: 'assistant',
      taskPlan: { tasks: [{ id: '1', title: 't', status: 'pending' }] },
    } as unknown as ConversationMessage;
    expect(inferUseWorkspaceTaskPanelFromMessage(pendingOnly)).toBe(false);
  });

  // After the stats-bar redesign, persistence stores only the backend-derived
  // TaskStatsMeta (taskKind + security/research) on `messages.stats` — it does
  // NOT round-trip toolCallCount / sandboxRunCount. On refresh, an
  // assistant turn whose timeline+taskPlan got compacted away would otherwise
  // lose its task-panel chrome (header + stats bar disappear). taskKind is
  // the strongest "this was an agentic security/research turn" signal we have,
  // so it must be sufficient on its own to keep chrome alive.
  it('T-01: snapshot keeps chrome when taskKind is present even if every other signal is empty', () => {
    expect(
      inferUseWorkspaceTaskPanelFromSnapshot({
        toolCallCount: 0,
        workspaceTabs: [],
        sandboxRunCount: 0,
        taskPlanMain: null,
        taskPlansSubagent: {},
        taskKind: 'security',
      }),
    ).toBe(true);

    expect(
      inferUseWorkspaceTaskPanelFromSnapshot({
        toolCallCount: 0,
        workspaceTabs: [],
        sandboxRunCount: 0,
        taskPlanMain: null,
        taskPlansSubagent: {},
        taskKind: 'research',
      }),
    ).toBe(true);
  });

  it('T-02: message-level inference keeps chrome alive after refresh when stats.taskKind is present (regression: stats bar disappeared on reload)', () => {
    const refreshedResearchTurn = {
      type: 'assistant',
      stats: {
        taskKind: 'research',
        research: {
          keyFindings: 12,
          recommendations: 16,
          sources: 79,
          gaps: 3,
          freshness: '<=90d',
        },
      },
      // Persistence path drops these; emulate the post-refresh shape.
      taskPlan: null,
      timeline: [],
      workspaceTabs: [],
    } as unknown as ConversationMessage;
    expect(inferUseWorkspaceTaskPanelFromMessage(refreshedResearchTurn)).toBe(true);

    const refreshedSecurityTurn = {
      type: 'assistant',
      stats: {
        taskKind: 'security',
        security: { severity: 'high', riskScore: 78 },
      },
      taskPlan: null,
      timeline: [],
      workspaceTabs: [],
    } as unknown as ConversationMessage;
    expect(inferUseWorkspaceTaskPanelFromMessage(refreshedSecurityTurn)).toBe(true);
  });
});
