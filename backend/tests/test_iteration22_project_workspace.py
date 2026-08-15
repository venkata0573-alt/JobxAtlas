"""Iteration 22 — Project Workspace + Milestone Billing backend tests.

Covers:
- POST /api/projects/lead (public)
- POST /api/admin/project-leads/{lead_id}/convert  (superadmin only)
- Idempotency guard on convert
- Support scope permitted on GET /api/admin/project-leads but blocked on convert
- GET /api/projects/workspace/{id}
- Phase progression (PATCH)
- Variance snapshot
- Risk register (POST + PATCH, validation)
- RACI matrix (silent stripping of invalid letters)
- Milestone billing: auto-generated, invoice, paid, custom milestone
- Access control on talent + wrong-employer
- Rollups after variance + first milestone paid
"""
import os
import pytest
import requests
from pathlib import Path

def _load_frontend_env():
    p = Path("/app/frontend/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")
API = BASE_URL + "/api"

ADMIN = ("admin@talenthub.io", "Admin@2026")
SUPPORT = ("support1@jobatlas.io", "Support@2026")
TALENT = ("talent@test.io", "Talent@2026")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def support_session():
    return _login(*SUPPORT)


@pytest.fixture(scope="module")
def talent_session():
    return _login(*TALENT)


@pytest.fixture(scope="module")
def lead_id():
    """Create a fresh public lead with $300k total budget."""
    payload = {
        "template_id": "fintech-kyc-aml",
        "company_name": "TEST_WorkspaceCo",
        "contact_name": "Test Contact",
        "contact_email": "test_workspace@example.com",
        "duration_months": 6,
        "notes": "iteration 22 test",
        "estimated_monthly_cost": 50000,
        "estimated_total_cost": 300000,
        "assigned_team": [
            {"role": "Program Manager", "seat_index": 1, "talent_id": "c-a",
             "talent_name": "Rosie", "rate": 140, "locked": True},
            {"role": "Senior Engineer", "seat_index": 1, "talent_id": "c-b",
             "talent_name": "Ben", "rate": 120, "locked": False},
        ],
    }
    r = requests.post(f"{API}/projects/lead", json=payload, timeout=15)
    assert r.status_code == 200, f"lead create failed: {r.status_code} {r.text}"
    lid = r.json()["id"]
    assert lid
    return lid


# --- Access control on GET /admin/project-leads ---
class TestListLeadsScopes:
    def test_admin_can_list(self, admin_session):
        r = admin_session.get(f"{API}/admin/project-leads", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)

    def test_support_can_list(self, support_session):
        r = support_session.get(f"{API}/admin/project-leads", timeout=15)
        assert r.status_code == 200, r.text

    def test_talent_cannot_list(self, talent_session):
        r = talent_session.get(f"{API}/admin/project-leads", timeout=15)
        assert r.status_code == 403


