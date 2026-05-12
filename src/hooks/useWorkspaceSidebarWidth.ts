import { useState, useCallback, type MouseEvent as ReactMouseEvent } from 'react';

export const WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY = 'secmanus:workspaceSidebarExpandedWidthPx';
export const WORKSPACE_SIDEBAR_WIDTH_DEFAULT = 240;
export const WORKSPACE_SIDEBAR_WIDTH_MIN = 240;
export const WORKSPACE_SIDEBAR_WIDTH_MAX = 420;

function readStoredWidth(): number {
  if (typeof window === 'undefined') return WORKSPACE_SIDEBAR_WIDTH_DEFAULT;
  const raw = localStorage.getItem(WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY);
  const n = raw ? parseInt(raw, 10) : NaN;
  if (!Number.isFinite(n)) return WORKSPACE_SIDEBAR_WIDTH_DEFAULT;
  return Math.min(
    WORKSPACE_SIDEBAR_WIDTH_MAX,
    Math.max(WORKSPACE_SIDEBAR_WIDTH_MIN, n),
  );
}

function clampWidth(w: number): number {
  return Math.min(
    WORKSPACE_SIDEBAR_WIDTH_MAX,
    Math.max(WORKSPACE_SIDEBAR_WIDTH_MIN, Math.round(w)),
  );
}

/**
 * Persisted width for the expanded desktop workspace rail (md+, not collapsed).
 */
export function useWorkspaceSidebarWidth() {
  const [expandedWidthPx, setExpandedWidthPxState] = useState(readStoredWidth);

  const setExpandedWidthPx = useCallback((next: number) => {
    const clamped = clampWidth(next);
    setExpandedWidthPxState(clamped);
    try {
      localStorage.setItem(WORKSPACE_SIDEBAR_WIDTH_STORAGE_KEY, String(clamped));
    } catch {
      /* ignore quota / private mode */
    }
  }, []);

  const beginResize = useCallback(
    (event: ReactMouseEvent) => {
      event.preventDefault();
      const startX = event.clientX;
      const startW = expandedWidthPx;
      const onMove = (ev: MouseEvent) => {
        setExpandedWidthPx(startW + (ev.clientX - startX));
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    },
    [expandedWidthPx, setExpandedWidthPx],
  );

  return { expandedWidthPx, setExpandedWidthPx, beginResize };
}
