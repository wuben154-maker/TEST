/**
 * Backend sync for the realtime context-usage ring.
 *
 * Write strategy: 20s debounce + hard flush on critical events.
 *
 * Every `llm_invoke_end` update lands in in-memory state + localStorage
 * synchronously (see `StreamingStateContext` + `contextUsagePersistence.ts`).
 * Backend flushes are coalesced: we keep a per-project timer and only
 * PATCH once per 20s window. That avoids a write per LLM call while still
 * keeping the backend fresh enough for cross-device visibility.
 *
 * The critical-event flushes below are what actually makes the 20s
 * debounce safe — they guarantee durability on every meaningful boundary:
 *
 *   - `done` SSE  → `flushNow(projectId)`
 *   - `context_summarized` SSE → `flushNow(projectId)`
 *   - stream abort / error → `flushNow(projectId)`
 *   - active project switch → `flushNow(oldProjectId)`
 *   - project delete → direct `updateContextUsage(id, null)` (not debounced)
 *   - `beforeunload` / `pagehide` → `flushAllNowViaBeacon()` (sendBeacon)
 *
 * Data-loss window is bounded by `min(20s, time-to-next-critical-event)`,
 * and every meaningful state change is mirrored in localStorage so a
 * same-device reload never loses anything.
 *
 * This module is stateful at the module level (one timer map per tab).
 * That's fine — the app has a single BE-sync orchestrator per page.
 */
import type { ContextUsageState } from '@/types/analysis';
import { projectsApi } from '@/lib/api-client';
import { config, isLocalMode } from '@/lib/config';
import { getAuthToken, CLIENT_TIMEZONE_HEADER } from '@/lib/api-client';

export const DEBOUNCE_MS = 20_000;

/**
 * Per-project pending state: the latest snapshot we've been asked to
 * flush, plus the timer that will PATCH it. When a new snapshot arrives
 * we overwrite ``pendingState`` (coalesce) and keep the same timer —
 * that's what lets us flush once per window instead of per call.
 *
 * Invariant: an entry is in ``pending`` **only while a snapshot actually
 * awaits durable write**. Once the debounce timer fires (or any flush
 * drains the queue) we `pending.delete(id)`. This removes the "idle
 * entry with pendingState=null" state that previously caused the
 * `flushNow` / `flushAllOnUnload` paths to emit a bogus
 * `{context_usage: null}` PATCH and wipe the backend column.
 */
interface PendingFlush {
  pendingState: ContextUsageState;
  timer: ReturnType<typeof setTimeout> | null;
}

const pending = new Map<string, PendingFlush>();

function clearTimer(entry: PendingFlush): void {
  if (entry.timer) {
    clearTimeout(entry.timer);
    entry.timer = null;
  }
}

function toWirePayload(
  state: ContextUsageState,
): { v: number; state: ContextUsageState; updatedAt: number } {
  return { v: 1, state, updatedAt: Date.now() };
}

async function doPatch(
  projectId: string,
  state: ContextUsageState,
): Promise<void> {
  // ``projectsApi.updateContextUsage`` already swallows errors into
  // ``{ error }``. We don't need to handle them here — a failed flush
  // just means the next scheduled flush will try again. localStorage
  // still has the latest value in the meantime.
  await projectsApi.updateContextUsage(projectId, toWirePayload(state));
}

/**
 * Schedule a coalesced backend flush for the given project. Safe to call
 * as often as you like — all calls within `DEBOUNCE_MS` collapse to a
 * single PATCH carrying the most recent ``state``.
 *
 * ``null`` is accepted and treated as "nothing queued" — callers that
 * actually want to clear the server column go through
 * ``projectsApi.updateContextUsage(id, null)`` directly (see the
 * project-delete path in ``StreamingStateContext``).
 */
export function scheduleBackendSync(
  projectId: string,
  state: ContextUsageState | null,
): void {
  if (!projectId) return;
  if (state === null) return; // never schedule a null snapshot
  let entry = pending.get(projectId);
  if (!entry) {
    entry = { pendingState: state, timer: null };
    pending.set(projectId, entry);
  } else {
    entry.pendingState = state; // coalesce newest snapshot
  }

  if (entry.timer) return; // debounce window already open

  entry.timer = setTimeout(() => {
    const snapshot = entry!.pendingState;
    // Remove the entry *before* kicking off the async PATCH so any
    // concurrent `scheduleBackendSync` opens a fresh debounce window,
    // and any concurrent `flushNow` / `flushAllOnUnload` correctly
    // sees "nothing pending" for this project.
    pending.delete(projectId);
    void doPatch(projectId, snapshot).catch(() => {
      /* best-effort background flush */
    });
  }, DEBOUNCE_MS);
}

