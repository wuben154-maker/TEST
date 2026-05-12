import { describe, expect, it } from 'vitest';
import {
  applyEventToContextUsage,
  createEmptyContextUsageState,
  deriveIndicator,
  MAIN_SUBAGENT_KEY,
  pickNewerContextUsage,
} from './contextUsage';
import type { ContextUsageState, ThinkingEvent } from '@/types/analysis';

function startEvent(invokeId: string, modelId?: string, scope?: 'main' | 'subagent', subagent?: string): ThinkingEvent {
  return {
    type: 'llm_invoke_start',
    id: invokeId,
    invokeId,
    modelId,
    scope,
    subagentName: subagent,
  };
}

function endEvent(
  invokeId: string,
  input: number,
  output: number,
  extras: Partial<ThinkingEvent> = {},
): ThinkingEvent {
  return {
    type: 'llm_invoke_end',
    id: invokeId,
    invokeId,
    usage: { inputTokens: input, outputTokens: output },
    timestamp: 1_700_000_000_000,
    ...extras,
  };
}

describe('applyEventToContextUsage', () => {
  it('ignores start without matching end', () => {
    const s0 = createEmptyContextUsageState();
    const s1 = applyEventToContextUsage(s0, startEvent('r1', 'anthropic/claude-sonnet-4'));
    expect(s1.latest).toBeUndefined();
    expect(s1.cumulative).toEqual({ inputTokens: 0, outputTokens: 0, invocations: 0 });
  });

  it('captures latest usage on invoke_end and increments cumulative', () => {
    const s0 = createEmptyContextUsageState();
    const s1 = applyEventToContextUsage(s0, startEvent('r1', 'anthropic/claude-sonnet-4'));
    const s2 = applyEventToContextUsage(s1, endEvent('r1', 5000, 200));
    expect(s2.latest).toMatchObject({
      invokeId: 'r1',
      modelId: 'anthropic/claude-sonnet-4',
      inputTokens: 5000,
      outputTokens: 200,
    });
    expect(s2.cumulative).toEqual({ inputTokens: 5000, outputTokens: 200, invocations: 1 });
  });

  it('accumulates across multiple invocations', () => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r1'));
    s = applyEventToContextUsage(s, endEvent('r1', 1000, 100));
    s = applyEventToContextUsage(s, startEvent('r2'));
    s = applyEventToContextUsage(s, endEvent('r2', 2000, 300));
    expect(s.cumulative).toEqual({ inputTokens: 3000, outputTokens: 400, invocations: 2 });
    expect(s.latest?.invokeId).toBe('r2');
  });

  it('attributes subagent invocations to subagentName bucket', () => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('m1'));
    s = applyEventToContextUsage(s, endEvent('m1', 1000, 100));
    s = applyEventToContextUsage(s, startEvent('d1', undefined, 'subagent', 'deep-research'));
    s = applyEventToContextUsage(s, endEvent('d1', 7000, 50, { scope: 'subagent', subagentName: 'deep-research' }));
    const byName = Object.fromEntries(s.bySubagent.map((b) => [b.subagentName, b]));
    expect(byName[MAIN_SUBAGENT_KEY].inputTokens).toBe(1000);
    expect(byName['deep-research'].inputTokens).toBe(7000);
    expect(byName['deep-research'].invocations).toBe(1);
    // Main ring uses latest main only; subagent end must not replace `latest` / `latestMain`.
    expect(s.latest?.invokeId).toBe('m1');
    expect(s.latestMain?.invokeId).toBe('m1');
    expect(s.latestSubagentByName?.['deep-research']?.inputTokens).toBe(7000);
  });

  it('records lastSummarizedAt on context_summarized', () => {
    const s0 = createEmptyContextUsageState();
    const s1 = applyEventToContextUsage(s0, {
      type: 'context_summarized',
      id: 'sum-1',
      timestamp: 1_700_000_000_000,
      cutoffIndex: 42,
    } as ThinkingEvent);
    expect(s1.lastSummarizedAt).toBe(1_700_000_000_000);
  });

  it('clears main snapshots on context_summarized (Option A)', () => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r1', 'm1'));
    s = applyEventToContextUsage(s, endEvent('r1', 50_000, 100));
    expect(s.latestMain?.inputTokens).toBe(50_000);
    s = applyEventToContextUsage(s, {
      type: 'context_summarized',
      id: 'sum-1',
      timestamp: 1_700_000_000_001,
    } as ThinkingEvent);
    expect(s.latestMain).toBeUndefined();
    expect(s.latest).toBeUndefined();
    expect(s.lastSummarizedAt).toBe(1_700_000_000_001);
    expect(s.cumulative).toEqual({ inputTokens: 50_000, outputTokens: 100, invocations: 1 });
    expect(s.bySubagent.length).toBeGreaterThanOrEqual(0);
  });

  it('treats missing usage on invoke_end as a no-op (legacy SSE)', () => {
    const s0 = createEmptyContextUsageState();
    const s1 = applyEventToContextUsage(s0, startEvent('r1'));
    const s2 = applyEventToContextUsage(s1, {
      type: 'llm_invoke_end',
      id: 'r1',
      invokeId: 'r1',
    } as ThinkingEvent);
    expect(s2.latest).toBeUndefined();
    expect(s2.cumulative.invocations).toBe(0);
  });

  it('clamps negative usage to zero', () => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r1'));
    s = applyEventToContextUsage(s, endEvent('r1', -10, -5));
    expect(s.latest?.inputTokens).toBe(0);
    expect(s.latest?.outputTokens).toBe(0);
  });
});

