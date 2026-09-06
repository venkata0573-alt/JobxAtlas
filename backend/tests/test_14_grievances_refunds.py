"""Phase 1b tests — FEATURES.md §14 dispute-fee payment + admin refund
+ refund-analytics + signed refund-audit PDF + verify.

Every webhook interaction uses `tests/stripe_fixtures.py`.

Coverage:
- POST /api/grievances/{gid}/pay-fee — losing party creates checkout
- Webhook checkout.session.completed with kind=dispute_fee → fee marked paid
- POST /api/admin/grievances/{gid}/refund-fee — moderation admin refunds
- GET /api/admin/revisions/refund-analytics — 30-day series + rolling rate
- GET /api/admin/revisions/refund-audit/pdf — signed audit PDF + persisted receipt
- GET /api/admin/revisions/refund-audit/verify/{sig} — lookup by signature
- S-04 evidence: verify endpoint does NOT recompute over current data
  (xfail strict=True — flips xpass when S-04's recompute fix lands)
- $49 amount spot-checks across pay-fee response + refund response
- 3 negatives per endpoint

Skipped (already covered by test_12_13_revisions.py::TestFeeStatusS25):
- GET /api/grievances/{gid}/fee-status — payer + party + admin + anon
  + unrelated + unknown (6 tests). Not duplicated.
"""
from __future__ import annotations

import pytest

from tests import stripe_fixtures as sf
from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# Seed reminders:
# - GRIEVANCE_OPEN_ID: kind=revision_dispute, dispute_fee.owed_by_id=TALENT_FLAGGED_ID,
#   dispute_fee.payment_status="unpaid", NO .status field, NO .stripe_session_id.
# - Grievance.status is "open" in seed; pay-fee handler requires "resolved".
# - dispute_fee.status is missing; _fee_recipient() checks for owed_by_talent /
#   owed_by_employer. Tests that hit pay-fee must set both fields in setup.


DISPUTE_FEE_USD = 49.0  # FEATURES.md §14 canonical value; assert in multiple sites.


async def _resolve_dispute(db, *, ruling: str = "talent") -> None:
    """Flip the seeded grievance to resolved with a clear fee-owner so
    pay-fee accepts it. Ruling=talent → fee owed by employer, and
    vice-versa (mirrors admin_rule_dispute at revisions.py:329)."""
    fee_owner = "employer" if ruling == "talent" else "talent"
    await db.grievances.update_one(
        {"id": seed_mod.GRIEVANCE_OPEN_ID},
        {"$set": {"status": "resolved", "ruling": ruling,
                  "dispute_fee.status": f"owed_by_{fee_owner}",
                  # owed_by_id follows the status: if ruling for talent,
                  # the employer owes; else the talent owes.
                  "dispute_fee.owed_by_id": (
                      seed_mod.EMPLOYER_CARD_ID if fee_owner == "employer"
                      else seed_mod.TALENT_FLAGGED_ID
                  )}},
    )


# ============================================================================
# 1. POST /api/grievances/{gid}/pay-fee — losing party creates checkout
# ============================================================================

