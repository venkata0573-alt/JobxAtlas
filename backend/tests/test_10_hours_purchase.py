"""Phase 1b tests — FEATURES.md §10 hours purchase (Stripe Checkout +
bank transfer path + webhook credit + status polling).

Every webhook interaction uses `tests/stripe_fixtures.py` — the wire-
format signer built for exactly this. stripe-mock cannot sign webhooks,
so any test that POSTs a raw event body without the fixture would 400.

Coverage:
- /api/payments/checkout (Stripe path)
- /api/payments/bank/initiate + /submit (bank path)
- /api/payments/mine (history)
- /api/payments/status/{session_id} (PaymentSuccess.jsx polling)
- Webhook checkout.session.completed with the default (hours) branch at
  server.py:590-595
- S-03(b) idempotency: replay same event.id twice — asserts credited-once
- F-05 dual-credit race: PaymentSuccess.jsx polling AND webhook both hit
  the same session_id, guarded by `payment_status: {"$ne": "paid"}`
- Forged / bad-signature webhook does not credit
- Unknown session_id webhook is a clean 200 no-op
- charge.refunded webhook — currently unhandled (no reversal); marked
  xfail(strict=True) so it self-clears when refund logic lands.
"""
from __future__ import annotations

import asyncio

import pytest

from tests import stripe_fixtures as sf
from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# ============================================================================
# 1. POST /api/payments/checkout — Stripe path (create the session)
# ============================================================================

