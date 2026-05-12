import { act, renderHook, waitFor } from '@testing-library/react';
import { projectsApi, type AnalysisProgress } from '@/lib/api-client';
import {
  useAnalysisProgressRestore,
  applyProgressUpdater,
  isProgressTimelineTerminalComplete,
  resetAnalysisProgressRestoreModuleGuards,
} from '@/hooks/useAnalysisProgressRestore';
import { createEmptyStreamingState } from '@/types/streaming';
import { clearHitlSubmittedParams, saveHitlSubmittedParams } from '@/lib/hitlSubmittedParamsStorage';

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return {
    ...actual,
    projectsApi: {
      ...actual.projectsApi,
      getAnalysisProgress: vi.fn(),
    },
  };
});

const mockGetAnalysisProgress = vi.mocked(projectsApi.getAnalysisProgress);

const makeProgress = (overrides: Partial<AnalysisProgress> = {}): AnalysisProgress => ({
  is_analyzing: true,
  user_input: 'analyze file',
  thinking_steps: [{ id: 's1', label: 'running', status: 'running' }],
  task_plan: { id: 'p1', tasks: [] },
  understanding: { summary: 'understood' },
  task_summary: 'summary',
  conclusion: 'detail',
  blocks: [{ type: 'analysis', id: 'b1', content: 'detail' }],
  timeline: [],
  updated_at: new Date().toISOString(),
  ...overrides,
});

describe('isProgressTimelineTerminalComplete', () => {
  it('is false when the last done is an HITL pause', () => {
    const timeline = [
      { type: 'step', id: 's1' },
      { type: 'done', id: 'd1', awaitingHuman: true },
    ];
    expect(isProgressTimelineTerminalComplete(timeline)).toBe(false);
  });

  it('is true when the chronologically last done is not awaiting human', () => {
    const timeline = [
      { type: 'done', id: 'd1', awaitingHuman: true },
      { type: 'parameter_response', id: 'pr', parameters: {} },
      { type: 'done', id: 'd2', awaitingHuman: false },
    ];
    expect(isProgressTimelineTerminalComplete(timeline)).toBe(true);
  });

  it('ignores trailing non-done events and uses the last done', () => {
    const timeline = [
      { type: 'done', id: 'd1', awaitingHuman: true },
      { type: 'parameter_response', id: 'pr', parameters: {} },
      { type: 'step', id: 's2', status: 'running' },
    ];
    expect(isProgressTimelineTerminalComplete(timeline)).toBe(false);
  });
});

