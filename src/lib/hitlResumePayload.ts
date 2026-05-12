/**
 * Build LangGraph / LangChain HITL resume payloads from UI decision selections.
 */
import type { AnalysisTimelineEntry, DecisionRequest } from '@/types/analysis';

function asRecord(v: unknown): Record<string, unknown> | null {
  return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

/**
 * Find the timeline row for a UserDecision ``request.id`` (matches SSE ``decision.id``).
 */
export function findDecisionRequestTimelineEntry(
  timeline: readonly AnalysisTimelineEntry[],
  decisionUiId: string,
): AnalysisTimelineEntry | undefined {
  const want = String(decisionUiId);
  for (let i = timeline.length - 1; i >= 0; i--) {
    const e = timeline[i];
    if (!e || e.type !== 'decision_request') continue;
    const d = asRecord(e.decision);
    if (d && String(d.id ?? '') === want) return e;
  }
  return undefined;
}

/**
 * Map LangChain HITLRequest + selected option ids to ``{ decisions: [...] }``.
 */
export function buildLangChainHitlResumePayload(
  hitlRequest: Record<string, unknown>,
  selectedOptionIds: string[],
): { decisions: Array<Record<string, unknown>> } {
  const actions = hitlRequest.action_requests;
  const n = Array.isArray(actions) ? actions.length : 0;
  const selected = new Set(selectedOptionIds.map((s) => String(s)));

  if (n === 0) {
    const first = selectedOptionIds[0] ? String(selectedOptionIds[0]) : 'approve';
    if (first === 'reject') {
      return { decisions: [{ type: 'reject' }] };
    }
    return { decisions: [{ type: 'approve' }] };
  }

  const fromHitlAction = new Set<number>();
  for (const sid of selected) {
    const m = /^hitl-action-(\d+)$/.exec(sid);
    if (m) fromHitlAction.add(parseInt(m[1], 10));
  }

  if (fromHitlAction.size > 0) {
    const decisions: Array<Record<string, unknown>> = [];
    for (let i = 0; i < n; i++) {
      decisions.push(fromHitlAction.has(i) ? { type: 'approve' } : { type: 'reject' });
    }
    return { decisions };
  }

  const first = selectedOptionIds[0] ? String(selectedOptionIds[0]) : '';
  if (first === 'reject' || selected.has('reject')) {
    return { decisions: Array.from({ length: n }, () => ({ type: 'reject' })) };
  }
  return { decisions: Array.from({ length: n }, () => ({ type: 'approve' })) };
}

/**
 * Map ``user_input_v1`` choice selection to resume object (tool expects ``response``).
 */
export function buildUserInputChoiceResumePayload(
  decision: DecisionRequest,
  selectedOptionIds: string[],
  requestIdFromEvent?: string,
): Record<string, unknown> {
  const firstId = selectedOptionIds[0] != null ? String(selectedOptionIds[0]) : '';
  const opt = decision.options.find((o) => String(o.id) === firstId);
  const label = opt?.label ?? firstId;
  const out: Record<string, unknown> = { response: label };
  if (requestIdFromEvent) out.requestId = requestIdFromEvent;
  return out;
}

/**
 * Build resume value for POST /analyze/resume from timeline context + UI selection.
 */
export function buildHitlResumeFromDecision(
  timeline: readonly AnalysisTimelineEntry[],
  decisionUiId: string,
  selectedOptionIds: string[],
  decisionFallback?: DecisionRequest,
): unknown {
  const entry = findDecisionRequestTimelineEntry(timeline, decisionUiId);
  const interruptKind = entry ? String(entry.interruptKind ?? '') : '';
  const hitlRaw = entry ? asRecord(entry.hitlRequest) : null;

  if (interruptKind === 'langchain_hitl_v1' && hitlRaw) {
    return buildLangChainHitlResumePayload(hitlRaw, selectedOptionIds);
  }

  if (interruptKind === 'user_input_v1' && entry?.userInputKind === 'choice') {
    const d = (entry.decision as DecisionRequest) || decisionFallback;
    if (!d || !Array.isArray(d.options)) {
      return { response: selectedOptionIds[0] != null ? String(selectedOptionIds[0]) : '' };
    }
    const rid = entry.requestId != null ? String(entry.requestId) : entry.id != null ? String(entry.id) : undefined;
    return buildUserInputChoiceResumePayload(d, selectedOptionIds, rid);
  }

  // Raw / unknown: pass structured reply like parameter path
  const rid = entry?.requestId != null ? String(entry.requestId) : entry?.id != null ? String(entry.id) : undefined;
  const first = selectedOptionIds[0] != null ? String(selectedOptionIds[0]) : '';
  return {
    response: first,
    ...(rid ? { requestId: rid } : {}),
  };
}
