"""Iteration 35 — Fee Refund Path + Reputation Boost Ribbon.

Covers:
  * POST /api/admin/grievances/{gid}/refund-fee validations (422/400/403/404)
  * Successful refund creates Stripe refund + persists refund_id/refunded_at
  * Idempotent guard on already-refunded fee (400)
  * db.notifications 'dispute_fee_refunded' row for payer
  * dispute_fee_transactions row flips to refunded with refund_id
  * GET /api/talent list + GET /api/talent/{id} expose is_proven_reliable
  * Ribbon fades after PROVEN_RELIABLE_DAYS (90)
"""
import os
import uuid
import asyncio
import pytest
import requests
from datetime import timedelta
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient

import sys
sys.path.insert(0, "/app/backend")
from deps import now as _now  # noqa: E402


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    fe = Path("/app/frontend/.env")
    for line in fe.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _load_backend_url()
ADMIN = ("admin@talenthub.io", "Admin@2026")


def _load_env(path):
    d = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


_BACKEND_ENV = _load_env("/app/backend/.env")
MONGO_URL = _BACKEND_ENV["MONGO_URL"]
DB_NAME = _BACKEND_ENV["DB_NAME"]
STRIPE_KEY = _BACKEND_ENV["STRIPE_SECRET_KEY"]


# ---------------- helpers ----------------
def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(email, pw):
    s = _sess()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return s


def _register(role):
    tag = uuid.uuid4().hex[:8]
    email = f"TEST_i35_{role}_{tag}@test.io"
    pw = "Test@2026Aa"
    body = {"email": email, "password": pw, "name": f"TEST i35 {role} {tag}", "role": role}
    s = _sess()
    r = s.post(f"{BASE}/api/auth/register", json=body, timeout=20)
    assert r.status_code == 200, f"register: {r.status_code} {r.text[:300]}"
    return {"session": s, "email": email, "password": pw, "id": r.json()["id"]}


def _grant_hours(user_id, hours):
    adm = _login(*ADMIN)
    r = adm.post(f"{BASE}/api/admin/users/{user_id}/adjust",
                 json={"hours_delta": hours, "reason": "iter35 seed"}, timeout=15)
    assert r.status_code == 200


def _run(coro):
    return asyncio.run(coro)


def _db_call(coro_fn):
    async def _wrap():
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            return await coro_fn(client[DB_NAME])
        finally:
            client.close()
    return _run(_wrap())


def _sign_engagement_submit(employer, talent, hours=10):
    e = employer["session"].post(f"{BASE}/api/engagements", json={
        "talent_id": talent["id"], "hours": hours,
        "scope": "TEST i35 refund flow scope description here",
        "mode": "remote", "location": "",
    }, timeout=15)
    assert e.status_code == 200, e.text[:300]
    eid = e.json()["id"]
    employer["session"].post(f"{BASE}/api/engagements/sign",
                             json={"engagement_id": eid, "signature": "Emp", "onsite_ack": False}, timeout=15)
    talent["session"].post(f"{BASE}/api/engagements/sign",
                           json={"engagement_id": eid, "signature": "Tal", "onsite_ack": False}, timeout=15)
    d = talent["session"].post(f"{BASE}/api/deliverables", json={
        "engagement_id": eid, "title": "TEST i35",
        "description": "initial", "link": "https://x/v0", "hours_claimed": 1.0,
    }, timeout=15)
    assert d.status_code == 200
    return eid, d.json()["id"]


def _drive_to_ruled_dispute(employer, talent, ruling="talent"):
    """Push a deliverable through 5 revisions, dispute, and admin rules."""
    eid, did = _sign_engagement_submit(employer, talent, hours=10)
    for n in range(1, 6):
        rr = employer["session"].post(f"{BASE}/api/deliverables/{did}/request-revision",
                                      json={"justification": f"iter35 revision {n} more polish thoroughly",
                                            "priority": "minor"}, timeout=15)
        assert rr.status_code == 200
        if n < 5:
            talent["session"].post(f"{BASE}/api/deliverables/{did}/resubmit",
                                   json={"link": f"https://x/v{n}", "hours_claimed": 1.0}, timeout=15)
    dr = talent["session"].post(f"{BASE}/api/deliverables/{did}/dispute",
                                json={"reason": "employer keeps scope-creeping across cycles"},
                                timeout=15)
    assert dr.status_code == 200, dr.text[:300]
    gid = dr.json()["grievance"]["id"]
    adm = _login(*ADMIN)
    r = adm.post(f"{BASE}/api/admin/revisions/{gid}/rule",
                 json={"ruling": ruling, "notes": "iter35 admin ruling for test"}, timeout=15)
    assert r.status_code == 200
    return gid


