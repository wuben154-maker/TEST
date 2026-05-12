/**
 * Realtime context-usage indicator — exploratory E2E.
 *
 * Runs in the authenticated fixture so the composer is rendered. We don't
 * trigger a full analysis here (that requires live LLM credentials); instead
 * we verify the idle badge exists and is accessible. Full streaming coverage
 * lives in the unit tests for `contextUsage` + `ContextUsageBadge` and in
 * `multiAnalyzeStreamEvents.test.ts`.
 */
import { test, expect } from '../fixtures/authenticated';

test.describe('Realtime context-usage indicator', () => {
  test('idle badge is rendered beside the model selector', async ({ page }) => {
    await page.goto('/start');
    // Wait for the composer bottom bar to mount.
    const badge = page.getByTestId('context-usage-badge');
    // Idle variant is disabled (no invocations yet) — may not have
    // data-severity. We just need the element in the DOM with a valid label.
    await expect(badge.or(page.locator('button[aria-label="Context usage"]'))).toBeVisible({
      timeout: 10_000,
    });
  });
});
