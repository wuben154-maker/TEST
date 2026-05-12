import { describe, expect, it } from 'vitest';
import type { AnalysisTimelineEntry } from '@/types/analysis';
import { toolOutputTimelineMaxChars } from '@/lib/config';
import {
  buildReActTimeline,
  coalesceThinkingBlocksAcrossTools,
  foldResearchTaskListBuckets,
  mergeConsecutiveReasoningTimelineRows,
  mergeResearchTaskListsIntoBlocks,
} from '@/lib/buildReActTimeline';

function entry(p: Partial<AnalysisTimelineEntry> & { type: string; seq: number }): AnalysisTimelineEntry {
  return { schemaVersion: 1, ...p } as AnalysisTimelineEntry;
}

describe('buildReActTimeline', () => {
  it('synthesizes thinking/result blocks from offline context when timeline is empty', () => {
    const blocks = buildReActTimeline([], {
      language: 'en',
      offline: {
        understanding: {
          inputType: 'text',
          summary: 'S',
          reasoningSummary: 'R',
          keyEntities: [],
          analysisGoals: [],
          suggestedApproach: '',
          confidence: 0.9,
        },
        streamReasoningFallback: 'live',
        extraSummary: { taskSummary: 'Done' },
      },
    });
    expect(blocks.some((b) => b.kind === 'thinking')).toBe(true);
    expect(blocks.some((b) => b.kind === 'result' && b.summary === 'Done')).toBe(true);
  });

  it('merges deep-research phase steps at min seq with latest status (no duplicate rows)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'step',
        seq: 1,
        id: 'dr-pre-clarify',
        phaseId: 'deep_research_clarify',
        label: 'Clarify phase',
        status: 'running',
        scope: 'subagent',
      }),
      entry({
        type: 'step',
        seq: 10,
        id: 'dr-phase-deep_research_clarify-success',
        phaseId: 'deep_research_clarify',
        label: 'Clarify phase',
        status: 'success',
        scope: 'subagent',
      }),
      entry({
        type: 'step',
        seq: 11,
        id: 'dr-phase-deep_research_plan-running',
        phaseId: 'deep_research_plan',
        label: 'Plan phase',
        status: 'running',
        scope: 'subagent',
      }),
      entry({
        type: 'step',
        seq: 20,
        id: 'dr-phase-deep_research_plan-success',
        phaseId: 'deep_research_plan',
        label: 'Plan phase',
        status: 'success',
        scope: 'subagent',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const steps = blocks.filter((b) => b.kind === 'step');
    expect(steps).toHaveLength(2);
    expect(steps[0]).toMatchObject({ label: 'Clarify phase', status: 'success' });
    expect(steps[1]).toMatchObject({ label: 'Plan phase', status: 'success' });
  });

  it('task-running step leads buffered subagent reasoning (same slot flush as phase milestones)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'before task row',
        turn: 1,
        scope: 'subagent',
      }),
      entry({
        type: 'step',
        seq: 2,
        id: 'task-running-call_x',
        label: 'Deep research',
        status: 'running',
        scope: 'subagent',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks[0]?.kind).toBe('step');
    expect(blocks[1]?.kind).toBe('thinking');
  });

  it('deep_research_collect step comes after buffered stream (after write brief), not before', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'research brief body',
        turn: 1,
        scope: 'subagent',
      }),
      entry({
        type: 'step',
        seq: 2,
        id: 'dr-phase-deep_research_collect-running',
        phaseId: 'deep_research_collect',
        label: 'Collect',
        status: 'running',
        scope: 'subagent',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks[0]?.kind).toBe('thinking');
    expect(blocks[1]?.kind).toBe('step');
    expect((blocks[0] as { reasoning: string }).reasoning).toContain('brief');
  });

  it('renders deep-research phase step before buffered reasoning that has lower seq (milestone leads)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'model thought before phase row',
        turn: 1,
        scope: 'subagent',
      }),
      entry({
        type: 'step',
        seq: 2,
        id: 'dr-pre-clarify',
        phaseId: 'deep_research_clarify',
        label: 'Clarify phase',
        status: 'running',
        scope: 'subagent',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks[0]?.kind).toBe('step');
    expect(blocks[1]?.kind).toBe('thinking');
    expect((blocks[1] as { reasoning: string }).reasoning).toContain('model thought');
  });

  it('places merged deep-research phase step at first seq, not after later success seq', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 5,
        id: 't1',
        toolName: 'read_file',
        toolInput: { file_path: 'a.ts' },
        turn: 1,
      }),
      entry({
        type: 'step',
        seq: 6,
        id: 'dr-pre',
        phaseId: 'deep_research_clarify',
        label: 'Clarify',
        status: 'running',
        scope: 'subagent',
      }),
      entry({
        type: 'tool_call',
        seq: 7,
        id: 't2',
        toolName: 'read_file',
        toolInput: { file_path: 'b.ts' },
        turn: 1,
      }),
      entry({
        type: 'step',
        seq: 100,
        id: 'dr-phase-deep_research_clarify-success',
        phaseId: 'deep_research_clarify',
        label: 'Clarify',
        status: 'success',
        scope: 'subagent',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const kinds = blocks.map((b) => b.kind);
    const iStep = kinds.indexOf('step');
    const iToolBefore = kinds.lastIndexOf('tool_execution', iStep);
    const iToolAfter = kinds.findIndex((k, i) => i > iStep && k === 'tool_execution');
    expect(iToolBefore).toBeGreaterThanOrEqual(0);
    expect(iStep).toBeGreaterThan(iToolBefore);
    expect(iToolAfter).toBeGreaterThan(iStep);
    expect(blocks[iStep]).toMatchObject({ kind: 'step', status: 'success', label: 'Clarify' });
  });

  it('deep_research_plan step comes after clarify stream, before brief stream', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'clarify reasoning output',
        turn: 1,
        scope: 'subagent',
      }),
      entry({
        type: 'step',
        seq: 2,
        id: 'dr-phase-deep_research_plan-running',
        phaseId: 'deep_research_plan',
        label: 'Define brief',
        status: 'running',
        scope: 'subagent',
      }),
      entry({
        type: 'reasoning',
        seq: 3,
        content: 'brief body text',
        turn: 2,
        scope: 'subagent',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks[0]?.kind).toBe('thinking');
    expect((blocks[0] as { reasoning: string }).reasoning).toContain('clarify');
    expect(blocks[1]?.kind).toBe('step');
    expect((blocks[1] as { label: string }).label).toBe('Define brief');
    expect(blocks[2]?.kind).toBe('thinking');
    expect((blocks[2] as { reasoning: string }).reasoning).toContain('brief');
  });

  it('full four-phase deep research: each label appears after prior stream, before own stream', () => {
    const rows: AnalysisTimelineEntry[] = [
      // Phase 1: clarify (pre-start, then reasoning)
      entry({ type: 'step', seq: 1, id: 'dr-pre-clarify', phaseId: 'deep_research_clarify', label: 'Clarify', status: 'running', scope: 'subagent' }),
      entry({ type: 'reasoning', seq: 2, content: 'clarify output', turn: 1, scope: 'subagent' }),
      // Transition: clarify success + plan running
      entry({ type: 'step', seq: 10, id: 'dr-phase-deep_research_clarify-success', phaseId: 'deep_research_clarify', label: 'Clarify', status: 'success', scope: 'subagent' }),
      entry({ type: 'step', seq: 11, id: 'dr-phase-deep_research_plan-running', phaseId: 'deep_research_plan', label: 'Plan', status: 'running', scope: 'subagent' }),
      // Phase 2: write_research_brief reasoning
      entry({ type: 'reasoning', seq: 12, content: 'brief output', turn: 2, scope: 'subagent' }),
      // Transition: plan success + collect running
      entry({ type: 'step', seq: 20, id: 'dr-phase-deep_research_plan-success', phaseId: 'deep_research_plan', label: 'Plan', status: 'success', scope: 'subagent' }),
      entry({ type: 'step', seq: 21, id: 'dr-phase-deep_research_collect-running', phaseId: 'deep_research_collect', label: 'Collect', status: 'running', scope: 'subagent' }),
      // Phase 3: ConductResearch tool calls
      entry({ type: 'tool_call', seq: 22, id: 'cr-1', toolName: 'ConductResearch', toolInput: { research_topic: 'Topic A' }, scope: 'subagent' }),
      entry({ type: 'tool_result', seq: 23, id: 'cr-1', toolName: 'ConductResearch', scope: 'subagent' }),
      // Transition: collect success + report running
      entry({ type: 'step', seq: 30, id: 'dr-phase-deep_research_collect-success', phaseId: 'deep_research_collect', label: 'Collect', status: 'success', scope: 'subagent' }),
      entry({ type: 'step', seq: 31, id: 'dr-phase-deep_research_report-running', phaseId: 'deep_research_report', label: 'Report', status: 'running', scope: 'subagent' }),
      // Phase 4: final report reasoning
      entry({ type: 'reasoning', seq: 32, content: 'final report', turn: 3, scope: 'subagent' }),
      entry({ type: 'step', seq: 40, id: 'dr-phase-deep_research_report-success', phaseId: 'deep_research_report', label: 'Report', status: 'success', scope: 'subagent' }),
    ];
    const blocks = buildReActTimeline(rows);
    const labels = blocks.map((b) => {
      if (b.kind === 'step') return `STEP:${(b as { label: string }).label}`;
      if (b.kind === 'thinking') return `THINK:${(b as { reasoning: string }).reasoning.slice(0, 15)}`;
      if (b.kind === 'task_list') return 'TASKS';
      return b.kind;
    });
    // Expected: Clarify → clarify stream → Plan → brief stream → Collect → research tasks → Report → final stream
    expect(labels).toEqual([
      'STEP:Clarify',
      'THINK:clarify output',
      'STEP:Plan',
      'THINK:brief output',
      'STEP:Collect',
      'TASKS',
      'STEP:Report',
      'THINK:final report',
    ]);
  });

  it('merges reasoning and answer by turn then tool execution', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'reasoning', seq: 1, content: 'think', turn: 1 }),
      entry({ type: 'answer', seq: 2, content: 'Hello user', turn: 1 }),
      entry({
        type: 'tool_call',
        seq: 3,
        id: 'tc1',
        toolName: 'read_file',
        toolInput: { file_path: 'app/x.ts' },
        turn: 1,
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    expect(blocks[0]).toMatchObject({
      kind: 'thinking',
      reasoning: 'think',
      answer: 'Hello user',
      turn: 1,
    });
    expect(blocks[1]?.kind).toBe('tool_execution');
    const te = blocks[1] as {
      kind: 'tool_execution';
      children: { toolName: string; detail: string; done: boolean }[];
    };
    expect(te.children.length).toBeGreaterThan(0);
    const row = te.children[0];
    expect(row.toolName).toBe('read file');
    expect(row.detail).toContain('x.ts');
    expect(row.done).toBe(false);
  });

  it('marks tool_execution child done when tool_result arrives', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 1,
        id: 'tc1',
        toolName: 'read_file',
        toolInput: { file_path: 'a.ts' },
      }),
      entry({ type: 'tool_result', seq: 2, id: 'tc1', toolOutput: { ok: true } }),
    ];
    const blocks = buildReActTimeline(rows);
    const te = blocks.find((b) => b.kind === 'tool_execution') as {
      kind: 'tool_execution';
      children: { done: boolean }[];
    };
    expect(te?.children[0]?.done).toBe(true);
  });

  it('merges orphan answer-only thinking block after llm_invoke_end into prior reasoning block', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_invoke_start', seq: 1, invokeId: 'i1' }),
      entry({ type: 'llm_delta', seq: 2, channel: 'reasoning', content: 'inner monologue', invokeId: 'i1' }),
      entry({ type: 'llm_invoke_end', seq: 3, invokeId: 'i1', timestamp: 1000 }),
      entry({ type: 'llm_delta', seq: 4, channel: 'text', content: 'Visible reply', invokeId: 'i1' }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const thinking = blocks.filter((b) => b.kind === 'thinking');
    expect(thinking).toHaveLength(1);
    expect(thinking[0]).toMatchObject({
      kind: 'thinking',
      reasoning: 'inner monologue',
      answer: 'Visible reply',
    });
  });

  it('does not merge orphan answer when tool_call sits between invoke_end and text', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_invoke_start', seq: 1, invokeId: 'i1' }),
      entry({ type: 'llm_delta', seq: 2, channel: 'reasoning', content: 'think', invokeId: 'i1' }),
      entry({ type: 'llm_invoke_end', seq: 3, invokeId: 'i1', timestamp: 1000 }),
      entry({
        type: 'tool_call',
        seq: 4,
        id: 'tc1',
        toolName: 'read_file',
        toolInput: { file_path: 'x.ts' },
      }),
      entry({ type: 'llm_delta', seq: 5, channel: 'text', content: 'Hi', invokeId: 'i1' }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const thinking = blocks.filter((b) => b.kind === 'thinking');
    expect(thinking).toHaveLength(2);
    expect((thinking[0] as { answer: string }).answer).toBe('');
    expect((thinking[1] as { reasoning: string; answer: string }).reasoning).toBe('');
    expect((thinking[1] as { answer: string }).answer).toBe('Hi');
  });

  it('sets invokeStartMs on open invoke for live duration UI', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_invoke_start', seq: 1, invokeId: 'i1', timestamp: 1_700_000_000_000 }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks[0]).toMatchObject({
      kind: 'thinking',
      invokeState: 'running',
      invokeStartMs: 1_700_000_000_000,
      reasoning: '',
      answer: '',
    });
  });

  it('sets invokeStartMs on running invoke with text-only stream', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_invoke_start', seq: 1, invokeId: 'i1', timestamp: 1000 }),
      entry({ type: 'llm_delta', seq: 2, channel: 'text', content: 'Hi', invokeId: 'i1' }),
    ];
    const blocks = buildReActTimeline(rows);
    const th = blocks.find((b) => b.kind === 'thinking');
    expect(th).toMatchObject({
      kind: 'thinking',
      invokeState: 'running',
      invokeStartMs: 1000,
      reasoning: '',
      answer: 'Hi',
    });
  });

  it('subagent llm_invoke_start + text delta yields running thinking with invokeStartMs', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'llm_invoke_start',
        seq: 22,
        invokeId: '4c7097c0b1da',
        scope: 'subagent',
        subagentStream: true,
        subagentName: 'web-security',
        turn: 1,
        timestamp: 1774944048338,
      }),
      entry({
        type: 'llm_delta',
        seq: 23,
        channel: 'text',
        content: '现在让我提取IOC信息：',
        invokeId: '4c7097c0b1da',
        scope: 'subagent',
        subagentStream: true,
        subagentName: 'web-security',
        turn: 1,
      }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks[0]).toMatchObject({
      kind: 'step',
      stepVariant: 'delegation_group',
    });
    const th = blocks.find((b) => b.kind === 'thinking');
    expect(th).toMatchObject({
      kind: 'thinking',
      invokeState: 'running',
      invokeStartMs: 1774944048338,
      reasoning: '',
      answer: '现在让我提取IOC信息：',
    });
  });

  it('flushes main reasoning before subagent invoke+delta (separate thinking blocks)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'reasoning', seq: 1, content: 'main plan', scope: 'main', turn: 1 }),
      entry({
        type: 'llm_invoke_start',
        seq: 11,
        invokeId: 'acfc4d6adfb0',
        scope: 'subagent',
        subagentStream: true,
        subagentName: 'web-security',
        turn: 1,
        timestamp: 1774947029263,
      }),
      entry({
        type: 'llm_delta',
        seq: 12,
        channel: 'text',
        content: 'sub reply',
        scope: 'subagent',
        subagentStream: true,
        invokeId: 'acfc4d6adfb0',
        turn: 1,
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const thinking = blocks.filter((b) => b.kind === 'thinking');
    expect(thinking).toHaveLength(2);
    expect(thinking[0]).toMatchObject({
      kind: 'thinking',
      reasoning: 'main plan',
      answer: '',
    });
    expect(thinking[1]).toMatchObject({
      kind: 'thinking',
      invokeState: 'running',
      invokeStartMs: 1774947029263,
      answer: 'sub reply',
    });
  });

  it('does not set invokeStartMs on completed invoke', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_invoke_start', seq: 1, invokeId: 'i1', timestamp: 1000 }),
      entry({ type: 'llm_delta', seq: 2, channel: 'text', content: 'Hi', invokeId: 'i1' }),
      entry({ type: 'llm_invoke_end', seq: 3, invokeId: 'i1', timestamp: 4000 }),
    ];
    const blocks = buildReActTimeline(rows);
    const th = blocks.find((b) => b.kind === 'thinking');
    expect(th).toMatchObject({
      kind: 'thinking',
      invokeState: 'done',
      invokeDurationSec: 3,
      answer: 'Hi',
    });
    expect((th as { invokeStartMs?: number }).invokeStartMs).toBeUndefined();
  });

  it('subagent text-only invoke (no reasoning channel) sets invokeState=done with duration', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'llm_invoke_start',
        seq: 30,
        invokeId: 'sub1',
        scope: 'subagent',
        subagentStream: true,
        subagentName: 'web-security',
        timestamp: 1774944050000,
      }),
      entry({
        type: 'llm_delta',
        seq: 31,
        channel: 'text',
        content: 'Extracted 3 IOC indicators.',
        invokeId: 'sub1',
        scope: 'subagent',
        subagentStream: true,
        subagentName: 'web-security',
      }),
      entry({
        type: 'llm_invoke_end',
        seq: 32,
        invokeId: 'sub1',
        scope: 'subagent',
        subagentStream: true,
        subagentName: 'web-security',
        timestamp: 1774944053000,
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const th = blocks.find((b) => b.kind === 'thinking');
    expect(th).toMatchObject({
      kind: 'thinking',
      invokeState: 'done',
      invokeDurationSec: 3,
      reasoning: '',
      answer: 'Extracted 3 IOC indicators.',
    });
  });

  it('does not merge when a new llm_invoke_start appears before the late text delta', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_invoke_start', seq: 0, invokeId: 'a' }),
      entry({ type: 'llm_delta', seq: 1, channel: 'reasoning', content: 'first', invokeId: 'a' }),
      entry({ type: 'llm_invoke_end', seq: 2, invokeId: 'a', timestamp: 100 }),
      entry({ type: 'llm_invoke_start', seq: 3, invokeId: 'b', timestamp: 101 }),
      entry({ type: 'llm_delta', seq: 4, channel: 'text', content: 'second', invokeId: 'b' }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const thinking = blocks.filter((b) => b.kind === 'thinking');
    expect(thinking).toHaveLength(2);
    expect((thinking[0] as { reasoning: string; answer: string }).reasoning).toContain('first');
    expect((thinking[0] as { answer: string }).answer).toBe('');
    expect((thinking[1] as { answer: string }).answer).toBe('second');
  });

  it('merges multiple streaming reasoning rows with the same turn into one thinking block', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'reasoning', seq: 1, content: 'p1', turn: 1 }),
      entry({ type: 'reasoning', seq: 2, content: 'p2', turn: 1 }),
      entry({ type: 'reasoning', seq: 3, content: 'p3', turn: 1 }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks.filter((b) => b.kind === 'thinking')).toHaveLength(1);
    expect((blocks[0] as { reasoning: string }).reasoning).toBe('p1p2p3');
  });

  it('keeps two thinking blocks when a step flushes between them (same turn)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'reasoning', seq: 1, content: 'before', turn: 1 }),
      entry({ type: 'step', seq: 2, id: 'milestone-x', label: 'Milestone', status: 'running' }),
      entry({ type: 'reasoning', seq: 3, content: 'after', turn: 1 }),
    ];
    const blocks = buildReActTimeline(rows);
    const thinking = blocks.filter((b) => b.kind === 'thinking');
    expect(thinking).toHaveLength(2);
    expect((thinking[0] as { reasoning: string }).reasoning).toBe('before');
    expect((thinking[1] as { reasoning: string }).reasoning).toBe('after');
    expect(blocks.some((b) => b.kind === 'step')).toBe(true);
  });

  it('merges reasoning for the same turn across tool calls into one thinking block', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'reasoning', seq: 1, content: 'a', turn: 1 }),
      entry({
        type: 'tool_call',
        seq: 2,
        id: 'tc1',
        toolName: 'read_file',
        toolInput: { file_path: 'f.ts' },
        turn: 1,
      }),
      entry({ type: 'reasoning', seq: 3, content: 'b', turn: 1 }),
      entry({ type: 'answer', seq: 4, content: 'out', turn: 1 }),
    ];
    const blocks = buildReActTimeline(rows);
    expect(blocks.filter((b) => b.kind === 'thinking')).toHaveLength(1);
    const th = blocks.find((b) => b.kind === 'thinking') as {
      kind: 'thinking';
      reasoning: string;
      answer: string;
    };
    expect(th.reasoning).toBe('ab');
    expect(th.answer).toBe('out');
    expect(blocks.some((b) => b.kind === 'tool_execution')).toBe(true);
  });

  it('merges task-running step running + success into one row with duration from timestamps', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'step',
        seq: 1,
        id: 'task-running-tc1',
        status: 'running',
        detail: 'research',
        timestamp: 10_000,
      }),
      entry({
        type: 'step',
        seq: 5,
        id: 'task-running-tc1',
        status: 'success',
        detail: 'research',
        timestamp: 13_000,
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const steps = blocks.filter((b) => b.kind === 'step') as {
      kind: 'step';
      stepVariant: string;
      status?: string;
      subagentDurationSec?: number;
    }[];
    expect(steps).toHaveLength(1);
    expect(steps[0].stepVariant).toBe('subagent_task');
    expect(steps[0].status).toBe('success');
    expect(steps[0].subagentDurationSec).toBe(3);
  });

  it('task-running single snapshot omits duration (avoid 0s after resume/replay)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'step',
        seq: 1,
        id: 'task-running-tc1',
        status: 'success',
        detail: 'subagent',
        timestamp: 10_000,
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const steps = blocks.filter((b) => b.kind === 'step') as { subagentDurationSec?: number }[];
    expect(steps).toHaveLength(1);
    expect(steps[0].subagentDurationSec).toBeUndefined();
  });

  it('task-running running+success with identical timestamps omits duration', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'step',
        seq: 1,
        id: 'task-running-tc1',
        status: 'running',
        timestamp: 10_000,
      }),
      entry({
        type: 'step',
        seq: 2,
        id: 'task-running-tc1',
        status: 'success',
        timestamp: 10_000,
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const steps = blocks.filter((b) => b.kind === 'step') as { subagentDurationSec?: number }[];
    expect(steps).toHaveLength(1);
    expect(steps[0].subagentDurationSec).toBeUndefined();
  });

  it('upserts task list by bucket key on repeated write_todos', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 1,
        toolName: 'write_todos',
        toolInput: {
          todos: [
            { id: 'a', content: 'One', status: 'pending' },
            { id: 'b', content: 'Two', status: 'pending' },
          ],
        },
        scope: 'main',
      }),
      entry({
        type: 'tool_call',
        seq: 2,
        toolName: 'write_todos',
        toolInput: {
          todos: [
            { id: 'a', content: 'One', status: 'completed' },
            { id: 'b', content: 'Two', status: 'pending' },
          ],
        },
        scope: 'main',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const tl = blocks.filter((b) => b.kind === 'task_list') as {
      kind: 'task_list';
      items: { id: string; done: boolean }[];
    }[];
    expect(tl).toHaveLength(1);
    expect(tl[0].items.find((i) => i.id === 'a')?.done).toBe(true);
  });

  it('orders thinking then tools then post-tool thinking when tools fall between two invokes', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_delta', seq: 1, channel: 'reasoning', content: 'think1', turn: 1 }),
      entry({ type: 'llm_invoke_end', seq: 2, invokeId: 'i1' }),
      entry({
        type: 'tool_call',
        seq: 3,
        id: 'tc1',
        toolName: 'read_file',
        toolInput: { file_path: 'x.ts' },
        turn: 1,
      }),
      entry({ type: 'llm_invoke_start', seq: 4, invokeId: 'i2' }),
      entry({ type: 'llm_delta', seq: 5, channel: 'reasoning', content: 'think2', turn: 2 }),
      entry({ type: 'llm_invoke_end', seq: 6, invokeId: 'i2' }),
    ];
    const blocks = buildReActTimeline(rows);
    const kinds = blocks.map((b) => b.kind);
    expect(kinds[0]).toBe('thinking');
    expect(kinds[1]).toBe('tool_execution');
    expect(kinds[2]).toBe('thinking');
    const thinking = blocks.filter((b) => b.kind === 'thinking');
    expect(thinking).toHaveLength(2);
    expect((thinking[0] as { reasoning: string }).reasoning).toBe('think1');
    expect((thinking[1] as { reasoning: string }).reasoning).toBe('think2');
  });

  it('creates separate task_list blocks for different subagentName', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 1,
        toolName: 'write_todos',
        toolInput: { todos: [{ content: 'Main', status: 'pending' }] },
        scope: 'main',
        subagentName: undefined,
      }),
      entry({
        type: 'tool_call',
        seq: 2,
        toolName: 'write_todos',
        toolInput: { todos: [{ content: 'Sub', status: 'pending' }] },
        scope: 'subagent',
        subagentName: 'research',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const tl = blocks.filter((b) => b.kind === 'task_list');
    expect(tl.length).toBe(2);
  });

  it('merges cumulative ConductResearch across explore chunks via fold + merge', () => {
    const full: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 1,
        id: 'tc-a',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        toolInput: { research_topic: 'Topic A' },
        scope: 'main',
      }),
      entry({ type: 'llm_invoke_end', seq: 2, invokeId: 'i1' }),
      entry({
        type: 'tool_call',
        seq: 3,
        id: 'tc-b',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        toolInput: { research_topic: 'Topic B' },
        scope: 'main',
      }),
    ];
    const chunkLate = full.filter((e) => Number(e.seq) >= 3);
    const base = buildReActTimeline(chunkLate);
    const buckets = foldResearchTaskListBuckets(full, { language: 'en', maxSeq: 3 });
    const merged = mergeResearchTaskListsIntoBlocks(base, buckets);
    const tl = merged.filter((b) => b.kind === 'task_list') as Array<{
      kind: 'task_list';
      items: { id: string; title: string }[];
    }>;
    expect(tl.length).toBeGreaterThanOrEqual(1);
    expect(tl[0]!.items).toHaveLength(2);
    expect(tl[0]!.items.map((i) => i.title)).toContain('Topic A');
    expect(tl[0]!.items.map((i) => i.title)).toContain('Topic B');
  });

  it('refreshes research row title when later tool_call repeats id with research_topic', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 1,
        id: 'tc-same',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        toolInput: {},
        scope: 'main',
      }),
      entry({
        type: 'tool_call',
        seq: 2,
        id: 'tc-same',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        toolInput: { research_topic: 'Filled topic' },
        scope: 'main',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const tl = blocks.filter((b) => b.kind === 'task_list') as Array<{
      kind: 'task_list';
      items: { id: string; title: string }[];
    }>;
    expect(tl[0]!.items).toHaveLength(1);
    expect(tl[0]!.items[0]!.title).toContain('Filled topic');
  });

  it('accumulates ConductResearch topics as one research task_list with done markers', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 1,
        id: 'tc-1',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        toolInput: { research_topic: 'Topic A details' },
        scope: 'main',
      }),
      entry({
        type: 'tool_call',
        seq: 2,
        id: 'tc-2',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        toolInput: { research_topic: 'Topic B' },
        scope: 'main',
      }),
      entry({
        type: 'tool_result',
        seq: 3,
        id: 'tc-1',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        scope: 'main',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const tl = blocks.filter((b) => b.kind === 'task_list') as Array<{
      kind: 'task_list';
      listVariant?: string;
      items: { id: string; title: string; done: boolean }[];
    }>;
    expect(tl.length).toBe(1);
    expect(tl[0]?.listVariant).toBe('research');
    expect(tl[0]?.items).toHaveLength(2);
    expect(tl[0]?.items[0]?.done).toBe(true);
    expect(tl[0]?.items[1]?.done).toBe(false);
    expect(tl[0]?.items[0]?.title).toContain('Topic A');
  });

  it('shows ConductResearch task_list row when research_topic is missing (streaming args)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call',
        seq: 1,
        id: 'tc-pending',
        toolName: 'ConductResearch',
        toolPresentation: 'research_task',
        toolInput: {},
        scope: 'subagent',
        subagentName: 'deep-research',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const tl = blocks.filter((b) => b.kind === 'task_list') as Array<{
      kind: 'task_list';
      items: { id: string; title: string }[];
    }>;
    expect(tl.length).toBe(1);
    expect(tl[0]?.items[0]?.id).toBe('tc-pending');
    expect(tl[0]?.items[0]?.title).toContain('loading');
  });

  it('creates empty thinking block from invoke boundaries and captures duration', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({ type: 'llm_invoke_start', seq: 1, invokeId: 'i1', timestamp: 1000 }),
      entry({ type: 'llm_invoke_end', seq: 2, invokeId: 'i1', timestamp: 3500 }),
    ];
    const blocks = buildReActTimeline(rows);
    const th = blocks.find((b) => b.kind === 'thinking') as
      | { kind: 'thinking'; invokeState?: 'running' | 'done'; invokeDurationSec?: number }
      | undefined;
    expect(th).toBeDefined();
    expect(th?.invokeState).toBe('done');
    // 3500ms - 1000ms = 2500ms = 2.5s (fractional, not rounded)
    expect(th?.invokeDurationSec).toBe(2.5);
  });
});

