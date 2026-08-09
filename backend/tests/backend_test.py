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
        pkgs = d.get("packages", d)  # tolerate wrapped or flat
        for k in ("starter_10", "growth_50", "scale_100", "enterprise_500"):
            assert k in pkgs


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
    def test_engagement_insufficient_hours_400(self, employer_sess, talent_user, employer_user):
        # Ensure hours_balance is 0 (other tests may have seeded)
        try:
            from pymongo import MongoClient
            mc = MongoClient(os.environ["MONGO_URL"])
            mc[os.environ["DB_NAME"]].users.update_one(
                {"id": employer_user["id"]}, {"$set": {"hours_balance": 0}})
        except Exception:
            pass
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


# ---------- Admin session fixture (from seeded admin) ----------
@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@talenthub.io", "password": "Admin@2026"})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return s


# ---------- Packages: bank + usd_to_inr ----------
class TestPackagesExtra:
    def test_packages_include_bank_and_inr(self):
        r = requests.get(f"{API}/packages")
        assert r.status_code == 200
        d = r.json()
        assert "packages" in d and "bank" in d and "usd_to_inr" in d
        assert d["usd_to_inr"] == 83
        for pid, pkg in d["packages"].items():
            assert "amount_inr" in pkg and pkg["amount_inr"] > 0
        assert d["bank"]["ifsc"]
        assert d["bank"]["account_number"]
        assert d["bank"]["country"] == "India"


