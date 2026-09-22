import { test, expect } from '@playwright/test';

test.describe('@accessibility DataVision shell', () => {
  test('keyboard, language direction and accessibility preferences', async ({ page }) => {
    await page.goto('/');

    const skip = page.locator('.skip-link');
    await skip.focus();
    await expect(skip).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('#main-content')).toBeFocused();

    await page.keyboard.press('Control+K');
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);

    const display = page.locator('.display-trigger');
    await display.click();
    const language = page.locator('.display-language select');
    await language.selectOption('en');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await language.selectOption('ar');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

    const toggles = page.locator('.accessibility-toggles input');
    await toggles.nth(0).check();
    await expect(page.locator('html')).toHaveAttribute('data-dv-contrast', 'high');
    await toggles.nth(1).check();
    await expect(page.locator('html')).toHaveAttribute('data-dv-motion', 'reduced');
  });
});
