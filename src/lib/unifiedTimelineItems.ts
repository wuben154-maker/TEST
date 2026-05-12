/**
 * Single ordered list for Command Center timeline body (design D1/D2/D3).
 * Merges understanding intro, main-scope errors, activity chunks, and streaming reasoning
 * with stable ordering: primary `sortKey` from `seq` / `firstSeq`, tie-break by emission order.
 *
 * `conclusion` is excluded (workspace-first); `task_summary` stays as activity chunks.
 * Streaming reasoning (tokens not yet on timeline) sorts after all committed rows (D3).
 */
import type { AnalysisTimelineEntry } from '@/types/analysis';
import {
  buildTimelineActivityChunks,
  isHiddenFromUserTimeline,
  prepareTimelineEntriesForDisplay,
  type TimelineActivityChunk,
} from '@/lib/timelineDisplay';

function seqOf(e: AnalysisTimelineEntry): number {
  const n = Number(e.seq);
  return Number.isFinite(n) ? n : 0;
}

/** True if main-scope reasoning is already represented on the timeline (avoid duplicating persisted `reasoning`). */
export function timelineHasMainScopeReasoningStream(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): boolean {
  if (!entries?.length) return false;
  return entries.some(
    (e) =>
      !isHiddenFromUserTimeline(e) &&
      (e.scope ?? 'main') === 'main' &&
      (e.type === 'reasoning' ||
        (e.type === 'llm_delta' && String((e as { channel?: string }).channel) === 'reasoning')),
  );
}

function chunkSortKey(c: TimelineActivityChunk): number {
  switch (c.kind) {
    case 'task_summary':
      return c.seq;
    case 'parameter_request':
    case 'decision_request':
      return c.seq;
    default:
      return c.firstSeq;
  }
}

/** Offset after max timeline seq so in-flight reasoning stays below the next SSE row. */
export const STREAM_REASONING_SORT_OFFSET = 1;

export type UnifiedTimelineItem =
  | { kind: 'understanding_intro'; sortKey: number; order: number; text: string }
  | { kind: 'main_error'; sortKey: number; order: number; entry: AnalysisTimelineEntry }
  | { kind: 'activity'; sortKey: number; order: number; chunk: TimelineActivityChunk }
  | { kind: 'stream_reasoning'; sortKey: number; order: number; text: string };

export type BuildUnifiedTimelineItemsOptions = {
  timeline: readonly AnalysisTimelineEntry[] | undefined;
  subagentFallbackName: string;
  /** Preformatted intro (summary + reasoningSummary), same as linear trace. */
  understandingIntro?: string;
  streamReasoning?: string;
  /** Only pin stream tail when analysis is in progress (avoids stale tokens after turn end). */
  isStreaming?: boolean;
};

/**
 * Build globally sorted timeline body items for one turn.
 */
export function buildUnifiedTimelineItems(opts: BuildUnifiedTimelineItemsOptions): UnifiedTimelineItem[] {
  const { timeline, subagentFallbackName, understandingIntro, streamReasoning, isStreaming } = opts;
  const entries = timeline ?? [];
  const sorted = prepareTimelineEntriesForDisplay(entries);
  const chunks = buildTimelineActivityChunks(entries, subagentFallbackName);

  let order = 0;
  const items: UnifiedTimelineItem[] = [];

  const maxFromChunks = chunks.reduce((m, c) => Math.max(m, chunkSortKey(c)), 0);
  const maxFromEntries = sorted.reduce(
    (m, e) => (isHiddenFromUserTimeline(e) ? m : Math.max(m, seqOf(e))),
    0,
  );
  const maxSeq = Math.max(maxFromChunks, maxFromEntries);

  const minChunkSeq = chunks.length ? Math.min(...chunks.map(chunkSortKey)) : Number.POSITIVE_INFINITY;
  const introSortKey = Number.isFinite(minChunkSeq) ? minChunkSeq - 0.5 : -0.5;

  const intro = understandingIntro?.trim();
  if (intro) {
    items.push({ kind: 'understanding_intro', sortKey: introSortKey, order: order++, text: intro });
  }

  for (const ev of sorted) {
    if (isHiddenFromUserTimeline(ev)) continue;
    if (ev.type === 'error' && ev.scope !== 'subagent') {
      items.push({ kind: 'main_error', sortKey: seqOf(ev), order: order++, entry: ev });
    }
  }

  for (const chunk of chunks) {
    items.push({ kind: 'activity', sortKey: chunkSortKey(chunk), order: order++, chunk });
  }

  const sr = streamReasoning?.trim();
  const shouldAppendStreamReasoning =
    !!sr &&
    (isStreaming || !timelineHasMainScopeReasoningStream(sorted));
  if (shouldAppendStreamReasoning) {
    items.push({
      kind: 'stream_reasoning',
      sortKey: maxSeq + STREAM_REASONING_SORT_OFFSET,
      order: order++,
      text: sr!,
    });
  }

  items.sort((a, b) => {
    if (a.sortKey !== b.sortKey) return a.sortKey - b.sortKey;
    return a.order - b.order;
  });

  return items;
}