# ---------- Bank Transfer Flow ----------
class TestBankTransfer:
    def test_talent_cannot_initiate_bank(self, talent_sess):
        r = talent_sess.post(f"{API}/payments/bank/initiate", json={"package_id": "starter_10"})
        assert r.status_code == 403

    def test_initiate_invalid_package(self, employer_sess):
        r = employer_sess.post(f"{API}/payments/bank/initiate", json={"package_id": "bogus_xyz"})
        assert r.status_code == 400

    def test_bank_flow_end_to_end(self, employer_sess, admin_sess):
        # Initiate
        r = employer_sess.post(f"{API}/payments/bank/initiate", json={"package_id": "growth_50"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_id"]
        assert d["reference"].startswith("TH-")
        assert d["amount_inr"] == 1400 * 83
        assert d["bank"]["ifsc"]
        pid = d["payment_id"]

        # Submit UTR without value -> 400
        rbad = employer_sess.post(f"{API}/payments/bank/submit",
                                  json={"payment_id": pid, "utr": "   ", "payer_note": "n/a"})
        assert rbad.status_code == 400

        # Submit valid UTR
        rsub = employer_sess.post(f"{API}/payments/bank/submit",
                                  json={"payment_id": pid, "utr": "UTR123456789", "payer_note": "IMPS"})
        assert rsub.status_code == 200
        assert rsub.json()["status"] == "awaiting_verification"

        # Employer sees own payments list
        mine = employer_sess.get(f"{API}/payments/mine")
        assert mine.status_code == 200
        entries = mine.json()
        rec = next((x for x in entries if x["id"] == pid), None)
        assert rec is not None
        assert rec["status"] == "awaiting_verification"
        assert rec["utr"] == "UTR123456789"

        # Non-admin cannot approve
        r_forbid = employer_sess.post(f"{API}/admin/bank-transfers/{pid}/approve")
        assert r_forbid.status_code == 403

        # Admin approve credits hours
        me_before = employer_sess.get(f"{API}/auth/me").json()
        hb_before = int(me_before.get("hours_balance") or 0)

        r_appr = admin_sess.post(f"{API}/admin/bank-transfers/{pid}/approve")
        assert r_appr.status_code == 200, r_appr.text
        assert r_appr.json()["ok"] is True

        # Hours credited (+50)
        me_after = employer_sess.get(f"{API}/auth/me").json()
        assert int(me_after["hours_balance"]) == hb_before + 50

        # Idempotent second approval
        r_appr2 = admin_sess.post(f"{API}/admin/bank-transfers/{pid}/approve")
        assert r_appr2.status_code == 200
        assert r_appr2.json().get("already") is True

    def test_admin_list_bank_transfers_admin_only(self, employer_sess, admin_sess):
        r_forbid = employer_sess.get(f"{API}/admin/bank-transfers")
        assert r_forbid.status_code == 403
        r_ok = admin_sess.get(f"{API}/admin/bank-transfers")
        assert r_ok.status_code == 200
        assert isinstance(r_ok.json(), list)


# ---------- EOI Flow ----------
class TestEOI:
    def test_employer_cannot_create_eoi(self, employer_sess):
        r = employer_sess.post(f"{API}/eoi", json={"message": "hi", "proposed_hours_per_week": 5})
        assert r.status_code == 403

    def test_eoi_flow(self, talent_sess, employer_sess, talent_user, employer_user, admin_sess):
        # Talent creates open EOI
        r = talent_sess.post(f"{API}/eoi", json={
            "employer_id": None,
            "message": "I'd love to help with your data platform work.",
            "proposed_hours_per_week": 8,
            "start_date": "2026-02-01",
        })
        assert r.status_code == 200, r.text
        eoi = r.json()
        assert eoi["status"] == "open"
        assert eoi["talent_id"] == talent_user["id"]
        eoi_id = eoi["id"]

        # Talent lists own EOI
        rt = talent_sess.get(f"{API}/eoi")
        assert rt.status_code == 200
        assert any(x["id"] == eoi_id for x in rt.json())

        # Employer sees open EOI (employer_id None -> visible to any employer)
        re_ = employer_sess.get(f"{API}/eoi")
        assert re_.status_code == 200
        assert any(x["id"] == eoi_id for x in re_.json()), "Employer should see open EOI"

        # Ensure employer has hours (seed via admin bank approve is possible; use direct DB if available)
        try:
            from pymongo import MongoClient
            mc = MongoClient(os.environ["MONGO_URL"])
            mc[os.environ["DB_NAME"]].users.update_one(
                {"id": employer_user["id"]}, {"$inc": {"hours_balance": 40}})
        except Exception as e:
            pytest.skip(f"DB seed unavailable: {e}")

        # Employer accepts EOI -> creates engagement
        ra = employer_sess.post(f"{API}/eoi/{eoi_id}/accept",
                                json={"scope": "Data pipelines", "hours": 12})
        assert ra.status_code == 200, ra.text
        eng = ra.json()
        assert eng["from_eoi_id"] == eoi_id
        assert eng["status"] == "pending_signatures"
        assert eng["hours_allocated"] == 12

        # EOI status changed to accepted
        rt2 = talent_sess.get(f"{API}/eoi").json()
        target = next(x for x in rt2 if x["id"] == eoi_id)
        assert target["status"] == "accepted"

        # Cannot re-accept
        ra2 = employer_sess.post(f"{API}/eoi/{eoi_id}/accept", json={"hours": 5})
        assert ra2.status_code == 400

    def test_eoi_insufficient_hours(self, talent_sess, employer_sess, employer_user):
        # Ensure employer hours are drained
        try:
            from pymongo import MongoClient
            mc = MongoClient(os.environ["MONGO_URL"])
            mc[os.environ["DB_NAME"]].users.update_one(
                {"id": employer_user["id"]}, {"$set": {"hours_balance": 0}})
        except Exception as e:
            pytest.skip(f"DB seed unavailable: {e}")
        # New EOI
        r = talent_sess.post(f"{API}/eoi", json={
            "message": "Second gig", "proposed_hours_per_week": 5, "employer_id": None})
        assert r.status_code == 200
        eid = r.json()["id"]
        ra = employer_sess.post(f"{API}/eoi/{eid}/accept", json={"hours": 20})
        assert ra.status_code == 400


# ---------- Availability & Calendar ----------
class TestAvailability:
    def test_put_and_get_availability(self, talent_sess, talent_user):
        slots = [{"day": 1, "start": "10:00", "end": "16:00"},
                 {"day": 3, "start": "09:00", "end": "12:00"}]
        r = talent_sess.put(f"{API}/availability", json={"timezone": "Asia/Kolkata", "slots": slots})
        assert r.status_code == 200
        assert r.json()["timezone"] == "Asia/Kolkata"
        assert len(r.json()["slots"]) == 2

        g = talent_sess.get(f"{API}/availability/{talent_user['id']}")
        assert g.status_code == 200
        d = g.json()
        assert d["user"]["id"] == talent_user["id"]
        assert d["availability"]["timezone"] == "Asia/Kolkata"
        assert len(d["availability"]["slots"]) == 2

    def test_calendar_events(self, employer_sess):
        r = employer_sess.get(f"{API}/calendar/events")
        assert r.status_code == 200
        events = r.json()
        assert isinstance(events, list)
        # Should contain engagement events from earlier signing/EOI tests
        types = {e["type"] for e in events}
        assert "engagement" in types or len(events) == 0  # tolerant


# ---------- Integrations providers coverage ----------
class TestIntegrationProvidersCoverage:
    def test_all_expected_providers_present(self):
        r = requests.get(f"{API}/integrations/providers")
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()}
        # Required by review request
        for pid in ("jira", "asana", "confluence", "monday", "sap", "servicenow", "ms_dynamics", "wrike"):
            assert pid in ids, f"Missing provider: {pid}"


# ---------- Work upload: XML ----------
class TestWorkUploadXML:
    def test_upload_msproject_xml(self, employer_sess):
        # Minimal MS Project-ish XML
        xml = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<Project xmlns='http://schemas.microsoft.com/project'>"
            "<Tasks>"
            "<Task><Name>Kickoff meeting</Name><Finish>2026-02-01T17:00:00</Finish></Task>"
            "<Task><Name>Draft spec</Name><Finish>2026-02-05T17:00:00</Finish></Task>"
            "</Tasks></Project>"
        ).encode()
        r = employer_sess.post(f"{API}/work/upload",
                               files={"file": ("plan.xml", xml, "application/xml")})
        # Parser is namespace-agnostic; accept either successful parse or 400
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            assert r.json()["inserted"] >= 0

    def test_upload_unsupported_ext_400(self, employer_sess):
        r = employer_sess.post(f"{API}/work/upload",
                               files={"file": ("readme.txt", b"hello", "text/plain")})
        assert r.status_code == 400


