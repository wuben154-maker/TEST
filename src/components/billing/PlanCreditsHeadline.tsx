import { useLanguage } from "@/contexts/LanguageContext";
import { DEFAULT_CREDITS_PER_USD, formatCreditsAmount, usdToCreditsAmount } from "@/lib/billingDisplay";
import type { BillingPlanRow } from "@/lib/api-client";

type Variant = "app" | "marketing";

export function PlanCreditsHeadline({
  plan,
  variant = "app",
  creditsPerUsd = DEFAULT_CREDITS_PER_USD,
}: {
  plan: Pick<BillingPlanRow, "slug" | "included_credits_usd">;
  variant?: Variant;
  creditsPerUsd?: number;
}) {
  const { t, language } = useLanguage();
  const budgetUsd = Number(plan.included_credits_usd ?? 0);
  const isCustom = plan.slug === "enterprise" || budgetUsd <= 0;

  const containerClass =
    variant === "marketing"
      ? "text-[13px] leading-relaxed text-[#e8e5de]/85"
      : "text-sm leading-relaxed text-foreground/90";

  if (isCustom) {
    return <p className={containerClass}>{t.billing.creditsCustom}</p>;
  }

  const displayCredits = Math.round(usdToCreditsAmount(budgetUsd, creditsPerUsd));
  const creditsPretty = formatCreditsAmount(displayCredits, language);
  const text = t.billing.creditsHeadline.replace("{{credits}}", creditsPretty);

  return (
    <p className={containerClass} data-testid="plan-credits-headline">
      <span className="font-medium">{text}</span>
    </p>
  );
}