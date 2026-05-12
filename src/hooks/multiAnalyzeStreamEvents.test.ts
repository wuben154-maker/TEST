import { describe, expect, it, vi } from 'vitest';
import type { ThinkingEvent } from '@/types/analysis';
import type { PerProjectStreamingState } from '@/types/streaming';
import { createEmptyStreamingState } from '@/types/streaming';
import { handleMultiAnalyzeStreamEvent, type MultiStreamEventCtx, type MultiProjectStreamRefs } from './multiAnalyzeStreamEvents';

function makeRefs(overrides: Partial<MultiProjectStreamRefs> = {}): MultiProjectStreamRefs {
  return {
    hasTaskPlan: false,
    hasResearchRoute: false,
    activeRequestId: 'req-a',
    pendingRequestId: '',
    pendingInput: '',
    pendingLanguage: 'zh',
    timelineLocalSeq: 0,
    ...overrides,
  };
}

function makeCtx(params: {
  handleTaskPlan: (projectId: string, event: ThinkingEvent) => void;
}): MultiStreamEventCtx {
  return {
    logSSEEvent: vi.fn(),
    getProjectRefs: () => ({
      hasTaskPlan: false,
      hasResearchRoute: false,
      activeRequestId: 'req-a',
      pendingRequestId: '',
      pendingInput: '',
      pendingLanguage: 'zh',
      timelineLocalSeq: 0,
    }),
    updateState: vi.fn(),
    pendingStateRef: { current: new Map() },
    handleTaskPlan: params.handleTaskPlan,
    handleTaskCreate: vi.fn(),
    handleTaskUpdate: vi.fn(),
    handleDecisionRequest: vi.fn(),
    handleUnderstanding: vi.fn(),
    handleParameterRequest: vi.fn(),
    handleTaskStart: vi.fn(),
    handleTaskStep: vi.fn(),
    handleTaskComplete: vi.fn(),
    handlePlanComplete: vi.fn(),
    processConclusion: vi.fn(),
  };
}

const writeTodosEvent = (todos: Array<{ content: string; status?: string }>): ThinkingEvent =>
  ({
    type: 'tool_call',
    toolName: 'write_todos',
    toolInput: { todos },
    id: 'wt-call',
    schemaVersion: 1,
  }) as ThinkingEvent;

describe('handleMultiAnalyzeStreamEvent — write_todos synthetic task ids', () => {
  it('prefixes PlannedTask ids with main:todo:requestId:index to avoid collision with server numeric ids', () => {
    const handleTaskPlan = vi.fn();
    const ctx = makeCtx({ handleTaskPlan });
    const refs = makeRefs({ activeRequestId: 'abc-123' });
    const flags = { sawConclusionEvent: false, sawErrorEvent: false, sawDoneEvent: false, sawHitlAwaiting: false };

    handleMultiAnalyzeStreamEvent('p1', refs, 'zh', writeTodosEvent([{ content: 'One' }, { content: 'Two' }]), flags, ctx);

    expect(handleTaskPlan).toHaveBeenCalledTimes(1);
    const synthetic = handleTaskPlan.mock.calls[0][1] as ThinkingEvent;
    expect(synthetic.type).toBe('task_plan');
    expect(synthetic.scope).toBe('main');
    const plan = synthetic.plan!;
    expect(plan.tasks.map((t) => t.id)).toEqual(['main:todo:abc-123:0', 'main:todo:abc-123:1']);
  });

  it('uses distinct id namespaces when activeRequestId differs (same todo indices)', () => {
    const captured: string[][] = [];
    const handleTaskPlan = vi.fn((_pid, ev: ThinkingEvent) => {
      if (ev.plan?.tasks) captured.push(ev.plan.tasks.map((t) => t.id));
    });
    const ctx = makeCtx({ handleTaskPlan });
    const flags = { sawConclusionEvent: false, sawErrorEvent: false, sawDoneEvent: false, sawHitlAwaiting: false };

    const refs1 = makeRefs({ activeRequestId: 'run-1' });
    handleMultiAnalyzeStreamEvent('p1', refs1, 'zh', writeTodosEvent([{ content: 'A' }]), flags, ctx);

    const refs2 = makeRefs({ activeRequestId: 'run-2' });
    handleMultiAnalyzeStreamEvent('p1', refs2, 'zh', writeTodosEvent([{ content: 'B' }]), flags, ctx);

    expect(captured).toEqual([['main:todo:run-1:0'], ['main:todo:run-2:0']]);
    expect(captured[0]![0]).not.toBe(captured[1]![0]);
  });

  it('falls back to main:todo:wt:index when activeRequestId is empty', () => {
    const handleTaskPlan = vi.fn();
    const ctx = makeCtx({ handleTaskPlan });
    const refs = makeRefs({ activeRequestId: '' });
    const flags = { sawConclusionEvent: false, sawErrorEvent: false, sawDoneEvent: false, sawHitlAwaiting: false };

    handleMultiAnalyzeStreamEvent('p1', refs, 'zh', writeTodosEvent([{ content: 'X' }]), flags, ctx);

    const ev = handleTaskPlan.mock.calls[0][1] as ThinkingEvent;
    expect(ev.plan!.tasks[0]!.id).toBe('main:todo:wt:0');
  });
});

