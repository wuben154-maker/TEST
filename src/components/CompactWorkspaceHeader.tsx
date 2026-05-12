import { Link as RouterLink } from 'react-router-dom';
import { Shield, LogOut, Globe, CreditCard, BarChart3, LayoutDashboard, UserCircle } from 'lucide-react';
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

export interface CompactWorkspaceHeaderProps {
  /** Opens project sidebar (same as transition / start page). */
  onMenuClick: () => void;
  /** Second line under "SecManus", e.g. `t.startPage.subtitle`. */
  subtitle: string;
}

/**
 * Minimal top bar for transition/start, billing, usage: SecManus + sidebar, language, account
 * (with Billing / Usage links). No workspace share/export or "Security workspace" strip.
 */
export function CompactWorkspaceHeader({ onMenuClick, subtitle }: CompactWorkspaceHeaderProps) {
  const { user, signOut } = useAuth();
  const { language, setLanguage, t } = useLanguage();

  const userInitial = user?.email?.charAt(0).toUpperCase() || 'U';
  const userAvatar = (user as { user_metadata?: { avatar_url?: string }; avatar_url?: string })
    ?.user_metadata?.avatar_url || (user as { avatar_url?: string })?.avatar_url;

  return (
    <header className="flex-shrink-0 flex items-center justify-between px-4 sm:px-6 py-4 border-b border-border/60 bg-sidebar/95 backdrop-blur-sm">
      <button
        type="button"
        onClick={onMenuClick}
        className="flex items-center gap-3 min-w-0 text-left rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 hover:bg-primary/20 transition-colors">
          <Shield className="w-5 h-5 text-primary" />
        </div>
        <div className="min-w-0">
          <h1 className="text-base font-semibold text-foreground truncate">{t.sidebar.brandTitle}</h1>
          <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
        </div>
      </button>
      <div className="flex items-center gap-1 shrink-0">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-9 w-9">
              <Globe className="w-4 h-4 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="bg-popover border border-border z-50">
            {(Object.keys(languages) as Language[]).map((lang) => (
              <DropdownMenuItem
                key={lang}
                onClick={() => setLanguage(lang)}
                className={language === lang ? 'bg-accent' : ''}
              >
                {languages[lang].nativeName}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full">
              <Avatar className="h-8 w-8">
                <AvatarImage src={userAvatar} />
                <AvatarFallback className="bg-primary/10 text-primary text-sm">
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
    </header>
  );
}
