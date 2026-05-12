import { describe, expect, it } from 'vitest';
import { streamingConclusionForChat } from './streamingConclusionForChat';
import type { AnalysisTimelineEntry, PlannedTask, TaskPlan } from '@/types/analysis';

const minimalTaskPlan: TaskPlan = {
  id: 'task-plan',
  tasks: [],
  isSingleTask: true,
  totalDurationMs: 0,
  status: 'success',
  createdAt: '',
};

const baseOpts = {
  blocksCount: 0,
  taskPlan: null as TaskPlan | null,
  taskPlansSubagent: {} as Record<string, TaskPlan | null>,
  workspaceTabsCount: 0,
  timeline: [] as AnalysisTimelineEntry[],
  taskKind: undefined as 'security' | 'research' | undefined,
};

describe('streamingConclusionForChat', () => {
  it('returns trimmed conclusion when no workspace report signals', () => {
    expect(
      streamingConclusionForChat('  Hello  ', {
        ...baseOpts,
      }),
    ).toBe('Hello');
  });

  it('returns undefined when workspace blocks exist (agentic fallback)', () => {
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        blocksCount: 1,
      }),
    ).toBeUndefined();
  });

  it('returns conclusion text when only main task plan exists (B strategy removes this trigger)', () => {
    // B-strategy: a bare task_plan is no longer enough to hijack the report
    // area; a plain agent that merely planned a todo list should land in chat
    // unless blocks / workspaceTabs / subagent plans / taskKind also say so.
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        taskPlan: minimalTaskPlan,
      }),
    ).toBe('Full report');
  });

  it('returns conclusion text when only timeline has task_plan (B strategy removes this trigger)', () => {
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        timeline: [{ type: 'task_plan', seq: 1, id: 'p1' }],
      }),
    ).toBe('Full report');
  });

  it('returns undefined when workspace tabs are present (agentic fallback kept)', () => {
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        workspaceTabsCount: 1,
      }),
    ).toBeUndefined();
  });

  it('returns undefined when a subagent task plan has tasks (agentic fallback kept)', () => {
    const task: PlannedTask = {
      id: 't1',
      title: 'Research',
      description: '',
      taskType: 'research',
      priority: 1,
      status: 'running',
      durationMs: 0,
      steps: [],
    };
    const subPlan: TaskPlan = {
      ...minimalTaskPlan,
      id: 'sub',
      tasks: [task],
    };
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        taskPlansSubagent: { sub: subPlan },
      }),
    ).toBeUndefined();
  });

  it('routes to report area when taskKind is security (B strategy primary gate)', () => {
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        taskKind: 'security',
      }),
    ).toBeUndefined();
  });

  it('routes to report area when taskKind is research (B strategy primary gate)', () => {
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        taskKind: 'research',
      }),
    ).toBeUndefined();
  });

  it('taskKind dominates even when only a bare task plan is present', () => {
    expect(
      streamingConclusionForChat('Full report', {
        ...baseOpts,
        taskKind: 'security',
        taskPlan: minimalTaskPlan,
      }),
    ).toBeUndefined();
  });
});
