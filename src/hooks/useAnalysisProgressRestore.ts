/**
 * Restore in-progress analysis state after page refresh.
 * Polls GET /projects/{id}/analysis-progress and updates StreamingStateContext
 * until the task completes.
 * Exposes cancelRestore(projectId) to stop polling when user clicks Stop on a restored session.
 *
 * IMPORTANT: Must stand down whenever the local frontend owns a live SSE stream
 * for the project. The restore path and the local stream write to the same
 * streaming state; if both run concurrently we get a race where the restore
 * overwrites a freshly completed turn (button bounces back to "working",
 * thinking timer resets, duplicated Q&A after history reload, etc.). The
 * `isLocallyStreaming` predicate lets the caller gate that out.
 */
import { useEffect, useRef, useCallback } from 'react';
import { projectsApi, type AnalysisProgress } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { ReloadProjectMessagesMeta } from '@/hooks/useProjects';

/**
 * True when the chronologically last `done` event in the timeline is not an
 * HITL pause (`awaitingHuman: true`). Used to ignore orphan `running` progress
 * rows when the backend failed to call clear_progress after a finished turn.
 */
export function isProgressTimelineTerminalComplete(timeline: unknown): boolean {
  if (!Array.isArray(timeline)) return false;
  for (let i = timeline.length - 1; i >= 0; i -= 1) {
    const e = timeline[i] as { type?: unknown; awaitingHuman?: unknown } | null;
    if (!e || typeof e !== 'object') continue;
    if (e.type === 'done') {
      return e.awaitingHuman !== true;
    }
  }
  return false;
}

function isStaleRunningProgressWithTerminalTimeline(data: AnalysisProgress | null | undefined): boolean {
  return Boolean(data?.is_analyzing && isProgressTimelineTerminalComplete(data.timeline));
}
import { createEmptyStreamingState } from '@/types/streaming';
import type { PerProjectStreamingState } from '@/types/streaming';
import type { AnalysisTimelineEntry, TaskPlan } from '@/types/analysis';
import { extractHitlUiStateFromTimeline } from '@/lib/hitlRestoreFromTimeline';
import { readHitlSubmittedParams } from '@/lib/hitlSubmittedParamsStorage';
import { extractSubagentTaskPlansFromTimeline } from '@/lib/timelineDisplay';
import { scrubTaskPlanPathsForDisplay } from '@/lib/scrubVirtualPathsForDisplay';

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 600_000; // 10 min max
/** Correlates mount → reload logs across Strict Mode remounts / deps churn. */
let progressRestorePollEffectSeq = 0;
/**
 * Suppress/recent-stop timestamps MUST survive `useAnalysisProgressRestore` hook remounts.
 * React 18 Strict Mode (and parent remounts) create a new hook instance; `useRef` Maps reset
 * and lose `stopPolling` TTL → `finishProgressForProject` runs later with empty suppress →
 * `reload_project_messages` flashes ~30–90s after SSE (exact timing depends on poll/bootstrap).
 */
const progressRestoreStoppedAtMs = new Map<string, number>();
const progressRestoreSuppressUntilMs = new Map<string, number>();
// After a local SSE stream finishes the backend `is_analyzing` row stays
// stale-true for up to ~20s while its write debounce drains. Anything that
// could still call `reloadProjectMessages` for that project during this
// window (an in-flight poll fetch resolving, the polling effect re-running
// because parent callbacks changed identity) would re-mount the chat list
// and look like a "page just refreshed" several seconds after the turn
// already settled. The local stream's `onProjectAnalysisComplete` calls
// `stopPolling`, which seeds a timestamp consulted by both escape paths.
const POST_STREAM_QUIET_WINDOW_MS = 30_000;
// After the quiet window expires, a stale `analysis-progress` row can still
// drive `finishProgressForProject` (e.g. `is_analyzing: true` with a terminal
// `done` timeline, or a late poll seeing `is_analyzing: false`). That path
// calls `reloadProjectMessages` and re-mounts chat + workspace from the DB —
// the "second refresh" users still see on long-running turns (web file /
// security). Suppress that reload for a longer TTL after any local `stopPolling`
// (fresh page load has no entry → restore still reloads). Cleared on
// `cancelRestore` (user Stop).
const PROGRESS_RELOAD_SUPPRESS_MS = 10 * 60 * 1000;
// After SSE completes, GET /analysis-progress can still return stale
// `is_analyzing: true` well past the 30s quiet window (backend debounce / row lag).
// That path calls `applyProgressUpdater` (not `reloadProjectMessages`) but still
// flashes the workspace like a "second refresh". Users reported ~1min flashes when
// stale-apply TTL was 60s while reload suppress stayed 10min — so apply must use the
// same TTL as module `progressRestoreSuppressUntilMs` after `stopPolling`. Fresh page load
// has no suppress entries → restore behavior unchanged.

