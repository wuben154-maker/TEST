import { describe, it, expect } from 'vitest';
import { buildLiveDisplayStats, buildActiveDisplayStats } from './liveDisplayStats';

describe('buildLiveDisplayStats', () => {
  it('retains internal layout signals (toolCallCount / sandboxRunCount / durationMs)', () => {
    const out = buildLiveDisplayStats(
      { toolCallCount: 3, sandboxRunCount: 1, resultStartTime: 1_000 },
      5_000,
    );
    expect(out.toolCallCount).toBe(3);
    expect(out.sandboxRunCount).toBe(1);
    expect(out.durationMs).toBe(4_000);
  });

  it('injects taskKind/security when statsMeta.security is present', () => {
    const out = buildLiveDisplayStats({
      statsMeta: {
        taskKind: 'security',
        security: { severity: 'critical', riskScore: 90 },
      },
      toolCallCount: 0,
      sandboxRunCount: 0,
      resultStartTime: 1_000,
    });
    expect(out.taskKind).toBe('security');
    expect(out.security).toEqual({ severity: 'critical', riskScore: 90 });
    expect(out.research).toBeUndefined();
  });

  it('injects taskKind/research when statsMeta.research is present', () => {
    const out = buildLiveDisplayStats({
      statsMeta: {
        taskKind: 'research',
        research: { keyFindings: 7, sources: 22, freshness: '<=30d' },
      },
    });
    expect(out.taskKind).toBe('research');
    expect(out.research?.keyFindings).toBe(7);
    expect(out.security).toBeUndefined();
  });

  it('omits taskKind fields when statsMeta is absent', () => {
    const out = buildLiveDisplayStats({ toolCallCount: 1 });
    expect(out.taskKind).toBeUndefined();
    expect(out.security).toBeUndefined();
    expect(out.research).toBeUndefined();
  });

  it('ignores malformed statsMeta without taskKind', () => {
    // A defensive check — partial payload from a future backend version.
    const out = buildLiveDisplayStats({
      statsMeta: { taskKind: undefined as unknown as 'security' },
    });
    expect(out.taskKind).toBeUndefined();
  });
});

describe('buildActiveDisplayStats', () => {
  it('returns stats from the persisted analysis result', () => {
    expect(
      buildActiveDisplayStats({ stats: { taskKind: 'security', toolCallCount: 2 } }),
    ).toEqual({ taskKind: 'security', toolCallCount: 2 });
  });

  it('returns empty object when stats absent', () => {
    expect(buildActiveDisplayStats({})).toEqual({});
  });
});
