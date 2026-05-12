import { test, expect } from "../fixtures/authenticated";

test.describe("analysis-workspace-report-collapse", () => {
  test("E2E-01: chat column has max-width wrapper on desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/start");
    const col = page.getByTestId("chat-column");
    await expect(col).toBeVisible({ timeout: 20_000 });
    await expect(col).toHaveClass(/max-w-3xl/);
  });
});
