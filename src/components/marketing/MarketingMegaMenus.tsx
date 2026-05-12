import { Link } from 'react-router-dom';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { MARKETING_SOLUTION_SLUGS, SOLUTION_SLUG_TO_I18N_KEY } from '@/lib/marketing-routes';
import { cn } from '@/lib/utils';
import type { TranslationKeys } from '@/i18n';

type MarketingMegaMenusProps = {
  t: TranslationKeys;
  onNavigate: () => void;
  triggerClassName: string;
};

const megaPanelClass =
  'overflow-hidden rounded-[18px] border border-[#2e2c28] bg-[#201e1b]/95 p-0 shadow-xl backdrop-blur-md';

const megaItemClass =
  'block rounded-lg px-3 py-2 no-underline outline-none transition-colors hover:bg-[#e8e5de]/[0.06] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)]';

export function MarketingMegaMenus({ t, onNavigate, triggerClassName }: MarketingMegaMenusProps) {
  const mm = t.marketing.megaMenu;

  const whoSlugs = MARKETING_SOLUTION_SLUGS.slice(0, 3);
  const useCaseSlugs = MARKETING_SOLUTION_SLUGS.slice(3);

  const columnFor = (slugs: readonly (typeof MARKETING_SOLUTION_SLUGS)[number][]) =>
    slugs.map((slug) => {
      const key = SOLUTION_SLUG_TO_I18N_KEY[slug];
      const item = mm[key as keyof typeof mm] as { name: string; desc: string };
      return (
        <li key={slug}>
          <Link to={`/solutions/${slug}`} className={megaItemClass} onClick={onNavigate}>
            <span className="block text-[14px] font-medium text-[#e8e5de]">{item.name}</span>
            <span className="mt-1 block text-[13px] leading-snug text-[#e8e5de]/65">{item.desc}</span>
          </Link>
        </li>
      );
    });

  const resourceEntries = [
    { to: '/blog', item: mm.blog },
    { to: '/help', item: mm.help },
    { to: '/product-log', item: mm.productLog },
  ] as const;

  return (
    <div className="hidden items-center gap-1 lg:flex">
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger
          type="button"
          className={cn(
            triggerClassName,
            'inline-flex items-center gap-1 border-0 bg-transparent data-[state=open]:bg-[#e8e5de]/[0.08]',
          )}
        >
          {t.marketing.navSolutions}
          <span className="text-[12px] opacity-70" aria-hidden>
            ▾
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          sideOffset={10}
          className={cn(megaPanelClass, 'z-[150] w-[min(920px,calc(100vw-48px)))] font-marketing text-[#e8e5de]')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2">
            <div className="flex flex-col gap-3 border-[#e8e5de]/[0.08] p-5 md:border-r">
              <p className="text-[12px] font-medium text-[#e8e5de]/35">{mm.whoForTitle}</p>
              <ul className="flex flex-col gap-2">{columnFor(whoSlugs)}</ul>
            </div>
            <div className="flex flex-col gap-3 bg-[#1a1916]/40 p-5">
              <p className="text-[12px] font-medium text-[#e8e5de]/35">{mm.useCasesTitle}</p>
              <ul className="flex flex-col gap-2">{columnFor(useCaseSlugs)}</ul>
            </div>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu modal={false}>
        <DropdownMenuTrigger
          type="button"
          className={cn(
            triggerClassName,
            'inline-flex items-center gap-1 border-0 bg-transparent data-[state=open]:bg-[#e8e5de]/[0.08]',
          )}
        >
          {t.marketing.navResources}
          <span className="text-[12px] opacity-70" aria-hidden>
            ▾
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          sideOffset={10}
          className={cn(megaPanelClass, 'z-[150] w-[min(420px,calc(100vw-48px)))] font-marketing text-[#e8e5de]')}
        >
          <div className="p-5">
            <p className="mb-3 text-[12px] font-medium text-[#e8e5de]/35">{mm.resourcesSectionTitle}</p>
            <ul className="flex flex-col gap-2">
              {resourceEntries.map(({ to, item }) => (
                <li key={to}>
                  <Link to={to} className={megaItemClass} onClick={onNavigate}>
                    <span className="block text-[14px] font-medium text-[#e8e5de]">{item.name}</span>
                    <span className="mt-1 block text-[13px] leading-snug text-[#e8e5de]/65">{item.desc}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
