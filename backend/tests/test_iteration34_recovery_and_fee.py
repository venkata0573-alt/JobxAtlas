"""Iteration 34 — Talent Recovery Playbook + Dispute Fee Collection Flow.

Covers:
  * GET /api/talent/me/recovery-status (clean, penalised, employer=403)
  * Recovery streak on approve of revision_count==0 deliverables
  * Under_review lifted after 3 clean approvals
  * Excessive_revisions lifted after 5 clean approvals (+ visibility/rate reset)
  * Rejection resets streak
  * revision_count>0 approvals DO NOT increment streak
  * Approve accepts status='submitted' OR 'revision_resubmitted'
  * Dispute -> admin ruling -> notification + fee ownership + deliverable stamped
  * POST /grievances/{id}/pay-fee (permissions, 400/403/404, checkout url + amount)
  * GET /grievances/{id}/fee-status
  * Stripe webhook simulation (kind=dispute_fee) marks fee as paid + idempotent
"""
import os
import json
import time
import uuid
import hmac
import hashlib
import pytest
import requests
import asyncio
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    fe = Path("/app/frontend/.env")
    if fe.exists():
        for line in fe.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _load_backend_url()
ADMIN = ("admin@talenthub.io", "Admin@2026")

# Load backend env for mongo + stripe webhook secret
def _load_env(path):
    d = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d

_BACKEND_ENV = _load_env("/app/backend/.env")
MONGO_URL = _BACKEND_ENV.get("MONGO_URL")
DB_NAME = _BACKEND_ENV.get("DB_NAME")
STRIPE_WEBHOOK_SECRET = _BACKEND_ENV.get("STRIPE_WEBHOOK_SECRET")


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
    email = f"TEST_i34_{role}_{tag}@test.io"
    pw = "Test@2026Aa"
    body = {"email": email, "password": pw, "name": f"TEST i34 {role} {tag}", "role": role}
    s = _sess()
    r = s.post(f"{BASE}/api/auth/register", json=body, timeout=20)
    assert r.status_code == 200, f"register: {r.status_code} {r.text[:300]}"
    return {"session": s, "email": email, "password": pw, "id": r.json()["id"]}


def _grant_hours(user_id: str, hours: int):
    adm = _login(*ADMIN)
    r = adm.post(f"{BASE}/api/admin/users/{user_id}/adjust",
                 json={"hours_delta": hours, "reason": "iter34 test seed"}, timeout=15)
    assert r.status_code == 200, r.text[:300]


def _sign_engagement_submit(employer, talent, hours=5):
    e = employer["session"].post(f"{BASE}/api/engagements", json={
        "talent_id": talent["id"], "hours": hours,
        "scope": "TEST i34 recovery/fee flow scope description here",
        "mode": "remote", "location": "",
    }, timeout=15)
    assert e.status_code == 200, e.text[:300]
    eid = e.json()["id"]
    r1 = employer["session"].post(f"{BASE}/api/engagements/sign",
                                    json={"engagement_id": eid, "signature": "Emp", "onsite_ack": False}, timeout=15)
    assert r1.status_code == 200
    r2 = talent["session"].post(f"{BASE}/api/engagements/sign",
                                  json={"engagement_id": eid, "signature": "Tal", "onsite_ack": False}, timeout=15)
    assert r2.status_code == 200
    d = talent["session"].post(f"{BASE}/api/deliverables", json={
        "engagement_id": eid, "title": "TEST i34 deliverable",
        "description": "initial submission",
        "link": "https://example.com/v1", "hours_claimed": 1.0,
    }, timeout=15)
    assert d.status_code == 200, d.text[:300]
    return eid, d.json()["id"]


def _submit_new_deliverable(employer, talent, engagement_id, v="v1"):
    """After a prior deliverable is approved/rejected, submit another."""
    d = talent["session"].post(f"{BASE}/api/deliverables", json={
        "engagement_id": engagement_id, "title": f"TEST i34 d {v}",
        "description": "next batch",
        "link": f"https://example.com/{v}", "hours_claimed": 0.5,
    }, timeout=15)
    assert d.status_code == 200, d.text[:300]
    return d.json()["id"]


