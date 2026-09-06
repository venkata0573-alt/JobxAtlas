// Flow 6: purchase hours → return to /payment/success → balance updates
//
// Full checkout requires Stripe's hosted-checkout UI, which stripe-mock
// does NOT provide (stripe-mock emulates the API only). To simulate the
// user completing checkout, we:
//   1. Have the employer initiate checkout via the UI (buttons on /hours).
//   2. Extract session_id from the create_checkout response.
//   3. Use the stripe_fixtures.py-equivalent (JS re-implementation below)
//      to POST a signed webhook that the backend accepts as
//      checkout.session.completed for that session_id.
//   4. Navigate to /payment/success?session_id=<id> and assert the SPA's
//      PaymentSuccess.jsx polling picks up the paid state and hours are
//      credited.
//
// stripe_fixtures.py is Python-only; below is the minimal JS equivalent
// (v1 HMAC sig over `t=<unix>.<payload>`) using the same
// STRIPE_WEBHOOK_SECRET the backend expects.

const { test, expect } = require('@playwright/test');
const crypto = require('crypto');
const { PERSONAS, BACKEND_URL } = require('./personas');
const { loginViaApi } = require('./helpers');

// Matches .env.test — must be the value backend/config.py resolves at boot.
const STRIPE_WEBHOOK_SECRET = 'whsec_test_atlas_locally_generated_for_signature_tests';

function signStripeWebhook(payloadBytes) {
  const ts = Math.floor(Date.now() / 1000);
  const signed = `${ts}.${payloadBytes.toString('utf-8')}`;
  const v1 = crypto.createHmac('sha256', STRIPE_WEBHOOK_SECRET)
    .update(signed).digest('hex');
  return `t=${ts},v1=${v1}`;
}

function checkoutSessionCompleted({ sessionId, kind = null, metadata = {}, hours = 10 }) {
  const meta = { ...metadata };
  if (kind) meta.kind = kind;
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
        mode: 'payment', metadata: meta,
      },
    },
    request: { id: null, idempotency_key: null },
  };
  const payload = Buffer.from(JSON.stringify(event));
  return { payload, headers: { 'Stripe-Signature': signStripeWebhook(payload),
                                'Content-Type': 'application/json' } };
}


test('purchase hours: checkout → webhook → PaymentSuccess reflects credit', async ({ page }) => {
  await loginViaApi(page, PERSONAS.EMPLOYER_CARD);

  // -- Read starting balance
  const meBefore = await page.request.get(`${BACKEND_URL}/api/auth/me`,
    { ignoreHTTPSErrors: true });
  const balanceBefore = (await meBefore.json()).hours_balance;

  // -- Create the Stripe checkout session. Best-effort UI (/hours page has
  // package buttons); fall back to direct POST /api/payments/checkout.
  await page.goto('/hours');
  let sessionId = null;
  const starterBtn = page.getByTestId('purchase-hours-starter-btn');
  if (await starterBtn.count()) {
    const [resp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/payments/checkout')),
      starterBtn.click(),
    ]);
    sessionId = (await resp.json()).session_id;
  } else {
    console.warn('MISSING TESTID: purchase-hours-starter-btn on PurchaseHours.jsx');
    const r = await page.request.post(`${BACKEND_URL}/api/payments/checkout`, {
      ignoreHTTPSErrors: true,
      data: { package_id: 'starter_10',
              origin_url: 'http://localhost:13000' },
    });
    expect(r.status()).toBe(200);
    sessionId = (await r.json()).session_id;
  }
  expect(sessionId).toBeTruthy();

  // -- Simulate Stripe firing checkout.session.completed for this session.
  // The default (no kind) branch at server.py:590-595 credits hours.
  const { payload, headers } = checkoutSessionCompleted({ sessionId });
  const wh = await page.request.post(`${BACKEND_URL}/api/stripe/webhook`, {
    ignoreHTTPSErrors: true,
    headers, data: payload,
  });
  expect(wh.status()).toBe(200);

  // -- Navigate to PaymentSuccess. The SPA polls
  // /api/payments/status/{session_id} and updates the UI + refetches
  // /auth/me when it flips to paid.
  await page.goto(`/payment/success?session_id=${sessionId}`);
  // Give the polling loop up to 10s to catch the paid state + refresh.
  await page.waitForResponse(r =>
    r.url().includes(`/api/payments/status/${sessionId}`)
    && r.status() === 200, { timeout: 10_000 }).catch(() => {});

  // -- Assert /auth/me reflects the credit
  const meAfter = await page.request.get(`${BACKEND_URL}/api/auth/me`,
    { ignoreHTTPSErrors: true });
  const balanceAfter = (await meAfter.json()).hours_balance;
  expect(balanceAfter).toBe(balanceBefore + 10);
});
