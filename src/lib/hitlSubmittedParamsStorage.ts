/**
 * Persists HITL submitted parameters per project + progress request id.
 * Used to restore read-only form values after refresh while analysis is paused.
 */

const STORAGE_PREFIX = 'secmanus_hitl_submitted_params';

function buildStorageKey(projectId: string, requestId: string): string {
  return `${STORAGE_PREFIX}:${projectId}:${requestId}`;
}

function canUseSessionStorage(): boolean {
  return typeof sessionStorage !== 'undefined';
}

function sanitizeRecord(input: unknown): Record<string, string> {
  if (!input || typeof input !== 'object') return {};
  const entries = Object.entries(input as Record<string, unknown>).map(([key, value]) => [
    key,
    String(value ?? ''),
  ]);
  return Object.fromEntries(entries);
}

export function saveHitlSubmittedParams(
  projectId: string,
  requestId: string,
  params: Record<string, string>,
): void {
  const pid = projectId.trim();
  const rid = requestId.trim();
  if (!pid || !rid || !canUseSessionStorage()) return;
  try {
    const key = buildStorageKey(pid, rid);
    sessionStorage.setItem(key, JSON.stringify(sanitizeRecord(params)));
  } catch {
    /* ignore storage quota/privacy errors */
  }
}

export function readHitlSubmittedParams(projectId: string, requestId: string): Record<string, string> {
  const pid = projectId.trim();
  const rid = requestId.trim();
  if (!pid || !rid || !canUseSessionStorage()) return {};
  try {
    const key = buildStorageKey(pid, rid);
    const raw = sessionStorage.getItem(key);
    if (!raw) return {};
    return sanitizeRecord(JSON.parse(raw));
  } catch {
    return {};
  }
}

export function clearHitlSubmittedParams(projectId: string, requestId: string): void {
  const pid = projectId.trim();
  const rid = requestId.trim();
  if (!pid || !rid || !canUseSessionStorage()) return;
  try {
    const key = buildStorageKey(pid, rid);
    sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}
