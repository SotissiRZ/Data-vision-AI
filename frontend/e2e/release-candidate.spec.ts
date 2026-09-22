import { expect, test } from '@playwright/test';

const API = '/api/backend';

test('@release-candidate security headers survive the frontend proxy', async ({ request }) => {
  const response = await request.get(`${API}/health`);
  expect(response.ok()).toBeTruthy();
  const headers = response.headers();
  expect(headers['x-content-type-options']).toBe('nosniff');
  expect(headers['x-frame-options']).toBe('DENY');
  expect(headers['referrer-policy']).toBe('no-referrer');
  expect(headers['permissions-policy']).toContain('camera=()');
});

test('@release-candidate unknown API routes remain correlated and non-5xx', async ({ request }) => {
  const response = await request.get(`${API}/__release_candidate_missing__`);
  expect(response.status()).toBe(404);
  expect(response.headers()['x-request-id']).toBeTruthy();
  expect(response.headers()['x-trace-id']).toBeTruthy();
});

test('@release-candidate critical shell remains keyboard reachable', async ({ page }) => {
  await page.goto('/');
  const skip = page.locator('.skip-link');
  await skip.focus();
  await expect(skip).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();

  const launcher = page.getByRole('button', { name: 'Ouvrir DataVision AI' });
  await launcher.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: 'Assistant DataVision AI' })).toBeVisible();
});
