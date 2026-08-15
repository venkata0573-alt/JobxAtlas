"""Iteration 28 tests: save-as-template, custom template lead, trusted partner
flag, employer KYB perks, verifications-with-refs endpoint."""
import os
import secrets
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return (v or "").rstrip("/")


BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL is required"

ADMIN_EMAIL = "admin@talenthub.io"
ADMIN_PW = "Admin@2026"
SUPPORT_EMAIL = "support1@jobatlas.io"
SUPPORT_PW = "Support@2026"
TALENT_EMAIL = "talent@test.io"
TALENT_PW = "Talent@2026"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def support():
    return _login(SUPPORT_EMAIL, SUPPORT_PW)


@pytest.fixture(scope="module")
def talent():
    return _login(TALENT_EMAIL, TALENT_PW)


# ---------------- Save as Template ----------------
@pytest.fixture(scope="module")
def a_project_id(admin):
    r = admin.get(f"{BASE_URL}/api/projects/mine", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    if not items:
        pytest.skip("No projects available to save as template")
    # Find a project with assigned_team populated
    for p in items:
        if p.get("assigned_team"):
            return p["id"]
    return items[0]["id"]


@pytest.fixture(scope="module")
def saved_template(admin, a_project_id):
    payload = {
        "title": f"Test blueprint {secrets.token_hex(3)}",
        "industry": "Financial Services & Fintech",
        "summary": "Real deal template",
    }
    r = admin.post(f"{BASE_URL}/api/admin/projects/{a_project_id}/save-as-template",
                   json=payload, timeout=15)
    assert r.status_code == 200, f"save-as-template failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("ok") is True
    tpl = data["template"]
    assert tpl["id"].startswith("custom-")
    assert tpl["source_project_id"] == a_project_id
    assert tpl["industry"] == payload["industry"]
    assert tpl["title"] == payload["title"]
    assert isinstance(tpl.get("team"), list) and len(tpl["team"]) > 0
    for seat in tpl["team"]:
        assert "rate_range" in seat
        low, high = seat["rate_range"]
        assert low < high
    return tpl


def test_save_as_template_superadmin(saved_template):
    assert saved_template["id"].startswith("custom-")


def test_save_as_template_support_forbidden(support, a_project_id):
    r = support.post(
        f"{BASE_URL}/api/admin/projects/{a_project_id}/save-as-template",
        json={"title": "Nope", "industry": "Financial Services & Fintech", "summary": "x"},
        timeout=15,
    )
    assert r.status_code == 403, f"expected 403 for support scope, got {r.status_code} {r.text}"


def test_custom_template_in_library(admin, saved_template):
    r = admin.get(f"{BASE_URL}/api/projects/templates", timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data.get("templates") or data.get("items") or (data if isinstance(data, list) else [])
    ids = [t["id"] for t in items]
    assert saved_template["id"] in ids


def test_custom_template_detail_has_pricing(admin, saved_template):
    r = admin.get(f"{BASE_URL}/api/projects/templates/{saved_template['id']}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("monthly_client_price", "total_client_price", "blended_margin_pct"):
        assert key in data, f"missing {key} in template detail: {list(data.keys())}"


def test_lead_against_custom_template(admin, saved_template):
    # Use assigned_team from template as the concrete team
    team = []
    idx = 1
    for seat in saved_template["team"]:
        low, high = seat["rate_range"]
        for _ in range(int(seat.get("count") or 1)):
            team.append({
                "role": seat["role"],
                "seat_index": idx,
                "talent_name": f"Test Person {secrets.token_hex(2)}",
                "rate": (low + high) // 2,
            })
            idx += 1
    payload = {
        "template_id": saved_template["id"],
        "company_name": "TestCo Custom",
        "contact_name": "Q A",
        "contact_email": f"qa_{secrets.token_hex(3)}@test.io",
        "duration_months": 6,
        "assigned_team": team,
    }
    r = admin.post(f"{BASE_URL}/api/projects/lead", json=payload, timeout=15)
    assert r.status_code == 200, f"lead failed: {r.status_code} {r.text}"
    assert r.json().get("ok") is True


# ---------------- Trusted Partner ----------------
def test_trusted_partner_fields_on_talent_list(admin):
    r = admin.get(f"{BASE_URL}/api/talent", timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    assert len(items) > 0
    for t in items:
        assert "is_trusted_partner" in t, f"missing is_trusted_partner on {t.get('id')}"
        assert "completed_engagements" in t
        assert "avg_rating" in t
        assert isinstance(t["is_trusted_partner"], bool)


# ---------------- Employer KYB perks ----------------
@pytest.fixture(scope="module")
def fresh_employer():
    email = f"kybperks_{secrets.token_hex(4)}@test.io"
    pw = "Test@2026"
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": email, "password": pw, "name": "KYB Test", "role": "employer"},
                      timeout=15)
    assert r.status_code in (200, 201), f"register: {r.status_code} {r.text}"
    s = _login(email, pw)
    # Fetch id
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
    uid = me.get("id") or me.get("user", {}).get("id")
    return {"email": email, "session": s, "id": uid}


def _submit_company_verification(session):
    payload = {
        "company_name": "TestCo KYB",
        "company_website": "https://testco.example.com",
        "company_registration_no": "REG-" + secrets.token_hex(3),
        "company_country": "US",
        "contact_role": "CEO",
    }
    r = session.post(f"{BASE_URL}/api/verification/company", json=payload, timeout=15)
    return r


def test_kyb_perks_grant_and_replay_guard(admin, fresh_employer):
    r = _submit_company_verification(fresh_employer["session"])
    assert r.status_code in (200, 201), f"verification/company: {r.status_code} {r.text}"

    # Check hours_balance before approve
    before = admin.get(f"{BASE_URL}/api/admin/users/{fresh_employer['id']}", timeout=15).json()
    hours_before = int((before.get("user") or before).get("hours_balance") or 0)

    r = admin.post(f"{BASE_URL}/api/admin/verifications/{fresh_employer['id']}/approve",
                   json={"notes": "ok"}, timeout=15)
    assert r.status_code == 200, f"approve: {r.status_code} {r.text}"
    body = r.json()
    perks = body.get("perks_granted") or {}
    assert perks.get("hours_credited") == 10, f"perks={perks}"
    assert perks.get("hero_placement") is True

    after = admin.get(f"{BASE_URL}/api/admin/users/{fresh_employer['id']}", timeout=15).json()
    u = after.get("user") or after
    assert int(u.get("hours_balance") or 0) == hours_before + 10
    assert u.get("hero_placement") is True
    assert u.get("kyb_perks_granted") is True

    # Re-submit + re-approve → no double credit
    r2 = _submit_company_verification(fresh_employer["session"])
    assert r2.status_code in (200, 201)
    r3 = admin.post(f"{BASE_URL}/api/admin/verifications/{fresh_employer['id']}/approve",
                    json={"notes": "again"}, timeout=15)
    assert r3.status_code == 200
    perks2 = r3.json().get("perks_granted") or {}
    assert not perks2, f"expected empty perks on replay, got {perks2}"

    final = admin.get(f"{BASE_URL}/api/admin/users/{fresh_employer['id']}", timeout=15).json()
    uf = final.get("user") or final
    assert int(uf.get("hours_balance") or 0) == hours_before + 10, "double-credit occurred!"


# ---------------- Verifications with refs ----------------
def test_verifications_with_refs_moderation(admin):
    r = admin.get(f"{BASE_URL}/api/admin/verifications-with-refs?status=pending", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    for it in data["items"]:
        assert "reference_summary" in it
        s = it["reference_summary"]
        for k in ("total", "yes", "partial", "no", "pending"):
            assert k in s
        assert "reference_checks" in it
        assert isinstance(it["reference_checks"], list)


def test_verifications_with_refs_support_allowed(support):
    r = support.get(f"{BASE_URL}/api/admin/verifications-with-refs?status=pending", timeout=15)
    assert r.status_code == 200


def test_verifications_with_refs_talent_forbidden(talent):
    r = talent.get(f"{BASE_URL}/api/admin/verifications-with-refs?status=pending", timeout=15)
    assert r.status_code == 403
