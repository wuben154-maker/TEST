/**
 * Pure reducers for the realtime context-usage indicator.
 *
 * Consumed by `useStreamingAnalysis` (and its multi-stream variant) to aggregate
 * `llm_invoke_start` / `llm_invoke_end` / `context_summarized` events into a
 * `ContextUsageState` for the `<ContextUsageBadge />` in the chat composer.
 *
 * See: docs/Process/realtime-context-usage-indicator/design.md (§UI, §Contracts).
 */

import type {
  ContextUsageState,
  InvokeUsageSnapshot,
  SubagentUsageAggregate,
  ThinkingEvent,
} from '@/types/analysis';

export const MAIN_SUBAGENT_KEY = 'main';

export function createEmptyContextUsageState(): ContextUsageState {
  return {
    latest: undefined,
    latestMain: undefined,
    latestSubagentByName: {},
    cumulative: { inputTokens: 0, outputTokens: 0, invocations: 0 },
    bySubagent: [],
    lastSummarizedAt: undefined,
  };
}

/** Snapshot that drives the main ring vs the main model context window. */
export function getMainUsageSnapshot(
  state: ContextUsageState | undefined | null,
): InvokeUsageSnapshot | undefined {
  if (state == null) return undefined;
  return state.latestMain ?? state.latest;
}

interface InternalState extends ContextUsageState {
  /** invokeId -> modelId captured on start, applied when the matching end arrives. */
  pendingModelId: Map<string, string | undefined>;
  /** invokeId -> subagentName captured on start, applied when the matching end arrives. */
  pendingSubagent: Map<string, string>;
}

function toInternal(state: ContextUsageState): InternalState {
  const internal = state as InternalState;
  // ``pendingModelId`` / ``pendingSubagent`` are runtime-only correlation
  // caches (invokeId → modelId / subagent). They **must** be Map instances
  // because we call ``.set()`` / ``.get()`` on them. If the state just came
  // out of ``JSON.parse(localStorage)`` the Maps were serialized to ``{}``
  // and the ``!internal.pendingModelId`` guard alone is not enough — an
  // empty object is truthy yet lacks ``.set``. Always coerce to Map.
  if (!(internal.pendingModelId instanceof Map)) internal.pendingModelId = new Map();
  if (!(internal.pendingSubagent instanceof Map)) internal.pendingSubagent = new Map();
  return internal;
}

function bucketFor(state: InternalState, subagentName: string): SubagentUsageAggregate {
  const existing = state.bySubagent.find((b) => b.subagentName === subagentName);
  if (existing) return existing;
  const fresh: SubagentUsageAggregate = {
    subagentName,
    invocations: 0,
    inputTokens: 0,
    outputTokens: 0,
  };
  state.bySubagent = [...state.bySubagent, fresh];
  return fresh;
}

/**
 * Apply one SSE event and return a **new** `ContextUsageState`.
 * Pure — safe to call from a React reducer or a `useRef`-held mutable aggregator.
 */
export function applyEventToContextUsage(
  prev: ContextUsageState,
  event: ThinkingEvent,
): ContextUsageState {
  const state = toInternal({
    ...prev,
    bySubagent: [...prev.bySubagent],
    latestSubagentByName: { ...(prev.latestSubagentByName ?? {}) },
  });

  if (event.type === 'llm_invoke_start') {
    const iid = event.invokeId ?? event.id;
    if (!iid) return prev;
    if (event.modelId) {
      state.pendingModelId.set(iid, event.modelId);
    }
    const subagent = event.scope === 'subagent'
      ? (event.subagentName || 'subagent')
      : MAIN_SUBAGENT_KEY;
    state.pendingSubagent.set(iid, subagent);
    return state;
  }

  if (event.type === 'llm_invoke_end') {
    const iid = event.invokeId ?? event.id;
    if (!iid) return prev;
    const usage = event.usage;
    // Usage may be omitted on legacy events — skip rather than pollute state.
    if (!usage) {
      state.pendingModelId.delete(iid);
      state.pendingSubagent.delete(iid);
      return state;
    }

    const inputTokens = Math.max(0, Number(usage.inputTokens) || 0);
    const outputTokens = Math.max(0, Number(usage.outputTokens) || 0);
    const modelId =
      state.pendingModelId.get(iid) ?? prev.latestMain?.modelId ?? prev.latest?.modelId;
    const subagent = state.pendingSubagent.get(iid)
      ?? (event.scope === 'subagent' ? (event.subagentName || 'subagent') : MAIN_SUBAGENT_KEY);
    state.pendingModelId.delete(iid);
    state.pendingSubagent.delete(iid);

    const snapshot: InvokeUsageSnapshot = {
      invokeId: iid,
      modelId,
      inputTokens,
      outputTokens,
      endedAt: typeof event.timestamp === 'number' ? event.timestamp : Date.now(),
    };

    if (subagent === MAIN_SUBAGENT_KEY) {
      state.latestMain = snapshot;
      state.latest = snapshot;
    } else {
      state.latestSubagentByName[subagent] = snapshot;
    }
    state.cumulative = {
      inputTokens: prev.cumulative.inputTokens + inputTokens,
      outputTokens: prev.cumulative.outputTokens + outputTokens,
      invocations: prev.cumulative.invocations + 1,
    };

    const bucket = bucketFor(state, subagent);
    bucket.invocations += 1;
    bucket.inputTokens += inputTokens;
    bucket.outputTokens += outputTokens;
    return state;
  }

  if (event.type === 'context_summarized') {
    // Option A (context-summarization-usage-orchestration): main ring numerator is
    // only valid until the next `llm_invoke_end`. After server-side compression,
    // stale high `latestMain` would lie — clear until the next main measurement.
    state.lastSummarizedAt = typeof event.timestamp === 'number' ? event.timestamp : Date.now();
    state.latestMain = undefined;
    state.latest = undefined;
    return state;
  }

  return prev;
}

