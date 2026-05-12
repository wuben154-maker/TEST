/**
 * Maps canonical analysis timeline entries to v0-style ReAct display blocks.
 */
import type { AnalysisTimelineEntry, InputUnderstanding } from '@/types/analysis';
import type { Language } from '@/i18n';
import { getTranslations } from '@/i18n';
import { toolOutputTimelineMaxChars } from '@/lib/config';
import { isHiddenFromUserTimeline, prepareTimelineEntriesForDisplay } from '@/lib/timelineDisplay';
import { effectiveToolPresentation } from '@/lib/toolPresentation';
import { compactToolRowLabel } from '@/lib/toolCallDisplay';

function interpolateTimeline(template: string, vars: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => vars[key] ?? `{${key}}`);
}

/** Official subagent id → short display label (fallback: title-case id). */
const SUBAGENT_DISPLAY_BY_LANG: Partial<
  Record<Language, Record<string, string>>
> = {
  en: {
    'email-security': 'Email security',
    'binary-analysis': 'Binary analysis',
    'web-security': 'Web security',
    'deep-research': 'Deep research',
    'soc-alert': 'SOC alert',
  },
  zh: {
    'email-security': '邮件安全',
    'binary-analysis': '二进制分析',
    'web-security': 'Web 安全',
    'deep-research': '深度研究',
    'soc-alert': 'SOC 告警',
  },
  ja: {
    'email-security': 'メールセキュリティ',
    'binary-analysis': 'バイナリ解析',
    'web-security': 'Web セキュリティ',
    'deep-research': 'ディープリサーチ',
    'soc-alert': 'SOC アラート',
  },
  ko: {
    'email-security': '이메일 보안',
    'binary-analysis': '바이너리 분석',
    'web-security': '웹 보안',
    'deep-research': '딥 리서치',
    'soc-alert': 'SOC 알림',
  },
};

function resolveSubagentDisplayName(subagentName: string | undefined, language: Language): string {
  const id = String(subagentName ?? '').trim();
  if (!id) return 'subagent';
  const fromTable = SUBAGENT_DISPLAY_BY_LANG[language]?.[id] ?? SUBAGENT_DISPLAY_BY_LANG.en?.[id];
  if (fromTable) return fromTable;
  return id
    .split('-')
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : ''))
    .join(' ');
}

/** Groups merged subagent-stream rows for nesting UI + reasoning merge (legacy bucket when unset). */
export function delegationStreamKey(ev: AnalysisTimelineEntry): string {
  const sn = String(ev.subagentName ?? '').trim();
  if (typeof ev.delegationDepth !== 'number' && ev.rootDelegationId == null) {
    return sn ? `legacy|${sn}` : 'legacy';
  }
  return [
    String(ev.delegationDepth ?? ''),
    String(ev.rootDelegationId ?? ''),
    String(ev.parentToolCallId ?? ''),
    sn,
  ].join('|');
}

function seqOfTimelineEntry(e: AnalysisTimelineEntry): number {
  const n = Number(e.seq);
  return Number.isFinite(n) ? n : 0;
}

export type ReActThinkingBlock = {
  kind: 'thinking';
  reasoning: string;
  answer: string;
  turn: number;
  invokeState?: 'running' | 'done';
  invokeDurationSec?: number;
  /** Server `llm_invoke_start.timestamp` (ms) for live elapsed label while `invokeState === 'running'`. */
  invokeStartMs?: number;
};

export type ReActStepBlock = {
  kind: 'step';
  stepVariant: 'subagent_task' | 'generic' | 'delegation_group';
  label: string;
  detail?: string;
  status?: string;
  /** Deep-research (and similar): stable slot id for React keys / one row per phase. */
  phaseId?: string;
  /** Merged wall-clock duration for task-running subagent steps (seconds). */
  subagentDurationSec?: number;
  /** When ``stepVariant === 'delegation_group'``: hop depth for left-indent (1 = first subagent). */
  delegationDepth?: number;
  /** Technical identifier of the subagent that owns this delegation group (e.g. `email-security`). */
  subagentId?: string;
};

/** One explore/action tool row; `done` becomes true when a matching `tool_result` is seen. */
export type ReActToolChild = {
  toolCallId: string;
  toolName: string;
  detail: string;
  done: boolean;
  /** Tool output for expanded `<pre>` (capped by ``toolOutputTimelineMaxChars``). */
  toolOutput?: string;
  /** True when tool_result status is 'error'. */
  isError?: boolean;
};

export type ReActToolExecutionBlock = {
  kind: 'tool_execution';
  children: ReActToolChild[];
  /** Technical id of the subagent that owns these tool calls, or undefined for main-graph tools. */
  subagentId?: string;
  /** Delegation hop depth matching the owning subagent banner (1 = first subagent). */
  delegationDepth?: number;
};

export type ReActTaskListBlock = {
  kind: 'task_list';
  bucketKey: string;
  /** `research`: ConductResearch topics — same list UI as todos with a distinct heading. */
  listVariant?: 'default' | 'research';
  items: { id: string; title: string; done: boolean }[];
};

export type ReActResultBlock = {
  kind: 'result';
  summary: string;
};

/** Placeholder for inline HITL form rendering at its chronological timeline position.
 *  Carries event payload so the form renders even when model state is cleared (conversation history).
 */
