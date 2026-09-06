"""Tests proving stripe_fixtures.py produces signatures that
stripe.Webhook.construct_event actually accepts (and correctly rejects
when they should be rejected).

Bounded scope. This file exercises the SIGNING wire format only —
whether a POST reaches the handler body at all. It does NOT test
downstream business logic (§10 hours purchase, §14 dispute-fee refund,
§17 milestone auto-collect). Those tests get their own sessions once
this fixture is trusted.

S-03 evidence — see the module docstring at the tail plus
test_S03_dispute_fee_branch_swallows_and_returns_200.
"""
from __future__ import annotations

import pytest

from tests import stripe_fixtures as sf
from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# ============================================================================
# 1. Happy path — a correctly signed payload REACHES the handler
# ============================================================================

class TestSignedPayloadReachesHandler:
    """These prove `stripe.Webhook.construct_event(payload, sig, SECRET)`
    at server.py:560 accepts what stripe_fixtures.sign_payload produces.
    A pass here is the load-bearing invariant every money-path test rests
    on."""

    async def test_checkout_session_completed_hours_purchase_returns_200(
        self, anon_client, db,
    ):
        """Fires the default 'hours_purchase' branch (server.py:590-595).
        The seed doesn't include a payment_transactions row for this
        session id, so the handler no-ops on the DB update — but it must
        still return 200, proving the signature verified and the branch
        was reached."""
        payload, headers = sf.checkout_session_completed(
            session_id="cs_test_hours_smoke",
            kind="hours_purchase",
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200, (
            f"Signed payload should verify + reach the handler; "
            f"got {r.status_code}: {r.text}"
        )

    async def test_checkout_session_completed_milestone_updates_db(
        self, anon_client, db,
    ):
        """End-to-end proof: signed payload → construct_event → milestone
        branch (server.py:575-588) → project_milestones + project_invoices
        marked paid. Uses the seeded MILESTONE_1_ID + INVOICE_OPEN_ID.
        Requires a payment_transactions row keyed on session_id — seed
        one directly since §17 checkout-to-webhook isn't covered here."""
        session_id = "cs_test_milestone_e2e"
        await db.payment_transactions.insert_one({
            "id": "pt-test-milestone-e2e",
            "session_id": session_id,
            "kind": "milestone",
            "milestone_id": seed_mod.MILESTONE_1_ID,
            "invoice_id": seed_mod.INVOICE_OPEN_ID,
            "employer_id": seed_mod.EMPLOYER_CARD_ID,
            "amount_cents": 100000,
            "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
        })
        payload, headers = sf.checkout_session_completed(
            session_id=session_id,
            kind="milestone",
            metadata={"milestone_id": seed_mod.MILESTONE_1_ID,
                      "invoice_id": seed_mod.INVOICE_OPEN_ID},
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200, r.text

        # Business logic actually ran:
        pt = await db.payment_transactions.find_one({"session_id": session_id})
        assert pt["payment_status"] == "paid"
        mi = await db.project_milestones.find_one({"id": seed_mod.MILESTONE_1_ID})
        assert mi["status"] == "paid"
        inv = await db.project_invoices.find_one({"id": seed_mod.INVOICE_OPEN_ID})
        assert inv["status"] == "paid"

    async def test_payment_intent_succeeded_reaches_handler(
        self, anon_client,
    ):
        """The handler doesn't branch on payment_intent.succeeded today
        (falls through to line 596 → 200). This test proves the signing
        wire format works for this event type too, so any future PI-level
        handler can reuse the fixture."""
        payload, headers = sf.payment_intent_succeeded(
            pi_id="pi_test_fixture_smoke",
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200

    async def test_charge_refunded_reaches_handler(self, anon_client):
        payload, headers = sf.charge_refunded(
            charge_id="ch_test_fixture_smoke",
            refund_id="re_test_fixture_smoke",
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200


# ============================================================================
# 2. Adversarial paths — construct_event MUST reject
# ============================================================================

class TestBadSignatureRejected:
    """The handler at server.py:559-562 catches every Exception from
    construct_event and raises HTTPException(400, "Invalid signature").
    Any bad-signature test that returns 200 means either (a) the SDK
    silently accepted a bad sig, or (b) the handler swallowed the
    verification error — both would be P0 findings, not test bugs."""

    async def test_bad_v1_signature_returns_400(self, anon_client):
        payload, _ = sf.checkout_session_completed(
            session_id="cs_test_bad_sig",
        )
        r = await anon_client.post(
            "/api/stripe/webhook",
            content=payload,
            headers=sf.with_bad_signature(payload),
        )
        assert r.status_code == 400, (
            f"BAD SIG WAS ACCEPTED — HTTP {r.status_code}. Either the "
            f"handler swallowed the verification error or the Stripe SDK "
            f"changed behaviour. Body: {r.text}"
        )
        assert "invalid signature" in r.text.lower()


class TestStaleTimestampRejected:
    """construct_event's tolerance is 300s by default. A payload signed
    with the right secret but timestamped >5min in the past must fail
    the timestamp check even though the HMAC itself is valid."""

    async def test_stale_timestamp_returns_400(self, anon_client):
        payload, _ = sf.checkout_session_completed(
            session_id="cs_test_stale_ts",
        )
        r = await anon_client.post(
            "/api/stripe/webhook",
            content=payload,
            headers=sf.with_stale_timestamp(payload, age_seconds=400),
        )
        assert r.status_code == 400, (
            f"STALE TIMESTAMP WAS ACCEPTED — replay window is wider than "
            f"expected. Got {r.status_code}: {r.text}"
        )


class TestMalformedHeaderRejected:
    async def test_missing_header_returns_400(self, anon_client):
        payload, _ = sf.checkout_session_completed(session_id="cs_test_no_header")
        r = await anon_client.post(
            "/api/stripe/webhook",
            content=payload,
            headers={"Content-Type": "application/json"},  # no Stripe-Signature
        )
        assert r.status_code == 400

    async def test_garbage_header_returns_400(self, anon_client):
        payload, _ = sf.checkout_session_completed(session_id="cs_test_garbage")
        r = await anon_client.post(
            "/api/stripe/webhook",
            content=payload,
            headers=sf.with_malformed_header(payload),
        )
        assert r.status_code == 400


# ============================================================================
# 3. S-03 evidence — dispute-fee branch swallows business-logic errors
# ============================================================================

class TestS03DisputeFeeBranchSwallowsErrors:
    """SECURITY_BACKLOG.md S-03 says the webhook handler swallows
    exceptions and returns 200, leaving the DB out of sync with Stripe.
    Verifying the shape here — code reading at server.py:568-573 shows
    the dispute-fee branch does:

        try:
            await mark_dispute_fee_paid(obj["id"])
        except Exception as _e:
            logger.exception(f"[webhook] dispute_fee mark failed: {_e}")
        return {"ok": True}

    The unconditional `return {"ok": True}` after `except` means ANY
    exception in mark_dispute_fee_paid results in a 200 — Stripe never
    retries — the fee stays 'unpaid' in ATLAS while Stripe considers
    the payment successful.

    This test cannot force mark_dispute_fee_paid to throw at the
    integration level (its own code short-circuits harmlessly on
    unknown session_id), so the assertion here is: a signed dispute_fee
    webhook for an unknown grievance session STILL returns 200 (proving
    the branch runs to completion) — combined with the code-reading
    evidence above, S-03 stands as filed.
    """

    async def test_dispute_fee_webhook_returns_200_even_for_unknown_session(
        self, anon_client, db,
    ):
        """Unknown session id → mark_dispute_fee_paid finds no tx →
        early-returns None. Not the swallow path but proves the branch
        runs. See docstring for the full S-03 evidence."""
        # Deliberately do NOT insert a dispute_fee_transactions row.
        payload, headers = sf.checkout_session_completed(
            session_id="cs_test_dispute_fee_unknown_session",
            kind="dispute_fee",
            metadata={"grievance_id": "does-not-exist"},
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200
        # No DB row was created — proving the handler no-op'd cleanly:
        tx = await db.dispute_fee_transactions.find_one({
            "session_id": "cs_test_dispute_fee_unknown_session",
        })
        assert tx is None

    async def test_S03_shape_documented_dispute_branch_swallows(self):
        """Meta-assertion: read server.py:568-573 verbatim and confirm the
        `try/except → return {"ok": True}` shape. If someone refactors
        this to `raise` (i.e. fixes S-03), this test's grep will miss the
        pattern and fail — that's the signal to close S-03.
        """
        from pathlib import Path
        src = Path("/app/backend/server.py").read_text()
        # Find the dispute_fee branch and assert on its shape.
        assert 'if meta.get("kind") == "dispute_fee":' in src
        # The swallow pattern: try/except that logs then returns 200
        # unconditionally. Match by proximity (nearby lines) rather than
        # exact-string so trivial reformatting doesn't break the test.
        dispute_idx = src.index('if meta.get("kind") == "dispute_fee":')
        # Look at the ~15 lines that follow.
        snippet = src[dispute_idx:dispute_idx + 800]
        assert "try:" in snippet, (
            "S-03 shape changed — dispute_fee branch no longer wraps the "
            "mark call in try/except. If this was intentional, S-03 may "
            "be ready to close; verify and remove this test."
        )
        assert "except Exception" in snippet
        assert "logger.exception" in snippet
        assert 'return {"ok": True}' in snippet, (
            "S-03 canary: after the try/except, the dispute_fee branch "
            "still returns 200 unconditionally. If this line moved to a "
            "raise, S-03 is fixed and this test should be updated."
        )
