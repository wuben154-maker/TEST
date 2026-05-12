import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type {
  PerProjectStreamingState,
} from '@/types/streaming';
import { createEmptyStreamingState } from '@/types/streaming';
import {
  saveContextUsage,
  clearContextUsage,
} from '@/lib/contextUsagePersistence';
import {
  scheduleBackendSync,
  cancelScheduled,
  flushAllOnUnload,
} from '@/lib/contextUsageSync';
import { projectsApi } from '@/lib/api-client';

type StateUpdater = (
  prev: PerProjectStreamingState
) => PerProjectStreamingState;

interface StreamingStateContextValue {
  getState: (projectId: string) => PerProjectStreamingState;
  /** Always returns the latest committed state regardless of closure age. Safe to call from long-running async functions. */
  getLatestState: (projectId: string) => PerProjectStreamingState;
  updateState: (projectId: string, updater: StateUpdater) => void;
  clearState: (projectId: string) => void;
  removeState: (projectId: string) => void;
  getAbortController: (projectId: string) => AbortController | null;
  setAbortController: (projectId: string, controller: AbortController | null) => void;
}

const StreamingStateContext = createContext<StreamingStateContextValue | null>(null);

export function StreamingStateProvider({ children }: { children: ReactNode }) {
  const [stateMap, setStateMap] = useState<Map<string, PerProjectStreamingState>>(new Map());
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  // Mirror of stateMap kept in a ref so long-running async functions can always read
  // the latest state without stale closure issues (ref is mutated synchronously inside
  // each setStateMap updater, before React schedules the re-render).
  const stateMapRef = useRef<Map<string, PerProjectStreamingState>>(new Map());

  const getState = useCallback((projectId: string): PerProjectStreamingState => {
    return stateMap.get(projectId) ?? createEmptyStreamingState();
  }, [stateMap]);

  // No dependency on stateMap closure — always reads the ref that is kept current.
  const getLatestState = useCallback((projectId: string): PerProjectStreamingState => {
    return stateMapRef.current.get(projectId) ?? createEmptyStreamingState();
  }, []);

  const updateState = useCallback((projectId: string, updater: StateUpdater) => {
    setStateMap((prev) => {
      const next = new Map(prev);
      const current = next.get(projectId) ?? createEmptyStreamingState();
      const updated = updater(current);
      next.set(projectId, updated);
      stateMapRef.current = next;
      // Side-effect: persist contextUsage whenever it changed. We compare by
      // reference first (cheap) — the reducer returns a new object on every
      // relevant event, so this is effectively "write on any usage change".
      // Writing to localStorage is sync but small; we also guard on empty
      // payloads inside saveContextUsage so idle → idle transitions are no-ops.
      if (current.contextUsage !== updated.contextUsage) {
        // Local hot-cache (fast, synchronous, survives hard reload on
        // same device).
        saveContextUsage(projectId, updated.contextUsage);
        // Authoritative source: schedule a coalesced backend PATCH.
        // Critical events (done / context_summarized / abort / project
        // switch / unload) bypass the debounce via flushNow() from the
        // streaming hook; this path just takes the slow-burst PATCHes.
        scheduleBackendSync(projectId, updated.contextUsage);
      }
      return next;
    });
  }, []);

  const clearState = useCallback((projectId: string) => {
    setStateMap((prev) => {
      const current = prev.get(projectId);
      // Don't overwrite if a new request is in progress (avoids clearing in-flight content)
      if (current?.isAnalyzing) return prev;
      const next = new Map(prev);
      const empty = createEmptyStreamingState();
      // Preserve sseEventLogs so the debug panel accumulates history across requests.
      // The user clears logs manually via the DevModePanel UI.
      // Preserve contextUsage so the realtime context-usage ring stays visible
      // after a turn ends — the ring must not disappear just because the live
      // panel was reset (see requirement "有数据后就要考虑持久化不能消失").
      next.set(projectId, {
        ...empty,
        sseEventLogs: current?.sseEventLogs ?? [],
        contextUsage: current?.contextUsage ?? empty.contextUsage,
      });
      stateMapRef.current = next;
      return next;
    });
  }, []);

  const removeState = useCallback((projectId: string) => {
    const controller = abortControllersRef.current.get(projectId);
    if (controller) {
      controller.abort();
      abortControllersRef.current.delete(projectId);
    }
    setStateMap((prev) => {
      const next = new Map(prev);
      next.delete(projectId);
      stateMapRef.current = next;
      return next;
    });
    // Project deleted → drop its persisted context-usage entry too.
    clearContextUsage(projectId);
    // Cancel any in-flight debounce so a stale snapshot can't race the
    // server-side cascade, then proactively clear the backend column as
    // defence-in-depth (the cascade handles the row drop, but columns on
    // other rows won't get touched automatically in partial-delete
    // scenarios).
    cancelScheduled(projectId);
    void projectsApi.updateContextUsage(projectId, null);
  }, []);

  // Install a global ``pagehide`` listener so any in-flight 20s debounce
  // still lands on the backend when the user closes the tab or hard-
  // navigates away. Covers the "reload mid-turn" scenario the user
  // explicitly asked about (data-loss window ≤ 20s on same-device).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handler = () => flushAllOnUnload();
    window.addEventListener('pagehide', handler);
    window.addEventListener('beforeunload', handler);
    return () => {
      window.removeEventListener('pagehide', handler);
      window.removeEventListener('beforeunload', handler);
    };
  }, []);

  const getAbortController = useCallback((projectId: string) => {
    return abortControllersRef.current.get(projectId) ?? null;
  }, []);

  const setAbortController = useCallback((projectId: string, controller: AbortController | null) => {
    const prev = abortControllersRef.current.get(projectId);
    if (prev) prev.abort();
    if (controller) {
      abortControllersRef.current.set(projectId, controller);
    } else {
      abortControllersRef.current.delete(projectId);
    }
  }, []);

  const value: StreamingStateContextValue = {
    getState,
    getLatestState,
    updateState,
    clearState,
    removeState,
    getAbortController,
    setAbortController,
  };

  return (
    <StreamingStateContext.Provider value={value}>
      {children}
    </StreamingStateContext.Provider>
  );
}

export function useStreamingStateContext(): StreamingStateContextValue {
  const ctx = useContext(StreamingStateContext);
  if (!ctx) {
    throw new Error('useStreamingStateContext must be used within StreamingStateProvider');
  }
  return ctx;
}