export type ReActHitlSlotBlock = {
  kind: 'hitl_slot';
  slotType: 'parameter_request' | 'decision_request';
  /** Parameter request field definitions from the SSE event (fallback for model.parameterRequests). */
  eventParameterRequests?: unknown[];
  /** Prompt detail from the SSE event. */
  eventPrompt?: string;
  /** Decision object from the SSE event (for decision_request). */
  eventDecision?: unknown;
};

export type ReActBlock =
  | ReActThinkingBlock
  | ReActStepBlock
  | ReActToolExecutionBlock
  | ReActTaskListBlock
  | ReActResultBlock
  | ReActHitlSlotBlock;

function isPhaseSlotReActStep(b: ReActBlock): boolean {
  if (b.kind !== 'step') return false;
  const s = b as ReActStepBlock;
  if (s.phaseId != null && String(s.phaseId).trim() !== '') return true;
  if (s.stepVariant === 'subagent_task') return true;
  if (s.stepVariant === 'delegation_group') return true;
  return false;
}

/**
 * If coalesce left [thinking, step], swap so the static row leads — except plan/collect/report,
 * which must stay after prior phase stream.
 */
function swapPhaseSlotStepBeforeAdjacentThinking(blocks: ReActBlock[]): ReActBlock[] {
  if (blocks.length < 2) return blocks;
  const out = blocks.slice();
  for (let i = 0; i < out.length - 1; i++) {
    const a = out[i];
    const b = out[i + 1];
    if (a.kind !== 'thinking' || b.kind !== 'step') continue;
    if (!isPhaseSlotReActStep(b)) continue;
    const spid = String((b as ReActStepBlock).phaseId ?? '').trim();
    if (PHASE_IDS_MILESTONE_AFTER_STREAM.has(spid)) continue;
    out[i] = b;
    out[i + 1] = a;
  }
  return out;
}

/** Held state when no SSE timeline rows exist (replay / pre-stream). */
export type BuildReActOfflineContext = {
  understanding?: InputUnderstanding | null;
  streamReasoningFallback?: string;
  extraSummary?: { taskSummary?: string };
};

function isSubstantiallySameSummary(a: string, b: string): boolean {
  const na = a.trim();
  const nb = b.trim();
  if (!na || !nb) return false;
  if (na === nb) return true;
  const shorter = na.length < nb.length ? na : nb;
  const longer = na.length >= nb.length ? na : nb;
  return longer.startsWith(shorter);
}

/**
 * Build ReAct blocks from understanding + stream fallback + task summary only (no timeline entries).
 */
function buildOfflineReActBlocks(offline: BuildReActOfflineContext | undefined, language: Language): ReActBlock[] {
  if (!offline) return [];
  const blocks: ReActBlock[] = [];
  const tReason = getTranslations(language).reasoning;

  const u = offline.understanding;
  if (u) {
    const intro = [u.summary, u.reasoningSummary].filter(Boolean).join('\n\n').trim();
    if (intro) {
      blocks.push({
        kind: 'thinking',
        reasoning: intro,
        answer: '',
        turn: 0,
      });
    }
  }

  const fb = offline.streamReasoningFallback?.trim();
  if (fb) {
    blocks.push({
      kind: 'thinking',
      reasoning: `${tReason.thinkingPrefix}${fb}`,
      answer: '',
      turn: 0,
    });
  }

  let lastSummaryText = '';
  const pushSummary = (text: string) => {
    const t = text.trim();
    if (!t) return;
    if (lastSummaryText && isSubstantiallySameSummary(lastSummaryText, t)) return;
    blocks.push({ kind: 'result', summary: t });
    lastSummaryText = t;
  };

  const extra = offline.extraSummary?.taskSummary?.trim();
  if (extra) pushSummary(extra);

  return coalesceThinkingBlocksAcrossTools(blocks);
}

const ADAPTER_STEP_IDS_SKIP = new Set(['analysis-start', 'analysis-complete', 'hitl-waiting', 'stream-init-resume']);

/**
 * Phases whose milestone must appear **after** prior phase's stream output.
 * Only `deep_research_clarify` leads (entry point — no prior stream).
 * All others flush prior thinking before their step label.
 */
const PHASE_IDS_MILESTONE_AFTER_STREAM = new Set([
  'deep_research_plan',
  'deep_research_collect',
  'deep_research_report',
]);

/**
 * Timeline `step` rows that use a fixed UI slot (phase banner, dr-*, or task-running).
 */
function isPhaseSlotTimelineStep(ev: AnalysisTimelineEntry): boolean {
  if (ev.type !== 'step') return false;
  const sid = String(ev.id ?? '');
  if (ADAPTER_STEP_IDS_SKIP.has(sid)) return false;
  const pid = ev.phaseId != null ? String(ev.phaseId).trim() : '';
  if (pid !== '') return true;
  if (/^dr-(phase-|pre-)/.test(sid)) return true;
  if (sid.startsWith('task-running-')) return true;
  return false;
}

/**
 * When true: skip pre-flush, emit step, then flush — static label leads buffered reasoning (clarify only).
 * When false for a slot step: normal flush-then-step (plan/collect/report after prior phase stream).
 */
function phaseMilestoneLeadsBufferedStream(ev: AnalysisTimelineEntry): boolean {
  if (!isPhaseSlotTimelineStep(ev)) return false;
  const pid = ev.phaseId != null ? String(ev.phaseId).trim() : '';
  if (PHASE_IDS_MILESTONE_AFTER_STREAM.has(pid)) return false;
  const sid = String(ev.id ?? '');
  if (!pid && sid.startsWith('dr-phase-')) {
    for (const late of PHASE_IDS_MILESTONE_AFTER_STREAM) {
      if (sid.includes(late)) return false;
    }
  }
  return true;
}

