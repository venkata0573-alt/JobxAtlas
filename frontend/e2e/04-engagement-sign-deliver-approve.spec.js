// Flow 4: engagement lifecycle — sign contract → submit deliverable → approve
//
// v2 posture: no API fallbacks. Setup uses API to CREATE a fresh
// engagement in `pending_signatures` (creating one via UI would need
// the /assemble mix-and-match page which is out of scope), but every
// action after that — signing, submitting a deliverable, approving —
// is driven through EngagementDetail.jsx real form fields + buttons.
//
// Testids (constants/testIds.js):
//   TID.contractSignature = "contract-signature-input"
//   TID.contractAgree     = "contract-agree-checkbox"
//   TID.contractSubmit    = "contract-submit-btn"
//   TID.deliverableTitle  = "deliverable-title"
//   TID.deliverableLink   = "deliverable-link"
//   TID.deliverableDesc   = "deliverable-desc"
//   TID.deliverableHours  = "deliverable-hours"
//   TID.deliverableSubmit = "deliverable-submit-btn"
//   TID.deliverableApprove(id) = "deliverable-approve-<id>"

const { test, expect } = require('@playwright/test');
const { PERSONAS, BACKEND_URL } = require('./personas');
const { loginViaApi } = require('./helpers');


test('engagement: sign → submit deliverable → approve', async ({ page, browser }) => {
  // -- Setup: create a fresh engagement so we control the sign state.
  await loginViaApi(page, PERSONAS.EMPLOYER_CARD);
  const create = await page.request.post(`${BACKEND_URL}/api/engagements`, {
    ignoreHTTPSErrors: true,
    data: {
      talent_id: PERSONAS.TALENT_CLEAN.id,
      hours: 10,
      scope: 'E2E — sign then approve loop',
      mode: 'remote',
    },
  });
  expect(create.status()).toBe(200);
  const eng = await create.json();
  const engId = eng.id;
  expect(eng.status).toBe('pending_signatures');

  // -- Employer signs via UI. Contract form has signature input, agree
  //    checkbox, and submit button.
  await page.goto(`/engagement/${engId}`);
  const empSigInput = page.getByTestId('contract-signature-input');
  await expect(empSigInput).toBeVisible({ timeout: 10_000 });
  await empSigInput.fill(PERSONAS.EMPLOYER_CARD.name);
  await page.getByTestId('contract-agree-checkbox').check();

  await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/engagements/sign')
                            && r.status() === 200),
    page.getByTestId('contract-submit-btn').click(),
  ]);

  // -- Talent signs in a fresh context.
  const talentCtx = await browser.newContext({ ignoreHTTPSErrors: true });
  const talentPage = await talentCtx.newPage();
  await loginViaApi(talentPage, PERSONAS.TALENT_CLEAN);
  await talentPage.goto(`/engagement/${engId}`);

  const talentSigInput = talentPage.getByTestId('contract-signature-input');
  await expect(talentSigInput).toBeVisible({ timeout: 10_000 });
  await talentSigInput.fill(PERSONAS.TALENT_CLEAN.name);
  await talentPage.getByTestId('contract-agree-checkbox').check();

  await Promise.all([
    talentPage.waitForResponse(r => r.url().includes('/api/engagements/sign')
                                    && r.status() === 200),
    talentPage.getByTestId('contract-submit-btn').click(),
  ]);

  // -- Talent submits a deliverable via the UI form.
  // The submit form is only rendered when status === "contract_signed" —
  // wait for the page to reflect the new state (a fresh render happens
  // after the sign call resolves).
  await talentPage.waitForTimeout(500); // give React a tick to re-render
  const delivTitle = talentPage.getByTestId('deliverable-title');
  await expect(delivTitle).toBeVisible({ timeout: 10_000 });
  await delivTitle.fill('E2E deliverable v1');
  await talentPage.getByTestId('deliverable-link').fill('https://example.test/e2e-v1');
  await talentPage.getByTestId('deliverable-desc').fill('End-to-end test deliverable');
  await talentPage.getByTestId('deliverable-hours').fill('3');

  const submitResp = talentPage.waitForResponse(r =>
    r.url().includes('/api/deliverables') && r.request().method() === 'POST'
    && r.status() === 200);
  await talentPage.getByTestId('deliverable-submit-btn').click();
  const submitted = await submitResp;
  const deliv = await submitted.json();

  // -- Employer approves via UI (per-deliverable approve button).
  await page.goto(`/engagement/${engId}`);
  const approveBtn = page.getByTestId(`deliverable-approve-${deliv.id}`);
  await expect(approveBtn).toBeVisible({ timeout: 10_000 });
  await Promise.all([
    page.waitForResponse(r => r.url().includes(`/deliverables/${deliv.id}/approve`)
                            && r.status() === 200),
    approveBtn.click(),
  ]);

  await talentCtx.close();
});
