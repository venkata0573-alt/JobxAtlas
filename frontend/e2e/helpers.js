// Shared login + API helpers for Playwright e2e tests.
//
// Two axes to cover:
//   loginViaUi(page, persona)    — drives /login through the SPA, exercising
//                                   the login form. Slower but end-to-end.
//   loginViaApi(page, persona)   — POSTs /api/auth/login directly and copies
//                                   the returned Set-Cookie into the browser
//                                   context. Fast — use for setup steps when
//                                   the login UI isn't what the test is
//                                   trying to verify.
//
// resetDb() — hits a debug endpoint IF it exists, otherwise noop. The
//   backend has no /api/test/reset (Phase 1a decision — tests use pytest
//   conftest's clean_db, not a runtime endpoint). Documented below.
//
// All API calls use the Playwright APIRequestContext with
// ignoreHTTPSErrors so the self-signed cert on the backend doesn't blow up.

const { FIXTURE_PASSWORD, BACKEND_URL } = require('./personas');

async function loginViaApi(page, persona) {
  // page.request inherits the browser context's ignoreHTTPSErrors:true
  // from playwright.config.js — no need to build a new context.
  const res = await page.request.post(`${BACKEND_URL}/api/auth/login`, {
    data: { email: persona.email, password: FIXTURE_PASSWORD },
  });
  if (!res.ok()) {
    throw new Error(`loginViaApi(${persona.email}) failed: ${res.status()} ${await res.text()}`);
  }
  // Playwright's page.context carries its own cookie jar. Copy cookies from
  // the login response into the browser context so subsequent page.goto()
  // requests carry the access_token cookie.
  const setCookie = res.headersArray().filter(h => h.name.toLowerCase() === 'set-cookie');
  const jar = [];
  for (const c of setCookie) {
    // Parse minimal fields — Playwright's addCookies wants {name, value, url, ...}.
    const [nv] = c.value.split(';');
    const [name, value] = nv.split('=');
    if (name && value) {
      jar.push({
        name: name.trim(),
        value: value.trim(),
        url: BACKEND_URL,
        // The SPA reads these on requests to the backend; sameSite=None per
        // deps.py:94. secure=true required since sameSite=None.
        sameSite: 'None',
        secure: true,
        httpOnly: name.trim() === 'access_token' || name.trim() === 'refresh_token',
      });
    }
  }
  await page.context().addCookies(jar);
}

async function loginViaUi(page, persona) {
  await page.goto('/login');
  // Testids from constants/testIds.js (canonical registry — not the newer
  // /constants/testIds/ folder which is only 3 constants and unused by
  // Login.jsx).
  await page.getByTestId('login-email').fill(persona.email);
  await page.getByTestId('login-password').fill(FIXTURE_PASSWORD);
  await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/auth/login') && r.status() === 200),
    page.getByTestId('login-submit-btn').click(),
  ]);
  // Wait for role-based redirect (Login.jsx routes talent → /talent,
  // employer → /employer, admin → /admin).
}

async function logoutViaUi(page) {
  // Header uses TID.navLogout = "nav-logout-btn" (constants/testIds.js).
  const btn = page.getByTestId('nav-logout-btn');
  if (await btn.count()) {
    await btn.first().click();
    return;
  }
  // Fallback: hit the endpoint directly. Header may hide the btn on some
  // routes; POST /api/auth/logout clears cookies regardless.
  await page.request.post('/api/auth/logout', { ignoreHTTPSErrors: true });
}

module.exports = { loginViaApi, loginViaUi, logoutViaUi };
