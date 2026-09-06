// Flow 1: register → email verification → login → logout
//
// v2 posture: no API fallbacks. Every click must land on real UI. If a
// flow cannot be completed through the UI, the test FAILS — that's the
// finding we want surfaced.
//
// Register-form gap (see Phase 1c v1 report): the /register page loads
// Cloudflare Turnstile from challenges.cloudflare.com, which is (a) an
// outbound-network dependency test hosts often block, and (b) even when
// reachable, ADDS a non-deterministic third-party rendering step that
// makes the test flaky. This spec therefore does NOT drive the register
// form via UI — backend/tests/test_03_auth.py::TestRegister covers the
// register endpoint end-to-end (via direct-import). What we CAN cover
// through the UI is: login form, /auth/me round-trip, logout button,
// wrong-password error path.

const { test, expect } = require('@playwright/test');
const { PERSONAS, BACKEND_URL } = require('./personas');
const { loginViaUi } = require('./helpers');


test.describe('login → session → logout (UI-only, no API fallbacks)', () => {
  test('talent login via UI lands on /talent and /auth/me reflects role', async ({ page }) => {
    await loginViaUi(page, PERSONAS.TALENT_CLEAN);
    await expect(page).toHaveURL(/\/talent/, { timeout: 10_000 });
    // /auth/me round-trip proves the cookie is being sent.
    const me = await page.request.get(`${BACKEND_URL}/api/auth/me`, {
      ignoreHTTPSErrors: true,
    });
    expect(me.status()).toBe(200);
    expect((await me.json()).role).toBe('talent');
  });

  test('employer login lands on /employer', async ({ page }) => {
    await loginViaUi(page, PERSONAS.EMPLOYER_CARD);
    await expect(page).toHaveURL(/\/employer/, { timeout: 10_000 });
  });

  test('admin login DOES NOT auto-route to /admin (F-14 finding)', async ({ page }) => {
    // Login.jsx:22 only handles talent + employer redirects — admin falls
    // into the "/" default. Recorded as F-14 in SECURITY_BACKLOG.md.
    // Admin can still reach /admin via direct nav; test both invariants.
    await loginViaUi(page, PERSONAS.ADMIN_ALL);
    await expect(page).toHaveURL(/localhost:13000\/?$/, { timeout: 10_000 });
    await page.goto('/admin');
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('header logout button clears session (S-31 canary)', async ({ page }) => {
    // S-31: the header logout button posts /api/auth/logout but the
    // browser cookie jar retains access_token because the backend's
    // delete_cookie call at auth.py:212 omits `secure=True, samesite="none"`
    // that the original set_cookie used (deps.py:92). Chromium treats the
    // deletion Set-Cookie as a NEW cookie (unsecured) rather than
    // overwriting the Secure one, so the httpOnly Secure cookie survives.
    // This test is the canary: today it FAILS (401 not observed post-
    // click). When S-31 lands (fix delete_cookie flags), it starts
    // passing and the assertion below reflects reality.
    await loginViaUi(page, PERSONAS.TALENT_CLEAN);
    await expect(page).toHaveURL(/\/talent/);

    // Click the header logout button. NO manual clearCookies fallback —
    // if this test fails, that's the S-31 finding.
    const logoutBtn = page.getByTestId('nav-logout-btn').first();
    await expect(logoutBtn).toBeVisible({ timeout: 5_000 });
    await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/auth/logout')
                              && r.status() === 200),
      logoutBtn.click(),
    ]);

    // Cookie must be cleared: /auth/me now 401s.
    const me = await page.request.get(`${BACKEND_URL}/api/auth/me`, {
      ignoreHTTPSErrors: true,
    });
    expect(me.status()).toBe(401);
  });

  test('wrong password stays on /login', async ({ page }) => {
    await page.goto('/login');
    await page.getByTestId('login-email').fill(PERSONAS.TALENT_CLEAN.email);
    await page.getByTestId('login-password').fill('not-the-right-password');
    await page.getByTestId('login-submit-btn').click();
    // Sonner toast fires; assert URL invariant (still on /login).
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL(/\/login/);
  });
});
