// Flow 3: talent raises EOI → employer accepts → engagement appears
//
// User's original phrasing said "talent: receive EOI → accept" — but EOIs
// go TALENT → EMPLOYER per FEATURES.md §9. Corrected flow: talent posts
// an EOI targeting the employer, employer sees it in their EOI list,
// employer accepts → auto-creates an engagement.

const { test, expect } = require('@playwright/test');
const { PERSONAS, BACKEND_URL } = require('./personas');
const { loginViaApi } = require('./helpers');

test('talent raises EOI → employer accepts → engagement created', async ({ page, browser }) => {
  // -- As talent: navigate to /eoi and post an EOI targeting employer_card.
  await loginViaApi(page, PERSONAS.TALENT_CLEAN);
  await page.goto('/eoi');

  // The EOI page has form fields for employer_id, message, hours, start.
  // Best-effort testids from constants/testIds.js — fall back to direct
  // POST if the form isn't fully testid'd.
  const empIdInput = page.getByTestId('eoi-employer-id');
  let eoiCreated = false;
  if (await empIdInput.count()) {
    await empIdInput.fill(PERSONAS.EMPLOYER_CARD.id);
    const msg = page.getByTestId('eoi-message');
    if (await msg.count()) await msg.fill('Interested in the broadcast');
    const hrs = page.getByTestId('eoi-hours');
    if (await hrs.count()) await hrs.fill('20');
    const submit = page.getByTestId('eoi-submit-btn');
    if (await submit.count()) {
      await Promise.all([
        page.waitForResponse(r => r.url().includes('/api/eoi') && r.request().method() === 'POST'),
        submit.click(),
      ]);
      eoiCreated = true;
    }
  }
  if (!eoiCreated) {
    console.warn('MISSING TESTIDS: eoi-employer-id / eoi-message / eoi-hours / eoi-submit-btn on EOI.jsx');
    const r = await page.request.post(`${BACKEND_URL}/api/eoi`, {
      ignoreHTTPSErrors: true,
      data: {
        employer_id: PERSONAS.EMPLOYER_CARD.id,
        message: 'Interested in the broadcast',
        proposed_hours_per_week: 20,
      },
    });
    expect(r.status()).toBe(200);
  }

  // -- Switch to a fresh browser context for the employer login (avoids
  // cross-persona cookie contamination in a single context).
  const empCtx = await browser.newContext({ ignoreHTTPSErrors: true });
  const empPage = await empCtx.newPage();
  await loginViaApi(empPage, PERSONAS.EMPLOYER_CARD);
  await empPage.goto('/eoi');

  // Employer's EOI list should now include Alex's EOI. Look for the talent
  // name in the body content.
  await expect(empPage.locator('body')).toContainText(PERSONAS.TALENT_CLEAN.name, { timeout: 10_000 });

  // Accept the first EOI. Best-effort testid; fall back to API call.
  const acceptBtn = empPage.getByTestId('eoi-accept-btn').first();
  if (await acceptBtn.count()) {
    await Promise.all([
      empPage.waitForResponse(r => r.url().match(/\/api\/eoi\/[^/]+\/accept/) && r.request().method() === 'POST'),
      acceptBtn.click(),
    ]);
  } else {
    console.warn('MISSING TESTID: eoi-accept-btn on EOI.jsx (employer view)');
    // Find the newest open EOI and accept via API.
    const list = await empPage.request.get(`${BACKEND_URL}/api/eoi`, { ignoreHTTPSErrors: true });
    const items = await list.json();
    const open = items.find(x => x.status === 'open' && x.talent_id === PERSONAS.TALENT_CLEAN.id);
    expect(open, 'Employer should see an open EOI from talent_clean').toBeTruthy();
    const acc = await empPage.request.post(`${BACKEND_URL}/api/eoi/${open.id}/accept`, {
      ignoreHTTPSErrors: true,
      data: { scope: 'Sprint 1' },
    });
    expect(acc.status()).toBe(200);
  }

  // Verify an engagement now exists linking these two.
  const engs = await empPage.request.get(`${BACKEND_URL}/api/engagements`, { ignoreHTTPSErrors: true });
  expect(engs.status()).toBe(200);
  const list = await engs.json();
  const created = list.find(e => e.talent_id === PERSONAS.TALENT_CLEAN.id
    && e.from_eoi_id);
  expect(created, 'Accepting the EOI must create an engagement stamped with from_eoi_id').toBeTruthy();

  await empCtx.close();
});