# Async mongo access
async def _get_db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client, client[DB_NAME]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def _set_user_profile(user_id: str, patch: dict):
    async def _do():
        client, db = await _get_db()
        try:
            await db.users.update_one({"id": user_id},
                                       {"$set": {f"profile.{k}": v for k, v in patch.items()}})
        finally:
            client.close()
    _run(_do())


def _get_user_profile(user_id: str) -> dict:
    async def _do():
        client, db = await _get_db()
        try:
            u = await db.users.find_one({"id": user_id}, {"_id": 0, "profile": 1})
            return (u or {}).get("profile") or {}
        finally:
            client.close()
    return _run(_do())


def _find_notifications(user_id: str, ntype: str):
    async def _do():
        client, db = await _get_db()
        try:
            return await db.notifications.find(
                {"user_id": user_id, "type": ntype}, {"_id": 0}
            ).to_list(50)
        finally:
            client.close()
    return _run(_do())


def _get_deliverable(deliverable_id: str) -> dict:
    async def _do():
        client, db = await _get_db()
        try:
            return await db.deliverables.find_one({"id": deliverable_id}, {"_id": 0}) or {}
        finally:
            client.close()
    return _run(_do())


def _get_transaction(session_id: str) -> dict:
    async def _do():
        client, db = await _get_db()
        try:
            return await db.dispute_fee_transactions.find_one({"session_id": session_id}, {"_id": 0}) or {}
        finally:
            client.close()
    return _run(_do())


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def employer():
    e = _register("employer")
    _grant_hours(e["id"], 500)
    return e


@pytest.fixture(scope="module")
def talent():
    return _register("talent")


