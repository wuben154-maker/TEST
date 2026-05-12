import { describe, expect, it } from "vitest";
import {
  normalizeQuotaHintsForComparison,
  QUOTA_HINT_ROW_ORDER,
} from "./quotaComparison";

describe("normalizeQuotaHintsForComparison", () => {
  const labels: Partial<Record<string, string>> = {
    concurrent_analyses: "Concurrent",
    e2b_sandbox: "Sandbox",
  };

  it("pads missing ordered ids and preserves label fallbacks", () => {
    const out = normalizeQuotaHintsForComparison(
      [{ id: "concurrent_analyses", label: "CA", value: "3" }],
      labels,
    );
    expect(out[0]).toEqual({ id: "concurrent_analyses", label: "CA", value: "3" });
    expect(out.find((r) => r.id === "queue_priority")?.value).toBe("—");
    expect(out.find((r) => r.id === "e2b_sandbox")?.label).toBe("Sandbox");
  });

  it("appends quota ids not listed in QUOTA_HINT_ROW_ORDER", () => {
    const out = normalizeQuotaHintsForComparison(
      [
        { id: "concurrent_analyses", label: "C", value: "1" },
        { id: "future_metric", label: "Future", value: "x" },
      ],
      {},
    );
    expect(out[out.length - 1]).toEqual({
      id: "future_metric",
      label: "Future",
      value: "x",
    });
    expect(QUOTA_HINT_ROW_ORDER.length).toBeGreaterThan(0);
  });
});
