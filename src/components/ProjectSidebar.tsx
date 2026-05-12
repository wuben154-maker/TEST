import { useEffect, useMemo, useRef, useState } from 'react';
import { Link as RouterLink, NavLink, useLocation } from 'react-router-dom';
import {
  Plus,
  X,
  ChevronLeft,
  ChevronRight,
  Trash2,
  Shield,
  PenLine,
  LayoutDashboard,
  Bot,
  Puzzle,
  BookOpen,
  UserCircle,
  CreditCard,
  BarChart3,
  Globe,
  LogOut,
  Search,
  ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Project } from '@/types/project';
import { AUTO_PROJECT_TITLE_MAX_LEN } from '@/lib/deriveAutoProjectTitle';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/hooks/useAuth';
import { languages, Language } from '@/i18n';

const RECENT_PROJECT_LIMIT = 5;
const RECENT_PROJECT_EXPAND_BATCH = 5;

const SIDEBAR_ROW =
  'mx-4 flex h-11 w-[calc(100%-2rem)] shrink-0 cursor-pointer items-center gap-3 rounded-lg border border-transparent px-3 text-left text-sm font-semibold text-[#e8e5de]/[0.83] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-blue-500/50 hover:border-[#2e2c28] hover:bg-[#e8e5de]/[0.04] hover:text-[#e8e5de]';

const SIDEBAR_ROW_ACTIVE = 'border-[#2e2c28] bg-[#e8e5de]/[0.06] text-[#e8e5de]';

const COLLAPSED_ICON_NAV =
  'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-transparent text-[#e8e5de]/70 transition-colors hover:border-[#2e2c28] hover:bg-[#e8e5de]/10 hover:text-[#e8e5de]';

function projectTitle(project: Project) {
  return (project.title || '').trim() || '—';
}

export interface ProjectSidebarProps {
  projects: Project[];
  currentProjectId: string;
  onSelectProject: (projectId: string) => void;
  /** Opens the workspace transition page (composer); does not create a project in the sidebar dialog. */
  onOpenWorkspaceStart: () => void;
  onDeleteProject: (projectId: string) => void;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  /** Second line under product name (e.g. start page vs auth subtitle). */
  brandSubtitle?: string;
  /** Desktop expanded width (px) at md+; ignored when collapsed or on narrow viewports. */
  expandedWidthPx?: number;
  /** Inline rename (e.g. double-click title); omitted when projects not ready. */
  onRenameProject?: (projectId: string, newTitle: string) => void;
}

