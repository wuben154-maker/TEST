import type {
  AnalysisTimelineEntry,
  InputUnderstanding,
  StreamEvent,
  TaskPlan,
} from '@/types/analysis';
import { isAdapterChromeStepId } from '@/lib/toolCallDisplay';
import { subagentTaskPlanMapKey } from '@/lib/taskPlanScope';
import { effectiveToolPresentation } from '@/lib/toolPresentation';
import { formatDelegatedTaskForDisplay } from '@/lib/delegatedTaskDisplay';
import { scrubTaskPlanPathsForDisplay } from '@/lib/scrubVirtualPathsForDisplay';

function seqOf(e: AnalysisTimelineEntry): number {
  const n = Number(e.seq);
  return Number.isFinite(n) ? n : 0;
}

/** Stable ordering for SSE replay (schemaVersion 1). */
export function sortTimelineBySeq(entries: readonly AnalysisTimelineEntry[]): AnalysisTimelineEntry[] {
  return [...entries].sort((a, b) => seqOf(a) - seqOf(b));
}

/**
 * After HITL / interrupt resume, a new SSE leg may restart `seq` at a low value while the client
 * keeps the pre-interrupt timeline. Sorting by raw `seq` then interleaves new rows before old ones
 * and breaks chunk order (e.g. task list between two "thought" segments).
 *
 * Walks **storage / append order** (caller must pass timeline arrays as appended, not pre-sorted by seq)
 * and assigns strictly increasing seq so a global sort matches chronological order.
 */
export function normalizeTimelineSeqMonotonic(
  entries: readonly AnalysisTimelineEntry[],
): AnalysisTimelineEntry[] {
  let last = 0;
  return entries.map((e) => {
    const s = seqOf(e);
    const next = s <= last ? last + 1 : s;
    last = next;
    return { ...e, seq: next };
  });
}

/** Normalize seq (append order), then sort by seq for display pipelines. */
export function prepareTimelineEntriesForDisplay(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): AnalysisTimelineEntry[] {
  if (!entries?.length) return [];
  return sortTimelineBySeq(normalizeTimelineSeqMonotonic([...entries]));
}

/**
 * Rows that must not appear in end-user reasoning / explore UI.
 * - `internal` flag or `type: internal` — implementation detail.
 * - `type: debug` — developer diagnostics; keep in DevMode SSE log only.
 */
export function isHiddenFromUserTimeline(ev: AnalysisTimelineEntry): boolean {
  if (ev.internal === true || ev.type === 'internal' || ev.type === 'debug') return true;
  if (ev.type === 'step' && ev.visibility === 'debug') return true;
  if (ev.type === 'step' && isAdapterChromeStepId(ev.id != null ? String(ev.id) : undefined)) {
    return true;
  }
  if (ev.type === 'tool_call' || ev.type === 'tool_result') {
    if (effectiveToolPresentation(ev) === 'state') return true;
    if (typeof (ev as { toolName?: unknown }).toolName === 'string' &&
        (ev as { toolName: string }).toolName === 'request_user_input') return true;
  }
  return false;
}

/** True when the timeline includes user-visible subagent-scoped rows (merged task() stream). */
export function timelineHasSubagentScope(entries: readonly AnalysisTimelineEntry[] | undefined): boolean {
  if (!entries?.length) return false;
  return entries.some(
    (e) =>
      !isHiddenFromUserTimeline(e) &&
      ((e.scope ?? 'main') === 'subagent' || e.subagentStream === true),
  );
}

function filterTimelineByScope(
  entries: readonly AnalysisTimelineEntry[],
  scope: 'main' | 'subagent',
): AnalysisTimelineEntry[] {
  return entries.filter((e) => (e.scope ?? 'main') === scope);
}

/**
 * Group reasoning chunks by backend ``turn`` (ReAct cycle).
 * Missing ``turn`` on a reasoning row is treated as ``0`` (single bucket for that stream).
 */