def _create_paid_payment_intent():
    """Create + confirm a real Stripe test-mode PI so we have something refundable."""
    import stripe
    stripe.api_key = STRIPE_KEY
    pi = stripe.PaymentIntent.create(
        amount=4900, currency="usd",
        payment_method="pm_card_visa",
        payment_method_types=["card"],
        confirm=True,
    )
    assert pi.status == "succeeded", f"PI not succeeded: {pi.status}"
    return pi.id


def _mark_fee_paid_via_db(gid, payer_id, pi_id, session_id=None):
    """Inject a paid dispute_fee + matching dispute_fee_transactions row."""
    sid = session_id or f"cs_test_iter35_{uuid.uuid4().hex[:16]}"
    now_iso = _now().isoformat()

    async def _do(db):
        await db.grievances.update_one(
            {"id": gid},
            {"$set": {
                "dispute_fee.payment_status": "paid",
                "dispute_fee.paid_at": now_iso,
                "dispute_fee.paid_by_id": payer_id,
                "dispute_fee.payment_intent_id": pi_id,
                "dispute_fee.stripe_session_id": sid,
            }},
        )
        await db.dispute_fee_transactions.insert_one({
            "id": uuid.uuid4().hex, "grievance_id": gid, "session_id": sid,
            "payer_id": payer_id, "amount_cents": 4900,
            "status": "completed", "payment_status": "paid",
            "payment_intent_id": pi_id,
            "created_at": now_iso, "paid_at": now_iso,
        })
    _db_call(_do)
    return sid


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def employer():
    e = _register("employer")
    _grant_hours(e["id"], 500)
    return e


# ==============================================================================
# 1. Refund validations
# ==============================================================================
class TestRefundValidations:
    def test_refund_short_reason_422(self, employer):
        tal = _register("talent")
        gid = _drive_to_ruled_dispute(employer, tal, ruling="talent")
        adm = _login(*ADMIN)
        r = adm.post(f"{BASE}/api/admin/grievances/{gid}/refund-fee",
                     json={"reason": "short "}, timeout=15)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text[:200]}"

    def test_refund_unpaid_400(self, employer):
        tal = _register("talent")
        gid = _drive_to_ruled_dispute(employer, tal, ruling="talent")
        adm = _login(*ADMIN)
        r = adm.post(f"{BASE}/api/admin/grievances/{gid}/refund-fee",
                     json={"reason": "New evidence surfaced clearly"}, timeout=15)
        assert r.status_code == 400
        assert "not been paid" in r.text.lower() or "paid" in r.text.lower()

    def test_refund_missing_grievance_404(self):
        adm = _login(*ADMIN)
        r = adm.post(f"{BASE}/api/admin/grievances/does-not-exist-abc/refund-fee",
                     json={"reason": "Some valid reason here"}, timeout=15)
        assert r.status_code == 404

    def test_refund_non_admin_403(self, employer):
        tal = _register("talent")
        gid = _drive_to_ruled_dispute(employer, tal, ruling="talent")
        # employer trying
        r = employer["session"].post(f"{BASE}/api/admin/grievances/{gid}/refund-fee",
                                     json={"reason": "New evidence surfaced clearly"}, timeout=15)
        assert r.status_code == 403
        # talent trying
        r2 = tal["session"].post(f"{BASE}/api/admin/grievances/{gid}/refund-fee",
                                 json={"reason": "New evidence surfaced clearly"}, timeout=15)
        assert r2.status_code == 403


