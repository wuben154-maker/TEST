import { test, expect } from "../fixtures/authenticated";

test.describe("official-website (auth)", () => {
  test("E2E-03a signed-in marketing header hides Sign in and shows account menu", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("official-site-sign-in")).toHaveCount(0);
    await expect(page.getByTestId("official-site-user-menu-trigger")).toBeVisible({
      timeout: 25_000,
    });
  });

  test("E2E-03 logout returns to marketing home", async ({ page }) => {
    await page.goto("/start");
    await expect(page.getByTestId("user-menu-trigger")).toBeVisible({
      timeout: 25_000,
    });

    await page.getByTestId("user-menu-trigger").click();
    await page.getByRole("menuitem", { name: /sign out|退出登录/i }).click();

    await expect.poll(() => new URL(page.url()).pathname).toBe("/");

    await expect(
      page.getByTestId("official-site-hero-title"),
    ).toBeVisible({ timeout: 15_000 });
  });
});
