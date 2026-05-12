import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Globe, LogOut } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useLanguage } from '@/contexts/LanguageContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { languages, type Language } from '@/i18n';
import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';
import { MarketingMegaMenus } from '@/components/marketing/MarketingMegaMenus';
import { MARKETING_SOLUTION_SLUGS, SOLUTION_SLUG_TO_I18N_KEY } from '@/lib/marketing-routes';

type MarketingSiteChromeProps = {
  children: ReactNode;
  /** When false, skip scroll listeners / sticky header border (e.g. short pages). */
  stickyHeader?: boolean;
};

export function MarketingSiteChrome({ children, stickyHeader = true }: MarketingSiteChromeProps) {
  const { user, signOut } = useAuth();
  const { t, language, setLanguage } = useLanguage();
  const { pathname, hash } = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    if (!stickyHeader) return;
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [stickyHeader]);

  const closeNav = () => setNavOpen(false);

  const gridBg = (
    <div
      className="pointer-events-none fixed inset-0 z-0 opacity-[0.06]"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 40 40'%3E%3Cpath d='M0 0h40M0 0v40' fill='none' stroke='%236366f1' stroke-opacity='1' stroke-width='1'/%3E%3C/svg%3E")`,
        backgroundSize: '40px 40px',
      }}
      aria-hidden
    />
  );

  const halos = (
    <div
      className="pointer-events-none fixed inset-0 z-0"
      aria-hidden
      style={{
        background: `
            radial-gradient(ellipse 70% 50% at 50% 20%, rgba(49, 46, 129, 0.08) 0%, transparent 55%),
            radial-gradient(ellipse 50% 45% at 80% 70%, rgba(76, 29, 149, 0.05) 0%, transparent 50%),
            radial-gradient(ellipse 100% 40% at 50% 100%, rgba(0, 0, 0, 0.25) 0%, transparent 60%)
          `,
        backgroundAttachment: 'fixed',
      }}
    />
  );

  const navLinkClass = (active: boolean) =>
    cn(
      'rounded-lg px-3 py-2 text-[14px] no-underline transition-colors focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none',
      active
        ? 'bg-[#e8e5de]/[0.08] text-[#e8e5de]'
        : 'text-[#e8e5de]/83 hover:bg-[#e8e5de]/[0.04] hover:text-[#e8e5de]',
    );

  const langAriaLabel = `${t.sidebar.chooseLanguage}: ${languages[language].nativeName}`;

  const onSecurityAgentNav = pathname === '/' && hash === '#features';
  const onPricing = pathname === '/pricing';

  const mm = t.marketing.megaMenu;

  const userAvatar =
    (user as { user_metadata?: { avatar_url?: string }; avatar_url?: string } | null)?.user_metadata?.avatar_url ||
    user?.avatar_url;
  const userInitial = user?.email?.charAt(0).toUpperCase() || user?.username?.charAt(0).toUpperCase() || 'U';

  const mobileSolutionLinks = MARKETING_SOLUTION_SLUGS.map((slug) => {
    const key = SOLUTION_SLUG_TO_I18N_KEY[slug];
    const item = mm[key as keyof typeof mm] as { name: string };
    return (
      <Link
        key={slug}
        to={`/solutions/${slug}`}
        className={cn(navLinkClass(pathname === `/solutions/${slug}`))}
        onClick={closeNav}
      >
        {item.name}
      </Link>
    );
  });

  return (
    <div className="relative min-h-dvh bg-[#1a1916] font-marketing text-[14px] leading-relaxed text-[#e8e5de] antialiased motion-reduce:scroll-auto [&_*]:box-border">
      {halos}
      {gridBg}

      <a
        href="#main"
        className={cn(
          'absolute left-3 top-3 z-[200] -m-px h-px w-px overflow-hidden border-0 p-0 whitespace-nowrap',
          'focus:fixed focus:left-3 focus:top-3 focus:m-0 focus:h-auto focus:w-auto focus:overflow-visible focus:rounded-lg focus:bg-[#282623] focus:px-3 focus:py-2 focus:text-[#e8e5de] focus:underline focus:[clip:auto]',
          'focus:shadow-[0_0_0_2px_rgba(59,130,246,0.5)]',
        )}
      >
        {t.marketing.skipToMain}
      </a>

      <header
        className={cn(
          'sticky top-0 z-[100] flex h-16 items-center transition-[background-color,border-color,backdrop-filter] duration-200',
          stickyHeader && scrolled
            ? 'border-b border-[#2e2c28] bg-[#1a1916]/92 backdrop-blur-md'
            : 'border-b border-transparent',
        )}
      >
        <div className="relative z-[1] mx-auto flex w-full max-w-[1200px] items-center justify-between gap-6 px-4 md:px-6">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-3 rounded-lg text-[#e8e5de] no-underline focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none"
          >
            <span className="h-9 w-9 text-[#e8e5de]" aria-hidden>
              <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M24 4L8 10v12c0 9.5 6.2 18.4 16 22 9.8-3.6 16-12.5 16-22V10L24 4z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
                <circle cx="24" cy="23" r="2.25" stroke="currentColor" strokeWidth="1.5" />
                <path
                  d="M18.5 30.5c1.9-2.2 4-3.3 5.5-3.3s3.6 1.1 5.5 3.3"
                  stroke="currentColor"
                  strokeWidth="1.25"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-[16px] font-semibold tracking-[-0.3px]">{t.marketing.brandName}</span>
              <span className="text-[12px] font-normal text-[#e8e5de]/35">{t.marketing.brandSubtitle}</span>
            </span>
          </Link>

          <button
            type="button"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#e8e5de]/35 bg-transparent text-[#e8e5de] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none lg:hidden"
            aria-expanded={navOpen}
            aria-controls="site-nav"
            aria-label={navOpen ? t.marketing.closeMenu : t.marketing.openMenu}
            onClick={() => setNavOpen((o) => !o)}
          >
            <span className="flex w-[18px] flex-col gap-[5px]" aria-hidden>
              <span className="h-0.5 rounded-sm bg-current" />
              <span className="h-0.5 rounded-sm bg-current" />
              <span className="h-0.5 rounded-sm bg-current" />
            </span>
          </button>

          <nav
            id="site-nav"
            className={cn(
              'font-marketing lg:static lg:flex lg:flex-1 lg:items-center lg:justify-end',
              navOpen
                ? 'fixed left-4 right-4 top-[72px] z-[101] max-h-[min(70vh,calc(100dvh-96px))] overflow-y-auto rounded-xl border border-[#2e2c28] bg-[#201e1b] p-3 shadow-xl lg:max-h-none lg:overflow-visible lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none'
                : 'hidden lg:flex',
            )}
            aria-label={t.marketing.mainNavAria}
          >
            <div className="flex flex-col gap-1 lg:flex-row lg:items-center lg:gap-2">
              <MarketingMegaMenus t={t} onNavigate={closeNav} triggerClassName={navLinkClass(false)} />
              <Link
                to={{ pathname: '/', hash: '#features' }}
                className={navLinkClass(onSecurityAgentNav)}
                onClick={closeNav}
              >
                {t.marketing.navSecurityAgent}
              </Link>
              <Link to="/pricing" className={navLinkClass(onPricing)} onClick={closeNav}>
                {t.marketing.navPricing}
              </Link>

              <div className="mt-2 border-t border-[#2e2c28] pt-2 lg:hidden">
                <p className="mb-1 px-3 text-[11px] font-medium uppercase tracking-wide text-[#e8e5de]/35">
                  {t.marketing.navSolutions}
                </p>
                <div className="flex flex-col gap-1">{mobileSolutionLinks}</div>
              </div>
              <div className="mt-3 border-t border-[#2e2c28] pt-2 lg:hidden">
                <p className="mb-1 px-3 text-[11px] font-medium uppercase tracking-wide text-[#e8e5de]/35">
                  {t.marketing.navResources}
                </p>
                <Link to="/blog" className={navLinkClass(pathname === '/blog')} onClick={closeNav}>
                  {mm.blog.name}
                </Link>
                <Link to="/help" className={navLinkClass(pathname === '/help')} onClick={closeNav}>
                  {mm.help.name}
                </Link>
                <Link to="/product-log" className={navLinkClass(pathname === '/product-log')} onClick={closeNav}>
                  {mm.productLog.name}
                </Link>
              </div>
            </div>
            <div className="my-3 h-px w-full bg-[#2e2c28] lg:my-0 lg:mx-4 lg:h-11 lg:w-px lg:shrink-0" />
            <div className="flex flex-wrap items-center gap-2 lg:justify-end lg:gap-3">
              {user ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className={cn(
                        'flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#e8e5de]/35 bg-[#e8e5de]/[0.04] transition-colors hover:bg-[#e8e5de]/[0.08] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none',
                      )}
                      aria-label={t.marketing.userMenuAria}
                      data-testid="official-site-user-menu-trigger"
                    >
                      <Avatar className="h-9 w-9 border border-[#2e2c28]">
                        <AvatarImage src={userAvatar} alt="" />
                        <AvatarFallback className="bg-[#282623] text-[13px] font-medium text-[#e8e5de]">
                          {userInitial}
                        </AvatarFallback>
                      </Avatar>
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    className="z-[150] min-w-[12rem] border-[#2e2c28] bg-[#201e1b] p-1 text-[#e8e5de] shadow-xl font-marketing"
                  >
                    <div className="max-w-[240px] truncate px-2 py-1.5 text-[12px] text-[#e8e5de]/65">
                      {user.email ?? user.username ?? user.id}
                    </div>
                    <DropdownMenuSeparator className="bg-[#2e2c28]" />
                    <DropdownMenuItem asChild className="cursor-pointer focus:bg-[#e8e5de]/10 focus:text-[#e8e5de]">
                      <Link to="/start" onClick={closeNav}>
                        {t.marketing.enterWorkspace}
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild className="cursor-pointer focus:bg-[#e8e5de]/10 focus:text-[#e8e5de]">
                      <Link to="/account/overview" onClick={closeNav}>
                        {t.sidebar.navAccountOverview}
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild className="cursor-pointer focus:bg-[#e8e5de]/10 focus:text-[#e8e5de]">
                      <Link to="/account/settings" onClick={closeNav}>
                        {t.account.navSettings}
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="bg-[#2e2c28]" />
                    <DropdownMenuItem
                      className="cursor-pointer text-[#e8e5de] focus:bg-[#e8e5de]/10 focus:text-[#e8e5de]"
                      onClick={() => {
                        closeNav();
                        void signOut();
                      }}
                    >
                      <LogOut className="mr-2 h-4 w-4 opacity-80" aria-hidden />
                      {t.nav.signOut}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className={cn(
                      'inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-[#e8e5de]/35 bg-transparent px-4 text-[13px] font-normal text-[#e8e5de] transition-colors hover:bg-[#e8e5de]/[0.06] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none lg:px-3',
                    )}
                    aria-label={langAriaLabel}
                  >
                    <Globe className="h-4 w-4 shrink-0 opacity-90" aria-hidden />
                    <span className="lg:hidden">{languages[language].nativeName}</span>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  className="z-[150] min-w-[10rem] border-[#2e2c28] bg-[#201e1b] p-1 text-[#e8e5de] shadow-xl font-marketing"
                >
                  {(Object.keys(languages) as Language[]).map((lang) => (
                    <DropdownMenuItem
                      key={lang}
                      onClick={() => {
                        setLanguage(lang);
                        closeNav();
                      }}
                      className={cn(
                        'cursor-pointer rounded-md focus:bg-[#e8e5de]/10 focus:text-[#e8e5de]',
                        language === lang ? 'bg-[#e8e5de]/10' : '',
                      )}
                    >
                      {languages[lang].nativeName}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>

              {!user ? (
                <Link
                  to="/auth"
                  className="inline-flex min-h-10 cursor-pointer items-center justify-center whitespace-nowrap rounded-lg border border-[#e8e5de]/35 bg-transparent px-4 text-[13px] font-normal text-[#e8e5de] no-underline transition-colors hover:bg-[#e8e5de]/[0.06] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none"
                  data-testid="official-site-sign-in"
                  onClick={closeNav}
                >
                  {t.marketing.signIn}
                </Link>
              ) : null}
            </div>
          </nav>
        </div>
      </header>

      {children}

      <footer className="relative z-[1] border-t border-[#2e2c28] py-12">
        <div className="mx-auto max-w-[1200px] px-4 md:px-6">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <h3 className="mb-3 text-[14px] font-semibold">{t.marketing.footerProduct}</h3>
              <ul className="space-y-2 text-[14px] text-[#e8e5de]/83">
                <li>
                  <Link to={{ pathname: '/', hash: '#features' }} className="text-inherit hover:text-[#e8e5de]">
                    {t.marketing.navSecurityAgent}
                  </Link>
                </li>
                <li>
                  <Link to="/pricing" className="text-inherit hover:text-[#e8e5de]">
                    {t.marketing.navPricing}
                  </Link>
                </li>
                <li>
                  <Link to="/auth" className="text-inherit hover:text-[#e8e5de]">
                    {t.marketing.signIn}
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="mb-3 text-[14px] font-semibold">{t.marketing.footerSolutions}</h3>
              <ul className="space-y-2 text-[14px] text-[#e8e5de]/83">
                {MARKETING_SOLUTION_SLUGS.map((slug) => {
                  const key = SOLUTION_SLUG_TO_I18N_KEY[slug];
                  const item = mm[key as keyof typeof mm] as { name: string };
                  return (
                    <li key={slug}>
                      <Link to={`/solutions/${slug}`} className="text-inherit hover:text-[#e8e5de]">
                        {item.name}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
            <div>
              <h3 className="mb-3 text-[14px] font-semibold">{t.marketing.footerResources}</h3>
              <ul className="space-y-2 text-[14px] text-[#e8e5de]/83">
                <li>
                  <Link to="/blog" className="text-inherit hover:text-[#e8e5de]">
                    {mm.blog.name}
                  </Link>
                </li>
                <li>
                  <Link to="/help" className="text-inherit hover:text-[#e8e5de]">
                    {mm.help.name}
                  </Link>
                </li>
                <li>
                  <Link to="/product-log" className="text-inherit hover:text-[#e8e5de]">
                    {mm.productLog.name}
                  </Link>
                </li>
              </ul>
            </div>
            <div className="space-y-8">
              <div>
                <h3 className="mb-3 text-[14px] font-semibold">{t.marketing.footerCompany}</h3>
                <ul className="space-y-2 text-[14px] text-[#e8e5de]/83">
                  <li>
                    <Link to="/auth" className="text-inherit hover:text-[#e8e5de]">
                      {t.marketing.footerRegister}
                    </Link>
                  </li>
                  <li>
                    <a href="mailto:hello@example.com" className="text-inherit hover:text-[#e8e5de]">
                      {t.marketing.footerContact}
                    </a>
                  </li>
                </ul>
              </div>
              <div>
                <h3 className="mb-3 text-[14px] font-semibold">{t.marketing.footerLegal}</h3>
                <ul className="space-y-2 text-[14px] text-[#e8e5de]/83">
                  <li>
                    <span className="text-[#e8e5de]/35" title={t.marketing.pricingComingSoon}>
                      {t.marketing.footerTerms}
                    </span>
                  </li>
                  <li>
                    <span className="text-[#e8e5de]/35" title={t.marketing.pricingComingSoon}>
                      {t.marketing.footerPrivacy}
                    </span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <div className="mt-10 border-t border-[#2e2c28] pt-6 text-center text-[13px] text-[#9a9a98]">
            {t.marketing.footerCopyright}
          </div>
        </div>
      </footer>
    </div>
  );
}
