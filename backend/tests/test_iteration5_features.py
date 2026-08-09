"""Tests for iteration 5 new features:
- /marketplace/industries + /marketplace/stats
- Shortlist CRUD + role gate
- Rate nudge scan + in-app banner + scheduler
- Sitemap
- Employer registration with company_industry
"""
import os
import time
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
if _BACKEND_ENV.exists():
    load_dotenv(_BACKEND_ENV)

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@talenthub.io"
ADMIN_PW = "Admin@2026"
TALENT_EMAIL = "talent@test.io"
TALENT_PW = "Talent@2026"
SEED_EMP = "emp-series-b-fintechs@test.io"
SEED_EMP_PW = "Employer@2026"

EMPLOYER_INDUSTRIES = [
    "Series-B fintechs", "PE-backed platforms", "Health-tech scale-ups",
    "YC-backed marketplaces", "Global consultancies", "Public-sector innovation",
    "Series-A SaaS teams", "Family-office ventures", "Cross-border e-commerce",
    "DTC brand houses", "Regulated data-cos", "ClimateTech pilots",
]


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text}")
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def talent_sess():
    return _login(TALENT_EMAIL, TALENT_PW)


@pytest.fixture(scope="module")
def seeded_employer_sess():
    return _login(SEED_EMP, SEED_EMP_PW)


# ---------- Marketplace industries/stats ----------
class TestMarketplace:
    def test_industries_public(self):
        r = requests.get(f"{API}/marketplace/industries")
        assert r.status_code == 200
        d = r.json()
        assert "industries" in d
        assert len(d["industries"]) == 12
        labels = [i["label"] for i in d["industries"]]
        for exp in EMPLOYER_INDUSTRIES:
            assert exp in labels, f"missing {exp}"
        for item in d["industries"]:
            assert "count" in item and isinstance(item["count"], int)

    def test_stats_public(self):
        r = requests.get(f"{API}/marketplace/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ("active_buyers", "industries", "industries_active", "engagements_signed"):
            assert k in d
        assert d["industries"] == 12


# ---------- Employer registration with industry ----------
class TestEmployerRegisterIndustry:
    def test_register_with_industry(self):
        s = requests.Session()
        email = f"new-emp-{int(time.time())}-{uuid.uuid4().hex[:6]}@test.io"
        payload = {
            "email": email, "password": "P@ssw0rd123",
            "name": "New Emp", "role": "employer",
            "company_industry": "Series-A SaaS teams",
        }
        r = s.post(f"{API}/auth/register", json=payload)
        assert r.status_code == 200, r.text
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200
        prof = me.json().get("profile") or {}
        assert prof.get("company_industry") == "Series-A SaaS teams"

    def test_register_with_unknown_industry_rejected(self):
        s = requests.Session()
        email = f"bad-emp-{uuid.uuid4().hex[:6]}@test.io"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "P@ssw0rd123",
            "name": "Bad Emp", "role": "employer",
            "company_industry": "Not A Real Industry",
        })
        assert r.status_code == 400

    def test_talent_industry_ignored(self):
        s = requests.Session()
        email = f"tal-{uuid.uuid4().hex[:6]}@test.io"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "P@ssw0rd123",
            "name": "T", "role": "talent",
            "company_industry": "Series-B fintechs",
        })
        assert r.status_code == 200
        me = s.get(f"{API}/auth/me").json()
        prof = me.get("profile") or {}
        assert not prof.get("company_industry")