function isTimelineReasoningStream(e: AnalysisTimelineEntry): boolean {
  if (e.type === 'reasoning') return true;
  return e.type === 'llm_delta' && String(e.channel) === 'reasoning';
}

function aggregateReasoningSegmentsByTurn(sorted: AnalysisTimelineEntry[]): string[] {
  const byTurn = new Map<number, string[]>();
  for (const e of sorted) {
    if (isHiddenFromUserTimeline(e)) continue;
    if (!isTimelineReasoningStream(e)) continue;
    const tn = typeof e.turn === 'number' ? e.turn : 0;
    const c = typeof e.content === 'string' ? e.content : '';
    if (!c.trim()) continue;
    if (!byTurn.has(tn)) byTurn.set(tn, []);
    byTurn.get(tn)!.push(c);
  }
  const keys = [...byTurn.keys()].sort((a, b) => a - b);
  return keys.map((k) => byTurn.get(k)!.join(''));
}

export type AggregateReasoningOptions = {
  /** Default ``main``: only main-agent reasoning (avoids turn collision with subagent). */
  scope?: 'main' | 'subagent';
};

/**
 * ReAct think segments: one string per distinct ``turn`` on reasoning events.
 * Default scope ``main`` matches main-agent persisted assistant ``reasoning`` text.
 */
export function aggregateReasoningSegmentsFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
  options?: AggregateReasoningOptions,
): string[] {
  if (!entries?.length) return [];
  const scope = options?.scope ?? 'main';
  const sorted = sortTimelineBySeq(filterTimelineByScope([...entries], scope));
  return aggregateReasoningSegmentsByTurn(sorted);
}

/** Full reasoning text for persistence / dedup (no delimiter between ReAct rounds). */
export function aggregateReasoningFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
  options?: AggregateReasoningOptions,
): string {
  return aggregateReasoningSegmentsFromTimeline(entries, options).join('');
}

const EXPLORE_TOOLS = new Set([
  'web_search',
  'web_searchs',
  'web_search_deep_research',
  'scrape_url',
  'read_file',
  'grep',
  'glob',
  'ls',
]);

/** Extract the file path from a read_file toolInput (backend uses file_path; path is a fallback). */
function getReadFilePath(input: Record<string, unknown>): string {
  return String(input['file_path'] ?? input['path'] ?? '');
}

/**
 * Merge consecutive read_file call+result pairs that target the same file into a single
 * call+result. All partial outputs are joined with '\n'. Non-consecutive reads of the same
 * file (i.e. another tool call interleaved) are kept separate.
 *
 * The merge is purely a display concern — the canonical timeline rows are unchanged.
 * Exported for unit testing.
 */
export function mergeReadFileChunks(events: StreamEvent[]): StreamEvent[] {
  // Pre-scan: build call_id -> file_path for all read_file tool_calls.
  const callFilePath = new Map<string, string>();
  for (const ev of events) {
    if (ev.type === 'tool_call' && ev.toolName === 'read_file') {
      callFilePath.set(ev.id, getReadFilePath((ev.toolInput ?? {}) as Record<string, unknown>));
    }
  }

  const output: StreamEvent[] = [];
  let currentFilePath: string | null = null;
  let currentResultIdx: number | null = null;

  for (const ev of events) {
    if (ev.type === 'tool_call' && ev.toolName === 'read_file') {
      const filePath = callFilePath.get(ev.id) ?? '';
      if (filePath && filePath === currentFilePath) {
        // Continuation of the same file — drop duplicate tool_call from display.
        continue;
      }
      // New file (or no current sequence): start tracking.
      currentFilePath = filePath;
      currentResultIdx = null;
      output.push({ ...ev });
    } else if (ev.type === 'tool_result' && ev.toolName === 'read_file') {
      const filePath = callFilePath.get(ev.id) ?? '';
      if (filePath && filePath === currentFilePath) {
        if (currentResultIdx === null) {
          // First result for this consecutive sequence — push and record index.
          currentResultIdx = output.length;
          output.push({ ...ev });
        } else {
          // Subsequent parts — append output to the existing result row.
          const existing = output[currentResultIdx]!;
          const prev = typeof existing.toolOutput === 'string' ? existing.toolOutput : '';
          const next = typeof ev.toolOutput === 'string' ? ev.toolOutput : '';
          output[currentResultIdx] = { ...existing, toolOutput: prev + '\n' + next };
        }
      } else {
        // Result for a different file (or file_path unknown) — reset state.
        currentFilePath = null;
        currentResultIdx = null;
        output.push({ ...ev });
      }
    } else {
      // Any other event (web_search, grep, write_file, etc.) breaks the consecutive sequence.
      currentFilePath = null;
      currentResultIdx = null;
      output.push({ ...ev });
    }
  }

  return output;
}

