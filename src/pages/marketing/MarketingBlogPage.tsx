import { useEffect } from 'react';
import { MarketingSiteChrome } from '@/components/marketing/MarketingSiteChrome';
import { useLanguage } from '@/contexts/LanguageContext';

export default function MarketingBlogPage() {
  const { t } = useLanguage();
  const p = t.marketing.resourcePages.blog;

  useEffect(() => {
    document.title = p.docTitle;
  }, [p.docTitle]);

  return (
    <MarketingSiteChrome>
      <main id="main" className="relative z-[1] mx-auto max-w-[720px] px-4 py-14 md:px-6 md:py-20">
        <article className="font-marketing">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-[#e8e5de] md:text-[32px]">
              {p.title}
            </h1>
            <span className="rounded-full border border-[#e8e5de]/25 bg-[#e8e5de]/[0.06] px-3 py-1 text-[12px] font-medium text-[#e8e5de]/83">
              {p.badge}
            </span>
          </div>
          <p className="mt-4 text-[16px] leading-relaxed text-[#e8e5de]/83">{p.lead}</p>
          <p className="mt-8 text-[15px] leading-relaxed text-[#e8e5de]/75">{p.body}</p>
        </article>
      </main>
    </MarketingSiteChrome>
  );
}
