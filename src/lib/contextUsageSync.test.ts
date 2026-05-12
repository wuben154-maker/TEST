import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import type { ContextUsageState } from '@/types/analysis';
import {
  scheduleBackendSync,
  flushNow,
  flushAllNow,
  cancelScheduled,
  flushAllOnUnload,
  DEBOUNCE_MS,
  __resetForTests,
} from '@/lib/contextUsageSync';

// Mock `projectsApi.updateContextUsage` — that's the only thing the sync
// module talks to. We collect every call so tests can assert coalescing /
// timing / payload shape.
const updateCalls: Array<{ projectId: string; body: unknown }> = [];

vi.mock('@/lib/api-client', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api-client')>(
      '@/lib/api-client',
    );
  return {
    ...actual,
    projectsApi: {
      ...actual.projectsApi,
      updateContextUsage: vi.fn(
        async (projectId: string, body: Record<string, unknown> | null) => {
          updateCalls.push({ projectId, body });
          return { data: null, error: null };
        },
      ),
    },
  };
});

function makeState(partial?: Partial<ContextUsageState>): ContextUsageState {
  return {
    latest: {
      invokeId: 'r1',
      modelId: 'anthropic/claude-sonnet-4',
      inputTokens: 1_000,
      outputTokens: 200,
      endedAt: 1_750_000_000_000,
    },
    cumulative: { inputTokens: 1_000, outputTokens: 200, invocations: 1 },
    bySubagent: [
      {
        subagentName: '__main__',
        invocations: 1,
        inputTokens: 1_000,
        outputTokens: 200,
      },
    ],
    lastSummarizedAt: undefined,
    ...partial,
  };
}