function progressToState(p: AnalysisProgress, projectId: string): Partial<PerProjectStreamingState> {
  const taskPlanRaw = p.task_plan || null;
  const taskPlan = taskPlanRaw ? scrubTaskPlanPathsForDisplay(taskPlanRaw as TaskPlan) : null;

  // Derive currentTaskId from the task plan's running task
  let currentTaskId: string | undefined;
  if (taskPlan) {
    // Backend now includes currentTaskId in the plan via _apply_task_lifecycle
    currentTaskId = (taskPlan as Record<string, unknown>).currentTaskId as string | undefined;
    if (!currentTaskId) {
      const running = (taskPlan.tasks as Array<{ id: string; status: string }>)?.find(
        (t) => t.status === 'running',
      );
      currentTaskId = running?.id;
    }
  }

  // Detect analysis mode: presence of task_plan implies deepagent
  const analysisMode = taskPlan ? 'deepagent' : (p.understanding ? 'deepagent' : 'unknown');

  const timeline = Array.isArray(p.timeline)
    ? (p.timeline as AnalysisTimelineEntry[])
    : [];

  const hitl = extractHitlUiStateFromTimeline(timeline);
  const progressRid = typeof p.request_id === 'string' && p.request_id.trim() ? p.request_id.trim() : '';

  const pid = (projectId || '').trim();
  const shouldTryHitlStorage =
    Boolean(pid && progressRid) &&
    (hitl.parameterRequests.length > 0 || hitl.hitlAwaiting || hitl.hitlResumeInFlight);
  const storedSubmitted = shouldTryHitlStorage ? readHitlSubmittedParams(pid, progressRid) : {};
  const fromDbTimeline = hitl.submittedParametersFromTimeline;
  const hitlParametersSubmitted =
    hitl.hitlResumeInFlight ||
    Object.keys(storedSubmitted).length > 0 ||
    Object.keys(fromDbTimeline).length > 0;

  const terminalTimelineComplete = isProgressTimelineTerminalComplete(p.timeline);
  const effectiveIsAnalyzing =
    Boolean(p.is_analyzing) && !hitl.hitlAwaiting && !terminalTimelineComplete;

  return {
    // Paused for HITL: no main analyzing spinner. Resume in flight: follow backend is_analyzing.
    // Orphan running row + terminal `done`: treat as idle (backend clear_progress may have been skipped).
    isAnalyzing: effectiveIsAnalyzing,
    userInput: p.user_input || '',
    // Timestamps are intentionally omitted here; the updater merges them onto
    // the previous state so the thinking timer does not reset on every poll.
    timeline,
    // Timeline is canonical for ReAct replay; avoid duplicating aggregated text in currentReasoning.
    currentReasoning: '',
    taskPlanMain: taskPlan,
    taskPlansSubagent: extractSubagentTaskPlansFromTimeline(timeline),
    currentTaskId,
    understanding: p.understanding || null,
    taskSummary: p.task_summary || '',
    conclusion: p.conclusion || '',
    blocks: Array.isArray(p.blocks) ? p.blocks : [],
    analysisMode: analysisMode as PerProjectStreamingState['analysisMode'],
    hitlAwaiting: hitl.hitlAwaiting,
    hitlSnapshot: hitl.hitlSnapshot,
    parameterRequests: hitl.parameterRequests,
    parameterRequestDetail: hitl.parameterRequestDetail,
    decisions: hitl.decisions,
    resolvedDecisions: { ...hitl.resolvedDecisionsFromTimeline },
    hitlParametersSubmitted,
    submittedParameters: { ...storedSubmitted, ...fromDbTimeline },
    // Stable correlation for omit + resume while this progress row is active.
    // Keep during HITL pause (UI isAnalyzing is false but row is still running).
    // Omit when timeline proves the turn finished but the row was not cleared.
    hitlProgressRequestId:
      Boolean(p.is_analyzing) && progressRid && !terminalTimelineComplete ? progressRid : undefined,
  };
}