function isMainExploreToolCall(e: AnalysisTimelineEntry): boolean {
  if (e.type !== 'tool_call') return false;
  const pres = effectiveToolPresentation(e);
  if (pres === 'task' || pres === 'state') return false;
  if (pres === 'research_task') return true;
  const name = String(e.toolName ?? '');
  if (name === 'ConductResearch') return true;
  return !!name && EXPLORE_TOOLS.has(name);
}

function isMainExploreToolResult(e: AnalysisTimelineEntry): boolean {
  if (e.type !== 'tool_result') return false;
  const pres = effectiveToolPresentation(e);
  if (pres === 'task' || pres === 'state') return false;
  if (pres === 'research_task') return true;
  const name = String(e.toolName ?? '');
  if (name === 'ConductResearch') return true;
  return !!name && EXPLORE_TOOLS.has(name);
}

/** Ordered blocks for TimelineActivity: explore runs, delegation line, subagent rows — all by global seq. */
export type TimelineActivityChunk =
  | { kind: 'explore'; key: string; events: StreamEvent[]; firstSeq: number }
  | { kind: 'delegation'; key: string; subagent: string; task: string; firstSeq: number }
  | { kind: 'subagent'; key: string; items: AnalysisTimelineEntry[]; firstSeq: number }
  | { kind: 'task_board'; key: string; firstSeq: number }
  | {
      kind: 'task_board_sub';
      key: string;
      firstSeq: number;
      subagentKey: string;
    }
  | {
      kind: 'reasoning_main';
      key: string;
      firstSeq: number;
      turn: number;
      text: string;
      invokeDurationSec?: number;
      invokeStartMs?: number;
      invokeState?: 'running' | 'done';
    }
  | { kind: 'task_summary'; key: string; seq: number; summary: string }
  | { kind: 'parameter_request'; key: string; seq: number; entry: AnalysisTimelineEntry }
  | { kind: 'decision_request'; key: string; seq: number; entry: AnalysisTimelineEntry };

/**
 * Single pass over timeline (sorted by seq) so main explore tools and subagent activity
 * interleave correctly. Delegation is emitted at the ``task`` tool_call, not when the first
 * subagent-scoped row arrives (avoids late "delegating" banner when SSE is buffered).
 */