# ==============================================================================
# 1. Recovery status endpoint basics
# ==============================================================================
class TestRecoveryStatus:
    def test_clean_talent_no_penalty(self, talent):
        r = talent["session"].get(f"{BASE}/api/talent/me/recovery-status", timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j["has_penalty"] is False
        assert j["clean_streak"] == 0

    def test_employer_forbidden(self, employer):
        r = employer["session"].get(f"{BASE}/api/talent/me/recovery-status", timeout=15)
        assert r.status_code == 403


# ==============================================================================
# 2. Under_review lifted after 3 clean approvals
# ==============================================================================
class TestRecoveryUnderReview:
    def test_under_review_lifts_after_3_clean_approvals(self, employer):
        tal = _register("talent")
        # Force under_review flag directly in DB
        _set_user_profile(tal["id"], {"under_review": True, "excessive_revisions": False,
                                        "clean_streak": 0})
        # Sign engagement w/ 10h
        eid, did1 = _sign_engagement_submit(employer, tal, hours=10)

        # Approve 1st (revision_count == 0)
        r = employer["session"].post(f"{BASE}/api/deliverables/{did1}/approve",
                                       json={"feedback": "good"}, timeout=15)
        assert r.status_code == 200, r.text[:300]

        prof = _get_user_profile(tal["id"])
        assert prof.get("clean_streak") == 1
        assert prof.get("under_review") is True

        # Recovery-status snapshot
        rs = tal["session"].get(f"{BASE}/api/talent/me/recovery-status").json()
        assert rs["has_penalty"] is True
        assert rs["target"] == "under_review"
        assert rs["clean_streak"] == 1
        assert rs["needed"] == 3
        assert rs["remaining"] == 2

        # 2nd approval
        did2 = _submit_new_deliverable(employer, tal, eid, "v2")
        r = employer["session"].post(f"{BASE}/api/deliverables/{did2}/approve",
                                       json={"feedback": "ok"}, timeout=15)
        assert r.status_code == 200
        prof = _get_user_profile(tal["id"])
        assert prof.get("clean_streak") == 2

        # 3rd approval -> under_review lifted, streak reset
        did3 = _submit_new_deliverable(employer, tal, eid, "v3")
        r = employer["session"].post(f"{BASE}/api/deliverables/{did3}/approve",
                                       json={"feedback": "great"}, timeout=15)
        assert r.status_code == 200
        prof = _get_user_profile(tal["id"])
        assert prof.get("under_review") is False, f"under_review not lifted: {prof}"
        assert prof.get("clean_streak") == 0

        # GET reflects it
        rs2 = tal["session"].get(f"{BASE}/api/talent/me/recovery-status").json()
        assert rs2["has_penalty"] is False
        assert rs2["clean_streak"] == 0


# ==============================================================================
# 3. Excessive_revisions lifted after 5 clean approvals
# ==============================================================================
class TestRecoveryExcessive:
    def test_excessive_lifts_after_5_clean(self, employer):
        tal = _register("talent")
        _set_user_profile(tal["id"], {
            "excessive_revisions": True, "under_review": True,
            "visibility_score": 80, "rate_bias_pct": -10, "clean_streak": 0,
        })
        eid, first = _sign_engagement_submit(employer, tal, hours=10)
        dids = [first]
        # approve first
        r = employer["session"].post(f"{BASE}/api/deliverables/{first}/approve",
                                       json={"feedback": "1"}, timeout=15)
        assert r.status_code == 200
        # approve 4 more
        for i in range(2, 6):
            did = _submit_new_deliverable(employer, tal, eid, f"v{i}")
            dids.append(did)
            r = employer["session"].post(f"{BASE}/api/deliverables/{did}/approve",
                                          json={"feedback": str(i)}, timeout=15)
            assert r.status_code == 200, r.text[:200]

        prof = _get_user_profile(tal["id"])
        assert prof.get("excessive_revisions") is False, f"still excessive: {prof}"
        assert int(prof.get("visibility_score") or 0) == 100
        assert float(prof.get("rate_bias_pct") or 0) == 0
        assert prof.get("clean_streak") == 0


# ==============================================================================
# 4. Rejection resets streak
# ==============================================================================
class TestStreakReset:
    def test_rejection_resets_streak(self, employer):
        tal = _register("talent")
        _set_user_profile(tal["id"], {"under_review": True, "clean_streak": 0})
        eid, did1 = _sign_engagement_submit(employer, tal, hours=10)
        # 1st approve
        assert employer["session"].post(f"{BASE}/api/deliverables/{did1}/approve",
                                          json={"feedback": "1"}, timeout=15).status_code == 200
        # 2nd approve
        did2 = _submit_new_deliverable(employer, tal, eid, "v2")
        assert employer["session"].post(f"{BASE}/api/deliverables/{did2}/approve",
                                          json={"feedback": "2"}, timeout=15).status_code == 200
        assert _get_user_profile(tal["id"]).get("clean_streak") == 2
        # reject one → streak back to 0
        did3 = _submit_new_deliverable(employer, tal, eid, "v3")
        r = employer["session"].post(f"{BASE}/api/deliverables/{did3}/reject",
                                       json={"feedback": "not good enough here"}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        prof = _get_user_profile(tal["id"])
        assert prof.get("clean_streak") == 0
        rs = tal["session"].get(f"{BASE}/api/talent/me/recovery-status").json()
        assert rs["clean_streak"] == 0


# ==============================================================================
# 5. Only revision_count==0 approvals increment streak
# ==============================================================================
class TestDirtyApprovalNoStreak:
    def test_revision_resubmit_approval_does_not_increment(self, employer):
        tal = _register("talent")
        _set_user_profile(tal["id"], {"under_review": True, "clean_streak": 0})
        eid, did = _sign_engagement_submit(employer, tal, hours=5)
        # Request one revision → revision_count becomes 1
        rr = employer["session"].post(f"{BASE}/api/deliverables/{did}/request-revision",
                                        json={"justification": "please rework this deliverable thoroughly",
                                              "priority": "minor"}, timeout=15)
        assert rr.status_code == 200
        # Talent resubmits
        rs = tal["session"].post(f"{BASE}/api/deliverables/{did}/resubmit",
                                   json={"link": "https://x/v2", "hours_claimed": 1.0}, timeout=15)
        assert rs.status_code == 200
        # Employer approves the resubmitted deliverable (status=revision_resubmitted)
        r = employer["session"].post(f"{BASE}/api/deliverables/{did}/approve",
                                       json={"feedback": "ok"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        # Streak should still be 0 since revision_count == 1
        prof = _get_user_profile(tal["id"])
        assert prof.get("clean_streak", 0) == 0, f"streak wrongly incremented: {prof}"


# ==============================================================================
# 6. Approve/reject regression on already-reviewed
# ==============================================================================
class TestApproveRegression:
    def test_approve_accepts_resubmitted_and_400_on_already_reviewed(self, employer, talent):
        tal = _register("talent")
        eid, did = _sign_engagement_submit(employer, tal, hours=5)
        # request-revision, resubmit, approve → 200 (already tested indirectly above)
        rr = employer["session"].post(f"{BASE}/api/deliverables/{did}/request-revision",
                                        json={"justification": "please rework this thoroughly for sure",
                                              "priority": "minor"}, timeout=15)
        assert rr.status_code == 200
        assert tal["session"].post(f"{BASE}/api/deliverables/{did}/resubmit",
                                     json={"link": "https://x/v2", "hours_claimed": 1.0}, timeout=15).status_code == 200
        r = employer["session"].post(f"{BASE}/api/deliverables/{did}/approve",
                                       json={"feedback": "done"}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        # Second approve → 400 already reviewed
        r2 = employer["session"].post(f"{BASE}/api/deliverables/{did}/approve",
                                        json={"feedback": "again"}, timeout=15)
        assert r2.status_code == 400


# ==============================================================================
# 7-13. Fee collection flow
# ==============================================================================
def _drive_to_dispute(employer, talent):
    """Take a deliverable through 5 revisions and open a dispute."""
    eid, did = _sign_engagement_submit(employer, talent, hours=10)
    for n in range(1, 6):
        rr = employer["session"].post(f"{BASE}/api/deliverables/{did}/request-revision",
                                        json={"justification": f"iter34 rev {n} more polish please",
                                              "priority": "minor"}, timeout=15)
        assert rr.status_code == 200, rr.text[:200]
        if n < 5:
            rs = talent["session"].post(f"{BASE}/api/deliverables/{did}/resubmit",
                                          json={"link": f"https://x/v{n}", "hours_claimed": 1.0}, timeout=15)
            assert rs.status_code == 200
    dr = talent["session"].post(f"{BASE}/api/deliverables/{did}/dispute",
                                  json={"reason": "employer keeps scope-creeping across cycles again"},
                                  timeout=15)
    assert dr.status_code == 200, dr.text[:300]
    return eid, did, dr.json()["grievance"]["id"], dr.json()["ref"]


@pytest.fixture(scope="module")
def dispute_ruled_for_talent(employer):
    """Dispute ruled in favour of talent → employer owes the fee."""
    tal = _register("talent")
    eid, did, gid, ref = _drive_to_dispute(employer, tal)
    # Deliverable stamped
    dlv = _get_deliverable(did)
    assert dlv.get("dispute_grievance_id") == gid
    assert dlv.get("dispute_ref") == ref
    assert dlv.get("dispute_opened_at")
    # Admin rules for talent
    adm = _login(*ADMIN)
    r = adm.post(f"{BASE}/api/admin/revisions/{gid}/rule",
                 json={"ruling": "talent", "notes": "employer overreached scope creep"}, timeout=15)
    assert r.status_code == 200, r.text[:300]
    return {"employer": employer, "talent": tal, "engagement_id": eid,
            "deliverable_id": did, "grievance_id": gid, "ref": ref}


class TestDisputeStampAndRuling:
    def test_deliverable_stamped_on_dispute(self, dispute_ruled_for_talent):
        d = _get_deliverable(dispute_ruled_for_talent["deliverable_id"])
        assert d.get("dispute_grievance_id") == dispute_ruled_for_talent["grievance_id"]
        assert d.get("dispute_ref") == dispute_ruled_for_talent["ref"]
        assert d.get("dispute_opened_at")

    def test_deliverable_transitions_to_dispute_resolved(self, dispute_ruled_for_talent):
        d = _get_deliverable(dispute_ruled_for_talent["deliverable_id"])
        assert d.get("status") == "dispute_resolved"
        assert d.get("dispute_ruling") == "talent"

    def test_notification_recorded_for_losing_party(self, dispute_ruled_for_talent):
        # Ruling for talent → employer is losing party
        empid = dispute_ruled_for_talent["employer"]["id"]
        notes = _find_notifications(empid, "dispute_fee_due")
        rows = [n for n in notes if n.get("grievance_id") == dispute_ruled_for_talent["grievance_id"]]
        assert len(rows) == 1, f"expected 1 notification, got {len(rows)}"
        assert float(rows[0].get("amount_usd") or 0) == 49.0

    def test_fee_status_endpoint(self, dispute_ruled_for_talent):
        emp = dispute_ruled_for_talent["employer"]
        gid = dispute_ruled_for_talent["grievance_id"]
        r = emp["session"].get(f"{BASE}/api/grievances/{gid}/fee-status", timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j["ref"] == dispute_ruled_for_talent["ref"]
        assert j["ruling"] == "talent"
        assert j["fee"]["amount_usd"] == 49
        assert j["fee"]["status"] == "owed_by_employer"
        assert j["fee"]["payment_status"] == "unpaid"
        assert j["fee"]["owed_by"] == emp["id"]

    def test_fee_status_admin_and_talent_ok(self, dispute_ruled_for_talent):
        gid = dispute_ruled_for_talent["grievance_id"]
        adm = _login(*ADMIN)
        assert adm.get(f"{BASE}/api/grievances/{gid}/fee-status", timeout=15).status_code == 200
        assert dispute_ruled_for_talent["talent"]["session"].get(
            f"{BASE}/api/grievances/{gid}/fee-status", timeout=15).status_code == 200

    def test_fee_status_unrelated_forbidden(self, dispute_ruled_for_talent):
        gid = dispute_ruled_for_talent["grievance_id"]
        stranger = _register("talent")
        r = stranger["session"].get(f"{BASE}/api/grievances/{gid}/fee-status", timeout=15)
        assert r.status_code == 403


class TestPayFeeEndpoint:
    def test_pay_fee_by_loser_returns_checkout(self, dispute_ruled_for_talent):
        emp = dispute_ruled_for_talent["employer"]
        gid = dispute_ruled_for_talent["grievance_id"]
        r = emp["session"].post(f"{BASE}/api/grievances/{gid}/pay-fee",
                                  json={"origin_url": BASE}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        assert "checkout_url" in j and j["checkout_url"].startswith("https://")
        assert "session_id" in j and j["session_id"].startswith("cs_")
        assert j.get("amount_usd") == 49.0
        # Verify session metadata via Stripe SDK
        import stripe
        stripe.api_key = _BACKEND_ENV.get("STRIPE_SECRET_KEY")
        s = stripe.checkout.Session.retrieve(j["session_id"])
        assert s.metadata.get("kind") == "dispute_fee"
        assert s.metadata.get("payer_id") == emp["id"]
        # Stash on module for webhook test
        TestPayFeeEndpoint._session_id = j["session_id"]
        TestPayFeeEndpoint._gid = gid
        TestPayFeeEndpoint._empid = emp["id"]

    def test_pay_fee_by_winner_forbidden(self, dispute_ruled_for_talent):
        tal = dispute_ruled_for_talent["talent"]
        gid = dispute_ruled_for_talent["grievance_id"]
        r = tal["session"].post(f"{BASE}/api/grievances/{gid}/pay-fee",
                                  json={"origin_url": BASE}, timeout=15)
        assert r.status_code == 403

    def test_pay_fee_by_admin_forbidden(self, dispute_ruled_for_talent):
        gid = dispute_ruled_for_talent["grievance_id"]
        adm = _login(*ADMIN)
        r = adm.post(f"{BASE}/api/grievances/{gid}/pay-fee",
                     json={"origin_url": BASE}, timeout=15)
        assert r.status_code == 403

    def test_pay_fee_unrelated_forbidden(self, dispute_ruled_for_talent):
        stranger = _register("talent")
        gid = dispute_ruled_for_talent["grievance_id"]
        r = stranger["session"].post(f"{BASE}/api/grievances/{gid}/pay-fee",
                                       json={"origin_url": BASE}, timeout=15)
        assert r.status_code == 403

    def test_pay_fee_unresolved_dispute_400(self, employer):
        # Build a fresh dispute but do NOT rule
        tal = _register("talent")
        _, _, gid, _ = _drive_to_dispute(employer, tal)
        r = tal["session"].post(f"{BASE}/api/grievances/{gid}/pay-fee",
                                  json={"origin_url": BASE}, timeout=15)
        assert r.status_code == 400

    def test_pay_fee_missing_grievance_404(self, employer):
        r = employer["session"].post(f"{BASE}/api/grievances/does-not-exist-xyz/pay-fee",
                                       json={"origin_url": BASE}, timeout=15)
        assert r.status_code == 404


# ==============================================================================
# 8. Stripe webhook simulation
# ==============================================================================
def _stripe_sign(payload_bytes: bytes, secret: str, ts: int) -> str:
    signed = f"{ts}.".encode() + payload_bytes
    mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class TestStripeWebhookFeePaid:
    def test_webhook_marks_fee_paid_idempotently(self, dispute_ruled_for_talent):
        sid = getattr(TestPayFeeEndpoint, "_session_id", None)
        gid = getattr(TestPayFeeEndpoint, "_gid", None)
        assert sid, "session_id not captured from pay-fee test"
        # Build a fake checkout.session.completed event
        event = {
            "id": f"evt_test_{uuid.uuid4().hex[:12]}",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": sid, "object": "checkout.session",
                "metadata": {"kind": "dispute_fee", "grievance_id": gid,
                              "payer_id": TestPayFeeEndpoint._empid},
            }},
        }
        body = json.dumps(event).encode()
        ts = int(time.time())
        sig = _stripe_sign(body, STRIPE_WEBHOOK_SECRET, ts)
        r = requests.post(f"{BASE}/api/stripe/webhook", data=body,
                          headers={"stripe-signature": sig,
                                   "Content-Type": "application/json"}, timeout=15)
        assert r.status_code == 200, f"webhook: {r.status_code} {r.text[:200]}"

        # Poll DB for eventual consistency
        for _ in range(10):
            tx = _get_transaction(sid)
            if tx.get("payment_status") == "paid":
                break
            time.sleep(0.3)
        assert tx.get("payment_status") == "paid", f"tx not marked paid: {tx}"

        # Fee status now paid
        adm = _login(*ADMIN)
        j = adm.get(f"{BASE}/api/grievances/{gid}/fee-status", timeout=15).json()
        assert j["fee"]["payment_status"] == "paid"
        assert j["fee"]["paid_at"]

        # Idempotent: second webhook call → still paid, no error
        ts2 = int(time.time())
        sig2 = _stripe_sign(body, STRIPE_WEBHOOK_SECRET, ts2)
        r2 = requests.post(f"{BASE}/api/stripe/webhook", data=body,
                           headers={"stripe-signature": sig2,
                                    "Content-Type": "application/json"}, timeout=15)
        assert r2.status_code == 200
        j2 = adm.get(f"{BASE}/api/grievances/{gid}/fee-status", timeout=15).json()
        assert j2["fee"]["payment_status"] == "paid"
