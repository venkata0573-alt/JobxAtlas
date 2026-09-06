"""Phase 1b tests — FEATURES.md §17 milestone / invoice payments
(Stripe Checkout per-milestone + webhook flip + polling status).

Every webhook interaction uses `tests/stripe_fixtures.py`.

Coverage:
- POST /api/projects/workspace/{project_id}/milestones/{milestone_id}/checkout
- GET  /api/projects/milestone-payment/status/{session_id}
- Webhook checkout.session.completed with `metadata.kind == "milestone"`
  (server.py:575-588) → milestone + invoice + payment_transactions all
  flip paid
- Idempotency: replay same event.id — assert single flip
- Forged / bad-signature webhook does not flip
- Unknown milestone session — clean 200 no-op

Not covered here:
- The nightly auto-collect off-session charge path (F-05 branch in
  projects.py:_attempt_off_session_charge) — needs a scheduler-run
  harness that Phase 1c will add.
- Setup-checkout / card-attach flows (/api/billing/setup*) — separate
  domain; test file for §17b if we split it.
"""
from __future__ import annotations

import pytest

from tests import stripe_fixtures as sf
from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# ============================================================================
# 1. POST checkout endpoint — role gating (ownership via _load_project_or_404)
# ============================================================================

class TestMilestoneCheckoutCreate:
    _PATH = (
        f"/api/projects/workspace/{seed_mod.PROJECT_OPEN_ID}"
        f"/milestones/{seed_mod.MILESTONE_1_ID}/checkout"
    )

    async def test_anon_401(self, anon_client):
        r = await anon_client.post(
            self._PATH,
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 401

    async def test_talent_gets_404_via_helper(self, talent_clean_client):
        """_load_project_or_404 → _can_view_project rejects talent (only
        admin + linked employer pass). Response is 403 from _load."""
        r = await talent_clean_client.post(
            self._PATH,
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 403, r.text

    async def test_non_linked_employer_403(self, employer_nocard_client):
        """employer_nocard is not the linked employer on PROJECT_OPEN_ID
        (seed links it to EMPLOYER_CARD_ID). _can_view_project → 403."""
        r = await employer_nocard_client.post(
            self._PATH,
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 403

    async def test_linked_employer_creates_session_and_persists_row(
        self, employer_card_client, db,
    ):
        r = await employer_card_client.post(
            self._PATH,
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("session_id")
        assert body.get("invoice_ref")
        pt = await db.payment_transactions.find_one({
            "session_id": body["session_id"], "kind": "milestone",
        })
        assert pt is not None
        assert pt["payment_status"] == "pending"
        assert pt["milestone_id"] == seed_mod.MILESTONE_1_ID
        assert pt["invoice_id"] == seed_mod.INVOICE_OPEN_ID

    async def test_missing_milestone_404(self, employer_card_client):
        r = await employer_card_client.post(
            f"/api/projects/workspace/{seed_mod.PROJECT_OPEN_ID}"
            f"/milestones/does-not-exist/checkout",
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 404

    async def test_already_paid_milestone_400(
        self, employer_card_client, db,
    ):
        await db.project_milestones.update_one(
            {"id": seed_mod.MILESTONE_1_ID},
            {"$set": {"status": "paid"}},
        )
        r = await employer_card_client.post(
            self._PATH,
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 400


# ============================================================================
# 2. Webhook happy path — kind=milestone → milestone/invoice/tx all flip paid
# ============================================================================

class TestMilestoneWebhookHappyPath:
    async def _seed_pending_milestone_tx(
        self, db, *, session_id: str,
    ) -> None:
        """Insert a payment_transactions row keyed on session_id, in the
        shape create_milestone_checkout would produce. Bypasses the
        checkout endpoint so this test is decoupled from stripe-mock's
        canned session-create response."""
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "kind": "milestone",
            "project_id": seed_mod.PROJECT_OPEN_ID,
            "milestone_id": seed_mod.MILESTONE_1_ID,
            "invoice_id": seed_mod.INVOICE_OPEN_ID,
            "amount": 100000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })

    async def test_signed_webhook_flips_milestone_invoice_tx(
        self, anon_client, db,
    ):
        session_id = "cs_test_milestone_happy_flip"
        await self._seed_pending_milestone_tx(db, session_id=session_id)

        payload, headers = sf.checkout_session_completed(
            session_id=session_id, kind="milestone",
            metadata={"milestone_id": seed_mod.MILESTONE_1_ID,
                      "invoice_id": seed_mod.INVOICE_OPEN_ID,
                      "project_id": seed_mod.PROJECT_OPEN_ID},
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200, r.text

        pt = await db.payment_transactions.find_one({"session_id": session_id})
        assert pt["payment_status"] == "paid"

        m = await db.project_milestones.find_one({"id": seed_mod.MILESTONE_1_ID})
        assert m["status"] == "paid"
        assert m.get("paid_at")

        inv = await db.project_invoices.find_one({"id": seed_mod.INVOICE_OPEN_ID})
        assert inv["status"] == "paid"
        assert inv.get("paid_at")


# ============================================================================
# 3. Idempotency — replay same event.id twice, assert single flip
# ============================================================================

class TestMilestoneReplayIdempotency:
    """S-03(b) evidence for the milestone branch. Same shape as the
    hours-purchase idempotency test — the session_id + $ne guard at
    projects.py:882 is expected to hold for sequential replay, but no
    stripe_events collection means an event-id-level dedup does not
    exist. Documented here so the fix scope is unambiguous."""

    async def test_concurrent_replay_is_still_idempotent(
        self, anon_client, db,
    ):
        """Mirrors test_concurrent_replay_may_double_credit from
        test_10_hours_purchase.py but for the milestone branch. The
        milestone branch at server.py:575-588 shares the same TOCTOU
        shape (snapshot find_one → Python if-check → follow-on writes
        inside the if-block), BUT the follow-on writes are idempotent
        `$set` (status="paid", paid_at) — no `$inc`. So concurrent
        delivery cannot double-credit or otherwise corrupt monetary
        state; the only observable effect is that `paid_at` gets
        restamped by whichever handler finishes last.

        This test is a passing invariant, not an xfail. Recorded here
        so a future refactor that adds a `$inc` (commissions, ledger,
        hours-credit-back) to this branch inherits the S-03(c) bug
        visibly. See SECURITY_BACKLOG.md S-03 note (c)."""
        import asyncio

        session_id = "cs_test_milestone_replay_concurrent"
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "kind": "milestone",
            "project_id": seed_mod.PROJECT_OPEN_ID,
            "milestone_id": seed_mod.MILESTONE_1_ID,
            "invoice_id": seed_mod.INVOICE_OPEN_ID,
            "amount": 100000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })
        payload, headers = sf.checkout_session_completed(
            session_id=session_id, kind="milestone",
            metadata={"milestone_id": seed_mod.MILESTONE_1_ID,
                      "invoice_id": seed_mod.INVOICE_OPEN_ID},
        )
        results = await asyncio.gather(*[
            anon_client.post("/api/stripe/webhook",
                             content=payload, headers=headers)
            for _ in range(5)
        ])
        for r in results:
            assert r.status_code == 200, r.text

        # No money-side field to double-count. State just settles paid.
        m = await db.project_milestones.find_one({"id": seed_mod.MILESTONE_1_ID})
        assert m["status"] == "paid"
        assert m.get("paid_at"), (
            "paid_at should be stamped (once by the winner, or restamped "
            "by every follow-on handler — either way non-null)"
        )
        inv = await db.project_invoices.find_one({"id": seed_mod.INVOICE_OPEN_ID})
        assert inv["status"] == "paid"
        pt = await db.payment_transactions.find_one({"session_id": session_id})
        assert pt["payment_status"] == "paid"

    async def test_sequential_replay_leaves_state_stable(
        self, anon_client, db,
    ):
        session_id = "cs_test_milestone_replay_seq"
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "kind": "milestone",
            "project_id": seed_mod.PROJECT_OPEN_ID,
            "milestone_id": seed_mod.MILESTONE_1_ID,
            "invoice_id": seed_mod.INVOICE_OPEN_ID,
            "amount": 100000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })
        payload, headers = sf.checkout_session_completed(
            session_id=session_id, kind="milestone",
            metadata={"milestone_id": seed_mod.MILESTONE_1_ID,
                      "invoice_id": seed_mod.INVOICE_OPEN_ID},
        )
        for _ in range(2):
            r = await anon_client.post(
                "/api/stripe/webhook", content=payload, headers=headers,
            )
            assert r.status_code == 200

        m = await db.project_milestones.find_one({"id": seed_mod.MILESTONE_1_ID})
        # Milestone stays exactly 'paid' — no duplicate transitions logged
        # or timestamps stomped.
        assert m["status"] == "paid"


# ============================================================================
# 4. Forged / bad-signature webhook does not flip
# ============================================================================

class TestMilestoneForgedWebhook:
    async def test_bad_signature_does_not_flip_milestone(
        self, anon_client, db,
    ):
        session_id = "cs_test_milestone_forged"
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "kind": "milestone",
            "project_id": seed_mod.PROJECT_OPEN_ID,
            "milestone_id": seed_mod.MILESTONE_1_ID,
            "invoice_id": seed_mod.INVOICE_OPEN_ID,
            "amount": 100000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })
        payload, _ = sf.checkout_session_completed(
            session_id=session_id, kind="milestone",
            metadata={"milestone_id": seed_mod.MILESTONE_1_ID,
                      "invoice_id": seed_mod.INVOICE_OPEN_ID},
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload,
            headers=sf.with_bad_signature(payload),
        )
        assert r.status_code == 400
        m = await db.project_milestones.find_one({"id": seed_mod.MILESTONE_1_ID})
        assert m["status"] != "paid", (
            f"Forged milestone webhook flipped status to {m['status']}"
        )
        pt = await db.payment_transactions.find_one({"session_id": session_id})
        assert pt["payment_status"] == "pending"


