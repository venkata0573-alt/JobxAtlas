"""Backend integration tests for TalentHub API."""
import io
import os
import uuid
import time
import pytest
import requests
from openpyxl import Workbook

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

TALENT_EMAIL = f"test_talent_{uuid.uuid4().hex[:8]}@test.io"
EMPLOYER_EMAIL = f"test_employer_{uuid.uuid4().hex[:8]}@test.io"
PW = "P@ssw0rd123"

@pytest.fixture(scope="module")
def talent_sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={"email": TALENT_EMAIL, "password": PW, "name": "Test Talent", "role": "talent"})
    assert r.status_code == 200, r.text
    return s

@pytest.fixture(scope="module")
def employer_sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={"email": EMPLOYER_EMAIL, "password": PW, "name": "Test Employer", "role": "employer"})
    assert r.status_code == 200, r.text
    return s

@pytest.fixture(scope="module")
def talent_user(talent_sess):
    return talent_sess.get(f"{API}/auth/me").json()

@pytest.fixture(scope="module")
def employer_user(employer_sess):
    return employer_sess.get(f"{API}/auth/me").json()


# ---------- Auth ----------
class TestAuth:
    def test_register_talent_sets_cookies(self, talent_sess):
        assert "access_token" in talent_sess.cookies.get_dict()
        me = talent_sess.get(f"{API}/auth/me")
        assert me.status_code == 200
        assert me.json()["role"] == "talent"
        assert me.json()["email"] == TALENT_EMAIL

    def test_register_employer(self, employer_sess):
        me = employer_sess.get(f"{API}/auth/me")
        assert me.status_code == 200
        assert me.json()["role"] == "employer"

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": TALENT_EMAIL, "password": "wrongpw"})
        assert r.status_code == 401

    def test_login_correct(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": TALENT_EMAIL, "password": PW})
        assert r.status_code == 200
        assert "access_token" in s.cookies.get_dict()
        assert r.json()["email"] == TALENT_EMAIL

    def test_me_unauthenticated(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_logout_clears_cookies(self):
        s = requests.Session()
        s.post(f"{API}/auth/login", json={"email": TALENT_EMAIL, "password": PW})
        r = s.post(f"{API}/auth/logout")
        assert r.status_code == 200
        # cookie should be cleared
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 401


# ---------- Profile ----------
class TestProfile:
    def test_update_profile(self, talent_sess):
        payload = {"headline": "Senior Python Dev", "bio": "10y exp",
                   "skills": ["python", "fastapi", "aws"], "years_experience": 10,
                   "hourly_rate": 75.0, "location": "Remote"}
        r = talent_sess.put(f"{API}/profile", json=payload)
        assert r.status_code == 200
        prof = r.json()["profile"]
        assert prof["headline"] == "Senior Python Dev"
        assert prof["years_experience"] == 10
        assert "python" in prof["skills"]

    def test_suggest_rate_no_500(self, talent_sess):
        r = talent_sess.post(f"{API}/profile/suggest-rate",
                             json={"skills": ["python", "aws"], "years_experience": 5, "location": "Remote"})
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("low", "mid", "high", "currency", "rationale"):
            assert k in d
        assert isinstance(d["low"], int) and isinstance(d["mid"], int) and isinstance(d["high"], int)


# ---------- Talent listing ----------
class TestTalent:
    def test_list_talent_public(self):
        r = requests.get(f"{API}/talent")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_talent_hides_email_for_non_engaged(self, employer_sess, talent_user):
        r = employer_sess.get(f"{API}/talent/{talent_user['id']}")
        assert r.status_code == 200
        assert "email" not in r.json() or r.json().get("email") is None


# ---------- Packages ----------
class TestPackages:
    def test_packages_returns_4(self):
        r = requests.get(f"{API}/packages")
        assert r.status_code == 200
        d = r.json()
        for k in ("starter_10", "growth_50", "scale_100", "enterprise_500"):
            assert k in d


# ---------- Payments ----------
class TestPayments:
    def test_talent_cannot_checkout(self, talent_sess):
        r = talent_sess.post(f"{API}/payments/checkout",
                             json={"package_id": "starter_10", "origin_url": BASE})
        assert r.status_code == 403

    def test_employer_checkout_creates_session(self, employer_sess):
        r = employer_sess.post(f"{API}/payments/checkout",
                               json={"package_id": "starter_10", "origin_url": BASE})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("http")
        assert d.get("session_id")
        # status endpoint
        s = requests.get(f"{API}/payments/status/{d['session_id']}")
        assert s.status_code == 200
        assert s.json()["session_id"] == d["session_id"]
        assert s.json()["payment_status"] in ("pending", "paid", "unpaid")


# ---------- Engagements ----------
class TestEngagements:
    def test_engagement_insufficient_hours_400(self, employer_sess, talent_user):
        # employer_sess still has 0 hours_balance
        r = employer_sess.post(f"{API}/engagements",
                               json={"talent_id": talent_user["id"], "hours": 5, "scope": "test scope"})
        assert r.status_code == 400

    def test_signing_flow(self, employer_sess, talent_sess, talent_user, employer_user):
        # Seed hours_balance via direct DB access (motor sync via pymongo)
        try:
            from pymongo import MongoClient
            mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
            db_name = os.environ.get("DB_NAME") or "test_database"
            mc = MongoClient(mongo_url)
            mc[db_name].users.update_one({"id": employer_user["id"]}, {"$set": {"hours_balance": 100}})
        except Exception as e:
            pytest.skip(f"DB seed unavailable: {e}")
        # Create engagement
        r = employer_sess.post(f"{API}/engagements",
                               json={"talent_id": talent_user["id"], "hours": 10, "scope": "Signing flow test"})
        assert r.status_code == 200, r.text
        eng = r.json()
        assert eng["status"] == "pending_signatures"
        eid = eng["id"]
        # Employer signs
        r1 = employer_sess.post(f"{API}/engagements/sign",
                                json={"engagement_id": eid, "signature": "Test Employer"})
        assert r1.status_code == 200
        assert r1.json()["status"] == "pending_signatures"
        # Talent signs
        r2 = talent_sess.post(f"{API}/engagements/sign",
                              json={"engagement_id": eid, "signature": "Test Talent"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "contract_signed"
        # Verify hours_balance deducted
        me = employer_sess.get(f"{API}/auth/me").json()
        assert me["hours_balance"] == 90, f"Expected 90, got {me['hours_balance']}"


# ---------- Integrations ----------
class TestIntegrations:
    def test_providers_list_has_11(self):
        r = requests.get(f"{API}/integrations/providers")
        assert r.status_code == 200
        provs = r.json()
        ids = {p["id"] for p in provs}
        expected = {"monday", "wrike", "ms_dynamics", "servicenow", "sap",
                    "asana", "jira", "trello", "clickup", "notion", "confluence"}
        assert expected.issubset(ids), f"Missing: {expected - ids}"
        assert len(provs) >= 11

    def test_connect_integration_and_list_items(self, employer_sess):
        r = employer_sess.post(f"{API}/integrations/connect",
                               json={"provider": "asana", "api_token": "fake_token_1234567890", "workspace": ""})
        assert r.status_code == 200
        assert "***" in r.json()["token_masked"]
        # allow small time
        time.sleep(0.5)
        items = employer_sess.get(f"{API}/work/items")
        assert items.status_code == 200
        assert isinstance(items.json(), list)
        assert len(items.json()) > 0


# ---------- Work upload ----------
class TestWorkUpload:
    def _make_xlsx(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["Task", "Status", "Hours"])
        ws.append(["Design UI", "open", 4])
        ws.append(["Build API", "in_progress", 6])
        ws.append(["Write tests", "done", 2])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_upload_xlsx(self, employer_sess):
        buf = self._make_xlsx()
        r = employer_sess.post(f"{API}/work/upload",
                               files={"file": ("tasks.xlsx", buf,
                                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["inserted"] >= 3

    def test_upload_mpp_returns_400(self, employer_sess):
        r = employer_sess.post(f"{API}/work/upload",
                               files={"file": ("plan.mpp", b"\x00\x01binary", "application/octet-stream")})
        assert r.status_code == 400
        assert "MS Project" in r.text or "mpp" in r.text.lower()


# ---------- Dashboard ----------
class TestDashboard:
    def _assert_keys(self, d):
        for k in ("engagements_total", "hours_purchased", "hours_balance",
                 "work_items_by_status", "work_items_by_source",
                 "integrations_connected", "upcoming"):
            assert k in d, f"Missing key: {k}"

    def test_metrics_employer(self, employer_sess):
        r = employer_sess.get(f"{API}/dashboard/metrics")
        assert r.status_code == 200
        self._assert_keys(r.json())

    def test_metrics_talent(self, talent_sess):
        r = talent_sess.get(f"{API}/dashboard/metrics")
        assert r.status_code == 200
        self._assert_keys(r.json())