describe('useAnalysisProgressRestore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetAnalysisProgressRestoreModuleGuards();
    clearHitlSubmittedParams('proj-hitl-store', 'req-99');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('restores live state when backend reports is_analyzing=true', async () => {
    mockGetAnalysisProgress.mockResolvedValue({ data: makeProgress(), error: null });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['project-1'], updateState, loadProjects));

    await waitFor(() => {
      expect(mockGetAnalysisProgress).toHaveBeenCalledWith('project-1');
      expect(updateState).toHaveBeenCalled();
    });

    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());
    expect(restored.isAnalyzing).toBe(true);
    expect(restored.userInput).toBe('analyze file');
    expect(restored.taskSummary).toBe('summary');
    expect(restored.conclusion).toBe('detail');
    expect(restored.blocks).toHaveLength(1);
  });

  it('maps API timeline into streaming state for ReAct replay', async () => {
    const timeline = [{ type: 'tool_call', toolName: 'x', id: 't1' }];
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({ timeline: timeline as AnalysisProgress['timeline'] }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['project-1'], updateState, loadProjects));

    await waitFor(() => {
      expect(updateState).toHaveBeenCalled();
    });
    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());
    expect(restored.timeline).toEqual(timeline);
    expect(restored.currentReasoning).toBe('');
  });

  it('restores HITL submitted field values from sessionStorage using progress request_id', async () => {
    saveHitlSubmittedParams('proj-hitl-store', 'req-99', { reply: 'stored-clarification' });
    const timeline = [
      {
        type: 'parameter_request',
        seq: 1,
        id: 'p1',
        parameterRequests: [
          {
            id: 'reply',
            name: 'reply',
            description: '',
            paramType: 'text',
            required: true,
            encrypted: false,
          },
        ],
      },
      { type: 'done', seq: 2, id: 'done', awaitingHuman: true },
    ];
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({
        request_id: 'req-99',
        timeline: timeline as AnalysisProgress['timeline'],
      }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['proj-hitl-store'], updateState, loadProjects));

    await waitFor(() => expect(updateState).toHaveBeenCalled());

    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());
    expect(restored.hitlParametersSubmitted).toBe(true);
    expect(restored.submittedParameters?.reply).toBe('stored-clarification');
    expect(restored.hitlProgressRequestId).toBe('req-99');
    clearHitlSubmittedParams('proj-hitl-store', 'req-99');
  });

  it('restores HITL submitted fields from timeline parameter_response without sessionStorage', async () => {
    const timeline = [
      {
        type: 'parameter_request',
        seq: 1,
        id: 'p1',
        parameterRequests: [
          {
            id: 'reply',
            name: 'reply',
            description: '',
            paramType: 'text',
            required: true,
            encrypted: false,
          },
        ],
      },
      { type: 'done', seq: 2, id: 'done', awaitingHuman: true },
      {
        type: 'parameter_response',
        seq: 3,
        id: 'hitl-parameter-response',
        parameters: { reply: 'persisted-in-db' },
      },
      { type: 'step', seq: 4, id: 's2', label: 'Thought', status: 'running' },
    ];
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({
        request_id: 'req-db-tl',
        timeline: timeline as AnalysisProgress['timeline'],
      }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['proj-db-timeline'], updateState, loadProjects));

    await waitFor(() => expect(updateState).toHaveBeenCalled());

    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());
    expect(restored.hitlParametersSubmitted).toBe(true);
    expect(restored.submittedParameters?.reply).toBe('persisted-in-db');
    expect(restored.hitlProgressRequestId).toBe('req-db-tl');
  });

  it('applyProgressUpdater sets isAnalyzing false when API row is running but timeline ended with final done', () => {
    const timeline = [
      { type: 'done', seq: 1, id: 'd1', awaitingHuman: true },
      { type: 'parameter_response', seq: 2, id: 'pr', parameters: { reply: 'ok' } },
      { type: 'done', seq: 3, id: 'd2', awaitingHuman: false },
    ];
    const progress = makeProgress({
      timeline: timeline as AnalysisProgress['timeline'],
    });
    const state = applyProgressUpdater(createEmptyStreamingState(), progress, 'proj-stale');
    expect(state.isAnalyzing).toBe(false);
    expect(state.hitlProgressRequestId).toBeUndefined();
  });

  it('stops treating stale running row as in-progress: clears state, reloads, no poll interval', async () => {
    vi.useFakeTimers();
    const timeline = [
      { type: 'done', seq: 1, id: 'd1', awaitingHuman: true },
      { type: 'parameter_response', seq: 2, id: 'pr', parameters: {} },
      { type: 'done', seq: 3, id: 'd2', awaitingHuman: false },
    ];
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({
        timeline: timeline as AnalysisProgress['timeline'],
      }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() =>
      useAnalysisProgressRestore(['proj-stale-row'], updateState, loadProjects),
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(loadProjects).toHaveBeenCalledTimes(1);
    expect(mockGetAnalysisProgress).toHaveBeenCalledTimes(1);
    expect(updateState).toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(12_000);
      await Promise.resolve();
    });

    expect(mockGetAnalysisProgress).toHaveBeenCalledTimes(1);
  });

  it('clears live state and reloads history when polling sees completion', async () => {
    vi.useFakeTimers();
    mockGetAnalysisProgress
      .mockResolvedValueOnce({ data: makeProgress(), error: null })
      .mockResolvedValueOnce({ data: makeProgress({ is_analyzing: false }), error: null });

    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['project-1'], updateState, loadProjects));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(updateState).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(loadProjects).toHaveBeenCalledTimes(1);
    expect(updateState).toHaveBeenCalledTimes(2);

    const clearUpdater = updateState.mock.calls[1][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const previous = {
      ...createEmptyStreamingState(),
      isAnalyzing: true,
      userInput: 'keep-me-cleared',
      sseEventLogs: [{ id: 'e1' } as any],
    };
    const cleared = clearUpdater(previous);
    expect(cleared.isAnalyzing).toBe(false);
    expect(cleared.userInput).toBe('');
    expect(cleared.sseEventLogs).toEqual(previous.sseEventLogs);
  });

  it('skips fetch and state writes while local stream owns the project', async () => {
    // If this predicate fires, the hook must not call getAnalysisProgress
    // nor touch updateState — otherwise it races with the in-flight SSE
    // stream and causes the button/timer flicker + duplicated Q&A.
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);
    const isLocallyStreaming = vi.fn(() => true);

    renderHook(() =>
      useAnalysisProgressRestore(
        ['project-local-stream'],
        updateState,
        loadProjects,
        undefined,
        isLocallyStreaming,
      ),
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(isLocallyStreaming).toHaveBeenCalledWith('project-local-stream');
    expect(mockGetAnalysisProgress).not.toHaveBeenCalled();
    expect(updateState).not.toHaveBeenCalled();
  });

  it('stopPolling halts future poll ticks without touching live state', async () => {
    // Reproduces the "~20s later the chat visually refreshes once" bug:
    // after the local stream finalizes, the restore hook's 3s poll would
    // eventually see backend `is_analyzing=false` and call
    // `clearProjectLiveState` + `reloadProjectMessages`, re-rendering the
    // whole conversation. `stopPolling` must cancel the timer silently
    // (no reloadProjectMessages, no extra updateState).
    mockGetAnalysisProgress.mockResolvedValue({ data: makeProgress(), error: null });

    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');

    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAnalysisProgressRestore(
        ['project-stop-poll'],
        updateState,
        loadProjects,
        reloadProjectMessages,
      ),
    );

    await waitFor(() => {
      expect(updateState).toHaveBeenCalledTimes(1);
    });

    // The hook installed exactly one 3s polling interval for this project.
    const pollingSchedule = setIntervalSpy.mock.calls.find(
      ([, ms]) => ms === 3000,
    );
    expect(pollingSchedule).toBeDefined();

    const clearCallsBefore = clearIntervalSpy.mock.calls.length;
    act(() => {
      result.current.stopPolling('project-stop-poll');
    });
    expect(clearIntervalSpy.mock.calls.length).toBeGreaterThan(clearCallsBefore);

    // The local state was not touched, and no message reload was triggered.
    expect(reloadProjectMessages).not.toHaveBeenCalled();
    expect(updateState).toHaveBeenCalledTimes(1);

    setIntervalSpy.mockRestore();
    clearIntervalSpy.mockRestore();
  });

  it('U-01: in-flight getAnalysisProgress resolving after stopPolling does not trigger reloadProjectMessages (post-stream quiet window)', async () => {
    // The bug: setInterval tick fires `getAnalysisProgress` (an async fetch);
    // before that promise resolves the local stream finalizes and calls
    // `stopPolling`. The fetch then resolves with `is_analyzing=false` (or a
    // terminal-timeline progress) and walks straight into
    // `finishProgressForProject` → `reloadProjectMessages`, which re-mounts
    // the entire conversation ~3-10s after the report already settled.
    //
    // After the fix, `stopPolling` records a timestamp and any post-fetch
    // branch within the quiet window is silently dropped.
    vi.useFakeTimers();

    // First call (bootstrap) — synchronous resolve so the hook starts the
    // setInterval timer.
    mockGetAnalysisProgress.mockResolvedValueOnce({
      data: makeProgress(),
      error: null,
    });

    // Second call (the "in-flight" tick) — manually controlled promise so we
    // can resolve it AFTER stopPolling.
    let resolveInFlight: (value: { data: AnalysisProgress | null; error: null }) => void = () => {};
    const inFlightPromise = new Promise<{ data: AnalysisProgress | null; error: null }>((r) => {
      resolveInFlight = r;
    });
    mockGetAnalysisProgress.mockReturnValueOnce(inFlightPromise as ReturnType<typeof projectsApi.getAnalysisProgress>);

    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAnalysisProgressRestore(
        ['project-inflight'],
        updateState,
        loadProjects,
        reloadProjectMessages,
      ),
    );

    // Drain the bootstrap fetch so the polling interval is installed.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(updateState).toHaveBeenCalled();

    // Tick the 3s interval — this dispatches the in-flight fetch but does
    // not yet resolve it.
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    // Local stream finishes; quiet window starts here.
    act(() => {
      result.current.stopPolling('project-inflight');
    });

    // In-flight fetch resolves with a "no longer analyzing" payload — the
    // canonical trigger that would otherwise call reloadProjectMessages.
    resolveInFlight({
      data: makeProgress({ is_analyzing: false }),
      error: null,
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(reloadProjectMessages).not.toHaveBeenCalled();
    expect(loadProjects).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('U-03: after quiet window expires, local stopPolling still suppresses reloadProjectMessages', async () => {
    vi.useFakeTimers();
    const t0 = 1_700_000_000_000;
    vi.setSystemTime(t0);

    mockGetAnalysisProgress.mockResolvedValueOnce({
      data: makeProgress(),
      error: null,
    });

    let resolveInFlight: (value: { data: AnalysisProgress | null; error: null }) => void = () => {};
    const inFlightPromise = new Promise<{ data: AnalysisProgress | null; error: null }>((r) => {
      resolveInFlight = r;
    });
    mockGetAnalysisProgress.mockReturnValueOnce(inFlightPromise as ReturnType<typeof projectsApi.getAnalysisProgress>);

    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAnalysisProgressRestore(
        ['project-suppress-long'],
        updateState,
        loadProjects,
        reloadProjectMessages,
      ),
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(updateState).toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    act(() => {
      result.current.stopPolling('project-suppress-long');
    });

    vi.setSystemTime(t0 + 30_000 + 5_000);

    resolveInFlight({
      data: makeProgress({ is_analyzing: false }),
      error: null,
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(reloadProjectMessages).not.toHaveBeenCalled();
    expect(loadProjects).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('U-02: effect re-subscription within the quiet window does not restart polling', async () => {
    // The other escape path: the polling effect's deps include caller
    // callbacks (`loadProjects`, `reloadProjectMessages`). Right after
    // `appendToConversation` the parent component re-renders with new
    // function identities, which re-runs the effect. Without the quiet
    // window the bootstrap step would re-fetch progress and re-create the
    // setInterval, since the backend `is_analyzing` row is still stale-true.
    vi.useFakeTimers();

    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress(),
      error: null,
    });

    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const updateState = vi.fn();
    const loadProjectsA = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result, rerender } = renderHook(
      ({ loadProjects }: { loadProjects: () => Promise<void> }) =>
        useAnalysisProgressRestore(
          ['project-resub'],
          updateState,
          loadProjects,
          reloadProjectMessages,
        ),
      { initialProps: { loadProjects: loadProjectsA } },
    );

    // Drain bootstrap and confirm exactly one polling interval is installed.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const intervalsAfterBootstrap = setIntervalSpy.mock.calls.filter(
      ([, ms]) => ms === 3000,
    ).length;
    expect(intervalsAfterBootstrap).toBe(1);

    // Local stream finishes; quiet window starts.
    act(() => {
      result.current.stopPolling('project-resub');
    });

    // Parent re-renders with a new `loadProjects` identity → the effect
    // re-runs. Backend is_analyzing is still stale-true.
    const loadProjectsB = vi.fn().mockResolvedValue(undefined);
    rerender({ loadProjects: loadProjectsB });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    // No additional 3s interval should have been installed: the quiet
    // window must skip the bootstrap branch for this project.
    const intervalsAfterRerender = setIntervalSpy.mock.calls.filter(
      ([, ms]) => ms === 3000,
    ).length;
    expect(intervalsAfterRerender).toBe(intervalsAfterBootstrap);
    expect(reloadProjectMessages).not.toHaveBeenCalled();
    expect(loadProjectsB).not.toHaveBeenCalled();

    setIntervalSpy.mockRestore();
    vi.useRealTimers();
  });

  it('U-03: polling resumes normally after the quiet window expires', async () => {
    // Sanity check: the quiet window is finite. After it elapses, a real
    // re-subscription (e.g. project list rebuilt much later) must be able
    // to start polling again.
    vi.useFakeTimers();

    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress(),
      error: null,
    });

    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const updateState = vi.fn();
    const loadProjectsA = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result, rerender } = renderHook(
      ({ loadProjects }: { loadProjects: () => Promise<void> }) =>
        useAnalysisProgressRestore(
          ['project-expiry'],
          updateState,
          loadProjects,
          reloadProjectMessages,
        ),
      { initialProps: { loadProjects: loadProjectsA } },
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const intervalsAfterBootstrap = setIntervalSpy.mock.calls.filter(
      ([, ms]) => ms === 3000,
    ).length;
    expect(intervalsAfterBootstrap).toBe(1);

    act(() => {
      result.current.stopPolling('project-expiry');
    });

    // Advance past the 30s quiet window and the same-tab stale-apply / reload
    // suppress TTL (aligned with PROGRESS_RELOAD_SUPPRESS_MS = 10min).
    await act(async () => {
      vi.advanceTimersByTime(10 * 60 * 1000 + 1000);
    });

    // Fresh re-subscription after suppress TTL expired — should be
    // treated as a normal restore session and resume polling.
    const loadProjectsB = vi.fn().mockResolvedValue(undefined);
    rerender({ loadProjects: loadProjectsB });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const intervalsAfterRerender = setIntervalSpy.mock.calls.filter(
      ([, ms]) => ms === 3000,
    ).length;
    expect(intervalsAfterRerender).toBeGreaterThan(intervalsAfterBootstrap);

    setIntervalSpy.mockRestore();
    vi.useRealTimers();
  });

  it('U-04: in-flight poll fetch resolving with is_analyzing=true does not overwrite local state during the quiet window', async () => {
    // The hidden bug after the first U-01 fix: poll() has TWO post-fetch
    // exits — the "no longer analyzing" exit (caught by U-01 via
    // finishProgressForProject) AND a direct `updateState(...)` write when
    // backend still reports `is_analyzing: true`. The second branch is what
    // produced the visible "content flashes" the user saw a few seconds
    // after a deep-research / security task settled: setInterval kicked off
    // a fetch, `stopPolling` fired (clearInterval can't cancel an already
    // dispatched fetch), and the late fetch resolved with stale
    // is_analyzing=true (debounce had not drained), overwriting the
    // freshly-finalized local streaming state.
    vi.useFakeTimers();

    // Bootstrap fetch — resolves synchronously so the polling timer installs.
    mockGetAnalysisProgress.mockResolvedValueOnce({
      data: makeProgress(),
      error: null,
    });

    // Tick fetch — manually resolved later, after stopPolling.
    let resolveTick: (value: { data: AnalysisProgress | null; error: null }) => void = () => {};
    const tickPromise = new Promise<{ data: AnalysisProgress | null; error: null }>((r) => {
      resolveTick = r;
    });
    mockGetAnalysisProgress.mockReturnValueOnce(
      tickPromise as ReturnType<typeof projectsApi.getAnalysisProgress>,
    );

    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAnalysisProgressRestore(
        ['project-stale-true'],
        updateState,
        loadProjects,
        reloadProjectMessages,
      ),
    );

    // Drain bootstrap so the 3s interval is armed and the first updateState
    // (from the bootstrap progress) lands. Capture the call count so we can
    // assert nothing happens after stopPolling.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const updatesAfterBootstrap = updateState.mock.calls.length;
    expect(updatesAfterBootstrap).toBeGreaterThan(0);

    // Tick the interval — dispatches a real fetch but doesn't resolve it yet.
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    // Local stream finalizes; quiet window starts.
    act(() => {
      result.current.stopPolling('project-stale-true');
    });

    // The in-flight fetch resolves with stale is_analyzing=true (backend
    // debounce hasn't drained). Without the fix this would walk straight
    // into the `updateState(...)` branch and visibly re-render the chat.
    resolveTick({
      data: makeProgress({ is_analyzing: true }),
      error: null,
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // No additional state writes after stopPolling.
    expect(updateState.mock.calls.length).toBe(updatesAfterBootstrap);
    expect(reloadProjectMessages).not.toHaveBeenCalled();
    expect(loadProjects).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('U-05: in-flight bootstrap getAnalysisProgress after stopPolling does not call applyProgressUpdater', async () => {
    // Bootstrap only checked the quiet window *before* awaiting the fetch. If
    // `stopPolling` runs while that request is in flight, the post-await path
    // must re-check the window — otherwise a stale `is_analyzing: true` row
    // lands ~one network tick later and flashes the workspace (~2–3s).
    vi.useFakeTimers();

    let resolveBootstrap: (value: { data: AnalysisProgress | null; error: null }) => void = () => {};
    const bootstrapPromise = new Promise<{ data: AnalysisProgress | null; error: null }>((r) => {
      resolveBootstrap = r;
    });
    mockGetAnalysisProgress.mockReturnValueOnce(
      bootstrapPromise as ReturnType<typeof projectsApi.getAnalysisProgress>,
    );

    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAnalysisProgressRestore(
        ['project-bootstrap-inflight'],
        updateState,
        loadProjects,
        reloadProjectMessages,
      ),
    );

    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      result.current.stopPolling('project-bootstrap-inflight');
    });

    resolveBootstrap({
      data: makeProgress({ is_analyzing: true }),
      error: null,
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(updateState).not.toHaveBeenCalled();
    expect(reloadProjectMessages).not.toHaveBeenCalled();
    expect(loadProjects).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('U-06: stale-apply TTL still blocks applyProgressUpdater after 30s quiet (no workspace flash)', async () => {
    vi.useFakeTimers();
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({ is_analyzing: true }),
      error: null,
    });

    const updateState = vi.fn();
    const loadProjectsA = vi.fn().mockResolvedValue(undefined);
    const reloadProjectMessages = vi.fn().mockResolvedValue(undefined);

    const { result, rerender } = renderHook(
      ({ loadProjects }: { loadProjects: () => Promise<void> }) =>
        useAnalysisProgressRestore(
          ['project-suppress-post-quiet'],
          updateState,
          loadProjects,
          reloadProjectMessages,
        ),
      { initialProps: { loadProjects: loadProjectsA } },
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockGetAnalysisProgress.mock.calls.length).toBeGreaterThan(0);
    expect(updateState.mock.calls.length).toBeGreaterThan(0);

    mockGetAnalysisProgress.mockClear();
    updateState.mockClear();

    act(() => {
      result.current.stopPolling('project-suppress-post-quiet');
    });

    // Past 30s quiet, but still inside same-tab stale-apply merge guard (10min).
    await act(async () => {
      vi.advanceTimersByTime(31_000);
    });

    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({ is_analyzing: true }),
      error: null,
    });

    const loadProjectsB = vi.fn().mockResolvedValue(undefined);
    rerender({ loadProjects: loadProjectsB });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(updateState).not.toHaveBeenCalled();
    expect(reloadProjectMessages).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('applyProgressUpdater preserves thinking timer across successive polls for the same turn', () => {
    // Purely functional check: when the user_input and isAnalyzing flag still
    // describe the same in-progress turn, the merge must reuse the previous
    // `thinkingStartTime` and `inputTimestamp` so the visible timer does not
    // snap back to 0 on every 3s poll.
    const progress = makeProgress({ user_input: 'same turn' });
    const empty = createEmptyStreamingState();

    const firstState = applyProgressUpdater(empty, progress, 'project-timer');
    expect(firstState.isAnalyzing).toBe(true);
    expect(firstState.userInput).toBe('same turn');
    const anchorThinking = firstState.thinkingStartTime;
    const anchorInput = firstState.inputTimestamp;
    expect(anchorThinking).toBeInstanceOf(Date);
    expect(anchorInput).toBeInstanceOf(Date);

    const secondState = applyProgressUpdater(firstState, progress, 'project-timer');
    expect(secondState.thinkingStartTime).toBe(anchorThinking);
    expect(secondState.inputTimestamp).toBe(anchorInput);

    // Different user_input → treated as a new turn; fresh anchors.
    const nextTurnProgress = makeProgress({ user_input: 'brand new turn' });
    const thirdState = applyProgressUpdater(secondState, nextTurnProgress, 'project-timer');
    expect(thirdState.thinkingStartTime).not.toBe(anchorThinking);
    expect(thirdState.inputTimestamp).not.toBe(anchorInput);
  });

  it('restores analysisMode and currentTaskId from progress', async () => {
    const taskPlan = {
      id: 'p1',
      tasks: [
        { id: '0', title: 'Task 0', status: 'success', steps: [] },
        { id: '1', title: 'Task 1', status: 'running', steps: [] },
      ],
      currentTaskId: '1',
    };
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({ task_plan: taskPlan }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['project-1'], updateState, loadProjects));

    await waitFor(() => {
      expect(updateState).toHaveBeenCalled();
    });

    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());

    expect(restored.analysisMode).toBe('deepagent');
    expect(restored.currentTaskId).toBe('1');
    expect(restored.taskPlanMain).not.toBeNull();
    expect(restored.taskPlanMain!.tasks[0].status).toBe('success');
    expect(restored.taskPlanMain!.tasks[1].status).toBe('running');
  });

  it('derives currentTaskId from running task when backend omits currentTaskId', async () => {
    const taskPlan = {
      id: 'p1',
      tasks: [
        { id: 'a', title: 'A', status: 'success', steps: [] },
        { id: 'b', title: 'B', status: 'running', steps: [] },
      ],
      // no currentTaskId field
    };
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({ task_plan: taskPlan }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['proj-2'], updateState, loadProjects));

    await waitFor(() => expect(updateState).toHaveBeenCalled());

    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());

    expect(restored.currentTaskId).toBe('b');
  });

  it('sets analysisMode to deepagent when understanding exists but no taskPlan', async () => {
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({ task_plan: null, understanding: { summary: 'yes' } }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['proj-3'], updateState, loadProjects));

    await waitFor(() => expect(updateState).toHaveBeenCalled());

    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());

    expect(restored.analysisMode).toBe('deepagent');
    expect(restored.currentTaskId).toBeUndefined();
  });

  it('sets analysisMode to unknown when no taskPlan and no understanding', async () => {
    mockGetAnalysisProgress.mockResolvedValue({
      data: makeProgress({ task_plan: null, understanding: null }),
      error: null,
    });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useAnalysisProgressRestore(['proj-4'], updateState, loadProjects));

    await waitFor(() => expect(updateState).toHaveBeenCalled());

    const updater = updateState.mock.calls[0][1] as (prev: ReturnType<typeof createEmptyStreamingState>) => ReturnType<typeof createEmptyStreamingState>;
    const restored = updater(createEmptyStreamingState());

    expect(restored.analysisMode).toBe('unknown');
  });

  it('stops polling after cancelRestore', async () => {
    vi.useFakeTimers();
    mockGetAnalysisProgress.mockResolvedValue({ data: makeProgress(), error: null });
    const updateState = vi.fn();
    const loadProjects = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAnalysisProgressRestore(['project-1'], updateState, loadProjects),
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(updateState).toHaveBeenCalled();

    act(() => {
      result.current.cancelRestore('project-1');
    });

    const callsBefore = mockGetAnalysisProgress.mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(9000);
      await Promise.resolve();
    });

    expect(mockGetAnalysisProgress).toHaveBeenCalledTimes(callsBefore);
  });
});