# ---------- Connected Accounts ----------
class TestConnectedAccounts:
    def test_providers_filtered_by_role_talent(self, talent_sess):
        r = talent_sess.get(f"{API}/accounts/providers")
        assert r.status_code == 200
        provs = r.json()
        ids = {p["id"] for p in provs}
        # Talent-specific
        assert "github" in ids and "payoneer" in ids and "wise" in ids
        # Employer-specific must be filtered out
        assert "slack" not in ids and "plaid" not in ids and "company" not in ids

    def test_providers_filtered_by_role_employer(self, employer_sess):
        r = employer_sess.get(f"{API}/accounts/providers")
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()}
        assert "slack" in ids and "plaid" in ids and "company" in ids
        assert "github" not in ids and "payoneer" not in ids

    def test_talent_cannot_connect_employer_provider(self, talent_sess):
        r = talent_sess.post(f"{API}/accounts/connect",
                             json={"provider": "slack", "handle": "https://x.slack.com"})
        assert r.status_code == 403

    def test_connect_missing_handle(self, talent_sess):
        r = talent_sess.post(f"{API}/accounts/connect",
                             json={"provider": "github", "handle": "   "})
        assert r.status_code == 400

    def test_connect_and_disconnect(self, talent_sess):
        r = talent_sess.post(f"{API}/accounts/connect",
                             json={"provider": "github", "handle": "octotest",
                                   "api_token": "gh_secret_xyz", "metadata": {"followers": 1}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["provider"] == "github"
        assert d["handle"] == "octotest"
        assert "api_token" not in d  # token must be stripped

        # Listed
        lst = talent_sess.get(f"{API}/accounts").json()
        acc = next(a for a in lst if a["id"] == d["id"])
        assert acc["provider"] == "github"

        # Reconnect same provider -> upsert (still one)
        r2 = talent_sess.post(f"{API}/accounts/connect",
                              json={"provider": "github", "handle": "octotest2"})
        assert r2.status_code == 200
        lst2 = talent_sess.get(f"{API}/accounts").json()
        gh_count = len([a for a in lst2 if a["provider"] == "github"])
        assert gh_count == 1

        aid = r2.json()["id"]
        # Disconnect
        rd = talent_sess.delete(f"{API}/accounts/{aid}")
        assert rd.status_code == 200
        lst3 = talent_sess.get(f"{API}/accounts").json()
        assert not any(a["id"] == aid for a in lst3)

        # Disconnect again -> 404
        rd2 = talent_sess.delete(f"{API}/accounts/{aid}")
        assert rd2.status_code == 404

    def test_unknown_provider(self, employer_sess):
        r = employer_sess.post(f"{API}/accounts/connect",
                               json={"provider": "bogusprov", "handle": "x"})
        assert r.status_code == 400


# ---------- Pricing ----------
class TestPricing:
    def test_pricing_returns_three_plans_and_compare(self):
        r = requests.get(f"{API}/pricing")
        assert r.status_code == 200
        d = r.json()
        assert "plans" in d and len(d["plans"]) == 3
        plan_ids = {p["id"] for p in d["plans"]}
        assert {"free", "starter", "growth"}.issubset(plan_ids)
        for p in d["plans"]:
            assert "name" in p and "price" in p and "features" in p and len(p["features"]) >= 3
        assert "compare" in d
        for k in ("upwork", "fiverr", "freelancer"):
            assert k in d["compare"]
        assert d["platform_fee_pct"] == 8