/**
 * Derive the indicator percentage and severity bucket for a given context window.
 * Uses **prompt / input tokens only** from the last main-scoped invoke vs the
 * main model window (output is not part of the pre-filled context budget).
 * Returns `null` when we have no main completed invocation yet (badge hidden).
 */
export type IndicatorSeverity = 'idle' | 'safe' | 'warn' | 'danger' | 'critical';

export function deriveIndicator(
  state: ContextUsageState,
  contextWindow: number | undefined,
): {
  percent: number;
  /** Input (prompt) tokens for the last main invoke — same units as the ring. */
  tokens: number;
  severity: IndicatorSeverity;
} | null {
  const main = getMainUsageSnapshot(state);
  if (!main || !contextWindow || contextWindow <= 0) {
    return null;
  }
  const tokens = Math.max(0, main.inputTokens);
  const percent = Math.min(100, Math.max(0, (tokens / contextWindow) * 100));
  let severity: Exclude<IndicatorSeverity, 'idle'> = 'safe';
  if (percent >= 95) severity = 'critical';
  else if (percent >= 90) severity = 'danger';
  else if (percent >= 70) severity = 'warn';
  return { percent, tokens, severity };
}

/** Subagent row: last prompt (input) vs that subagent run’s model context window. */
export function deriveSubagentPromptIndicator(
  snapshot: InvokeUsageSnapshot | undefined,
  contextWindow: number | undefined,
): { percent: number; tokens: number } | null {
  if (!snapshot || !contextWindow || contextWindow <= 0) return null;
  const tokens = Math.max(0, snapshot.inputTokens);
  const percent = Math.min(100, Math.max(0, (tokens / contextWindow) * 100));
  return { percent, tokens };
}

/**
 * Pick the newer of two context-usage sources (localStorage vs backend).
 *
 * Used on project hydration to decide which snapshot seeds in-memory
 * state. Policy:
 *
 *   - If both sources carry data → winner = the one with the larger
 *     ``updatedAt``. Ties go to ``backend`` because it's authoritative
 *     (server-stamped second precision means ms-epoch ties are almost
 *     always a sign that backend was written "just now" as well).
 *   - If only one source has data → that one wins.
 *   - If neither has data → returns ``null`` (ring stays hidden).
 *
 * ``updatedAt`` values are epoch ms; missing / zero means "very old"
 * and loses against any positive timestamp. This lets legacy local-
 * storage entries (pre-2026-04-19 increment, no ``updatedAt`` key) be
 * superseded by any backend write.
 */
export function pickNewerContextUsage(
  local: { state: ContextUsageState; updatedAt: number } | null,
  backend: { state: ContextUsageState; updatedAt: number } | null,
): { state: ContextUsageState; source: 'local' | 'backend' } | null {
  const hasLocal = !!local?.state;
  const hasBackend = !!backend?.state;
  if (!hasLocal && !hasBackend) return null;
  if (!hasLocal) return { state: backend!.state, source: 'backend' };
  if (!hasBackend) return { state: local!.state, source: 'local' };
  // Tie-break: backend wins on equal timestamps.
  if (backend!.updatedAt >= local!.updatedAt) {
    return { state: backend!.state, source: 'backend' };
  }
  return { state: local!.state, source: 'local' };
}