describe('deriveIndicator', () => {
  it('returns null when no latest', () => {
    const s = createEmptyContextUsageState();
    expect(deriveIndicator(s, 200_000)).toBeNull();
  });

  it('returns null when context window unknown', () => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r1'));
    s = applyEventToContextUsage(s, endEvent('r1', 100, 10));
    expect(deriveIndicator(s, undefined)).toBeNull();
    expect(deriveIndicator(s, 0)).toBeNull();
  });

  it.each([
    [100, 'safe'],
    [140_000, 'warn'],
    [180_000, 'danger'],
    [195_000, 'critical'],
  ] as const)('buckets severity for tokens=%i', (tokens, expectedSeverity) => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r1'));
    s = applyEventToContextUsage(s, endEvent('r1', tokens, 0));
    const out = deriveIndicator(s, 200_000);
    expect(out?.severity).toBe(expectedSeverity);
  });

  it('clamps percent to 100 even for over-budget usage', () => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r1'));
    s = applyEventToContextUsage(s, endEvent('r1', 300_000, 10_000));
    const out = deriveIndicator(s, 200_000);
    expect(out?.percent).toBe(100);
  });

  it('uses input tokens only for the ring (ignores output for percent)', () => {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r1'));
    s = applyEventToContextUsage(s, endEvent('r1', 20_000, 500_000));
    const out = deriveIndicator(s, 200_000);
    expect(out?.tokens).toBe(20_000);
    expect(out?.percent).toBe(10);
  });
});

describe('pickNewerContextUsage', () => {
  function buildState(marker: number): ContextUsageState {
    let s = createEmptyContextUsageState();
    s = applyEventToContextUsage(s, startEvent('r' + marker));
    s = applyEventToContextUsage(s, endEvent('r' + marker, marker, 1));
    return s;
  }

  it('returns null when neither source has data', () => {
    expect(pickNewerContextUsage(null, null)).toBeNull();
  });

  it('returns the local state when only local has data', () => {
    const local = { state: buildState(100), updatedAt: 1_700_000_000_000 };
    const winner = pickNewerContextUsage(local, null);
    expect(winner?.source).toBe('local');
    expect(winner?.state.latest?.inputTokens).toBe(100);
  });

  it('returns the backend state when only backend has data', () => {
    const backend = { state: buildState(200), updatedAt: 1_700_000_000_000 };
    const winner = pickNewerContextUsage(null, backend);
    expect(winner?.source).toBe('backend');
    expect(winner?.state.latest?.inputTokens).toBe(200);
  });

  it('returns the newer source by updatedAt', () => {
    const older = { state: buildState(100), updatedAt: 1_700_000_000_000 };
    const newer = { state: buildState(200), updatedAt: 1_700_000_099_999 };
    const winBackendNewer = pickNewerContextUsage(older, newer);
    expect(winBackendNewer?.source).toBe('backend');
    expect(winBackendNewer?.state.latest?.inputTokens).toBe(200);

    const winLocalNewer = pickNewerContextUsage(newer, older);
    expect(winLocalNewer?.source).toBe('local');
    expect(winLocalNewer?.state.latest?.inputTokens).toBe(200);
  });

  it('breaks ties in favour of backend (authoritative)', () => {
    const local = { state: buildState(100), updatedAt: 1_700_000_000_000 };
    const backend = { state: buildState(200), updatedAt: 1_700_000_000_000 };
    const winner = pickNewerContextUsage(local, backend);
    expect(winner?.source).toBe('backend');
    expect(winner?.state.latest?.inputTokens).toBe(200);
  });

  it('legacy local entry (updatedAt = 0) loses against any positive backend updatedAt', () => {
    const legacyLocal = { state: buildState(100), updatedAt: 0 };
    const backend = { state: buildState(200), updatedAt: 1 };
    const winner = pickNewerContextUsage(legacyLocal, backend);
    expect(winner?.source).toBe('backend');
  });
});
