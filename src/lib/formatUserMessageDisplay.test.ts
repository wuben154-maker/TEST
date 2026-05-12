import { describe, expect, it } from 'vitest';
import {
  formatUserMessageForChat,
  parseUserMessageAttachments,
  USER_MESSAGE_ATTACHMENT_LINE_PREFIX,
  isHitlResumePlaceholderUserContent,
  HITL_RESUME_PLACEHOLDER_USER_TEXT,
} from './formatUserMessageDisplay';

describe('isHitlResumePlaceholderUserContent', () => {
  it('matches backend HITL resume placeholder exactly', () => {
    expect(isHitlResumePlaceholderUserContent(HITL_RESUME_PLACEHOLDER_USER_TEXT)).toBe(true);
    expect(isHitlResumePlaceholderUserContent(` ${HITL_RESUME_PLACEHOLDER_USER_TEXT} `)).toBe(true);
    expect(isHitlResumePlaceholderUserContent('real question')).toBe(false);
  });
});

describe('formatUserMessageForChat', () => {
  it('appends attachment lines after user text', () => {
    expect(
      formatUserMessageForChat('请分析', [{ filename: 'a.eml' }, { filename: 'b.pdf' }]),
    ).toBe(`请分析\n\n${USER_MESSAGE_ATTACHMENT_LINE_PREFIX}a.eml\n${USER_MESSAGE_ATTACHMENT_LINE_PREFIX}b.pdf`);
  });

  it('shows only attachment lines when message is empty', () => {
    expect(formatUserMessageForChat('', [{ filename: 'log.txt' }])).toBe(
      `${USER_MESSAGE_ATTACHMENT_LINE_PREFIX}log.txt`,
    );
  });

  it('uses placeholder when no text and no attachments', () => {
    expect(formatUserMessageForChat('', [])).toBe('[Attachment-only request]');
  });
});

describe('parseUserMessageAttachments', () => {
  it('parses body and files', () => {
    const raw = `请分析\n\n${USER_MESSAGE_ATTACHMENT_LINE_PREFIX}a.php\n${USER_MESSAGE_ATTACHMENT_LINE_PREFIX}b.txt`;
    expect(parseUserMessageAttachments(raw)).toEqual({
      body: '请分析',
      files: ['a.php', 'b.txt'],
    });
  });

  it('returns whole string as body when no marker lines', () => {
    expect(parseUserMessageAttachments('仅正文')).toEqual({ body: '仅正文', files: [] });
  });
});
