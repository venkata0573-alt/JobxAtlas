"""Iteration 26 tests: email verification magic-link, company + BGV verification,
admin approval flow, verified badges, and custom project template."""
import os
import time
import pytest
import requests

def _load_frontend_env_url():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env_url() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

ADMIN = ("admin@talenthub.io", "Admin@2026")
EMPLOYER = ("emp-series-b-fintechs@test.io", "Employer@2026")
TALENT = ("talent@test.io", "Talent@2026")

NEW_TALENT_EMAIL = f"newverify2_{int(time.time())}@test.io"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def employer_session():
    return _login(*EMPLOYER)


@pytest.fixture(scope="module")
def talent_session():
    return _login(*TALENT)


# ---------- Register + email verification ----------
def test_register_new_user_returns_unverified():
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={
        "email": NEW_TALENT_EMAIL, "password": "Testing@2026",
        "name": "New Verify", "role": "talent"
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("email_verified") is False
    assert data.get("verification_status") == "none"


def test_verify_email_flow(admin_session):
    # Fetch token
    r = admin_session.get(f"{API}/admin/users", params={"q": NEW_TALENT_EMAIL.split("@")[0]})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    match = [u for u in items if u["email"] == NEW_TALENT_EMAIL]
    assert match, f"user not found in {items}"
    token = match[0].get("email_verification_token")
    assert token, f"no email_verification_token on doc: {match[0]}"

    # First call succeeds
    r = requests.get(f"{API}/auth/verify-email", params={"token": token})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["email"] == NEW_TALENT_EMAIL

    # Second call with same (consumed) token -> 400
    r2 = requests.get(f"{API}/auth/verify-email", params={"token": token})
    assert r2.status_code == 400


def test_resend_verification_already_verified(talent_session):
    # Ensure talent is verified first
    # talent@test.io may or may not be email_verified; use verify-email if needed.
    me = talent_session.get(f"{API}/auth/me").json()
    if not me.get("email_verified"):
        # rotate token via resend then verify
        talent_session.post(f"{API}/auth/resend-verification")
        # get token via admin
        adm = _login(*ADMIN)
        r = adm.get(f"{API}/admin/users", params={"q": "talent@test.io"})
        token = next(u["email_verification_token"] for u in r.json()["items"]
                     if u["email"] == "talent@test.io")
        requests.get(f"{API}/auth/verify-email", params={"token": token})
    r = talent_session.post(f"{API}/auth/resend-verification")
    assert r.status_code == 200
    assert r.json().get("already_verified") is True


def test_resend_verification_unverified_rotates_token(admin_session):
    # Register fresh user
    email = f"rotate_{int(time.time())}@test.io"
    s = requests.Session()
    s.post(f"{API}/auth/register", json={
        "email": email, "password": "Testing@2026",
        "name": "Rotate", "role": "talent"
    })
    r1 = admin_session.get(f"{API}/admin/users", params={"q": email.split("@")[0]})
    tok1 = next(u["email_verification_token"] for u in r1.json()["items"] if u["email"] == email)

    r = s.post(f"{API}/auth/resend-verification")
    assert r.status_code == 200

    r2 = admin_session.get(f"{API}/admin/users", params={"q": email.split("@")[0]})
    tok2 = next(u["email_verification_token"] for u in r2.json()["items"] if u["email"] == email)
    assert tok1 != tok2


# ---------- Company verification submit ----------
def test_company_verification_submit(employer_session):
    r = employer_session.post(f"{API}/verification/company", json={
        "company_name": "TestCo",
        "company_registration_number": "REG-123",
        "tax_id": "TAX-999",
        "company_website": "https://testco.example",
        "company_size": "11-50",
        "year_founded": 2020,
        "country": "UK"
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"

    # /verification/me confirms pending
    me = employer_session.get(f"{API}/verification/me").json()
    assert me["verification_status"] == "pending"


def test_company_verification_talent_forbidden(talent_session):
    r = talent_session.post(f"{API}/verification/company", json={
        "company_name": "Nope"
    })
    assert r.status_code == 403


# ---------- BGV submit ----------
def test_bgv_valid(talent_session):
    payload = {
        "work_history": [{"company": "PrevCo", "role": "Eng", "start": "2020-01"}],
        "references": [
            {"name": "Ref A", "email": "refa@test.io", "relationship": "Manager"},
            {"name": "Ref B", "email": "refb@test.io", "relationship": "Peer"},
        ],
        "linkedin_url": "https://linkedin.com/in/test"
    }
    r = talent_session.post(f"{API}/verification/bgv", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"

    me = talent_session.get(f"{API}/verification/me").json()
    assert me["verification_status"] == "pending"


def test_bgv_insufficient_refs(talent_session):
    r = talent_session.post(f"{API}/verification/bgv", json={
        "work_history": [{"company": "X", "role": "Y", "start": "2020"}],
        "references": [{"name": "R", "email": "r@test.io", "relationship": "M"}]
    })
    assert r.status_code == 400


def test_bgv_zero_work_history(talent_session):
    r = talent_session.post(f"{API}/verification/bgv", json={
        "work_history": [],
        "references": [
            {"name": "A", "email": "a@t.io", "relationship": "M"},
            {"name": "B", "email": "b@t.io", "relationship": "P"},
        ]
    })
    assert r.status_code == 400


# ---------- Admin verifications listing + approve/reject ----------
def test_admin_list_pending(admin_session):
    r = admin_session.get(f"{API}/admin/verifications", params={"status": "pending"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert isinstance(items, list)


def test_admin_reject_requires_notes(admin_session, employer_session):
    me = employer_session.get(f"{API}/auth/me").json()
    uid = me["id"]
    # First re-submit as pending to be safe
    employer_session.post(f"{API}/verification/company", json={
        "company_name": "TestCo", "company_size": "11-50", "year_founded": 2020
    })
    r = admin_session.post(f"{API}/admin/verifications/{uid}/reject", json={})
    assert r.status_code == 400


def test_admin_approve_flow(admin_session, employer_session, talent_session):
    # Re-put employer + talent into pending state
    employer_session.post(f"{API}/verification/company", json={
        "company_name": "TestCo", "company_size": "11-50", "year_founded": 2020
    })
    talent_session.post(f"{API}/verification/bgv", json={
        "work_history": [{"company": "P", "role": "E", "start": "2020"}],
        "references": [
            {"name": "A", "email": "a@t.io", "relationship": "M"},
            {"name": "B", "email": "b@t.io", "relationship": "P"},
        ]
    })
    emp_me = employer_session.get(f"{API}/auth/me").json()
    tal_me = talent_session.get(f"{API}/auth/me").json()

    r1 = admin_session.post(f"{API}/admin/verifications/{emp_me['id']}/approve",
                            json={"notes": "ok"})
    assert r1.status_code == 200 and r1.json()["status"] == "verified"

    r2 = admin_session.post(f"{API}/admin/verifications/{tal_me['id']}/approve",
                            json={"notes": "ok"})
    assert r2.status_code == 200 and r2.json()["status"] == "verified"


# ---------- Badge exposure ----------
def test_talent_list_exposes_is_verified(talent_session):
    r = talent_session.get(f"{API}/talent")
    assert r.status_code == 200
    talents = r.json()
    any_verified = any(t.get("is_verified") is True for t in talents)
    assert any_verified, "expected at least one verified talent"


def test_employers_list_exposes_is_verified(talent_session):
    r = talent_session.get(f"{API}/employers")
    assert r.status_code == 200
    body = r.json()
    employers = body["items"] if isinstance(body, dict) else body
    any_verified = any(e.get("is_verified") is True for e in employers)
    assert any_verified, "expected at least one verified employer"


# ---------- Custom project lead ----------
def test_custom_project_lead_success():
    payload = {
        "template_id": "custom",
        "custom_title": "My custom project",
        "custom_industry": "FinTech",
        "custom_summary": "Testing",
        "company_name": "AcmeCo",
        "contact_name": "Jane",
        "contact_email": "jane@acme.io",
        "duration_months": 6,
        "assigned_team": [
            {"role": "Senior Engineer", "seat_index": 1, "rate": 120},
            {"role": "Designer", "seat_index": 2, "rate": 90},
        ]
    }
    r = requests.post(f"{API}/projects/lead", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "quote" in body
    q = body["quote"]
    assert q["monthly_client_price"] > 0
    assert q["total_client_price"] > 0
    assert "blended_margin_pct" in q


def test_custom_project_lead_requires_seats():
    payload = {
        "template_id": "custom",
        "custom_title": "Empty",
        "custom_industry": "Other",
        "company_name": "AcmeCo",
        "contact_name": "Jane",
        "contact_email": "jane@acme.io",
        "duration_months": 6,
    }
    r = requests.post(f"{API}/projects/lead", json=payload)
    assert r.status_code == 400
    assert "seat" in r.text.lower()