/** Test-only: module guards persist across hook instances; reset between Vitest cases. */
export function resetAnalysisProgressRestoreModuleGuards(): void {
  progressRestoreStoppedAtMs.clear();
  progressRestoreSuppressUntilMs.clear();
}

export function applyProgressUpdater(
  prev: PerProjectStreamingState,
  data: AnalysisProgress,
  projectId: string,
): PerProjectStreamingState {
  const base = createEmptyStreamingState();
  const mapped = progressToState(data, projectId);
  const nextUserInput = (mapped.userInput ?? '') as string;
  const prevUserInput = prev.userInput ?? '';
  const sameTurn = prev.isAnalyzing && prevUserInput === nextUserInput && prevUserInput !== '';
  return {
    ...base,
    ...mapped,
    // Preserve developer event log across restore batches.
    sseEventLogs: prev.sseEventLogs,
    // Keep timer anchors stable while the same turn is still progressing so
    // the thinking animation does not restart on each 3s poll.
    inputTimestamp: sameTurn && prev.inputTimestamp ? prev.inputTimestamp : new Date(),
    thinkingStartTime: sameTurn && prev.thinkingStartTime ? prev.thinkingStartTime : new Date(),
  };
}

export function useAnalysisProgressRestore(
  projectIds: string[],
  updateState: (projectId: string, updater: (p: PerProjectStreamingState) => PerProjectStreamingState) => void,
  loadProjects: () => Promise<void>,
  reloadProjectMessages?: (
    projectId: string,
    meta?: ReloadProjectMessagesMeta,
  ) => Promise<void>,
  isLocallyStreaming?: (projectId: string) => boolean,
) {
  const intervalsRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  const startedAtRef = useRef<Map<string, number>>(new Map());

  const isInPostStreamQuietWindow = useCallback((projectId: string): boolean => {
    const ts = progressRestoreStoppedAtMs.get(projectId);
    if (typeof ts !== 'number') return false;
    if (Date.now() - ts > POST_STREAM_QUIET_WINDOW_MS) {
      progressRestoreStoppedAtMs.delete(projectId);
      return false;
    }
    return true;
  }, []);

  const isStaleProgressApplySuppressed = useCallback((projectId: string): boolean => {
    const until = progressRestoreSuppressUntilMs.get(projectId);
    return typeof until === 'number' && Date.now() < until;
  }, []);

  // Keep the latest predicate in a ref so the polling effect can see
  // up-to-date local-stream status without re-subscribing every render.
  const isLocallyStreamingRef = useRef<typeof isLocallyStreaming>(isLocallyStreaming);
  useEffect(() => {
    isLocallyStreamingRef.current = isLocallyStreaming;
  }, [isLocallyStreaming]);

  const clearProjectLiveState = useCallback((projectId: string) => {
    // If the local stream currently owns this project's state, leave it
    // alone. clearState() on StreamingStateContext already has an is_analyzing
    // guard for normal writes, but this hook bypasses it by building a fresh
    // empty state, so we must guard explicitly.
    if (isLocallyStreamingRef.current?.(projectId)) return;
    updateState(projectId, (prev) => ({
      ...createEmptyStreamingState(),
      sseEventLogs: prev.sseEventLogs,
    }));
  }, [updateState]);

  useEffect(() => {
    if (projectIds.length === 0) return;

    const pollEffectRunId = ++progressRestorePollEffectSeq;
    logger.info('progress_restore_poll_effect_start', {
      run_id: pollEffectRunId,
      project_ids: [...projectIds],
      project_count: projectIds.length,
    });

    const tearDownPollInterval = (projectId: string) => {
      const id = intervalsRef.current.get(projectId);
      if (id) {
        clearInterval(id);
        intervalsRef.current.delete(projectId);
        startedAtRef.current.delete(projectId);
      }
    };

    const finishProgressForProject = async (projectId: string, source: 'poll' | 'bootstrap') => {
      const now = Date.now();
      // Quiet window: the local stream has just finalized for this project
      // and any reload here would re-mount the chat list. Tear down the
      // timer (if any) but skip the live-state clear and the messages
      // reload — that's the "flash refresh" the user sees ~3-10s later.
      if (isInPostStreamQuietWindow(projectId)) {
        logger.info('progress_restore_finish_skipped_quiet_window', {
          poll_effect_run_id: pollEffectRunId,
          project_id: projectId,
          source,
          at_ms: now,
        });
        tearDownPollInterval(projectId);
        return;
      }
      const suppressUntil = progressRestoreSuppressUntilMs.get(projectId);
      if (typeof suppressUntil === 'number' && Date.now() < suppressUntil) {
        logger.info('progress_restore_finish_skipped_reload_suppressed', {
          poll_effect_run_id: pollEffectRunId,
          project_id: projectId,
          source,
          at_ms: now,
          suppress_reload_until_ms: suppressUntil,
          suppress_remaining_ms: suppressUntil - now,
        });
        tearDownPollInterval(projectId);
        return;
      }
      logger.warn('progress_restore_finish_reload', {
        poll_effect_run_id: pollEffectRunId,
        project_id: projectId,
        source,
        at_ms: now,
        action: reloadProjectMessages ? 'reload_project_messages' : 'load_projects_full',
      });
      tearDownPollInterval(projectId);
      clearProjectLiveState(projectId);
      if (reloadProjectMessages) {
        await reloadProjectMessages(projectId, {
          reason: 'progress_restore_finish',
          finish_source: source,
        });
      } else {
        logger.info('progress_restore_finish_load_projects_full', {
          poll_effect_run_id: pollEffectRunId,
          project_id: projectId,
          finish_source: source,
          at_ms: Date.now(),
        });
        await loadProjects();
      }
    };

    const poll = async (projectId: string) => {
      if (isLocallyStreamingRef.current?.(projectId)) return;
      try {
        const { data } = await projectsApi.getAnalysisProgress(projectId);
        // A local stream may have started between the fetch kickoff and its
        // resolution; re-check before touching state.
        if (isLocallyStreamingRef.current?.(projectId)) return;
        // Post-stream quiet window: a poll fetch dispatched by the previous
        // setInterval tick can outlive the `clearInterval(...)` issued by
        // `stopPolling`, then resolve seconds later. If the backend's
        // is_analyzing debounce has not drained yet (`is_analyzing` still
        // true), we would otherwise overwrite the freshly-finalized local
        // state with stale polled data — the visible "content flashes" the
        // user reports a few seconds after the turn settled. Drop the result.
        if (isInPostStreamQuietWindow(projectId)) return;
        if (!data?.is_analyzing || isStaleRunningProgressWithTerminalTimeline(data)) {
          logger.info('progress_restore_poll_terminal', {
            poll_effect_run_id: pollEffectRunId,
            project_id: projectId,
            is_analyzing: data?.is_analyzing ?? false,
            stale_terminal_timeline: isStaleRunningProgressWithTerminalTimeline(data),
            at_ms: Date.now(),
          });
          await finishProgressForProject(projectId, 'poll');
          return;
        }
        if (isStaleProgressApplySuppressed(projectId)) return;
        updateState(projectId, (prev) => applyProgressUpdater(prev, data, projectId));
      } catch {
        // Ignore poll errors
      }
    };

    for (const projectId of projectIds) {
      (async () => {
        if (isLocallyStreamingRef.current?.(projectId)) return;
        // Quiet window: skip bootstrap entirely so a parent re-render that
        // re-runs this effect (new `loadProjects` / `reloadProjectMessages`
        // identity right after `appendToConversation`) does not start a
        // fresh polling interval for a project we just stopped.
        if (isInPostStreamQuietWindow(projectId)) {
          logger.debug('progress_restore_bootstrap_skipped_quiet_window', {
            project_id: projectId,
            at_ms: Date.now(),
          });
          return;
        }
        try {
          const { data } = await projectsApi.getAnalysisProgress(projectId);
          if (isLocallyStreamingRef.current?.(projectId)) return;
          // Bootstrap can overlap stream finalization: the pre-fetch quiet check
          // may have passed, then `stopPolling` opens the window before this
          // request resolves. Without a post-await guard the late response still
          // calls `applyProgressUpdater` (~POLL_INTERVAL_MS later) and flashes UI.
          if (isInPostStreamQuietWindow(projectId)) return;
          if (!data?.is_analyzing) return;

          if (isStaleRunningProgressWithTerminalTimeline(data)) {
            await finishProgressForProject(projectId, 'bootstrap');
            return;
          }

          if (isStaleProgressApplySuppressed(projectId)) return;

          startedAtRef.current.set(projectId, Date.now());
          logger.debug('progress_restore_poll_interval_started', {
            poll_effect_run_id: pollEffectRunId,
            project_id: projectId,
            interval_ms: POLL_INTERVAL_MS,
            at_ms: Date.now(),
          });
          updateState(projectId, (prev) => applyProgressUpdater(prev, data, projectId));

          const id = setInterval(() => {
            const started = startedAtRef.current.get(projectId);
            if (started && Date.now() - started > POLL_TIMEOUT_MS) {
              logger.warn('progress_restore_poll_timeout', { project_id: projectId, at_ms: Date.now() });
              clearInterval(intervalsRef.current.get(projectId)!);
              intervalsRef.current.delete(projectId);
              startedAtRef.current.delete(projectId);
              clearProjectLiveState(projectId);
              return;
            }
            poll(projectId);
          }, POLL_INTERVAL_MS);
          intervalsRef.current.set(projectId, id);
        } catch {
          // Ignore
        }
      })();
    }

    return () => {
      logger.debug('progress_restore_poll_effect_cleanup', {
        run_id: pollEffectRunId,
        project_ids: [...projectIds],
      });
      intervalsRef.current.forEach((id) => clearInterval(id));
      intervalsRef.current.clear();
      startedAtRef.current.clear();
    };
  }, [projectIds.join(','), updateState, loadProjects, reloadProjectMessages, clearProjectLiveState, isInPostStreamQuietWindow]);

  // Stop polling + forget the timer without touching live state. Call this
  // on the local stream's finalize path: after `done`, the backend progress
  // row still reports `is_analyzing: true` for up to ~20s while its write
  // debounce drains, and the next poll tick would otherwise react to the
  // eventual `is_analyzing: false` by calling `reloadProjectMessages` —
  // which re-renders the entire chat list and looks like a "content flashes
  // / refreshes" after the turn settled. `cancelRestore` is the harder
  // variant used by the user-facing Stop button and still clears live state.
  const stopPolling = useCallback((projectId: string) => {
    const now = Date.now();
    const hadInterval = intervalsRef.current.has(projectId);
    const id = intervalsRef.current.get(projectId);
    if (id) {
      clearInterval(id);
      intervalsRef.current.delete(projectId);
      startedAtRef.current.delete(projectId);
    }
    // Open the post-stream quiet window for this project. Both the
    // in-flight poll branch and the polling effect's bootstrap step will
    // skip work for the next POST_STREAM_QUIET_WINDOW_MS.
    progressRestoreStoppedAtMs.set(projectId, now);
    const suppressUntil = now + PROGRESS_RELOAD_SUPPRESS_MS;
    progressRestoreSuppressUntilMs.set(projectId, suppressUntil);
    logger.info('progress_restore_stop_polling', {
      project_id: projectId,
      at_ms: now,
      cleared_interval: hadInterval,
      quiet_window_ms: POST_STREAM_QUIET_WINDOW_MS,
      suppress_reload_and_stale_apply_until_ms: suppressUntil,
    });
  }, []);

  const cancelRestore = useCallback((projectId: string) => {
    logger.info('progress_restore_cancel_restore', { project_id: projectId, at_ms: Date.now() });
    stopPolling(projectId);
    // `stopPolling` seeds suppress for normal stream completion; user Stop must
    // not block a later legitimate progress → DB sync.
    progressRestoreSuppressUntilMs.delete(projectId);
    clearProjectLiveState(projectId);
  }, [stopPolling, clearProjectLiveState]);

  return { cancelRestore, stopPolling };
}
