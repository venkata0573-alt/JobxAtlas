"""Iteration 29 backend tests:
- /api/trust/stats public shape
- Trusted-partner sort on /api/talent
- BGV auto-approve on 2 YES / 0 NO / email_verified
- Captcha bypass when TURNSTILE_SECRET_KEY unset
- CRM connect validation (hubspot bogus token, salesforce missing instance_url)
"""
import os
import secrets
import requests
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to frontend/.env in this container
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

API = f"{BASE_URL}/api"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

ADMIN_EMAIL = "admin@talenthub.io"
ADMIN_PW = "Admin@2026"


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return s


# ---------------- /trust/stats ----------------
def test_trust_stats_public_no_auth():
    r = requests.get(f"{API}/trust/stats")
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("verified_companies", "verified_talents",
              "references_validated_last_30d", "references_validated_total",
              "engagements_last_30d", "engagements_total"):
        assert k in data, f"missing {k}"
        assert isinstance(data[k], int), f"{k} is {type(data[k])}"
    assert "as_of" in data and isinstance(data["as_of"], str)
    # ISO-ish
    assert "T" in data["as_of"]


# ---------------- Trusted Partner sort ----------------
def test_talent_list_trusted_partner_sort():
    r = requests.get(f"{API}/talent")
    assert r.status_code == 200, r.text
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else body
    assert isinstance(items, list) and len(items) > 0

    any_trusted = any(x.get("is_trusted_partner") for x in items)
    any_verified = any(x.get("is_verified") for x in items)
    if any_trusted:
        assert items[0]["is_trusted_partner"] is True
    elif any_verified:
        assert items[0].get("is_verified") is True
    # sanity: field shape present on every row
    for x in items:
        assert "is_trusted_partner" in x
        assert "is_verified" in x or "verification_status" in x


# ---------------- Captcha bypass when unset ----------------
def test_register_no_turnstile_ok():
    email = f"cap_{secrets.token_hex(4)}@test.io"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@2026",
        "name": "Cap Test", "role": "talent",
    })
    assert r.status_code == 200, r.text
    assert r.json().get("email") == email


# ---------------- BGV auto-approve rule ----------------
@pytest.fixture(scope="module")
def bgv_talent(db, admin_session):
    email = "bgv-auto@test.io"
    # Fresh — delete any prior state (test hygiene)
    db.users.delete_many({"email": email})
    db.reference_checks.delete_many({"ref_email": {"$in": [
        "r1@ex.io", "r2@ex.io", "r3@ex.io",
    ]}})
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@2026",
        "name": "BGV Auto", "role": "talent",
    })
    assert r.status_code == 200, r.text
    # grab email token from db
    u = db.users.find_one({"email": email})
    tok = u.get("email_verification_token")
    assert tok, "no verification token stored"
    v = requests.get(f"{API}/auth/verify-email", params={"token": tok})
    assert v.status_code == 200, v.text
    return {"session": s, "email": email, "uid": u["id"]}