/**
 * Same `phaseId` may emit running then success. Merge at **min seq**; overlay latest fields.
 */
function mergePhaseIdMilestoneStepsAtMinSeq(
  entries: readonly AnalysisTimelineEntry[],
): AnalysisTimelineEntry[] {
  type Group = { first: AnalysisTimelineEntry; last: AnalysisTimelineEntry };
  const byPhase = new Map<string, Group>();
  for (const ev of entries) {
    if (ev.type !== 'step') continue;
    const pid = ev.phaseId != null ? String(ev.phaseId).trim() : '';
    if (pid === '') continue;
    const s = seqOfTimelineEntry(ev);
    const g = byPhase.get(pid);
    if (!g) {
      byPhase.set(pid, { first: ev, last: ev });
    } else {
      if (s < seqOfTimelineEntry(g.first)) g.first = ev;
      if (s >= seqOfTimelineEntry(g.last)) g.last = ev;
    }
  }
  const mergedByPhase = new Map<string, AnalysisTimelineEntry>();
  for (const { first, last } of byPhase.values()) {
    const pid = String(first.phaseId ?? last.phaseId ?? '').trim();
    if (!pid) continue;
    mergedByPhase.set(pid, {
      ...first,
      ...last,
      seq: first.seq,
      phaseId: first.phaseId ?? last.phaseId,
    } as AnalysisTimelineEntry);
  }
  const emitted = new Set<string>();
  const out: AnalysisTimelineEntry[] = [];
  for (const ev of entries) {
    if (ev.type !== 'step') {
      out.push(ev);
      continue;
    }
    const pid = ev.phaseId != null ? String(ev.phaseId).trim() : '';
    if (pid === '') {
      out.push(ev);
      continue;
    }
    if (emitted.has(pid)) continue;
    emitted.add(pid);
    const m = mergedByPhase.get(pid);
    if (m) out.push(m);
  }
  return out;
}

type TimelineEntryExt = AnalysisTimelineEntry & {
  mergeSubagentDurationSec?: number;
};

/**
 * Collapse duplicate `task-running-*` step rows (running + success) into one timeline entry.
 * Success-only row is not shown separately; duration uses optional `timestamp` on events.
 */
function dedupeTaskRunningSteps(sorted: readonly AnalysisTimelineEntry[]): TimelineEntryExt[] {
  const byId = new Map<string, AnalysisTimelineEntry[]>();
  for (const ev of sorted) {
    if (ev.type === 'step' && String(ev.id ?? '').startsWith('task-running-')) {
      const id = String(ev.id);
      if (!byId.has(id)) byId.set(id, []);
      byId.get(id)!.push(ev);
    }
  }
  const seenTaskRunning = new Set<string>();
  const out: TimelineEntryExt[] = [];
  for (const ev of sorted) {
    if (ev.type === 'step' && String(ev.id ?? '').startsWith('task-running-')) {
      const id = String(ev.id);
      if (seenTaskRunning.has(id)) continue;
      seenTaskRunning.add(id);
      const group = byId.get(id)!;
      const first = group[0];
      const last = group[group.length - 1];
      const t0 = typeof first.timestamp === 'number' ? first.timestamp : undefined;
      const t1 = typeof last.timestamp === 'number' ? last.timestamp : undefined;
      // Single-row replay (e.g. resume/persistence) or identical timestamps yield 0s — omit duration
      // so the UI uses "completed" copy instead of "0 seconds".
      let mergeSubagentDurationSec: number | undefined;
      if (group.length >= 2 && t0 != null && t1 != null && t1 > t0) {
        const sec = Math.round((t1 - t0) / 1000);
        mergeSubagentDurationSec = sec > 0 ? sec : undefined;
      }
      out.push({
        ...first,
        status: last.status ?? first.status,
        mergeSubagentDurationSec,
      });
      continue;
    }
    out.push(ev);
  }
  return out;
}

function shouldFlushThinkingBeforeEvent(ev: AnalysisTimelineEntry): boolean {
  if (ev.type === 'reasoning' || ev.type === 'answer') return false;
  if (ev.type === 'llm_delta') return false;
  if (ev.type === 'llm_invoke_start') return false;
  if (ev.type === 'tool_call' || ev.type === 'tool_result') return false;
  return true;
}

/** Stream bucket for merge: main vs subagent must never merge into one thinking block. */
function timelineStreamScope(ev: AnalysisTimelineEntry): 'main' | 'subagent' {
  if (ev.subagentStream === true || ev.scope === 'subagent') return 'subagent';
  return 'main';
}

/**
 * True when two consecutive timeline `reasoning` rows belong to the same think phase.
 * - Both numeric turns: must match.
 * - Otherwise: merge (streaming often omits `turn` on early chunks or mixes set/unset).
 */
function shouldMergeConsecutiveReasoningRows(
  a: AnalysisTimelineEntry,
  b: AnalysisTimelineEntry,
): boolean {
  if (timelineStreamScope(a) !== timelineStreamScope(b)) return false;
  if (timelineStreamScope(a) === 'subagent' && timelineStreamScope(b) === 'subagent') {
    if (delegationStreamKey(a) !== delegationStreamKey(b)) return false;
  }
  const ta = typeof a.turn === 'number' ? a.turn : undefined;
  const tb = typeof b.turn === 'number' ? b.turn : undefined;
  if (ta !== undefined && tb !== undefined) return ta === tb;
  return true;
}

