import { describe, it, expect, beforeEach } from 'vitest';
import type { ContextUsageState } from '@/types/analysis';
import {
  saveContextUsage,
  loadContextUsage,
  loadContextUsagePayload,
  clearContextUsage,
  clearAllContextUsage,
} from '@/lib/contextUsagePersistence';

const projectId = 'proj-abc';

function makeState(partial?: Partial<ContextUsageState>): ContextUsageState {
  return {
    latest: {
      invokeId: 'r1',
      modelId: 'anthropic/claude-sonnet-4',
      inputTokens: 120_000,
      outputTokens: 2_000,
      endedAt: 1_750_000_000_000,
    },
    cumulative: { inputTokens: 120_000, outputTokens: 2_000, invocations: 3 },
    bySubagent: [
      { subagentName: '__main__', invocations: 2, inputTokens: 90_000, outputTokens: 1_500 },
      { subagentName: 'deep-research', invocations: 1, inputTokens: 30_000, outputTokens: 500 },
    ],
    lastSummarizedAt: undefined,
    ...partial,
  };
}

describe('contextUsagePersistence', () => {
  beforeEach(() => {
    clearAllContextUsage();
  });

  it('round-trips a meaningful state through localStorage', () => {
    const state = makeState();
    saveContextUsage(projectId, state);
    const loaded = loadContextUsage(projectId);
    expect(loaded).not.toBeNull();
    expect(loaded?.latest?.inputTokens).toBe(120_000);
    expect(loaded?.bySubagent.length).toBe(2);
    expect(loaded?.cumulative.invocations).toBe(3);
  });

  it('skips saving empty state so a stale meaningful value is not overwritten', () => {
    const state = makeState();
    saveContextUsage(projectId, state);

    const empty: ContextUsageState = {
      latest: undefined,
      latestMain: undefined,
      latestSubagentByName: {},
      cumulative: { inputTokens: 0, outputTokens: 0, invocations: 0 },
      bySubagent: [],
      lastSummarizedAt: undefined,
    };
    saveContextUsage(projectId, empty);
    const loaded = loadContextUsage(projectId);
    expect(loaded?.latest?.inputTokens).toBe(120_000);
  });

  it('returns null when nothing is stored', () => {
    expect(loadContextUsage('never-seen')).toBeNull();
  });

  it('returns null when the stored payload has an unknown version', () => {
    window.localStorage.setItem(
      'secmanus:context-usage:v1:' + projectId,
      JSON.stringify({ v: 999, state: makeState() }),
    );
    expect(loadContextUsage(projectId)).toBeNull();
  });

  it('returns null for corrupted JSON', () => {
    window.localStorage.setItem(
      'secmanus:context-usage:v1:' + projectId,
      'not-json',
    );
    expect(loadContextUsage(projectId)).toBeNull();
  });

  it('clearContextUsage removes only the targeted project entry', () => {
    saveContextUsage('a', makeState());
    saveContextUsage('b', makeState());
    clearContextUsage('a');
    expect(loadContextUsage('a')).toBeNull();
    expect(loadContextUsage('b')).not.toBeNull();
  });

  it('loadContextUsagePayload returns state + updatedAt for fresh writes', () => {
    const before = Date.now();
    saveContextUsage(projectId, makeState());
    const payload = loadContextUsagePayload(projectId);
    expect(payload).not.toBeNull();
    expect(payload!.state.latest?.inputTokens).toBe(120_000);
    expect(payload!.updatedAt).toBeGreaterThanOrEqual(before);
    expect(payload!.updatedAt).toBeLessThanOrEqual(Date.now());
  });

  it('loadContextUsagePayload treats legacy (no updatedAt) entries as very old', () => {
    // Legacy entry written by a pre-2026-04-19 client — no ``updatedAt``.
    window.localStorage.setItem(
      'secmanus:context-usage:v1:legacy',
      JSON.stringify({ v: 1, state: makeState() }),
    );
    const payload = loadContextUsagePayload('legacy');
    expect(payload).not.toBeNull();
    // Zero = "very old"; the hydrate path uses this to prefer the backend
    // value when both are present.
    expect(payload!.updatedAt).toBe(0);
  });
});
