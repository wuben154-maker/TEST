import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useWorkspaceSidebarWidth,
  WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY,
  WORKSPACE_SIDEBAR_WIDTH_DEFAULT,
  WORKSPACE_SIDEBAR_WIDTH_MIN,
  WORKSPACE_SIDEBAR_WIDTH_MAX,
} from './useWorkspaceSidebarWidth';

describe('useWorkspaceSidebarWidth', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults when storage empty', () => {
    const { result } = renderHook(() => useWorkspaceSidebarWidth());
    expect(result.current.expandedWidthPx).toBe(WORKSPACE_SIDEBAR_WIDTH_DEFAULT);
  });

  it('reads initial width from localStorage', () => {
    localStorage.setItem(WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY, '300');
    const { result } = renderHook(() => useWorkspaceSidebarWidth());
    expect(result.current.expandedWidthPx).toBe(300);
  });

  it('clamps stored value to min/max', () => {
    localStorage.setItem(WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY, '900');
    const { result } = renderHook(() => useWorkspaceSidebarWidth());
    expect(result.current.expandedWidthPx).toBe(WORKSPACE_SIDEBAR_WIDTH_MAX);
    localStorage.setItem(WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY, '100');
    const { result: r2 } = renderHook(() => useWorkspaceSidebarWidth());
    expect(r2.current.expandedWidthPx).toBe(WORKSPACE_SIDEBAR_WIDTH_MIN);
  });

  it('setExpandedWidthPx persists clamped value', () => {
    const { result } = renderHook(() => useWorkspaceSidebarWidth());
    act(() => result.current.setExpandedWidthPx(500));
    expect(result.current.expandedWidthPx).toBe(WORKSPACE_SIDEBAR_WIDTH_MAX);
    expect(localStorage.getItem(WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY)).toBe(
      String(WORKSPACE_SIDEBAR_WIDTH_MAX),
    );
  });
});
