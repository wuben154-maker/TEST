import { describe, expect, it } from "vitest";
import {
  coerceCreditsPerUsd,
  formatBillingUsdAmount,
  parseBillingDecimal,
  periodCreditsFromBillingSummary,
  resolveLocalizedText,
  resolvePlanBenefits,
  resolvePlanQuotaHints,
  resolvePlanTagline,
  usdToCreditsAmount,
} from "./billingDisplay";

describe("usdToCreditsAmount / parseBillingDecimal / coerceCreditsPerUsd", () => {
  it("converts USD to credits at the default rate", () => {
    expect(usdToCreditsAmount(1)).toBe(100);
    expect(usdToCreditsAmount(0.5, 100)).toBe(50);
  });

  it("parseBillingDecimal accepts numbers and numeric strings", () => {
    expect(parseBillingDecimal("12.5")).toBe(12.5);
    expect(parseBillingDecimal(3)).toBe(3);
    expect(parseBillingDecimal("")).toBe(0);
    expect(parseBillingDecimal(undefined)).toBe(0);
  });

  it("coerceCreditsPerUsd picks the first positive value", () => {
    expect(coerceCreditsPerUsd(undefined, 80, "120")).toBe(80);
    expect(coerceCreditsPerUsd(null, "bad", 100)).toBe(100);
    expect(coerceCreditsPerUsd(undefined, "bad")).toBe(100);
  });
});

describe("periodCreditsFromBillingSummary", () => {
  it("uses credits field when provided", () => {
    const s = {
      spent_credits_period: "42",
      spent_usd_period: "1",
    } as Record<string, unknown>;
    expect(periodCreditsFromBillingSummary(s, "spent_credits_period", "spent_usd_period", 100)).toBe(42);
  });

  it("falls back to USD × rate when credits key missing", () => {
    const s = { spent_usd_period: "0.25" } as Record<string, unknown>;
    expect(periodCreditsFromBillingSummary(s, "spent_credits_period", "spent_usd_period", 100)).toBe(25);
  });
});

describe("formatBillingUsdAmount", () => {
  it("formats positive USD with cents", () => {
    const out = formatBillingUsdAmount(12.345, "en");
    expect(out).toMatch(/\$12\.3[45]/);
  });

  it("falls back to $0.00 for negative or NaN", () => {
    expect(formatBillingUsdAmount(-1, "en")).toMatch(/\$0\.00/);
    expect(formatBillingUsdAmount(Number.NaN, "en")).toMatch(/\$0\.00/);
  });
});

describe("resolveLocalizedText", () => {
  it("prefers requested language", () => {
    const out = resolveLocalizedText({ en: "hi", zh: "你好" }, "zh");
    expect(out).toBe("你好");
  });
  it("falls back to en when requested locale missing", () => {
    const out = resolveLocalizedText({ en: "hi" }, "zh");
    expect(out).toBe("hi");
  });
  it("falls back to first non-empty entry when en missing", () => {
    const out = resolveLocalizedText({ ja: "こんにちは" }, "zh");
    expect(out).toBe("こんにちは");
  });
  it("returns empty string for missing/empty blob", () => {
    expect(resolveLocalizedText(undefined, "en")).toBe("");
    expect(resolveLocalizedText({}, "en")).toBe("");
  });
});

describe("resolvePlanBenefits", () => {
  it("yields ordered list with id + localized text", () => {
    const plan = {
      features_json: [
        { id: "a", text: { en: "Alpha", zh: "甲" } },
        { id: "b", text: { en: "Beta" } },
      ],
    } as const;
    const out = resolvePlanBenefits(plan, "zh");
    expect(out).toEqual([
      { id: "a", text: "甲" },
      { id: "b", text: "Beta" },
    ]);
  });

  it("uses fallback when DB benefits are empty", () => {
    const out = resolvePlanBenefits(
      { features_json: [] },
      "en",
      [{ id: "x", text: "Backup" }],
    );
    expect(out).toEqual([{ id: "x", text: "Backup" }]);
  });
});

describe("resolvePlanQuotaHints", () => {
  it("preserves id, value, and resolves label", () => {
    const out = resolvePlanQuotaHints(
      {
        quota_hints: [
          {
            id: "concurrent_analyses",
            value: "3",
            label: { en: "Concurrent analyses" },
          },
        ],
      },
      "en",
    );
    expect(out).toEqual([
      { id: "concurrent_analyses", label: "Concurrent analyses", value: "3" },
    ]);
  });

  it("uses i18n fallback label when blob missing", () => {
    const out = resolvePlanQuotaHints(
      { quota_hints: [{ id: "queue_priority", value: "high" }] },
      "en",
      { queue_priority: "Queue priority" },
    );
    expect(out[0].label).toBe("Queue priority");
  });

  it("drops items without value", () => {
    const out = resolvePlanQuotaHints(
      { quota_hints: [{ id: "x", value: "" }] },
      "en",
    );
    expect(out).toEqual([]);
  });
});

describe("resolvePlanTagline", () => {
  it("returns the localized tagline when present", () => {
    const out = resolvePlanTagline({ tagline_json: { en: "Tag" } }, "en");
    expect(out).toBe("Tag");
  });
  it("returns empty string when missing", () => {
    expect(resolvePlanTagline({}, "en")).toBe("");
  });
});
