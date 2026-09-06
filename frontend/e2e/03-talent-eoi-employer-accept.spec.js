// Flow 3: talent raises EOI → employer sees + accepts → engagement created
//
// v2 posture: no API fallbacks. All clicks are on real form fields and
// buttons. EOI.jsx testids from constants/testIds.js:
//   TID.eoiEmployer  → "eoi-employer-select"  (input, not select — misnomer)
//   TID.eoiMessage   → "eoi-message"
//   TID.eoiHours     → "eoi-hours"
//   TID.eoiSubmit    → "eoi-submit-btn"
//   TID.eoiAccept(id)→ "eoi-accept-<id>"
//   TID.eoiRow(id)   → "eoi-row-<id>"

const { test, expect } = require('@playwright/test');
const { PERSONAS, BACKEND_URL } = require('./personas');
const { loginViaApi } = require('./helpers');


test('talent raises EOI → employer accepts → engagement created', async ({ page, browser }) => {
  const uniqMsg = `E2E EOI ${Date.now()}`;

  // -- Talent side. Listener BEFORE goto so we don't race the mount fetch.
  await loginViaApi(page, PERSONAS.TALENT_CLEAN);
  const talentListResp = page.waitForResponse(r =>
    r.url().includes('/api/eoi') && r.request().method() === 'GET',
    { timeout: 15_000 });
  await page.goto('/eoi');
  await talentListResp;

  await page.getByTestId('eoi-employer-select').fill(PERSONAS.EMPLOYER_CARD.id);
  await page.getByTestId('eoi-hours').fill('20');
  await page.getByTestId('eoi-message').fill(uniqMsg);

  const postResp = page.waitForResponse(r => r.url().includes('/api/eoi')
                                          && r.request().method() === 'POST'
                                          && r.status() === 200);
  await page.getByTestId('eoi-submit-btn').click();
  const posted = await postResp;
  const eoi = await posted.json();

  // The EOI row should render in the "Your EOIs" list.
  await expect(page.getByTestId(`eoi-row-${eoi.id}`)).toBeVisible({ timeout: 5_000 });

  // -- Employer side (fresh context so cookies don't collide).
  const empCtx = await browser.newContext({ ignoreHTTPSErrors: true });
  const empPage = await empCtx.newPage();
  await loginViaApi(empPage, PERSONAS.EMPLOYER_CARD);
  const empListResp = empPage.waitForResponse(r =>
    r.url().includes('/api/eoi') && r.request().method() === 'GET',
    { timeout: 15_000 });
  await empPage.goto('/eoi');
  await empListResp;

  // The row must appear on the employer's Incoming EOIs list.
  const row = empPage.getByTestId(`eoi-row-${eoi.id}`);
  await expect(row).toBeVisible({ timeout: 5_000 });

  // Accept via the row's accept button.
  const acceptBtn = empPage.getByTestId(`eoi-accept-${eoi.id}`);
  await expect(acceptBtn).toBeVisible();
  await Promise.all([
    empPage.waitForResponse(r => r.url().match(/\/api\/eoi\/[^/]+\/accept/)
                                && r.status() === 200),
    acceptBtn.click(),
  ]);

  // On accept the SPA navs to /engagement/<id>.
  await expect(empPage).toHaveURL(/\/engagement\/[^/]+/, { timeout: 5_000 });

  // Verify the engagement exists in the backing store with from_eoi_id.
  const engs = await empPage.request.get(`${BACKEND_URL}/api/engagements`,
    { ignoreHTTPSErrors: true });
  const items = await engs.json();
  const created = items.find(e => e.talent_id === PERSONAS.TALENT_CLEAN.id
                              && e.from_eoi_id === eoi.id);
  expect(created, 'Accepting an EOI must create an engagement stamped from_eoi_id')
    .toBeTruthy();

  await empCtx.close();
});