export function buildTimelineActivityChunks(
  entries: readonly AnalysisTimelineEntry[] | undefined,
  subagentFallback: string = 'subagent',
): TimelineActivityChunk[] {
  if (!entries?.length) return [];
  const sorted = prepareTimelineEntriesForDisplay(entries);
  const chunks: TimelineActivityChunk[] = [];
  const exploreBuf: StreamEvent[] = [];
  const subBuf: AnalysisTimelineEntry[] = [];
  const subagentTaskBoardKeys = new Set<string>();
  let chunkIndex = 0;
  let taskBoardInserted = false;
  let exploreAnchorSeq = 0;
  let invokeStartTs: number | undefined;

  const subagentPlanKey = (e: AnalysisTimelineEntry) => subagentTaskPlanMapKey(e);

  const flushExplore = () => {
    if (!exploreBuf.length) return;
    const merged = mergeReadFileChunks([...exploreBuf]);
    chunks.push({
      kind: 'explore',
      key: `ex-${chunkIndex++}-${merged[0]!.id ?? 0}`,
      events: merged,
      firstSeq: exploreAnchorSeq,
    });
    exploreBuf.length = 0;
  };

  const flushSubagent = () => {
    if (!subBuf.length) return;
    const first = subBuf[0]!;
    chunks.push({
      kind: 'subagent',
      key: `sg-${chunkIndex++}-${first.id ?? seqOf(first)}`,
      items: [...subBuf],
      firstSeq: seqOf(first),
    });
    subBuf.length = 0;
  };

  const ensureTaskBoard = (e: AnalysisTimelineEntry) => {
    flushExplore();
    flushSubagent();
    if (!taskBoardInserted) {
      chunks.push({
        kind: 'task_board',
        key: `tb-${chunkIndex++}`,
        firstSeq: seqOf(e),
      });
      taskBoardInserted = true;
    }
  };

  for (const e of sorted) {
    if (isHiddenFromUserTimeline(e)) continue;
    if (e.type === 'error' && e.scope !== 'subagent') continue;

    const scope = e.scope ?? 'main';

    if (scope === 'subagent') {
      flushExplore();
      const ty = String(e.type);
      const isWriteTodosPlanCall =
        ty === 'tool_call' &&
        String(e.toolName) === 'write_todos' &&
        effectiveToolPresentation(e) === 'task';
      if (ty === 'task_plan' || ty === 'task_create' || ty === 'task_update' || isWriteTodosPlanCall) {
        if (subBuf.length) flushSubagent();
        const sk = subagentPlanKey(e);
        const skKey = `${sk}`;
        if (!subagentTaskBoardKeys.has(skKey)) {
          subagentTaskBoardKeys.add(skKey);
          chunks.push({
            kind: 'task_board_sub',
            key: `tbs-${chunkIndex++}-${skKey}`,
            firstSeq: seqOf(e),
            subagentKey: sk,
          });
        }
        continue;
      }
      if (
        ty === 'tool_call' ||
        ty === 'tool_result' ||
        ty === 'step' ||
        ty === 'reasoning' ||
        ty === 'llm_delta' ||
        ty === 'llm_invoke_start' ||
        ty === 'llm_invoke_end' ||
        ty === 'error'
      ) {
        subBuf.push(e);
      }
      continue;
    }

    if (e.type === 'llm_invoke_start') {
      invokeStartTs = typeof e.timestamp === 'number' ? e.timestamp : undefined;
      continue;
    }
    if (e.type === 'llm_invoke_end') {
      flushExplore();
      flushSubagent();
      const endTs = typeof e.timestamp === 'number' ? e.timestamp : undefined;
      const durationSec =
        endTs != null && invokeStartTs != null
          ? Math.max(0, (endTs - invokeStartTs) / 1000)
          : undefined;
      const last = chunks[chunks.length - 1];
      if (last?.kind === 'reasoning_main') {
        last.invokeDurationSec = durationSec;
        last.invokeState = 'done';
      }
      invokeStartTs = undefined;
      continue;
    }

    if (
      isTimelineReasoningStream(e) &&
      typeof e.content === 'string' &&
      e.content.trim()
    ) {
      flushExplore();
      flushSubagent();
      const turn = typeof e.turn === 'number' ? e.turn : 0;
      const last = chunks[chunks.length - 1];
      if (last?.kind === 'reasoning_main' && last.turn === turn) {
        last.text += e.content;
      } else {
        chunks.push({
          kind: 'reasoning_main',
          key: `rm-${chunkIndex++}-${turn}-${seqOf(e)}`,
          firstSeq: seqOf(e),
          turn,
          text: e.content,
          invokeStartMs: invokeStartTs,
          invokeState: invokeStartTs != null ? 'running' : undefined,
        });
      }
      continue;
    }

    if (e.type === 'task_summary' && typeof e.summary === 'string' && e.summary.trim()) {
      flushExplore();
      flushSubagent();
      chunks.push({
        kind: 'task_summary',
        key: `ts-${seqOf(e)}`,
        seq: seqOf(e),
        summary: e.summary,
      });
      continue;
    }

    const isMainWriteTodosPlan =
      e.type === 'tool_call' &&
      String(e.toolName) === 'write_todos' &&
      effectiveToolPresentation(e) === 'task';
    if (
      e.type === 'task_plan' ||
      e.type === 'task_create' ||
      e.type === 'task_update' ||
      isMainWriteTodosPlan
    ) {
      ensureTaskBoard(e);
      continue;
    }

    if (e.type === 'parameter_request') {
      flushExplore();
      flushSubagent();
      chunks.push({
        kind: 'parameter_request',
        key: `pr-${seqOf(e)}-${String(e.id ?? 'param')}`,
        seq: seqOf(e),
        entry: e,
      });
      continue;
    }

    if (e.type === 'decision_request' && e.decision && typeof e.decision === 'object') {
      flushExplore();
      flushSubagent();
      chunks.push({
        kind: 'decision_request',
        key: `dr-${seqOf(e)}-${String(e.id ?? 'dec')}`,
        seq: seqOf(e),
        entry: e,
      });
      continue;
    }

    if (e.type === 'tool_call' && String(e.toolName) === 'task' && effectiveToolPresentation(e) === 'task') {
      flushExplore();
      flushSubagent();
      const inp = (e.toolInput || {}) as Record<string, unknown>;
      const subagent = String(inp.subagent_type ?? subagentFallback);
      const task = formatDelegatedTaskForDisplay(String(inp.description ?? inp.task ?? ''));
      const last = chunks[chunks.length - 1];
      if (last?.kind === 'delegation' && last.subagent === subagent && last.task === task) {
        continue;
      }
      chunks.push({
        kind: 'delegation',
        key: `del-${seqOf(e)}-${String(inp.subagent_type ?? 'task')}`,
        subagent,
        task,
        firstSeq: seqOf(e),
      });
      continue;
    }

    if (isMainExploreToolCall(e)) {
      flushSubagent();
      if (exploreBuf.length === 0) exploreAnchorSeq = seqOf(e);
      exploreBuf.push({
        type: 'tool_call',
        id: String(e.id ?? `tc-${exploreBuf.length}`),
        seq: seqOf(e),
        scope: e.scope,
        subagentName: e.subagentName,
        timestamp: typeof e.timestamp === 'number' ? e.timestamp : Date.now(),
        toolName: String(e.toolName ?? ''),
        toolInput: (e.toolInput as Record<string, unknown>) || {},
        ...(e.toolPresentation != null &&
        (e.toolPresentation === 'task' ||
          e.toolPresentation === 'action' ||
          e.toolPresentation === 'state' ||
          e.toolPresentation === 'parameter' ||
          e.toolPresentation === 'research_task')
          ? { toolPresentation: e.toolPresentation }
          : {}),
      });
      continue;
    }

    if (isMainExploreToolResult(e)) {
      flushSubagent();
      if (exploreBuf.length === 0) exploreAnchorSeq = seqOf(e);
      exploreBuf.push({
        type: 'tool_result',
        id: String(e.id ?? `tr-${exploreBuf.length}`),
        seq: seqOf(e),
        scope: e.scope,
        subagentName: e.subagentName,
        timestamp: typeof e.timestamp === 'number' ? e.timestamp : Date.now(),
        toolName: String(e.toolName ?? ''),
        toolOutput: e.toolOutput,
        ...(e.toolPresentation != null &&
        (e.toolPresentation === 'task' ||
          e.toolPresentation === 'action' ||
          e.toolPresentation === 'state' ||
          e.toolPresentation === 'parameter' ||
          e.toolPresentation === 'research_task')
          ? { toolPresentation: e.toolPresentation }
          : {}),
      });
      continue;
    }
  }

  flushExplore();
  flushSubagent();
  return chunks;
}

