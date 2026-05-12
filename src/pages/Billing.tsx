import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { billingApi, getAuthToken, type BillingPlanRow } from "@/lib/api-client";
import {
  coerceCreditsPerUsd,
  DEFAULT_CREDITS_PER_USD,
  formatCreditsAmount,
  parseBillingDecimal,
  periodCreditsFromBillingSummary,
} from "@/lib/billingDisplay";
import { BillingSummaryMeta } from "@/components/billing/BillingSummaryMeta";
import { PlanCard } from "@/components/billing/PlanCard";
import { Loader2 } from "lucide-react";

const CHECKOUT_SLUGS = new Set(["pro", "ultra"]);

export default function Billing() {
  const { t, language } = useLanguage();
  const { user, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [plans, setPlans] = useState<BillingPlanRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [plansError, setPlansError] = useState<string | null>(null);
  const [checkoutSlug, setCheckoutSlug] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [creditsPerUsd, setCreditsPerUsd] = useState(DEFAULT_CREDITS_PER_USD);

  const refresh = useCallback(() => {
    let cancelled = false;
    (async () => {
      try {
        const [sum, pl] = await Promise.all([billingApi.getSummary(), billingApi.getPlans()]);
        if (!cancelled) {
          setSummary(sum);
          setPlans(pl.plans ?? []);
          setCreditsPerUsd(coerceCreditsPerUsd(pl.credits_per_usd, sum.credits_per_usd));
          setLoadError(null);
          setPlansError(null);
        }
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          setLoadError(msg);
          setPlansError(msg);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!getAuthToken() || !user?.id) return;
    return refresh();
  }, [authLoading, user?.id, refresh]);

  const planSlug = String(summary?.plan_slug ?? "free");
  const subStatus = String(summary?.subscription_status ?? "inactive").toLowerCase();
  const isPaidPlan = planSlug === "pro" || planSlug === "ultra";
  const isActiveSub = subStatus === "active" || subStatus === "trialing";
  const hasStripeCustomer = summary?.has_stripe_customer === true;
  const showManagePortal = isPaidPlan || isActiveSub || hasStripeCustomer;

  const spentCredits = useMemo(() => {
    if (!summary) return 0;
    return periodCreditsFromBillingSummary(summary, "spent_credits_period", "spent_usd_period", creditsPerUsd);
  }, [summary, creditsPerUsd]);
  const capCredits = useMemo(() => {
    if (!summary) return 0;
    return periodCreditsFromBillingSummary(
      summary,
      "monthly_spend_cap_credits",
      "monthly_spend_cap_usd",
      creditsPerUsd,
    );
  }, [summary, creditsPerUsd]);
  const progressPct = useMemo(() => {
    if (capCredits <= 0) return 0;
    return Math.min(100, Math.max(0, Math.round((spentCredits / capCredits) * 100)));
  }, [spentCredits, capCredits]);

  const onSubscribe = async (slug: string) => {
    if (!CHECKOUT_SLUGS.has(slug)) return;
    setCheckoutSlug(slug);
    try {
      const { url } = await billingApi.createCheckout(slug as "pro" | "ultra");
      if (url) window.location.href = url;
      else toast.error(t.billing.checkoutError);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg || t.billing.checkoutError);
    } finally {
      setCheckoutSlug(null);
    }
  };

  const onPortal = async () => {
    setPortalLoading(true);
    try {
      const { url } = await billingApi.createPortal();
      if (url) window.location.href = url;
      else toast.error(t.billing.portalError);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg || t.billing.portalError);
    } finally {
      setPortalLoading(false);
    }
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6 md:p-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{t.billing.title}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              <Link to="/start" className="underline-offset-4 hover:underline">
                {t.billing.backToWorkspace}
              </Link>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {showManagePortal && (
              <Button variant="default" size="sm" disabled={portalLoading} onClick={onPortal}>
                {portalLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  t.billing.manageSubscription
                )}
              </Button>
            )}
            <Button variant="outline" size="sm" asChild>
              <Link to="/usage">{t.billing.navUsage}</Link>
            </Button>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{t.billing.summaryTitle}</CardTitle>
            <CardDescription>{t.billing.summaryDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {loadError ? (
              <p className="text-sm text-destructive">{loadError}</p>
            ) : !summary ? (
              <p className="text-sm text-muted-foreground">{t.billing.loadingSummary}</p>
            ) : (
              <>
                <BillingSummaryMeta
                  planSlug={summary.plan_slug}
                  subscriptionStatus={summary.subscription_status}
                  periodStart={summary.period_start}
                  periodEnd={summary.period_end}
                />

                <div data-testid="billing-progress-credits" className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{t.billing.fieldCreditsPeriod}</span>
                    <span className="font-medium text-foreground">
                      {t.billing.progressCreditsUsedOfCap
                        .replace("{{spent}}", formatCreditsAmount(spentCredits, language))
                        .replace("{{cap}}", formatCreditsAmount(capCredits, language))}
                    </span>
                  </div>
                  <div
                    className="h-2 w-full overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-valuenow={progressPct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={t.billing.fieldCreditsPeriod}
                  >
                    <div
                      className="h-full bg-primary transition-all"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <div>
          <h2 className="text-lg font-semibold tracking-tight">{t.billing.plansTitle}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t.billing.plansSubtitle}</p>
        </div>

        {plansError && !plans.length ? (
          <p className="text-sm text-destructive">{plansError}</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {plans.map((p) => {
              const isCurrent = p.slug === planSlug;
              const canCheckout = CHECKOUT_SLUGS.has(p.slug) && planSlug === "free";
              const isEnterprise = p.slug === "enterprise";

              const ctaSlot = isEnterprise ? (
                <Button variant="outline" className="w-full" disabled>
                  {t.billing.contactSales}
                </Button>
              ) : canCheckout ? (
                <Button
                  className="w-full"
                  disabled={checkoutSlug === p.slug}
                  onClick={() => onSubscribe(p.slug)}
                >
                  {checkoutSlug === p.slug ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    t.billing.subscribe
                  )}
                </Button>
              ) : isCurrent ? (
                <Button variant="secondary" className="w-full" disabled>
                  {t.billing.currentPlan}
                </Button>
              ) : (
                <Button
                  variant="outline"
                  className="w-full"
                  disabled
                  title={t.billing.usePortalToChange}
                >
                  {t.billing.usePortalToChange}
                </Button>
              );

              return (
                <PlanCard
                  key={p.slug}
                  plan={p}
                  variant="app"
                  isCurrent={isCurrent}
                  creditsPerUsd={creditsPerUsd}
                  ctaSlot={ctaSlot}
                />
              );
            })}
          </div>
        )}

        <p className="text-xs text-muted-foreground">{t.billing.stripeFootnote}</p>
      </div>
    </div>
  );
}
