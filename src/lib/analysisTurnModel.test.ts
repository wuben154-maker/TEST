import { describe, expect, it } from 'vitest';
import { buildAnalysisTurnItems, type AnalysisTurnViewModel } from './analysisTurnModel';
import type { Language } from '@/i18n';

const ctx = (sub = 'sub'): { language: Language; subagentFallbackName: string; includeNextActionsFooter?: boolean } => ({
  language: 'zh',
  subagentFallbackName: sub,
});

const emptyModel = (): AnalysisTurnViewModel => ({
  isAnalyzing: false,
  timeline: [],
  parameterRequests: [],
  decisions: [],
  resolvedDecisions: {},
  nextActions: [],
  taskPlan: null,
  taskPlansSubagent: {},
});

describe('buildAnalysisTurnItems', () => {
  it('omits react_timeline when no timeline and no offline content', () => {
    const m = emptyModel();
    m.userInput = 'hi';
    const items = buildAnalysisTurnItems(m, ctx());
    expect(items.some((i) => i.kind === 'user_message')).toBe(true);
    expect(items.some((i) => i.kind === 'react_timeline')).toBe(false);
  });

  it('emits react_timeline when understanding exists without timeline (unified replay)', () => {
    const m = emptyModel();
    m.understanding = {
      inputType: 'text',
      summary: 'Goal',
      keyEntities: [],
      analysisGoals: [],
      suggestedApproach: '',
      confidence: 0.9,
    };
    const items = buildAnalysisTurnItems(m, ctx());
    const rt = items.find((i) => i.kind === 'react_timeline');
    expect(rt).toBeDefined();
    if (rt?.kind === 'react_timeline') {
      expect(rt.timeline.length).toBe(0);
    }
  });

  it('emits react_timeline when persisted reasoning exists without timeline', () => {
    const m = emptyModel();
    m.currentReasoning = 'Restored from DB';
    const items = buildAnalysisTurnItems(m, ctx());
    expect(items.some((i) => i.kind === 'react_timeline')).toBe(true);
  });

  it('emits react_timeline when timeline non-empty', () => {
    const m = emptyModel();
    m.timeline = [
      {
        type: 'reasoning',
        id: 'r1',
        seq: 1,
        content: 'x',
        schemaVersion: 1,
        scope: 'main',
      } as import('@/types/analysis').AnalysisTimelineEntry,
    ];
    const items = buildAnalysisTurnItems(m, ctx());
    expect(items.some((i) => i.kind === 'react_timeline')).toBe(true);
  });

  it('emits react_timeline when analyzing even if timeline empty', () => {
    const m = emptyModel();
    m.isAnalyzing = true;
    const items = buildAnalysisTurnItems(m, ctx());
    expect(items.some((i) => i.kind === 'react_timeline')).toBe(true);
  });

  it('omits next_actions_footer when includeNextActionsFooter false', () => {
    const m = emptyModel();
    m.nextActions = [{ id: '1', label: 'Go', message: 'm' }];
    const withFooter = buildAnalysisTurnItems(m, { ...ctx(), includeNextActionsFooter: true });
    const without = buildAnalysisTurnItems(m, { ...ctx(), includeNextActionsFooter: false });
    expect(withFooter.some((i) => i.kind === 'next_actions_footer')).toBe(true);
    expect(without.some((i) => i.kind === 'next_actions_footer')).toBe(false);
  });

  it('suppresses parameters_footer when timeline has parameter_request (rendered inline via hitl_slot)', () => {
    const m = emptyModel();
    m.parameterRequests = [{ id: 'reply', name: 'reply', description: '', paramType: 'text', required: true, encrypted: false }];
    m.timeline = [
      {
        type: 'parameter_request',
        id: 'pr-1',
        seq: 2,
        schemaVersion: 1,
        scope: 'main',
        parameterRequests: m.parameterRequests,
      } as import('@/types/analysis').AnalysisTimelineEntry,
    ];
    const items = buildAnalysisTurnItems(m, ctx());
    expect(items.some((i) => i.kind === 'parameters_footer')).toBe(false);
    expect(items.some((i) => i.kind === 'react_timeline')).toBe(true);
  });

  it('keeps parameters_footer when parameterRequests exist but no timeline row (understanding-only)', () => {
    const m = emptyModel();
    m.parameterRequests = [{ id: 'x', name: 'x', description: '', paramType: 'text', required: true, encrypted: false }];
    m.timeline = [
      {
        type: 'reasoning',
        id: 'r1',
        seq: 1,
        content: 'x',
        schemaVersion: 1,
        scope: 'main',
      } as import('@/types/analysis').AnalysisTimelineEntry,
    ];
    const items = buildAnalysisTurnItems(m, ctx());
    expect(items.some((i) => i.kind === 'parameters_footer')).toBe(true);
  });
});
