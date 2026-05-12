import type { Language } from "@/i18n";
import type {
  BillingPlanRow,
  LocalizedText,
  PlanFeatureItem,
  PlanQuotaHint,
} from "@/lib/api-client";

export const DEFAULT_CREDITS_PER_USD = 100;

/** First positive finite value wins; used for API `credits_per_usd` from plans/summary/usage. */
export function coerceCreditsPerUsd(...candidates: unknown[]): number {
  for (const x of candidates) {
    if (typeof x === "number" && Number.isFinite(x) && x > 0) return x;
    if (typeof x === "string" && x.trim() !== "") {
      const n = Number.parseFloat(x);
      if (Number.isFinite(n) && n > 0) return n;
    }
  }
  return DEFAULT_CREDITS_PER_USD;
}

const localeForLang = (language: Language): string => {
  if (language === "zh") return "zh-CN";
  if (language === "ja") return "ja-JP";
  if (language === "ko") return "ko-KR";
  return "en-US";
};

export function parseBillingDecimal(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return Math.max(0, v);
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number.parseFloat(v);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }
  return 0;
}

/** Display Credits: 100 Credits == USD 1 (product rule; gate remains USD). */
export function usdToCreditsAmount(
  usd: number,
  creditsPerUsd: number = DEFAULT_CREDITS_PER_USD,
): number {
  const rate = Number.isFinite(creditsPerUsd) && creditsPerUsd > 0 ? creditsPerUsd : DEFAULT_CREDITS_PER_USD;
  const u = Number.isFinite(usd) && usd >= 0 ? usd : 0;
  return u * rate;
}

/** Prefer API credits field when present; otherwise derive from USD × rate. */
export function periodCreditsFromBillingSummary(
  summary: Record<string, unknown>,
  creditsKey: "spent_credits_period" | "monthly_spend_cap_credits",
  usdKey: "spent_usd_period" | "monthly_spend_cap_usd",
  rate: number,
): number {
  if (Object.prototype.hasOwnProperty.call(summary, creditsKey)) {
    const v = summary[creditsKey];
    if (v !== undefined && v !== null) return parseBillingDecimal(v);
  }
  return usdToCreditsAmount(parseBillingDecimal(summary[usdKey]), rate);
}

export function formatCreditsAmount(credits: number, language: Language): string {
  const safe = Number.isFinite(credits) && credits >= 0 ? credits : 0;
  return safe.toLocaleString(localeForLang(language), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

// Kept for the disclosure (folded) layer where token estimates are exposed as a
// transparency aid, never as the primary display unit.
export function formatBillingTokens(n: number, language: Language): string {
  if (n <= 0) return "—";
  return n.toLocaleString(localeForLang(language));
}

export function formatBillingPrice(usd: number, language: Language): string {
  if (usd <= 0) return "—";
  return new Intl.NumberFormat(localeForLang(language), {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(usd);
}

// USD with cents, used for spend / cap displays where precision matters.
export function formatBillingUsdAmount(usd: number, language: Language): string {
  const safe = Number.isFinite(usd) && usd >= 0 ? usd : 0;
  return new Intl.NumberFormat(localeForLang(language), {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(safe);
}

// Resolve a localized string blob with a deterministic fallback chain.
// Order: requested language → English → first available value → empty string.
export function resolveLocalizedText(
  blob: LocalizedText | undefined,
  language: Language,
): string {
  if (!blob) return "";
  const direct = blob[language];
  if (direct && direct.trim()) return direct;
  const en = blob.en;
  if (en && en.trim()) return en;
  for (const v of Object.values(blob)) {
    if (typeof v === "string" && v.trim()) return v;
  }
  return "";
}

export type ResolvedBenefit = {
  id: string;
  text: string;
};

export function resolvePlanBenefits(
  plan: Pick<BillingPlanRow, "features_json">,
  language: Language,
  fallback: ResolvedBenefit[] = [],
): ResolvedBenefit[] {
  const items: PlanFeatureItem[] = Array.isArray(plan.features_json)
    ? plan.features_json
    : [];
  const resolved = items
    .map((item): ResolvedBenefit | null => {
      const text = resolveLocalizedText(item?.text, language);
      if (!text) return null;
      return { id: String(item.id || ""), text };
    })
    .filter((x): x is ResolvedBenefit => x !== null);
  if (resolved.length > 0) return resolved;
  return fallback;
}

export type ResolvedQuotaHint = {
  id: string;
  label: string;
  value: string;
};

export function resolvePlanQuotaHints(
  plan: Pick<BillingPlanRow, "quota_hints">,
  language: Language,
  labelFallback: Partial<Record<string, string>> = {},
): ResolvedQuotaHint[] {
  const items: PlanQuotaHint[] = Array.isArray(plan.quota_hints) ? plan.quota_hints : [];
  return items
    .map((item): ResolvedQuotaHint | null => {
      const id = String(item?.id || "");
      const value = String(item?.value ?? "").trim();
      if (!id || !value) return null;
      const label =
        resolveLocalizedText(item?.label, language) || labelFallback[id] || id;
      return { id, label, value };
    })
    .filter((x): x is ResolvedQuotaHint => x !== null);
}

export function resolvePlanTagline(
  plan: Pick<BillingPlanRow, "tagline_json">,
  language: Language,
): string {
  return resolveLocalizedText(plan.tagline_json, language);
}
