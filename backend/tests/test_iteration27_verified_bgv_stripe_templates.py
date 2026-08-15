"""Iteration 27 tests: verified-only filter, BGV auto-emails + reference check public endpoints,
Stripe card setup checkout, and bulk project templates."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _login(session, email, password):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture
def admin_client():
    s = requests.Session()
    _login(s, "admin@talenthub.io", "Admin@2026")
    return s


@pytest.fixture
def support_client():
    s = requests.Session()
    _login(s, "support1@jobatlas.io", "Support@2026")
    return s


@pytest.fixture
def talent_client():
    s = requests.Session()
    _login(s, "talent@test.io", "Talent@2026")
    return s


@pytest.fixture
def employer_client():
    s = requests.Session()
    _login(s, "emp-series-b-fintechs@test.io", "Employer@2026")
    return s


# =========================
# Verified-only filter
# =========================
class TestVerifiedOnlyFilter:
    def test_baseline_talent_list(self):
        r = requests.get(f"{API}/talent")
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", data.get("talents", []))
        assert len(items) >= 1, f"expected some talent, got {len(items)}"
        self._baseline = items

    def test_verified_only_filter(self):
        r_all = requests.get(f"{API}/talent")
        r_ver = requests.get(f"{API}/talent?verified_only=true")
        assert r_ver.status_code == 200
        all_items = r_all.json() if isinstance(r_all.json(), list) else r_all.json().get("items", [])
        ver_items = r_ver.json() if isinstance(r_ver.json(), list) else r_ver.json().get("items", [])
        assert len(ver_items) <= len(all_items), "verified subset must be <= all"
        for t in ver_items:
            # each item should be verified
            assert t.get("is_verified") is True or t.get("verification_status") == "verified", \
                f"non-verified item leaked: {t}"


# =========================
# BGV auto-emails + reference check
# =========================
class TestBGVReferenceFlow:
    def test_bgv_submit_creates_reference_checks(self, talent_client):
        payload = {
            "legal_name": "Test Talent",
            "date_of_birth": "1990-01-01",
            "address": "123 Test St",
            "id_type": "passport",
            "id_number": "X12345",
            "work_history": [
                {"company": "Acme Corp", "role": "Engineer", "start": "2020-01", "end": "2022-12"}
            ],
            "references": [
                {"name": "Ref One", "email": f"ref1_{os.urandom(3).hex()}@example.com",
                 "relationship": "manager", "company": "Acme"},
                {"name": "Ref Two", "email": f"ref2_{os.urandom(3).hex()}@example.com",
                 "relationship": "colleague", "company": "Acme"},
            ],
        }
        r = talent_client.post(f"{API}/verification/bgv", json=payload)
        assert r.status_code in (200, 201), f"{r.status_code}: {r.text}"
        data = r.json()
        assert data.get("references_notified") == 2, f"expected references_notified=2, got {data}"

    def test_admin_ref_check_list_and_public_flow(self, admin_client, talent_client, support_client, employer_client):
        # get talent id via /auth/me
        me = talent_client.get(f"{API}/auth/me").json()
        talent_id = me.get("id") or me.get("user", {}).get("id")
        assert talent_id, f"can't determine talent id: {me}"

        # admin list
        r = admin_client.get(f"{API}/admin/reference-checks/{talent_id}")
        assert r.status_code == 200, r.text
        payload = r.json()
        items = payload.get("items", [])
        assert isinstance(items, list) and len(items) >= 1, f"no ref checks returned: {payload}"
        assert "count" in payload and "answered" in payload

        # support scope also has access
        rs = support_client.get(f"{API}/admin/reference-checks/{talent_id}")
        assert rs.status_code == 200, f"support should have access: {rs.status_code} {rs.text}"

        # talent NOT allowed to hit admin endpoint
        rt = talent_client.get(f"{API}/admin/reference-checks/{talent_id}")
        assert rt.status_code == 403, f"talent should be forbidden: {rt.status_code}"

        # employer also forbidden
        re = employer_client.get(f"{API}/admin/reference-checks/{talent_id}")
        assert re.status_code == 403

        # tokens are (correctly) not exposed by admin list — fetch from Mongo directly for testing
        token = None
        try:
            from pymongo import MongoClient
            mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = mc[os.environ.get("DB_NAME", "test_database")]
            doc = db.reference_checks.find_one({"talent_id": talent_id, "response": None})
            if not doc:
                doc = db.reference_checks.find_one({"talent_id": talent_id})
            if doc:
                token = doc.get("token")
        except Exception as e:
            pytest.skip(f"cannot access mongo: {e}")
        assert token, "no reference_check token available for talent"

        # public GET (no auth)
        pub = requests.get(f"{API}/reference-check/{token}")
        assert pub.status_code == 200, f"public GET failed: {pub.status_code} {pub.text}"
        pdata = pub.json()
        for f in ("talent_name", "ref_name", "status"):
            assert f in pdata, f"missing {f} in {pdata}"
        # security: never leak talent_id or token
        assert "talent_id" not in pdata, "talent_id leaked in public payload"
        assert "token" not in pdata, "token leaked in public payload"

        # public POST invalid response
        bad = requests.post(f"{API}/reference-check/{token}", json={"response": "maybe", "note": "bad"})
        assert bad.status_code == 400, f"expected 400 for invalid response, got {bad.status_code}"

        # public POST valid
        if not pdata.get("already_answered"):
            ok = requests.post(f"{API}/reference-check/{token}", json={"response": "yes", "note": "Great engineer"})
            assert ok.status_code == 200, f"valid POST failed: {ok.status_code} {ok.text}"
            odata = ok.json()
            assert odata.get("ok") is True
            assert odata.get("response") in ("yes", "partial", "no")

            # idempotent second post
            again = requests.post(f"{API}/reference-check/{token}", json={"response": "yes", "note": "again"})
            assert again.status_code == 200
            assert again.json().get("already_answered") is True

    def test_public_ref_bogus_token(self):
        r = requests.get(f"{API}/reference-check/nonexistent_token_zzz_123")
        assert r.status_code == 404


# =========================
# Stripe card setup checkout
# =========================
class TestStripeSetupCheckout:
    def test_setup_checkout_employer(self, employer_client):
        r = employer_client.post(f"{API}/billing/setup-checkout", json={"origin_url": "https://example.com"})
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        data = r.json()
        assert data.get("checkout_url", "").startswith("https://checkout.stripe.com/"), data
        assert data.get("session_id", "").startswith("cs_test_"), data
        # second call — session should be fresh but customer id stable (we can't inspect DB from here reliably)
        r2 = employer_client.post(f"{API}/billing/setup-checkout", json={"origin_url": "https://example.com"})
        assert r2.status_code == 200
        assert r2.json().get("session_id") != data.get("session_id"), "session_id should be fresh"

    def test_setup_checkout_talent_forbidden(self, talent_client):
        r = talent_client.post(f"{API}/billing/setup-checkout", json={"origin_url": "https://example.com"})
        assert r.status_code == 403, f"talent must be forbidden, got {r.status_code}"

    def test_setup_status_incomplete(self, employer_client):
        r = employer_client.post(f"{API}/billing/setup-checkout", json={"origin_url": "https://example.com"})
        sid = r.json()["session_id"]
        s = employer_client.get(f"{API}/billing/setup-checkout/status/{sid}")
        assert s.status_code == 200, s.text
        data = s.json()
        assert data.get("ok") is False
        assert "reason" in data
        assert "setup_status" in data["reason"]

    def test_setup_status_bogus(self, employer_client):
        r = employer_client.get(f"{API}/billing/setup-checkout/status/cs_test_bogus_zzz")
        assert r.status_code == 400

    def test_setup_status_cross_user_forbidden(self, employer_client):
        # employer1 creates session
        r = employer_client.post(f"{API}/billing/setup-checkout", json={"origin_url": "https://example.com"})
        sid = r.json()["session_id"]
        # employer2 logs in
        s2 = requests.Session()
        r2 = s2.post(f"{API}/auth/login", json={"email": "emp-health-tech-scale-ups@test.io", "password": "Employer@2026"})
        if r2.status_code != 200:
            pytest.skip("second employer login unavailable")
        cross = s2.get(f"{API}/billing/setup-checkout/status/{sid}")
        assert cross.status_code == 403, f"cross-user must be 403, got {cross.status_code} {cross.text}"


# =========================
# Bulk project templates
# =========================
class TestProjectTemplates:
    def test_templates_list_and_industries(self, employer_client):
        # try public first then employer-auth
        r = requests.get(f"{API}/projects/templates")
        if r.status_code in (401, 403):
            r = employer_client.get(f"{API}/projects/templates")
        assert r.status_code == 200, r.text
        payload = r.json()
        items = payload if isinstance(payload, list) else payload.get("items", payload.get("templates", []))
        assert len(items) >= 20, f"expected >=20 templates, got {len(items)}"

        # count industries
        industries = {}
        for t in items:
            ind = t.get("industry") or t.get("category") or ""
            industries[ind] = industries.get(ind, 0) + 1

        expected_industries = [
            "Financial Services & Fintech",
            "Healthcare & Life Sciences",
            "Retail & E-Commerce",
            "Media & Entertainment",
            "Education & EdTech",
            "Government & Public Sector",
            "AI & Deep Tech",
            "Climate & Sustainability",
        ]
        present_with_2_plus = [i for i in expected_industries if industries.get(i, 0) >= 2]
        assert len(present_with_2_plus) >= 3, \
            f"only {len(present_with_2_plus)} of expected industries have >=2 templates; got {industries}"

    def test_template_detail(self, employer_client):
        r = requests.get(f"{API}/projects/templates")
        if r.status_code in (401, 403):
            r = employer_client.get(f"{API}/projects/templates")
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", r.json().get("templates", []))
        # pick a few to spot check
        for t in items[:5]:
            tid = t.get("id") or t.get("template_id") or t.get("slug")
            if not tid:
                continue
            d = requests.get(f"{API}/projects/templates/{tid}")
            if d.status_code in (401, 403):
                d = employer_client.get(f"{API}/projects/templates/{tid}")
            assert d.status_code == 200, f"template {tid} failed: {d.status_code} {d.text}"
            body = d.json()
            assert "monthly_client_price" in body or "blended_margin_pct" in body, \
                f"pricing fields missing in template detail: {body.keys()}"