/** Build explore StreamEvents from main-scope timeline rows (pairs tool_call + tool_result by id). */
export function buildExploreStreamEventsFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): StreamEvent[] {
  if (!entries?.length) return [];
  return buildTimelineActivityChunks(entries).flatMap((c) => (c.kind === 'explore' ? c.events : []));
}

export function timelineHasError(entries: readonly AnalysisTimelineEntry[] | undefined): boolean {
  if (!entries?.length) return false;
  return entries.some((e) => e.type === 'error' && !isHiddenFromUserTimeline(e));
}

export function getTimelineErrorDetail(entries: readonly AnalysisTimelineEntry[] | undefined): string {
  if (!entries?.length) return '';
  const sorted = sortTimelineBySeq(entries);
  for (let i = sorted.length - 1; i >= 0; i--) {
    const e = sorted[i];
    if (e.type === 'error' && !isHiddenFromUserTimeline(e)) {
      return String(e.detail ?? e.label ?? '');
    }
  }
  return '';
}

export function extractLatestTaskPlanFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
  options?: { scope?: 'main' | 'subagent' },
): TaskPlan | null {
  if (!entries?.length) return null;
  const scope = options?.scope ?? 'main';
  const sorted = sortTimelineBySeq(entries);
  let last: TaskPlan | null = null;
  for (const e of sorted) {
    if (
      e.type === 'task_plan' &&
      e.plan &&
      typeof e.plan === 'object' &&
      (e.scope ?? 'main') === scope
    ) {
      last = e.plan as TaskPlan;
    }
  }
  return last ? scrubTaskPlanPathsForDisplay(last) : null;
}

