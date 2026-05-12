import { describe, expect, it } from 'vitest';
import type { AnalysisTimelineEntry } from '@/types/analysis';
import {
  aggregateReasoningFromTimeline,
  aggregateReasoningSegmentsFromTimeline,
  buildExploreStreamEventsFromTimeline,
  buildTimelineActivityChunks,
  isHiddenFromUserTimeline,
  mergeReadFileChunks,
  normalizeTimelineSeqMonotonic,
  prepareTimelineEntriesForDisplay,
  timelineHasSubagentScope,
} from './timelineDisplay';

function reasoning(id: string, seq: number, content: string): AnalysisTimelineEntry {
  return {
    type: 'reasoning',
    id,
    seq,
    content,
    schemaVersion: 1,
    scope: 'main',
  } as AnalysisTimelineEntry;
}

function toolResult(id: string, seq: number): AnalysisTimelineEntry {
  return {
    type: 'tool_result',
    id,
    seq,
    toolName: 'web_search',
    toolOutput: {},
    schemaVersion: 1,
    scope: 'main',
  } as AnalysisTimelineEntry;
}

function webSearchCall(id: string, seq: number): AnalysisTimelineEntry {
  return {
    type: 'tool_call',
    id,
    seq,
    toolName: 'web_search',
    toolInput: { query: 'q' },
    schemaVersion: 1,
    scope: 'main',
  } as AnalysisTimelineEntry;
}

function taskCall(id: string, seq: number, subagent_type: string): AnalysisTimelineEntry {
  return {
    type: 'tool_call',
    id,
    seq,
    toolName: 'task',
    toolInput: { subagent_type, description: 'do it' },
    schemaVersion: 1,
    scope: 'main',
  } as AnalysisTimelineEntry;
}

function readFileCall(id: string, seq: number, filePath: string, offset: number = 0): AnalysisTimelineEntry {
  return {
    type: 'tool_call',
    id,
    seq,
    toolName: 'read_file',
    toolInput: { file_path: filePath, offset, limit: 2000 },
    schemaVersion: 1,
    scope: 'main',
  } as AnalysisTimelineEntry;
}

function readFileResult(id: string, seq: number, output: string): AnalysisTimelineEntry {
  return {
    type: 'tool_result',
    id,
    seq,
    toolName: 'read_file',
    toolOutput: output,
    schemaVersion: 1,
    scope: 'main',
  } as AnalysisTimelineEntry;
}

function subToolCall(id: string, seq: number, name: string): AnalysisTimelineEntry {
  return {
    type: 'tool_call',
    id,
    seq,
    toolName: name,
    toolInput: {},
    schemaVersion: 1,
    scope: 'subagent',
  } as AnalysisTimelineEntry;
}

describe('isHiddenFromUserTimeline', () => {
  it('hides adapter heartbeat steps', () => {
    expect(
      isHiddenFromUserTimeline({
        type: 'step',
        id: 'analysis-start',
        seq: 1,
        schemaVersion: 1,
      } as AnalysisTimelineEntry),
    ).toBe(true);
    expect(
      isHiddenFromUserTimeline({
        type: 'step',
        id: 'stream-init',
        seq: 0,
        schemaVersion: 1,
      } as AnalysisTimelineEntry),
    ).toBe(true);
    expect(
      isHiddenFromUserTimeline({
        type: 'reasoning',
        id: 'r1',
        seq: 2,
        content: 'x',
        schemaVersion: 1,
      } as AnalysisTimelineEntry),
    ).toBe(false);
  });

  it('hides steps with visibility debug (e.g. deep-research debug-node / debug-input)', () => {
    expect(
      isHiddenFromUserTimeline({
        type: 'step',
        id: 'debug-node-write_research_brief',
        seq: 3,
        visibility: 'debug',
        schemaVersion: 1,
      } as AnalysisTimelineEntry),
    ).toBe(true);
  });

  it('hides state-presentation tool_call/tool_result (e.g. ResearchQuestion structured output)', () => {
    expect(
      isHiddenFromUserTimeline({
        type: 'tool_call',
        id: 'rq-1',
        seq: 1,
        toolName: 'ResearchQuestion',
        toolInput: { research_brief: 'x' },
        toolPresentation: 'state',
        schemaVersion: 1,
        scope: 'subagent',
      } as AnalysisTimelineEntry),
    ).toBe(true);
    expect(
      isHiddenFromUserTimeline({
        type: 'tool_result',
        id: 'rq-1',
        seq: 2,
        toolName: 'ResearchQuestion',
        toolPresentation: 'state',
        schemaVersion: 1,
        scope: 'subagent',
      } as AnalysisTimelineEntry),
    ).toBe(true);
  });
});