/** Legacy `reasoning` / `answer` or `llm_delta` with `channel`. */
function streamTextRowKind(ev: AnalysisTimelineEntry): 'reasoning' | 'text' | null {
  const t = String(ev.type ?? '');
  if (t === 'reasoning') return 'reasoning';
  if (t === 'answer') return 'text';
  if (t === 'llm_delta') {
    const ch = String((ev as { channel?: string }).channel ?? '');
    if (ch === 'reasoning') return 'reasoning';
    if (ch === 'text') return 'text';
  }
  return null;
}

/**
 * Collapse adjacent reasoning/text stream rows (legacy + `llm_delta`) before block build.
 * Preserves `llm_invoke_start` / `llm_invoke_end` so `buildReActTimeline` can flush on invoke boundaries.
 * Normalizes merged rows to `type: reasoning` | `answer`.
 */
export function mergeConsecutiveReasoningTimelineRows(
  entries: readonly TimelineEntryExt[],
): TimelineEntryExt[] {
  const out: TimelineEntryExt[] = [];
  for (const ev of entries) {
    if (ev.type === 'llm_invoke_start' || ev.type === 'llm_invoke_end') {
      out.push(ev);
      continue;
    }
    const kind = streamTextRowKind(ev);
    if (!kind) {
      out.push(ev);
      continue;
    }
    const normalized: TimelineEntryExt = {
      ...ev,
      type: kind === 'reasoning' ? 'reasoning' : 'answer',
      channel: undefined,
      invokeId: undefined,
    };
    const prev = out[out.length - 1];
    if (
      prev &&
      streamTextRowKind(prev) === kind &&
      shouldMergeConsecutiveReasoningRows(prev, normalized)
    ) {
      const nextTurn =
        typeof normalized.turn === 'number'
          ? normalized.turn
          : typeof prev.turn === 'number'
            ? prev.turn
            : undefined;
      const merged: TimelineEntryExt = {
        ...prev,
        content: String(prev.content ?? '') + String(normalized.content ?? ''),
      };
      if (nextTurn !== undefined) merged.turn = nextTurn;
      out[out.length - 1] = merged;
    } else {
      out.push({ ...normalized });
    }
  }
  return out;
}

/** Middle blocks that follow one Thinking block before the next Thinking (order preserved). */
const THINKING_COALESCE_MIDDLE_KINDS = new Set<ReActBlock['kind']>([
  'tool_execution',
  'task_list',
  'step',
]);

/**
 * Walks the block list and attaches tool/step/task_list rows after each thinking block.
 * Does **not** merge multiple `thinking` blocks: each `llm_invoke_end` (or legacy flush) is its own
 * chunk; same ReAct `turn` may yield several thinking blocks.
 */
export function coalesceThinkingBlocksAcrossTools(blocks: ReActBlock[]): ReActBlock[] {
  const out: ReActBlock[] = [];
  let i = 0;
  while (i < blocks.length) {
    const b = blocks[i];
    if (b.kind !== 'thinking') {
      out.push(b);
      i++;
      continue;
    }
    const cur: ReActThinkingBlock = { ...b };
    i++;
    const middle: ReActBlock[] = [];
    while (i < blocks.length) {
      const nb = blocks[i];
      if (nb.kind === 'step' && isPhaseSlotReActStep(nb)) {
        break;
      }
      if (THINKING_COALESCE_MIDDLE_KINDS.has(nb.kind)) {
        middle.push(nb);
        i++;
        continue;
      }
      break;
    }
    out.push(cur, ...middle);
  }
  return out;
}

function listBucketKey(ev: AnalysisTimelineEntry): string {
  const scope = String(ev.scope ?? 'main');
  const sn = String(ev.subagentName ?? 'main');
  const inp = (ev.toolInput as Record<string, unknown>) || {};
  const lid = String(inp.listId ?? inp.planSessionId ?? inp.todoListId ?? '');
  return `${scope}:${sn}:${lid}`;
}

const _RESEARCH_TASK_BUCKET_MARK = 'conduct-research';

/** Stable bucket for ConductResearch rows (scope + subagent + fixed mark). */
export function researchTaskBucketKey(ev: AnalysisTimelineEntry): string {
  const scope = String(ev.scope ?? 'main');
  const sn = String(ev.subagentName ?? 'main');
  return `${scope}:${sn}:${_RESEARCH_TASK_BUCKET_MARK}`;
}

/** Cumulative research task rows up to ``maxSeq`` (inclusive), for cross-chunk UI merge. */
export type ResearchTaskListBuckets = Map<
  string,
  { id: string; title: string; done: boolean }[]
>;

