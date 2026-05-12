import { Fragment, useEffect, useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { MarketingSiteChrome } from '@/components/marketing/MarketingSiteChrome';
import { MarketingHomeComposer } from '@/components/MarketingHomeComposer';
import { OfficialSiteWorkflowSection } from '@/components/marketing/OfficialSiteWorkflowSection';
import { useLanguage } from '@/contexts/LanguageContext';
import { cn } from '@/lib/utils';

const FEATURE_KEYS = ['inquiry', 'binary', 'tracing', 'phishing'] as const;

const AUTH_BTN =
  'inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-[#e8e5de]/35 bg-transparent px-4 text-[13px] text-[#e8e5de] transition-colors hover:bg-[#e8e5de]/[0.06] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none';

/** Public marketing homepage — routed at `/`; see docs/Process/official-website/design.md */
export default function OfficialSite() {
  const { t } = useLanguage();
  const location = useLocation();

  useEffect(() => {
    document.title = t.marketing.docTitle;
  }, [t.marketing.docTitle]);

  useEffect(() => {
    const id = location.hash?.replace(/^#/, '').trim();
    if (!id) return;
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, [location.pathname, location.hash]);

  const flowChips = useMemo(
    () => [
      t.marketing.flowChipAlert,
      t.marketing.flowChipLead,
      t.marketing.flowChipSpecialists,
      t.marketing.flowChipEvidence,
      t.marketing.flowChipVerdict,
    ],
    [t],
  );

  const featureCards = useMemo(
    () =>
      FEATURE_KEYS.map((key) => {
        const f = t.marketing.features[key];
        return {
          title: f.title,
          desc: f.desc,
          tags: [f.tag1, f.tag2, f.tag3] as const,
          outputs: f.outputs,
          cta: f.cta,
        };
      }),
    [t],
  );

  return (
    <MarketingSiteChrome>
      <main id="main" className="relative z-[1]">
        {/* Hero */}
        <section aria-labelledby="hero-title" className="relative isolate overflow-x-clip px-4 pb-10 pt-8 md:px-6 md:pb-14 md:pt-12">
          <div
            className="pointer-events-none absolute inset-[-12%_-8%_0_-8%] z-0 blur-[42px]"
            aria-hidden
            style={{
              background: `
              radial-gradient(60% 45% at 50% 78%, rgba(99, 102, 241, 0.26) 0%, transparent 70%),
              radial-gradient(45% 35% at 28% 72%, rgba(167, 139, 250, 0.16) 0%, transparent 70%),
              radial-gradient(45% 35% at 72% 74%, rgba(165, 243, 252, 0.09) 0%, transparent 70%),
              linear-gradient(180deg, rgba(0, 0, 0, 0.32) 0%, transparent 38%)`,
              opacity: 0.92,
            }}
          />
          <div className="relative z-[1] mx-auto w-full max-w-[min(1200px,_100%)] text-center">
            <h1
              id="hero-title"
              data-testid="official-site-hero-title"
              className="mx-auto mb-3 flex max-w-[52ch] flex-col items-center gap-1 text-balance text-[clamp(32px,4.4vw,56px)] font-semibold leading-[1.1] tracking-[-0.6px] md:gap-1.5"
            >
              <span className="block">{t.marketing.heroLine1}</span>
              <span className="block">
                {t.marketing.heroLine2Start}
                <span
                  className="bg-[linear-gradient(110deg,#a5f3fc_0%,#6366f1_45%,#a78bfa_78%)] bg-clip-text text-transparent"
                  style={{ WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
                >
                  {t.marketing.heroLine2Gradient}
                </span>
                {t.marketing.heroLine2End}
              </span>
            </h1>
            <p className="mx-auto mb-6 max-w-[52ch] text-balance text-[clamp(15px,1.1vw,17px)] leading-relaxed text-[#e8e5de]/83 md:mb-7">
              {t.marketing.heroSubtitle}
            </p>

            <div className="mx-auto w-full max-w-[min(960px,_96vw)]">
              <MarketingHomeComposer
                wrapperClassName={cn(
                  '!rounded-[24px] !border-[#2e2c28] !bg-[#181614]/85 backdrop-blur-[18px]',
                  '!shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_24px_60px_rgba(0,0,0,0.45)]',
                  'focus-within:!border-indigo-500/45 focus-within:!shadow-[0_0_0_2px_rgba(59,130,246,0.45),0_1px_0_rgba(255,255,255,0.06)_inset,0_28px_72px_rgba(0,0,0,0.5)]',
                )}
              />
            </div>
          </div>
        </section>

        {/* Features */}
        <section
          id="features"
          className="scroll-mt-[4.75rem] px-4 pb-10 pt-2 md:px-6 md:pb-14 md:pt-4"
          aria-labelledby="features-title"
        >
          <div className="mx-auto max-w-[1200px]">
            <header className="mb-8 w-full">
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">
                {t.marketing.featuresEyebrow}
              </p>
              <h2
                id="features-title"
                className="mb-3 max-w-none text-[32px] font-semibold leading-tight tracking-[-0.5px] [word-break:keep-all]"
              >
                {t.marketing.featuresTitle}
              </h2>
              <p className="max-w-[52rem] text-balance text-[16px] leading-relaxed text-[#e8e5de]/83">
                {t.marketing.featuresLeadLine1}
                <br />
                {t.marketing.featuresLeadLine2}
              </p>
              <div
                className="mt-3 flex max-w-full flex-nowrap items-center gap-2 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                aria-label={t.marketing.flowLabelsAria}
              >
                {flowChips.map((chipLabel, index) => (
                  <Fragment key={chipLabel}>
                    {index > 0 ? (
                      <span className="text-[12px] text-[#9a9a98]/50" aria-hidden>
                        {t.marketing.wfArrow}
                      </span>
                    ) : null}
                    <span className="inline-flex shrink-0 items-center whitespace-nowrap rounded-full border border-[#2e2c28] bg-[#e8e5de]/[0.02] px-3 py-1 text-[12px] font-semibold tracking-wide text-[#9a9a98]">
                      {chipLabel}
                    </span>
                  </Fragment>
                ))}
              </div>
            </header>

            <div className="grid gap-4 sm:grid-cols-2 lg:gap-6">
              {featureCards.map((f) => (
                <article
                  key={f.title}
                  className="flex flex-col rounded-xl border border-[#2e2c28] bg-[#e8e5de]/[0.03] p-6"
                >
                  <h3 className="text-[18px] font-semibold">{f.title}</h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-[#e8e5de]/83">{f.desc}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {f.tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center rounded-md border border-[#2e2c28] bg-[#e8e5de]/[0.04] px-2 py-0.5 text-[11px] font-medium text-[#e8e5de]/70"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 border-t border-[#2e2c28]/60 pt-3 text-[13px] text-[#9a9a98]">
                    <span className="font-semibold text-[#e8e5de]/60">{t.marketing.wfOutputsPrefix} </span>
                    {f.outputs}
                  </p>
                  <Link to="/auth" className={cn(AUTH_BTN, 'mt-4 self-start no-underline')}>
                    {f.cta} <span aria-hidden>{t.marketing.wfArrow}</span>
                  </Link>
                </article>
              ))}
            </div>
          </div>
        </section>

        <OfficialSiteWorkflowSection />
      </main>
    </MarketingSiteChrome>
  );
}