describe('prepareTimelineEntriesForDisplay (seq resume / HITL)', () => {
  it('remaps restarted seq so new rows sort after pre-interrupt timeline (append order)', () => {
    const plan = {
      id: 'tp',
      tasks: [
        {
          id: '0',
          title: 'T',
          description: '',
          taskType: 'security' as const,
          priority: 1,
          status: 'pending' as const,
          durationMs: 0,
          steps: [],
        },
      ],
      isSingleTask: true,
      totalDurationMs: 0,
      status: 'pending' as const,
      createdAt: '',
    };
    const entries: AnalysisTimelineEntry[] = [
      { ...reasoning('r-pre', 50, 'first think leg'), turn: 1 },
      {
        type: 'task_plan',
        id: 'tp',
        seq: 60,
        plan,
        schemaVersion: 1,
      } as AnalysisTimelineEntry,
      { ...reasoning('r-post', 5, 'resume leg replays low seq'), turn: 2 },
    ];
    const prepared = prepareTimelineEntriesForDisplay(entries);
    const kinds = buildTimelineActivityChunks(prepared).map((c) => c.kind);
    expect(prepared.map((e) => e.seq)).toEqual([50, 60, 61]);
    expect(kinds[0]).toBe('reasoning_main');
    expect(kinds).toContain('task_board');
    const tbIdx = kinds.indexOf('task_board');
    const rmIdx = kinds.indexOf('reasoning_main', kinds.indexOf('reasoning_main') + 1);
    expect(tbIdx).toBeGreaterThan(-1);
    expect(rmIdx).toBeGreaterThan(tbIdx);
  });

  it('normalizeTimelineSeqMonotonic is idempotent on already-increasing seq', () => {
    const entries: AnalysisTimelineEntry[] = [
      { ...reasoning('a', 1, 'x') },
      { ...reasoning('b', 2, 'y') },
    ];
    const once = normalizeTimelineSeqMonotonic(entries);
    const twice = normalizeTimelineSeqMonotonic(once);
    expect(once.map((e) => e.seq)).toEqual([1, 2]);
    expect(twice.map((e) => e.seq)).toEqual([1, 2]);
  });
});

