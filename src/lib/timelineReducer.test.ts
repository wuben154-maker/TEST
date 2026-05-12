import { describe, expect, it } from 'vitest';
import type { ThinkingEvent } from '@/types/analysis';
import { appendToAnalysisTimeline } from './timelineReducer';

describe('appendToAnalysisTimeline', () => {
  it('uses server seq and normalizes schemaVersion and scope', () => {
    const ev = {
      type: 'reasoning' as const,
      id: 'r1',
      seq: 42,
      content: 'hello',
    } satisfies ThinkingEvent;
    const next = appendToAnalysisTimeline([], ev, () => 999);
    expect(next).toHaveLength(1);
    expect(next[0].seq).toBe(42);
    expect(next[0].schemaVersion).toBe(1);
    expect(next[0].scope).toBe('main');
    expect(next[0].content).toBe('hello');
  });

  it('bumps local seq when seq missing and preserves subagent scope', () => {
    let n = 0;
    const bump = () => ++n;
    const ev = {
      type: 'tool_call' as const,
      id: 'tc-1',
      subagentStream: true,
      toolName: 'read_file',
      toolInput: {},
    } satisfies ThinkingEvent;
    const t1 = appendToAnalysisTimeline([], ev, bump);
    const t2 = appendToAnalysisTimeline(t1, { ...ev, id: 'tc-2' }, bump);
    expect(t2).toHaveLength(2);
    expect(t2[0].seq).toBe(1);
    expect(t2[1].seq).toBe(2);
    expect(t2[0].scope).toBe('subagent');
    expect(t2[0].type).toBe('tool_call');
    expect(t2[1].type).toBe('tool_call');
  });

  it('interleaves reasoning, tool_call, tool_result without collapsing types', () => {
    let seq = 0;
    const bump = () => ++seq;
    let t = appendToAnalysisTimeline(
      [],
      { type: 'reasoning', id: 'r', content: 'a' } satisfies ThinkingEvent,
      bump,
    );
    t = appendToAnalysisTimeline(
      t,
      { type: 'tool_call', id: 'c1', toolName: 'x', toolInput: {} } satisfies ThinkingEvent,
      bump,
    );
    t = appendToAnalysisTimeline(
      t,
      {
        type: 'tool_result',
        id: 'c1',
        toolName: 'x',
        toolOutput: 'out',
      } satisfies ThinkingEvent,
      bump,
    );
    expect(t.map((e) => e.type)).toEqual(['reasoning', 'tool_call', 'tool_result']);
  });

  it('replaces same deep_research phase row in place (running then success)', () => {
    let n = 0;
    const bump = () => ++n;
    const running = {
      type: 'step' as const,
      id: 'dr-pre-clarify',
      phaseId: 'deep_research_clarify',
      label: 'Clarify',
      status: 'running' as const,
    } satisfies ThinkingEvent;
    const success = {
      ...running,
      id: 'dr-phase-deep_research_clarify-success',
      status: 'success' as const,
    };
    let t = appendToAnalysisTimeline([], running, bump);
    expect(t).toHaveLength(1);
    expect(t[0].status).toBe('running');
    t = appendToAnalysisTimeline(t, success, bump);
    expect(t).toHaveLength(1);
    expect(t[0].status).toBe('success');
    expect(t[0].id).toBe('dr-phase-deep_research_clarify-success');
  });

  it('preserves original running seq when success replaces phase entry', () => {
    const bump = () => 999;
    const running = {
      type: 'step' as const,
      id: 'dr-phase-deep_research_plan-running',
      phaseId: 'deep_research_plan',
      label: '拟定研究课题',
      status: 'running' as const,
      seq: 5,
    } satisfies ThinkingEvent;
    const reasoning = {
      type: 'reasoning' as const,
      id: 'r1',
      seq: 8,
      content: 'brief output',
    } satisfies ThinkingEvent;
    const success = {
      type: 'step' as const,
      id: 'dr-phase-deep_research_plan-success',
      phaseId: 'deep_research_plan',
      label: '拟定研究课题',
      status: 'success' as const,
      seq: 15,
    } satisfies ThinkingEvent;

    let t = appendToAnalysisTimeline([], running, bump);
    t = appendToAnalysisTimeline(t, reasoning, bump);
    t = appendToAnalysisTimeline(t, success, bump);

    expect(t).toHaveLength(2);
    const phase = t.find((e) => e.phaseId === 'deep_research_plan')!;
    expect(phase.status).toBe('success');
    expect(phase.seq).toBe(5);
  });

  it('drops task-running replay after same id already succeeded (HITL resume)', () => {
    const bump = () => 1;
    const done = {
      type: 'step' as const,
      id: 'task-running-call_xyz',
      label: 'deep-research done',
      status: 'success' as const,
      seq: 10,
      timestamp: 1_000,
    } satisfies ThinkingEvent;
    const replayRunning = {
      type: 'step' as const,
      id: 'task-running-call_xyz',
      label: 'deep-research analyzing',
      status: 'running' as const,
      seq: 20,
      timestamp: 2_000,
    } satisfies ThinkingEvent;
    let t = appendToAnalysisTimeline([], done, bump);
    expect(t).toHaveLength(1);
    t = appendToAnalysisTimeline(t, replayRunning, bump);
    expect(t).toHaveLength(1);
    expect(t[0].status).toBe('success');
  });

  it('upgrades task-running running to success in place (same id)', () => {
    const bump = () => 1;
    const running = {
      type: 'step' as const,
      id: 'task-running-tc1',
      label: 'x',
      status: 'running' as const,
      seq: 5,
      timestamp: 100,
    } satisfies ThinkingEvent;
    const success = {
      type: 'step' as const,
      id: 'task-running-tc1',
      label: 'x done',
      status: 'success' as const,
      seq: 9,
      timestamp: 3_100,
    } satisfies ThinkingEvent;
    let t = appendToAnalysisTimeline([], running, bump);
    t = appendToAnalysisTimeline(t, success, bump);
    expect(t).toHaveLength(1);
    expect(t[0].status).toBe('success');
    expect(t[0].seq).toBe(5);
    expect(t[0].timestamp).toBe(3_100);
  });

  it('ignores duplicate task-running running for same id', () => {
    const bump = () => 1;
    const r1 = {
      type: 'step' as const,
      id: 'task-running-a',
      status: 'running' as const,
      seq: 1,
    } satisfies ThinkingEvent;
    const r2 = { ...r1, seq: 2 };
    let t = appendToAnalysisTimeline([], r1, bump);
    t = appendToAnalysisTimeline(t, r2, bump);
    expect(t).toHaveLength(1);
    expect(t[0].seq).toBe(1);
  });
});
