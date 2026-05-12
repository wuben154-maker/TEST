import { describe, expect, it } from 'vitest';
import { deriveAutoProjectTitle } from './deriveAutoProjectTitle';

describe('deriveAutoProjectTitle', () => {
  it('prefers first non-empty line of user text', () => {
    expect(
      deriveAutoProjectTitle({
        userText: '  \n\nHello world\nmore',
        fileNames: ['a.pdf'],
        fallbackLabel: 'X',
      }),
    ).toBe('Hello world · a.pdf');
  });

  it('prefers user text with attachment hint (upload-then-type submit)', () => {
    expect(
      deriveAutoProjectTitle({
        userText: 'Q1 phishing triage scope',
        fileNames: ['evidence.zip', 'notes.pdf'],
        fallbackLabel: 'evidence.zip',
      }),
    ).toBe('Q1 phishing triage scope · evidence.zip, notes.pdf');
  });

  it('uses file names when no text', () => {
    expect(
      deriveAutoProjectTitle({
        userText: '',
        fileNames: ['C:/dir/report.pdf'],
        fallbackLabel: 'X',
      }),
    ).toBe('report.pdf');
  });

  it('joins multiple files', () => {
    const t = deriveAutoProjectTitle({
      userText: '',
      fileNames: ['a.txt', 'b.txt', 'c.txt'],
      fallbackLabel: 'X',
    });
    expect(t).toContain('a.txt');
    expect(t).toContain('b.txt');
  });

  it('uses fallback when empty', () => {
    expect(
      deriveAutoProjectTitle({
        userText: '   \n',
        fileNames: [],
        fallbackLabel: '新建',
      }),
    ).toBe('新建');
  });

  it('keeps attachment suffix when user text must be shortened', () => {
    const t = deriveAutoProjectTitle({
      userText:
        'This is a very long first line that cannot fit together with the file hint in fifty characters total budget',
      fileNames: ['short.pdf'],
      fallbackLabel: 'X',
    });
    expect(t.length).toBeLessThanOrEqual(50);
    expect(t).toContain('short.pdf');
    expect(t).toContain('·');
  });
});
