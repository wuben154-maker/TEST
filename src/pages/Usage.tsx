import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { billingApi, getAuthToken } from "@/lib/api-client";
import {
  coerceCreditsPerUsd,
  DEFAULT_CREDITS_PER_USD,
  formatCreditsAmount,
  parseBillingDecimal,
  usdToCreditsAmount,
} from "@/lib/billingDisplay";

const PAGE_SIZE = 30;

function displayRowCredits(row: Record<string, unknown>, creditsPerUsd: number): number {
  if (Object.prototype.hasOwnProperty.call(row, "cost_credits") && row.cost_credits != null) {
    return parseBillingDecimal(row.cost_credits);
  }
  return usdToCreditsAmount(parseBillingDecimal(row.cost_usd), creditsPerUsd);
}

/** Page numbers to show (1-based), with gaps as "gap" when there are many pages. */
function buildUsagePageList(currentPage: number, totalPages: number): (number | "gap")[] {
  if (totalPages <= 1) {
    return totalPages === 1 ? [1] : [];
  }
  if (totalPages <= 9) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const pages = new Set<number>();
  pages.add(1);
  pages.add(totalPages);
  const windowRadius = 2;
  for (let d = -windowRadius; d <= windowRadius; d++) {
    const p = currentPage + d;
    if (p >= 1 && p <= totalPages) {
      pages.add(p);
    }
  }
  const sorted = [...pages].sort((a, b) => a - b);
  const out: (number | "gap")[] = [];
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && sorted[i]! - sorted[i - 1]! > 1) {
      out.push("gap");
    }
    out.push(sorted[i]!);
  }
  return out;
}

export default function Usage() {
  const { t, language } = useLanguage();
  const { user, loading: authLoading } = useAuth();
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [creditsPerUsd, setCreditsPerUsd] = useState(DEFAULT_CREDITS_PER_USD);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [usageReason, setUsageReason] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [listLoading, setListLoading] = useState(false);

  useEffect(() => {
    setOffset(0);
  }, [user?.id]);

  useEffect(() => {
    if (authLoading) return;
    if (!getAuthToken() || !user?.id) return;
    let cancelled = false;
    setListLoading(true);
    (async () => {
      try {
        const data = await billingApi.getUsageEvents(PAGE_SIZE, offset);
        if (!cancelled) {
          setItems(data.items ?? []);
          setCreditsPerUsd(coerceCreditsPerUsd(data.credits_per_usd));
          setTotal(typeof data.total === "number" ? data.total : 0);
          setLoadError(null);
          const disabled =
            data.usage_persistence === "disabled" && typeof data.reason === "string";
          setUsageReason(disabled ? String(data.reason) : null);
        }
      } catch (e) {
        if (!cancelled) {
          setItems([]);
          setTotal(0);
          setLoadError(e instanceof Error ? e.message : String(e));
          setUsageReason(null);
        }
      } finally {
        if (!cancelled) setListLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, user?.id, offset]);

  const totalPages = useMemo(() => {
    if (total <= 0) return 0;
    return Math.max(1, Math.ceil(total / PAGE_SIZE));
  }, [total]);

  const currentPage = useMemo(() => Math.floor(offset / PAGE_SIZE) + 1, [offset]);

  const pageButtons = useMemo(
    () => buildUsagePageList(currentPage, totalPages),
    [currentPage, totalPages]
  );

  return (
      <div className="min-h-0 flex-1 overflow-y-auto p-6 md:p-10">
        <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">{t.billing.usageTitle}</h1>
          <Button variant="outline" size="sm" asChild>
            <Link to="/billing">{t.billing.navBilling}</Link>
          </Button>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>{t.billing.usageTitle}</CardTitle>
            <CardDescription>{t.billing.usageWip}</CardDescription>
          </CardHeader>
          <CardContent>
            {loadError ? (
              <p className="text-sm text-destructive">{loadError}</p>
            ) : items.length === 0 ? (
              <div className="space-y-2 text-sm">
                {usageReason ? (
                  <p className="text-amber-700 dark:text-amber-500">{usageReason}</p>
                ) : null}
                <p className="text-muted-foreground">{t.billing.usageWip}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">{t.billing.usageColTime}</th>
                        <th className="py-2 pr-4 font-medium">{t.billing.usageColModel}</th>
                        <th className="py-2 pr-4 font-medium">{t.billing.usageColIn}</th>
                        <th className="py-2 pr-4 font-medium">{t.billing.usageColOut}</th>
                        <th className="py-2 font-medium">{t.billing.usageColCredits}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((row) => (
                        <tr key={String(row.id ?? row.request_id)} className="border-b border-border/60">
                          <td className="py-2 pr-4 align-top text-xs text-muted-foreground">
                            {String(row.created_at ?? "—")}
                          </td>
                          <td className="py-2 pr-4 align-top font-mono text-xs">{String(row.model_id ?? "—")}</td>
                          <td className="py-2 pr-4 align-top">{String(row.prompt_tokens ?? "0")}</td>
                          <td className="py-2 pr-4 align-top">{String(row.completion_tokens ?? "0")}</td>
                          <td className="py-2 align-top">
                            {formatCreditsAmount(displayRowCredits(row, creditsPerUsd), language)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4">
                  <div className="flex flex-col gap-1 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                    <p>
                      {items.length > 0
                        ? t.billing.usagePaginationRange.replace("{{start}}", String(offset + 1)).replace(
                            "{{end}}",
                            String(offset + items.length),
                          )
                        : null}
                    </p>
                    {items.length > 0 ? (
                      <p>
                        {t.billing.meteringCreditsEquivalence.replace(
                          "{{per}}",
                          String(
                            Number.isFinite(creditsPerUsd) && creditsPerUsd > 0
                              ? creditsPerUsd
                              : DEFAULT_CREDITS_PER_USD,
                          ),
                        )}
                      </p>
                    ) : null}
                  </div>
                  {total > 0 && totalPages >= 1 ? (
                    <div className="flex flex-wrap items-center gap-1" role="navigation" aria-label="Pagination">
                      {pageButtons.map((entry, idx) =>
                        entry === "gap" ? (
                          <span
                            key={`gap-${idx}`}
                            className="px-1.5 text-sm text-muted-foreground"
                            aria-hidden
                          >
                            …
                          </span>
                        ) : (
                          <Button
                            key={entry}
                            type="button"
                            variant={entry === currentPage ? "default" : "outline"}
                            size="sm"
                            className="min-w-9 px-2"
                            disabled={listLoading}
                            onClick={() => setOffset((entry - 1) * PAGE_SIZE)}
                          >
                            {entry}
                          </Button>
                        )
                      )}
                    </div>
                  ) : null}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
        </div>
      </div>
  );
}
