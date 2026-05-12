/**
 * Per-project persistence for `ContextUsageState` via localStorage.
 *
 * Rationale: the context-usage badge must NOT disappear after a page reload
 * (or across project switches). Streaming state is ephemeral (`useState` map
 * inside `StreamingStateContext`); the only source of truth that survives a
 * reload is localStorage. We scope everything by `projectId` so each project
 * keeps its own ring.
 *
 * Stored payload is versioned so we can evolve the schema without blowing up
 * old entries — invalid / unknown versions simply return `null`.
 */
import type { ContextUsageState } from '@/types/analysis';

const KEY_PREFIX = 'secmanus:context-usage:v1:';
const CURRENT_VERSION = 1;

/**
 * Wire + on-disk payload.
 *
 * ``updatedAt`` (epoch ms) is stamped every time the client writes — it
 * lets the hydrate path compare localStorage vs backend (which also
 * carries an ``updatedAt`` in its jsonb body and a server-stamped
 * ``context_usage_updated_at`` in the ``projects`` row) and pick the
 * newer source.
 *
 * The key is versioned (``v1``); bumping the version invalidates old
 * entries so schema evolution can never crash the UI.
 */
export interface StoredPayload {
  v: number;
  state: ContextUsageState;
  updatedAt: number;
}

function key(projectId: string): string {
  return `${KEY_PREFIX}${projectId}`;
}

function hasLocalStorage(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage;
}

function hasMeaningfulData(state: ContextUsageState): boolean {
  if (state.latestMain ?? state.latest) return true;
  if (state.latestSubagentByName && Object.keys(state.latestSubagentByName).length > 0) {
    return true;
  }
  if (state.cumulative && state.cumulative.invocations > 0) return true;
  if (state.bySubagent && state.bySubagent.length > 0) return true;
  return false;
}

/**
 * Persist a `ContextUsageState` for a project. No-op on SSR or when the
 * state is empty — an empty payload would overwrite a valid saved one and
 * defeat the "don't disappear" invariant the user asked for.
 */
export function saveContextUsage(
  projectId: string,
  state: ContextUsageState,
): void {
  if (!hasLocalStorage() || !projectId) return;
  try {
    if (!hasMeaningfulData(state)) return;
    // Strip runtime-only Map caches (``pendingModelId``, ``pendingSubagent``)
    // before serializing: ``JSON.stringify(Map)`` returns ``{}``, which then
    // fails the ``.set()`` call on next read because the guard in
    // ``toInternal`` treated ``{}`` as already-present. Persist only the
    // public shape — the caches are rebuilt on the fly from live events.
    const {
      // @ts-expect-error runtime-only fields from InternalState
      pendingModelId: _pm,
      // @ts-expect-error runtime-only fields from InternalState
      pendingSubagent: _ps,
      ...cleanState
    } = state as ContextUsageState & Record<string, unknown>;
    void _pm;
    void _ps;
    const payload: StoredPayload = {
      v: CURRENT_VERSION,
      state: cleanState as ContextUsageState,
      updatedAt: Date.now(),
    };
    window.localStorage.setItem(key(projectId), JSON.stringify(payload));
  } catch {
    // Quota exceeded / private-mode / corrupted storage — swallow silently.
  }
}

/**
 * Load a previously saved payload (state + updatedAt), or ``null`` if
 * absent / invalid. The caller uses ``updatedAt`` to diff against the
 * backend-side ``context_usage_updated_at`` on hydrate.
 */
export function loadContextUsagePayload(
  projectId: string,
): { state: ContextUsageState; updatedAt: number } | null {
  if (!hasLocalStorage() || !projectId) return null;
  try {
    const raw = window.localStorage.getItem(key(projectId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredPayload>;
    if (!parsed || parsed.v !== CURRENT_VERSION) return null;
    if (!parsed.state) return null;
    // Be defensive: ensure required shape keys exist even if the schema
    // shifted client-side.
    const state = parsed.state as ContextUsageState;
    if (!state.cumulative) return null;
    if (!Array.isArray(state.bySubagent)) return null;
    // Legacy entries (pre-2026-04-19 increment) lack ``updatedAt``; treat
    // them as "very old" so the backend always wins on hydrate when both
    // sources are present.
    const updatedAt =
      typeof parsed.updatedAt === 'number' && parsed.updatedAt > 0
        ? parsed.updatedAt
        : 0;
    return { state, updatedAt };
  } catch {
    return null;
  }
}

/**
 * Backwards-compatible: return just the ``ContextUsageState`` without the
 * timestamp. Retained because existing callers (`useStreamingAnalysisMulti`)
 * don't care about the stamp yet — the hydrate path that *does* care uses
 * ``loadContextUsagePayload`` directly.
 */
export function loadContextUsage(projectId: string): ContextUsageState | null {
  const payload = loadContextUsagePayload(projectId);
  return payload ? payload.state : null;
}

/** Remove persisted state for a project (called on project deletion). */
export function clearContextUsage(projectId: string): void {
  if (!hasLocalStorage() || !projectId) return;
  try {
    window.localStorage.removeItem(key(projectId));
  } catch {
    // intentionally empty
  }
}

/** Test-only: wipe every persisted entry under our prefix. */
export function clearAllContextUsage(): void {
  if (!hasLocalStorage()) return;
  try {
    const toRemove: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k && k.startsWith(KEY_PREFIX)) toRemove.push(k);
    }
    for (const k of toRemove) window.localStorage.removeItem(k);
  } catch {
    // intentionally empty
  }
}
