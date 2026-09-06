// Smoke: proves the stack is reachable and the login form works end-to-end.
// If this fails, none of the flow tests can pass — investigate here first.

const { test, expect } = require('@playwright/test');
const { PERSONAS } = require('./personas');
const { loginViaUi, loginViaApi, logoutViaUi } = require('./helpers');

test('landing page loads', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/localhost:13000/);
  // Landing has a hero + "Get started" button per TID.landingGetStarted.
});

test('login via UI → /auth/me returns the seeded persona', async ({ page }) => {
  await loginViaUi(page, PERSONAS.TALENT_CLEAN);
  // After login, Login.jsx redirects by role — talent → /talent.
  await expect(page).toHaveURL(/\/talent/);
  // /auth/me should return the persona through the SPA's own axios
  // (proves the cookie is being sent).
  const meRes = await page.request.get('https://localhost:18443/api/auth/me', {
    ignoreHTTPSErrors: true,
  });
  expect(meRes.status()).toBe(200);
  const me = await meRes.json();
  expect(me.email).toBe(PERSONAS.TALENT_CLEAN.email);
});

test('login via API → cookie carries into browser context', async ({ page }) => {
  await loginViaApi(page, PERSONAS.EMPLOYER_CARD);
  // Now the SPA should treat us as authed. Go to a protected page.
  await page.goto('/employer');
  // Employer dashboard renders (no redirect back to /login).
  await expect(page).not.toHaveURL(/\/login/);
});
