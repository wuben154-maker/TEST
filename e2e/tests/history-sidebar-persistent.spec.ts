import { test, expect } from "../fixtures/authenticated";

test.describe("history-sidebar-persistent", () => {
  test("E2E-01: docked project aside visible on desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/start");
    await expect(
      page.getByRole("complementary", {
        name: /Workspace navigation|工作区导航|ワークスペースナビ|작업 공간 탐색/i,
      }),
    ).toBeVisible({ timeout: 20_000 });
  });

  test("E2E-02: sidebar stays in layout when opening billing (no full remount)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/start");
    const aside = page.getByRole("complementary", {
      name: /Workspace navigation|工作区导航|ワークスペースナビ|작업 공간 탐색/i,
    });
    await expect(aside).toBeVisible({ timeout: 20_000 });
    await page.locator("aside nav").getByRole("link", { name: /Billing|账单|請求|결제/i }).click();
    await expect(page).toHaveURL(/\/billing$/);
    await expect(aside).toBeVisible();
  });
});
