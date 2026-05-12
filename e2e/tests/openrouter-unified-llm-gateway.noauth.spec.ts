import { test, expect } from '@playwright/test';

test.describe('openrouter-unified-llm-gateway', () => {
  test('model selector can show OpenRouter beside OpenCode', async ({ page }) => {
    const user = {
      id: '00000000-0000-4000-8000-000000000001',
      email: 'e2e@example.test',
      username: 'E2E User',
    };

    await page.addInitScript((authUser) => {
      localStorage.setItem('auth_token', 'e2e-token');
      localStorage.setItem('auth_user', JSON.stringify(authUser));
    }, user);

    await page.route('**/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(user),
      });
    });

    await page.route('**/api/models', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          models: [
            {
              id: 'openrouter/anthropic/claude-opus-4.7',
              name: 'Claude Opus 4.7 (OpenRouter)',
              provider: 'openrouter',
              context_window: 1000000,
              max_output_tokens: 65536,
            },
            {
              id: 'opencode/gpt-5.5',
              name: 'GPT 5.5 (Zen)',
              provider: 'opencode',
              context_window: 1100000,
              max_output_tokens: 16384,
            },
          ],
        }),
      });
    });

    await page.goto('/start');
    await page.getByRole('button', { name: /Claude Opus 4\.7|Model/i }).click();

    await expect(page.getByText('OpenRouter', { exact: true })).toBeVisible();
    await expect(page.getByText('OpenCode Zen', { exact: true })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Claude Opus 4.7 (OpenRouter)' })).toBeVisible();
  });
});
