import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { MarketingSiteChrome } from '@/components/marketing/MarketingSiteChrome';
import { useLanguage } from '@/contexts/LanguageContext';
import { billingApi, type BillingPlanRow } from '@/lib/api-client';
import { coerceCreditsPerUsd, DEFAULT_CREDITS_PER_USD } from '@/lib/billingDisplay';
import { PlanCard } from '@/components/billing/PlanCard';
import { MeteringDisclosure } from '@/components/billing/MeteringDisclosure';
import { cn } from '@/lib/utils';

const CHECKOUT_SLUGS = new Set(['pro', 'ultra']);

const AUTH_BTN =
  'inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-[#e8e5de]/35 bg-transparent px-4 text-[13px] text-[#e8e5de] transition-colors hover:bg-[#e8e5de]/[0.06] focus-visible:shadow-[0_0_0_2px_rgba(59,130,246,0.5)] focus-visible:outline-none';

export default function OfficialPricing() {
  const { t } = useLanguage();
  const [plans, setPlans] = useState<BillingPlanRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creditsPerUsd, setCreditsPerUsd] = useState(DEFAULT_CREDITS_PER_USD);

  useEffect(() => {
    document.title = t.marketing.pricing.docTitle;
  }, [t.marketing.pricing.docTitle]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await billingApi.getPlans();
        if (!cancelled) {
          const sorted = [...(res.plans ?? [])].sort((a, b) => a.sort_order - b.sort_order);
          setPlans(sorted);
          setCreditsPerUsd(coerceCreditsPerUsd(res.credits_per_usd));
          setLoadError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e));
          setPlans([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const faqItems = useMemo(
    () => [
      { q: t.marketing.pricing.faq1Q, a: t.marketing.pricing.faq1A },
      { q: t.marketing.pricing.faq2Q, a: t.marketing.pricing.faq2A },
      { q: t.marketing.pricing.faq3Q, a: t.marketing.pricing.faq3A },
    ],
    [t.marketing.pricing],
  );

  return (
    <MarketingSiteChrome>
      <main id="main" className="relative z-[1] px-4 pb-16 pt-10 md:px-6 md:pb-20 md:pt-14">
        <div className="mx-auto max-w-[1200px]">
          <header className="mb-10 max-w-[720px]">
            <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">
              {t.marketing.pricing.heroEyebrow}
            </p>
            <h1 className="mb-3 text-[clamp(28px,3.6vw,40px)] font-semibold leading-tight tracking-[-0.5px]">
              {t.marketing.navPricing}
            </h1>
            <p className="text-balance text-[16px] leading-relaxed text-[#e8e5de]/83">
              {t.billing.plansSubtitle}
            </p>
            <p className="mt-3 text-[14px] leading-relaxed text-[#9a9a98]">
              {t.marketing.pricing.heroLead}
            </p>
          </header>

          {loading ? (
            <div className="flex items-center gap-2 text-[#9a9a98]" aria-live="polite">
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
              <span>{t.common.loading}</span>
            </div>
          ) : loadError ? (
            <p className="text-sm text-red-400/90" role="alert">
              {t.marketing.pricing.loadError}
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {plans.map((p) => {
                const isEnterprise = p.slug === 'enterprise';
                const canSubscribe = CHECKOUT_SLUGS.has(p.slug);

                const ctaSlot = isEnterprise ? (
                  <a
                    href="mailto:hello@example.com"
                    className={cn(AUTH_BTN, 'flex w-full justify-center no-underline')}
                  >
                    {t.billing.contactSales}
                  </a>
                ) : canSubscribe ? (
                  <Link to="/auth" className={cn(AUTH_BTN, 'flex w-full justify-center no-underline')}>
                    {t.marketing.pricing.signInToSubscribe}
                  </Link>
                ) : (
                  <Link to="/auth" className={cn(AUTH_BTN, 'flex w-full justify-center no-underline')}>
                    {t.marketing.pricing.freePlanCta}
                  </Link>
                );

                return (
                  <PlanCard
                    key={p.slug}
                    plan={p}
                    variant="marketing"
                    creditsPerUsd={creditsPerUsd}
                    ctaSlot={ctaSlot}
                  />
                );
              })}
            </div>
          )}

          <section className="mt-10">
            <MeteringDisclosure
              variant="marketing"
              defaultOpen={false}
              showUsageLink={false}
              creditsPerUsd={creditsPerUsd}
            />
          </section>

          <section
            className="mt-14 rounded-xl border border-[#2e2c28] bg-[#e8e5de]/[0.02] p-6 md:p-8"
            aria-labelledby="pricing-faq"
          >
            <h2 id="pricing-faq" className="mb-6 text-[20px] font-semibold tracking-tight">
              {t.marketing.pricing.faqTitle}
            </h2>
            <dl className="space-y-5">
              {faqItems.map((item) => (
                <div key={item.q}>
                  <dt className="text-[14px] font-semibold text-[#e8e5de]">{item.q}</dt>
                  <dd className="mt-1 text-[14px] leading-relaxed text-[#e8e5de]/78">{item.a}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="mt-10 space-y-3 text-[13px] leading-relaxed text-[#9a9a98]">
            <p>{t.marketing.pricing.publicFootnote}</p>
            <p>{t.marketing.pricing.paymentNote}</p>
          </section>

          <p className="mt-8">
            <Link
              to="/"
              className="text-[13px] text-[#a5b4fc] underline-offset-4 hover:text-[#c7d2fe] hover:underline"
            >
              {t.marketing.pricing.backHome}
            </Link>
          </p>
        </div>
      </main>
    </MarketingSiteChrome>
  );
}
