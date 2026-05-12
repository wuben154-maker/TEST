import { useCallback, useState } from 'react';

const STORAGE_KEY = 'secmanus:workspaceSidebarCollapsed';

function readInitialCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function persistCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
  } catch {
    /* ignore quota / private mode */
  }
}

/**
 * Desktop project rail collapsed state (48px vs 240px), persisted in localStorage.
 */
export function useWorkspaceSidebarCollapsed() {
  const [collapsed, setCollapsedState] = useState(readInitialCollapsed);

  const setCollapsed = useCallback((next: boolean) => {
    setCollapsedState(next);
    persistCollapsed(next);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((c) => {
      const next = !c;
      persistCollapsed(next);
      return next;
    });
  }, []);

  return { collapsed, setCollapsed, toggleCollapsed };
}
