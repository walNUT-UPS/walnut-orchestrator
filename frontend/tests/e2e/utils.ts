import { Page, expect } from '@playwright/test';

export async function loginViaUI(page: Page) {
  const email = process.env.PW_ADMIN_EMAIL || 'admin@example.com';
  const password = process.env.PW_ADMIN_PASSWORD || 'admin12345_admin12345_admin12345!';

  await page.goto('/');

  // If already authenticated, ProtectedRoute will render the app layout; otherwise LoginForm.
  const isLoginVisible = await page.locator('form:has-text("Sign in")').first().isVisible().catch(() => false);
  if (isLoginVisible) {
    await page.getByLabel(/email|username/i).fill(email);
    await page.getByLabel(/password/i).fill(password);
    await page.getByRole('button', { name: /sign in|log in/i }).click();
  }

  // Expect TopBar to appear (navigation button present)
  await expect(page.getByRole('navigation').or(page.locator('text=Overview'))).toBeTruthy();
}

export async function assertMenuNearTrigger(page: Page, triggerSelector: string) {
  const trigger = page.locator(triggerSelector);
  await expect(trigger).toBeVisible();

  const scrollBefore = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
  await trigger.click();

  const wrapper = page.locator('[data-radix-popper-content-wrapper]').first();
  await expect(wrapper).toBeVisible();

  const tb = await trigger.boundingBox();
  const cb = await wrapper.boundingBox();
  if (!tb || !cb) throw new Error('Failed to measure bounding boxes');

  // Should not teleport to top-left
  expect(cb.x).toBeGreaterThan(8);
  expect(cb.y).toBeGreaterThan(8);

  // Should be within viewport
  const vw = page.viewportSize()!.width;
  const vh = page.viewportSize()!.height;
  expect(cb.x + cb.width).toBeLessThan(vw + 4);
  expect(cb.y + cb.height).toBeLessThan(vh + 4);

  // Should be positioned near trigger (either aligned by x or y within a reasonable distance)
  const dx = Math.abs((cb.x + cb.width / 2) - (tb.x + tb.width / 2));
  const dy = Math.abs(cb.y - (tb.y + tb.height));
  expect(Math.min(dx, dy)).toBeLessThan(200);

  // Should not cause scroll jump
  const scrollAfter = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
  expect(Math.abs(scrollAfter.x - scrollBefore.x)).toBeLessThan(5);
  expect(Math.abs(scrollAfter.y - scrollBefore.y)).toBeLessThan(5);
}

