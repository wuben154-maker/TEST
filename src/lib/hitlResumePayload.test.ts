import { describe, expect, it } from 'vitest';
import type { AnalysisTimelineEntry } from '@/types/analysis';
import {
  buildHitlResumeFromDecision,
  buildLangChainHitlResumePayload,
  findDecisionRequestTimelineEntry,
} from '@/lib/hitlResumePayload';

describe('findDecisionRequestTimelineEntry', () => {
  it('returns the latest matching decision_request row', () => {
    const tl = [
      { type: 'step', seq: 1, id: 's' },
      {
        type: 'decision_request',
        seq: 2,
        id: 'dr1',
        interruptKind: 'langchain_hitl_v1',
        decision: { id: 'dec-a', question: 'q', options: [] },
        hitlRequest: { action_requests: [], review_configs: [] },
      },
    ] as AnalysisTimelineEntry[];
    expect(findDecisionRequestTimelineEntry(tl, 'dec-a')?.seq).toBe(2);
    expect(findDecisionRequestTimelineEntry(tl, 'missing')).toBeUndefined();
  });
});

describe('buildLangChainHitlResumePayload', () => {
  it('maps approve/reject for empty action_requests fallback', () => {
    expect(buildLangChainHitlResumePayload({ action_requests: [] }, ['approve'])).toEqual({
      decisions: [{ type: 'approve' }],
    });
    expect(buildLangChainHitlResumePayload({ action_requests: [] }, ['reject'])).toEqual({
      decisions: [{ type: 'reject' }],
    });
  });

  it('maps hitl-action-N indices to per-action approve/reject', () => {
    const hitl = {
      action_requests: [{ name: 'a' }, { name: 'b' }],
      review_configs: [],
    };
    expect(buildLangChainHitlResumePayload(hitl, ['hitl-action-0'])).toEqual({
      decisions: [{ type: 'approve' }, { type: 'reject' }],
    });
    expect(buildLangChainHitlResumePayload(hitl, ['hitl-action-0', 'hitl-action-1'])).toEqual({
      decisions: [{ type: 'approve' }, { type: 'approve' }],
    });
  });
});

describe('buildHitlResumeFromDecision', () => {
  it('builds LangChain decisions from timeline', () => {
    const tl = [
      {
        type: 'decision_request',
        seq: 1,
        id: 'x',
        interruptKind: 'langchain_hitl_v1',
        decision: { id: 'dec1', question: 'q', options: [{ id: 'approve', label: 'OK' }] },
        hitlRequest: { action_requests: [{}], review_configs: [] },
      },
    ] as AnalysisTimelineEntry[];
    expect(buildHitlResumeFromDecision(tl, 'dec1', ['approve'])).toEqual({ decisions: [{ type: 'approve' }] });
  });

  it('builds user_input_v1 choice response', () => {
    const tl = [
      {
        type: 'decision_request',
        seq: 1,
        id: 'rid-1',
        requestId: 'rid-1',
        interruptKind: 'user_input_v1',
        userInputKind: 'choice' as const,
        decision: {
          id: 'rid-1',
          question: 'Pick',
          options: [
            { id: '0', label: 'Alpha' },
            { id: '1', label: 'Beta' },
          ],
        },
      },
    ] as AnalysisTimelineEntry[];
    expect(buildHitlResumeFromDecision(tl, 'rid-1', ['1'])).toEqual({
      response: 'Beta',
      requestId: 'rid-1',
    });
  });
});