# ==============================================================================
# 2. Successful refund end-to-end via real Stripe test-mode
# ==============================================================================
class TestRefundHappyPath:
    _gid = None
    _pi_id = None
    _payer_id = None

    def test_refund_success_returns_ok(self, employer):
        tal = _register("talent")
        gid = _drive_to_ruled_dispute(employer, tal, ruling="talent")  # employer owes
        pi_id = _create_paid_payment_intent()
        _mark_fee_paid_via_db(gid, employer["id"], pi_id)

        adm = _login(*ADMIN)
        r = adm.post(f"{BASE}/api/admin/grievances/{gid}/refund-fee",
                     json={"reason": "New evidence surfaced — issuing refund"}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        j = r.json()
        assert j["ok"] is True
        assert j["refund_id"] and j["refund_id"].startswith("re_")
        assert j["refunded_at"]
        assert float(j["amount_usd"]) == 49.0

        # Verify with Stripe SDK
        import stripe
        stripe.api_key = STRIPE_KEY
        ref = stripe.Refund.retrieve(j["refund_id"])
        assert ref.status == "succeeded", f"Stripe refund not succeeded: {ref.status}"

        TestRefundHappyPath._gid = gid
        TestRefundHappyPath._pi_id = pi_id
        TestRefundHappyPath._payer_id = employer["id"]

    def test_fee_status_shows_refunded(self, employer):
        gid = TestRefundHappyPath._gid
        assert gid, "prior test didn't run"
        r = employer["session"].get(f"{BASE}/api/grievances/{gid}/fee-status", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["fee"]["payment_status"] == "refunded"

        # Direct DB check for refunded_at + transactions
        async def _do(db):
            g = await db.grievances.find_one({"id": gid}, {"_id": 0, "dispute_fee": 1})
            tx = await db.dispute_fee_transactions.find_one({"grievance_id": gid}, {"_id": 0})
            return g, tx
        g, tx = _db_call(_do)
        assert g["dispute_fee"].get("refunded_at")
        assert g["dispute_fee"].get("refund_id", "").startswith("re_")
        assert g["dispute_fee"].get("refund_reason")
        assert g["dispute_fee"].get("refunded_by_id")
        assert tx["payment_status"] == "refunded"
        assert tx.get("refund_id", "").startswith("re_")

    def test_notification_row_for_payer(self):
        payer_id = TestRefundHappyPath._payer_id
        gid = TestRefundHappyPath._gid

        async def _do(db):
            return await db.notifications.find(
                {"user_id": payer_id, "type": "dispute_fee_refunded",
                 "grievance_id": gid}, {"_id": 0},
            ).to_list(10)
        rows = _db_call(_do)
        assert len(rows) == 1, f"expected 1 notification, got {len(rows)}"
        assert rows[0].get("ref")

    def test_refund_idempotent_400(self):
        gid = TestRefundHappyPath._gid
        adm = _login(*ADMIN)
        r = adm.post(f"{BASE}/api/admin/grievances/{gid}/refund-fee",
                     json={"reason": "Second attempt should fail"}, timeout=15)
        assert r.status_code == 400, r.text[:200]


# ==============================================================================
# 3. Reputation ribbon: is_proven_reliable in list + detail
# ==============================================================================
def _set_profile(user_id, patch):
    async def _do(db):
        await db.users.update_one({"id": user_id},
                                   {"$set": {f"profile.{k}": v for k, v in patch.items()}})
    _db_call(_do)


class TestProvenReliable:
    def test_list_and_detail_expose_is_proven_reliable(self, employer):
        # Talent recently cleared → true
        t_recent = _register("talent")
        _set_profile(t_recent["id"], {"recovery_cleared_at": _now().isoformat()})
        # Talent cleared 100 days ago → false
        t_old = _register("talent")
        old_iso = (_now() - timedelta(days=100)).isoformat()
        _set_profile(t_old["id"], {"recovery_cleared_at": old_iso})
        # Talent w/ no recovery_cleared_at → false
        t_none = _register("talent")

        # List
        r = employer["session"].get(f"{BASE}/api/talent?limit=500", timeout=15)
        assert r.status_code == 200, r.text[:300]
        raw = r.json()
        items = raw.get("items") if isinstance(raw, dict) else raw
        by_id = {t["id"]: t for t in items if "id" in t}

        assert t_recent["id"] in by_id, "recent talent missing from list"
        assert by_id[t_recent["id"]].get("is_proven_reliable") is True
        # 100d old
        if t_old["id"] in by_id:
            assert by_id[t_old["id"]].get("is_proven_reliable") is False
        # none
        if t_none["id"] in by_id:
            assert by_id[t_none["id"]].get("is_proven_reliable") is False

        # Detail
        for uid, expected in [(t_recent["id"], True), (t_old["id"], False), (t_none["id"], False)]:
            rd = employer["session"].get(f"{BASE}/api/talent/{uid}", timeout=15)
            assert rd.status_code == 200, f"{uid}: {rd.status_code} {rd.text[:200]}"
            assert rd.json().get("is_proven_reliable") is expected, f"{uid}: {rd.json().get('is_proven_reliable')} != {expected}"

    def test_env_knob_present(self):
        from routes.revisions import PROVEN_RELIABLE_DAYS, is_proven_reliable
        assert PROVEN_RELIABLE_DAYS == 90
        # Sanity check helper
        assert is_proven_reliable({"recovery_cleared_at": _now().isoformat()}) is True
        assert is_proven_reliable({"recovery_cleared_at": (_now() - timedelta(days=100)).isoformat()}) is False
        assert is_proven_reliable({}) is False