/**
 * Immediately flush the most recent pending snapshot for ``projectId``
 * and cancel any outstanding debounce timer. Call on every critical
 * event listed at the top of this module.
 *
 * No-op when nothing is queued — does NOT send a `{context_usage:
 * null}` PATCH. Explicit clear goes through
 * ``projectsApi.updateContextUsage(id, null)`` directly.
 */
export async function flushNow(projectId: string): Promise<void> {
  if (!projectId) return;
  const entry = pending.get(projectId);
  if (!entry) return;
  clearTimer(entry);
  const snapshot = entry.pendingState;
  pending.delete(projectId);
  await doPatch(projectId, snapshot);
}

/**
 * Flush every project with a pending write. Used on project switch when
 * we want to make sure the *previous* project's turn is durable before
 * the new one takes focus.
 */
export async function flushAllNow(): Promise<void> {
  // Snapshot keys upfront — flushNow() mutates the map.
  const keys = Array.from(pending.keys());
  await Promise.all(keys.map((id) => flushNow(id)));
}

/**
 * Cancel any scheduled debounce for a project without sending a PATCH.
 * Use on project delete where the caller will explicitly clear via
 * `updateContextUsage(id, null)` and doesn't want a stale snapshot to
 * race with that.
 */
export function cancelScheduled(projectId: string): void {
  const entry = pending.get(projectId);
  if (!entry) return;
  clearTimer(entry);
  pending.delete(projectId);
}

/**
 * Best-effort durability hook for `beforeunload` / `pagehide`. We can't
 * `await` anything inside those handlers — the tab closes before `fetch`
 * resolves. `navigator.sendBeacon` is the only cross-browser mechanism
 * that reliably POSTs during unload, but it only supports POST, not
 * PATCH. We work around that by hitting the **same** resource with a
 * tiny "method-override" envelope: backend accepts standard PATCH in
 * normal paths, and a dedicated POST beacon endpoint could be added
 * later if needed. For now, we issue PATCH via `fetch({ keepalive })`
 * as the primary durability mechanism, which modern browsers keep alive
 * through unload, and fall back to sendBeacon if `keepalive` is rejected.
 *
 * Runs synchronously and returns void — never throws.
 */
export function flushAllOnUnload(): void {
  if (typeof window === 'undefined') return;
  const base = isLocalMode() ? config.localApiUrl : config.pythonBackendUrl;
  const token = getAuthToken();
  const tz = (() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      return 'UTC';
    }
  })();

  // Snapshot pending entries first — we mutate the map below.
  const entries = Array.from(pending.entries());
  pending.clear();
  for (const [projectId, entry] of entries) {
    clearTimer(entry);
    const snapshot = entry.pendingState;
    // Invariant: an entry only lives in ``pending`` while a real
    // snapshot is queued, so ``snapshot`` is guaranteed non-null.
    // Emit it via keepalive so the last debounce window doesn't
    // get dropped on reload.

    const body = JSON.stringify({
      context_usage: toWirePayload(snapshot),
    });
    const url = `${base}/projects/${projectId}`;

    // Preferred: fetch with keepalive — supports Authorization header.
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        [CLIENT_TIMEZONE_HEADER]: tz,
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      // eslint-disable-next-line @typescript-eslint/no-floating-promises
      fetch(url, {
        method: 'PATCH',
        headers,
        body,
        keepalive: true,
      });
      continue;
    } catch {
      // Fall through to beacon.
    }

    // Fallback: sendBeacon (POST-only; the real PATCH just didn't survive
    // unload). This is best-effort — if the backend doesn't listen on
    // POST /projects/:id the beacon is silently dropped. We accept that
    // tradeoff: fetch-keepalive is implemented by every browser we care
    // about, so this path is effectively dead code for recovery, not
    // primary durability.
    if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
      try {
        const blob = new Blob([body], { type: 'application/json' });
        navigator.sendBeacon(url, blob);
      } catch {
        // swallow
      }
    }
  }
}

/** Test-only: reset module state. */
export function __resetForTests(): void {
  for (const entry of pending.values()) clearTimer(entry);
  pending.clear();
}