describe('mergeConsecutiveReasoningTimelineRows', () => {
  it('concatenates adjacent reasoning with mixed missing turn then numeric turn', () => {
    const merged = mergeConsecutiveReasoningTimelineRows([
      entry({ type: 'reasoning', seq: 1, content: 'a' }),
      entry({ type: 'reasoning', seq: 2, content: 'b', turn: 1 }),
    ]);
    expect(merged).toHaveLength(1);
    expect(merged[0].content).toBe('ab');
    expect(merged[0].turn).toBe(1);
  });

  it('does not merge consecutive reasoning when both turns are set and differ', () => {
    const merged = mergeConsecutiveReasoningTimelineRows([
      entry({ type: 'reasoning', seq: 1, content: 'a', turn: 1 }),
      entry({ type: 'reasoning', seq: 2, content: 'b', turn: 2 }),
    ]);
    expect(merged).toHaveLength(2);
  });

  it('merges adjacent llm_delta reasoning into one legacy reasoning row', () => {
    const merged = mergeConsecutiveReasoningTimelineRows([
      entry({
        type: 'llm_delta',
        seq: 1,
        channel: 'reasoning',
        content: 'a',
        invokeId: 'i1',
      }),
      entry({
        type: 'llm_delta',
        seq: 2,
        channel: 'reasoning',
        content: 'b',
        invokeId: 'i1',
      }),
    ]);
    expect(merged).toHaveLength(1);
    expect(merged[0].type).toBe('reasoning');
    expect(String(merged[0].content)).toBe('ab');
  });

  it('does not merge llm_delta reasoning across llm_invoke_end', () => {
    const merged = mergeConsecutiveReasoningTimelineRows([
      entry({ type: 'llm_delta', seq: 1, channel: 'reasoning', content: 'a', turn: 1 }),
      entry({ type: 'llm_invoke_end', seq: 2, invokeId: 'i1' }),
      entry({ type: 'llm_delta', seq: 3, channel: 'reasoning', content: 'b', turn: 1 }),
    ]);
    const reasoningRows = merged.filter((e) => e.type === 'reasoning');
    expect(reasoningRows).toHaveLength(2);
    expect(merged.some((e) => e.type === 'llm_invoke_end')).toBe(true);
  });

  it('does not merge main and subagent reasoning into one row', () => {
    const merged = mergeConsecutiveReasoningTimelineRows([
      entry({ type: 'llm_delta', seq: 1, channel: 'reasoning', content: 'main', scope: 'main' }),
      entry({
        type: 'llm_delta',
        seq: 2,
        channel: 'reasoning',
        content: 'sub',
        scope: 'subagent',
        subagentStream: true,
      }),
    ]);
    expect(merged).toHaveLength(2);
    expect(String(merged[0]?.content)).toBe('main');
    expect(String(merged[1]?.content)).toBe('sub');
  });
});

