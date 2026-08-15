"""Iteration 25 tests: Employer Invoice Inbox, Billing setup, admin overdue
scan, Slack notify no-op safety, and marketplace shortlist CRUD split."""
import os
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"


def _session(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_sess():
    return _session("admin@talenthub.io", "Admin@2026")


@pytest.fixture(scope="session")
def support_sess():
    return _session("support1@jobatlas.io", "Support@2026")


@pytest.fixture(scope="session")
def emp_linked_sess():
    return _session("emp-series-b-fintechs@test.io", "Employer@2026")


@pytest.fixture(scope="session")
def talent_sess():
    return _session("talent@test.io", "Talent@2026")


# ---------- Employer Invoice Inbox ----------
class TestInvoiceInbox:
    def test_employer_inbox_shape(self, emp_linked_sess):
        r = emp_linked_sess.get(f"{API}/invoices/mine", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("items", "count", "total_open", "total_paid"):
            assert k in data, f"missing key {k}"
        assert isinstance(data["items"], list)
        assert isinstance(data["count"], int)
        assert isinstance(data["total_open"], (int, float))
        assert isinstance(data["total_paid"], (int, float))
        # verify enriched fields on at least one item if any
        if data["items"]:
            it = data["items"][0]
            for k in ("milestone_name", "milestone_due", "project_company",
                      "project_template", "is_overdue", "status", "amount"):
                assert k in it, f"missing enriched field {k}"

    def test_totals_math(self, emp_linked_sess):
        r = emp_linked_sess.get(f"{API}/invoices/mine", timeout=30)
        data = r.json()
        open_sum = sum(float(i.get("amount") or 0) for i in data["items"] if i.get("status") != "paid")
        paid_sum = sum(float(i.get("amount") or 0) for i in data["items"] if i.get("status") == "paid")
        assert abs(open_sum - data["total_open"]) < 0.5
        assert abs(paid_sum - data["total_paid"]) < 0.5

    def test_admin_sees_all(self, admin_sess, emp_linked_sess):
        r_admin = admin_sess.get(f"{API}/invoices/mine", timeout=30)
        r_emp = emp_linked_sess.get(f"{API}/invoices/mine", timeout=30)
        assert r_admin.status_code == 200
        assert r_admin.json()["count"] >= r_emp.json()["count"]

    def test_talent_gets_empty(self, talent_sess):
        r = talent_sess.get(f"{API}/invoices/mine", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 0
        assert d["items"] == []
        assert d["total_open"] == 0
        assert d["total_paid"] == 0


# ---------- Overdue detection ----------
class TestOverdueFlag:
    def test_overdue_flag_present_and_boolean(self, admin_sess):
        r = admin_sess.get(f"{API}/invoices/mine", timeout=30)
        assert r.status_code == 200
        for inv in r.json()["items"]:
            assert isinstance(inv["is_overdue"], bool)


# ---------- Billing setup ----------
class TestBilling:
    def test_talent_setup_forbidden(self, talent_sess):
        r = talent_sess.post(f"{API}/billing/setup",
                              json={"payment_method_id": "pm_bogus"}, timeout=30)
        assert r.status_code == 403

    def test_talent_status_forbidden(self, talent_sess):
        r = talent_sess.get(f"{API}/billing/status", timeout=30)
        assert r.status_code == 403

    def test_employer_status_no_card(self, emp_linked_sess):
        r = emp_linked_sess.get(f"{API}/billing/status", timeout=30)
        assert r.status_code == 200, r.text
        # Might have a card from a prior test run — accept either shape
        data = r.json()
        assert "attached" in data
        assert isinstance(data["attached"], bool)

    def test_employer_setup_bogus_pm_400(self, emp_linked_sess):
        r = emp_linked_sess.post(f"{API}/billing/setup",
                                  json={"payment_method_id": "pm_bogus_iter25"}, timeout=30)
        # Either 400 attach failed, or 500 if stripe not configured
        assert r.status_code in (400, 500), r.text
        if r.status_code == 400:
            body = r.text.lower()
            assert "attach failed" in body or "no such" in body or "invalid" in body


# ---------- Admin overdue scan ----------
class TestOverdueScan:
    def test_superadmin_scan_ok(self, admin_sess):
        r = admin_sess.post(f"{API}/admin/invoices/scan-overdue", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("scanned", "reminders_sent", "auto_collected", "failed"):
            assert k in d
            assert isinstance(d[k], int)

    def test_support_scope_forbidden(self, support_sess):
        r = support_sess.post(f"{API}/admin/invoices/scan-overdue", timeout=30)
        assert r.status_code == 403

    def test_talent_forbidden(self, talent_sess):
        r = talent_sess.post(f"{API}/admin/invoices/scan-overdue", timeout=30)
        assert r.status_code == 403

    def test_employer_forbidden(self, emp_linked_sess):
        r = emp_linked_sess.post(f"{API}/admin/invoices/scan-overdue", timeout=30)
        assert r.status_code == 403


# ---------- Slack notify no-op via variance breach ----------
class TestSlackNoOp:
    def test_variance_breach_still_returns_200(self, admin_sess):
        # Find any existing project (admin can see all)
        # Use invoices/mine to discover a project_id
        r = admin_sess.get(f"{API}/invoices/mine", timeout=30)
        items = r.json().get("items", [])
        if not items:
            pytest.skip("no seeded project to run variance against")
        pid = items[0]["project_id"]
        payload = {
            "week_start": "2026-01-05",
            "planned_hours": 100, "actual_hours": 125,   # +25% breach
            "planned_cost": 10000, "actual_cost": 12500,
            "notes": "iter25 slack-noop probe",
        }
        r2 = admin_sess.post(f"{API}/projects/workspace/{pid}/variances",
                              json=payload, timeout=30)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "variance" in body and "alert" in body


# ---------- Marketplace shortlist CRUD (moved to routes/marketplace.py) ----------
class TestShortlistExtracted:
    def test_shortlist_crud_flow(self, emp_linked_sess):
        tag = uuid.uuid4().hex[:8]
        talent_id = f"TEST_iter25_{tag}"
        payload = {
            "talent_id": talent_id,
            "talent_name": "Iter25 Test Talent",
            "headline": "Senior Dev",
            "location": "London",
            "hourly_rate": 95,
            "skills": ["React"],
            "context": "iter25 probe",
        }
        r = emp_linked_sess.post(f"{API}/shortlist", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        # LIST
        r2 = emp_linked_sess.get(f"{API}/shortlist", timeout=30)
        assert r2.status_code == 200
        ids = [i["talent_id"] for i in r2.json()["items"]]
        assert talent_id in ids
        # DELETE
        r3 = emp_linked_sess.delete(f"{API}/shortlist/{talent_id}", timeout=30)
        assert r3.status_code == 200
        assert r3.json()["ok"] is True
        # verify removed
        r4 = emp_linked_sess.get(f"{API}/shortlist", timeout=30)
        assert talent_id not in [i["talent_id"] for i in r4.json()["items"]]

    def test_shortlist_talent_forbidden(self, talent_sess):
        r = talent_sess.post(f"{API}/shortlist",
                              json={"talent_id": "x", "talent_name": "x"}, timeout=30)
        assert r.status_code == 403

    def test_shortlist_broadcast_still_present(self, emp_linked_sess):
        # Endpoint remains in server.py; empty shortlist -> 400 (not 404)
        # First clear anything created above; then broadcast
        r = emp_linked_sess.post(f"{API}/shortlist/broadcast",
                                  json={"message": "iter25 probe"}, timeout=30)
        # Depending on prior state, could be 200 (has shortlist) or 400 (empty).
        # Both indicate the endpoint is wired.
        assert r.status_code in (200, 400), r.text


# ---------- Previously-extracted marketplace endpoints still 200 ----------
class TestMarketplaceSplit:
    def test_seo_skills(self):
        r = requests.get(f"{API}/seo/skills", timeout=15)
        assert r.status_code == 200
        assert "skills" in r.json()

    def test_seo_city_skills(self):
        r = requests.get(f"{API}/seo/city-skills", timeout=15)
        assert r.status_code == 200
        assert "combos" in r.json()

    def test_sitemap_xml(self):
        r = requests.get(f"{API}/sitemap.xml", timeout=15)
        assert r.status_code == 200
        assert "<urlset" in r.text

    def test_marketplace_industries(self):
        r = requests.get(f"{API}/marketplace/industries", timeout=15)
        assert r.status_code == 200
        assert "industries" in r.json()

    def test_marketplace_stats(self):
        r = requests.get(f"{API}/marketplace/stats", timeout=15)
        assert r.status_code == 200
        assert "active_buyers" in r.json()


# ---------- server.py line count guard ----------
class TestServerLineCount:
    def test_server_py_below_2700(self):
        path = "/app/backend/server.py"
        with open(path) as f:
            n = sum(1 for _ in f)
        assert n < 2700, f"server.py is {n} lines (must be <2700)"
