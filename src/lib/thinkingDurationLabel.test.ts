import { describe, expect, it } from 'vitest';
import { formatThinkingElapsed, formatThoughtDuration } from '@/lib/thinkingDurationLabel';

describe('formatThoughtDuration', () => {
  it('shows one decimal place for values under 10 seconds', () => {
    expect(formatThoughtDuration(0)).toBe('Thought 0.0s');
    expect(formatThoughtDuration(0.3)).toBe('Thought 0.3s');
    expect(formatThoughtDuration(1.5)).toBe('Thought 1.5s');
    expect(formatThoughtDuration(9.9)).toBe('Thought 9.9s');
  });

  it('rounds to whole seconds for values >= 10 seconds', () => {
    expect(formatThoughtDuration(10)).toBe('Thought 10s');
    expect(formatThoughtDuration(12)).toBe('Thought 12s');
    expect(formatThoughtDuration(120)).toBe('Thought 120s');
  });

  it('never shows negative', () => {
    expect(formatThoughtDuration(-1)).toBe('Thought 0.0s');
  });

  it('uses Thought brief when contentless', () => {
    expect(formatThoughtDuration(1.2, { brief: true })).toBe('Thought brief 1.2s');
    expect(formatThoughtDuration(10, { brief: true })).toBe('Thought brief 10s');
  });
});

describe('formatThinkingElapsed', () => {
  it('matches numeric rules and never uses Thought / Thought brief', () => {
    expect(formatThinkingElapsed(0)).toBe('Thinking 0.0s');
    expect(formatThinkingElapsed(2.4)).toBe('Thinking 2.4s');
    expect(formatThinkingElapsed(10)).toBe('Thinking 10s');
    expect(formatThinkingElapsed(-1)).toBe('Thinking 0.0s');
  });
});