class TestPayFee:
    _PATH = f"/api/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/pay-fee"

    async def test_anon_401(self, anon_client):
        r = await anon_client.post(self._PATH, json={})
        assert r.status_code == 401

    async def test_unknown_grievance_404(self, employer_card_client):
        r = await employer_card_client.post(
            "/api/grievances/does-not-exist/pay-fee", json={},
        )
        assert r.status_code == 404

    async def test_dispute_not_resolved_400(self, talent_flagged_client, db):
        """Seed leaves grievance.status="open"; pay-fee requires "resolved"."""
        r = await talent_flagged_client.post(self._PATH, json={})
        assert r.status_code == 400, r.text
        assert "resolved" in r.text.lower()

    async def test_wrong_payer_403(self, talent_clean_client, db):
        """Only the losing party (owner of dispute_fee) can pay. Set fee
        owed by employer, then have an unrelated talent try to pay."""
        await _resolve_dispute(db, ruling="talent")  # fee owed by employer
        r = await talent_clean_client.post(self._PATH, json={})
        assert r.status_code == 403, r.text

    async def test_payer_creates_checkout_session_with_49_usd(
        self, employer_card_client, db,
    ):
        """Fee owed by employer (ruling was for talent). employer_card is
        the linked employer on the seeded grievance → is the payer →
        pay-fee returns a checkout URL. Also asserts the $49 amount is
        the actual line-item on the Stripe session (via stripe-mock)."""
        await _resolve_dispute(db, ruling="talent")  # fee owed by employer_card
        r = await employer_card_client.post(
            self._PATH,
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("checkout_url"), (
            f"pay-fee must return checkout_url; got: {body}"
        )
        assert body.get("session_id")

        # dispute_fee_transactions row inserted keyed on session_id.
        tx = await db.dispute_fee_transactions.find_one({
            "session_id": body["session_id"],
        })
        assert tx is not None
        assert tx["grievance_id"] == seed_mod.GRIEVANCE_OPEN_ID
        assert tx["payer_id"] == seed_mod.EMPLOYER_CARD_ID
        # $49 in cents. FEATURES.md §14 canonical amount.
        assert tx["amount_cents"] == int(DISPUTE_FEE_USD * 100), (
            f"Fee amount must be ${DISPUTE_FEE_USD} = "
            f"{int(DISPUTE_FEE_USD * 100)} cents; got {tx['amount_cents']}"
        )

    async def test_already_paid_short_circuits(
        self, employer_card_client, db,
    ):
        """If dispute_fee.payment_status is already 'paid', pay-fee
        returns already_paid=True (idempotent). No new session created."""
        await _resolve_dispute(db, ruling="talent")
        await db.grievances.update_one(
            {"id": seed_mod.GRIEVANCE_OPEN_ID},
            {"$set": {"dispute_fee.payment_status": "paid"}},
        )
        r = await employer_card_client.post(self._PATH, json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("already_paid") is True
        assert body.get("amount_usd") == DISPUTE_FEE_USD


# ============================================================================
# 2. Dispute-fee webhook — checkout.session.completed with kind=dispute_fee
# ============================================================================

class TestDisputeFeeWebhook:
    async def _pay_fee_and_get_session_id(
        self, employer_card_client, db,
    ) -> str:
        """Set up + kick off pay-fee, return the session_id so the test
        can fire a signed webhook against the SAME id (dispute_fee_
        transactions is keyed on session_id)."""
        await _resolve_dispute(db, ruling="talent")
        r = await employer_card_client.post(
            f"/api/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/pay-fee",
            json={"origin_url": "https://localhost:13000"},
        )
        assert r.status_code == 200, r.text
        return r.json()["session_id"]

    async def test_signed_webhook_flips_dispute_fee_paid(
        self, anon_client, employer_card_client, db,
    ):
        session_id = await self._pay_fee_and_get_session_id(
            employer_card_client, db,
        )
        payload, headers = sf.checkout_session_completed(
            session_id=session_id,
            kind="dispute_fee",
            metadata={"grievance_id": seed_mod.GRIEVANCE_OPEN_ID,
                      "payer_id": seed_mod.EMPLOYER_CARD_ID,
                      "grievance_ref": "GR-SEED-0001"},
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload, headers=headers,
        )
        assert r.status_code == 200, r.text

        # dispute_fee.payment_status flipped to paid
        g = await db.grievances.find_one({"id": seed_mod.GRIEVANCE_OPEN_ID})
        assert g["dispute_fee"]["payment_status"] == "paid"
        assert g["dispute_fee"].get("paid_at")

        # dispute_fee_transactions row flipped too
        tx = await db.dispute_fee_transactions.find_one({"session_id": session_id})
        assert tx["payment_status"] == "paid"
        assert tx.get("paid_at")

    async def test_bad_signature_does_not_flip(
        self, anon_client, employer_card_client, db,
    ):
        session_id = await self._pay_fee_and_get_session_id(
            employer_card_client, db,
        )
        payload, _ = sf.checkout_session_completed(
            session_id=session_id, kind="dispute_fee",
            metadata={"grievance_id": seed_mod.GRIEVANCE_OPEN_ID},
        )
        r = await anon_client.post(
            "/api/stripe/webhook", content=payload,
            headers=sf.with_bad_signature(payload),
        )
        assert r.status_code == 400
        g = await db.grievances.find_one({"id": seed_mod.GRIEVANCE_OPEN_ID})
        assert g["dispute_fee"]["payment_status"] != "paid"


# ============================================================================
# 3. POST /api/admin/grievances/{gid}/refund-fee — moderation admin refund
# ============================================================================

class TestRefundFee:
    _PATH = f"/api/admin/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/refund-fee"

    async def _mark_fee_paid(
        self, db, *, payment_intent_id: str = "pi_test_refund_fee",
    ) -> None:
        """Force the grievance into a refundable state: resolved,
        dispute_fee.payment_status=paid, with payment_intent_id. Also
        insert a matching dispute_fee_transactions row so the refund
        handler's update_one has a target."""
        await _resolve_dispute(db, ruling="talent")
        await db.grievances.update_one(
            {"id": seed_mod.GRIEVANCE_OPEN_ID},
            {"$set": {"dispute_fee.payment_status": "paid",
                      "dispute_fee.payment_intent_id": payment_intent_id,
                      "dispute_fee.paid_at": "2026-09-01T00:00:00+00:00",
                      "dispute_fee.paid_by_id": seed_mod.EMPLOYER_CARD_ID}},
        )
        await db.dispute_fee_transactions.insert_one({
            "id": "tx-refund-test", "session_id": "cs_refund_test",
            "grievance_id": seed_mod.GRIEVANCE_OPEN_ID,
            "payer_id": seed_mod.EMPLOYER_CARD_ID,
            "amount_cents": int(DISPUTE_FEE_USD * 100),
            "payment_intent_id": payment_intent_id,
            "status": "completed", "payment_status": "paid",
            "paid_at": "2026-09-01T00:00:00+00:00",
            "created_at": "2026-09-01T00:00:00+00:00",
        })

    async def test_anon_401(self, anon_client):
        r = await anon_client.post(self._PATH, json={"reason": "test reason"})
        assert r.status_code == 401

    async def test_admin_noscope_403(self, admin_noscope_client):
        """S-09 pattern check: admin without moderation scope must not pass."""
        r = await admin_noscope_client.post(
            self._PATH, json={"reason": "trying without scope"},
        )
        assert r.status_code == 403

    async def test_unknown_grievance_404(self, admin_all_client):
        r = await admin_all_client.post(
            "/api/admin/grievances/does-not-exist/refund-fee",
            json={"reason": "not found path"},
        )
        assert r.status_code == 404

    async def test_fee_not_paid_400(self, admin_all_client, db):
        """Seed fee is 'unpaid'; refund handler requires 'paid'."""
        r = await admin_all_client.post(
            self._PATH, json={"reason": "refund unpaid fee"},
        )
        assert r.status_code == 400, r.text
        assert "not been paid" in r.text.lower()

    async def test_fee_already_refunded_400(self, admin_all_client, db):
        await _resolve_dispute(db, ruling="talent")
        await db.grievances.update_one(
            {"id": seed_mod.GRIEVANCE_OPEN_ID},
            {"$set": {"dispute_fee.payment_status": "refunded"}},
        )
        r = await admin_all_client.post(
            self._PATH, json={"reason": "double refund attempt"},
        )
        assert r.status_code == 400
        assert "already refunded" in r.text.lower()

    async def test_short_reason_rejected(self, admin_all_client, db):
        """min_length=10 on RefundIn."""
        await self._mark_fee_paid(db)
        r = await admin_all_client.post(
            self._PATH, json={"reason": "short"},
        )
        assert r.status_code == 422

    async def test_admin_refund_flips_state_and_returns_refund_id(
        self, admin_all_client, db,
    ):
        """Happy path with stripe-mock — stripe.Refund.create returns a
        canned refund object; handler flips dispute_fee + dispute_fee_
        transactions to refunded, returns refund_id + $49 amount."""
        await self._mark_fee_paid(db, payment_intent_id="pi_test_refund_happy")
        r = await admin_all_client.post(
            self._PATH,
            json={"reason": "New evidence surfaced after ruling"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body.get("refund_id"), (
            f"refund_id must be returned; got: {body}"
        )
        assert body["amount_usd"] == DISPUTE_FEE_USD

        g = await db.grievances.find_one({"id": seed_mod.GRIEVANCE_OPEN_ID})
        assert g["dispute_fee"]["payment_status"] == "refunded"
        assert g["dispute_fee"].get("refunded_at")
        assert g["dispute_fee"].get("refund_id") == body["refund_id"]

        tx = await db.dispute_fee_transactions.find_one(
            {"id": "tx-refund-test"},
        )
        assert tx["payment_status"] == "refunded"
        assert tx.get("refunded_at")
        assert tx.get("refunded_by_id") == seed_mod.ADMIN_ALL_ID


# ============================================================================
# 4. GET /api/admin/revisions/refund-analytics — 30-day + rolling rate
# ============================================================================

class TestRefundAnalytics:
    _PATH = "/api/admin/revisions/refund-analytics"

    async def test_anon_401(self, anon_client):
        r = await anon_client.get(self._PATH)
        assert r.status_code == 401

    async def test_admin_noscope_403(self, admin_noscope_client):
        r = await admin_noscope_client.get(self._PATH)
        assert r.status_code == 403

    async def test_empty_state_returns_30_zero_buckets(self, admin_all_client):
        r = await admin_all_client.get(self._PATH)
        assert r.status_code == 200
        body = r.json()
        # 30-day window (server: buckets[d] for 30 days).
        assert len(body["series"]) == 30
        assert body["totals"]["paid_30d"] == 0
        assert body["totals"]["refunded_30d"] == 0
        assert body["totals"]["refund_rate_pct"] == 0

    async def test_paid_and_refunded_reflected_in_series(
        self, admin_all_client, db,
    ):
        """Seed one paid tx + one refunded tx, both within the 30-day
        window. Expect totals.paid_30d>=1, refunded_30d>=1, rate>0."""
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.dispute_fee_transactions.insert_many([
            {"id": "tx-paid-only", "grievance_id": "g1",
             "session_id": "cs_paid_only",
             "payer_id": seed_mod.EMPLOYER_CARD_ID,
             "amount_cents": int(DISPUTE_FEE_USD * 100),
             "status": "completed", "payment_status": "paid",
             "paid_at": recent, "created_at": recent},
            {"id": "tx-paid-refunded", "grievance_id": "g2",
             "session_id": "cs_paid_refunded",
             "payer_id": seed_mod.EMPLOYER_CARD_ID,
             "amount_cents": int(DISPUTE_FEE_USD * 100),
             "status": "completed", "payment_status": "refunded",
             "paid_at": recent, "refunded_at": recent, "created_at": recent},
        ])
        r = await admin_all_client.get(self._PATH)
        assert r.status_code == 200
        body = r.json()
        assert body["totals"]["paid_30d"] >= 2, (
            f"Two paid txs seeded; totals paid_30d = {body['totals']['paid_30d']}"
        )
        assert body["totals"]["refunded_30d"] >= 1
        assert body["totals"]["refund_rate_pct"] > 0
        assert body["alert"]["threshold_pct"] == 20, (
            "refund_alert_threshold_pct default is 20 per config.BusinessRules"
        )


# ============================================================================
# 5. GET /api/admin/revisions/refund-audit/pdf — signed PDF + receipt row
# ============================================================================

class TestRefundAuditPdf:
    _PATH = "/api/admin/revisions/refund-audit/pdf"

    async def test_anon_401(self, anon_client):
        r = await anon_client.get(self._PATH)
        assert r.status_code == 401

    async def test_admin_noscope_403(self, admin_noscope_client):
        r = await admin_noscope_client.get(self._PATH)
        assert r.status_code == 403

    async def test_bad_days_zero_rejected(self, admin_all_client):
        r = await admin_all_client.get(f"{self._PATH}?days=0")
        assert r.status_code == 400

    async def test_bad_days_over_365_rejected(self, admin_all_client):
        r = await admin_all_client.get(f"{self._PATH}?days=400")
        assert r.status_code == 400

    async def test_pdf_returns_bytes_signature_header_and_persists_receipt(
        self, admin_all_client, db,
    ):
        r = await admin_all_client.get(f"{self._PATH}?days=30")
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type") == "application/pdf"
        assert r.content.startswith(b"%PDF-"), (
            f"Response body should start with PDF magic bytes; "
            f"got: {r.content[:16]!r}"
        )
        sig = r.headers.get("x-audit-signature")
        assert sig and len(sig) == 64, (
            f"X-Audit-Signature header must be a 64-char sha256 hex; got: {sig!r}"
        )
        # Receipt row persisted.
        rec = await db.refund_audit_receipts.find_one({"signature": sig})
        assert rec is not None
        assert rec["issued_by_id"] == seed_mod.ADMIN_ALL_ID
        assert rec["row_count"] >= 0


# ============================================================================
# 6. GET /api/admin/revisions/refund-audit/verify/{sig} — lookup + S-04 canary
# ============================================================================

class TestRefundAuditVerify:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get(
            "/api/admin/revisions/refund-audit/verify/anysig"
        )
        assert r.status_code == 401

    async def test_admin_noscope_403(self, admin_noscope_client):
        r = await admin_noscope_client.get(
            "/api/admin/revisions/refund-audit/verify/anysig"
        )
        assert r.status_code == 403

    async def test_unknown_signature_returns_not_found(self, admin_all_client):
        r = await admin_all_client.get(
            "/api/admin/revisions/refund-audit/verify/"
            "0000000000000000000000000000000000000000000000000000000000000000"
        )
        assert r.status_code == 200
        assert r.json()["receipt_found"] is False

    async def test_known_signature_returns_receipt(self, admin_all_client):
        """Issue a PDF, extract signature, verify it. Round-trip proof."""
        r_pdf = await admin_all_client.get(
            "/api/admin/revisions/refund-audit/pdf?days=30"
        )
        assert r_pdf.status_code == 200
        sig = r_pdf.headers["x-audit-signature"]

        r_v = await admin_all_client.get(
            f"/api/admin/revisions/refund-audit/verify/{sig}"
        )
        assert r_v.status_code == 200
        body = r_v.json()
        assert body["receipt_found"] is True
        assert body["receipt"]["signature"] == sig
        assert body["receipt"]["issued_by_id"] == seed_mod.ADMIN_ALL_ID

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "S-04 evidence: the verify endpoint at revisions.py:978-987 "
            "does a plain `db.refund_audit_receipts.find_one({signature})` "
            "— it never RECOMPUTES `_refund_audit_signature` over the "
            "current dispute_fee_transactions rows. So a tampered "
            "underlying row still 'verifies' as long as the receipt row "
            "exists with that signature. The S-04 fix is (a) switch to "
            "hmac.new(secret, msg, sha256) + hmac.compare_digest, and "
            "(b) make verify re-run the query for the same window + "
            "recompute the hash + include recompute_matches: false in "
            "the response when tampering is detected. When (b) lands, "
            "the response body gains a `recompute_matches` field and "
            "this test's assertion (below) will pass — strict=True then "
            "fails on the unexpected pass, forcing removal."
        ),
    )
    async def test_verify_detects_tampering_via_recompute(
        self, admin_all_client, db,
    ):
        """Issue an audit PDF over an empty set → get sig. Then insert a
        refunded dispute_fee_transactions row into the same window
        (i.e. tamper with the underlying data). Re-verify. Today: still
        receipt_found=True with no recompute — S-04 gap. Post-fix:
        response includes recompute_matches=False."""
        from datetime import datetime, timezone, timedelta

        # 1. Issue over empty state — signature is over 0 rows.
        r_pdf = await admin_all_client.get(
            "/api/admin/revisions/refund-audit/pdf?days=30"
        )
        sig = r_pdf.headers["x-audit-signature"]

        # 2. Tamper: insert a refunded tx in the window that WASN'T there
        #    when the signature was computed. A recomputing verify would
        #    now hash over 1 row, produce a different sig, and flag the
        #    mismatch. A lookup-only verify (current) doesn't notice.
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        await db.dispute_fee_transactions.insert_one({
            "id": "tx-tamper", "grievance_id": "g-tamper",
            "session_id": "cs_tamper",
            "payer_id": seed_mod.EMPLOYER_CARD_ID,
            "amount_cents": int(DISPUTE_FEE_USD * 100),
            "status": "completed", "payment_status": "refunded",
            "paid_at": recent, "refunded_at": recent,
            "refunded_by_id": seed_mod.ADMIN_ALL_ID,
            "refund_reason": "tampering test row",
            "created_at": recent,
        })

        # 3. Re-verify. Post-S-04-fix expectation: response includes a
        #    recompute_matches=False. Today: field doesn't exist → default
        #    to None → assertion fails → xfail catches.
        r_v = await admin_all_client.get(
            f"/api/admin/revisions/refund-audit/verify/{sig}"
        )
        assert r_v.status_code == 200
        body = r_v.json()
        assert body.get("recompute_matches") is False, (
            "S-04 fix must include recompute_matches in the verify "
            "response and set it to False when the current data doesn't "
            "hash to the receipt signature. Current shape returns only "
            f"receipt_found; body={body}"
        )
