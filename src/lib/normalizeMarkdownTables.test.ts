import { describe, expect, it } from 'vitest';
import {
  fixCitationPipeRowGlue,
  normalizeMarkdownForWorkspace,
} from './normalizeMarkdownTables';

describe('normalizeMarkdownTables', () => {
  it('inserts newline before next row after citation pipe glue', () => {
    const raw = '| a | b |\n|---|---|\n| foo [196] | | 深信服 | x |';
    expect(fixCitationPipeRowGlue(raw)).toBe(
      '| a | b |\n|---|---|\n| foo [196]\n| 深信服 | x |',
    );
  });

  it('does not mutate inside triple-backtick fences', () => {
    const fenced = '```\nx [1] | | y\n```\n| h |\n|---|\n| foo [2] | | bar |';
    const out = normalizeMarkdownForWorkspace(fenced);
    expect(out).toContain('x [1] | | y');
    expect(out).toContain('| foo [2]\n| bar |');
  });
});
