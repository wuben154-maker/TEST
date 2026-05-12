/**
 * Marker for each attachment line in stored/displayed user content.
 * Chat UI strips this and renders filenames with an ImageUp-style icon.
 */
export const USER_MESSAGE_ATTACHMENT_LINE_PREFIX = '📎 ';

/**
 * Split formatted user bubble text into body + attachment filenames.
 */
export function parseUserMessageAttachments(raw: string): { body: string; files: string[] } {
  const trimmed = raw.trimEnd();
  if (!trimmed) return { body: '', files: [] };

  const lines = trimmed.split('\n');
  const isAttachLine = (l: string) => l.trimStart().startsWith(USER_MESSAGE_ATTACHMENT_LINE_PREFIX);
  const nameFromLine = (l: string) =>
    l.trimStart().slice(USER_MESSAGE_ATTACHMENT_LINE_PREFIX.length).trim();

  const attachIdx = lines.findIndex((l) => isAttachLine(l));
  if (attachIdx === -1) return { body: trimmed, files: [] };

  const attachLines = lines.slice(attachIdx);
  if (!attachLines.every((l) => !l.trim() || isAttachLine(l))) {
    return { body: trimmed, files: [] };
  }

  const body = lines.slice(0, attachIdx).join('\n').replace(/\s+$/, '');
  const files = attachLines
    .filter((l) => l.trim())
    .map(nameFromLine)
    .filter(Boolean);
  return { body, files };
}

/**
 * Chat / history display: combine typed text with attachment filenames.
 * API requests must still use the raw message + attachments array separately.
 */
/** Backend stores this literal for POST /analyze/resume rows; hide from chat history UI. */
export const HITL_RESUME_PLACEHOLDER_USER_TEXT = '[HITL resume]';

export function isHitlResumePlaceholderUserContent(raw: string | undefined | null): boolean {
  return (raw ?? '').trim() === HITL_RESUME_PLACEHOLDER_USER_TEXT;
}

export function formatUserMessageForChat(
  text: string,
  attachments: Array<{ filename?: string }>,
): string {
  const names = attachments
    .map((a) => (a.filename || '').trim())
    .filter(Boolean);
  const base = text.trim();
  const fileLines = names.map((n) => `${USER_MESSAGE_ATTACHMENT_LINE_PREFIX}${n}`);

  if (fileLines.length === 0) {
    return base || '[Attachment-only request]';
  }
  if (base) {
    return `${base}\n\n${fileLines.join('\n')}`;
  }
  return fileLines.join('\n');
}
