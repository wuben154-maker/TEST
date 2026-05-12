import { test, expect } from "@playwright/test";

test.describe("official-website @no-auth", () => {
  test("E2E-01 public home shows marketing hero", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("official-site-hero-title")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/Security Agent/i).first()).toBeVisible();
    // Workspace sidebar copy should not appear on public home
    await expect(page.locator("text=What do you want to work on?")).toHaveCount(0);
  });

  test("E2E-02 Sign in navigates to auth", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("official-site-sign-in").click();
    await expect(page).toHaveURL(/\/auth/);
  });

  test("E2E-04 marketing resource pages render", async ({ page }) => {
    await page.goto("/help");
    await expect(page.locator("#main")).toBeVisible({ timeout: 15_000 });
    await page.goto("/product-log");
    await expect(page.locator("#main")).toBeVisible({ timeout: 15_000 });
    await page.goto("/blog");
    await expect(page.locator("#main")).toBeVisible({ timeout: 15_000 });
    await page.goto("/solutions/security-team");
    await expect(page.locator("#main")).toBeVisible({ timeout: 15_000 });
  });
});
