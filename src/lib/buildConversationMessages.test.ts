import { describe, expect, it } from 'vitest';
import { buildConversationMessages } from './buildConversationMessages';
import { createEmptyStreamingState } from '@/types/streaming';
import type { TaskPlan } from '@/types/analysis';

// An agentic (task_plan) turn must include at least one task that has actually
// executed. A plan whose tasks are all still `pending` represents a HITL-aborted
// turn (agent planned, then asked for input, user replied conversationally) and
// is intentionally treated as a plain chat reply — see
// `taskPlanHasStartedExecution` in `src/lib/analysisWorkspaceChrome.ts`.
const minimalTaskPlan: TaskPlan = {
  id: 'task-plan',
  tasks: [
    {
      id: 't1',
      title: 'T',
      description: '',
      taskType: 'security',
      priority: 0,
      status: 'success',
      durationMs: 0,
      steps: [],
    },
  ],
  isSingleTask: true,
  totalDurationMs: 0,
  status: 'success',
  createdAt: '',
};

describe('buildConversationMessages', () => {
  it('keeps assistant chat empty for task_plan turns even when workspace has no blocks (no conclusion duplicate)', () => {
    const base = createEmptyStreamingState();
    const state = {
      ...base,
      userInput: 'What is 2+2?',
      inputTimestamp: new Date(),
      taskPlanMain: minimalTaskPlan,
      conclusion: 'The answer is 4.',
      timeline: [
        {
          type: 'reasoning',
          id: 'r1',
          seq: 1,
          content: 'thinking',
          turn: 1,
          schemaVersion: 1,
          scope: 'main',
        },
      ],
    };
    const msgs = buildConversationMessages(state);
    expect(msgs).not.toBeNull();
    const assistant = msgs![1];
    expect(assistant.content).toBe('');
  });

  it('propagates statsMeta from streaming state into assistant message stats (security profile)', () => {
    const base = createEmptyStreamingState();
    const state = {
      ...base,
      userInput: 'Scan this url',
      inputTimestamp: new Date(),
      taskPlanMain: minimalTaskPlan,
      conclusion: 'Done',
      resultStartTime: Date.now() - 5_000,
      toolCallCount: 3,
      sandboxRunCount: 0,
      statsMeta: {
        taskKind: 'security' as const,
        security: {
          severity: 'high' as const,
          riskScore: 78,
          threatClasses: ['XSS', 'SQLi'],
          validation: ['static', 'yara'] as Array<'static' | 'yara' | 'sandbox' | 'ti'>,
        },
      },
    };
    const msgs = buildConversationMessages(state);
    expect(msgs).not.toBeNull();
    const stats = msgs![1].stats!;
    expect(stats.taskKind).toBe('security');
    expect(stats.security?.severity).toBe('high');
    expect(stats.security?.riskScore).toBe(78);
    expect(stats.security?.threatClasses).toEqual(['XSS', 'SQLi']);
    expect(stats.toolCallCount).toBe(3);
  });

  it('propagates statsMeta from streaming state into assistant message stats (research profile)', () => {
    const base = createEmptyStreamingState();
    const state = {
      ...base,
      userInput: 'Research AI trends',
      inputTimestamp: new Date(),
      taskPlanMain: minimalTaskPlan,
      conclusion: 'Done',
      statsMeta: {
        taskKind: 'research' as const,
        research: {
          keyFindings: 5,
          recommendations: 2,
          sources: 14,
          freshness: '<=30d' as const,
          gaps: 1,
        },
      },
    };
    const msgs = buildConversationMessages(state);
    const stats = msgs![1].stats!;
    expect(stats.taskKind).toBe('research');
    expect(stats.research?.keyFindings).toBe(5);
    expect(stats.research?.sources).toBe(14);
    expect(stats.research?.freshness).toBe('<=30d');
    expect(stats.security).toBeUndefined();
  });

  it('omits taskKind/security/research when no statsMeta was captured', () => {
    const base = createEmptyStreamingState();
    const state = {
      ...base,
      userInput: 'hi',
      inputTimestamp: new Date(),
      taskPlanMain: minimalTaskPlan,
      conclusion: 'hello',
    };
    const msgs = buildConversationMessages(state);
    const stats = msgs![1].stats;
    // Either stats omitted entirely, or present but without task-profile keys.
    expect(stats?.taskKind).toBeUndefined();
    expect(stats?.security).toBeUndefined();
    expect(stats?.research).toBeUndefined();
  });

  it('preserves conversational conclusion when task plan exists but never started (HITL-abort)', () => {
    // Scenario: user asks to analyse a binary file → agent plans → hits
    // parameter_request → user replies "I haven't uploaded yet" → agent says
    // "please upload relevant content" and the turn ends. All tasks are still
    // `pending`, so the message should behave like a plain chat reply: content
    // must carry the conclusion instead of being cleared as an "agentic turn".
    const base = createEmptyStreamingState();
    const pendingOnlyPlan: TaskPlan = {
      id: 'task-plan-pending',
      tasks: [
        {
          id: 't1',
          title: 'T',
          description: '',
          taskType: 'security',
          priority: 0,
          status: 'pending',
          durationMs: 0,
          steps: [],
        },
      ],
      isSingleTask: true,
      totalDurationMs: 0,
      status: 'pending',
      createdAt: '',
    };
    const state = {
      ...base,
      userInput: '帮我分析二进制文件',
      inputTimestamp: new Date(),
      taskPlanMain: pendingOnlyPlan,
      conclusion: '请上传相关内容后我再进行分析。',
    };
    const msgs = buildConversationMessages(state);
    expect(msgs).not.toBeNull();
    expect(msgs![1].content).toBe('请上传相关内容后我再进行分析。');
  });

  it('keeps chat empty when task_plan and workspace blocks exist (full report in workspace)', () => {
    const base = createEmptyStreamingState();
    const state = {
      ...base,
      userInput: 'Analyze',
      inputTimestamp: new Date(),
      taskPlanMain: minimalTaskPlan,
      conclusion: 'Summary line',
      blocks: [
        {
          type: 'summary',
          id: 'summary-1',
          severity: 'info' as const,
          title: 'Report',
          description: 'Details',
        },
      ],
      timeline: [
        {
          type: 'reasoning',
          id: 'r1',
          seq: 1,
          content: 'x',
          turn: 1,
          schemaVersion: 1,
          scope: 'main',
        },
      ],
    };
    const msgs = buildConversationMessages(state);
    expect(msgs).not.toBeNull();
    expect(msgs![1].content).toBe('');
  });

  it('fills assistant requestId from completedRequestId when currentRequestId is cleared (post-stream finalize)', () => {
    const base = createEmptyStreamingState();
    const state = {
      ...base,
      userInput: 'x',
      inputTimestamp: new Date(),
      taskPlanMain: minimalTaskPlan,
      currentRequestId: '',
      completedRequestId: 'req-finish-xyz',
      timeline: [
        {
          type: 'reasoning' as const,
          id: 'r1',
          seq: 1,
          content: 'y',
          turn: 1,
          schemaVersion: 1,
          scope: 'main',
        },
      ],
    };
    const msgs = buildConversationMessages(state);
    expect(msgs).not.toBeNull();
    expect(msgs![1].requestId).toBe('req-finish-xyz');
  });
});
