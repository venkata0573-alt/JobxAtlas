"""Iteration 8: Industry filter on /api/talent + profile industries field."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TALENT = {"email": "talent@test.io", "password": "Talent@2026"}


@pytest.fixture(scope="module")
def talent_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=TALENT)
    assert r.status_code == 200, r.text
    return s


def test_put_profile_industries(talent_session):
    payload = {
        "name": "Test Talent",
        "industries": ["SaaS & Enterprise Software", "Financial Services & Fintech"],
    }
    r = talent_session.put(f"{API}/profile", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    prof = data.get("profile") or data.get("user", {}).get("profile") or {}
    inds = prof.get("industries", [])
    assert "SaaS & Enterprise Software" in inds
    assert "Financial Services & Fintech" in inds


def test_talent_list_filter_by_saas():
    r = requests.get(f"{API}/talent", params={"industry": "SaaS & Enterprise Software"})
    assert r.status_code == 200, r.text
    data = r.json()
    talents = data if isinstance(data, list) else data.get("talents", data.get("items", []))
    assert len(talents) >= 1
    # At least one should have SaaS tagged
    found = False
    for t in talents:
        prof = t.get("profile", {}) or {}
        if "SaaS & Enterprise Software" in (prof.get("industries") or []):
            found = True
            break
    assert found, f"No talent with SaaS industry found: {talents}"


def test_talent_list_filter_healthcare_empty():
    r = requests.get(f"{API}/talent", params={"industry": "Healthcare & Life Sciences"})
    assert r.status_code == 200, r.text
    data = r.json()
    talents = data if isinstance(data, list) else data.get("talents", data.get("items", []))
    assert len(talents) == 0, f"Expected 0 talents, got {len(talents)}"


def test_talent_list_no_filter_returns_all():
    r = requests.get(f"{API}/talent")
    assert r.status_code == 200
    data = r.json()
    talents = data if isinstance(data, list) else data.get("talents", data.get("items", []))
    assert len(talents) >= 26, f"Expected >=26, got {len(talents)}"


def test_marketplace_industries_regression():
    r = requests.get(f"{API}/marketplace/industries")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))
