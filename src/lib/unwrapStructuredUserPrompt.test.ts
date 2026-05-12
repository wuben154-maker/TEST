import { describe, expect, it } from 'vitest';

import { unwrapStructuredUserPrompt } from './unwrapStructuredUserPrompt';

describe('unwrapStructuredUserPrompt', () => {
  it('leaves plain text unchanged', () => {
    const s = 'Hello, analyze this alert.';
    expect(unwrapStructuredUserPrompt(s)).toBe(s);
  });

  it('unwraps research_brief JSON', () => {
    const inner = 'Study AI security vendors from 2025 to 2026.';
    const raw = JSON.stringify({ research_brief: inner });
    expect(unwrapStructuredUserPrompt(raw)).toBe(inner);
  });

  it('does not unwrap multiple keys', () => {
    const raw = JSON.stringify({ research_brief: 'a', extra: 'b' });
    expect(unwrapStructuredUserPrompt(raw)).toBe(raw.trim());
  });

  it('unwraps fenced json block', () => {
    const inner = 'Fenced brief body.';
    const body = JSON.stringify({ research_brief: inner });
    const raw = `\`\`\`json\n${body}\n\`\`\``;
    expect(unwrapStructuredUserPrompt(raw)).toBe(inner);
  });

  it('returns empty for null', () => {
    expect(unwrapStructuredUserPrompt(null)).toBe('');
  });
});
