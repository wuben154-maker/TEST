import { expect, test } from '@playwright/test';

test.describe('report-content-display-upgrade', () => {
  test('shared report renders title and analysis markdown without authentication', async ({ page }) => {
    await page.route('**/shared-reports/by-token/report-content-display-upgrade-token', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          title: 'E2E shared security report',
          created_at: '2026-04-25T09:00:00.000Z',
          blocks: [
            {
              type: 'analysis',
              id: 'analysis-1',
              title: 'Detailed analysis',
              content: [
                '## Executive Summary',
                '',
                'The report preserves markdown analysis content.',
                '',
                '- Finding one',
                '- Finding two',
              ].join('\n'),
            },
            {
              type: 'log',
              id: 'log-1',
              content: 'GET /shell.php?cmd=id',
            },
          ],
        }),
      });
    });

    await page.goto('/share/report-content-display-upgrade-token');

    await expect(page.getByRole('heading', { name: 'E2E shared security report', level: 1 })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Executive Summary' })).toBeVisible();
    await expect(page.getByText('The report preserves markdown analysis content.')).toBeVisible();
    await expect(page.getByText('GET /shell.php?cmd=id')).toBeVisible();
  });
});
