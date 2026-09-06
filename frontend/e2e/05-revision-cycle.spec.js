// Flow 5: revision cycle — employer requests revision → talent resubmits
//
// v2 posture: no API fallbacks. Every click is real UI. Testids from
// EngagementDetail.jsx (direct string values, no TID.* wrapper):
//   `request-revision-<deliverableId>` (button that opens modal)
//   `revision-modal`
//   `revision-justification` (textarea, min 20 chars)
//   `revision-priority-<name>` (per-priority button: minor|major|blocking)
//   `revision-submit` (submit button in modal)
//   `resubmit-<deliverableId>` (button on talent side)
//   `resubmit-modal`, `resubmit-link`, `resubmit-hours`, `resubmit-submit`

const { test, expect } = require('@playwright/test');
const { PERSONAS, SEEDED_IDS } = require('./personas');
const { loginViaApi } = require('./helpers');


test('revision cycle: employer requests revision → talent resubmits', async ({ page, browser }) => {
  const engId = SEEDED_IDS.ENGAGEMENT_SIGNED;
  const delivId = SEEDED_IDS.DELIVERABLE_SUBMITTED;

  // -- Employer opens the revision modal + fills it + submits.
  await loginViaApi(page, PERSONAS.EMPLOYER_CARD);
  await page.goto(`/engagement/${engId}`);

  const reqBtn = page.getByTestId(`request-revision-${delivId}`);
  await expect(reqBtn).toBeVisible({ timeout: 10_000 });
  await reqBtn.click();

  await expect(page.getByTestId('revision-modal')).toBeVisible();
  // min_length=20 enforced by RequestRevisionIn (routes/revisions.py:47).
  await page.getByTestId('revision-justification').fill(
    'Please tighten the header copy and add a totals row at the bottom.'
  );
  await page.getByTestId('revision-priority-minor').click();
  await Promise.all([
    page.waitForResponse(r => r.url().includes('/request-revision')
                            && r.status() === 200),
    page.getByTestId('revision-submit').click(),
  ]);

  // -- Talent resubmits via UI (fresh context to avoid cookie collision).
  const talentCtx = await browser.newContext({ ignoreHTTPSErrors: true });
  const talentPage = await talentCtx.newPage();
  await loginViaApi(talentPage, PERSONAS.TALENT_CLEAN);
  await talentPage.goto(`/engagement/${engId}`);

  const resubmitBtn = talentPage.getByTestId(`resubmit-${delivId}`);
  await expect(resubmitBtn).toBeVisible({ timeout: 10_000 });
  await resubmitBtn.click();

  await expect(talentPage.getByTestId('resubmit-modal')).toBeVisible();
  await talentPage.getByTestId('resubmit-link').fill('https://example.test/revised-v1');
  await talentPage.getByTestId('resubmit-hours').fill('1');
  await Promise.all([
    talentPage.waitForResponse(r => r.url().includes('/resubmit')
                                  && r.status() === 200),
    talentPage.getByTestId('resubmit-submit').click(),
  ]);

  await talentCtx.close();
});
