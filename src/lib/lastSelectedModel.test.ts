import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  getLastSelectedModelId,
  getLastSelectedModelIdForApi,
  LAST_SELECTED_MODEL_STORAGE_KEY,
  setLastSelectedModelId,
} from './lastSelectedModel';

describe('lastSelectedModel', () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('getLastSelectedModelId returns stored value', () => {
    localStorage.setItem(LAST_SELECTED_MODEL_STORAGE_KEY, 'anthropic/claude-sonnet-4');
    expect(getLastSelectedModelId()).toBe('anthropic/claude-sonnet-4');
  });

  it('getLastSelectedModelIdForApi returns undefined for empty or whitespace', () => {
    expect(getLastSelectedModelIdForApi()).toBeUndefined();
    localStorage.setItem(LAST_SELECTED_MODEL_STORAGE_KEY, '  ');
    expect(getLastSelectedModelIdForApi()).toBeUndefined();
  });

  it('getLastSelectedModelIdForApi trims and returns id', () => {
    localStorage.setItem(LAST_SELECTED_MODEL_STORAGE_KEY, '  google/gemini-pro  ');
    expect(getLastSelectedModelIdForApi()).toBe('google/gemini-pro');
  });

  it('setLastSelectedModelId persists', () => {
    setLastSelectedModelId('opencode/foo');
    expect(localStorage.getItem(LAST_SELECTED_MODEL_STORAGE_KEY)).toBe('opencode/foo');
  });

  it('getLastSelectedModelId returns null when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(getLastSelectedModelId()).toBeNull();
  });
});
