import { describe, expect, it } from 'vitest';
import {
  effectiveToolPresentation,
  inferToolPresentationFromToolName,
  isContextEnrichmentToolName,
} from './toolPresentation';

describe('inferToolPresentationFromToolName', () => {
  it('maps orchestration tools to task', () => {
    expect(inferToolPresentationFromToolName('write_todos')).toBe('task');
    expect(inferToolPresentationFromToolName('task')).toBe('task');
  });

  it('maps think_tool, deep-research orchestration tools, and internal/hitl to state', () => {
    expect(inferToolPresentationFromToolName('think_tool')).toBe('state');
    expect(inferToolPresentationFromToolName('ConductResearch')).toBe('research_task');
    expect(inferToolPresentationFromToolName('ResearchComplete')).toBe('state');
    expect(inferToolPresentationFromToolName('ResearchQuestion')).toBe('state');
    expect(inferToolPresentationFromToolName('internal_foo')).toBe('state');
    expect(inferToolPresentationFromToolName('HITL_bar')).toBe('state');
  });

  it('defaults unknown names to action', () => {
    expect(inferToolPresentationFromToolName('web_search')).toBe('action');
    expect(inferToolPresentationFromToolName('unknown_xyz')).toBe('action');
  });
});

describe('effectiveToolPresentation', () => {
  it('prefers explicit SSE field', () => {
    expect(
      effectiveToolPresentation({ toolPresentation: 'state', toolName: 'web_search' }),
    ).toBe('state');
  });

  it('falls back to toolName when field missing', () => {
    expect(effectiveToolPresentation({ toolName: 'write_todos' })).toBe('task');
  });
});

describe('isContextEnrichmentToolName', () => {
  it('matches explore set used by streaming switch', () => {
    expect(isContextEnrichmentToolName('read_file')).toBe(true);
    expect(isContextEnrichmentToolName('web_searchs')).toBe(true);
    expect(isContextEnrichmentToolName('think_tool')).toBe(false);
  });
});