describe('handleMultiAnalyzeStreamEvent — task_error scoped buckets', () => {
  const runningTask = (id: string) => ({
    id,
    title: 't',
    description: '',
    taskType: 'security' as const,
    priority: 1,
    status: 'running' as const,
    durationMs: 0,
    steps: [],
  });

  const planWith = (tasks: ReturnType<typeof runningTask>[]) => ({
    id: 'p',
    tasks,
    isSingleTask: tasks.length === 1,
    totalDurationMs: 0,
    status: 'running' as const,
    createdAt: '',
  });

  it('updates only taskPlanMain when scope is main', () => {
    const ctx = makeCtx({ handleTaskPlan: vi.fn() });
    const mainPlan = planWith([runningTask('0')]);
    let state: PerProjectStreamingState = {
      ...createEmptyStreamingState(),
      taskPlanMain: mainPlan,
      taskPlansSubagent: { web: planWith([runningTask('0')]) },
    };
    ctx.updateState = vi.fn((_pid, fn) => {
      state = fn(state);
    });

    const flags = { sawConclusionEvent: false, sawErrorEvent: false, sawDoneEvent: false, sawHitlAwaiting: false };
    const refs = makeRefs();
    const ev: ThinkingEvent = {
      type: 'task_error',
      id: '0',
      scope: 'main',
      detail: 'boom',
      schemaVersion: 1,
    } as ThinkingEvent;

    handleMultiAnalyzeStreamEvent('p1', refs, 'zh', ev, flags, ctx);

    expect(state.taskPlanMain?.tasks[0]?.status).toBe('error');
    expect(state.taskPlansSubagent.web?.tasks[0]?.status).toBe('running');
  });

  it('updates only the matching subagent bucket when scope is subagent', () => {
    const ctx = makeCtx({ handleTaskPlan: vi.fn() });
    const task0 = runningTask('0');
    let state: PerProjectStreamingState = {
      ...createEmptyStreamingState(),
      taskPlanMain: planWith([{ ...task0 }]),
      taskPlansSubagent: {
        alpha: planWith([{ ...task0 }]),
        beta: planWith([{ ...task0 }]),
      },
    };
    ctx.updateState = vi.fn((_pid, fn) => {
      state = fn(state);
    });

    const flags = { sawConclusionEvent: false, sawErrorEvent: false, sawDoneEvent: false, sawHitlAwaiting: false };
    const refs = makeRefs();
    const ev: ThinkingEvent = {
      type: 'task_error',
      id: '0',
      scope: 'subagent',
      subagentName: 'alpha',
      detail: 'sub fail',
      schemaVersion: 1,
    } as ThinkingEvent;

    handleMultiAnalyzeStreamEvent('p1', refs, 'zh', ev, flags, ctx);

    expect(state.taskPlanMain?.tasks[0]?.status).toBe('running');
    expect(state.taskPlansSubagent.alpha?.tasks[0]?.status).toBe('error');
    expect(state.taskPlansSubagent.beta?.tasks[0]?.status).toBe('running');
  });
});

describe('handleMultiAnalyzeStreamEvent — ConductResearch grows task plan', () => {
  it('appends each ConductResearch call so task board total increases', () => {
    const ctx = makeCtx({ handleTaskPlan: vi.fn() });
    let state: PerProjectStreamingState = createEmptyStreamingState();
    ctx.updateState = vi.fn((_pid, fn) => {
      state = fn(state);
    });
    const flags = { sawConclusionEvent: false, sawErrorEvent: false, sawDoneEvent: false, sawHitlAwaiting: false };
    const refs = makeRefs();

    handleMultiAnalyzeStreamEvent(
      'p1',
      refs,
      'en',
      {
        type: 'tool_call',
        toolName: 'ConductResearch',
        id: 'cr-1',
        toolInput: { research_topic: 'Alpha' },
        scope: 'main',
        schemaVersion: 1,
      } as ThinkingEvent,
      flags,
      ctx,
    );
    handleMultiAnalyzeStreamEvent(
      'p1',
      refs,
      'en',
      {
        type: 'tool_call',
        toolName: 'ConductResearch',
        id: 'cr-2',
        toolInput: { research_topic: 'Beta' },
        scope: 'main',
        schemaVersion: 1,
      } as ThinkingEvent,
      flags,
      ctx,
    );

    expect(state.taskPlanMain?.tasks.map((t) => t.id)).toEqual(['cr-1', 'cr-2']);
    expect(refs.hasTaskPlan).toBe(true);
  });

  it('marks matching id success on ConductResearch tool_result', () => {
    const ctx = makeCtx({ handleTaskPlan: vi.fn() });
    let state: PerProjectStreamingState = createEmptyStreamingState();
    ctx.updateState = vi.fn((_pid, fn) => {
      state = fn(state);
    });
    const flags = { sawConclusionEvent: false, sawErrorEvent: false, sawDoneEvent: false, sawHitlAwaiting: false };
    const refs = makeRefs();

    handleMultiAnalyzeStreamEvent(
      'p1',
      refs,
      'en',
      {
        type: 'tool_call',
        toolName: 'ConductResearch',
        id: 'cr-x',
        toolInput: { research_topic: 'Z' },
        scope: 'main',
        schemaVersion: 1,
      } as ThinkingEvent,
      flags,
      ctx,
    );
    handleMultiAnalyzeStreamEvent(
      'p1',
      refs,
      'en',
      {
        type: 'tool_result',
        toolName: 'ConductResearch',
        id: 'cr-x',
        scope: 'main',
        schemaVersion: 1,
      } as ThinkingEvent,
      flags,
      ctx,
    );

    expect(state.taskPlanMain?.tasks[0]?.status).toBe('success');
  });
});

