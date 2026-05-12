import { Link as RouterLink } from 'react-router-dom';
import { Globe, LogOut, FileText, CreditCard, BarChart3, LayoutDashboard, UserCircle, Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { useAuth } from '@/hooks/useAuth';
import { useLanguage } from '@/contexts/LanguageContext';
import { languages, Language } from '@/i18n';

interface TopNavbarProps {
  /** Opens the project sidebar on small viewports (brand lives in the sidebar). */
  onMobileSidebarOpen?: () => void;
  blocksCount?: number;
}

export function TopNavbar({
  onMobileSidebarOpen,
  blocksCount = 0,
}: TopNavbarProps) {
  const { user, signOut } = useAuth();
  const { language, setLanguage, t } = useLanguage();

  const userInitial = user?.email?.charAt(0).toUpperCase() || 'U';
  const userAvatar = (user as any)?.user_metadata?.avatar_url || (user as any)?.avatar_url;

  return (
    <div className="flex h-11 shrink-0 items-center bg-sidebar px-2 md:px-3">
      {onMobileSidebarOpen ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="mr-1.5 h-8 w-8 shrink-0 md:hidden"
          onClick={onMobileSidebarOpen}
          aria-label={t.sidebar.openSidebar}
        >
          <Menu className="h-4 w-4" />
        </Button>
      ) : null}

      {/* Workspace strip */}
      <div className="flex min-w-0 flex-1 items-center gap-2 md:flex-initial">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <FileText className="h-3.5 w-3.5 text-primary" />
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground">{t.workspace.securityWorkspace}</span>
          {blocksCount > 0 && (
            <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
              {blocksCount} {t.workspace.blocks}
            </span>
          )}
        </div>
      </div>

      {/* Spacer to push right section to the end */}
      <div className="flex-1" />

      {/* Right Section - Actions */}
      <div className="flex items-center gap-1">
        {/* Language Switcher */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Globe className="h-3.5 w-3.5 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="bg-popover border border-border z-50">
            {(Object.keys(languages) as Language[]).map((lang) => (
              <DropdownMenuItem
                key={lang}
                onClick={() => setLanguage(lang)}
                className={language === lang ? "bg-accent" : ""}
              >
                {languages[lang].nativeName}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full"
              data-testid="user-menu-trigger"
            >
              <Avatar className="h-7 w-7">
                <AvatarImage src={userAvatar} />
                <AvatarFallback className="bg-primary/10 text-primary text-xs">
                  {userInitial}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[12rem] bg-popover border border-border z-50">
            <DropdownMenuItem className="text-muted-foreground text-xs py-1" disabled>
              {user?.email}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <RouterLink to="/account/overview" className="cursor-pointer">
                <LayoutDashboard className="w-4 h-4 mr-2" />
                {t.account.navOverview}
              </RouterLink>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <RouterLink to="/account/settings" className="cursor-pointer">
                <UserCircle className="w-4 h-4 mr-2" />
                {t.account.navSettings}
              </RouterLink>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <RouterLink to="/billing" className="cursor-pointer">
                <CreditCard className="w-4 h-4 mr-2" />
                {t.billing.navBilling}
              </RouterLink>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <RouterLink to="/usage" className="cursor-pointer">
                <BarChart3 className="w-4 h-4 mr-2" />
                {t.billing.navUsage}
              </RouterLink>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut} className="text-destructive focus:text-destructive">
              <LogOut className="w-4 h-4 mr-2" />
              {t.nav.signOut}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