# --- Convert lead ---
class TestConvertLead:
    def test_support_cannot_convert(self, support_session, lead_id):
        r = support_session.post(f"{API}/admin/project-leads/{lead_id}/convert",
                                 json={"currency": "usd"}, timeout=15)
        assert r.status_code == 403, r.text

    def test_superadmin_converts(self, admin_session, lead_id, request):
        r = admin_session.post(f"{API}/admin/project-leads/{lead_id}/convert",
                               json={"currency": "usd"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        project = data["project"]
        assert project["status"] == "active"
        assert project["currency"] == "usd"
        assert len(project["phases"]) == 5
        expected_ids = ["initiate", "plan", "execute", "monitor", "close"]
        assert [p["id"] for p in project["phases"]] == expected_ids
        assert project["phases"][0]["status"] == "in_progress"
        for p in project["phases"][1:]:
            assert p["status"] == "not_started"
        # RACI seeded from assigned_team: 5 rows
        assert len(project["raci"]) == 5
        # Stash project_id for other tests
        request.config.cache.set("project_id", project["id"])

    def test_idempotent(self, admin_session, lead_id):
        r = admin_session.post(f"{API}/admin/project-leads/{lead_id}/convert",
                               json={"currency": "usd"}, timeout=15)
        assert r.status_code == 400

    def test_lead_marked_converted(self, admin_session, lead_id):
        r = admin_session.get(f"{API}/admin/project-leads", timeout=15)
        items = r.json()["items"]
        my = next((x for x in items if x["id"] == lead_id), None)
        assert my is not None
        assert my["status"] == "converted"
        assert my.get("converted_project_id")


@pytest.fixture(scope="module")
def project_id(admin_session, lead_id, request):
    pid = request.config.cache.get("project_id", None)
    if pid:
        return pid
    # fallback: query
    r = admin_session.get(f"{API}/projects/mine", timeout=15)
    for p in r.json().get("items", []):
        if p.get("lead_id") == lead_id:
            return p["id"]
    pytest.fail("Could not determine converted project id")


# --- Workspace GET ---
class TestWorkspaceGet:
    def test_get_workspace(self, admin_session, project_id):
        r = admin_session.get(f"{API}/projects/workspace/{project_id}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for k in ("project", "variances", "risks", "milestones", "invoices", "rollups"):
            assert k in data, f"missing key {k}"
        # Auto-generated 4 milestones (may have extra custom ones added by later tests)
        auto = [m for m in data["milestones"]
                if m["name"] in ("Kickoff", "Phase 1 Delivery", "Phase 2 Delivery", "Final Sign-off")]
        assert len(auto) == 4
        for m in auto:
            assert m["amount"] == 75000  # 25% of 300k
        assert data["rollups"]["total_budget"] == 300000

    def test_talent_cannot_view(self, talent_session, project_id):
        r = talent_session.get(f"{API}/projects/workspace/{project_id}", timeout=15)
        assert r.status_code == 403

    def test_wrong_employer_cannot_view(self, project_id):
        # Login as an unrelated employer (from seed)
        s = _login("emp-series-b-fintechs@test.io", "Employer@2026")
        r = s.get(f"{API}/projects/workspace/{project_id}", timeout=15)
        assert r.status_code == 403


# --- Phase progression ---
class TestPhases:
    def test_bad_status(self, admin_session, project_id):
        r = admin_session.patch(f"{API}/projects/workspace/{project_id}/phases/initiate",
                                json={"status": "foo"}, timeout=15)
        assert r.status_code == 400

    def test_unknown_phase(self, admin_session, project_id):
        r = admin_session.patch(f"{API}/projects/workspace/{project_id}/phases/nope",
                                json={"status": "complete"}, timeout=15)
        assert r.status_code == 404

    def test_complete_initiate(self, admin_session, project_id):
        r = admin_session.patch(f"{API}/projects/workspace/{project_id}/phases/initiate",
                                json={"status": "complete"}, timeout=15)
        assert r.status_code == 200
        phases = r.json()["phases"]
        ph = next(p for p in phases if p["id"] == "initiate")
        assert ph["status"] == "complete"
        assert ph["completed_at"]
        assert ph["signed_off_by"]  # fallback to user name/email


# --- Variance ---
class TestVariance:
    def test_variance_math(self, admin_session, project_id):
        r = admin_session.post(f"{API}/projects/workspace/{project_id}/variances", json={
            "week_start": "2026-01-05",
            "planned_hours": 320, "actual_hours": 340,
            "planned_cost": 50000, "actual_cost": 52000,
            "notes": "TEST_variance",
        }, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["hours_variance_pct"] == 6.2
        assert d["cost_variance_pct"] == 4.0


# --- Risks ---
class TestRisks:
    def test_low_low(self, admin_session, project_id):
        r = admin_session.post(f"{API}/projects/workspace/{project_id}/risks",
                               json={"title": "TEST_low", "likelihood": "L", "impact": "L"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["score"] == 1

    def test_high_high(self, admin_session, project_id, request):
        r = admin_session.post(f"{API}/projects/workspace/{project_id}/risks",
                               json={"title": "TEST_high", "likelihood": "H", "impact": "H",
                                     "owner": "Rosie"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["score"] == 9
        request.config.cache.set("risk_id", data["id"])

    def test_bad_likelihood(self, admin_session, project_id):
        r = admin_session.post(f"{API}/projects/workspace/{project_id}/risks",
                               json={"title": "bad", "likelihood": "X", "impact": "M"}, timeout=15)
        assert r.status_code == 400

    def test_patch_risk(self, admin_session, project_id, request):
        rid = request.config.cache.get("risk_id", None)
        assert rid, "no risk_id cached"
        r = admin_session.patch(f"{API}/projects/workspace/{project_id}/risks/{rid}",
                                json={"title": "TEST_high", "likelihood": "H", "impact": "H",
                                      "status": "mitigated", "owner": "Rosie"}, timeout=15)
        assert r.status_code == 200


# --- RACI ---
class TestRaci:
    def test_stripping(self, admin_session, project_id):
        rows = [{"activity": "Charter approval",
                 "assignments": {"Rosie": "A", "Ben": "R", "Rando": "Z", "Bad": "XX"}}]
        r = admin_session.put(f"{API}/projects/workspace/{project_id}/raci",
                              json={"rows": rows}, timeout=15)
        assert r.status_code == 200, r.text
        out = r.json()["raci"][0]["assignments"]
        assert out == {"Rosie": "A", "Ben": "R"}  # Z and XX stripped


# --- Milestones + Invoicing ---
class TestMilestones:
    def test_invoice_first(self, admin_session, project_id, request):
        w = admin_session.get(f"{API}/projects/workspace/{project_id}", timeout=15).json()
        first = next(m for m in w["milestones"] if m["name"] == "Kickoff")
        r = admin_session.post(
            f"{API}/projects/workspace/{project_id}/milestones/{first['id']}/invoice",
            timeout=15)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["ref"].startswith("INV-")
        assert inv["amount"] == 75000
        request.config.cache.set("kickoff_id", first["id"])

    def test_invoice_twice_fails(self, admin_session, project_id, request):
        mid = request.config.cache.get("kickoff_id", None)
        r = admin_session.post(
            f"{API}/projects/workspace/{project_id}/milestones/{mid}/invoice", timeout=15)
        assert r.status_code == 400

    def test_mark_paid(self, admin_session, project_id, request):
        mid = request.config.cache.get("kickoff_id", None)
        r = admin_session.post(
            f"{API}/projects/workspace/{project_id}/milestones/{mid}/paid", timeout=15)
        assert r.status_code == 200
        # Verify persisted
        w = admin_session.get(f"{API}/projects/workspace/{project_id}", timeout=15).json()
        m = next(x for x in w["milestones"] if x["id"] == mid)
        assert m["status"] == "paid"
        inv = next((i for i in w["invoices"] if i["milestone_id"] == mid), None)
        assert inv and inv["status"] == "paid"

    def test_custom_milestone_from_percent(self, admin_session, project_id):
        r = admin_session.post(f"{API}/projects/workspace/{project_id}/milestones", json={
            "name": "TEST_extra", "percent": 10, "due_date": "2026-06-01",
        }, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount"] == 30000  # 10% of 300k
        assert d["status"] == "pending"


# --- Rollups ---
class TestRollups:
    def test_rollups(self, admin_session, project_id):
        w = admin_session.get(f"{API}/projects/workspace/{project_id}", timeout=15).json()
        r = w["rollups"]
        assert r["paid"] == 75000
        assert r["billed"] >= 75000
        assert r["cost_variance_pct"] == 4.0
        assert r["total_budget"] == 300000