def test_bgv_auto_approve(db, bgv_talent):
    s = bgv_talent["session"]
    uid = bgv_talent["uid"]
    # Submit BGV with 3 refs
    payload = {
        "work_history": [{"company": "Acme", "role": "Eng",
                          "start": "2020-01", "end": "2023-12",
                          "description": "did stuff"}],
        "references": [
            {"name": "R One", "email": "r1@ex.io", "relationship": "manager", "company": "Acme"},
            {"name": "R Two", "email": "r2@ex.io", "relationship": "peer", "company": "Acme"},
            {"name": "R Three", "email": "r3@ex.io", "relationship": "peer", "company": "Beta"},
        ],
        "government_id_url": "https://ex.io/id.pdf",
        "linkedin_url": "https://linkedin.com/in/bgv-auto",
    }
    r = s.post(f"{API}/verification/bgv", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["references_notified"] == 3

    # Grab 3 ref tokens from db
    refs = list(db.reference_checks.find({"talent_id": uid}).sort("sent_at", 1))
    assert len(refs) == 3

    # First "yes" — must NOT auto-approve yet
    r1 = requests.post(f"{API}/reference-check/{refs[0]['token']}",
                       json={"response": "yes", "note": "great"})
    assert r1.status_code == 200
    me1 = s.get(f"{API}/verification/me").json()
    assert me1["verification_status"] == "pending", me1

    # Second "yes" — auto-approve fires
    r2 = requests.post(f"{API}/reference-check/{refs[1]['token']}",
                       json={"response": "yes", "note": "solid"})
    assert r2.status_code == 200
    me2 = s.get(f"{API}/verification/me").json()
    assert me2["verification_status"] == "verified", me2
    u = db.users.find_one({"id": uid})
    assert u.get("verified_by") == "auto-bgv-rule", u.get("verified_by")


def test_bgv_no_answer_does_not_auto_approve(db):
    """Isolated: 2 YES + 1 NO -> should NOT stay verified via auto-rule (no
    auto-approval fires if any 'no' present)."""
    email = f"bgvno_{secrets.token_hex(3)}@test.io"
    db.users.delete_many({"email": email})
    s = requests.Session()
    assert s.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@2026", "name": "BGV No", "role": "talent",
    }).status_code == 200
    u = db.users.find_one({"email": email})
    assert requests.get(f"{API}/auth/verify-email",
                        params={"token": u["email_verification_token"]}).status_code == 200
    payload = {
        "work_history": [{"company": "A", "role": "E", "start": "2020-01",
                          "end": "2022-12", "description": ""}],
        "references": [
            {"name": "N1", "email": f"n1_{secrets.token_hex(2)}@x.io", "relationship": "mgr"},
            {"name": "N2", "email": f"n2_{secrets.token_hex(2)}@x.io", "relationship": "peer"},
            {"name": "N3", "email": f"n3_{secrets.token_hex(2)}@x.io", "relationship": "peer"},
        ],
    }
    assert s.post(f"{API}/verification/bgv", json=payload).status_code == 200
    refs = list(db.reference_checks.find({"talent_id": u["id"]}).sort("sent_at", 1))
    assert len(refs) == 3
    # 1 NO, then 2 YES
    assert requests.post(f"{API}/reference-check/{refs[0]['token']}",
                        json={"response": "no", "note": "fake"}).status_code == 200
    assert requests.post(f"{API}/reference-check/{refs[1]['token']}",
                        json={"response": "yes"}).status_code == 200
    assert requests.post(f"{API}/reference-check/{refs[2]['token']}",
                        json={"response": "yes"}).status_code == 200
    me = s.get(f"{API}/verification/me").json()
    assert me["verification_status"] == "pending", me
    u2 = db.users.find_one({"id": u["id"]})
    assert u2.get("verified_by") != "auto-bgv-rule"


# ---------------- CRM Integrations ----------------
@pytest.fixture(scope="module")
def employer_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "emp-series-b-fintechs@test.io",
                     "password": "Employer@2026"})
    assert r.status_code == 200, r.text
    return s


def test_crm_hubspot_bogus_token_400(employer_session):
    r = employer_session.post(f"{API}/integrations/crm/connect",
                              json={"provider": "hubspot",
                                    "access_token": "pat-na1-bogus-xxxxx"})
    assert r.status_code == 400, r.text
    assert "hubspot" in r.text.lower() and ("could not verify" in r.text.lower() or "verify" in r.text.lower())


def test_crm_salesforce_missing_instance_url_400(employer_session):
    r = employer_session.post(f"{API}/integrations/crm/connect",
                              json={"provider": "salesforce",
                                    "access_token": "bogus"})
    assert r.status_code == 400, r.text
    assert "instance_url" in r.text.lower() or "instance url" in r.text.lower()


def test_crm_list_and_delete(employer_session):
    r = employer_session.get(f"{API}/integrations/crm")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    r2 = employer_session.delete(f"{API}/integrations/crm/hubspot")
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2.get("ok") is True
    assert body2.get("deleted") == 0