class TestPaymentsCheckout:
    async def test_anon_401(self, anon_client):
        r = await anon_client.post(
            "/api/payments/checkout",
            json={"package_id": "starter_10",
                  "origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 401

    async def test_talent_role_403(self, talent_clean_client):
        r = await talent_clean_client.post(
            "/api/payments/checkout",
            json={"package_id": "starter_10",
                  "origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 403

    async def test_invalid_package_400(self, employer_card_client):
        r = await employer_card_client.post(
            "/api/payments/checkout",
            json={"package_id": "does-not-exist",
                  "origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 400

    async def test_employer_creates_session_and_persists_row(
        self, employer_card_client, db,
    ):
        r = await employer_card_client.post(
            "/api/payments/checkout",
            json={"package_id": "starter_10",
                  "origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("session_id"), (
            f"checkout response must carry a session_id; got: {body}"
        )
        # Row persisted with payment_status=pending.
        pt = await db.payment_transactions.find_one({"session_id": body["session_id"]})
        assert pt is not None
        assert pt["payment_status"] == "pending"
        assert pt["hours"] == 10
        assert pt["user_id"] == seed_mod.EMPLOYER_CARD_ID


# ============================================================================
# 2. POST /api/payments/bank/{initiate, submit} — bank path
# ============================================================================

class TestPaymentsBank:
    async def test_bank_initiate_talent_403(self, talent_clean_client):
        r = await talent_clean_client.post(
            "/api/payments/bank/initiate",
            json={"package_id": "starter_10"},
        )
        assert r.status_code == 403

    async def test_bank_initiate_bad_package_400(self, employer_card_client):
        r = await employer_card_client.post(
            "/api/payments/bank/initiate",
            json={"package_id": "does-not-exist"},
        )
        assert r.status_code == 400

    async def test_bank_end_to_end_leaves_awaiting_verification(
        self, employer_card_client, db,
    ):
        init = await employer_card_client.post(
            "/api/payments/bank/initiate",
            json={"package_id": "starter_10"},
        )
        assert init.status_code == 200
        pid = init.json()["payment_id"]
        sub = await employer_card_client.post(
            "/api/payments/bank/submit",
            json={"payment_id": pid, "utr": "UTR-TEST-12345", "payer_note": ""},
        )
        assert sub.status_code == 200
        assert sub.json()["status"] == "awaiting_verification"
        # payment_transactions row updated but NOT paid — admin approval flow.
        pt = await db.payment_transactions.find_one({"id": pid})
        assert pt["status"] == "awaiting_verification"
        assert pt["payment_status"] == "pending", (
            "Bank-transfer path must NOT auto-credit — admin still has to "
            "approve. Silent credit here would be a money-loss bug."
        )
        assert pt["utr"] == "UTR-TEST-12345"

    async def test_bank_submit_empty_utr_400(self, employer_card_client):
        init = await employer_card_client.post(
            "/api/payments/bank/initiate",
            json={"package_id": "starter_10"},
        )
        pid = init.json()["payment_id"]
        r = await employer_card_client.post(
            "/api/payments/bank/submit",
            json={"payment_id": pid, "utr": "   ", "payer_note": ""},
        )
        assert r.status_code == 400


# ============================================================================
# 3. GET /api/payments/mine — history is per-user
# ============================================================================

class TestPaymentsMine:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/payments/mine")
        assert r.status_code == 401

    async def test_history_scoped_to_caller(
        self, employer_card_client, employer_nocard_client, db,
    ):
        """Insert one payment row for each employer; each should only see
        their own. Cross-tenant leak here would expose invoicing data."""
        for uid, sid in (
            (seed_mod.EMPLOYER_CARD_ID, "pt-card-scope-1"),
            (seed_mod.EMPLOYER_NOCARD_ID, "pt-nocard-scope-1"),
        ):
            await db.payment_transactions.insert_one({
                "id": f"pt-{sid}", "session_id": sid, "user_id": uid,
                "package_id": "starter_10", "hours": 10,
                "amount": 30000, "currency": "usd",
                "status": "initiated", "payment_status": "pending",
                "created_at": "2026-09-06T00:00:00+00:00",
                "updated_at": "2026-09-06T00:00:00+00:00",
            })
        r_card = await employer_card_client.get("/api/payments/mine")
        r_nocard = await employer_nocard_client.get("/api/payments/mine")
        card_sids = {p["session_id"] for p in r_card.json()}
        nocard_sids = {p["session_id"] for p in r_nocard.json()}
        assert "pt-card-scope-1" in card_sids
        assert "pt-nocard-scope-1" not in card_sids
        assert "pt-nocard-scope-1" in nocard_sids
        assert "pt-card-scope-1" not in nocard_sids


# ============================================================================
# 4. Webhook happy path — checkout.session.completed → hours credited
# ============================================================================

class TestWebhookCreditsHours:
    async def _seed_pending(
        self, db, *, session_id: str, user_id: str, hours: int = 10,
    ) -> None:
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": user_id, "package_id": "starter_10",
            "hours": hours, "amount": 30000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })

    async def test_signed_webhook_credits_hours(self, anon_client, db):
        session_id = "cs_test_hours_happy"
        # employer_card seeded with hours_balance=1000
        await self._seed_pending(
            db, session_id=session_id, user_id=seed_mod.EMPLOYER_CARD_ID, hours=10,
        )
        payload, headers = sf.checkout_session_completed(
            session_id=session_id, kind=None,  # kind=None → default hours branch
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200, r.text
        pt = await db.payment_transactions.find_one({"session_id": session_id})
        assert pt["payment_status"] == "paid"
        u = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        assert u["hours_balance"] == 1000 + 10


# ============================================================================
# 5. S-03(b) — event.id idempotency (sequential + concurrent)
# ============================================================================

class TestS03bIdempotency:
    """SECURITY_BACKLOG.md S-03 says the fix scope includes a stripe_events
    collection keyed on event.id (unique index) so a re-delivered webhook
    processes at most once. That collection does not exist today; the
    only guard is the `payment_status: {"$ne": "paid"}` filter on the
    payment_transactions row.

    - Sequential replay: session_id guard makes this pass today (predicted).
    - Concurrent replay (asyncio.gather × N): race window between the
      find_one snapshot and the $inc-users update lets both handlers
      $inc the balance even though only one update to payment_transactions
      succeeds. Marked xfail(strict=False) — outcome depends on Mongo
      timing on tmpfs.
    """

    async def _seed(self, db, session_id: str) -> None:
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "package_id": "starter_10",
            "hours": 10, "amount": 30000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })

    async def test_sequential_replay_credits_once(self, anon_client, db):
        """Sequential replay of the same event.id + same session_id.
        Predicted: passes today because the second webhook sees
        payment_status='paid' and skips the credit branch."""
        session_id = "cs_test_replay_seq"
        await self._seed(db, session_id)
        payload, headers = sf.checkout_session_completed(session_id=session_id)

        r1 = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r1.status_code == 200
        r2 = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r2.status_code == 200

        u = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        assert u["hours_balance"] == 1000 + 10, (
            f"Sequential replay double-credited: got {u['hours_balance']}, "
            f"expected {1000 + 10}. Session_id guard at server.py:591 should "
            f"have caught this — investigate before writing the stripe_events "
            f"S-03(b) fix."
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "S-03(b) / F-05: concurrent webhooks for the same event.id "
            "have a find_one → $inc race window. The payment_transactions "
            "update uses `payment_status: {'$ne': 'paid'}` guard atomically, "
            "but the subsequent `db.users.update_one($inc)` at server.py:595 "
            "runs unconditionally once the enclosing `if` block was entered "
            "on the stale snapshot. Timing-dependent — may xpass on a slow "
            "test host. Definitive fix is a stripe_events collection with a "
            "unique event.id index so the second delivery is dropped before "
            "the find_one runs."
        ),
    )
    async def test_concurrent_replay_may_double_credit(self, anon_client, db):
        """Fire 5 identical webhook posts in parallel. If the race hits,
        the balance ends up > +10; if Mongo serialises them tightly it
        may stay at +10 (xpass — informational, strict=False)."""
        session_id = "cs_test_replay_concurrent"
        await self._seed(db, session_id)
        payload, headers = sf.checkout_session_completed(session_id=session_id)

        results = await asyncio.gather(*[
            anon_client.post("/api/stripe/webhook",
                             content=payload, headers=headers)
            for _ in range(5)
        ])
        for r in results:
            assert r.status_code == 200, r.text

        u = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        # Assertion the eventual fix must make true: credited exactly once.
        assert u["hours_balance"] == 1000 + 10, (
            f"F-05 race hit: balance {u['hours_balance']}, expected {1000 + 10} "
            f"after 5 concurrent replays. Fix = stripe_events dedup (S-03(b))."
        )


# ============================================================================
# 6. F-05 dual-credit — webhook AND /payments/status/{id} polling
# ============================================================================

class TestF05DualCredit:
    """FEATURES.md §10 + CLAUDE.md landmine list: PaymentSuccess.jsx
    polls `/api/payments/status/{session_id}` while Stripe fires the
    webhook. Both paths credit hours; both use the `payment_status:
    {'$ne': 'paid'}` guard. This test proves the guard holds when both
    fire on the same session."""

    async def test_webhook_then_poll_credits_once(self, anon_client, db):
        """Fire the webhook first, then the polling endpoint. The poll
        hits Stripe (stripe-mock returns a canned session), calls
        _credit_hours_if_paid which sees payment_status=paid → short-
        circuits. Balance stays at +10."""
        session_id = "cs_test_dual_credit_wp"
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "package_id": "starter_10",
            "hours": 10, "amount": 30000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })
        payload, headers = sf.checkout_session_completed(session_id=session_id)

        # Webhook first.
        r_wh = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r_wh.status_code == 200

        # Then the polling endpoint. stripe-mock returns a canned session
        # (payment_status varies by version); either way the local guard
        # must hold.
        r_poll = await anon_client.get(f"/api/payments/status/{session_id}")
        assert r_poll.status_code == 200

        u = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        assert u["hours_balance"] == 1000 + 10, (
            f"F-05 dual-credit: webhook + poll both incremented. Balance "
            f"{u['hours_balance']}, expected {1000 + 10}."
        )


# ============================================================================
# 7. Forged webhook does NOT credit
# ============================================================================

class TestForgedWebhookDoesNotCredit:
    async def test_bad_signature_does_not_credit_hours(self, anon_client, db):
        """A payload for a valid pending session, delivered with a wrong
        signature, must be 400 AND leave hours_balance untouched."""
        session_id = "cs_test_forged"
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "package_id": "starter_10",
            "hours": 10, "amount": 30000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })
        payload, _ = sf.checkout_session_completed(session_id=session_id)
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload,
            headers=sf.with_bad_signature(payload),
        )
        assert r.status_code == 400
        pt = await db.payment_transactions.find_one({"session_id": session_id})
        assert pt["payment_status"] == "pending", (
            f"Forged webhook was accepted — payment_status={pt['payment_status']}"
        )
        u = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        assert u["hours_balance"] == 1000, (
            f"Forged webhook credited hours despite 400. Balance: {u['hours_balance']}"
        )


