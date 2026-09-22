import { expect, test } from '@playwright/test';

const API = '/api/backend';

test('@production web and backend readiness are healthy', async ({ request }) => {
  const web = await request.get('/api/health');
  expect(web.ok()).toBeTruthy();

  const backend = await request.get(`${API}/health/ready`);
  expect(backend.ok()).toBeTruthy();
  const payload = await backend.json();
  expect(payload.ready).toBeTruthy();
});

test('@production assistant opens, exposes context and resizes', async ({ page }) => {
  await page.goto('/');
  const launcher = page.getByRole('button', { name: 'Ouvrir DataVision AI' });
  await expect(launcher).toBeVisible();
  await launcher.click();

  const assistant = page.getByRole('dialog', { name: 'Assistant DataVision AI' });
  await expect(assistant).toBeVisible();
  await expect(page.getByText('Contexte actif').first()).toBeVisible();

  const enlarge = page.getByRole('button', { name: 'Agrandir la fenêtre' });
  await expect(enlarge).toBeVisible();
  await enlarge.click();
  await expect(page.getByRole('button', { name: 'Réduire la fenêtre' })).toBeVisible();
});

test('@production core proxy rejects no request with gateway failure', async ({ request }) => {
  const response = await request.get(`${API}/health/live`);
  expect(response.status()).toBeLessThan(500);
});
