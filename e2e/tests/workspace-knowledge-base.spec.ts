import { test, expect } from "../fixtures/authenticated";

test.describe("workspace-knowledge-base", () => {
  test("E2E-01: knowledge route shows primary heading", async ({ page }) => {
    await page.goto("/knowledge");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
  });

  test("E2E-02: knowledge page exposes search and refresh", async ({ page }) => {
    await page.goto("/knowledge");
    await expect(page.getByTestId("kb-search")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("kb-refresh")).toBeVisible();
  });

  test("E2E-03: empty state shows workspace CTA when there are no items", async ({ page }) => {
    await page.goto("/knowledge");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
    const listItems = page.getByRole("listitem");
    const cta = page.getByTestId("kb-empty-cta");
    if ((await listItems.count()) === 0) {
      await expect(cta).toBeVisible({ timeout: 5_000 });
    }
  });
});
