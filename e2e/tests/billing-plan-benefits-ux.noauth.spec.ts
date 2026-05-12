import { test, expect } from "@playwright/test";

const apiBase = (
  process.env.E2E_API_BASE || "http://127.0.0.1:8000"
).replace(/\/$/, "");

test.describe("billing-plan-benefits-ux @no-auth", () => {
  test("E2E-01 GET /billing/plans returns Credits + benefits payload", async ({
    request,
  }) => {
    const res = await request.get(`${apiBase}/billing/plans`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.plans)).toBe(true);
    expect(body.plans.length).toBeGreaterThan(0);

    const pro = body.plans.find((p: { slug: string }) => p.slug === "pro");
    expect(pro, "pro plan must be present").toBeTruthy();
    expect(pro).toHaveProperty("included_credits_usd");
    expect(typeof pro.included_credits_usd).toBe("number");
    expect(pro).toHaveProperty("credits_label");
    expect(pro).toHaveProperty("features_json");
    expect(Array.isArray(pro.features_json)).toBe(true);
    expect(pro.features_json.length).toBeGreaterThan(0);
    for (const item of pro.features_json) {
      expect(item).toHaveProperty("id");
      expect(item).toHaveProperty("text");
    }
    expect(pro).toHaveProperty("quota_hints");
    expect(Array.isArray(pro.quota_hints)).toBe(true);
  });

  test("E2E-02 GET /billing/plans omits legacy `included_tokens_per_period`", async ({
    request,
  }) => {
    const res = await request.get(`${apiBase}/billing/plans`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    for (const plan of body.plans) {
      expect(
        Object.prototype.hasOwnProperty.call(plan, "included_tokens_per_period"),
        `plan ${plan.slug} must not expose legacy field`,
      ).toBe(false);
    }
  });

  test("E2E-03 /pricing renders Credits headline and benefits list", async ({
    page,
  }) => {
    await page.goto("/pricing");

    const proCard = page.locator('[data-plan-slug="pro"]');
    await expect(proCard).toBeVisible({ timeout: 15_000 });

    // Credits headline visible (USD-equivalent display).
    await expect(
      proCard.locator('[data-testid="plan-credits-headline"]'),
    ).toBeVisible();

    // At least one benefit row is rendered (li under benefits list).
    const benefitItems = proCard.locator("ul li[data-benefit-id]");
    expect(await benefitItems.count()).toBeGreaterThan(0);

    // Legacy "Included tokens / month" main display must NOT appear.
    const legacyMatches = await page
      .getByText(/Included tokens \/ month|每月包含 Token/i)
      .count();
    expect(legacyMatches).toBe(0);
  });

  test("E2E-04 /pricing metering disclosure is collapsed by default", async ({
    page,
  }) => {
    await page.goto("/pricing");
    // Disclosure trigger uses aria-expanded; default false (collapsed).
    const trigger = page
      .getByRole("button", { name: /How billing works|计费说明|課金の仕組み|요금 안내/i })
      .first();
    await expect(trigger).toBeVisible({ timeout: 15_000 });
    await expect(trigger).toHaveAttribute("aria-expanded", "false");

    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
  });
});