describe('buildTimelineActivityChunks', () => {
  it('interleaves explore, delegation at task, then subagent, then more explore by seq', () => {
    const entries: AnalysisTimelineEntry[] = [
      webSearchCall('ws1', 1),
      { ...toolResult('ws1', 2), id: 'ws1' },
      taskCall('tc-task', 3, 'web-security'),
      subToolCall('sub1', 4, 'read_file'),
      webSearchCall('ws2', 5),
    ];
    const chunks = buildTimelineActivityChunks(entries, 'fallback');
    expect(chunks.map((c) => c.kind)).toEqual(['explore', 'delegation', 'subagent', 'explore']);
    expect(chunks[0]!.kind === 'explore' && chunks[0]!.events).toHaveLength(2);
    expect(chunks[1]!.kind === 'delegation' && chunks[1]!.subagent).toBe('web-security');
    expect(chunks[2]!.kind === 'subagent' && chunks[2]!.items).toHaveLength(1);
    expect(chunks[3]!.kind === 'explore' && chunks[3]!.events).toHaveLength(1);
    const flatExplore = buildExploreStreamEventsFromTimeline(entries);
    expect(flatExplore).toHaveLength(3);
    expect(flatExplore.map((e) => e.id)).toEqual(['ws1', 'ws1', 'ws2']);
  });

  it('drops state tools from subagent chunks (ResearchQuestion without SSE toolPresentation uses name inference)', () => {
    const entries: AnalysisTimelineEntry[] = [
      {
        type: 'tool_call',
        id: 'rq',
        seq: 1,
        toolName: 'ResearchQuestion',
        toolInput: { research_brief: 'brief' },
        schemaVersion: 1,
        scope: 'subagent',
      } as AnalysisTimelineEntry,
      subToolCall('rf', 2, 'read_file'),
    ];
    const chunks = buildTimelineActivityChunks(entries);
    expect(chunks.map((c) => c.kind)).toEqual(['subagent']);
    expect(chunks[0]!.kind === 'subagent' && chunks[0]!.items).toHaveLength(1);
    expect(chunks[0]!.kind === 'subagent' && chunks[0]!.items[0]!.toolName).toBe('read_file');
  });

  it('emits delegation at task even when no subagent rows exist yet (streaming gap)', () => {
    const entries: AnalysisTimelineEntry[] = [taskCall('t1', 1, 'web-security')];
    const chunks = buildTimelineActivityChunks(entries);
    expect(chunks).toEqual([
      expect.objectContaining({ kind: 'delegation', subagent: 'web-security' }),
    ]);
  });

  it('inserts a single task_board chunk when task_plan appears and keeps chronological order', () => {
    const plan = {
      id: 'tp',
      tasks: [
        {
          id: '0',
          title: 'Only',
          description: '',
          taskType: 'security' as const,
          priority: 1,
          status: 'pending' as const,
          durationMs: 0,
          steps: [],
        },
      ],
      isSingleTask: true,
      totalDurationMs: 0,
      status: 'pending' as const,
      createdAt: '',
    };
    const entries: AnalysisTimelineEntry[] = [
      webSearchCall('ws1', 1),
      { ...toolResult('ws1', 2), id: 'ws1' },
      {
        type: 'task_plan',
        id: 'tp',
        seq: 3,
        plan,
        schemaVersion: 1,
      } as AnalysisTimelineEntry,
      readFileCall('r1', 4, 'z.py'),
      readFileResult('r1', 5, 'body'),
    ];
    const chunks = buildTimelineActivityChunks(entries);
    expect(chunks.map((c) => c.kind)).toEqual(['explore', 'task_board', 'explore']);
  });

  it('inserts task_board when main-scope write_todos tool_call appears (no task_plan row)', () => {
    const entries: AnalysisTimelineEntry[] = [
      webSearchCall('ws1', 1),
      { ...toolResult('ws1', 2), id: 'ws1' },
      {
        type: 'tool_call',
        id: 'wt-1',
        seq: 3,
        toolName: 'write_todos',
        toolInput: { todos: [{ content: 'Todo A', status: 'pending' }] },
        toolPresentation: 'task',
        schemaVersion: 1,
        scope: 'main',
      } as AnalysisTimelineEntry,
      readFileCall('r1', 4, 'z.py'),
      readFileResult('r1', 5, 'body'),
    ];
    const chunks = buildTimelineActivityChunks(entries);
    expect(chunks.map((c) => c.kind)).toEqual(['explore', 'task_board', 'explore']);
  });

  it('skips consecutive duplicate delegation lines (same subagent and task text)', () => {
    const entries: AnalysisTimelineEntry[] = [
      taskCall('t1', 1, 'web-security'),
      taskCall('t2', 2, 'web-security'),
    ];
    const chunks = buildTimelineActivityChunks(entries);
    expect(chunks.filter((c) => c.kind === 'delegation')).toHaveLength(1);
  });

  it('delegation task strips layered deep-research wire format for display', () => {
    const entries: AnalysisTimelineEntry[] = [
      {
        type: 'tool_call',
        id: 'tc-dr',
        seq: 1,
        toolName: 'task',
        toolInput: {
          subagent_type: 'deep-research',
          description:
            'ORIGINAL_QUERY: user question here\n---CONTEXT---\ninternal context must not show',
        },
        toolPresentation: 'task',
        schemaVersion: 1,
        scope: 'main',
      } as AnalysisTimelineEntry,
    ];
    const chunks = buildTimelineActivityChunks(entries);
    const del = chunks.find((c) => c.kind === 'delegation');
    expect(del && del.kind === 'delegation' && del.task).toBe('user question here');
  });
});