export function ProjectSidebar({
  projects,
  currentProjectId,
  onSelectProject,
  onOpenWorkspaceStart,
  onDeleteProject,
  mobileOpen,
  onMobileOpenChange,
  collapsed,
  onCollapsedChange,
  brandSubtitle: brandSubtitleProp,
  expandedWidthPx,
  onRenameProject,
}: ProjectSidebarProps) {
  const { t, language, setLanguage } = useLanguage();
  const { user, signOut } = useAuth();
  const location = useLocation();
  const brandSubtitle = brandSubtitleProp ?? t.auth.subtitle;

  const [projectSearch, setProjectSearch] = useState('');
  /** Extra rows beyond `RECENT_PROJECT_LIMIT` when not searching (increments by batch). */
  const [recentListExtra, setRecentListExtra] = useState(0);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState('');
  const skipCommitOnBlurRef = useRef(false);

  const userInitial = user?.email?.charAt(0).toUpperCase() || 'U';
  const userAvatar = (user as { user_metadata?: { avatar_url?: string }; avatar_url?: string })
    ?.user_metadata?.avatar_url || (user as { avatar_url?: string })?.avatar_url;

  const sortedFilteredProjects = useMemo(() => {
    const q = projectSearch.trim().toLowerCase();
    const sorted = [...projects].sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
    if (!q) return sorted;
    return sorted.filter((p) => projectTitle(p).toLowerCase().includes(q));
  }, [projects, projectSearch]);

  const isSearching = projectSearch.trim().length > 0;

  useEffect(() => {
    if (isSearching) setRecentListExtra(0);
  }, [isSearching]);

  const listProjects = useMemo(() => {
    if (isSearching) return sortedFilteredProjects;
    const cap = RECENT_PROJECT_LIMIT + recentListExtra;
    return sortedFilteredProjects.slice(0, Math.min(cap, sortedFilteredProjects.length));
  }, [isSearching, sortedFilteredProjects, recentListExtra]);

  const hasMoreRecentInList =
    !isSearching && sortedFilteredProjects.length > RECENT_PROJECT_LIMIT + recentListExtra;

  const beginEditTitle = (project: Project) => {
    if (!onRenameProject) return;
    setEditingProjectId(project.id);
    setEditDraft((project.title || '').trim());
  };

  const commitRename = (project: Project) => {
    if (!onRenameProject) {
      setEditingProjectId(null);
      return;
    }
    const prev = (project.title || '').trim();
    const next = editDraft.trim();
    if (!next) {
      setEditingProjectId(null);
      return;
    }
    const capped = next.slice(0, AUTO_PROJECT_TITLE_MAX_LEN);
    if (capped !== prev) {
      onRenameProject(project.id, capped);
    }
    setEditingProjectId(null);
  };

  const cancelRename = () => {
    skipCommitOnBlurRef.current = true;
    setEditingProjectId(null);
  };

  const renderProjectRow = (project: Project) => (
    <div
      key={project.id}
      role="button"
      tabIndex={0}
      className={cn(
        // Grid keeps [dot | title | delete] inside the sidebar rail; flex+flex-1 was pushing the action past the rail edge.
        'group mx-2 grid min-h-10 w-full min-w-0 max-w-full grid-cols-[auto_minmax(0,1fr)_2rem] items-center gap-2 rounded-lg border px-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-blue-500/50',
        'border-transparent text-[#e8e5de]/[0.83]',
        currentProjectId === project.id
          ? 'border-[#2e2c28] bg-[#e8e5de]/[0.06] text-[#e8e5de]'
          : 'hover:border-[#2e2c28] hover:bg-[#e8e5de]/[0.04] hover:text-[#e8e5de]',
      )}
      onClick={() => {
        if (editingProjectId === project.id) return;
        onSelectProject(project.id);
        onMobileOpenChange(false);
      }}
      onKeyDown={(e) => {
        if (editingProjectId === project.id) return;
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        onSelectProject(project.id);
        onMobileOpenChange(false);
      }}
    >
      <span className="h-2 w-2 shrink-0 place-self-center rounded-full bg-[#e8e5de]/[0.35]" aria-hidden />
      <div className="min-w-0 overflow-hidden">
        {editingProjectId === project.id && onRenameProject ? (
          <Input
            value={editDraft}
            onChange={(e) =>
              setEditDraft(e.target.value.slice(0, AUTO_PROJECT_TITLE_MAX_LEN))
            }
            onClick={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
            onBlur={() => {
              if (skipCommitOnBlurRef.current) {
                skipCommitOnBlurRef.current = false;
                return;
              }
              commitRename(project);
            }}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') {
                e.preventDefault();
                (e.currentTarget as HTMLInputElement).blur();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelRename();
              }
            }}
            maxLength={AUTO_PROJECT_TITLE_MAX_LEN}
            autoFocus
            className="h-7 min-w-0 border-[#2e2c28] bg-[#201e1b] px-2 text-[14px] font-medium leading-none text-[#e8e5de] placeholder:text-[#9a9a98] focus-visible:ring-1 focus-visible:ring-blue-500/50"
            aria-label={t.sidebar.projectNamePlaceholder}
          />
        ) : (
          <TooltipProvider delayDuration={400}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className={cn(
                    'block truncate text-[14px] font-medium leading-none',
                    onRenameProject ? 'cursor-text' : 'cursor-default',
                  )}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    beginEditTitle(project);
                  }}
                >
                  {projectTitle(project)}
                </span>
              </TooltipTrigger>
              <TooltipContent
                side="right"
                className="max-w-xs border-[#2e2c28] bg-[#282623] text-[#e8e5de]"
              >
                <div>
                  {projectTitle(project)}
                  {onRenameProject ? (
                    <div className="mt-1 text-xs font-normal text-[#e8e5de]/70">
                      {t.sidebar.renameProjectHint}
                    </div>
                  ) : null}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
      <div className="flex w-8 shrink-0 justify-center justify-self-end" onClick={(e) => e.stopPropagation()}>
        <TooltipProvider delayDuration={400}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className={cn('inline-flex', projects.length <= 1 ? 'cursor-not-allowed' : '')}>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className={cn(
                    'h-8 w-8',
                    projects.length <= 1
                      ? 'cursor-not-allowed text-[#e8e5de]/22 hover:bg-transparent'
                      : 'text-rose-200/40 hover:bg-rose-500/[0.07] hover:text-rose-200/65 focus-visible:ring-2 focus-visible:ring-rose-300/25',
                  )}
                  disabled={projects.length <= 1}
                  aria-label={t.sidebar.deleteConversation}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (projects.length > 1) onDeleteProject(project.id);
                  }}
                >
                  <Trash2 className="h-4 w-4" strokeWidth={2} aria-hidden />
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent
              side="left"
              className="max-w-xs border-[#2e2c28] bg-[#282623] text-[#e8e5de]"
            >
              {projects.length <= 1 ? t.sidebar.keepOneConversation : t.sidebar.deleteConversation}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  );

  return (
    <>
      {mobileOpen ? (
        <button
          type="button"
          aria-label={t.common.close}
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => onMobileOpenChange(false)}
        />
      ) : null}

      <aside
        aria-label={t.sidebar.workspaceNavigation}
        className={cn(
          'flex h-full min-h-0 shrink-0 flex-col border-r border-[#2e2c28] bg-[#1a1916] text-sm',
          'transition-[transform,width] duration-200 ease-in-out',
          'w-60 max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-50 max-md:shadow-2xl',
          mobileOpen ? 'max-md:translate-x-0' : 'max-md:pointer-events-none max-md:-translate-x-full',
          'md:pointer-events-auto md:relative md:z-auto md:translate-x-0',
          collapsed
            ? 'md:w-12'
            : expandedWidthPx !== undefined
              ? 'md:w-[var(--sidebar-expanded)] md:min-w-[240px] md:max-w-[420px]'
              : 'md:w-60',
        )}
        style={
          !collapsed && expandedWidthPx !== undefined
            ? ({ ['--sidebar-expanded' as string]: `${expandedWidthPx}px` } as React.CSSProperties)
            : undefined
        }
      >
        <TooltipProvider delayDuration={300}>
          {/* Desktop collapsed: expand, new project, account nav icons */}
          <div
            className={cn(
              'hidden min-h-0 w-full shrink-0 flex-col items-center gap-1 overflow-y-auto overflow-x-hidden border-b border-[#2e2c28] py-2',
              collapsed ? 'md:flex' : 'md:hidden',
            )}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 text-[#e8e5de]/80 hover:bg-[#e8e5de]/10 hover:text-[#e8e5de]"
                  onClick={() => onCollapsedChange(false)}
                  aria-label={t.sidebar.expandSidebar}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right" className="border-[#2e2c28] bg-[#282623] text-[#e8e5de]">
                {t.sidebar.expandSidebar}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 text-[#e8e5de]/80 hover:bg-[#e8e5de]/10 hover:text-[#e8e5de]"
                  onClick={() => onOpenWorkspaceStart()}
                  aria-label={t.sidebar.newConversation}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right" className="border-[#2e2c28] bg-[#282623] text-[#e8e5de]">
                {t.sidebar.newConversation}
              </TooltipContent>
            </Tooltip>

            <NavLink
              to="/catalog/subagents"
              className={({ isActive }) =>
                cn(COLLAPSED_ICON_NAV, isActive && SIDEBAR_ROW_ACTIVE)
              }
              aria-label={t.sidebar.navProfessionalSubagents}
            >
              <Bot className="h-4 w-4" />
            </NavLink>
            <NavLink
              to="/catalog/skills"
              className={({ isActive }) =>
                cn(COLLAPSED_ICON_NAV, isActive && SIDEBAR_ROW_ACTIVE)
              }
              aria-label={t.sidebar.navDedicatedSkills}
            >
              <Puzzle className="h-4 w-4" />
            </NavLink>
            <NavLink
              to="/knowledge"
              className={({ isActive }) =>
                cn(COLLAPSED_ICON_NAV, isActive && SIDEBAR_ROW_ACTIVE)
              }
              aria-label={t.sidebar.navKnowledgeBase}
            >
              <BookOpen className="h-4 w-4" />
            </NavLink>
            <NavLink
              to="/account/overview"
              className={({ isActive }) =>
                cn(
                  COLLAPSED_ICON_NAV,
                  (isActive || location.pathname === '/account') && SIDEBAR_ROW_ACTIVE,
                )
              }
              aria-label={t.sidebar.navAccountOverview}
            >
              <LayoutDashboard className="h-4 w-4" />
            </NavLink>
            <NavLink
              to="/billing"
              end
              className={({ isActive }) =>
                cn(COLLAPSED_ICON_NAV, isActive && SIDEBAR_ROW_ACTIVE)
              }
              aria-label={t.billing.navBilling}
            >
              <CreditCard className="h-4 w-4" />
            </NavLink>
          </div>
        </TooltipProvider>

        {/* Expanded chrome */}
        <div
          className={cn(
            'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden',
            collapsed ? 'md:hidden' : 'flex',
          )}
        >
          <div className="flex h-[52px] shrink-0 items-center justify-between gap-2 border-b border-[#2e2c28] px-3">
            <div className="flex min-w-0 flex-1 items-start gap-2.5">
              <div
                className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[10px] border border-[#2e2c28] bg-gradient-to-br from-[#e8e5de]/10 to-[#e8e5de]/5"
                aria-hidden
              >
                <Shield className="h-4 w-4 text-[#e8e5de]" />
              </div>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-[15px] font-semibold tracking-tight text-[#e8e5de]">
                  {t.sidebar.brandTitle}
                </div>
                <div className="truncate text-xs text-[#e8e5de]/55">{brandSubtitle}</div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-0.5">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-[#e8e5de]/70 hover:bg-[#e8e5de]/10 hover:text-[#e8e5de]"
                    aria-label={t.sidebar.chooseLanguage}
                  >
                    <Globe className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  className="z-50 border-[#2e2c28] bg-[#282623] text-[#e8e5de]"
                >
                  {(Object.keys(languages) as Language[]).map((lang) => (
                    <DropdownMenuItem
                      key={lang}
                      className={cn(
                        'focus:bg-[#e8e5de]/10',
                        language === lang ? 'bg-[#e8e5de]/10' : '',
                      )}
                      onClick={() => setLanguage(lang)}
                    >
                      {languages[lang].nativeName}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 rounded-full text-[#e8e5de]/80 hover:bg-[#e8e5de]/10"
                    aria-label={t.nav.profile}
                  >
                    <Avatar className="h-7 w-7">
                      <AvatarImage src={userAvatar} />
                      <AvatarFallback className="bg-[#e8e5de]/10 text-xs text-[#e8e5de]">
                        {userInitial}
                      </AvatarFallback>
                    </Avatar>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  className="z-50 min-w-[12rem] border-[#2e2c28] bg-[#282623] text-[#e8e5de]"
                >
                  <DropdownMenuItem className="py-1 text-xs text-[#e8e5de]/50" disabled>
                    {user?.email}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator className="bg-[#2e2c28]" />
                  <DropdownMenuItem asChild className="focus:bg-[#e8e5de]/10">
                    <RouterLink to="/account/overview" className="cursor-pointer">
                      <LayoutDashboard className="mr-2 h-4 w-4" />
                      {t.account.navOverview}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild className="focus:bg-[#e8e5de]/10">
                    <RouterLink to="/account/settings" className="cursor-pointer">
                      <UserCircle className="mr-2 h-4 w-4" />
                      {t.account.navSettings}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild className="focus:bg-[#e8e5de]/10">
                    <RouterLink to="/billing" className="cursor-pointer">
                      <CreditCard className="mr-2 h-4 w-4" />
                      {t.billing.navBilling}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild className="focus:bg-[#e8e5de]/10">
                    <RouterLink to="/usage" className="cursor-pointer">
                      <BarChart3 className="mr-2 h-4 w-4" />
                      {t.billing.navUsage}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator className="bg-[#2e2c28]" />
                  <DropdownMenuItem
                    className="text-red-400 focus:bg-red-400/10 focus:text-red-400"
                    onClick={signOut}
                  >
                    <LogOut className="mr-2 h-4 w-4" />
                    {t.nav.signOut}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="hidden h-8 w-8 text-[#e8e5de]/80 hover:bg-[#e8e5de]/10 hover:text-[#e8e5de] md:flex"
                onClick={() => onCollapsedChange(true)}
                aria-label={t.sidebar.collapseSidebar}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-[#e8e5de]/80 hover:bg-[#e8e5de]/10 hover:text-[#e8e5de] md:hidden"
                onClick={() => onMobileOpenChange(false)}
                aria-label={t.common.close}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden pt-1">
            <button
              type="button"
              className={cn(SIDEBAR_ROW, 'mt-1')}
              onClick={() => onOpenWorkspaceStart()}
            >
              <PenLine className="h-[18px] w-[18px] shrink-0 text-[#9a9a98]" aria-hidden />
              <span className="truncate">{t.sidebar.newConversation}</span>
            </button>

            <nav className="mt-1 flex shrink-0 flex-col gap-1" aria-label={t.sidebar.featureNav}>
              <NavLink
                to="/catalog/subagents"
                className={({ isActive }) => cn(SIDEBAR_ROW, isActive ? SIDEBAR_ROW_ACTIVE : '')}
              >
                <Bot className="h-[18px] w-[18px] shrink-0 text-[#9a9a98]" aria-hidden />
                <span className="truncate">{t.sidebar.navProfessionalSubagents}</span>
              </NavLink>
              <NavLink
                to="/catalog/skills"
                className={({ isActive }) => cn(SIDEBAR_ROW, isActive ? SIDEBAR_ROW_ACTIVE : '')}
              >
                <Puzzle className="h-[18px] w-[18px] shrink-0 text-[#9a9a98]" aria-hidden />
                <span className="truncate">{t.sidebar.navDedicatedSkills}</span>
              </NavLink>
              <NavLink
                to="/knowledge"
                className={({ isActive }) => cn(SIDEBAR_ROW, isActive ? SIDEBAR_ROW_ACTIVE : '')}
              >
                <BookOpen className="h-[18px] w-[18px] shrink-0 text-[#9a9a98]" aria-hidden />
                <span className="truncate">{t.sidebar.navKnowledgeBase}</span>
              </NavLink>
              <NavLink
                to="/account/overview"
                className={({ isActive }) =>
                  cn(
                    SIDEBAR_ROW,
                    isActive || location.pathname === '/account' ? SIDEBAR_ROW_ACTIVE : '',
                  )
                }
              >
                <LayoutDashboard className="h-[18px] w-[18px] shrink-0 text-[#9a9a98]" aria-hidden />
                <span className="truncate">{t.sidebar.navAccountOverview}</span>
              </NavLink>
              <NavLink
                to="/billing"
                end
                className={({ isActive }) => cn(SIDEBAR_ROW, isActive ? SIDEBAR_ROW_ACTIVE : '')}
              >
                <CreditCard className="h-[18px] w-[18px] shrink-0 text-[#9a9a98]" aria-hidden />
                <span className="truncate">{t.billing.navBilling}</span>
              </NavLink>
            </nav>

            <hr className="mx-4 my-2 shrink-0 border-[#2e2c28]" />

            <div className="flex min-w-0 shrink-0 items-center gap-2 px-3 pb-2 pt-0.5">
              <span className="shrink-0 truncate text-xs font-semibold tracking-tight text-[#9a9a98]">
                {t.sidebar.conversationHistory}
              </span>
              <div className="relative min-w-0 flex-1">
                <Search
                  className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#9a9a98]"
                  aria-hidden
                />
                <Input
                  value={projectSearch}
                  onChange={(e) => setProjectSearch(e.target.value)}
                  placeholder={t.sidebar.searchProjects}
                  className="h-8 border-[#2e2c28] bg-[#201e1b] pl-8 text-sm text-[#e8e5de] placeholder:text-[#9a9a98]"
                  aria-label={t.sidebar.searchProjects}
                />
              </div>
            </div>

            <ScrollArea className="min-h-0 min-w-0 flex-1">
              <div
                className="flex min-w-0 flex-col gap-1 px-2 pb-4 pt-0.5"
                aria-label={t.sidebar.projectListRegion}
              >
                {listProjects.map((project) => renderProjectRow(project))}

                {hasMoreRecentInList ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className="mx-2 flex h-10 w-[calc(100%-1rem)] shrink-0 items-center justify-between rounded-lg px-3 text-sm font-medium text-[#9a9a98] hover:bg-[#e8e5de]/10 hover:text-[#e8e5de]"
                    aria-label={t.sidebar.moreHistoryProjectsAria}
                    onClick={() =>
                      setRecentListExtra((n) => n + RECENT_PROJECT_EXPAND_BATCH)
                    }
                  >
                    <span>{t.sidebar.moreHistoryProjects}</span>
                    <ChevronDown className="h-4 w-4 shrink-0 opacity-80" aria-hidden />
                  </Button>
                ) : null}
              </div>
            </ScrollArea>
          </div>
        </div>

      </aside>
    </>
  );
}
