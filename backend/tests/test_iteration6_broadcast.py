"""Iteration 6 tests: auth regression (routes/auth.py), deps.py constants, sitemap,
shortlist CRUD, shortlist broadcast + talent inbox, admin rate-nudge scan, scheduler."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@talenthub.io", "Admin@2026")
TALENT = ("talent@test.io", "Talent@2026")
EMP = ("emp-series-b-fintechs@test.io", "Employer@2026")


def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(s, email, pw):
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return r.json()


# ============ Auth regression ============
class TestAuthRegression:
    def test_register_fresh_employer(self):
        s = _session()
        email = f"TEST_emp_{uuid.uuid4().hex[:8]}@test.io"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "Employer@2026",
            "name": "TEST Employer", "role": "employer",
            "company_industry": "Series-B fintechs",
        }, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == email.lower()
        assert data["role"] == "employer"
        assert data["profile"]["company_industry"] == "Series-B fintechs"
        # cookies set
        assert "access_token" in s.cookies

    def test_register_unknown_industry_rejected(self):
        s = _session()
        email = f"TEST_bad_{uuid.uuid4().hex[:8]}@test.io"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "Employer@2026",
            "name": "TEST Bad", "role": "employer",
            "company_industry": "NotARealIndustry",
        }, timeout=30)
        assert r.status_code == 400

    def test_login_admin(self):
        s = _session()
        u = _login(s, *ADMIN)
        assert u["email"] == ADMIN[0]
        assert u["role"] == "admin"

    def test_me_returns_user(self):
        s = _session()
        _login(s, *ADMIN)
        r = s.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN[0]

    def test_logout_clears_cookies(self):
        s = _session()
        _login(s, *ADMIN)
        r = s.post(f"{API}/auth/logout", timeout=30)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_put_profile_updates(self):
        s = _session()
        _login(s, *TALENT)
        payload = {
            "headline": "TEST headline", "bio": "TEST bio",
            "skills": ["React", "TypeScript", "Node"],
            "years_experience": 8, "hourly_rate": 75.0,
            "location": "London", "timezone": "UTC",
            "weekly_capacity_hours": 40,
        }
        r = s.put(f"{API}/profile", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["profile"]["headline"] == "TEST headline"

    def test_suggest_rate(self):
        s = _session()
        _login(s, *TALENT)
        r = s.post(f"{API}/profile/suggest-rate", json={
            "skills": ["React", "Node"], "years_experience": 8, "location": "London",
        }, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("low", "mid", "high", "rationale"):
            assert k in data, f"missing {k} in {data}"


# ============ deps.py constants exposure ============
class TestDepsConstants:
    def test_industries_endpoint(self):
        s = _session()
        r = s.get(f"{API}/marketplace/industries", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # can be list of {label,count} or list of str
        items = data if isinstance(data, list) else data.get("industries", [])
        assert len(items) == 12

    def test_marketplace_stats(self):
        s = _session()
        r = s.get(f"{API}/marketplace/stats", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("industries") == 12 or data.get("industry_count") == 12 or len(data.get("industries_list", [])) == 12

    def test_seo_skills(self):
        s = _session()
        r = s.get(f"{API}/seo/skills", timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("skills", [])
        assert len(items) == 12


# ============ Sitemap ============
class TestSitemap:
    def test_sitemap(self):
        r = requests.get(f"{API}/sitemap.xml", timeout=30)
        assert r.status_code == 200
        assert "<urlset" in r.text
        assert r.text.count("<url>") >= 70


# ============ Shortlist CRUD ============
class TestShortlistCRUD:
    def test_shortlist_crud_and_talent_403(self):
        emp = _session(); _login(emp, *EMP)
        # get talent id
        tal = _session(); tuser = _login(tal, *TALENT); talent_id = tuser["id"]

        # add
        r = emp.post(f"{API}/shortlist", json={"talent_id": talent_id, "talent_name": "Test Talent", "is_curated": False}, timeout=30)
        assert r.status_code in (200, 201), r.text

        # list
        r = emp.get(f"{API}/shortlist", timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
        assert any(x.get("talent_id") == talent_id for x in items)

        # talent forbidden
        r = tal.post(f"{API}/shortlist", json={"talent_id": talent_id, "talent_name": "x"}, timeout=30)
        assert r.status_code == 403


# ============ Broadcast ============
class TestBroadcast:
    def test_broadcast_happy_path_and_talent_inbox(self):
        emp = _session(); _login(emp, *EMP)
        tal = _session(); tuser = _login(tal, *TALENT); talent_id = tuser["id"]

        # ensure real talent in shortlist
        emp.post(f"{API}/shortlist", json={"talent_id": talent_id, "talent_name": tuser.get("name") or "Talent", "is_curated": False}, timeout=30)

        msg = f"TEST Ready to hire — reply here! {uuid.uuid4().hex[:6]}"
        r = emp.post(f"{API}/shortlist/broadcast", json={"message": msg}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data.get("delivered", 0) >= 1
        assert data.get("emailed", 0) == 0
        assert data.get("email_failures", 0) >= 1
        assert data.get("total_shortlist", 0) >= 1
        assert "broadcast_id" in data

        # talent inbox
        r = tal.get(f"{API}/talent/me/broadcasts", timeout=30)
        assert r.status_code == 200
        inbox = r.json()
        assert inbox["count"] >= 1
        assert inbox["unread"] >= 1
        # find our broadcast
        item = next((x for x in inbox["items"] if x.get("message") == msg), None)
        assert item is not None, f"broadcast not delivered to talent inbox: {inbox}"
        assert item["read"] is False
        assert item.get("employer_name")

        # mark read
        r = tal.post(f"{API}/talent/me/broadcasts/{item['id']}/read", timeout=30)
        assert r.status_code == 200

        r = tal.get(f"{API}/talent/me/broadcasts", timeout=30)
        inbox2 = r.json()
        item2 = next(x for x in inbox2["items"] if x["id"] == item["id"])
        assert item2["read"] is True

    def test_broadcast_empty_shortlist(self):
        s = _session()
        email = f"TEST_freshemp_{uuid.uuid4().hex[:8]}@test.io"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "Employer@2026",
            "name": "TEST Fresh Emp", "role": "employer",
            "company_industry": "Series-B fintechs",
        }, timeout=30)
        assert r.status_code == 200
        r = s.post(f"{API}/shortlist/broadcast", json={}, timeout=30)
        assert r.status_code == 400
        assert "empty" in r.json().get("detail", "").lower()

    def test_broadcast_default_message(self):
        emp = _session(); _login(emp, *EMP)
        tal = _session(); tuser = _login(tal, *TALENT)
        emp.post(f"{API}/shortlist", json={"talent_id": tuser["id"], "talent_name": tuser.get("name") or "Talent", "is_curated": False}, timeout=30)
        r = emp.post(f"{API}/shortlist/broadcast", json={}, timeout=60)
        assert r.status_code == 200
        # verify inbox has default message
        r = tal.get(f"{API}/talent/me/broadcasts", timeout=30)
        items = r.json()["items"]
        # newest for this employer should have default
        latest = items[0]
        assert latest["message"].startswith("Hi — I'm ready to bring you on")

    def test_broadcast_talent_403(self):
        tal = _session(); _login(tal, *TALENT)
        r = tal.post(f"{API}/shortlist/broadcast", json={"message": "x"}, timeout=30)
        assert r.status_code == 403

    def test_broadcast_anonymous_401(self):
        r = requests.post(f"{API}/shortlist/broadcast", json={"message": "x"}, timeout=30)
        assert r.status_code == 401

    def test_broadcasts_inbox_employer_empty(self):
        emp = _session(); _login(emp, *EMP)
        r = emp.get(f"{API}/talent/me/broadcasts", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data == {"items": [], "count": 0, "unread": 0}


# ============ Rate Nudge + Scheduler regression ============
class TestRateNudgeAndScheduler:
    def test_rate_nudge_scan(self):
        s = _session(); _login(s, *ADMIN)
        r = s.post(f"{API}/admin/rate-nudges/scan", timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("checked", "nudged", "emailed", "email_failures", "threshold_pct", "scanned_at"):
            assert k in d, f"missing {k}"
        assert d["threshold_pct"] == 15

    def test_scheduler(self):
        s = _session(); _login(s, *ADMIN)
        r = s.get(f"{API}/admin/scheduler", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("running") is True
        jobs = d.get("jobs", [])
        job = next((j for j in jobs if j.get("id") == "monthly_rate_nudge_scan"), None)
        assert job is not None, f"job missing: {jobs}"
        assert job.get("next_run_time")
        assert "cron" in job.get("trigger", "").lower()
