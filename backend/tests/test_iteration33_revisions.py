"""Iteration 33 — Revision Workflow (request-revision, penalty ladder, dispute, admin rulings)."""
import os
import time
import uuid
import pytest
import requests
from pathlib import Path


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    fe = Path("/app/frontend/.env")
    if fe.exists():
        for line in fe.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _load_backend_url()
ADMIN = ("admin@talenthub.io", "Admin@2026")

# Read config from module so tests aren't hard-coded to 3/5/49
import sys
sys.path.insert(0, "/app/backend")
from routes.revisions import (
    REVIEW_FLAG_THRESHOLD, PENALTY_THRESHOLD, DISPUTE_FEE_USD, VISIBILITY_PENALTY,
    RATE_NUDGE_PENALTY_PCT, EMPLOYER_FLAG_TALENTS,
)


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(email, pw):
    s = _sess()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


def _register(role, extra_industry=None):
    tag = uuid.uuid4().hex[:8]
    email = f"TEST_i33_{role}_{tag}@test.io"
    pw = "Test@2026Aa"
    body = {"email": email, "password": pw, "name": f"TEST i33 {role} {tag}", "role": role}
    # NB: EMPLOYER_INDUSTRIES has changed between iterations; skip the field to
    # side-step the strict allowlist for test-only accounts.
    if False and role == "employer" and extra_industry:
        body["company_industry"] = extra_industry
    s = _sess()
    r = s.post(f"{BASE}/api/auth/register", json=body, timeout=20)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:300]}"
    return {"session": s, "email": email, "password": pw, "id": r.json()["id"]}


def _admin_grant_hours(user_id: str, hours: int):
    adm = _login(*ADMIN)
    r = adm.post(f"{BASE}/api/admin/users/{user_id}/adjust",
                 json={"hours_delta": hours, "reason": "iteration33 test seed"}, timeout=15)
    assert r.status_code == 200, f"grant hours failed: {r.status_code} {r.text[:300]}"


def _new_engagement_signed_with_deliverable(employer, talent, hours=10):
    """Employer creates engagement, both parties sign, talent submits deliverable.
    Returns (engagement_id, deliverable_id)."""
    e = employer["session"].post(f"{BASE}/api/engagements", json={
        "talent_id": talent["id"], "hours": hours,
        "scope": "TEST i33 revision workflow scope",
        "mode": "remote", "location": "",
    }, timeout=15)
    assert e.status_code == 200, f"create engagement: {e.status_code} {e.text[:300]}"
    eid = e.json()["id"]
    # Employer signs
    r1 = employer["session"].post(f"{BASE}/api/engagements/sign",
                                   json={"engagement_id": eid, "signature": "Emp Sig", "onsite_ack": False},
                                   timeout=15)
    assert r1.status_code == 200, r1.text[:300]
    # Talent signs
    r2 = talent["session"].post(f"{BASE}/api/engagements/sign",
                                 json={"engagement_id": eid, "signature": "Tal Sig", "onsite_ack": False},
                                 timeout=15)
    assert r2.status_code == 200, r2.text[:300]
    assert r2.json()["status"] == "contract_signed"
    # Talent submits deliverable
    d = talent["session"].post(f"{BASE}/api/deliverables", json={
        "engagement_id": eid, "title": "TEST i33 deliverable",
        "description": "initial submission for revision test",
        "link": "https://example.com/v1", "hours_claimed": 1.0,
    }, timeout=15)
    assert d.status_code == 200, d.text[:300]
    return eid, d.json()["id"]


# ---------- Shared employer + talent fixtures (module scope) ----------

@pytest.fixture(scope="module")
def employer_A():
    emp = _register("employer", extra_industry="Series-B fintechs")
    # Grant plenty of hours for many engagements
    _admin_grant_hours(emp["id"], 500)
    return emp


@pytest.fixture(scope="module")
def talent_A():
    return _register("talent")


@pytest.fixture(scope="module")
def flow_A(employer_A, talent_A):
    """Freshly signed engagement + submitted deliverable for the happy-path tests."""
    eid, did = _new_engagement_signed_with_deliverable(employer_A, talent_A)
    return {"engagement_id": eid, "deliverable_id": did}


# ==============================================================================
#  Validation tests
# ==============================================================================

