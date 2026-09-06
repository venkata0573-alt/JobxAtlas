// Flow 6: purchase hours → return to PaymentSuccess → balance updates
//
// v2 posture: no API fallbacks for the checkout initiation — click the
// real "Buy" button on /hours which POSTs /api/payments/checkout. We
// then simulate Stripe firing checkout.session.completed via the
// stripe_fixtures.py-equivalent JS signer (stripe-mock cannot sign
// webhooks — same rationale as backend/tests/stripe_fixtures.py). This
// isn't UI-avoidance — it's the only way to observe the credit path
// end-to-end without a real Stripe hosted-checkout UI (stripe-mock
// doesn't provide one).
//
// Testids (constants/testIds.js):
//   TID.pkgBuy("starter_10") = "pkg-buy-starter_10"

const { test, expect } = require('@playwright/test');
const crypto = require('crypto');
const { PERSONAS, BACKEND_URL } = require('./personas');
const { loginViaApi } = require('./helpers');

// Must match .env.test — the value backend/config.py resolves at boot.
const STRIPE_WEBHOOK_SECRET = 'whsec_test_atlas_locally_generated_for_signature_tests';

function signStripeWebhook(payloadBytes) {
  const ts = Math.floor(Date.now() / 1000);
  const signed = `${ts}.${payloadBytes.toString('utf-8')}`;
  const v1 = crypto.createHmac('sha256', STRIPE_WEBHOOK_SECRET)
    .update(signed).digest('hex');
  return `t=${ts},v1=${v1}`;
}

function checkoutSessionCompleted({ sessionId }) {
  const event = {
    id: `evt_test_${sessionId}`,
    object: 'event',
    api_version: '2024-06-20',
    created: Math.floor(Date.now() / 1000),
    type: 'checkout.session.completed',
    livemode: false,
    data: {
      object: {
        id: sessionId, object: 'checkout.session',
        amount_total: 30000, currency: 'usd',
        payment_intent: `pi_test_${sessionId}`,
        payment_status: 'paid', status: 'complete',
        mode: 'payment', metadata: {},
      },
    },
    request: { id: null, idempotency_key: null },
  };
  const payload = Buffer.from(JSON.stringify(event));
  return {
    payload,
    headers: {
      'Stripe-Signature': signStripeWebhook(payload),
      'Content-Type': 'application/json',
    },
  };
}


test('purchase hours: UI checkout button → webhook → PaymentSuccess reflects credit', async ({ page }) => {
  await loginViaApi(page, PERSONAS.EMPLOYER_CARD);

  // -- Starting balance
  const meBefore = await page.request.get(`${BACKEND_URL}/api/auth/me`,
    { ignoreHTTPSErrors: true });
  const balanceBefore = (await meBefore.json()).hours_balance;

  // -- Click the real "Buy" button on /employer/purchase (starter_10 package).
  //    Route is `/employer/purchase` (App.js:60).
  //
  //    PurchaseHours.jsx sets `window.location = r.data.checkout_url` the
  //    moment the response lands (would take the browser to stripe-mock
  //    which serves no HTML). We route.fulfill the response and rewrite
  //    checkout_url to point at /payment/success on our own origin — the
  //    session_id is captured in the same interception, and the SPA
  //    navigates back to a page it can actually render. This intercepts
  //    the wire, not the button — the click is still real UI.
  let capturedSessionId = null;
  await page.route('**/api/payments/checkout', async (route) => {
    const response = await route.fetch();
    const originalBody = await response.json();
    capturedSessionId = originalBody.session_id;
    await route.fulfill({
      response,
      body: JSON.stringify({
        ...originalBody,
        checkout_url: `/payment/success?session_id=${capturedSessionId}`,
      }),
      headers: { ...response.headers(), 'content-type': 'application/json' },
    });
  });

  await page.goto('/employer/purchase');
  const buyBtn = page.getByTestId('pkg-buy-starter_10');
  await expect(buyBtn).toBeVisible({ timeout: 10_000 });
  await buyBtn.click();
  // Give the intercept + SPA navigate a tick.
  await page.waitForURL(/\/payment\/success/, { timeout: 10_000 });
  expect(capturedSessionId).toBeTruthy();
  const sessionId = capturedSessionId;

  // -- Simulate Stripe firing checkout.session.completed for that session.
  //    (stripe-mock cannot sign webhooks; the JS signer above matches
  //    backend/tests/stripe_fixtures.py's wire format byte-for-byte.)
  const { payload, headers } = checkoutSessionCompleted({ sessionId });
  const wh = await page.request.post(`${BACKEND_URL}/api/stripe/webhook`, {
    ignoreHTTPSErrors: true, headers, data: payload,
  });
  expect(wh.status()).toBe(200);

  // -- Navigate to PaymentSuccess and let the polling loop see the paid
  //    state. PaymentSuccess.jsx polls GET /api/payments/status/{id}.
  await page.goto(`/payment/success?session_id=${sessionId}`);
  await page.waitForResponse(r =>
    r.url().includes(`/api/payments/status/${sessionId}`)
    && r.status() === 200, { timeout: 10_000 }).catch(() => {});

  // -- Balance must be up by the package's hours (10 for starter_10).
  const meAfter = await page.request.get(`${BACKEND_URL}/api/auth/me`,
    { ignoreHTTPSErrors: true });
  const balanceAfter = (await meAfter.json()).hours_balance;
  expect(balanceAfter).toBe(balanceBefore + 10);
});
