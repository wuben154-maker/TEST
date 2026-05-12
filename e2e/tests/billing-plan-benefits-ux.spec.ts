import { test, expect } from "../fixtures/authenticated";

test.describe("billing-plan-benefits-ux (authenticated)", () => {
  test("E2E-05 /billing renders credits progress and plan cards", async ({
    page,
  }) => {
    await page.goto("/billing");

    const progress = page.getByTestId("billing-progress-credits");
    await expect(progress).toBeVisible({ timeout: 15_000 });
    await expect(progress.locator('[role="progressbar"]')).toBeVisible();

    // Plan grid: first card has the Credits headline.
    const firstCard = page.locator("[data-plan-slug]").first();
    await expect(firstCard).toBeVisible();
    await expect(
      firstCard.locator('[data-testid="plan-credits-headline"]'),
    ).toBeVisible();
  });
});
