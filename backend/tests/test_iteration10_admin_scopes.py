"""Iteration 10 tests — assemble team, /api/employers, admin scopes & staff/support/customization."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@talenthub.io", "Admin@2026")
SUPPORT = ("support1@jobatlas.io", "Support@2026")
TALENT = ("talent@test.io", "Talent@2026")
EMPLOYER = ("emp-series-b-fintechs@test.io", "Employer@2026")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_client():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def talent_client():
    return _login(*TALENT)


@pytest.fixture(scope="module")
def employer_client():
    try:
        return _login(*EMPLOYER)
    except AssertionError:
        pytest.skip("employer seed missing")


# ---------- Projects: team suggestions + lead submission ----------
def test_team_suggestions_fintech():
    r = requests.get(f"{API}/projects/templates/fintech-kyc-aml/team-suggestions", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["template_id"] == "fintech-kyc-aml"
    assert isinstance(d["seats"], list)
    assert len(d["seats"]) >= 1
    seat = d["seats"][0]
    for k in ("role", "seat_index", "rate_range"):
        assert k in seat
    assert "suggested_talent" in seat


def test_submit_project_lead_with_team():
    payload = {
        "template_id": "fintech-kyc-aml",
        "company_name": "TEST_ScopingCo",
        "contact_name": "Test User",
        "contact_email": "test-scoping@example.com",
        "duration_months": 3,
        "notes": "please scope",
        "assigned_team": [{
            "role": "Backend Engineer", "seat_index": 1,
            "talent_id": "t-1", "talent_name": "Alice", "rate": 90, "locked": True,
        }],
        "estimated_monthly_cost": 15000,
        "estimated_total_cost": 45000,
    }
    r = requests.post(f"{API}/projects/lead", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert "id" in d and d["id"]


# ---------- /api/employers ----------
def test_employers_talent_ok(talent_client):
    r = talent_client.get(f"{API}/employers", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d
    if d["items"]:
        item = d["items"][0]
        for k in ("company_name", "company_industry", "hours_balance", "active_engagements"):
            assert k in item, f"missing {k}"


def test_employers_forbidden_for_employer(employer_client):
    r = employer_client.get(f"{API}/employers", timeout=15)
    assert r.status_code == 403


# ---------- Admin /me + scope enforcement ----------
def test_admin_me_superadmin(admin_client):
    r = admin_client.get(f"{API}/admin/me", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "superadmin" in d["effective_scopes"]
    catalog_ids = [s["id"] for s in d["scopes_catalog"]]
    for sid in ("support", "finance", "moderation", "customization", "superadmin"):
        assert sid in catalog_ids
    # superadmin should get all scope IDs as effective
    for sid in catalog_ids:
        assert sid in d["effective_scopes"]


def test_admin_me_support_only():
    s = _login(*SUPPORT)
    r = s.get(f"{API}/admin/me", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["effective_scopes"] == ["support"]


def test_support_scope_restrictions():
    s = _login(*SUPPORT)
    forbidden = ["/admin/staff", "/admin/customization", "/admin/bank-transfers", "/admin/payouts/runs"]
    for p in forbidden:
        r = s.get(f"{API}{p}", timeout=15)
        assert r.status_code == 403, f"{p} expected 403 got {r.status_code}"
    allowed = ["/admin/users", "/admin/grievances"]
    for p in allowed:
        r = s.get(f"{API}{p}", timeout=15)
        assert r.status_code == 200, f"{p} expected 200 got {r.status_code}"


# ---------- Admin staff CRUD ----------
def test_staff_last_superadmin_guard(admin_client):
    # Find admin@talenthub.io ID
    r = admin_client.get(f"{API}/admin/staff", timeout=15)
    assert r.status_code == 200
    staff = r.json()["staff"]
    admin_row = next((s for s in staff if s["email"] == ADMIN[0]), None)
    assert admin_row, "admin@talenthub.io missing from staff list"
    # Try to strip superadmin — must 400
    r = admin_client.patch(f"{API}/admin/staff/{admin_row['id']}",
                            json={"admin_permissions": ["support"]}, timeout=15)
    assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"


def test_staff_create_delete_recreate(admin_client):
    # Delete support1 if present
    r = admin_client.get(f"{API}/admin/staff", timeout=15)
    staff = r.json()["staff"]
    support_row = next((s for s in staff if s["email"] == SUPPORT[0]), None)
    if support_row:
        d = admin_client.delete(f"{API}/admin/staff/{support_row['id']}", timeout=15)
        assert d.status_code == 200
    # Re-create
    r = admin_client.post(f"{API}/admin/staff", json={
        "email": SUPPORT[0], "name": "Support One",
        "password": SUPPORT[1], "admin_permissions": ["support"],
    }, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == SUPPORT[0]
    assert body["admin_permissions"] == ["support"]
    assert "password_hash" not in body
    # Sanity: login works
    s2 = _login(*SUPPORT)
    assert s2.get(f"{API}/admin/me", timeout=15).status_code == 200


# ---------- Support console: notes + adjust ----------
def test_support_notes_and_adjust():
    s = _login(*SUPPORT)
    # find the talent user
    r = s.get(f"{API}/admin/users", params={"q": TALENT[0], "role": "talent"}, timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "talent not found via /admin/users"
    uid = items[0]["id"]
    before = int(items[0].get("hours_balance") or 0)
    # note
    r = s.post(f"{API}/admin/users/{uid}/notes", json={"text": "TEST_note from iteration10"}, timeout=15)
    assert r.status_code in (200, 201)
    assert r.json()["text"] == "TEST_note from iteration10"
    # adjust +5
    r = s.post(f"{API}/admin/users/{uid}/adjust", json={"hours_delta": 5, "reason": "TEST"}, timeout=15)
    assert r.status_code == 200
    r = s.get(f"{API}/admin/users/{uid}", timeout=15)
    assert r.status_code == 200
    after = int(r.json()["user"].get("hours_balance") or 0)
    assert after == before + 5, f"expected {before+5}, got {after}"
    # revert
    s.post(f"{API}/admin/users/{uid}/adjust", json={"hours_delta": -5, "reason": "TEST revert"}, timeout=15)


# ---------- Customization ----------
def test_customization_scope_and_update(admin_client):
    r = admin_client.get(f"{API}/admin/customization", timeout=15)
    assert r.status_code == 200
    original = r.json().get("hero_headline")
    new_val = "TEST_headline iteration10"
    r = admin_client.put(f"{API}/admin/customization", json={"hero_headline": new_val}, timeout=15)
    assert r.status_code == 200
    assert r.json()["hero_headline"] == new_val
    # public
    r = requests.get(f"{API}/customization/public", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["hero_headline"] == new_val
    assert "updated_by" not in d
    # restore
    if original:
        admin_client.put(f"{API}/admin/customization", json={"hero_headline": original}, timeout=15)


def test_customization_forbidden_for_support():
    s = _login(*SUPPORT)
    r = s.get(f"{API}/admin/customization", timeout=15)
    assert r.status_code == 403
    r = s.put(f"{API}/admin/customization", json={"hero_headline": "x"}, timeout=15)
    assert r.status_code == 403
