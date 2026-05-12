import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWorkspaceSidebarCollapsed } from './useWorkspaceSidebarCollapsed';

const KEY = 'secmanus:workspaceSidebarCollapsed';

describe('useWorkspaceSidebarCollapsed', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to expanded when storage empty', () => {
    const { result } = renderHook(() => useWorkspaceSidebarCollapsed());
    expect(result.current.collapsed).toBe(false);
  });

  it('reads initial collapsed from localStorage', () => {
    localStorage.setItem(KEY, '1');
    const { result } = renderHook(() => useWorkspaceSidebarCollapsed());
    expect(result.current.collapsed).toBe(true);
  });

  it('setCollapsed persists', () => {
    const { result } = renderHook(() => useWorkspaceSidebarCollapsed());
    act(() => result.current.setCollapsed(true));
    expect(result.current.collapsed).toBe(true);
    expect(localStorage.getItem(KEY)).toBe('1');
    act(() => result.current.setCollapsed(false));
    expect(localStorage.getItem(KEY)).toBe('0');
  });

  it('toggleCollapsed flips state and persists', () => {
    const { result } = renderHook(() => useWorkspaceSidebarCollapsed());
    act(() => result.current.toggleCollapsed());
    expect(result.current.collapsed).toBe(true);
    expect(localStorage.getItem(KEY)).toBe('1');
    act(() => result.current.toggleCollapsed());
    expect(result.current.collapsed).toBe(false);
    expect(localStorage.getItem(KEY)).toBe('0');
  });
});
