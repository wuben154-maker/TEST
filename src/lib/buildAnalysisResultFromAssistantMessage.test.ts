import { describe, expect, it } from 'vitest';
import {
  assistantMessageYieldsAnalysisTab,
  buildAnalysisResultFromAssistantMessage,
} from './buildAnalysisResultFromAssistantMessage';
import type { ConversationMessage } from '@/types/project';
import type { TaskPlan } from '@/types/analysis';

// A plan with at least one executed task — mirrors a real finalize-time plan.
// An all-pending plan must NOT yield an analysis tab (see
// taskPlanHasStartedExecution in analysisWorkspaceChrome).
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

const pendingOnlyTaskPlan: TaskPlan = {
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

describe('assistantMessageYieldsAnalysisTab', () => {
  it('is true when blocks were produced', () => {
    const msg: ConversationMessage = {
      id: 'assistant-blocks',
      type: 'assistant',
      content: '',
      reasoning: '',
      blocks: [
        { id: 'b1', type: 'analysis', title: 'x', content: 'y', timestamp: new Date() },
      ],
      timestamp: new Date(),
      timeline: [],
    };
    expect(assistantMessageYieldsAnalysisTab(msg)).toBe(true);
  });

  it('is false when only tool calls executed but no blocks and no workspace tabs', () => {
    // HITL-resume scenario: agent calls an internal helper (write_todos / ls / read)
    // once, then produces only a conversational conclusion ("please upload the file").
    // Neither a block nor a workspace tab is emitted. The Report panel of a tab for
    // this turn would literally say "No report content" → do not create the tab.
    const msg: ConversationMessage = {
      id: 'assistant-toolcalls-only',
      type: 'assistant',
      content: '请您上传需要分析的二进制文件到工作区。',
      reasoning: '',
      blocks: [],
      timestamp: new Date(),
      taskPlan: minimalTaskPlan,
      workspaceTabs: [],
      stats: { toolCallCount: 1 },
      timeline: [],
    };
    expect(assistantMessageYieldsAnalysisTab(msg)).toBe(false);
  });

  it('is true when workspace tab instances exist', () => {
    const msg: ConversationMessage = {
      id: 'assistant-wstabs',
      type: 'assistant',
      content: '',
      reasoning: '',
      blocks: [],
      timestamp: new Date(),
      workspaceTabs: [
        {
          id: 'shell-1',
          title: 'Shell',
          kind: 'shell',
          createdAt: new Date().toISOString(),
          payload: { commands: [] } as never,
        },
      ],
      timeline: [],
    };
    expect(assistantMessageYieldsAnalysisTab(msg)).toBe(true);
  });

  it('is false for plain assistant with no blocks and no agentic signals', () => {
    const msg: ConversationMessage = {
      id: 'assistant-plain',
      type: 'assistant',
      content: 'Hello',
      reasoning: '',
      blocks: [],
      timestamp: new Date(),
      timeline: [],
    };
    expect(assistantMessageYieldsAnalysisTab(msg)).toBe(false);
  });

  it('is false for HITL-aborted turn whose task plan never executed any task', () => {
    // Scenario: user asks "analyse this binary file" → agent plans → parameter_request
    // (asking for the file path) → user replies "I haven't uploaded yet" → agent
    // concludes "please upload the file" and the turn ends without running any task.
    // The turn must NOT pop open a report tab — it is a plain conversational reply.
    const msg: ConversationMessage = {
      id: 'assistant-hitl-abort',
      type: 'assistant',
      content: '请上传相关内容后我再进行分析。',
      reasoning: '',
      blocks: [],
      timestamp: new Date(),
      taskPlan: pendingOnlyTaskPlan,
      timeline: [],
    };
    expect(assistantMessageYieldsAnalysisTab(msg)).toBe(false);
  });

  it('is false for HITL-aborted turn even if a task reached `running` before interrupt', () => {
    // Realistic HITL scenario: agent plans + starts T1 (status='running') and then T1
    // emits a parameter_request. User replies conversationally → turn ends with no
    // tool_call, no block, no workspace tab. The plan shows a running task but no
    // observable output exists, so still NO report tab.
    const runningOnlyPlan: TaskPlan = {
      id: 'task-plan-running',
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
    const msg: ConversationMessage = {
      id: 'assistant-hitl-running',
      type: 'assistant',
      content: '请上传相关内容后我再进行分析。',
      reasoning: '',
      blocks: [],
      timestamp: new Date(),
      taskPlan: runningOnlyPlan,
      workspaceTabs: [],
      stats: {},
      timeline: [],
    };
    expect(assistantMessageYieldsAnalysisTab(msg)).toBe(false);
  });
});

describe('buildAnalysisResultFromAssistantMessage', () => {
  it('uses empty blocks array when message has no blocks', () => {
    const assistant: ConversationMessage = {
      id: 'a',
      type: 'assistant',
      content: '',
      reasoning: '',
      blocks: [],
      timestamp: new Date(),
      taskPlan: minimalTaskPlan,
      workspaceTabs: [],
      timeline: [],
    };
    const user: ConversationMessage = {
      id: 'u',
      type: 'user',
      content: 'Q',
      timestamp: new Date(),
    };
    const r = buildAnalysisResultFromAssistantMessage(assistant, [user, assistant], 'Analysis', 0);
    expect(r.blocks).toEqual([]);
    expect(r.useWorkspaceTaskPanel).toBe(true);
  });

  it('hydrates stats.taskKind=security with full SecurityStats from persisted message', () => {
    // Simulates the full round-trip after a page refresh:
    //   DB row → rowToConversation (loads `stats` from JSONB) → ConversationMessage.stats
    //   → buildAnalysisResultFromAssistantMessage → AnalysisResult.stats
    // TaskStatsBar consumes `result.stats` and renders the 5-chip security profile.
    const assistant: ConversationMessage = {
      id: 'a-sec',
      type: 'assistant',
      content: 'web shell detected',
      reasoning: '',
      blocks: [
        { type: 'analysis', id: 'b1', content: 'report body', title: 'Report' } as never,
      ],
      timestamp: new Date(),
      workspaceTabs: [],
      timeline: [],
      stats: {
        taskKind: 'security',
        security: {
          severity: 'high',
          riskScore: 82,
          actionable: { total: 2, critical: 0, high: 1, medium: 1 },
          threatClasses: ['web_shell', 'sqli'],
          validation: ['static', 'yara', 'sandbox'],
        },
      },
    };
    const user: ConversationMessage = {
      id: 'u',
      type: 'user',
      content: 'Q',
      timestamp: new Date(),
    };
    const r = buildAnalysisResultFromAssistantMessage(
      assistant,
      [user, assistant],
      'Analysis',
      0,
    );
    expect(r.stats?.taskKind).toBe('security');
    expect(r.stats?.security?.severity).toBe('high');
    expect(r.stats?.security?.riskScore).toBe(82);
    expect(r.stats?.security?.actionable).toEqual({
      total: 2,
      critical: 0,
      high: 1,
      medium: 1,
    });
    expect(r.stats?.security?.threatClasses).toEqual(['web_shell', 'sqli']);
    expect(r.stats?.security?.validation).toEqual(['static', 'yara', 'sandbox']);
  });

  it('hydrates stats.taskKind=research with full ResearchStats from persisted message', () => {
    const assistant: ConversationMessage = {
      id: 'a-res',
      type: 'assistant',
      content: 'research report body',
      reasoning: '',
      blocks: [
        { type: 'analysis', id: 'b1', content: 'report body', title: 'Report' } as never,
      ],
      timestamp: new Date(),
      workspaceTabs: [],
      timeline: [],
      stats: {
        taskKind: 'research',
        research: {
          keyFindings: 5,
          recommendations: 3,
          sources: 12,
          freshness: '<=30d',
          gaps: 2,
        },
      },
    };
    const user: ConversationMessage = {
      id: 'u',
      type: 'user',
      content: 'Q',
      timestamp: new Date(),
    };
    const r = buildAnalysisResultFromAssistantMessage(
      assistant,
      [user, assistant],
      'Analysis',
      0,
    );
    expect(r.stats?.taskKind).toBe('research');
    expect(r.stats?.research?.keyFindings).toBe(5);
    expect(r.stats?.research?.recommendations).toBe(3);
    expect(r.stats?.research?.sources).toBe(12);
    expect(r.stats?.research?.freshness).toBe('<=30d');
    expect(r.stats?.research?.gaps).toBe(2);
  });
});
