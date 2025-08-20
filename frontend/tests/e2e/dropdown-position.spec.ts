import { test, expect } from '@playwright/test';
import { loginViaUI, assertMenuNearTrigger } from './utils';

test.describe('DropdownMenu positioning', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('TopBar avatar menu is positioned near trigger (desktop)', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Run on chromium for consistency');
    await page.goto('/overview');
    await assertMenuNearTrigger(page, '[data-testid="avatar-menu-trigger"]');
    await page.screenshot({ path: `tests/e2e-artifacts/topbar-avatar-desktop.png`, fullPage: true });
  });

  test('TopBar mobile nav menu positions correctly (mobile)', async ({ page }) => {
    await page.goto('/overview');
    // Mobile trigger visible on small viewports (Pixel 5 project)
    await assertMenuNearTrigger(page, '[data-testid="mobile-nav-trigger"]');
    await page.screenshot({ path: `tests/e2e-artifacts/topbar-mobile-nav.png`, fullPage: true });
  });

  test('Hosts row action menu positions correctly', async ({ page }) => {
    await page.goto('/hosts');
    // Open first action trigger
    const firstTrigger = page.locator('[data-testid="instance-actions-trigger"]').first();
    await assertMenuNearTrigger(page, '[data-testid="instance-actions-trigger"]');
    await page.screenshot({ path: `tests/e2e-artifacts/hosts-actions.png`, fullPage: true });
  });

  test('Integrations type action menu positions correctly', async ({ page }) => {
    await page.goto('/settings');
    // The settings screen redirects to a default tab; scroll if needed and open a type actions menu
    await assertMenuNearTrigger(page, '[data-testid="type-actions-trigger"]');
    await page.screenshot({ path: `tests/e2e-artifacts/integrations-type-actions.png`, fullPage: true });
  });
});