# ============================================================================
# 8. Unknown session_id → clean 200 no-op
# ============================================================================

class TestUnknownSessionId:
    async def test_unknown_session_id_is_clean_200(self, anon_client, db):
        payload, headers = sf.checkout_session_completed(
            session_id="cs_test_completely_unknown_session_id",
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200
        # No row created; no hours credited.
        pt = await db.payment_transactions.find_one({
            "session_id": "cs_test_completely_unknown_session_id",
        })
        assert pt is None


# ============================================================================
# 9. charge.refunded — xfail(strict=True) canary for missing reversal logic
# ============================================================================

class TestChargeRefundedReversal:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "No handler branch for charge.refunded — server.py:563-596 "
            "only branches on checkout.session.completed. A refund "
            "webhook falls through to line 596 and returns 200 no-op. "
            "hours_balance stays credited even though Stripe reversed "
            "the charge — money-tracking desync. Fix: add a charge."
            "refunded branch that looks up the payment_transactions row "
            "by payment_intent_id + reverses the $inc. When landed, "
            "this test starts passing; strict=True fails the xfail → "
            "forces removal."
        ),
    )
    async def test_charge_refunded_reverses_hours_credit(
        self, anon_client, db,
    ):
        """Set up a paid hours purchase (via webhook), then fire
        charge.refunded → assert hours_balance decremented back."""
        session_id = "cs_test_refund_reversal"
        pi_id = "pi_test_refund_reversal"
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "package_id": "starter_10",
            "hours": 10, "amount": 30000, "currency": "usd",
            "payment_intent_id": pi_id,
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })
        # Prime with a successful webhook.
        pay_p, pay_h = sf.checkout_session_completed(
            session_id=session_id, payment_intent=pi_id,
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=pay_p, headers=pay_h,
        )
        assert r.status_code == 200
        u = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        assert u["hours_balance"] == 1000 + 10

        # Now the refund.
        ref_p, ref_h = sf.charge_refunded(
            charge_id="ch_test_refund_reversal",
            payment_intent=pi_id,
            refund_id="re_test_refund_reversal",
            amount_refunded=30000,
        )
        r_ref = await anon_client.post(
            "/api/stripe/webhook", content=ref_p, headers=ref_h,
        )
        assert r_ref.status_code == 200

        # Expected post-fix: balance back to 1000.
        u2 = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        assert u2["hours_balance"] == 1000, (
            f"charge.refunded did not reverse the credit. Balance is "
            f"{u2['hours_balance']}, expected 1000."
        )
