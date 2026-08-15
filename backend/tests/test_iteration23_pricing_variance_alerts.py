"""Iteration 23 tests: pricing engine, /pricing endpoints, employer workspace
linking via convert, /projects/mine, /alerts + variance-breach auto-alert."""
import os
import time
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _session(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_token():
    return _session("admin@talenthub.io", "Admin@2026")


@pytest.fixture(scope="session")
def emp_linked_token():
    return _session("emp-series-b-fintechs@test.io", "Employer@2026")


@pytest.fixture(scope="session")
def emp_control_token():
    return _session("emp-health-tech-scale-ups@test.io", "Employer@2026")


@pytest.fixture(scope="session")
def talent_token():
    return _session("talent@test.io", "Talent@2026")


def _h(sess):
    return {}  # cookies carry auth


# ---------- Pricing ----------
class TestPricingTiers:
    def test_tiers(self):
        r = requests.get(f"{API}/pricing/tiers", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["min_margin_floor_pct"] == 10
        tiers = d["margin_tiers"]
        assert len(tiers) == 5
        labels = [t["label"] for t in tiers]
        assert "Entry" in labels and "Mid" in labels and "Senior" in labels and "Principal" in labels
        mp = {t["label"]: t["margin_pct"] for t in tiers}
        assert mp["Entry"] == 20 and mp["Mid"] == 18 and mp["Senior"] == 15 and mp["Principal"] == 12
        # Top tier = 10
        top = [t for t in tiers if t["label"] not in ("Entry", "Mid", "Senior", "Principal")][0]
        assert top["margin_pct"] == 10


class TestPricingQuote:
    def test_quote_math(self):
        payload = {"seats": [{"rate": 180}, {"rate": 45}, {"rate": 90}], "months": 6}
        r = requests.post(f"{API}/pricing/quote", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # 3 seats * 160h = 480h/mo -> 320+ bucket -> 2% discount
        assert d["volume_discount_pct"] == 2.0
        # per-seat effective margins after discount
        # $180 principal 12 -> max(10, 12-2)=10 -> sell = 180*1.10 = 198
        # $45 entry 20 -> 18 -> sell = 45*1.18 = 53.10
        # $90 mid 18 -> 16 -> sell = 90*1.16 = 104.40
        seats = {s["talent_rate"]: s for s in d["breakdown"]}
        assert seats[180.0]["effective_margin_pct"] == 10
        assert seats[180.0]["sell_rate"] == 198.0
        assert seats[45.0]["effective_margin_pct"] == 18
        assert abs(seats[45.0]["sell_rate"] - 53.1) < 0.01
        assert seats[90.0]["effective_margin_pct"] == 16
        assert abs(seats[90.0]["sell_rate"] - 104.4) < 0.01
        # blended margin
        assert d["blended_margin_pct"] > 0
        # totals sanity: monthly_client_price > monthly_talent_cost
        assert d["monthly_client_price"] > d["monthly_talent_cost"]


# ---------- Template pricing surface ----------
class TestTemplatePricing:
    def test_template_detail_has_margin_fields(self, admin_token):
        r = requests.get(f"{API}/projects/templates/fintech-kyc-aml", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("monthly_client_price", "monthly_talent_cost", "total_client_price",
                  "total_talent_cost", "total_margin", "blended_margin_pct", "pricing_tiers"):
            assert k in d, f"missing {k}"
            if k != "pricing_tiers":
                assert d[k] >= 0

    def test_team_suggestions_have_sell_rate(self, admin_token):
        r = admin_token.get(f"{API}/projects/templates/fintech-kyc-aml/team-suggestions", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # Should be a dict with slots/suggested_talent
        # Structure: iterate all suggested talent entries
        found_any = False
        # Handle common shapes
        items = d.get("seats") or []
        for slot in items:
            cand = slot.get("suggested_talent")
            if cand:
                assert "sell_rate" in cand and "margin_pct" in cand
                found_any = True
        assert found_any, "no suggested_talent with sell_rate found"


# ---------- Lead + convert flow ----------
@pytest.fixture(scope="session")
def created_lead():
    tag = uuid.uuid4().hex[:6]
    payload = {
        "template_id": "fintech-kyc-aml",
        "company_name": f"TEST_Series-B FinCo {tag}",
        "contact_name": "Test Sponsor",
        "contact_email": "emp-series-b-fintechs@test.io",
        "duration_months": 6,
        "notes": "iteration 23 test",
        "assigned_team": [{"role": "PM", "seat_index": 1, "talent_name": "Rosie", "rate": 140}],
    }
    r = requests.post(f"{API}/projects/lead", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


class TestLeadPricing:
    def test_lead_quote_is_server_computed(self, created_lead):
        q = created_lead["quote"]
        # Senior tier @ $140/hr -> 15%. Single seat = 160h/mo -> no volume discount.
        # sell_rate = 140 * 1.15 = 161
        # monthly_client_price = 161 * 160 = 25760
        # total_client_price = 25760 * 6 = 154560
        assert q["monthly_client_price"] == 25760.0
        assert q["total_client_price"] == 154560.0
        assert q["blended_margin_pct"] == 15.0


@pytest.fixture(scope="session")
def converted_project(admin_token, created_lead):
    lead_id = created_lead["id"]
    r = admin_token.post(f"{API}/admin/project-leads/{lead_id}/convert", json={"currency": "usd"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["project"]


class TestConvertFlow:
    def test_project_carries_margin_fields(self, converted_project):
        p = converted_project
        assert p["total_budget"] == 154560.0
        assert p["blended_margin_pct"] == 15.0
        assert p["total_talent_cost"] > 0
        assert p["total_margin"] > 0

    def test_project_auto_linked_to_employer(self, converted_project, emp_linked_token):
        # confirm via /projects/mine
        r = emp_linked_token.get(f"{API}/projects/mine", timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["items"]]
        assert converted_project["id"] in ids
        assert converted_project["employer_id"] is not None

    def test_milestones_auto_generated(self, admin_token, converted_project):
        r = admin_token.get(f"{API}/projects/workspace/{converted_project['id']}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        ms = d["milestones"]
        assert len(ms) == 4
        for m in ms:
            assert abs(m["amount"] - 154560.0 * 0.25) < 1


# ---------- /projects/mine access ----------
class TestProjectsMine:
    def test_control_employer_sees_zero_of_this_project(self, emp_control_token, converted_project):
        r = emp_control_token.get(f"{API}/projects/mine", timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["items"]]
        assert converted_project["id"] not in ids

    def test_talent_gets_none(self, talent_token):
        r = talent_token.get(f"{API}/projects/mine", timeout=15)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_admin_sees_all(self, admin_token, converted_project):
        r = admin_token.get(f"{API}/projects/mine", timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["items"]]
        assert converted_project["id"] in ids


# ---------- Workspace access ----------
class TestWorkspaceAccess:
    def test_linked_employer_ok(self, emp_linked_token, converted_project):
        r = emp_linked_token.get(f"{API}/projects/workspace/{converted_project['id']}", timeout=15)
        assert r.status_code == 200

    def test_other_employer_forbidden(self, emp_control_token, converted_project):
        r = emp_control_token.get(f"{API}/projects/workspace/{converted_project['id']}", timeout=15)
        assert r.status_code == 403


# ---------- Variance alerts ----------
class TestVarianceAlerts:
    def test_breach_creates_alert(self, emp_linked_token, converted_project):
        pid = converted_project["id"]
        r = emp_linked_token.post(f"{API}/projects/workspace/{pid}/variances",
                           json={"week_start": "2026-01-05", "planned_hours": 100,
                                 "actual_hours": 125, "planned_cost": 10000,
                                 "actual_cost": 12500, "notes": "iter23 breach"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["alert"] is not None
        assert d["alert"]["severity"] == "high"
        assert d["alert"]["kind"] == "variance_breach"

    def test_no_breach_no_alert(self, emp_linked_token, converted_project):
        pid = converted_project["id"]
        r = emp_linked_token.post(f"{API}/projects/workspace/{pid}/variances",
                           json={"week_start": "2026-01-12", "planned_hours": 100,
                                 "actual_hours": 100, "planned_cost": 10000,
                                 "actual_cost": 10000, "notes": "flat"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["alert"] is None

    def test_alerts_mine_linked_employer(self, emp_linked_token, converted_project):
        r = emp_linked_token.get(f"{API}/alerts/mine", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 1
        assert d["unread"] >= 1
        for a in d["items"]:
            assert a["employer_id"] is not None

    def test_alerts_mine_talent_empty(self, talent_token):
        r = talent_token.get(f"{API}/alerts/mine", timeout=15)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_alerts_mine_admin_sees_all(self, admin_token):
        r = admin_token.get(f"{API}/alerts/mine", timeout=15)
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_mark_read_by_employer(self, emp_linked_token):
        r = emp_linked_token.get(f"{API}/alerts/mine", timeout=15)
        alert_id = r.json()["items"][0]["id"]
        r2 = emp_linked_token.post(f"{API}/alerts/{alert_id}/read", timeout=15)
        assert r2.status_code == 200

    def test_mark_read_talent_forbidden(self, emp_linked_token, talent_token):
        r = emp_linked_token.get(f"{API}/alerts/mine", timeout=15)
        items = r.json()["items"]
        if not items:
            pytest.skip("no alerts")
        alert_id = items[0]["id"]
        r2 = talent_token.post(f"{API}/alerts/{alert_id}/read", timeout=15)
        assert r2.status_code == 403
