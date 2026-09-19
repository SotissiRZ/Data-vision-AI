import { expect, test } from '@playwright/test';

test('@smoke application shell is usable', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('DataVision AI').first()).toBeVisible();
  await expect(page.getByRole('button', { name: /Rechercher/i })).toBeVisible();
  await expect(page.getByText('AI Analyst').first()).toBeVisible();
});

test('@smoke display controls remain available', async ({ page }) => {
  await page.goto('/');
  const display = page.getByRole('button', { name: /Régler l'affichage/i });
  await expect(display).toBeVisible();
  await display.click();
  await expect(page.getByText('Mode de lecture')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Grand texte' })).toBeVisible();
});