describe('contextUsageSync', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    updateCalls.length = 0;
    __resetForTests();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('coalesces many rapid schedules into one PATCH per DEBOUNCE_MS window', async () => {
    scheduleBackendSync('p1', makeState({ cumulative: { inputTokens: 1_000, outputTokens: 100, invocations: 1 } }));
    scheduleBackendSync('p1', makeState({ cumulative: { inputTokens: 2_000, outputTokens: 200, invocations: 2 } }));
    scheduleBackendSync('p1', makeState({ cumulative: { inputTokens: 3_000, outputTokens: 300, invocations: 3 } }));

    expect(updateCalls).toHaveLength(0);

    // Advance just before the debounce — still no fire.
    vi.advanceTimersByTime(DEBOUNCE_MS - 1);
    expect(updateCalls).toHaveLength(0);

    // Cross the threshold.
    vi.advanceTimersByTime(2);
    await vi.runAllTimersAsync();
    expect(updateCalls).toHaveLength(1);
    expect(updateCalls[0].projectId).toBe('p1');
    const body = updateCalls[0].body as { state: ContextUsageState };
    expect(body.state.cumulative.invocations).toBe(3); // newest wins
  });

  it('flushNow fires immediately and cancels the pending timer', async () => {
    scheduleBackendSync('p1', makeState());
    expect(updateCalls).toHaveLength(0);

    await flushNow('p1');
    expect(updateCalls).toHaveLength(1);

    // Advancing past the original debounce produces no extra PATCH.
    vi.advanceTimersByTime(DEBOUNCE_MS * 2);
    await vi.runAllTimersAsync();
    expect(updateCalls).toHaveLength(1);
  });

  it('flushNow is a no-op when no snapshot was scheduled', async () => {
    await flushNow('never-seen');
    expect(updateCalls).toHaveLength(0);
  });

  it('flushAllNow flushes every pending project in parallel', async () => {
    scheduleBackendSync('a', makeState());
    scheduleBackendSync('b', makeState({ cumulative: { inputTokens: 5, outputTokens: 1, invocations: 1 } }));

    await flushAllNow();
    const ids = updateCalls.map((c) => c.projectId).sort();
    expect(ids).toEqual(['a', 'b']);
  });

  it('cancelScheduled drops a pending write without firing', async () => {
    scheduleBackendSync('p1', makeState());
    cancelScheduled('p1');

    vi.advanceTimersByTime(DEBOUNCE_MS * 2);
    await vi.runAllTimersAsync();

    expect(updateCalls).toHaveLength(0);
  });

  it('scheduling for two projects runs two independent timers', async () => {
    scheduleBackendSync('a', makeState());
    scheduleBackendSync('b', makeState());

    vi.advanceTimersByTime(DEBOUNCE_MS + 1);
    await vi.runAllTimersAsync();
    expect(updateCalls).toHaveLength(2);
    const ids = updateCalls.map((c) => c.projectId).sort();
    expect(ids).toEqual(['a', 'b']);
  });

  // --- Regression: "refresh after turn done clears the backend ring" ---
  //
  // `pendingState === null` was overloaded: the module used it both for
  // "nothing queued" AND for "please clear on server". Because
  // `scheduleBackendSync` never actually receives `null` from any caller
  // today (only legit state objects flow in), seeing `null` at flush-time
  // always means "nothing queued" and we MUST NOT send a null PATCH.
  // Otherwise the sequence "done fires flushNow -> finally fires flushNow
  // again -> refresh fires flushAllOnUnload" ends up PATCHing
  // `{context_usage: null}` and wipes the backend column.
  it('flushNow after the timer already fired is a no-op (does NOT null-out the backend)', async () => {
    scheduleBackendSync('p1', makeState());

    // Let the debounce fire naturally — the 1st PATCH is expected.
    vi.advanceTimersByTime(DEBOUNCE_MS + 1);
    await vi.runAllTimersAsync();
    expect(updateCalls).toHaveLength(1);
    expect((updateCalls[0].body as { state: ContextUsageState }).state).toBeDefined();

    // Now the `finally` path (or any other critical hook) calls flushNow.
    // Before the fix this produced a second PATCH with `context_usage: null`,
    // wiping the column. After the fix it's a no-op.
    await flushNow('p1');
    expect(updateCalls).toHaveLength(1);
    // And definitely not a null-payload PATCH.
    for (const call of updateCalls) {
      expect(call.body).not.toBeNull();
    }
  });

  it('repeated flushNow calls without new scheduling do not issue redundant null PATCHes', async () => {
    scheduleBackendSync('p1', makeState());
    await flushNow('p1');
    expect(updateCalls).toHaveLength(1);

    await flushNow('p1');
    await flushNow('p1');
    expect(updateCalls).toHaveLength(1);
  });

  it('flushAllOnUnload does NOT send a null PATCH after the last snapshot was already flushed', () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() =>
        Promise.resolve(
          new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
        ),
      );

    scheduleBackendSync('p1', makeState());
    // Fire the debounce so the real PATCH lands.
    vi.advanceTimersByTime(DEBOUNCE_MS + 1);
    // We deliberately don't await here: the point is that unload happens
    // *after* the setTimeout callback emptied `pendingState` to null.
    // Any pending microtasks from the flush don't matter — the in-flight
    // fetch has already been issued.

    // Now simulate the browser firing pagehide/beforeunload.
    flushAllOnUnload();

    // The only fetch we expect is the original debounce PATCH (if the
    // sync module routed it through projectsApi.updateContextUsage, it
    // goes through the mocked `updateContextUsage` below and not through
    // `fetch`; in that case fetchSpy should have ZERO calls). What MUST
    // be true is: no fetch with `context_usage: null` body.
    for (const [, init] of fetchSpy.mock.calls) {
      const body = JSON.parse(String((init as RequestInit).body ?? '{}')) as {
        context_usage?: unknown;
      };
      expect(body.context_usage).not.toBeNull();
    }

    fetchSpy.mockRestore();
  });

  it('flushAllOnUnload issues keepalive fetches for every pending project', () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() =>
        Promise.resolve(
          new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
        ),
      );

    scheduleBackendSync('a', makeState());
    scheduleBackendSync('b', makeState());

    flushAllOnUnload();

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const calls = fetchSpy.mock.calls.map((c) => c[1]);
    for (const init of calls) {
      expect(init?.method).toBe('PATCH');
      expect((init as RequestInit).keepalive).toBe(true);
    }

    fetchSpy.mockRestore();
  });
});
