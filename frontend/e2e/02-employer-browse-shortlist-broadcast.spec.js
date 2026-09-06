// Flow 2: employer discovers talent → shortlists → sends broadcast
//
// v2 posture: no API fallbacks. Rerouted through the ONLY UI path that
// can shortlist a talent — SkillLanding (/hire/react-developers) modal.
// BrowseTalent (/browse) has no shortlist button; its cards only carry
// a "View →" link to /employer. This is a real product gap (recorded
// in the report — the user's original "browse marketplace → shortlist"
// wording implies /browse should support it, but only SkillLanding
// does today).

const { test, expect } = require('@playwright/test');
const { PERSONAS } = require('./personas');
const { loginViaApi } = require('./helpers');


test('employer: SkillLanding → shortlist talent (via modal) → send broadcast', async ({ page }) => {
  await loginViaApi(page, PERSONAS.EMPLOYER_CARD);

  // -- Discovery: hit the SEO landing page. Set up the waitForResponse
  //    listener BEFORE goto — otherwise the mount-time fetch may
  //    complete before the listener attaches, giving a bogus timeout.
  const landingResp = page.waitForResponse(r =>
    r.url().includes('/api/seo/hire/react-developers') && r.status() === 200,
    { timeout: 15_000 });
  await page.goto('/hire/react-developers');
  await landingResp;
  // Click Alex's card by testid to open the modal (curated-talent-card-<id>).
  await page.getByTestId(`curated-talent-card-${PERSONAS.TALENT_CLEAN.id}`)
    .click({ timeout: 10_000 });

  // -- Shortlist via the modal's "Shortlist for future hire" button.
  const shortlistBtn = page.getByTestId('shortlist-btn');
  await expect(shortlistBtn).toBeVisible({ timeout: 5_000 });
  await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/shortlist')
                            && r.request().method() === 'POST'
                            && r.status() === 200),
    shortlistBtn.click(),
  ]);

  // -- Broadcast from /employer/shortlist. The page's broadcast-btn
  //    opens the modal; broadcast-message is the textarea;
  //    send-broadcast-btn fires the POST.
  await page.goto('/employer/shortlist');
  await expect(page.getByTestId(`shortlist-item-${PERSONAS.TALENT_CLEAN.id}`))
    .toBeVisible({ timeout: 5_000 });

  await page.getByTestId('broadcast-btn').click();
  await expect(page.getByTestId('broadcast-modal')).toBeVisible();
  await page.getByTestId('broadcast-message').fill(
    'Ready to hire — 20h/wk starting Monday.'
  );
  await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/shortlist/broadcast')
                            && r.request().method() === 'POST'
                            && r.status() === 200),
    page.getByTestId('send-broadcast-btn').click(),
  ]);
  // Modal closes on success (sendBroadcast sets broadcastOpen=false).
  await expect(page.getByTestId('broadcast-modal')).not.toBeVisible({ timeout: 5_000 });
});
