import { useEffect } from 'react';
import { MarketingSiteChrome } from '@/components/marketing/MarketingSiteChrome';
import { useLanguage } from '@/contexts/LanguageContext';

export default function MarketingProductLogPage() {
  const { t } = useLanguage();
  const p = t.marketing.resourcePages.productLog;

  const entries = [
    { title: p.entry1Title, date: p.entry1Date, body: p.entry1Body },
    { title: p.entry2Title, date: p.entry2Date, body: p.entry2Body },
    { title: p.entry3Title, date: p.entry3Date, body: p.entry3Body },
    { title: p.entry4Title, date: p.entry4Date, body: p.entry4Body },
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
          <ul className="mt-12 space-y-10">
            {entries.map((e, i) => (
              <li key={i} className="border-l-2 border-[#e8e5de]/20 pl-5">
                <time
                  dateTime={e.date}
                  className="text-[12px] font-medium uppercase tracking-wide text-[#e8e5de]/45"
                >
                  {e.date}
                </time>
                <h2 className="mt-2 text-[18px] font-semibold text-[#e8e5de]">{e.title}</h2>
                <p className="mt-2 text-[15px] leading-relaxed text-[#e8e5de]/75">{e.body}</p>
              </li>
            ))}
          </ul>
        </article>
      </main>
    </MarketingSiteChrome>
  );
}