class TestRequestRevisionValidation:
    def test_short_justification_returns_422(self, employer_A, flow_A):
        r = employer_A["session"].post(
            f"{BASE}/api/deliverables/{flow_A['deliverable_id']}/request-revision",
            json={"justification": "too short", "priority": "minor"}, timeout=15)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text[:200]}"

    def test_priority_invalid_returns_400(self, employer_A, flow_A):
        r = employer_A["session"].post(
            f"{BASE}/api/deliverables/{flow_A['deliverable_id']}/request-revision",
            json={"justification": "This justification is definitely more than twenty chars long.",
                  "priority": "urgent"}, timeout=15)
        assert r.status_code == 400
        assert "priority" in r.text.lower()

    def test_non_employer_forbidden(self, talent_A, flow_A):
        r = talent_A["session"].post(
            f"{BASE}/api/deliverables/{flow_A['deliverable_id']}/request-revision",
            json={"justification": "This justification is definitely more than twenty chars long.",
                  "priority": "minor"}, timeout=15)
        assert r.status_code == 403


# ==============================================================================
#  Full penalty ladder on ONE deliverable + dispute
# ==============================================================================

class TestPenaltyLadder:
    """Drives revision_count from 0 -> PENALTY_THRESHOLD on a single deliverable
    and validates flag/score updates + dispute availability."""

    @pytest.fixture(scope="class")
    def ladder(self, employer_A, talent_A):
        eid, did = _new_engagement_signed_with_deliverable(employer_A, talent_A)
        return {"emp": employer_A, "tal": talent_A,
                "engagement_id": eid, "deliverable_id": did}

    def _request_revision(self, ladder, n):
        return ladder["emp"]["session"].post(
            f"{BASE}/api/deliverables/{ladder['deliverable_id']}/request-revision",
            json={"justification": f"Revision #{n} — need clearer explanation and updated tests.",
                  "priority": "major"}, timeout=15)

    def _resubmit(self, ladder, n):
        return ladder["tal"]["session"].post(
            f"{BASE}/api/deliverables/{ladder['deliverable_id']}/resubmit",
            json={"link": f"https://example.com/v{n+1}", "hours_claimed": 1.0,
                  "notes": f"resubmission #{n}"}, timeout=15)

    def test_first_revision_ok(self, ladder):
        r = self._request_revision(ladder, 1)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["revision_count"] == 1
        assert j["penalty_triggered"] is False
        assert j["dispute_available"] is False

    def test_second_revision_after_resubmit(self, ladder):
        r0 = self._resubmit(ladder, 1)
        assert r0.status_code == 200, r0.text[:300]
        r = self._request_revision(ladder, 2)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["revision_count"] == 2

    def test_cannot_request_when_not_submitted(self, ladder):
        # deliverable is currently in state 'revision_requested' (already open cycle)
        r = self._request_revision(ladder, 99)
        assert r.status_code == 400
        assert "submit" in r.text.lower() or "resubmit" in r.text.lower()

    def test_third_revision_triggers_under_review(self, ladder):
        self._resubmit(ladder, 2)
        r = self._request_revision(ladder, 3)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["revision_count"] == REVIEW_FLAG_THRESHOLD
        assert j["penalty_triggered"] is True
        assert j["dispute_available"] is False
        # Check talent profile
        adm = _login(*ADMIN)
        me = adm.get(f"{BASE}/api/talent/{ladder['tal']['id']}", timeout=15).json()
        prof = me.get("profile") or {}
        assert prof.get("under_review") is True
        flags = prof.get("revision_flags") or []
        assert any(f.get("level") == "under_review"
                   and f.get("deliverable_id") == ladder["deliverable_id"] for f in flags)

    def test_fifth_revision_triggers_excessive(self, ladder):
        # 4th
        self._resubmit(ladder, 3)
        r4 = self._request_revision(ladder, 4)
        assert r4.status_code == 200, r4.text[:300]
        # 5th
        self._resubmit(ladder, 4)
        r5 = self._request_revision(ladder, 5)
        assert r5.status_code == 200, r5.text[:300]
        j = r5.json()
        assert j["revision_count"] == PENALTY_THRESHOLD
        assert j["dispute_available"] is True

        # Talent profile mutations
        adm = _login(*ADMIN)
        me = adm.get(f"{BASE}/api/talent/{ladder['tal']['id']}", timeout=15).json()
        prof = me.get("profile") or {}
        assert prof.get("excessive_revisions") is True
        assert prof.get("under_review") is True
        assert int(prof.get("visibility_score") or 100) == 100 - VISIBILITY_PENALTY
        assert float(prof.get("rate_bias_pct") or 0) == -RATE_NUDGE_PENALTY_PCT

    def test_talent_list_demotes_and_revokes_trusted(self, ladder):
        """After 5th revision, /api/talent should show excessive_revisions=true,
        is_trusted_partner=false, and the affected talent must appear at bottom."""
        r = requests.get(f"{BASE}/api/talent", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        ids = [u["id"] for u in rows]
        assert ladder["tal"]["id"] in ids, "talent missing from list"
        row = next(u for u in rows if u["id"] == ladder["tal"]["id"])
        assert row.get("excessive_revisions") is True
        assert row.get("is_trusted_partner") is False
        # Position: excessive_revisions rows sink to bottom. Check no non-excessive
        # row appears AFTER our talent.
        idx = ids.index(ladder["tal"]["id"])
        for later in rows[idx + 1:]:
            assert later.get("excessive_revisions") is True, \
                f"non-excessive talent {later.get('id')} ranked below excessive one"

    def test_revisions_thread_visibility(self, ladder):
        """GET /revisions is visible to employer + talent + admin, forbidden to others."""
        # Employer
        r_e = ladder["emp"]["session"].get(
            f"{BASE}/api/deliverables/{ladder['deliverable_id']}/revisions", timeout=15)
        assert r_e.status_code == 200
        body = r_e.json()
        assert body["dispute_available"] is True
        assert body["dispute_fee_usd"] == DISPUTE_FEE_USD
        assert body["revision_count"] == PENALTY_THRESHOLD
        assert len(body["items"]) == PENALTY_THRESHOLD

        # Talent
        r_t = ladder["tal"]["session"].get(
            f"{BASE}/api/deliverables/{ladder['deliverable_id']}/revisions", timeout=15)
        assert r_t.status_code == 200

        # Admin (moderation scope via superadmin)
        adm = _login(*ADMIN)
        r_a = adm.get(f"{BASE}/api/deliverables/{ladder['deliverable_id']}/revisions", timeout=15)
        assert r_a.status_code == 200

        # An unrelated user should get 403
        stranger = _register("talent")
        r_x = stranger["session"].get(
            f"{BASE}/api/deliverables/{ladder['deliverable_id']}/revisions", timeout=15)
        assert r_x.status_code == 403


# ==============================================================================
#  Dispute flow + admin ruling
# ==============================================================================

class TestDisputeAndRuling:

    @pytest.fixture(scope="class")
    def ladder_disp(self, employer_A):
        """Freshly signed engagement + deliverable driven to 5 revisions."""
        talent = _register("talent")
        eid, did = _new_engagement_signed_with_deliverable(employer_A, talent)
        for n in range(1, PENALTY_THRESHOLD + 1):
            r = employer_A["session"].post(
                f"{BASE}/api/deliverables/{did}/request-revision",
                json={"justification": f"Rev {n}: substantive re-work please, thanks.",
                      "priority": "major"}, timeout=15)
            assert r.status_code == 200, r.text[:200]
            if n < PENALTY_THRESHOLD:
                r2 = talent["session"].post(
                    f"{BASE}/api/deliverables/{did}/resubmit",
                    json={"link": f"https://x/v{n}", "hours_claimed": 1.0}, timeout=15)
                assert r2.status_code == 200, r2.text[:200]
        return {"emp": employer_A, "tal": talent,
                "engagement_id": eid, "deliverable_id": did}

    def test_dispute_before_threshold_forbidden(self, employer_A):
        """<PENALTY_THRESHOLD revisions → 400."""
        talent = _register("talent")
        eid, did = _new_engagement_signed_with_deliverable(employer_A, talent)
        r = talent["session"].post(f"{BASE}/api/deliverables/{did}/dispute",
                                    json={"reason": "I feel wronged for many reasons here."},
                                    timeout=15)
        assert r.status_code == 400

    def test_dispute_creates_grievance(self, ladder_disp):
        r = ladder_disp["tal"]["session"].post(
            f"{BASE}/api/deliverables/{ladder_disp['deliverable_id']}/dispute",
            json={"reason": "Employer is nitpicking; requesting arbitration please."}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        g = r.json()["grievance"]
        assert g["kind"] == "revision_dispute"
        assert g["dispute_fee"]["amount_usd"] == DISPUTE_FEE_USD
        assert g["dispute_fee"]["status"] == "pending"
        assert len(g["revision_thread"]) == PENALTY_THRESHOLD
        # store for downstream tests
        ladder_disp["grievance_id"] = g["id"]

    def test_second_dispute_blocked(self, ladder_disp):
        r = ladder_disp["tal"]["session"].post(
            f"{BASE}/api/deliverables/{ladder_disp['deliverable_id']}/dispute",
            json={"reason": "Trying again — this second dispute must be rejected!"}, timeout=15)
        assert r.status_code == 400

    def test_admin_revisions_index(self, ladder_disp):
        adm = _login(*ADMIN)
        r = adm.get(f"{BASE}/api/admin/revisions", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "revisions" in j and "disputes" in j and "counts" in j
        assert any(d.get("deliverable_id") == ladder_disp["deliverable_id"]
                   for d in j["disputes"])

    def test_admin_revisions_non_admin_forbidden(self, ladder_disp):
        r = ladder_disp["tal"]["session"].get(f"{BASE}/api/admin/revisions", timeout=15)
        assert r.status_code == 403

    def test_admin_rules_for_talent_reverts_penalty(self, ladder_disp):
        adm = _login(*ADMIN)
        # find the grievance id (freshly)
        idx = adm.get(f"{BASE}/api/admin/revisions", timeout=15).json()
        gid = next(d["id"] for d in idx["disputes"]
                   if d["deliverable_id"] == ladder_disp["deliverable_id"])
        r = adm.post(f"{BASE}/api/admin/revisions/{gid}/rule",
                     json={"ruling": "talent", "notes": "Employer scope-creeping across cycles."},
                     timeout=15)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["fee_status"] == "owed_by_employer"
        assert j["fee_usd"] == DISPUTE_FEE_USD

        # Talent penalties should lift
        me = adm.get(f"{BASE}/api/talent/{ladder_disp['tal']['id']}", timeout=15).json()
        prof = me.get("profile") or {}
        assert prof.get("excessive_revisions") is False
        assert int(prof.get("visibility_score") or 0) == 100
        assert float(prof.get("rate_bias_pct") or 0) == 0


# ==============================================================================
#  Employer abuse-flag guardrail
# ==============================================================================

class TestEmployerAbuseFlag:
    """Same employer drives ≥5 revisions on ≥EMPLOYER_FLAG_TALENTS distinct talents."""

    def test_employer_flagged_after_threshold(self):
        emp = _register("employer", extra_industry="Series-B fintechs")
        _admin_grant_hours(emp["id"], 500)
        for _ in range(EMPLOYER_FLAG_TALENTS):
            tal = _register("talent")
            _, did = _new_engagement_signed_with_deliverable(emp, tal)
            for n in range(1, PENALTY_THRESHOLD + 1):
                rr = emp["session"].post(
                    f"{BASE}/api/deliverables/{did}/request-revision",
                    json={"justification": f"Abuse-flag test rev {n}, more polish please.",
                          "priority": "minor"}, timeout=15)
                assert rr.status_code == 200, rr.text[:200]
                if n < PENALTY_THRESHOLD:
                    rs = tal["session"].post(
                        f"{BASE}/api/deliverables/{did}/resubmit",
                        json={"link": f"https://x/v{n}", "hours_claimed": 1.0}, timeout=15)
                    assert rs.status_code == 200
        # After enough talents crossed threshold, employer should be flagged
        adm = _login(*ADMIN)
        r = adm.get(f"{BASE}/api/admin/employers-flagged", timeout=15)
        assert r.status_code == 200
        j = r.json()
        ids = [u["id"] for u in j["items"]]
        assert emp["id"] in ids, f"employer {emp['id']} not in flagged list: {ids}"
        # Non-admin forbidden
        tal = _register("talent")
        r2 = tal["session"].get(f"{BASE}/api/admin/employers-flagged", timeout=15)
        assert r2.status_code == 403


# ==============================================================================
#  Resubmit → status transition
# ==============================================================================

class TestResubmitTransition:
    def test_resubmit_moves_deliverable_and_stamps_revision(self, employer_A):
        talent = _register("talent")
        _, did = _new_engagement_signed_with_deliverable(employer_A, talent)
        r = employer_A["session"].post(
            f"{BASE}/api/deliverables/{did}/request-revision",
            json={"justification": "Please tighten the copy and add unit tests.", "priority": "minor"},
            timeout=15)
        assert r.status_code == 200
        rev_id = r.json()["revision"]["id"]

        # Talent resubmits
        rs = talent["session"].post(f"{BASE}/api/deliverables/{did}/resubmit",
                                    json={"link": "https://x/v2", "hours_claimed": 2.5,
                                          "notes": "Fixed copy, added tests."}, timeout=15)
        assert rs.status_code == 200

        # Revisions endpoint should show the latest revision stamped resubmitted
        rev = employer_A["session"].get(f"{BASE}/api/deliverables/{did}/revisions",
                                         timeout=15).json()
        item = next(x for x in rev["items"] if x["id"] == rev_id)
        assert item["status"] == "resubmitted"
        assert item["resubmit_link"] == "https://x/v2"
        assert float(item["resubmit_hours"]) == 2.5
        assert item["resubmit_notes"] == "Fixed copy, added tests."