describe('aggregateReasoningSegmentsFromTimeline', () => {
  it('segments by backend turn when reasoning has turn field', () => {
    const entries: AnalysisTimelineEntry[] = [
      { ...reasoning('r1', 1, 'A'), turn: 1 },
      { ...reasoning('r2', 2, 'B'), turn: 1 },
      { ...reasoning('r3', 3, 'C'), turn: 2 },
    ];
    expect(aggregateReasoningSegmentsFromTimeline(entries)).toEqual(['AB', 'C']);
    expect(aggregateReasoningFromTimeline(entries)).toBe('ABC');
  });

  it('tool_result does not split segments; only distinct turn on reasoning rows does', () => {
    const entries: AnalysisTimelineEntry[] = [
      { ...reasoning('r1', 1, 'A'), turn: 1 },
      { ...reasoning('r2', 2, 'B'), turn: 1 },
      toolResult('tr1', 3),
      { ...reasoning('r3', 4, 'C'), turn: 2 },
    ];
    expect(aggregateReasoningSegmentsFromTimeline(entries)).toEqual(['AB', 'C']);
    expect(aggregateReasoningFromTimeline(entries)).toBe('ABC');
  });

  it('missing turn on reasoning uses bucket 0 (single segment for streaming chunks)', () => {
    const entries: AnalysisTimelineEntry[] = [reasoning('r1', 1, 'x'), reasoning('r2', 2, 'y')];
    expect(aggregateReasoningSegmentsFromTimeline(entries)).toEqual(['xy']);
  });

  it('default scope main excludes subagent reasoning', () => {
    const entries: AnalysisTimelineEntry[] = [
      { ...reasoning('r1', 1, 'main'), scope: 'main' },
      { ...reasoning('r2', 2, 'sub'), scope: 'subagent' },
    ];
    expect(aggregateReasoningSegmentsFromTimeline(entries)).toEqual(['main']);
    expect(aggregateReasoningSegmentsFromTimeline(entries, { scope: 'subagent' })).toEqual(['sub']);
  });

  it('skips internal entries; same implicit turn merges into one segment', () => {
    const entries: AnalysisTimelineEntry[] = [
      reasoning('r1', 1, 'a'),
      { type: 'reasoning', id: 'i', seq: 2, content: 'bad', internal: true } as AnalysisTimelineEntry,
      toolResult('tr', 3),
      reasoning('r2', 4, 'b'),
    ];
    expect(aggregateReasoningSegmentsFromTimeline(entries)).toEqual(['ab']);
  });

  it('skips type debug from reasoning aggregation (dev-only rows)', () => {
    const entries: AnalysisTimelineEntry[] = [
      reasoning('r1', 1, 'a'),
      { type: 'debug', id: 'd', seq: 2, content: 'secret' } as AnalysisTimelineEntry,
      reasoning('r2', 3, 'b'),
    ];
    expect(aggregateReasoningSegmentsFromTimeline(entries)).toEqual(['ab']);
    expect(isHiddenFromUserTimeline(entries[1]!)).toBe(true);
  });
});