export function foldResearchTaskListBuckets(
  entries: readonly AnalysisTimelineEntry[] | undefined,
  opts?: {
    language?: Language;
    maxSeq?: number;
    onlyBucketKey?: string;
  },
): ResearchTaskListBuckets {
  const language = opts?.language ?? 'en';
  const maxSeq = opts?.maxSeq;
  const onlyBucketKey = opts?.onlyBucketKey;
  const buckets: ResearchTaskListBuckets = new Map();

  if (!entries?.length) return buckets;

  const prepared = prepareTimelineEntriesForDisplay(entries);
  const visibleSorted = prepared.filter((e) => !isHiddenFromUserTimeline(e));
  const capped =
    maxSeq === undefined
      ? visibleSorted
      : visibleSorted.filter((e) => seqOfTimelineEntry(e) <= maxSeq);

  const t = getTranslations(language);

  for (const ev of capped) {
    if (ev.type === 'tool_call') {
      const pres = effectiveToolPresentation(ev);
      if (!(pres === 'research_task' || ev.toolName === 'ConductResearch')) continue;
      const toolCallId = String(ev.id ?? '');
      if (!toolCallId) continue;
      const inp = (ev.toolInput as Record<string, unknown>) || {};
      const rawTitle = String(inp.research_topic ?? '').trim();
      const titleBase = rawTitle || t.reasoning.researchTopicPending;
      const key = researchTaskBucketKey(ev);
      if (onlyBucketKey !== undefined && key !== onlyBucketKey) continue;
      const title = titleBase.length > 2000 ? `${titleBase.slice(0, 2000)}…` : titleBase;
      let items = buckets.get(key);
      if (!items) {
        items = [];
        buckets.set(key, items);
      }
      const hit = items.find((it) => it.id === toolCallId);
      if (hit) {
        if (rawTitle && title !== hit.title) hit.title = title;
      } else {
        items.push({ id: toolCallId, title, done: false });
      }
    } else if (ev.type === 'tool_result') {
      const rid = String(ev.id ?? '');
      if (
        !rid ||
        !(
          effectiveToolPresentation(ev) === 'research_task' || ev.toolName === 'ConductResearch'
        )
      ) {
        continue;
      }
      const key = researchTaskBucketKey(ev);
      if (onlyBucketKey !== undefined && key !== onlyBucketKey) continue;
      const items = buckets.get(key);
      if (!items) continue;
      const row = items.find((it) => it.id === rid);
      if (row) row.done = true;
    }
  }

  return buckets;
}

/** Merge cumulative research buckets into blocks built from a single explore/subagent chunk. */
export function mergeResearchTaskListsIntoBlocks(
  blocks: ReActBlock[],
  buckets: ResearchTaskListBuckets,
): ReActBlock[] {
  const keysInBlocks = new Set<string>();
  const next = blocks.map((b) => {
    if (b.kind === 'task_list' && b.listVariant === 'research') {
      keysInBlocks.add(b.bucketKey);
      const cum = buckets.get(b.bucketKey);
      if (cum?.length) {
        return { ...b, items: cum.map((i) => ({ ...i })) };
      }
    }
    return b;
  });
  const toInsert: ReActBlock[] = [];
  for (const [key, items] of buckets) {
    if (!items.length || keysInBlocks.has(key)) continue;
    toInsert.push({
      kind: 'task_list',
      bucketKey: key,
      listVariant: 'research',
      items: items.map((i) => ({ ...i })),
    });
  }
  if (!toInsert.length) return next;
  const firstToolIdx = next.findIndex((b) => b.kind === 'tool_execution');
  const insertAt = firstToolIdx >= 0 ? firstToolIdx : 0;
  return [...next.slice(0, insertAt), ...toInsert, ...next.slice(insertAt)];
}

/** Highest finite ``seq`` in a slice, or undefined if none (avoids capping fold to 0). */
export function maxSeqInTimelineSlice(
  entries: readonly (AnalysisTimelineEntry | { seq?: number })[] | undefined,
): number | undefined {
  if (!entries?.length) return undefined;
  let m = 0;
  let any = false;
  for (const e of entries) {
    const n = Number((e as AnalysisTimelineEntry).seq);
    if (Number.isFinite(n)) {
      any = true;
      m = Math.max(m, n);
    }
  }
  return any ? m : undefined;
}

function parseTodosFromWriteTodos(
  ev: AnalysisTimelineEntry,
): { id: string; title: string; done: boolean }[] | null {
  if (ev.type !== 'tool_call' || ev.toolName !== 'write_todos' || !ev.toolInput) return null;
  const inp = ev.toolInput as Record<string, unknown>;
  const raw = (inp.todos ?? inp.tasks) as unknown[] | undefined;
  if (!Array.isArray(raw)) return null;
  const out: { id: string; title: string; done: boolean }[] = [];
  raw.forEach((todo, idx) => {
    if (!todo || typeof todo !== 'object') return;
    const t = todo as Record<string, unknown>;
    const id = t.id !== undefined && t.id !== null && String(t.id).trim() !== '' ? String(t.id) : String(idx);
    const title = String(t.content ?? t.task ?? t.title ?? '');
    const st = String(t.status ?? 'pending');
    const done = st === 'completed' || st === 'success';
    out.push({ id, title, done });
  });
  return out.length ? out : null;
}

function pickToolDetail(input: Record<string, unknown>): string {
  const v =
    input.file_path ??
    input.path ??
    input.url ??
    (typeof input.query === 'string' ? input.query : '') ??
    '';
  return String(v);
}

function readFilePathFromInput(input: Record<string, unknown>): string {
  return String(input.file_path ?? input.path ?? '').trim();
}

/**
 * Build ordered ReAct UI blocks from timeline (user-visible rows only, sorted by seq).
 * When ``entries`` is empty, synthesizes blocks from ``opts.offline`` (understanding / stream / summary).
 */
