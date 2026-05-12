import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { MarketingSiteChrome } from '@/components/marketing/MarketingSiteChrome';
import { useLanguage } from '@/contexts/LanguageContext';
import { isMarketingSolutionSlug, SOLUTION_SLUG_TO_I18N_KEY } from '@/lib/marketing-routes';

export default function MarketingSolutionPage() {
  const { slug } = useParams<{ slug: string }>();
  const { t } = useLanguage();

  const valid = slug && isMarketingSolutionSlug(slug);
  const pageKey = valid ? SOLUTION_SLUG_TO_I18N_KEY[slug] : null;
  const content = pageKey ? t.marketing.solutionPages[pageKey] : null;

  useEffect(() => {
    if (content?.docTitle) document.title = content.docTitle;
  }, [content?.docTitle]);

  if (!valid || !pageKey || !content) {
    return (
      <MarketingSiteChrome>
        <main id="main" className="relative z-[1] mx-auto max-w-[720px] px-4 py-24 md:px-6">
          <h1 className="font-marketing text-2xl font-semibold text-[#e8e5de]">404</h1>
          <p className="mt-2 font-marketing text-[#e8e5de]/83">Page not found.</p>
          <Link
            to="/"
            className="mt-6 inline-block font-marketing text-[14px] text-[#e8e5de] underline underline-offset-4 hover:text-[#e8e5de]"
          >
            ← Home
          </Link>
        </main>
      </MarketingSiteChrome>
    );
  }

  return (
    <MarketingSiteChrome>
      <main id="main" className="relative z-[1] mx-auto max-w-[min(960px,_94vw)] px-4 py-14 md:px-6 md:py-20">
        <article className="font-marketing">
          <header className="max-w-[52ch]">
            <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[#e8e5de]/35">
              {content.heroEyebrow} {content.navTitle}
            </p>
            <h1 className="text-balance text-[clamp(26px,3.4vw,36px)] font-semibold leading-tight tracking-[-0.02em] text-[#e8e5de]">
              {content.heroTitle}
            </h1>
            <p className="mt-4 text-balance text-[16px] leading-relaxed text-[#e8e5de]/83">{content.lead}</p>
          </header>

          <section className="mt-14 md:mt-16" aria-labelledby={`solution-benefits-${pageKey}`}>
            <h2
              id={`solution-benefits-${pageKey}`}
              className="mb-6 text-[18px] font-semibold tracking-[-0.02em] text-[#e8e5de]"
            >
              {content.benefitsHeading}
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {content.benefits.map((b, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-[#2e2c28] bg-[#181614]/50 p-5 shadow-[0_1px_0_rgba(255,255,255,0.04)_inset]"
                >
                  <h3 className="text-[15px] font-semibold text-[#e8e5de]">{b.title}</h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-[#e8e5de]/75">{b.desc}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-14 md:mt-16" aria-labelledby={`solution-steps-${pageKey}`}>
            <h2
              id={`solution-steps-${pageKey}`}
              className="mb-6 text-[18px] font-semibold tracking-[-0.02em] text-[#e8e5de]"
            >
              {content.stepsHeading}
            </h2>
            <ol className="space-y-0 border-l border-[#2e2c28] pl-6">
              {content.steps.map((step, i) => (
                <li key={i} className="relative pb-8 last:pb-0">
                  <span
                    className="absolute top-1 -left-[calc(1.5rem+5px)] flex size-[11px] -translate-x-1/2 rounded-full bg-[#6366f1] ring-4 ring-[#1a1916]"
                    aria-hidden
                  />
                  <h3 className="text-[15px] font-semibold text-[#e8e5de]">{step.title}</h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-[#e8e5de]/75">{step.body}</p>
                </li>
              ))}
            </ol>
          </section>

          <section className="mt-14 md:mt-16" aria-labelledby={`solution-sample-${pageKey}`}>
            <h2
              id={`solution-sample-${pageKey}`}
              className="mb-6 text-[18px] font-semibold tracking-[-0.02em] text-[#e8e5de]"
            >
              {content.sampleHeading}
            </h2>
            <div className="overflow-hidden rounded-xl border border-[#2e2c28] bg-[#121110]/90 shadow-[0_1px_0_rgba(255,255,255,0.04)_inset]">
              <div className="border-b border-[#2e2c28] px-5 py-3">
                <h3 className="text-[14px] font-semibold text-[#e8e5de]/90">{content.sampleCardTitle}</h3>
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap px-5 py-4 font-mono text-[12px] leading-relaxed text-[#c9c6bf]/92">
                {content.sampleBody}
              </pre>
            </div>
          </section>

          <section className="mt-14 md:mt-16" aria-labelledby={`solution-why-${pageKey}`}>
            <h2
              id={`solution-why-${pageKey}`}
              className="mb-6 text-[18px] font-semibold tracking-[-0.02em] text-[#e8e5de]"
            >
              {content.whyHeading}
            </h2>
            <div className="grid gap-6 sm:grid-cols-3">
              {content.metrics.map((m, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-[#2e2c28] bg-[#181614]/35 px-5 py-5 text-center sm:text-left"
                >
                  <p className="text-[17px] font-semibold text-[#e8e5de]">{m.kpi}</p>
                  <p className="mt-2 text-[13px] leading-relaxed text-[#e8e5de]/72">{m.label}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-14 md:mt-16" aria-labelledby={`solution-trust-${pageKey}`}>
            <h2
              id={`solution-trust-${pageKey}`}
              className="mb-6 text-[18px] font-semibold tracking-[-0.02em] text-[#e8e5de]"
            >
              {content.trustHeading}
            </h2>
            <ul className="space-y-3 text-[14px] leading-relaxed text-[#e8e5de]/78">
              {content.trustBullets.map((line, i) => (
                <li key={i} className="flex gap-3">
                  <span className="mt-2 inline-block size-1.5 shrink-0 rounded-full bg-[#a78bfa]" aria-hidden />
                  <span>{line}</span>
                </li>
              ))}
            </ul>
          </section>

          <div className="mt-14 flex flex-wrap gap-3 border-t border-[#2e2c28] pt-10 md:mt-16">
            <Link
              to="/auth"
              className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[#e8e5de]/35 bg-transparent px-4 text-[13px] text-[#e8e5de] no-underline transition-colors hover:bg-[#e8e5de]/[0.06]"
            >
              {t.marketing.signIn}
            </Link>
            <Link
              to="/start"
              className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[#e8e5de] px-4 text-[13px] font-medium text-[#1a1916] no-underline transition-colors hover:bg-[#f5f2ea]"
            >
              {t.billing.freePlanCta}
            </Link>
          </div>
        </article>
      </main>
    </MarketingSiteChrome>
  );
}
