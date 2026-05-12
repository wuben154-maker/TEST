/**
 * Heuristic for picking a "primary" active stream among concurrent runs (abort owners + analyzing ids).
 *
 * The main workspace chat binds live streaming UI to the **selected** project only
 * (`useStreamingAnalysisMulti` uses `currentProjectId` → `getLatestState`). Using this
 * resolver for that path caused another project's live turn to appear under the current
 * project's history when multiple analyses ran in parallel.
 *
 * Kept as a tested helper for future UI (e.g. sidebar activity) or tooling.
 */
export function resolveStreamDisplayProjectId(
  currentProjectId: string | null,
  abortControllerProjectIds: readonly string[],
  analyzingProjectIds: readonly string[],
): string | null {
  if (currentProjectId) {
    if (abortControllerProjectIds.includes(currentProjectId)) return currentProjectId;
    if (analyzingProjectIds.includes(currentProjectId)) return currentProjectId;
  }
  if (abortControllerProjectIds.length === 1) {
    return abortControllerProjectIds[0] ?? null;
  }
  if (abortControllerProjectIds.length > 1) {
    if (currentProjectId && abortControllerProjectIds.includes(currentProjectId)) {
      return currentProjectId;
    }
    return abortControllerProjectIds[0] ?? null;
  }
  if (analyzingProjectIds.length >= 1) {
    return analyzingProjectIds[0] ?? null;
  }
  return currentProjectId;
}