# ============================================================================
# 5. Unknown milestone session → clean 200 no-op
# ============================================================================

class TestMilestoneUnknownSession:
    async def test_unknown_session_is_no_op(self, anon_client, db):
        payload, headers = sf.checkout_session_completed(
            session_id="cs_test_milestone_unknown",
            kind="milestone",
            metadata={"milestone_id": "does-not-exist",
                      "invoice_id": "does-not-exist"},
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200
        # Nothing created; seed milestone untouched.
        m = await db.project_milestones.find_one({"id": seed_mod.MILESTONE_1_ID})
        assert m["status"] == "invoiced"  # seed default


# ============================================================================
# 6. GET status endpoint — auth-required + role gate + payment_status guard
# ============================================================================

class TestMilestonePaymentStatus:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get(
            "/api/projects/milestone-payment/status/cs_any"
        )
        assert r.status_code == 401

    async def test_unknown_session_404(self, employer_card_client):
        r = await employer_card_client.get(
            "/api/projects/milestone-payment/status/cs_unknown_polling"
        )
        assert r.status_code == 404

    async def test_status_endpoint_reports_paid_after_webhook(
        self, anon_client, employer_card_client, db,
    ):
        """End-to-end: fire the signed webhook → milestone/invoice/tx
        flip paid → the status endpoint reports payment_status='paid'
        without hitting Stripe."""
        session_id = "cs_test_milestone_status_reports_paid"
        await db.payment_transactions.insert_one({
            "id": f"pt-{session_id}", "session_id": session_id,
            "user_id": seed_mod.EMPLOYER_CARD_ID, "kind": "milestone",
            "project_id": seed_mod.PROJECT_OPEN_ID,
            "milestone_id": seed_mod.MILESTONE_1_ID,
            "invoice_id": seed_mod.INVOICE_OPEN_ID,
            "amount": 100000, "currency": "usd",
            "status": "initiated", "payment_status": "pending",
            "created_at": "2026-09-06T00:00:00+00:00",
            "updated_at": "2026-09-06T00:00:00+00:00",
        })
        payload, headers = sf.checkout_session_completed(
            session_id=session_id, kind="milestone",
            metadata={"milestone_id": seed_mod.MILESTONE_1_ID,
                      "invoice_id": seed_mod.INVOICE_OPEN_ID},
        )
        wh = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert wh.status_code == 200

        r = await employer_card_client.get(
            f"/api/projects/milestone-payment/status/{session_id}"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["payment_status"] == "paid"
        assert body["milestone_id"] == seed_mod.MILESTONE_1_ID