describe('handleMultiAnalyzeStreamEvent — conclusion vs stream requestId', () => {
  it('processes conclusion when requestId differs from activeRequestId (main graph id vs HTTP stream)', () => {
    const processConclusion = vi.fn();
    const base = makeCtx({ handleTaskPlan: vi.fn() });
    const ctx: MultiStreamEventCtx = { ...base, processConclusion };
    let state = createEmptyStreamingState();
    ctx.updateState = vi.fn((_pid, fn) => {
      state = fn(state);
    });
    const refs = makeRefs({ activeRequestId: 'd3521708-resume-stream' });
    const ev = {
      type: 'conclusion',
      requestId: '019d568f-parent-or-graph',
      content: '{"title":"Report","summary":"Done"}',
      schemaVersion: 1,
    } as ThinkingEvent;
    const flags = {
      sawConclusionEvent: false,
      sawErrorEvent: false,
      sawDoneEvent: false,
      sawHitlAwaiting: false,
    };

    const skip = handleMultiAnalyzeStreamEvent('p1', refs, 'en', ev, flags, ctx);

    expect(skip).toBe(false);
    expect(flags.sawConclusionEvent).toBe(true);
    expect(processConclusion).toHaveBeenCalledWith(
      'p1',
      '{"title":"Report","summary":"Done"}',
      '',
      'en',
    );
    expect(state.conclusion).toContain('Report');
  });
});

describe('handleMultiAnalyzeStreamEvent — HITL vs stream requestId', () => {
  it('uses interruptRequestId for HITL resume correlation', () => {
    const handleParameterRequest = vi.fn();
    const base = makeCtx({ handleTaskPlan: vi.fn() });
    const ctx: MultiStreamEventCtx = { ...base, handleParameterRequest };
    const refs = makeRefs({ activeRequestId: '019d568f-stream-uuid' });
    const ev = {
      type: 'parameter_request',
      requestId: '019d568f-stream-uuid',
      interruptRequestId: 'dr-clarify-cb9',
      id: 'dr-clarify-cb9',
      schemaVersion: 1,
      parameterRequests: [
        {
          id: 'reply',
          name: 'Reply',
          description: 'Answer',
          paramType: 'text' as const,
          required: true,
          encrypted: false,
        },
      ],
    } as ThinkingEvent;
    const flags = {
      sawConclusionEvent: false,
      sawErrorEvent: false,
      sawDoneEvent: false,
      sawHitlAwaiting: false,
    };

    const skip = handleMultiAnalyzeStreamEvent('p1', refs, 'zh', ev, flags, ctx);

    expect(skip).toBe(false);
    expect(ctx.updateState).toHaveBeenCalled();
    expect(handleParameterRequest).toHaveBeenCalledWith('p1', ev);
    expect(refs.pendingRequestId).toBe('dr-clarify-cb9');
  });

  it('still drops mismatched requestId for non-HITL events', () => {
    const ctx = makeCtx({ handleTaskPlan: vi.fn() });
    const refs = makeRefs({ activeRequestId: 'req-a' });
    const ev = {
      type: 'tool_call',
      toolName: 'some_tool',
      requestId: 'other-stream',
      id: 'call-x',
      schemaVersion: 1,
    } as ThinkingEvent;
    const flags = {
      sawConclusionEvent: false,
      sawErrorEvent: false,
      sawDoneEvent: false,
      sawHitlAwaiting: false,
    };

    const skip = handleMultiAnalyzeStreamEvent('p1', refs, 'zh', ev, flags, ctx);

    expect(skip).toBe(true);
    expect(ctx.updateState).not.toHaveBeenCalled();
  });
});