describe('coalesceThinkingBlocksAcrossTools', () => {
  it('does not merge two thinking blocks separated by tool_execution (order preserved)', () => {
    const blocks = coalesceThinkingBlocksAcrossTools([
      { kind: 'thinking', reasoning: 'x', answer: '', turn: 1 },
      {
        kind: 'tool_execution',
        children: [{ toolCallId: 't', toolName: 't', detail: '', done: true }],
      },
      { kind: 'thinking', reasoning: 'y', answer: 'z', turn: 1 },
    ]);
    expect(blocks).toHaveLength(3);
    expect(blocks[0]).toMatchObject({ kind: 'thinking', reasoning: 'x', turn: 1 });
    expect(blocks[1]?.kind).toBe('tool_execution');
    expect(blocks[2]).toMatchObject({ kind: 'thinking', reasoning: 'y', answer: 'z', turn: 1 });
  });

  it('does not merge two thinking blocks separated by step', () => {
    const blocks = coalesceThinkingBlocksAcrossTools([
      { kind: 'thinking', reasoning: 'a', answer: '', turn: 1 },
      { kind: 'step', stepVariant: 'generic', label: 'S' },
      { kind: 'thinking', reasoning: 'b', answer: '', turn: 1 },
    ]);
    expect(blocks).toHaveLength(3);
    expect(blocks[0]).toMatchObject({ kind: 'thinking', reasoning: 'a', turn: 1 });
    expect(blocks[1]?.kind).toBe('step');
    expect(blocks[2]).toMatchObject({ kind: 'thinking', reasoning: 'b', turn: 1 });
  });

  it('does not coalesce phaseId step under prior thinking (slot step stays separate)', () => {
    const blocks = coalesceThinkingBlocksAcrossTools([
      { kind: 'thinking', reasoning: 'a', answer: '', turn: 1 },
      {
        kind: 'step',
        stepVariant: 'generic',
        label: 'Plan',
        phaseId: 'deep_research_plan',
      },
      { kind: 'thinking', reasoning: 'b', answer: '', turn: 1 },
    ]);
    expect(blocks.map((b) => b.kind)).toEqual(['thinking', 'step', 'thinking']);
  });

  // --- toolOutput / isError capture tests ---

  it('captures toolOutput from tool_result with string output', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call', seq: 1, id: 'tc1',
        toolName: 'web_search', toolInput: { query: 'test' },
        toolPresentation: 'action',
      }),
      entry({
        type: 'tool_result', seq: 2, id: 'tc1',
        toolName: 'web_search', toolOutput: 'Found 5 results for test',
        status: 'success',
        toolPresentation: 'action',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const te = blocks.find((b) => b.kind === 'tool_execution');
    expect(te?.kind).toBe('tool_execution');
    if (te?.kind !== 'tool_execution') return;
    expect(te.children[0]?.done).toBe(true);
    expect(te.children[0]?.toolOutput).toBe('Found 5 results for test');
    expect(te.children[0]?.isError).toBeUndefined();
  });

  it('sets isError when tool_result status is error', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call', seq: 1, id: 'tc1',
        toolName: 'shell', toolInput: { command: 'fail' },
        toolPresentation: 'action',
      }),
      entry({
        type: 'tool_result', seq: 2, id: 'tc1',
        toolName: 'shell',
        toolOutput: '{"error": "command not found"}',
        status: 'error',
        toolPresentation: 'action',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const te = blocks.find((b) => b.kind === 'tool_execution');
    expect(te?.kind).toBe('tool_execution');
    if (te?.kind !== 'tool_execution') return;
    expect(te.children[0]?.done).toBe(true);
    expect(te.children[0]?.isError).toBe(true);
    expect(te.children[0]?.toolOutput).toBeTruthy();
  });

  it('leaves toolOutput undefined when tool_result has no output', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call', seq: 1, id: 'tc1',
        toolName: 'read_file', toolInput: { file_path: 'a.ts' },
        toolPresentation: 'action',
      }),
      entry({
        type: 'tool_result', seq: 2, id: 'tc1',
        toolName: 'read_file', toolOutput: '',
        toolPresentation: 'action',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const te = blocks.find((b) => b.kind === 'tool_execution');
    expect(te?.kind).toBe('tool_execution');
    if (te?.kind !== 'tool_execution') return;
    expect(te.children[0]?.done).toBe(true);
    expect(te.children[0]?.toolOutput).toBeUndefined();
  });

  it('truncates long toolOutput past timeline display max', () => {
    const max = toolOutputTimelineMaxChars;
    const longOutput = 'x'.repeat(max + 500);
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call', seq: 1, id: 'tc1',
        toolName: 'web_search', toolInput: { query: 'test' },
        toolPresentation: 'action',
      }),
      entry({
        type: 'tool_result', seq: 2, id: 'tc1',
        toolName: 'web_search', toolOutput: longOutput,
        toolPresentation: 'action',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const te = blocks.find((b) => b.kind === 'tool_execution');
    expect(te?.kind).toBe('tool_execution');
    if (te?.kind !== 'tool_execution') return;
    expect(te.children[0]?.toolOutput).toBeDefined();
    expect(te.children[0]!.toolOutput!.length).toBeLessThanOrEqual(max + 1);
    expect(te.children[0]!.toolOutput!.endsWith('…')).toBe(true);
  });

  it('handles JSON object toolOutput by stringifying', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'tool_call', seq: 1, id: 'tc1',
        toolName: 'read_file', toolInput: { file_path: 'x.ts' },
        toolPresentation: 'action',
      }),
      entry({
        type: 'tool_result', seq: 2, id: 'tc1',
        toolName: 'read_file', toolOutput: { data: 'hello' },
        toolPresentation: 'action',
      }),
    ];
    const blocks = buildReActTimeline(rows);
    const te = blocks.find((b) => b.kind === 'tool_execution');
    expect(te?.kind).toBe('tool_execution');
    if (te?.kind !== 'tool_execution') return;
    expect(te.children[0]?.toolOutput).toBe('{"data":"hello"}');
  });

  it('inserts a delegation_group step when subagent rows include delegationDepth', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'x',
        scope: 'subagent',
        subagentName: 'email-security',
        delegationDepth: 1,
        rootDelegationId: 'root-tc-1',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const dg = blocks.find(
      (b) => b.kind === 'step' && b.stepVariant === 'delegation_group',
    );
    expect(dg?.kind).toBe('step');
    if (dg?.kind !== 'step') return;
    expect(dg.stepVariant).toBe('delegation_group');
    expect(dg.label).toContain('Email security');
  });

  it('inserts delegation_group for subagent-only legacy rows (subagentName, no envelope)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'x',
        scope: 'subagent',
        subagentName: 'binary-analysis',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const dg = blocks.find(
      (b) => b.kind === 'step' && b.stepVariant === 'delegation_group',
    );
    expect(dg?.kind).toBe('step');
    if (dg?.kind !== 'step') return;
    expect(dg.stepVariant).toBe('delegation_group');
    expect(dg.label.toLowerCase()).toContain('binary');
  });

  it('does not merge consecutive subagent reasoning across different subagentName (legacy)', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'a',
        scope: 'subagent',
        subagentName: 'email-security',
      }),
      entry({
        type: 'reasoning',
        seq: 2,
        content: 'b',
        scope: 'subagent',
        subagentName: 'binary-analysis',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const thinkingBlocks = blocks.filter((b) => b.kind === 'thinking');
    expect(thinkingBlocks.length).toBe(2);
  });

  it('does not merge subagent reasoning when delegation envelope fields differ', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'a',
        scope: 'subagent',
        subagentName: 'email-security',
        delegationDepth: 1,
        rootDelegationId: 'r1',
      }),
      entry({
        type: 'reasoning',
        seq: 2,
        content: 'b',
        scope: 'subagent',
        subagentName: 'binary-analysis',
        delegationDepth: 2,
        rootDelegationId: 'r1',
        parentToolCallId: 'p1',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const thinkingBlocks = blocks.filter((b) => b.kind === 'thinking');
    expect(thinkingBlocks.length).toBe(2);
  });

  // --- Issue 01: subagentId / delegationDepth tagging ---

  it('depth=1 subagent tool block carries subagentId and delegationDepth 1', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'thinking',
        scope: 'subagent',
        subagentName: 'email-security',
        delegationDepth: 1,
        rootDelegationId: 'root-1',
      }),
      entry({
        type: 'tool_call',
        seq: 2,
        id: 'tc-1',
        toolName: 'read_file',
        toolInput: { file_path: '/etc/passwd' },
        scope: 'subagent',
        subagentName: 'email-security',
        delegationDepth: 1,
        rootDelegationId: 'root-1',
      }),
      entry({
        type: 'llm_invoke_start',
        seq: 3,
        scope: 'main',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const toolBlock = blocks.find((b) => b.kind === 'tool_execution');
    expect(toolBlock?.kind).toBe('tool_execution');
    if (toolBlock?.kind !== 'tool_execution') return;
    expect(toolBlock.subagentId).toBe('email-security');
    expect(toolBlock.delegationDepth).toBe(1);
  });

  it('depth=2 nested subagent tool block carries delegationDepth 2', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'nested',
        scope: 'subagent',
        subagentName: 'binary-analysis',
        delegationDepth: 2,
        rootDelegationId: 'root-1',
        parentToolCallId: 'p1',
      }),
      entry({
        type: 'tool_call',
        seq: 2,
        id: 'tc-2',
        toolName: 'read_file',
        toolInput: { file_path: '/bin/sh' },
        scope: 'subagent',
        subagentName: 'binary-analysis',
        delegationDepth: 2,
        rootDelegationId: 'root-1',
        parentToolCallId: 'p1',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const toolBlock = blocks.find((b) => b.kind === 'tool_execution');
    expect(toolBlock?.kind).toBe('tool_execution');
    if (toolBlock?.kind !== 'tool_execution') return;
    expect(toolBlock.delegationDepth).toBe(2);
    expect(toolBlock.subagentId).toBe('binary-analysis');
  });

  it('main-graph tool block has subagentId undefined after returning from subagent', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'sub',
        scope: 'subagent',
        subagentName: 'email-security',
        delegationDepth: 1,
        rootDelegationId: 'root-1',
      }),
      entry({
        type: 'llm_invoke_start',
        seq: 2,
        scope: 'main',
      }),
      entry({
        type: 'tool_call',
        seq: 3,
        id: 'tc-main',
        toolName: 'read_file',
        toolInput: { file_path: '/etc/hosts' },
        scope: 'main',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const toolBlock = blocks.find((b) => b.kind === 'tool_execution');
    expect(toolBlock?.kind).toBe('tool_execution');
    if (toolBlock?.kind !== 'tool_execution') return;
    expect(toolBlock.subagentId).toBeUndefined();
    expect(toolBlock.delegationDepth).toBeUndefined();
  });

  it('legacy rows (subagentName only, no delegation envelope) flush tool blocks with subagentId undefined', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'legacy',
        scope: 'subagent',
        subagentName: 'email-security',
        // no delegationDepth / rootDelegationId → legacy bucket
      }),
      entry({
        type: 'tool_call',
        seq: 2,
        id: 'tc-leg',
        toolName: 'read_file',
        toolInput: { file_path: '/tmp/x' },
        scope: 'subagent',
        subagentName: 'email-security',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const toolBlock = blocks.find((b) => b.kind === 'tool_execution');
    expect(toolBlock?.kind).toBe('tool_execution');
    if (toolBlock?.kind !== 'tool_execution') return;
    expect(toolBlock.subagentId).toBeUndefined();
  });

  it('delegation_group step block carries subagentId equal to subagentName', () => {
    const rows: AnalysisTimelineEntry[] = [
      entry({
        type: 'reasoning',
        seq: 1,
        content: 'x',
        scope: 'subagent',
        subagentName: 'email-security',
        delegationDepth: 1,
        rootDelegationId: 'root-1',
      }),
    ];
    const blocks = buildReActTimeline(rows, { language: 'en' });
    const dg = blocks.find((b) => b.kind === 'step' && b.stepVariant === 'delegation_group');
    expect(dg?.kind).toBe('step');
    if (dg?.kind !== 'step') return;
    expect(dg.subagentId).toBe('email-security');
  });
});
