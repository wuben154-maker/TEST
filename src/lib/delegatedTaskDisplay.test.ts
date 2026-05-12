import { describe, expect, it } from 'vitest';
import { formatDelegatedTaskForDisplay } from './delegatedTaskDisplay';

describe('formatDelegatedTaskForDisplay', () => {
  it('strips ORIGINAL_QUERY prefix and CONTEXT section, keeps user question', () => {
    const raw =
      'ORIGINAL_QUERY: 深度分析一下claude code泄露代码中关于AI Agent的安全设计思路\n' +
      '---CONTEXT---\n' +
      '需要研究2026年之前公开的Claude代码泄露相关信息。';
    expect(formatDelegatedTaskForDisplay(raw)).toBe('深度分析一下claude code泄露代码中关于AI Agent的安全设计思路');
  });

  it('handles lowercase original_query prefix', () => {
    expect(formatDelegatedTaskForDisplay('original_query: Hello world')).toBe('Hello world');
  });

  it('returns plain description when no layered markers', () => {
    expect(formatDelegatedTaskForDisplay('Just a normal task')).toBe('Just a normal task');
  });

  it('truncates long output', () => {
    const long = 'x'.repeat(500);
    const out = formatDelegatedTaskForDisplay(long, 100);
    expect(out.length).toBe(101);
    expect(out.endsWith('…')).toBe(true);
  });

  it('returns empty string for whitespace-only input', () => {
    expect(formatDelegatedTaskForDisplay('   \n')).toBe('');
  });
});
