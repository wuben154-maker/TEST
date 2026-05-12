/**
 * Derive live HITL UI state from a persisted SSE timeline (refresh / progress restore).
 */
import type {
  AnalysisTimelineEntry,
  DecisionRequest,
  ParameterRequest,
} from '@/types/analysis';

export type HitlRestoreFromTimeline = {
  /** True only when the graph is paused at a terminal ``done`` with ``awaitingHuman`` (no later events). */
  hitlAwaiting: boolean;
  /** User submitted HITL input and the stream continued — show read-only form + analyzing UI. */
  hitlResumeInFlight: boolean;
  hitlSnapshot: { interruptIds?: string[] } | null;
  parameterRequests: ParameterRequest[];
  parameterRequestDetail?: string;
  decisions: DecisionRequest[];
  /** Filled from persisted ``parameter_response`` rows (DB timeline) after resume — survives refresh without sessionStorage. */
  submittedParametersFromTimeline: Record<string, string>;
  /** Filled from persisted ``decision_response`` rows after resume (choice HITL). */
  resolvedDecisionsFromTimeline: Record<string, string[]>;
};

function emptyHitl(): HitlRestoreFromTimeline {
  return {
    hitlAwaiting: false,
    hitlResumeInFlight: false,
    hitlSnapshot: null,
    parameterRequests: [],
    parameterRequestDetail: undefined,
    decisions: [],
    submittedParametersFromTimeline: {},
    resolvedDecisionsFromTimeline: {},
  };
}

function collectParameterResponsesAfterPause(
  timeline: readonly AnalysisTimelineEntry[],
  pauseDoneIndex: number,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (let i = pauseDoneIndex + 1; i < timeline.length; i++) {
    const e = timeline[i];
    if (e?.type !== 'parameter_response') continue;
    const raw = e.parameters;
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      out[String(k)] = v == null ? '' : String(v);
    }
  }
  return out;
}

function collectDecisionResponsesAfterPause(
  timeline: readonly AnalysisTimelineEntry[],
  pauseDoneIndex: number,
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (let i = pauseDoneIndex + 1; i < timeline.length; i++) {
    const e = timeline[i];
    if (e?.type !== 'decision_response') continue;
    const id = e.decisionUiId != null ? String(e.decisionUiId) : '';
    const opts = e.selectedOptions;
    if (!id || !Array.isArray(opts)) continue;
    out[id] = opts.map((x) => String(x ?? ''));
  }
  return out;
}

/**
 * Read HITL flags and pending form/decision state from canonical timeline rows.
 *
 * Finds the **last** ``done`` row with ``awaitingHuman === true``.
 * - If it is the final event → graph is paused (``hitlAwaiting``).
 * - If later events follow → user submitted and the stream continued (``hitlResumeInFlight``),
 *   including the case where the analysis completed with a trailing ``done(awaitingHuman=false)``.
 *   This keeps HITL forms visible in read-only mode for completed conversation replay.
 */
export function extractHitlUiStateFromTimeline(
  timeline: readonly AnalysisTimelineEntry[],
): HitlRestoreFromTimeline {
  // Find the last `done` with `awaitingHuman` — not just the last `done`.
  // A completed turn may end with `done(awaitingHuman=false)` after the HITL
  // interaction finished; the HITL pause `done` sits earlier in the timeline.
  let lastDoneIdx = -1;
  for (let i = timeline.length - 1; i >= 0; i--) {
    if (timeline[i]?.type === 'done' && timeline[i]?.awaitingHuman === true) {
      lastDoneIdx = i;
      break;
    }
  }

  if (lastDoneIdx < 0) {
    return emptyHitl();
  }

  const lastDone = timeline[lastDoneIdx]!;

  const hasTailAfterPause = lastDoneIdx < timeline.length - 1;
  const hitlAwaiting = !hasTailAfterPause;
  const hitlResumeInFlight = hasTailAfterPause;

  let hitlSnapshot: { interruptIds?: string[] } | null = null;
  const h = lastDone.hitl as { interruptIds?: unknown } | undefined;
  if (h && typeof h === 'object' && Array.isArray(h.interruptIds)) {
    hitlSnapshot = { interruptIds: h.interruptIds.map(String) };
  }

  const prefix = timeline.slice(0, lastDoneIdx);
  let parameterRequests: ParameterRequest[] = [];
  let parameterRequestDetail: string | undefined;
  for (let i = prefix.length - 1; i >= 0; i--) {
    const e = prefix[i];
    if (e?.type === 'parameter_request') {
      const pr = e.parameterRequests;
      if (Array.isArray(pr) && pr.length > 0) {
        parameterRequests = pr as ParameterRequest[];
        parameterRequestDetail = typeof e.detail === 'string' ? e.detail : undefined;
        break;
      }
    }
  }

  let decisions: DecisionRequest[] = [];
  for (let i = prefix.length - 1; i >= 0; i--) {
    const e = prefix[i];
    if (e?.type === 'decision_request' && e.decision && typeof e.decision === 'object') {
      decisions = [e.decision as DecisionRequest];
      break;
    }
  }

  const submittedParametersFromTimeline = hitlResumeInFlight
    ? collectParameterResponsesAfterPause(timeline, lastDoneIdx)
    : {};
  const resolvedDecisionsFromTimeline = hitlResumeInFlight
    ? collectDecisionResponsesAfterPause(timeline, lastDoneIdx)
    : {};

  return {
    hitlAwaiting,
    hitlResumeInFlight,
    hitlSnapshot,
    parameterRequests,
    parameterRequestDetail,
    decisions,
    submittedParametersFromTimeline,
    resolvedDecisionsFromTimeline,
  };
}