# ---------- Shortlist CRUD ----------
class TestShortlist:
    def test_talent_forbidden(self, talent_sess):
        r = talent_sess.post(f"{API}/shortlist", json={
            "talent_id": "x", "talent_name": "x",
        })
        assert r.status_code == 403
        r2 = talent_sess.get(f"{API}/shortlist")
        assert r2.status_code == 403

    def test_add_list_remove(self, seeded_employer_sess):
        tid = f"curated-{uuid.uuid4().hex[:8]}"
        # Add
        r = seeded_employer_sess.post(f"{API}/shortlist", json={
            "talent_id": tid, "talent_name": "Test Curated",
            "headline": "React dev", "location": "London",
            "hourly_rate": 85, "skills": ["React", "TypeScript"],
            "context": "hire/react-developers-london", "is_curated": True,
        })
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert r.json()["count"] >= 1

        # List includes it
        lst = seeded_employer_sess.get(f"{API}/shortlist")
        assert lst.status_code == 200
        items = lst.json()["items"]
        match = [x for x in items if x["talent_id"] == tid]
        assert len(match) == 1
        assert match[0]["talent_name"] == "Test Curated"
        assert match[0]["hourly_rate"] == 85

        # Upsert (add again -> still 1 record)
        r2 = seeded_employer_sess.post(f"{API}/shortlist", json={
            "talent_id": tid, "talent_name": "Test Curated Updated",
            "hourly_rate": 90, "skills": ["React"],
        })
        assert r2.status_code == 200
        lst2 = seeded_employer_sess.get(f"{API}/shortlist").json()
        match2 = [x for x in lst2["items"] if x["talent_id"] == tid]
        assert len(match2) == 1
        assert match2[0]["talent_name"] == "Test Curated Updated"

        # Delete
        rd = seeded_employer_sess.delete(f"{API}/shortlist/{tid}")
        assert rd.status_code == 200
        lst3 = seeded_employer_sess.get(f"{API}/shortlist").json()
        assert not any(x["talent_id"] == tid for x in lst3["items"])


# ---------- Rate Nudge ----------
class TestRateNudge:
    def test_admin_only_scan(self, seeded_employer_sess):
        r = seeded_employer_sess.post(f"{API}/admin/rate-nudges/scan")
        assert r.status_code == 403

    def test_scan_and_nudge_talent(self, admin_sess, talent_sess):
        # Set talent to a rate that should drift >15% (very high or very low)
        prof = {
            "headline": "Senior React Dev", "bio": "8y",
            "skills": ["React", "TypeScript", "Node"],
            "years_experience": 8, "hourly_rate": 220.0, "location": "London",
        }
        up = talent_sess.put(f"{API}/profile", json=prof)
        assert up.status_code == 200

        r = admin_sess.post(f"{API}/admin/rate-nudges/scan")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("checked", "nudged", "emailed", "email_failures",
                  "threshold_pct", "scanned_at"):
            assert k in d
        assert d["threshold_pct"] == 15
        # Since RESEND_API_KEY empty, no emails sent
        assert d["emailed"] == 0

        # Talent should have a nudge doc (if drift triggered)
        n = talent_sess.get(f"{API}/talent/me/rate-nudge")
        assert n.status_code == 200
        nudge = n.json().get("nudge")
        # nudge may or may not trigger based on AI mid; if triggered check schema
        if nudge:
            assert nudge["talent_id"]
            assert nudge["email_status"] in ("RESEND_API_KEY not configured", "failed", "sent")
            assert nudge["email_status"] == "RESEND_API_KEY not configured"

    def test_scheduler_status(self, admin_sess):
        r = admin_sess.get(f"{API}/admin/scheduler")
        assert r.status_code == 200
        d = r.json()
        assert d["running"] is True
        assert isinstance(d["jobs"], list)
        assert len(d["jobs"]) >= 1
        job = next((j for j in d["jobs"] if j["id"] == "monthly_rate_nudge_scan"), None)
        assert job is not None
        assert job["next_run_time"]
        assert "cron" in job["trigger"].lower()

    def test_non_admin_scheduler_forbidden(self, talent_sess):
        r = talent_sess.get(f"{API}/admin/scheduler")
        assert r.status_code == 403


# ---------- Sitemap ----------
class TestSitemap:
    def test_sitemap_xml(self):
        r = requests.get(f"{API}/sitemap.xml")
        assert r.status_code == 200
        body = r.text
        assert "<urlset" in body
        assert body.count("<url>") >= 70
        for path in ("/browse", "/pricing", "/register"):
            assert path in body