describe('mergeReadFileChunks', () => {
  it('merges consecutive read_file calls on the same file into one call+result', () => {
    const { StreamEvent } = {} as never; void StreamEvent;
    const events = [
      { type: 'tool_call' as const, id: 'r1', timestamp: 0, toolName: 'read_file', toolInput: { file_path: 'foo.py', offset: 0 } },
      { type: 'tool_result' as const, id: 'r1', timestamp: 1, toolName: 'read_file', toolOutput: 'lines 1-2000' },
      { type: 'tool_call' as const, id: 'r2', timestamp: 2, toolName: 'read_file', toolInput: { file_path: 'foo.py', offset: 2000 } },
      { type: 'tool_result' as const, id: 'r2', timestamp: 3, toolName: 'read_file', toolOutput: 'lines 2001-4000' },
      { type: 'tool_call' as const, id: 'r3', timestamp: 4, toolName: 'read_file', toolInput: { file_path: 'foo.py', offset: 4000 } },
      { type: 'tool_result' as const, id: 'r3', timestamp: 5, toolName: 'read_file', toolOutput: 'lines 4001-6000' },
    ];
    const merged = mergeReadFileChunks(events);
    // 3 pairs → 1 pair (2 events)
    expect(merged).toHaveLength(2);
    expect(merged[0]!.type).toBe('tool_call');
    expect(merged[0]!.id).toBe('r1');
    expect(merged[1]!.type).toBe('tool_result');
    const out = String(merged[1]!.toolOutput ?? '');
    expect(out).toContain('lines 1-2000');
    expect(out).toContain('lines 2001-4000');
    expect(out).toContain('lines 4001-6000');
  });

  it('does not merge reads of different files', () => {
    const events = [
      { type: 'tool_call' as const, id: 'r1', timestamp: 0, toolName: 'read_file', toolInput: { file_path: 'foo.py', offset: 0 } },
      { type: 'tool_result' as const, id: 'r1', timestamp: 1, toolName: 'read_file', toolOutput: 'foo content' },
      { type: 'tool_call' as const, id: 'r2', timestamp: 2, toolName: 'read_file', toolInput: { file_path: 'bar.py', offset: 0 } },
      { type: 'tool_result' as const, id: 'r2', timestamp: 3, toolName: 'read_file', toolOutput: 'bar content' },
    ];
    const merged = mergeReadFileChunks(events);
    expect(merged).toHaveLength(4);
  });

  it('does not merge non-consecutive reads of the same file (other tool interleaved)', () => {
    const events = [
      { type: 'tool_call' as const, id: 'r1', timestamp: 0, toolName: 'read_file', toolInput: { file_path: 'foo.py', offset: 0 } },
      { type: 'tool_result' as const, id: 'r1', timestamp: 1, toolName: 'read_file', toolOutput: 'part1' },
      { type: 'tool_call' as const, id: 'ws1', timestamp: 2, toolName: 'web_search', toolInput: { query: 'x' } },
      { type: 'tool_result' as const, id: 'ws1', timestamp: 3, toolName: 'web_search', toolOutput: 'results' },
      { type: 'tool_call' as const, id: 'r2', timestamp: 4, toolName: 'read_file', toolInput: { file_path: 'foo.py', offset: 2000 } },
      { type: 'tool_result' as const, id: 'r2', timestamp: 5, toolName: 'read_file', toolOutput: 'part2' },
    ];
    const merged = mergeReadFileChunks(events);
    // web_search breaks the sequence → 6 events remain
    expect(merged).toHaveLength(6);
    // Both foo.py tool_calls kept
    expect(merged.filter((e) => e.type === 'tool_call' && e.toolName === 'read_file')).toHaveLength(2);
  });

  it('passes through non-read_file events unchanged', () => {
    const events = [
      { type: 'tool_call' as const, id: 'ws1', timestamp: 0, toolName: 'web_search', toolInput: { query: 'x' } },
      { type: 'tool_result' as const, id: 'ws1', timestamp: 1, toolName: 'web_search', toolOutput: 'ok' },
    ];
    const merged = mergeReadFileChunks(events);
    expect(merged).toEqual(events);
  });

  it('does not merge read_file pairs when write_file is interleaved in the same stream', () => {
    const events = [
      { type: 'tool_call' as const, id: 'r1', timestamp: 0, toolName: 'read_file', toolInput: { file_path: 'f.py' } },
      { type: 'tool_result' as const, id: 'r1', timestamp: 1, toolName: 'read_file', toolOutput: 'a' },
      { type: 'tool_call' as const, id: 'w1', timestamp: 2, toolName: 'write_file', toolInput: { path: 'f.py' } },
      { type: 'tool_result' as const, id: 'w1', timestamp: 3, toolName: 'write_file', toolOutput: 'ok' },
      { type: 'tool_call' as const, id: 'r2', timestamp: 4, toolName: 'read_file', toolInput: { file_path: 'f.py' } },
      { type: 'tool_result' as const, id: 'r2', timestamp: 5, toolName: 'read_file', toolOutput: 'b' },
    ];
    const merged = mergeReadFileChunks(events);
    expect(merged.filter((e) => e.type === 'tool_call' && e.toolName === 'read_file')).toHaveLength(2);
  });
});

