import { describe, expect, it, vi, afterEach } from 'vitest';
import { attachKnowledgeArchiveDeadline, parseKnowledgeArchiveFromRow } from './knowledgeArchive';

describe('attachKnowledgeArchiveDeadline', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('resolves when the inner promise resolves before the deadline', async () => {
    const out = attachKnowledgeArchiveDeadline(Promise.resolve(42), 60_000, () => {});
    await expect(out).resolves.toBe(42);
  });

  it('rejects when the deadline elapses first', async () => {
    vi.useFakeTimers();
    const p = new Promise<number>(() => {
      /* deliberately unresolved */
    });
    const onDeadline = vi.fn();
    const out = attachKnowledgeArchiveDeadline(p, 1000, onDeadline);
    vi.advanceTimersByTime(1000);
    await expect(out).rejects.toMatchObject({ name: 'KnowledgeArchiveDeadlineError' });
    expect(onDeadline).toHaveBeenCalled();
  });
});

describe('parseKnowledgeArchiveFromRow', () => {
  it('returns undefined for null / non-objects', () => {
    expect(parseKnowledgeArchiveFromRow(null)).toBeUndefined();
    expect(parseKnowledgeArchiveFromRow([])).toBeUndefined();
  });

  it('maps snake_case API payload', () => {
    expect(
      parseKnowledgeArchiveFromRow({
        filename: 'a.docx',
        display_path: 'knowledge/a.docx',
        report_label: 'R1',
      }),
    ).toEqual({
      pending: undefined,
      filename: 'a.docx',
      displayPath: 'knowledge/a.docx',
      reportLabel: 'R1',
    });
  });

  it('accepts pending-only row for hydration edge cases', () => {
    expect(parseKnowledgeArchiveFromRow({ pending: true, filename: '' })).toEqual({
      pending: true,
      filename: '',
      displayPath: '',
      reportLabel: '',
    });
  });
});
