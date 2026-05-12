import { useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProjectSidebar } from '@/components/ProjectSidebar';
import { useWorkspaceProjects } from '@/contexts/WorkspaceProjectsContext';
import { useAuth } from '@/hooks/useAuth';
import { useLanguage } from '@/contexts/LanguageContext';
import { useProjectSidebarChrome } from '@/hooks/useProjectSidebarChrome';
import { useWorkspaceSidebarWidth } from '@/hooks/useWorkspaceSidebarWidth';
import { useStreamingStateContext } from '@/contexts/StreamingStateContext';
import {
  dismissPostLoginLandingUI,
  showPostLoginLandingUI,
  WORKSPACE_START_COLLAPSE_SIDEBAR_EVENT,
} from '@/lib/postLoginLanding';

export type WorkspaceOutletContext = {
  openMobileSidebar: () => void;
  closeMobileSidebar: () => void;
};

function WorkspaceChromeInner() {
  const navigate = useNavigate();
  const location = useLocation();
  const { removeState } = useStreamingStateContext();
  const { t } = useLanguage();
  const { mobileOpen, setMobileOpen, collapsed, setCollapsed, closeMobileSidebar } =
    useProjectSidebarChrome();
  const { expandedWidthPx, beginResize } = useWorkspaceSidebarWidth();
  const {
    projects,
    currentProjectId,
    selectProject,
    deleteProject,
    updateProjectTitle,
    isLoading: projectsLoading,
  } = useWorkspaceProjects();

  /** Empty project list: show expanded rail. Never key off post-login session (it outlives uploads and would re-expand a collapsed rail). */
  useEffect(() => {
    if (projectsLoading) return;
    if (projects.length === 0) {
      setCollapsed(false);
    }
  }, [projectsLoading, projects.length, setCollapsed]);

  useEffect(() => {
    const onWorkspaceStartCollapse = () => {
      setCollapsed(true);
      closeMobileSidebar();
    };
    window.addEventListener(WORKSPACE_START_COLLAPSE_SIDEBAR_EVENT, onWorkspaceStartCollapse);
    return () =>
      window.removeEventListener(WORKSPACE_START_COLLAPSE_SIDEBAR_EVENT, onWorkspaceStartCollapse);
  }, [setCollapsed, closeMobileSidebar]);

  if (projectsLoading) {
    return (
      <div className="flex h-screen w-screen overflow-hidden bg-background">
        <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
          <ProjectSidebar
            projects={[]}
            currentProjectId=""
            onSelectProject={() => {}}
            onOpenWorkspaceStart={() => {}}
            onDeleteProject={() => {}}
            mobileOpen={mobileOpen}
            onMobileOpenChange={setMobileOpen}
            collapsed={collapsed}
            onCollapsedChange={setCollapsed}
            brandSubtitle={t.auth.subtitle}
            expandedWidthPx={collapsed ? undefined : expandedWidthPx}
          />
          {!collapsed ? (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize sidebar"
              className="relative hidden w-0 shrink-0 md:block"
            >
              <div
                className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize"
                onMouseDown={beginResize}
              />
            </div>
          ) : null}
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-sidebar">
            <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
              <div className="flex flex-1 items-center justify-center">
                <div className="text-muted-foreground">{t.common.loading}</div>
              </div>
            </main>
          </div>
        </div>
      </div>
    );
  }

  const handleSelectProject = (id: string) => {
    selectProject(id);
    closeMobileSidebar();
    if (location.pathname !== '/start') {
      navigate('/start');
    }
    dismissPostLoginLandingUI();
  };

  /** Sidebar "Create project" — go to transition page (composer); do not open inline name dialog or create a row yet. */
  const handleOpenWorkspaceStart = () => {
    showPostLoginLandingUI();
    closeMobileSidebar();
    navigate('/start');
  };

  const handleDeleteProject = (id: string) => {
    removeState(id);
    void deleteProject(id);
  };

  const isWorkspaceHome = location.pathname === '/start';

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <ProjectSidebar
          projects={projects}
          currentProjectId={currentProjectId ?? ''}
          onSelectProject={handleSelectProject}
          onOpenWorkspaceStart={handleOpenWorkspaceStart}
          onDeleteProject={handleDeleteProject}
          onRenameProject={(id, title) => {
            void updateProjectTitle(id, title);
          }}
          mobileOpen={mobileOpen}
          onMobileOpenChange={setMobileOpen}
          collapsed={collapsed}
          onCollapsedChange={setCollapsed}
          brandSubtitle={t.auth.subtitle}
          expandedWidthPx={collapsed ? undefined : expandedWidthPx}
        />
        {!collapsed ? (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize sidebar"
            className="relative hidden w-0 shrink-0 md:block"
          >
            {/* Hit zone on the rail edge only — visual divider is ProjectSidebar border-r */}
            <div
              className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize"
              onMouseDown={beginResize}
            />
          </div>
        ) : null}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-sidebar">
          {!isWorkspaceHome ? (
            <div className="flex shrink-0 items-center justify-end border-b border-border/60 bg-sidebar/95 px-2 py-2 md:hidden">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={() => setMobileOpen(true)}
                aria-label={t.sidebar.openSidebar}
              >
                <Menu className="h-5 w-5" />
              </Button>
            </div>
          ) : null}
          <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
            <Outlet
              context={
                {
                  openMobileSidebar: () => setMobileOpen(true),
                  closeMobileSidebar,
                } satisfies WorkspaceOutletContext
              }
            />
          </main>
        </div>
      </div>
    </div>
  );
}

/**
 * Logged-in workspace routes: one persistent sidebar + project store; child routes render in Outlet.
 */
export function AppWorkspaceShell() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const { t } = useLanguage();

  useEffect(() => {
    if (!loading && !user) {
      navigate('/auth');
    }
  }, [loading, user, navigate]);

  if (loading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="text-muted-foreground">{t.common.loading}</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="text-muted-foreground">{t.common.loading}</div>
      </div>
    );
  }

  return <WorkspaceChromeInner />;
}
