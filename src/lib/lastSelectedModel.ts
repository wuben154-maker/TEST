/**
 * Persists the user's last model choice (shared with ModelSelector).
 * Used for HITL resume so POST /analyze/resume matches the model used for POST /analyze.
 */

export const LAST_SELECTED_MODEL_STORAGE_KEY = 'secmanus_last_selected_model';

export function getLastSelectedModelId(): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem(LAST_SELECTED_MODEL_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setLastSelectedModelId(modelId: string): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(LAST_SELECTED_MODEL_STORAGE_KEY, modelId);
  } catch {
    /* ignore */
  }
}

/** Value for JSON bodies: omit property when unset or whitespace-only. */
export function getLastSelectedModelIdForApi(): string | undefined {
  const v = getLastSelectedModelId()?.trim();
  return v ? v : undefined;
}