/** Extract per-subagent task plans keyed by subagentName (or `_default`). */
export function extractSubagentTaskPlansFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): Record<string, TaskPlan | null> {
  if (!entries?.length) return {};
  const sorted = sortTimelineBySeq(entries);
  const result: Record<string, TaskPlan | null> = {};
  for (const e of sorted) {
    if (
      e.type === 'task_plan' &&
      e.plan &&
      typeof e.plan === 'object' &&
      (e.scope ?? 'main') === 'subagent'
    ) {
      const key = subagentTaskPlanMapKey(e);
      result[key] = scrubTaskPlanPathsForDisplay(e.plan as TaskPlan);
    }
  }
  return result;
}

/**
 * Estimate total thinking duration (seconds) from timeline LLM invoke boundaries.
 * Sums all `llm_invoke_start` → `llm_invoke_end` intervals on the main scope.
 * Falls back to 0 when no invoke boundaries are present.
 */
export function estimateThinkingDurationFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): number {
  if (!entries?.length) return 0;
  const sorted = sortTimelineBySeq(entries);
  let total = 0;
  let startTs: number | undefined;
  for (const e of sorted) {
    if ((e.scope ?? 'main') !== 'main') continue;
    if (e.type === 'llm_invoke_start' && typeof e.timestamp === 'number') {
      startTs = e.timestamp;
    } else if (e.type === 'llm_invoke_end' && typeof e.timestamp === 'number' && startTs != null) {
      total += Math.max(0, e.timestamp - startTs);
      startTs = undefined;
    }
  }
  return total > 0 ? Math.round(total / 1000) : 0;
}

export function extractUnderstandingFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): InputUnderstanding | null {
  if (!entries?.length) return null;
  const sorted = sortTimelineBySeq(entries);
  for (let i = sorted.length - 1; i >= 0; i--) {
    const e = sorted[i];
    if (e.type === 'understanding' && e.understanding && typeof e.understanding === 'object') {
      return e.understanding as InputUnderstanding;
    }
  }
  return null;
}

export function extractTaskSummaryFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): string {
  if (!entries?.length) return '';
  const sorted = sortTimelineBySeq(entries);
  for (let i = sorted.length - 1; i >= 0; i--) {
    const e = sorted[i];
    if (e.type === 'task_summary' && typeof e.summary === 'string') return e.summary;
  }
  return '';
}

export function extractWorkspaceTitleFromTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
): string | undefined {
  const plan = extractLatestTaskPlanFromTimeline(entries);
  return plan?.workspaceTitle;
}
