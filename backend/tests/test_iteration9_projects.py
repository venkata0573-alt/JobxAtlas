"""Iteration 9: Project Delivery workflow tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_IDS = {
    "fintech-kyc-aml", "fintech-payments-integration",
    "healthcare-fhir-ehr", "healthcare-telehealth-mvp",
    "saas-onboarding-revamp", "saas-analytics-dashboard",
    "ecomm-storefront-rebuild", "ai-llm-copilot",
}
EXPECTED_PHASE_NAMES = ["Initiate", "Plan", "Execute", "Monitor & Control", "Close"]


# ---------- GET /api/projects/templates ----------
def test_list_templates():
    r = requests.get(f"{API}/projects/templates", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 8
    ids = {t["id"] for t in data["templates"]}
    assert ids == EXPECTED_IDS, f"Mismatch: {ids ^ EXPECTED_IDS}"
    assert len(data["phases"]) == 5
    names = [p["name"] for p in data["phases"]]
    assert names == EXPECTED_PHASE_NAMES
    for p in data["phases"]:
        assert p.get("gate")
        assert isinstance(p.get("deliverables"), list) and len(p["deliverables"]) > 0
    for t in data["templates"]:
        for k in ("industry", "title", "duration_months", "summary", "team"):
            assert k in t, f"{t['id']} missing {k}"
        assert isinstance(t["team"], list) and len(t["team"]) > 0


def test_list_templates_filter_fintech():
    ind = "Financial Services & Fintech"
    r = requests.get(f"{API}/projects/templates", params={"industry": ind}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert {t["id"] for t in data["templates"]} == {"fintech-kyc-aml", "fintech-payments-integration"}


# ---------- GET /api/projects/templates/{id} ----------
def test_template_detail_kyc():
    r = requests.get(f"{API}/projects/templates/fintech-kyc-aml", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == "fintech-kyc-aml"
    assert d["monthly_headcount"] == 6
    assert d["estimated_monthly_cost"] > 0
    assert d["estimated_total_cost"] > d["estimated_monthly_cost"]
    assert d["estimated_total_cost"] == d["estimated_monthly_cost"] * d["duration_months"]
    assert len(d["phases"]) == 5


def test_template_detail_unknown_404():
    r = requests.get(f"{API}/projects/templates/no-such-template", timeout=15)
    assert r.status_code == 404


# ---------- POST /api/projects/lead ----------
def test_lead_submit_success():
    payload = {
        "template_id": "saas-onboarding-revamp",
        "company_name": "TEST_Acme Corp",
        "contact_name": "TEST_Jane Doe",
        "contact_email": "test_jane@example.com",
        "duration_months": 3,
        "notes": "Need help with onboarding revamp"
    }
    r = requests.post(f"{API}/projects/lead", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d.get("id")
    assert "scoping team" in d.get("message", "").lower()


def test_lead_invalid_template_400():
    payload = {
        "template_id": "does-not-exist",
        "company_name": "TEST_X",
        "contact_name": "TEST_Y",
        "contact_email": "x@y.com",
        "duration_months": 2,
    }
    r = requests.post(f"{API}/projects/lead", json=payload, timeout=15)
    assert r.status_code == 400


def test_lead_missing_fields_422():
    r = requests.post(f"{API}/projects/lead", json={"template_id": "fintech-kyc-aml"}, timeout=15)
    assert r.status_code == 422


# ---------- Regression: landing copy removed contractual language ----------
def test_landing_no_regression_health():
    # Simple smoke test for a couple of existing endpoints
    r = requests.get(f"{API}/marketplace/stats", timeout=15)
    assert r.status_code == 200
    r2 = requests.get(f"{API}/marketplace/industries", timeout=15)
    assert r2.status_code == 200
