import { describe, expect, it } from "vitest";
import {
  isMarketingSolutionSlug,
  MARKETING_SOLUTION_SLUGS,
  SOLUTION_SLUG_TO_I18N_KEY,
} from "./marketing-routes";

describe("marketing-routes", () => {
  it("accepts known solution slugs", () => {
    for (const slug of MARKETING_SOLUTION_SLUGS) {
      expect(isMarketingSolutionSlug(slug)).toBe(true);
      expect(SOLUTION_SLUG_TO_I18N_KEY[slug]).toBeTruthy();
    }
  });

  it("rejects unknown slugs", () => {
    expect(isMarketingSolutionSlug("unknown")).toBe(false);
    expect(isMarketingSolutionSlug("")).toBe(false);
  });
});