export function buildReActTimeline(
  entries: readonly AnalysisTimelineEntry[] | undefined,
  opts?: { language?: Language; offline?: BuildReActOfflineContext },
): ReActBlock[] {
  const language: Language = opts?.language ?? 'en';
  if (!entries?.length) {
    return buildOfflineReActBlocks(opts?.offline, language);
  }

  const prepared = prepareTimelineEntriesForDisplay(entries);
  const visibleSorted = prepared.filter((e) => !isHiddenFromUserTimeline(e));
  const sorted = mergeConsecutiveReasoningTimelineRows(
    dedupeTaskRunningSteps(mergePhaseIdMilestoneStepsAtMinSeq(visibleSorted)),
  );
  const blocks: ReActBlock[] = [];

  let bufR = '';
  let bufA = '';
  let bufTurn = 0;
  let hasBufTurn = false;
  let invokeOpen = false;
  let invokeStartTs: number | undefined;
  /** Stream bucket for the current reasoning/answer buffer (main vs subagent must not share one block). */
  let bufStreamScope: 'main' | 'subagent' | null = null;
  /**
   * Index of a `thinking` block flushed at `llm_invoke_end` with reasoning only (no answer).
   * A following answer-only flush may merge into it **unless** a new `llm_invoke_start` or
   * structural block (tool/step/result/task_list) invalidates this first.
   */
  let invokeEndOrphanCandidateIdx: number | null = null;

  const flushThinking = (
    opts?: {
      allowEmpty?: boolean;
      invokeState?: 'running' | 'done';
      invokeDurationSec?: number;
      /** When true, a reasoning-only flush may become the merge target for a late text delta. */
      fromInvokeEnd?: boolean;
      invokeStartMs?: number;
    },
  ) => {
    const allowEmpty = opts?.allowEmpty === true;
    const fromInvokeEnd = opts?.fromInvokeEnd === true;

    // Late `llm_delta` text after `llm_invoke_end` (same invoke, no new start): fold into prior block.
    if (
      invokeEndOrphanCandidateIdx !== null &&
      !bufR.trim() &&
      bufA.trim() !== ''
    ) {
      const idx = invokeEndOrphanCandidateIdx;
      const target = blocks[idx];
      if (
        target?.kind === 'thinking' &&
        target.reasoning.trim() !== '' &&
        !target.answer.trim()
      ) {
        target.answer = bufA;
        if (opts?.invokeState !== undefined) target.invokeState = opts.invokeState;
        if (opts?.invokeDurationSec !== undefined) target.invokeDurationSec = opts.invokeDurationSec;
        bufR = '';
        bufA = '';
        hasBufTurn = false;
        bufStreamScope = null;
        invokeEndOrphanCandidateIdx = null;
        return;
      }
      invokeEndOrphanCandidateIdx = null;
    }

    if (!allowEmpty && !bufR.trim() && !bufA.trim()) return;

    const reasoning = bufR;
    const answer = bufA;
    const turn = hasBufTurn ? bufTurn : 0;
    bufR = '';
    bufA = '';
    hasBufTurn = false;
    bufStreamScope = null;

    const running = opts?.invokeState === 'running';
    const newBlock: ReActThinkingBlock = {
      kind: 'thinking',
      reasoning,
      answer,
      turn,
      invokeState: opts?.invokeState,
      invokeDurationSec: opts?.invokeDurationSec,
      invokeStartMs: running ? opts?.invokeStartMs : undefined,
    };

    const keepOrphanCandidate =
      fromInvokeEnd && newBlock.reasoning.trim() !== '' && !newBlock.answer.trim();

    if (!keepOrphanCandidate) {
      invokeEndOrphanCandidateIdx = null;
    }

    blocks.push(newBlock);

    if (keepOrphanCandidate) {
      invokeEndOrphanCandidateIdx = blocks.length - 1;
    }
  };

  let toolChildren: ReActToolChild[] = [];
  let lastReadFilePath: string | null = null;
  /** Technical id of the currently-active subagent (set on delegation banner, cleared on main-graph llm_invoke_start). */
  let currentSubagentId: string | null = null;
  /** Delegation depth of the currently-active subagent. */
  let currentDelegationDepth: number | null = null;

  const markToolCallDone = (
    toolResultId: string,
    rawOutput?: string,
    isError?: boolean,
  ) => {
    if (!toolResultId) return;
    const applyResult = (c: ReActToolChild) => {
      c.done = true;
      if (rawOutput) {
        const maxLen = toolOutputTimelineMaxChars;
        c.toolOutput =
          rawOutput.length > maxLen
            ? rawOutput.slice(0, maxLen) + '…'
            : rawOutput;
      }
      if (isError) c.isError = true;
    };
    const pending = toolChildren.find((c) => c.toolCallId === toolResultId);
    if (pending) {
      applyResult(pending);
      return;
    }
    for (let bi = blocks.length - 1; bi >= 0; bi--) {
      const b = blocks[bi];
      if (b.kind !== 'tool_execution') continue;
      const row = b.children.find((c) => c.toolCallId === toolResultId);
      if (row) {
        applyResult(row);
        return;
      }
    }
  };

  const flushTools = () => {
    if (!toolChildren.length) return;
    invokeEndOrphanCandidateIdx = null;
    blocks.push({
      kind: 'tool_execution',
      children: toolChildren.map((c) => ({ ...c })),
      subagentId: currentSubagentId ?? undefined,
      delegationDepth: currentDelegationDepth ?? undefined,
    });
    toolChildren = [];
    lastReadFilePath = null;
  };

  const upsertTaskList = (
    key: string,
    items: { id: string; title: string; done: boolean }[],
  ) => {
    const snapshot = items.map((i) => ({ ...i }));
    const idx = blocks.findIndex((b) => b.kind === 'task_list' && b.bucketKey === key);
    const nb: ReActTaskListBlock = {
      kind: 'task_list',
      bucketKey: key,
      listVariant: 'default',
      items: snapshot,
    };
    if (idx >= 0) blocks[idx] = nb;
    else {
      invokeEndOrphanCandidateIdx = null;
      blocks.push(nb);
    }
  };

  let lastDelegationBannerKey: string | null = null;
  /** Guard against repeated banners for the same delegation invocation.
   *  Each unique dk (delegationDepth|rootDelegationId|parentToolCallId|subagentName)
   *  represents one specific task() call and should only produce one banner,
   *  even when duplicate events arrive via both stream_writer and queue paths. */
  const seenDelegationKeys = new Set<string>();

  for (const ev of sorted) {
    const entry = ev as AnalysisTimelineEntry;
    const scBanner = timelineStreamScope(entry);
    if (scBanner === 'subagent') {
      const dk = delegationStreamKey(entry);
      if (dk !== 'legacy') {
        if (lastDelegationBannerKey !== null && dk !== lastDelegationBannerKey) {
          flushThinking();
          flushTools();
        }
        if (!seenDelegationKeys.has(dk)) {
          seenDelegationKeys.add(dk);
          invokeEndOrphanCandidateIdx = null;
          const tloc = getTranslations(language);
          const display = resolveSubagentDisplayName(entry.subagentName, language);
          const techId = String(entry.subagentName ?? '').trim();
          const headingTpl =
            typeof entry.delegationDepth === 'number' && entry.delegationDepth >= 2
              ? tloc.reasoning.delegationNestedHeading
              : tloc.reasoning.delegationSpecialistHeading;
          const bannerDepth =
            typeof entry.delegationDepth === 'number' ? entry.delegationDepth : undefined;
          blocks.push({
            kind: 'step',
            stepVariant: 'delegation_group',
            label: interpolateTimeline(headingTpl, {
              displayName: display,
            }),
            detail: techId
              ? interpolateTimeline(tloc.reasoning.delegationTechnicalIdLabel, { id: techId })
              : undefined,
            status: 'success',
            delegationDepth: bannerDepth,
            subagentId: techId || undefined,
          });
        }
        // Only track subagentId/depth for entries that carry the delegation envelope
        // (delegationDepth + rootDelegationId). Legacy-only rows (subagentName, no envelope)
        // must not stamp subagentId onto tool blocks.
        if (typeof entry.delegationDepth === 'number' && entry.rootDelegationId != null) {
          currentSubagentId = String(entry.subagentName ?? '').trim() || null;
          currentDelegationDepth = entry.delegationDepth;
        }
        lastDelegationBannerKey = dk;
      }
    }

    const t = typeof ev.turn === 'number' ? ev.turn : undefined;

    if (ev.type === 'llm_invoke_end') {
      const t1 = typeof ev.timestamp === 'number' ? ev.timestamp : undefined;
      const durationSec =
        t1 != null && invokeStartTs != null ? Math.max(0, (t1 - invokeStartTs) / 1000) : undefined;
      flushThinking({
        allowEmpty: true,
        invokeState: 'done',
        invokeDurationSec: durationSec,
        fromInvokeEnd: true,
      });
      invokeOpen = false;
      invokeStartTs = undefined;
      continue;
    }
    if (ev.type === 'llm_invoke_start') {
      invokeEndOrphanCandidateIdx = null;
      const invSc = timelineStreamScope(ev);
      if (
        bufStreamScope !== null &&
        invSc !== bufStreamScope &&
        (bufR.trim() || bufA.trim())
      ) {
        flushThinking();
      }
      // Commit pending tool rows before the next LLM streaming phase. Otherwise
      // tool_call/tool_result pairs that sit between two invokes stay buffered
      // until loop end and render after the second thinking block (wrong order).
      flushTools();
      if (invSc === 'main') {
        currentSubagentId = null;
        currentDelegationDepth = null;
      }
      invokeOpen = true;
      invokeStartTs = typeof ev.timestamp === 'number' ? ev.timestamp : undefined;
      continue;
    }

    if (ev.type === 'reasoning') {
      const sc = timelineStreamScope(ev);
      if (
        bufStreamScope !== null &&
        sc !== bufStreamScope &&
        (bufR.trim() || bufA.trim())
      ) {
        flushThinking();
      }
      if (t !== undefined && hasBufTurn && t !== bufTurn && (bufR || bufA)) flushThinking();
      if (t !== undefined) {
        bufTurn = t;
        hasBufTurn = true;
      }
      bufR += typeof ev.content === 'string' ? ev.content : '';
      bufStreamScope = sc;
      continue;
    }

    if (ev.type === 'answer') {
      const sc = timelineStreamScope(ev);
      if (
        bufStreamScope !== null &&
        sc !== bufStreamScope &&
        (bufR.trim() || bufA.trim())
      ) {
        flushThinking();
      }
      if (t !== undefined && hasBufTurn && t !== bufTurn && (bufR || bufA)) flushThinking();
      if (t !== undefined) {
        bufTurn = t;
        hasBufTurn = true;
      }
      bufA += typeof ev.content === 'string' ? ev.content : '';
      bufStreamScope = sc;
      continue;
    }

    const milestoneLeadsStream = phaseMilestoneLeadsBufferedStream(ev);

    if (shouldFlushThinkingBeforeEvent(ev) && !milestoneLeadsStream) {
      flushThinking();
    }

    if (ev.type === 'parameter_request' || ev.type === 'decision_request') {
      flushTools();
      invokeEndOrphanCandidateIdx = null;
      blocks.push({
        kind: 'hitl_slot',
        slotType: ev.type as 'parameter_request' | 'decision_request',
        eventParameterRequests:
          ev.type === 'parameter_request' && Array.isArray(ev.parameterRequests)
            ? ev.parameterRequests
            : undefined,
        eventPrompt:
          ev.type === 'parameter_request' && typeof ev.detail === 'string'
            ? ev.detail
            : undefined,
        eventDecision:
          ev.type === 'decision_request' && ev.decision
            ? ev.decision
            : undefined,
      });
      continue;
    }

    if (ev.type === 'step') {
      flushTools();
      invokeEndOrphanCandidateIdx = null;
      const sid = String(ev.id ?? '');
      if (ADAPTER_STEP_IDS_SKIP.has(sid)) continue;
      const isSubagentTask = sid.startsWith('task-running-');
      const ext = ev as TimelineEntryExt;
      const phaseId =
        ev.phaseId != null && String(ev.phaseId).trim() !== '' ? String(ev.phaseId) : undefined;
      blocks.push({
        kind: 'step',
        stepVariant: isSubagentTask ? 'subagent_task' : 'generic',
        label: String(ev.label ?? ev.detail ?? 'Step'),
        detail: ev.detail ? String(ev.detail) : undefined,
        status: ev.status != null ? String(ev.status) : undefined,
        phaseId,
        subagentDurationSec: ext.mergeSubagentDurationSec,
      });
      if (milestoneLeadsStream) {
        flushThinking();
      }
      continue;
    }

    if (ev.type === 'tool_call') {
      const pres = effectiveToolPresentation(ev);
      if (ev.toolName === 'write_todos' || pres === 'task') {
        flushTools();
        const todos = parseTodosFromWriteTodos(ev);
        if (todos) upsertTaskList(listBucketKey(ev), todos);
        continue;
      }
      if (pres === 'research_task' || ev.toolName === 'ConductResearch') {
        flushTools();
        const toolCallId = String(ev.id ?? '');
        if (!toolCallId) {
          continue;
        }
        const inp = (ev.toolInput as Record<string, unknown>) || {};
        const rawTitle = String(inp.research_topic ?? '').trim();
        const t = getTranslations(language);
        const titleBase = rawTitle || t.reasoning.researchTopicPending;
        if (titleBase) {
          const key = researchTaskBucketKey(ev);
          const title =
            titleBase.length > 2000 ? `${titleBase.slice(0, 2000)}…` : titleBase;
          const idx = blocks.findIndex(
            (b) => b.kind === 'task_list' && b.bucketKey === key,
          );
          if (idx >= 0) {
            const existing = blocks[idx] as ReActTaskListBlock;
            const hit = existing.items.find((it) => it.id === toolCallId);
            if (hit) {
              if (rawTitle && title !== hit.title) hit.title = title;
            } else {
              invokeEndOrphanCandidateIdx = null;
              blocks[idx] = {
                ...existing,
                listVariant: 'research',
                items: [...existing.items, { id: toolCallId, title, done: false }],
              };
            }
          } else {
            invokeEndOrphanCandidateIdx = null;
            blocks.push({
              kind: 'task_list',
              bucketKey: key,
              listVariant: 'research',
              items: [{ id: toolCallId, title, done: false }],
            });
          }
        }
        continue;
      }
      if (pres === 'action' || pres === 'parameter') {
        invokeEndOrphanCandidateIdx = null;
        const name = String(ev.toolName ?? '');
        const inp = (ev.toolInput as Record<string, unknown>) || {};
        if (name === 'read_file') {
          const filePath = readFilePathFromInput(inp);
          if (filePath && filePath === lastReadFilePath) {
            continue;
          }
          lastReadFilePath = filePath || null;
        } else {
          lastReadFilePath = null;
        }
        const short = compactToolRowLabel(name) || name;
        const detail = pickToolDetail(inp);
        const toolCallId = String(ev.id ?? `call-${ev.seq}`);
        toolChildren.push({ toolCallId, toolName: short, detail, done: false });
        continue;
      }
      continue;
    }

    if (ev.type === 'tool_result') {
      const rid = String(ev.id ?? '');
      if (
        rid &&
        (effectiveToolPresentation(ev) === 'research_task' ||
          ev.toolName === 'ConductResearch')
      ) {
        const key = researchTaskBucketKey(ev);
        for (const b of blocks) {
          if (b.kind !== 'task_list' || b.bucketKey !== key) continue;
          const row = b.items.find((it) => it.id === rid);
          if (row) {
            row.done = true;
            break;
          }
        }
      }
      const rawOutput = ev.toolOutput != null
        ? (typeof ev.toolOutput === 'string' ? ev.toolOutput : JSON.stringify(ev.toolOutput))
        : undefined;
      const isError = String(ev.status ?? '') === 'error';
      if (rid) markToolCallDone(rid, rawOutput?.trim() || undefined, isError || undefined);
      continue;
    }

    if (ev.type === 'task_summary' && typeof ev.summary === 'string' && ev.summary.trim()) {
      flushTools();
      invokeEndOrphanCandidateIdx = null;
      blocks.push({ kind: 'result', summary: ev.summary.trim() });
      continue;
    }
  }

  if (invokeOpen) {
    flushThinking({ allowEmpty: true, invokeState: 'running', invokeStartMs: invokeStartTs });
  } else {
    flushThinking();
  }
  flushTools();
  return swapPhaseSlotStepBeforeAdjacentThinking(coalesceThinkingBlocksAcrossTools(blocks));
}
