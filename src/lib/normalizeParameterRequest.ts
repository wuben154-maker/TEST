import type { ParameterRequest } from '@/types/analysis';

const PARAM_TYPES = new Set(['text', 'password', 'url', 'json', 'boolean']);

/**
 * Coerce SSE / persisted payloads into ParameterRequest.
 * Backend understanding events historically used snake_case (param_type, validation_regex).
 */
export function normalizeParameterRequest(raw: ParameterRequest): ParameterRequest {
  const r = raw as unknown as Record<string, unknown>;
  const paramRaw = r.paramType ?? r.param_type ?? 'text';
  let paramType = typeof paramRaw === 'string' ? paramRaw : 'text';
  if (!PARAM_TYPES.has(paramType)) {
    paramType = 'text';
  }
  const vr = r.validationRegex ?? r.validation_regex;
  let validationRegex: string | undefined;
  if (typeof vr === 'string' && vr.trim()) {
    validationRegex = vr.trim();
  }
  const placeholder =
    typeof r.placeholder === 'string' && r.placeholder ? r.placeholder : undefined;
  return {
    id: String(r.id ?? ''),
    name: String(r.name ?? ''),
    description: String(r.description ?? ''),
    paramType: paramType as ParameterRequest['paramType'],
    required: Boolean(r.required),
    placeholder,
    validationRegex,
    encrypted: Boolean(r.encrypted),
    isClarification: Boolean(r.isClarification),
  };
}

/** Safe regex test: avoids /g lastIndex flakiness; supports /pattern/flags literals. */
export function matchesValidationRegex(pattern: string, value: string): boolean {
  const trimmed = pattern.trim();
  let body = trimmed;
  let flags = '';
  if (trimmed.startsWith('/') && trimmed.lastIndexOf('/') > 0) {
    const last = trimmed.lastIndexOf('/');
    body = trimmed.slice(1, last);
    flags = trimmed.slice(last + 1);
  }
  flags = flags.replace(/g/g, '');
  try {
    return new RegExp(body, flags).test(value);
  } catch {
    return false;
  }
}

export function fieldHasFormatConstraint(req: ParameterRequest): boolean {
  if (req.paramType === 'url' || req.paramType === 'json') return true;
  return Boolean(req.validationRegex && req.validationRegex.trim());
}

/**
 * Single free-text HITL fields use id/name "reply" in SSE; the card title already explains the form.
 */
export function shouldHideParameterRequestNameLabel(req: ParameterRequest): boolean {
  const id = req.id.trim().toLowerCase();
  const name = req.name.trim().toLowerCase();
  return id === 'reply' && name === 'reply';
}
