import { test, expect } from "../fixtures/authenticated";

test.describe("Smoke — authenticated home", () => {
  test("home page loads and shows the main workspace", async ({ page }) => {
    await page.goto("/start");
    await expect(page).toHaveTitle(/SecManus|Workspace/i, { timeout: 10_000 });
    const body = page.locator("body");
    await expect(body).toBeVisible();
  });
});
