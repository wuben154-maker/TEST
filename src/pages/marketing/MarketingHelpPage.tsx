import { useEffect } from 'react';
import { MarketingSiteChrome } from '@/components/marketing/MarketingSiteChrome';
import { useLanguage } from '@/contexts/LanguageContext';

export default function MarketingHelpPage() {
  const { t } = useLanguage();
  const p = t.marketing.resourcePages.help;

  const faq = [
    { q: p.faq1Q, a: p.faq1A },
    { q: p.faq2Q, a: p.faq2A },
    { q: p.faq3Q, a: p.faq3A },
    { q: p.faq4Q, a: p.faq4A },
    { q: p.faq5Q, a: p.faq5A },
  ];

  useEffect(() => {
    document.title = p.docTitle;
  }, [p.docTitle]);

  return (
    <MarketingSiteChrome>
      <main id="main" className="relative z-[1] mx-auto max-w-[720px] px-4 py-14 md:px-6 md:py-20">
        <article className="font-marketing">
          <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-[#e8e5de] md:text-[32px]">
            {p.title}
          </h1>
          <p className="mt-4 text-[16px] leading-relaxed text-[#e8e5de]/83">{p.lead}</p>
          <dl className="mt-10 space-y-8">
            {faq.map((item, i) => (
              <div key={i} className="border-b border-[#2e2c28] pb-8 last:border-0 last:pb-0">
                <dt className="text-[15px] font-semibold text-[#e8e5de]">{item.q}</dt>
                <dd className="mt-2 text-[15px] leading-relaxed text-[#e8e5de]/75">{item.a}</dd>
              </div>
            ))}
          </dl>
        </article>
      </main>
    </MarketingSiteChrome>
  );
}
