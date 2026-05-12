import { useLanguage } from "@/contexts/LanguageContext";
import {
  DEFAULT_CREDITS_PER_USD,
  formatBillingPrice,
  resolvePlanBenefits,
  resolvePlanQuotaHints,
  resolvePlanTagline,
} from "@/lib/billingDisplay";
import type { BillingPlanRow } from "@/lib/api-client";
import { PlanBenefitsList } from "./PlanBenefitsList";
import { PlanCreditsHeadline } from "./PlanCreditsHeadline";
import { QuotaHintsRow } from "./QuotaHintsRow";
import { fallbackBenefitsBySlug, quotaLabelFallback } from "./planFallbacks";
import { normalizeQuotaHintsForComparison } from "./quotaComparison";

type Variant = "app" | "marketing";

export function PlanCard({
  plan,
  variant,
  isCurrent,
  creditsPerUsd = DEFAULT_CREDITS_PER_USD,
  ctaSlot,
}: {
  plan: BillingPlanRow;
  variant: Variant;
  isCurrent?: boolean;
  creditsPerUsd?: number;
  ctaSlot: React.ReactNode;
}) {
  const { t, language } = useLanguage();

  const tagline = resolvePlanTagline(plan, language);
  const benefits = resolvePlanBenefits(
    plan,
    language,
    fallbackBenefitsBySlug(plan.slug, t),
  );
  const rawHints = resolvePlanQuotaHints(plan, language, quotaLabelFallback(t));
  const hints =
    rawHints.length > 0 ? normalizeQuotaHintsForComparison(rawHints, quotaLabelFallback(t)) : [];

  const wrapperClass =
    variant === "marketing"
      ? "flex flex-col gap-5 rounded-xl border border-[#2e2c28] bg-[#e8e5de]/[0.03] p-6"
      : `flex flex-col gap-4 rounded-lg border bg-card p-5 shadow-sm ${
          isCurrent ? "border-primary ring-1 ring-primary/20" : "border-border"
        }`;

  const titleClass =
    variant === "marketing"
      ? "text-[18px] font-semibold text-[#e8e5de]"
      : "text-base font-semibold text-foreground";

  const priceClass =
    variant === "marketing"
      ? "text-[clamp(22px,2.5vw,28px)] font-semibold tracking-tight text-[#e8e5de]"
      : "text-2xl font-semibold tracking-tight text-foreground";

  return (
    <article
      className={wrapperClass}
      data-plan-slug={plan.slug}
      data-current-plan={isCurrent ? "true" : undefined}
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <h2 className={titleClass}>{plan.display_name}</h2>
          {isCurrent ? (
            <span className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              {t.billing.currentPlan}
            </span>
          ) : null}
        </div>
        {tagline ? (
          <p
            className={
              variant === "marketing"
                ? "text-[13px] leading-relaxed text-[#9a9a98]"
                : "text-sm leading-relaxed text-muted-foreground"
            }
          >
            {tagline}
          </p>
        ) : null}
        <div className={priceClass}>
          {plan.monthly_price_usd > 0 ? (
            <>
              {formatBillingPrice(plan.monthly_price_usd, language)}
              <span
                className={
                  variant === "marketing"
                    ? "text-sm font-normal text-[#9a9a98]"
                    : "text-sm font-normal text-muted-foreground"
                }
              >
                {" "}
                {t.billing.perMonth}
              </span>
            </>
          ) : (
            // Free / Enterprise show a dash for price; Credits headline carries the meaning.
            <span
              className={
                variant === "marketing"
                  ? "text-[clamp(22px,2.5vw,28px)] font-semibold text-[#e8e5de]"
                  : "text-2xl font-semibold text-foreground"
              }
            >
              —
            </span>
          )}
        </div>
        <PlanCreditsHeadline plan={plan} variant={variant} creditsPerUsd={creditsPerUsd} />
      </div>

      <PlanBenefitsList
        benefits={benefits}
        variant={variant}
        ariaLabel={t.billing.benefitsTitle}
        emptyText={t.billing.benefitsEmpty}
      />

      {hints.length > 0 ? (
        <QuotaHintsRow hints={hints} variant={variant} title={t.billing.quotaTitle} />
      ) : null}

      <div
        className={
          variant === "marketing"
            ? "mt-auto border-t border-[#2e2c28]/60 pt-5"
            : "mt-auto pt-1"
        }
      >
        {ctaSlot}
      </div>
    </article>
  );
}
