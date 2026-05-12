import { describe, expect, it } from 'vitest';
import type { AnalysisTimelineEntry } from '@/types/analysis';
import {
  STREAM_REASONING_SORT_OFFSET,
  buildUnifiedTimelineItems,
} from './unifiedTimelineItems';

function reasoning(seq: number, content: string): AnalysisTimelineEntry {
  return {
    type: 'reasoning',
    id: `r-${seq}`,
    seq,
    content,
    schemaVersion: 1,
    scope: 'main',
  } as AnalysisTimelineEntry;
}

describe('buildUnifiedTimelineItems', () => {
  it('places understanding intro before first activity chunk by sortKey', () => {
    const timeline: AnalysisTimelineEntry[] = [reasoning(2, 'think')];
    const items = buildUnifiedTimelineItems({
      timeline,
      subagentFallbackName: 'sub',
      understandingIntro: 'User goal summary',
      isStreaming: false,
    });
    expect(items[0]?.kind).toBe('understanding_intro');
    expect(items[0]?.sortKey).toBeLessThan(items.find((i) => i.kind === 'activity')?.sortKey ?? 0);
  });

  it('interleaves main_error by seq between reasoning activity chunks', () => {
    const timeline: AnalysisTimelineEntry[] = [
      { ...reasoning(2, 'before'), turn: 1 },
      {
        type: 'error',
        id: 'e1',
        seq: 3,
        detail: 'failed',
        schemaVersion: 1,
        scope: 'main',
      } as AnalysisTimelineEntry,
      { ...reasoning(4, 'after'), turn: 2 },
    ];
    const items = buildUnifiedTimelineItems({ timeline, subagentFallbackName: 'sub' });
    const kinds = items.map((i) => i.kind);
    expect(kinds).toEqual(['activity', 'main_error', 'activity']);
    expect(items[1]?.kind === 'main_error' && items[1].sortKey).toBe(3);
  });

  it('appends streaming reasoning after max committed seq (D3)', () => {
    const timeline: AnalysisTimelineEntry[] = [reasoning(10, 'done on timeline')];
    const items = buildUnifiedTimelineItems({
      timeline,
      subagentFallbackName: 'sub',
      streamReasoning: 'still typing…',
      isStreaming: true,
    });
    const stream = items.filter((i) => i.kind === 'stream_reasoning');
    expect(stream).toHaveLength(1);
    expect(stream[0]!.sortKey).toBe(10 + STREAM_REASONING_SORT_OFFSET);
    const lastNonStream = items.filter((i) => i.kind !== 'stream_reasoning').pop();
    expect(lastNonStream!.sortKey).toBeLessThan(stream[0]!.sortKey);
  });

  it('omits stream_reasoning when not streaming if main reasoning already on timeline', () => {
    const items = buildUnifiedTimelineItems({
      timeline: [reasoning(1, 'x')],
      subagentFallbackName: 'sub',
      streamReasoning: 'orphan',
      isStreaming: false,
    });
    expect(items.some((i) => i.kind === 'stream_reasoning')).toBe(false);
  });

  it('appends persisted stream_reasoning when not streaming and timeline has no main reasoning rows', () => {
    const items = buildUnifiedTimelineItems({
      timeline: [],
      subagentFallbackName: 'sub',
      streamReasoning: 'only in DB reasoning column',
      isStreaming: false,
    });
    expect(items.some((i) => i.kind === 'stream_reasoning')).toBe(true);
  });
});
