import { useLanguage } from "@/contexts/LanguageContext";
import type { Language } from "@/i18n";

function billingLocale(language: Language): string {
  if (language === "zh") return "zh-CN";
  if (language === "ja") return "ja-JP";
  if (language === "ko") return "ko-KR";
  return "en-US";
}

function formatPeriodRange(start: unknown, end: unknown, language: Language): string {
  const toDate = (v: unknown): Date | null => {
    if (v == null || String(v).trim() === "") return null;
    const d = new Date(String(v));
    return Number.isNaN(d.getTime()) ? null : d;
  };
  const a = toDate(start);
  const b = toDate(end);
  if (!a || !b) return "—";
  const loc = billingLocale(language);
  const opts: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric" };
  return `${a.toLocaleDateString(loc, opts)} → ${b.toLocaleDateString(loc, opts)}`;
}

/**
 * Vertical definition list for plan / subscription / billing period (avoids cramped 2-col grid).
 */
export function BillingSummaryMeta({
  planSlug,
  subscriptionStatus,
  periodStart,
  periodEnd,
}: {
  planSlug: unknown;
  subscriptionStatus: unknown;
  periodStart?: unknown;
  periodEnd?: unknown;
}) {
  const { t, language } = useLanguage();

  const periodText = formatPeriodRange(periodStart, periodEnd, language);

  return (
    <dl className="overflow-hidden rounded-lg border border-border/80 bg-muted/25 text-sm shadow-sm">
      <div className="flex items-baseline justify-between gap-6 px-4 py-3 sm:gap-10">
        <dt className="shrink-0 text-muted-foreground">{t.billing.fieldPlan}</dt>
        <dd className="min-w-0 text-right font-medium text-foreground">
          {String(planSlug ?? "—")}
        </dd>
      </div>
      <div className="flex items-baseline justify-between gap-6 border-t border-border/60 px-4 py-3 sm:gap-10">
        <dt className="shrink-0 text-muted-foreground">{t.billing.fieldStatus}</dt>
        <dd className="min-w-0 text-right font-medium text-foreground">
          {String(subscriptionStatus ?? "—")}
        </dd>
      </div>
      <div className="flex flex-col gap-1 border-t border-border/60 px-4 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <dt className="shrink-0 text-muted-foreground sm:pt-0.5">{t.billing.fieldPeriod}</dt>
        <dd className="min-w-0 text-right text-xs tabular-nums text-muted-foreground sm:max-w-[min(100%,20rem)] sm:text-sm">
          {periodText}
        </dd>
      </div>
    </dl>
  );
}
