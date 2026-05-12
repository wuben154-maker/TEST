import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { accountApi, billingApi, getAuthToken } from "@/lib/api-client";
import { LayoutDashboard, Loader2 } from "lucide-react";
import {
  coerceCreditsPerUsd,
  DEFAULT_CREDITS_PER_USD,
  formatBillingUsdAmount,
  formatBillingTokens,
  formatCreditsAmount,
  parseBillingDecimal,
  periodCreditsFromBillingSummary,
} from "@/lib/billingDisplay";
import { BillingSummaryMeta } from "@/components/billing/BillingSummaryMeta";
import { MeteringDisclosure } from "@/components/billing/MeteringDisclosure";

export default function AccountOverview() {
  const { t, language } = useLanguage();
  const { user, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [overview, setOverview] = useState<{
    project_count: number;
    analysis_sessions_count: number;
    total_llm_tokens_lifetime: number;
  } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creditsPerUsd, setCreditsPerUsd] = useState(DEFAULT_CREDITS_PER_USD);

  const refresh = useCallback(() => {
    let cancelled = false;
    (async () => {
      try {
        const [sum, ov] = await Promise.all([billingApi.getSummary(), accountApi.getOverview()]);
        if (!cancelled) {
          setSummary(sum);
          setOverview(ov);
          setCreditsPerUsd(coerceCreditsPerUsd(sum.credits_per_usd));
          setLoadError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e));
          setSummary(null);
          setOverview(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Wait for global auth (validated /me) so billing and overview use the same JWT user.
  useEffect(() => {
    if (authLoading) return;
    if (!getAuthToken() || !user?.id) {
      setSummary(null);
      setOverview(null);
      setLoadError(null);
      return;
    }
    return refresh();
  }, [authLoading, user?.id, refresh]);

  const planSlug = String(summary?.plan_slug ?? "free");
  const spentUsd = summary ? parseBillingDecimal(summary.spent_usd_period) : 0;
  const capUsd = summary ? parseBillingDecimal(summary.monthly_spend_cap_usd) : 0;
  const tokensUsedEstimate = Number(summary?.tokens_used_period_estimate ?? 0);
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

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6 md:p-10">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{t.account.overviewTitle}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              <Link to="/start" className="underline-offset-4 hover:underline">
                {t.account.backToWorkspace}
              </Link>
            </p>
            {user?.email ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {t.account.signedInAs}:{" "}
                <span className="font-medium text-foreground">{user.email}</span>
                {user.username ? (
                  <span className="text-muted-foreground"> · {user.username}</span>
                ) : null}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link to="/account/settings">{t.account.navSettings}</Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/usage">{t.billing.navUsage}</Link>
            </Button>
          </div>
        </div>

        {loadError ? (
          <p className="text-sm text-destructive">{loadError || t.account.loadError}</p>
        ) : null}

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <LayoutDashboard className="h-5 w-5 text-primary" />
              <CardTitle>{t.account.planSection}</CardTitle>
            </div>
            <CardDescription>{t.billing.summaryDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {authLoading || !user?.id ? (
              <p className="text-sm text-muted-foreground">{t.billing.loadingSummary}</p>
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

                <div data-testid="account-progress-credits" className="space-y-2">
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
                  <p className="text-xs text-muted-foreground">
                    {t.billing.progressUsdFootnote
                      .replace("{{spentUsd}}", formatBillingUsdAmount(spentUsd, language))
                      .replace("{{capUsd}}", formatBillingUsdAmount(capUsd, language))}
                  </p>
                </div>

                <MeteringDisclosure
                  tokensEstimate={tokensUsedEstimate}
                  variant="app"
                  defaultOpen={false}
                  creditsPerUsd={creditsPerUsd}
                />

                <div className="flex flex-wrap gap-2 pt-1">
                  {planSlug === "free" ? (
                    <Button size="sm" asChild>
                      <Link to="/billing">{t.account.upgradePlan}</Link>
                    </Button>
                  ) : null}
                  <Button variant="outline" size="sm" asChild>
                    <Link to="/billing">{t.account.manageBilling}</Link>
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t.account.projectStats}</CardTitle>
            <CardDescription>{t.billing.usageWip}</CardDescription>
          </CardHeader>
          <CardContent>
            {authLoading || !user?.id || !overview ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">{t.account.projectCount}</dt>
                  <dd className="font-medium">{overview.project_count}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">{t.account.analysisCount}</dt>
                  <dd className="font-medium">{overview.analysis_sessions_count}</dd>
                </div>
              </dl>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t.account.tokenStats}</CardTitle>
            <CardDescription>{t.billing.usageWip}</CardDescription>
          </CardHeader>
          <CardContent>
            {authLoading || !user?.id || !summary || !overview ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div className="flex justify-between gap-4 sm:col-span-2">
                  <dt className="text-muted-foreground">
                    {t.billing.meteringTokensEstimate}
                  </dt>
                  <dd className="font-medium">
                    {formatBillingTokens(tokensUsedEstimate, language)}
                  </dd>
                </div>
                <div className="flex justify-between gap-4 sm:col-span-2">
                  <dt className="text-muted-foreground">{t.account.tokensLifetime}</dt>
                  <dd className="font-medium">
                    {formatBillingTokens(overview.total_llm_tokens_lifetime, language)}
                  </dd>
                </div>
              </dl>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
