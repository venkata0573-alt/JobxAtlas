"""Iteration 30 backend tests: trust/timeseries + trust/stats regression + CRM."""
import os
import requests
import pytest

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # Fallback: read /app/frontend/.env directly
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return "http://localhost:8001"


BASE = _load_backend_url()
API = BASE + "/api"

EMP = ("emp-series-b-fintechs@test.io", "Employer@2026")
TAL = ("talent@test.io", "Talent@2026")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email} failed {r.status_code} {r.text[:200]}"
    return s


# -------- Trust --------
def test_trust_timeseries_shape():
    r = requests.get(f"{API}/trust/timeseries", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "series" in data
    series = data["series"]
    assert len(series) == 30, f"expected 30 buckets, got {len(series)}"
    for row in series:
        for k in ("date", "refs", "engagements", "verified_talents", "verified_companies"):
            assert k in row, f"missing key {k}"
            if k != "date":
                assert isinstance(row[k], int)


def test_trust_stats_regression():
    r = requests.get(f"{API}/trust/stats", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("verified_companies", "verified_talents", "references_validated_last_30d",
              "references_validated_total", "engagements_last_30d", "engagements_total"):
        assert k in d, f"missing {k}"
        assert isinstance(d[k], int)


# -------- CRM --------
def test_crm_list_as_employer():
    s = _login(*EMP)
    r = s.get(f"{API}/integrations/crm", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)


def test_crm_list_as_talent_ok_empty_or_200():
    s = _login(*TAL)
    r = s.get(f"{API}/integrations/crm", timeout=15)
    # per contract talent should 200 (empty list) OR 403; primary contract is 200
    assert r.status_code in (200, 403), r.status_code
    if r.status_code == 200:
        assert isinstance(r.json().get("items", []), list)


def test_crm_connect_hubspot_bogus_token_400():
    s = _login(*EMP)
    r = s.post(f"{API}/integrations/crm/connect",
               json={"provider": "hubspot", "access_token": "garbage-token-xyz"},
               timeout=20)
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"
