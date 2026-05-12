import { describe, expect, it } from 'vitest';
import { getTranslations } from '@/i18n';
import {
  humanizeToolCallLine,
  humanizeToolCallSegments,
  fallbackToolDisplayName,
  compactToolRowLabel,
  isAdapterChromeStepId,
  shouldHideStepRow,
} from './toolCallDisplay';

describe('shouldHideStepRow', () => {
  it('shows subagent delegate task-running steps (ReAct / dev visibility)', () => {
    expect(shouldHideStepRow({ type: 'step', id: 'task-running-abc' })).toBe(false);
  });

  it('hides subagent LangGraph values tick steps (legacy SSE)', () => {
    expect(shouldHideStepRow({ type: 'step', id: 'subagent-web-security-values-3' })).toBe(true);
  });

  it('hides adapter heartbeat steps (start / complete / stream-init)', () => {
    expect(shouldHideStepRow({ type: 'step', id: 'analysis-start' })).toBe(true);
    expect(shouldHideStepRow({ type: 'step', id: 'analysis-complete' })).toBe(true);
    expect(shouldHideStepRow({ type: 'step', id: 'stream-init' })).toBe(true);
    expect(isAdapterChromeStepId('analysis-start')).toBe(true);
    expect(shouldHideStepRow({ type: 'tool_call', id: 'x' })).toBe(false);
  });
});

describe('humanizeToolCallLine', () => {
  it('renders web_search from i18n (en)', () => {
    const t = getTranslations('en');
    expect(humanizeToolCallLine('web_search', { query: 'malware' }, 'en')).toBe(
      t.toolActivity.webSearch.replace('{query}', 'malware'),
    );
  });

  it('renders web_search from i18n (ja)', () => {
    const t = getTranslations('ja');
    expect(humanizeToolCallLine('web_search', { query: 'test' }, 'ja')).toBe(
      t.toolActivity.webSearch.replace('{query}', 'test'),
    );
  });

  it('renders web_searchs (SSE alias) queries array (en)', () => {
    const t = getTranslations('en');
    expect(
      humanizeToolCallLine('web_searchs', { queries: ['CVE-2024-1', 'patch'] }, 'en'),
    ).toBe(t.toolActivity.webSearch.replace('{query}', 'CVE-2024-1 (+1)'));
  });

  it('renders web_search_deep_research queries array for persisted legacy rows (en)', () => {
    const t = getTranslations('en');
    expect(
      humanizeToolCallLine('web_search_deep_research', { queries: ['CVE-2024-1', 'patch'] }, 'en'),
    ).toBe(t.toolActivity.webSearch.replace('{query}', 'CVE-2024-1 (+1)'));
  });

  it('returns empty for task tool', () => {
    expect(humanizeToolCallLine('task', { description: 'x' }, 'en')).toBe('');
  });

  it('uses generic fallback for unknown tools', () => {
    const t = getTranslations('en');
    expect(humanizeToolCallLine('unknown_xyz', {}, 'en')).toBe(
      t.toolActivity.genericWithName.replace('{name}', 'unknown xyz'),
    );
  });
});

describe('humanizeToolCallSegments', () => {
  it('splits read_file into verb + path badge (en)', () => {
    const t = getTranslations('en');
    const segs = humanizeToolCallSegments('read_file', { path: '/x.py' }, 'en');
    expect(segs).toEqual([
      { kind: 'verb', text: t.toolActivity.traceVerbRead },
      { kind: 'badge', text: '/x.py' },
    ]);
  });

  it('returns empty array for task tool', () => {
    expect(humanizeToolCallSegments('task', {}, 'en')).toEqual([]);
  });

  it('uses zh grep layout (muted + badges)', () => {
    const segs = humanizeToolCallSegments(
      'grep',
      { pattern: 'foo', path: 'src' },
      'zh',
    );
    expect(segs[0]).toEqual({ kind: 'muted', text: '在 ' });
    expect(segs[1]).toEqual({ kind: 'badge', text: 'src' });
  });

  it('splits web_searchs into verb + queries badge', () => {
    const t = getTranslations('en');
    const segs = humanizeToolCallSegments(
      'web_searchs',
      { queries: ['foo bar', 'baz'] },
      'en',
    );
    expect(segs).toEqual([
      { kind: 'verb', text: t.toolActivity.traceVerbWebSearch },
      { kind: 'badge', text: 'foo bar (+1)' },
    ]);
  });

  it('summarizes glob pattern when input is a JSON array string', () => {
    const raw = JSON.stringify(['/a.php', '/b.php']);
    const segs = humanizeToolCallSegments('glob', { pattern: raw }, 'en');
    expect(segs[1]).toMatchObject({ kind: 'badge' });
    if (segs[1].kind === 'badge') {
      expect(segs[1].text).toContain('/a.php');
      expect(segs[1].text).toMatch(/\+1 more/);
    }
  });
});

describe('compactToolRowLabel', () => {
  it('returns snake_case tool id as spaced words without arguments', () => {
    expect(compactToolRowLabel('read_file')).toBe('read file');
    expect(compactToolRowLabel('web_search')).toBe('web search');
    expect(compactToolRowLabel('web_searchs')).toBe('web searchs');
    expect(compactToolRowLabel('web_search_deep_research')).toBe('web search deep research');
  });

  it('returns empty for task tool', () => {
    expect(compactToolRowLabel('task')).toBe('');
  });
});

describe('fallbackToolDisplayName', () => {
  it('hides task tool name (no user-visible label)', () => {
    expect(fallbackToolDisplayName('task', 'en')).toBe('');
    expect(fallbackToolDisplayName('task', 'zh')).toBe('');
  });

  it('passes through other tool names', () => {
    expect(fallbackToolDisplayName('read_file', 'en')).toBe('read_file');
  });
});
