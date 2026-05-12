import { describe, expect, it } from 'vitest';
import type { AnalysisTimelineEntry } from '@/types/analysis';
import { extractHitlUiStateFromTimeline } from '@/lib/hitlRestoreFromTimeline';

describe('extractHitlUiStateFromTimeline', () => {
  it('detects awaitingHuman and extracts pending parameter + decision rows', () => {
    const timeline = [
      { type: 'parameter_request', seq: 1, id: 'p1', parameterRequests: [{ id: 'reply', name: 'reply', description: '', paramType: 'text', required: true, encrypted: false }], detail: 'Why?' },
      {
        type: 'decision_request',
        seq: 2,
        id: 'd1',
        decision: { id: 'd1', question: 'Pick', options: [{ id: 'a', label: 'A' }] },
      },
      { type: 'done', seq: 3, id: 'done', awaitingHuman: true, hitl: { interruptIds: ['x'] } },
    ] as AnalysisTimelineEntry[];

    const h = extractHitlUiStateFromTimeline(timeline);
    expect(h.hitlAwaiting).toBe(true);
    expect(h.hitlResumeInFlight).toBe(false);
    expect(h.hitlSnapshot?.interruptIds).toEqual(['x']);
    expect(h.parameterRequests).toHaveLength(1);
    expect(h.parameterRequestDetail).toBe('Why?');
    expect(h.decisions).toHaveLength(1);
    expect(h.decisions[0]?.id).toBe('d1');
    expect(h.submittedParametersFromTimeline).toEqual({});
    expect(h.resolvedDecisionsFromTimeline).toEqual({});
  });

  it('returns empty HITL when no terminal done.awaitingHuman', () => {
    const h = extractHitlUiStateFromTimeline([{ type: 'step', seq: 1, id: 's' }] as AnalysisTimelineEntry[]);
    expect(h.hitlAwaiting).toBe(false);
    expect(h.hitlResumeInFlight).toBe(false);
    expect(h.decisions).toHaveLength(0);
    expect(h.submittedParametersFromTimeline).toEqual({});
    expect(h.resolvedDecisionsFromTimeline).toEqual({});
  });

  it('completed run after HITL still exposes form data as resume-in-flight for read-only replay', () => {
    const timeline = [
      { type: 'parameter_request', seq: 1, id: 'p1', parameterRequests: [{ id: 'reply', name: 'reply', description: '', paramType: 'text', required: true, encrypted: false }] },
      { type: 'done', seq: 2, id: 'd1', awaitingHuman: true, hitl: { interruptIds: ['x'] } },
      { type: 'step', seq: 3, id: 's2', label: 'Thought', status: 'running' },
      { type: 'done', seq: 4, id: 'd2', awaitingHuman: false },
    ] as AnalysisTimelineEntry[];

    const h = extractHitlUiStateFromTimeline(timeline);
    expect(h.hitlAwaiting).toBe(false);
    expect(h.hitlResumeInFlight).toBe(true);
    expect(h.parameterRequests).toHaveLength(1);
    expect(h.submittedParametersFromTimeline).toEqual({});
    expect(h.resolvedDecisionsFromTimeline).toEqual({});
  });

  it('completed run with parameter_response shows submitted values in read-only form', () => {
    const timeline = [
      { type: 'parameter_request', seq: 1, id: 'p1', parameterRequests: [{ id: 'reply', name: 'reply', description: '', paramType: 'text', required: true, encrypted: false }], detail: 'Need info' },
      { type: 'done', seq: 2, id: 'd1', awaitingHuman: true, hitl: { interruptIds: ['x'] } },
      { type: 'parameter_response', seq: 3, id: 'pr1', parameters: { reply: 'user answer' } },
      { type: 'step', seq: 4, id: 's2', label: 'Analysis', status: 'running' },
      { type: 'done', seq: 5, id: 'd2', awaitingHuman: false },
    ] as AnalysisTimelineEntry[];

    const h = extractHitlUiStateFromTimeline(timeline);
    expect(h.hitlAwaiting).toBe(false);
    expect(h.hitlResumeInFlight).toBe(true);
    expect(h.parameterRequests).toHaveLength(1);
    expect(h.parameterRequestDetail).toBe('Need info');
    expect(h.submittedParametersFromTimeline).toEqual({ reply: 'user answer' });
  });

  it('completed run with decision_response shows resolved choice in read-only form', () => {
    const timeline = [
      {
        type: 'decision_request', seq: 1, id: 'dr1',
        decision: { id: 'dec-ui', question: 'Continue?', options: [{ id: 'yes', label: 'Yes' }, { id: 'no', label: 'No' }] },
      },
      { type: 'done', seq: 2, id: 'd1', awaitingHuman: true, hitl: { interruptIds: ['x'] } },
      { type: 'decision_response', seq: 3, id: 'resp1', decisionUiId: 'dec-ui', selectedOptions: ['yes'] },
      { type: 'step', seq: 4, id: 's2', label: 'Continuing', status: 'running' },
      { type: 'done', seq: 5, id: 'd2', awaitingHuman: false },
    ] as AnalysisTimelineEntry[];

    const h = extractHitlUiStateFromTimeline(timeline);
    expect(h.hitlAwaiting).toBe(false);
    expect(h.hitlResumeInFlight).toBe(true);
    expect(h.decisions).toHaveLength(1);
    expect(h.decisions[0]?.id).toBe('dec-ui');
    expect(h.resolvedDecisionsFromTimeline['dec-ui']).toEqual(['yes']);
  });

  it('when paused done is not last entry, marks resume in flight and keeps form data', () => {
    const timeline = [
      { type: 'parameter_request', seq: 1, id: 'p1', parameterRequests: [{ id: 'reply', name: 'reply', description: '', paramType: 'text', required: true, encrypted: false }], detail: 'Need more' },
      { type: 'done', seq: 2, id: 'd1', awaitingHuman: true, hitl: { interruptIds: ['x'] } },
      { type: 'step', seq: 3, id: 's2', label: 'Thought', status: 'running' },
    ] as AnalysisTimelineEntry[];

    const h = extractHitlUiStateFromTimeline(timeline);
    expect(h.hitlAwaiting).toBe(false);
    expect(h.hitlResumeInFlight).toBe(true);
    expect(h.parameterRequests).toHaveLength(1);
    expect(h.parameterRequestDetail).toBe('Need more');
    expect(h.submittedParametersFromTimeline).toEqual({});
    expect(h.resolvedDecisionsFromTimeline).toEqual({});
  });

  it('reads parameter_response rows after paused done for DB-backed submitted fields', () => {
    const timeline = [
      {
        type: 'parameter_request',
        seq: 1,
        id: 'p1',
        parameterRequests: [
          {
            id: 'reply',
            name: 'reply',
            description: '',
            paramType: 'text',
            required: true,
            encrypted: false,
          },
        ],
      },
      { type: 'done', seq: 2, id: 'd1', awaitingHuman: true, hitl: { interruptIds: ['x'] } },
      {
        type: 'parameter_response',
        seq: 3,
        id: 'hitl-parameter-response',
        parameters: { reply: 'from-db', requestId: 'r1' },
      },
      { type: 'step', seq: 4, id: 's2', label: 'Thought', status: 'running' },
    ] as AnalysisTimelineEntry[];

    const h = extractHitlUiStateFromTimeline(timeline);
    expect(h.hitlResumeInFlight).toBe(true);
    expect(h.submittedParametersFromTimeline.reply).toBe('from-db');
    expect(h.submittedParametersFromTimeline.requestId).toBe('r1');
    expect(h.resolvedDecisionsFromTimeline).toEqual({});
  });

  it('reads decision_response rows after paused done for choice HITL', () => {
    const timeline = [
      {
        type: 'decision_request',
        seq: 1,
        id: 'dr1',
        decision: { id: 'dec-ui', question: 'OK?', options: [{ id: 'yes', label: 'Yes' }] },
      },
      { type: 'done', seq: 2, id: 'd1', awaitingHuman: true, hitl: { interruptIds: ['x'] } },
      {
        type: 'decision_response',
        seq: 3,
        id: 'hitl-decision-response',
        decisionUiId: 'dec-ui',
        selectedOptions: ['yes'],
      },
      { type: 'step', seq: 4, id: 's2', label: 'Thought', status: 'running' },
    ] as AnalysisTimelineEntry[];

    const h = extractHitlUiStateFromTimeline(timeline);
    expect(h.hitlResumeInFlight).toBe(true);
    expect(h.resolvedDecisionsFromTimeline['dec-ui']).toEqual(['yes']);
    expect(h.submittedParametersFromTimeline).toEqual({});
  });
});
