import type { AnalysisTimelineEntry, ThinkingEvent } from '@/types/analysis';

/**
 * Append one user-visible SSE event to the analysis timeline (schemaVersion 1).
 * Preserves server `seq` when present; otherwise uses bumpLocalSeq() for offline ordering.
 *
 * Steps with a non-empty `phaseId`: running → success updates the **first** row with that id
 * (same UI slot). Keep in sync with `mergePhaseIdMilestoneStepsAtMinSeq` in `buildReActTimeline.ts`.
 */
export function appendToAnalysisTimeline(
  timeline: readonly AnalysisTimelineEntry[],
  ev: ThinkingEvent,
  bumpLocalSeq: () => number,
): AnalysisTimelineEntry[] {
  const seq = typeof ev.seq === 'number' ? ev.seq : bumpLocalSeq();
  let clone: Record<string, unknown>;
  try {
    clone = JSON.parse(JSON.stringify(ev)) as Record<string, unknown>;
  } catch {
    clone = { type: ev.type, id: ev.id };
  }
  clone.seq = seq;
  clone.schemaVersion = typeof ev.schemaVersion === 'number' ? ev.schemaVersion : 1;
  clone.scope = ev.scope ?? (ev.subagentStream ? 'subagent' : 'main');

  if (clone.type === 'step') {
    const pid = clone.phaseId != null ? String(clone.phaseId).trim() : '';
    if (pid !== '') {
      const next = timeline.slice() as AnalysisTimelineEntry[];
      for (let i = 0; i < next.length; i++) {
        const row = next[i] as Record<string, unknown>;
        if (
          row.type === 'step' &&
          row.phaseId != null &&
          String(row.phaseId).trim() === pid
        ) {
          next[i] = { ...clone, seq: row.seq } as AnalysisTimelineEntry;
          return next;
        }
      }
    }

    // Subagent delegation chrome: same stable id as AIMessage tool_call id.
    // On HITL resume the graph may replay ToolMessages; timeline is not cleared, so
    // skip duplicate running/success rows for an id that already completed.
    const sid = String(clone.id ?? '');
    if (sid.startsWith('task-running-')) {
      const idx = timeline.findIndex(
        (row) => row.type === 'step' && String(row.id ?? '') === sid,
      );
      if (idx >= 0) {
        const prev = timeline[idx] as AnalysisTimelineEntry;
        const prevStatus = String(prev.status ?? '');
        const newStatus = String(clone.status ?? '');
        if (prevStatus === 'success') {
          return timeline.slice() as AnalysisTimelineEntry[];
        }
        if (prevStatus === 'running' && newStatus === 'success') {
          const next = timeline.slice() as AnalysisTimelineEntry[];
          const endTs =
            typeof clone.timestamp === 'number' ? clone.timestamp : prev.timestamp;
          next[idx] = {
            ...prev,
            ...clone,
            seq: prev.seq,
            timestamp: endTs,
          } as AnalysisTimelineEntry;
          return next;
        }
        if (prevStatus === 'running' && newStatus === 'running') {
          return timeline.slice() as AnalysisTimelineEntry[];
        }
      }
    }
  }

  return [...timeline, clone as AnalysisTimelineEntry];
}