describe('buildTimelineActivityChunks — read_file chunked read merging', () => {
  it('collapses multi-part read of the same file to one explore event pair', () => {
    const entries: AnalysisTimelineEntry[] = [
      readFileCall('r1', 1, 'big.py', 0),
      readFileResult('r1', 2, 'part-A'),
      readFileCall('r2', 3, 'big.py', 2000),
      readFileResult('r2', 4, 'part-B'),
    ];
    const chunks = buildTimelineActivityChunks(entries);
    expect(chunks).toHaveLength(1);
    expect(chunks[0]!.kind).toBe('explore');
    const events = chunks[0]!.kind === 'explore' ? chunks[0]!.events : [];
    expect(events).toHaveLength(2);
    expect(events[0]!.id).toBe('r1');
    const out = String(events[1]!.toolOutput ?? '');
    expect(out).toContain('part-A');
    expect(out).toContain('part-B');
  });

  it('keeps separate chunks for different files read consecutively', () => {
    const entries: AnalysisTimelineEntry[] = [
      readFileCall('r1', 1, 'a.py', 0),
      readFileResult('r1', 2, 'aaa'),
      readFileCall('r2', 3, 'b.py', 0),
      readFileResult('r2', 4, 'bbb'),
    ];
    const chunks = buildTimelineActivityChunks(entries);
    expect(chunks).toHaveLength(1);
    const events = chunks[0]!.kind === 'explore' ? chunks[0]!.events : [];
    // Two distinct files → 2 call+result pairs = 4 events
    expect(events).toHaveLength(4);
  });

  it('flatExplore count matches merged event count', () => {
    const entries: AnalysisTimelineEntry[] = [
      readFileCall('r1', 1, 'big.py', 0),
      readFileResult('r1', 2, 'part-A'),
      readFileCall('r2', 3, 'big.py', 2000),
      readFileResult('r2', 4, 'part-B'),
      readFileCall('r3', 5, 'big.py', 4000),
      readFileResult('r3', 6, 'part-C'),
    ];
    const flat = buildExploreStreamEventsFromTimeline(entries);
    // 3 parts merged → 1 call + 1 result = 2
    expect(flat).toHaveLength(2);
  });
});

describe('timelineHasSubagentScope', () => {
  it('returns false for empty or main-only timelines', () => {
    expect(timelineHasSubagentScope(undefined)).toBe(false);
    expect(timelineHasSubagentScope([])).toBe(false);
    expect(timelineHasSubagentScope([reasoning('r', 1, 'x')])).toBe(false);
  });

  it('returns true when scope is subagent', () => {
    expect(
      timelineHasSubagentScope([
        {
          type: 'llm_invoke_start',
          id: 's',
          seq: 1,
          scope: 'subagent',
          schemaVersion: 1,
        } as AnalysisTimelineEntry,
      ]),
    ).toBe(true);
  });

  it('returns true when subagentStream is set on a visible row', () => {
    expect(
      timelineHasSubagentScope([
        {
          type: 'llm_delta',
          id: 'd',
          seq: 1,
          channel: 'text',
          content: 'x',
          subagentStream: true,
          schemaVersion: 1,
        } as AnalysisTimelineEntry,
      ]),
    ).toBe(true);
  });

  it('ignores hidden rows', () => {
    expect(
      timelineHasSubagentScope([
        {
          type: 'debug',
          id: 'd',
          seq: 1,
          scope: 'subagent',
        } as AnalysisTimelineEntry,
      ]),
    ).toBe(false);
  });
});
