"""Iteration 7 tests:
- SSE real-time broadcast stream
- Broadcast history endpoint
- Standardised 16 industries + migration
- Admin routes physical extraction (routes/admin.py)
- Regression: auth + scheduler
"""
import os
import json
import time
import uuid
import threading
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


EXPECTED_INDUSTRIES = {
    "Financial Services & Fintech", "Healthcare & Life Sciences",
    "SaaS & Enterprise Software", "E-commerce & Retail",
    "Media & Entertainment", "Education & EdTech",
    "Marketing & Advertising", "Manufacturing & Industrial",
    "Real Estate & PropTech", "Travel & Hospitality",
    "Energy & CleanTech", "Legal & Professional Services",
    "Non-profit & Public Sector", "Logistics & Supply Chain",
    "Cybersecurity", "AI & Data Platforms",
}
LEGACY_LABELS = {"Series-B fintechs", "PE-backed platforms", "Health-tech scale-ups",
                 "YC-backed marketplaces", "ClimateTech pilots"}


# ============ Industries + migration ============
class TestIndustries:
    def test_industries_returns_16(self):
        r = requests.get(f"{API}/marketplace/industries", timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("industries", [])
        labels = set()
        for it in items:
            if isinstance(it, dict):
                labels.add(it.get("label") or it.get("name") or it.get("industry"))
            else:
                labels.add(it)
        assert len(items) == 16, f"got {len(items)}: {labels}"
        assert labels == EXPECTED_INDUSTRIES, f"labels mismatch: extra={labels-EXPECTED_INDUSTRIES}, missing={EXPECTED_INDUSTRIES-labels}"
        assert not (labels & LEGACY_LABELS), f"legacy labels present: {labels & LEGACY_LABELS}"

    def test_industries_include_migrated_fintech_count(self):
        r = requests.get(f"{API}/marketplace/industries", timeout=30)
        data = r.json()
        items = data if isinstance(data, list) else data.get("industries", [])
        # Verify Financial Services has count >= 1 (from migrated legacy accounts)
        fs = next((x for x in items if isinstance(x, dict) and (x.get("label") == "Financial Services & Fintech" or x.get("name") == "Financial Services & Fintech")), None)
        if fs is not None and "count" in fs:
            assert fs["count"] >= 1, f"Financial Services count should be >=1 from migration: {fs}"

    def test_marketplace_stats_16(self):
        r = requests.get(f"{API}/marketplace/stats", timeout=30)
        assert r.status_code == 200
        data = r.json()
        val = data.get("industries") or data.get("industry_count") or len(data.get("industries_list", []))
        assert val == 16, f"stats returned {val}: {data}"

    def test_legacy_employer_login_and_migrated_industry(self):
        s = _session()
        u = _login(s, *EMP)
        industry = (u.get("profile") or {}).get("company_industry")
        assert industry == "Financial Services & Fintech", f"legacy emp not migrated: {industry}"


# ============ Broadcast History (new endpoint) ============
class TestBroadcastHistory:
    def test_history_returns_runs_and_creates_new_docs(self):
        emp = _session(); _login(emp, *EMP)
        tal = _session(); tuser = _login(tal, *TALENT)
        # Ensure shortlist
        emp.post(f"{API}/shortlist", json={"talent_id": tuser["id"], "talent_name": tuser.get("name") or "Talent", "is_curated": False}, timeout=30)

        # Baseline count
        r = emp.get(f"{API}/shortlist/broadcasts", timeout=30)
        assert r.status_code == 200
        base = r.json()
        assert "runs" in base and "count" in base
        base_count = base["count"]

        # Send 2 broadcasts back-to-back
        msg1 = f"TEST_hist_A_{uuid.uuid4().hex[:6]}"
        msg2 = f"TEST_hist_B_{uuid.uuid4().hex[:6]}"
        r1 = emp.post(f"{API}/shortlist/broadcast", json={"subject": "Hey", "message": msg1}, timeout=30)
        assert r1.status_code == 200
        r2 = emp.post(f"{API}/shortlist/broadcast", json={"subject": "Hey", "message": msg2}, timeout=30)
        assert r2.status_code == 200

        # History now has +2
        r = emp.get(f"{API}/shortlist/broadcasts", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == base_count + 2, f"expected {base_count+2}, got {d['count']}"
        runs = d["runs"]
        # Check first two runs have required fields
        for run in runs[:2]:
            for k in ("id", "employer_id", "message", "delivered", "emailed", "email_failures", "total_shortlist", "created_at"):
                assert k in run, f"missing {k} in run: {run}"

    def test_history_talent_403(self):
        tal = _session(); _login(tal, *TALENT)
        r = tal.get(f"{API}/shortlist/broadcasts", timeout=30)
        assert r.status_code == 403

    def test_broadcast_same_talent_twice_creates_two_docs(self):
        emp = _session(); _login(emp, *EMP)
        tal = _session(); tuser = _login(tal, *TALENT)
        emp.post(f"{API}/shortlist", json={"talent_id": tuser["id"], "talent_name": "Talent", "is_curated": False}, timeout=30)

        # Baseline inbox
        r = tal.get(f"{API}/talent/me/broadcasts", timeout=30)
        base_count = r.json()["count"]

        unique = uuid.uuid4().hex[:6]
        emp.post(f"{API}/shortlist/broadcast", json={"message": f"TEST_dup_{unique}_1"}, timeout=30)
        emp.post(f"{API}/shortlist/broadcast", json={"message": f"TEST_dup_{unique}_2"}, timeout=30)

        r = tal.get(f"{API}/talent/me/broadcasts", timeout=30)
        assert r.json()["count"] == base_count + 2, f"expected +2 broadcasts, got {r.json()['count']} vs base {base_count}"


# ============ SSE Stream ============
class TestSSE:
    def test_sse_token_talent(self):
        s = _session(); _login(s, *TALENT)
        r = s.get(f"{API}/auth/sse-token", timeout=30)
        assert r.status_code == 200
        assert "token" in r.json()
        assert len(r.json()["token"]) > 20

    def test_sse_token_anonymous_401(self):
        r = requests.get(f"{API}/auth/sse-token", timeout=30)
        assert r.status_code == 401

    def test_sse_stream_anonymous_401(self):
        r = requests.get(f"{API}/talent/me/broadcasts/stream", timeout=10, stream=True)
        assert r.status_code == 401

    def test_sse_stream_employer_403(self):
        emp = _session(); _login(emp, *EMP)
        tok = emp.get(f"{API}/auth/sse-token", timeout=30).json()["token"]
        r = requests.get(f"{API}/talent/me/broadcasts/stream?token={tok}", timeout=10, stream=True)
        assert r.status_code == 403

    def test_sse_stream_hello_and_broadcast_event(self):
        # Setup: employer and talent
        tal = _session(); tuser = _login(tal, *TALENT)
        sse_tok = tal.get(f"{API}/auth/sse-token", timeout=30).json()["token"]

        emp = _session(); _login(emp, *EMP)
        emp.post(f"{API}/shortlist", json={"talent_id": tuser["id"], "talent_name": "Talent", "is_curated": False}, timeout=30)

        # Container to hold received events from stream thread
        received: list = []
        error_holder: list = []

        def consume():
            try:
                with requests.get(f"{API}/talent/me/broadcasts/stream?token={sse_tok}",
                                  stream=True, timeout=20) as r:
                    assert r.status_code == 200, f"stream status {r.status_code}"
                    assert "text/event-stream" in r.headers.get("content-type", ""), r.headers
                    for line in r.iter_lines(decode_unicode=True):
                        if line is None:
                            continue
                        if line.startswith("data:"):
                            try:
                                payload = json.loads(line[5:].strip())
                                received.append(payload)
                                if payload.get("type") == "broadcast":
                                    return
                            except Exception:
                                pass
                        if len(received) >= 5:
                            return
            except Exception as e:
                error_holder.append(str(e))

        t = threading.Thread(target=consume, daemon=True)
        t.start()

        # Wait a moment for stream to connect and hello event to arrive
        time.sleep(2.5)

        # Fire a broadcast
        msg = f"TEST_sse_{uuid.uuid4().hex[:8]}"
        r = emp.post(f"{API}/shortlist/broadcast", json={"subject": "Live!", "message": msg}, timeout=30)
        assert r.status_code == 200

        # Wait up to ~8s for the broadcast event
        t.join(timeout=8)

        if error_holder:
            pytest.fail(f"stream error: {error_holder}")

        # We expect at least one 'hello' and one 'broadcast'
        types = [e.get("type") for e in received]
        assert "hello" in types, f"no hello event; received: {received}"
        bc = next((e for e in received if e.get("type") == "broadcast"), None)
        assert bc is not None, f"no broadcast event within 8s; received: {received}"
        assert bc.get("message") == msg
        assert "employer_name" in bc
        assert "id" in bc


# ============ Admin routes (extracted to routes/admin.py) ============
class TestAdminRoutes:
    def _admin(self):
        s = _session(); _login(s, *ADMIN); return s

    def test_bank_transfers_list(self):
        r = self._admin().get(f"{API}/admin/bank-transfers", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_bank_transfers_anonymous_401(self):
        r = requests.get(f"{API}/admin/bank-transfers", timeout=30)
        assert r.status_code == 401

    def test_bank_transfers_non_admin_403(self):
        tal = _session(); _login(tal, *TALENT)
        r = tal.get(f"{API}/admin/bank-transfers", timeout=30)
        assert r.status_code == 403

    def test_reviews_list(self):
        r = self._admin().get(f"{API}/admin/reviews", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_grievances_list(self):
        r = self._admin().get(f"{API}/admin/grievances", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_payouts_runs_list(self):
        r = self._admin().get(f"{API}/admin/payouts/runs", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_payouts_run_create(self):
        r = self._admin().post(f"{API}/admin/payouts/run", json={
            "period_start": "2026-01-01", "period_end": "2026-01-31", "currency": "usd",
        }, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "run" in d and "payouts" in d
        assert d["run"]["period_start"] == "2026-01-01"

    def test_rate_nudge_scan(self):
        r = self._admin().post(f"{API}/admin/rate-nudges/scan", timeout=120)
        assert r.status_code == 200
        d = r.json()
        for k in ("checked", "nudged", "threshold_pct", "scanned_at"):
            assert k in d
        assert d["threshold_pct"] == 15

    def test_scheduler_running(self):
        r = self._admin().get(f"{API}/admin/scheduler", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("running") is True
        assert any(j.get("id") == "monthly_rate_nudge_scan" for j in d.get("jobs", []))

    def test_review_reject_404(self):
        r = self._admin().post(f"{API}/admin/reviews/nonexistent-id/reject", timeout=30)
        assert r.status_code == 404


# ============ Register endpoint accepts new industries ============
class TestRegisterWithNewIndustry:
    def test_register_with_new_industry(self):
        s = _session()
        email = f"TEST_newind_{uuid.uuid4().hex[:8]}@test.io"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "Employer@2026",
            "name": "TEST NewInd", "role": "employer",
            "company_industry": "Cybersecurity",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["profile"]["company_industry"] == "Cybersecurity"

    def test_register_with_legacy_industry_rejected(self):
        s = _session()
        email = f"TEST_legind_{uuid.uuid4().hex[:8]}@test.io"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "Employer@2026",
            "name": "TEST LegInd", "role": "employer",
            "company_industry": "Series-B fintechs",
        }, timeout=30)
        assert r.status_code == 400
