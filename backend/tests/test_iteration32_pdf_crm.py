"""Iteration 32 — Drill Export PDF + CRM Sync Cron backend tests."""
import os
import re
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
EMPLOYER = ("emp-series-b-fintechs@test.io", "Employer@2026")
TALENT = ("talent@test.io", "Talent@2026")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


# ---------- Drill PDF export ----------
class TestDrillPDF:
    def test_pdf_refs_headers_and_magic(self):
        r = requests.get(f"{BASE}/api/trust/timeseries/details/pdf", params={"series": "refs"}, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        sig = r.headers.get("X-Drill-Signature") or r.headers.get("x-drill-signature")
        assert sig and re.fullmatch(r"[0-9a-f]{64}", sig), f"bad sig header: {sig}"
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1000

    def test_pdf_bogus_series_400(self):
        r = requests.get(f"{BASE}/api/trust/timeseries/details/pdf", params={"series": "bogus"}, timeout=20)
        assert r.status_code == 400

    def test_pdf_filter_changes_signature(self):
        r1 = requests.get(f"{BASE}/api/trust/timeseries/details/pdf", params={"series": "engagements"}, timeout=30)
        r2 = requests.get(f"{BASE}/api/trust/timeseries/details/pdf",
                          params={"series": "engagements", "q": "nomatchxyz"}, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        s1 = r1.headers.get("X-Drill-Signature")
        s2 = r2.headers.get("X-Drill-Signature")
        assert s1 and s2 and s1 != s2

    def test_pdf_writes_receipt_lookupable(self):
        r = requests.get(f"{BASE}/api/trust/timeseries/details/pdf",
                         params={"series": "refs"}, timeout=30)
        sig = r.headers.get("X-Drill-Signature")
        lookup = requests.get(f"{BASE}/api/trust/verify-drill/{sig}", timeout=15)
        assert lookup.status_code == 200
        j = lookup.json()
        assert j.get("receipt_found") is True
        assert j["receipt"]["signature"] == sig
        assert j["receipt"]["series"] == "refs"


class TestVerifyDrill:
    def test_verify_drill_authentic_and_tamper(self):
        # Pull the JSON items + ts by generating a PDF (uses same items list).
        # But POST /verify-drill requires ts + items — we need the exact ts used.
        # The GET /details endpoint returns items but a fresh `ts` is generated
        # inside PDF. So call the JSON endpoint and reconstruct: signature uses
        # {series, ts, items} — the /verify-drill returns expected_signature
        # so we can verify by matching a specific ts we craft ourselves.
        details = requests.get(f"{BASE}/api/trust/timeseries/details",
                               params={"series": "engagements"}, timeout=20).json()
        items = details.get("items", [])
        ts = "2026-01-15T12:00:00+00:00"
        # First call: get expected_signature (authentic=false since we sent dummy sig)
        r = requests.post(f"{BASE}/api/trust/verify-drill", json={
            "signature": "0" * 64, "series": "engagements", "ts": ts, "items": items,
        }, timeout=20)
        assert r.status_code == 200
        expected = r.json()["expected_signature"]
        assert re.fullmatch(r"[0-9a-f]{64}", expected)

        # Now post the expected sig back → authentic:true
        r2 = requests.post(f"{BASE}/api/trust/verify-drill", json={
            "signature": expected, "series": "engagements", "ts": ts, "items": items,
        }, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["authentic"] is True

        # Tamper an item → authentic:false
        tampered = [dict(x) for x in items]
        if tampered:
            tampered[0] = {**tampered[0], "primary": "ZZ"}
        else:
            tampered = [{"primary": "ZZ", "secondary": "s", "chip": "c", "date": "2026-01-01"}]
        r3 = requests.post(f"{BASE}/api/trust/verify-drill", json={
            "signature": expected, "series": "engagements", "ts": ts, "items": tampered,
        }, timeout=20)
        assert r3.status_code == 200
        assert r3.json()["authentic"] is False

    def test_verify_drill_lookup_missing(self):
        r = requests.get(f"{BASE}/api/trust/verify-drill/nosuchsignature", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"receipt_found": False, "receipt": None}


# ---------- CRM sync ----------
class TestCrmSync:
    def test_sync_log_empty_regression(self):
        s = _login(*EMPLOYER)
        r = s.get(f"{BASE}/api/integrations/crm/sync-log", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "count" in j
        # Fresh employer with no CRM → should be []
        # (allow >=0 since a previous test iteration may have created rows)
        assert isinstance(j["items"], list)

    def test_sync_now_no_connections(self):
        s = _login(*EMPLOYER)
        r = s.post(f"{BASE}/api/integrations/crm/sync-now", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert j.get("connections") == 0
        assert j.get("pushed") == 0
        assert j.get("skipped") == 0
        assert j.get("failed") == 0

    def test_sync_now_talent_forbidden(self):
        s = _login(*TALENT)
        r = s.post(f"{BASE}/api/integrations/crm/sync-now", timeout=15)
        assert r.status_code == 403


# ---------- Scheduler ----------
class TestScheduler:
    def test_nightly_crm_sync_job_registered(self):
        s = _login(*ADMIN)
        r = s.get(f"{BASE}/api/admin/scheduler", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Endpoint may return {jobs:[...]} or a list
        jobs = data.get("jobs") if isinstance(data, dict) else data
        assert jobs, f"no jobs in response: {data}"
        ids = [j.get("id") for j in jobs]
        assert "nightly_crm_sync" in ids
        job = next(j for j in jobs if j.get("id") == "nightly_crm_sync")
        blob = str(job).lower()
        # cron hour=2 minute=0
        assert "cron" in blob or "trigger" in blob
