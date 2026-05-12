/**
 * Build the `displayStats` payload consumed by <TaskStatsBar />.
 *
 * Responsibility:
 * - Internal layout-routing signals: durationMs, toolCallCount, sandboxRunCount
 *   (`isComplexResult` still relies on them — do NOT drop).
 * - Task-stats profile (security / research) from the backend-owned
 *   `conclusion.meta` (`statsMeta`). Stats bar renders straight from these.
 *
 * Extracted from LiveWorkspace.tsx so the merge is directly testable without
 * rendering the full workspace shell.
 */
import type { AnalysisResultStats, TaskStatsMeta } from '@/types/project';

export interface LiveStatsSignals {
  statsMeta?: TaskStatsMeta;
  toolCallCount?: number;
  sandboxRunCount?: number;
  resultStartTime?: number;
}

/** Result of a finished turn (reloaded or active-selected); already carries stats. */
export interface ActiveStatsSignals {
  stats?: AnalysisResultStats;
}

/** Compute stats bar inputs for the **streaming** or **pendingFinalize** branch. */
export function buildLiveDisplayStats(
  live: LiveStatsSignals,
  now: number = Date.now(),
): AnalysisResultStats {
  const out: AnalysisResultStats = {
    toolCallCount: live.toolCallCount,
    sandboxRunCount: live.sandboxRunCount,
    durationMs:
      live.resultStartTime !== undefined ? now - live.resultStartTime : undefined,
  };
  // Prefer the backend-owned TaskStatsMeta. Copy keys individually so a
  // partial payload never accidentally overwrites unrelated fields.
  const meta = live.statsMeta;
  if (meta?.taskKind) {
    out.taskKind = meta.taskKind;
    if (meta.security) out.security = meta.security;
    if (meta.research) out.research = meta.research;
  }
  return out;
}

/** Compute stats bar inputs for the **done** branch (persisted analysis result). */
export function buildActiveDisplayStats(active: ActiveStatsSignals): AnalysisResultStats {
  return active.stats ?? {};
}
