import { useCallback, useState } from 'react';
import { useWorkspaceSidebarCollapsed } from '@/hooks/useWorkspaceSidebarCollapsed';

const MD_MIN = 768;

function isDesktopBp(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(`(min-width: ${MD_MIN}px)`).matches;
}

/**
 * Combines mobile drawer open state with persisted desktop rail collapse.
 * Top bar menu: collapse toggle on desktop, drawer toggle on small viewports.
 */
export function useProjectSidebarChrome() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { collapsed, setCollapsed, toggleCollapsed } = useWorkspaceSidebarCollapsed();

  const onTopNavMenuClick = useCallback(() => {
    if (isDesktopBp()) {
      toggleCollapsed();
    } else {
      setMobileOpen((o) => !o);
    }
  }, [toggleCollapsed]);

  const closeMobileSidebar = useCallback(() => setMobileOpen(false), []);

  return {
    mobileOpen,
    setMobileOpen,
    collapsed,
    setCollapsed,
    onTopNavMenuClick,
    closeMobileSidebar,
  };
}
