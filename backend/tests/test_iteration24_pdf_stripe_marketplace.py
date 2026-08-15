"""Iteration 24 tests: PDF milestone invoice, Stripe milestone checkout,
sell-rate on /api/talent, and marketplace/SEO route extraction."""
import os
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://hourly-talent-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _session(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


# ---------- Session-scoped auth fixtures ----------
@pytest.fixture(scope="session")
def admin_sess():
    return _session("admin@talenthub.io", "Admin@2026")


@pytest.fixture(scope="session")
def emp_linked_sess():
    return _session("emp-series-b-fintechs@test.io", "Employer@2026")


@pytest.fixture(scope="session")
def emp_control_sess():
    return _session("emp-health-tech-scale-ups@test.io", "Employer@2026")


@pytest.fixture(scope="session")
def talent_sess():
    return _session("talent@test.io", "Talent@2026")


# ---------- Seed a project linked to emp-series-b-fintechs ----------
@pytest.fixture(scope="session")
def linked_project(admin_sess):
    """Create a fresh lead + convert to a project linked to the fintech employer."""
    tag = uuid.uuid4().hex[:6]
    payload = {
        "template_id": "fintech-kyc-aml",
        "company_name": f"TEST_Iter24 FinCo {tag}",
        "contact_name": "Iter24 Sponsor",
        "contact_email": "emp-series-b-fintechs@test.io",
        "duration_months": 6,
        "notes": "iter24 test seed",
        "assigned_team": [{"role": "PM", "seat_index": 1, "talent_name": "Rosie", "rate": 140}],
    }
    r = requests.post(f"{API}/projects/lead", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    lead_id = r.json()["id"]
    r2 = admin_sess.post(f"{API}/admin/project-leads/{lead_id}/convert",
                          json={"currency": "usd"}, timeout=30)
    assert r2.status_code == 200, r2.text
    project = r2.json()["project"]
    # fetch milestones
    r3 = admin_sess.get(f"{API}/projects/workspace/{project['id']}", timeout=15)
    assert r3.status_code == 200
    data = r3.json()
    return {"project": project, "milestones": data["milestones"], "invoices": data.get("invoices", [])}


@pytest.fixture(scope="session")
def issued_invoice(admin_sess, linked_project):
    """Issue an invoice against the first pending milestone (as admin)."""
    pid = linked_project["project"]["id"]
    ms = linked_project["milestones"]
    pending = [m for m in ms if m.get("status") == "pending"]
    assert pending, "no pending milestones"
    m = pending[0]
    r = admin_sess.post(f"{API}/projects/workspace/{pid}/milestones/{m['id']}/invoice",
                        timeout=30)
    assert r.status_code == 200, r.text
    invoice = r.json()
    return {"project_id": pid, "milestone_id": m["id"], "invoice": invoice}


# ============================================================
# PDF Invoice Download
# ============================================================
class TestInvoicePdf:
    def test_admin_pdf_download_ok(self, admin_sess, issued_invoice):
        pid = issued_invoice["project_id"]
        iid = issued_invoice["invoice"]["id"]
        r = admin_sess.get(f"{API}/projects/workspace/{pid}/invoices/{iid}/pdf", timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        body = r.content
        assert body[:4] == b"%PDF", f"not a PDF magic: {body[:8]}"
        assert len(body) > 1024, f"PDF too small: {len(body)} bytes"
        # ReportLab produced signature
        assert b"ReportLab" in body, "expected ReportLab producer marker"

    def test_bogus_invoice_id_404(self, admin_sess, issued_invoice):
        pid = issued_invoice["project_id"]
        r = admin_sess.get(f"{API}/projects/workspace/{pid}/invoices/nope-xxx/pdf", timeout=15)
        assert r.status_code == 404

    def test_talent_forbidden_403(self, talent_sess, issued_invoice):
        pid = issued_invoice["project_id"]
        iid = issued_invoice["invoice"]["id"]
        r = talent_sess.get(f"{API}/projects/workspace/{pid}/invoices/{iid}/pdf", timeout=15)
        assert r.status_code == 403, f"expected 403, got {r.status_code}"


# ============================================================
# Stripe milestone checkout
# ============================================================
class TestMilestoneCheckout:
    def test_admin_checkout_creates_session(self, admin_sess, linked_project):
        pid = linked_project["project"]["id"]
        # Pick a milestone that is not the one already invoiced above (or any non-paid)
        r0 = admin_sess.get(f"{API}/projects/workspace/{pid}", timeout=15)
        ms = r0.json()["milestones"]
        target = next((m for m in ms if m.get("status") != "paid"), None)
        assert target
        r = admin_sess.post(
            f"{API}/projects/workspace/{pid}/milestones/{target['id']}/checkout",
            json={"origin_url": "https://example.com"}, timeout=45,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["checkout_url"].startswith("https://checkout.stripe.com/"), d
        assert d.get("session_id")
        assert d.get("invoice_ref")
        # session_id will be used by subsequent tests
        pytest.iter24_session_id = d["session_id"]
        pytest.iter24_checkout_mid = target["id"]
        pytest.iter24_pid = pid

    def test_pending_milestone_auto_issues_invoice(self, admin_sess):
        """The milestone we just paid — if it was pending — should now be invoiced."""
        pid = pytest.iter24_pid
        mid = pytest.iter24_checkout_mid
        r = admin_sess.get(f"{API}/projects/workspace/{pid}", timeout=15)
        m = next((x for x in r.json()["milestones"] if x["id"] == mid), None)
        assert m is not None
        # Should be invoiced or paid at minimum (auto-issued when pending)
        assert m["status"] in ("invoiced", "paid"), f"unexpected status {m['status']}"
        assert m.get("invoice_id")

    def test_talent_checkout_forbidden(self, talent_sess, linked_project):
        pid = linked_project["project"]["id"]
        # Talent shouldn't even see workspace -> 403
        ms = linked_project["milestones"]
        r = talent_sess.post(
            f"{API}/projects/workspace/{pid}/milestones/{ms[0]['id']}/checkout",
            json={"origin_url": "https://example.com"}, timeout=15,
        )
        assert r.status_code == 403

    def test_unlinked_employer_checkout_forbidden(self, emp_control_sess, linked_project):
        pid = linked_project["project"]["id"]
        ms = linked_project["milestones"]
        r = emp_control_sess.post(
            f"{API}/projects/workspace/{pid}/milestones/{ms[0]['id']}/checkout",
            json={"origin_url": "https://example.com"}, timeout=15,
        )
        assert r.status_code == 403

    def test_linked_employer_checkout_ok(self, emp_linked_sess, linked_project):
        pid = linked_project["project"]["id"]
        r0 = emp_linked_sess.get(f"{API}/projects/workspace/{pid}", timeout=15)
        assert r0.status_code == 200
        ms = r0.json()["milestones"]
        target = next((m for m in ms if m.get("status") != "paid"), None)
        assert target
        r = emp_linked_sess.post(
            f"{API}/projects/workspace/{pid}/milestones/{target['id']}/checkout",
            json={"origin_url": "https://example.com"}, timeout=45,
        )
        assert r.status_code == 200, r.text
        assert r.json()["checkout_url"].startswith("https://checkout.stripe.com/")


# ============================================================
# Milestone payment status
# ============================================================
class TestMilestonePaymentStatus:
    def test_status_pending_for_unpaid_session(self, admin_sess):
        sid = getattr(pytest, "iter24_session_id", None)
        if not sid:
            pytest.skip("no session id from checkout test")
        r = admin_sess.get(f"{API}/projects/milestone-payment/status/{sid}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "payment_status" in d
        # Should be 'pending' since we didn't complete Stripe checkout
        assert d["payment_status"] in ("pending", "paid")

    def test_status_404_for_bogus_session(self, admin_sess):
        r = admin_sess.get(f"{API}/projects/milestone-payment/status/cs_bogus_xxx", timeout=15)
        assert r.status_code == 404


# ============================================================
# Sell rate on /api/talent
# ============================================================
class TestTalentSellRate:
    def test_authenticated_talent_list_has_sell_rate(self, admin_sess):
        r = admin_sess.get(f"{API}/talent", timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        with_rate = [t for t in items if (t.get("profile") or {}).get("hourly_rate", 0) > 0]
        assert with_rate, "no talent with hourly_rate>0 to validate"
        for t in with_rate:
            assert "sell_rate" in t, f"missing sell_rate on {t.get('id')}"
            assert "margin_pct" in t, f"missing margin_pct on {t.get('id')}"
            assert t["sell_rate"] > (t["profile"]["hourly_rate"])

    def test_talent_75_gets_88_5(self, admin_sess):
        r = admin_sess.get(f"{API}/talent", timeout=30)
        items = r.json()
        target = next((t for t in items
                       if (t.get("profile") or {}).get("hourly_rate") == 75), None)
        assert target, "no talent found with $75/hr rate"
        # Mid tier -> 18% margin -> 75 * 1.18 = 88.5
        assert target["margin_pct"] == 18
        assert abs(target["sell_rate"] - 88.5) < 0.01


# ============================================================
# Marketplace routes moved to routes/marketplace.py
# ============================================================
class TestMarketplaceRoutes:
    def test_seo_skills(self):
        r = requests.get(f"{API}/seo/skills", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "skills" in d
        assert len(d["skills"]) == 12, f"expected 12 skills, got {len(d['skills'])}"

    def test_seo_city_skills(self):
        r = requests.get(f"{API}/seo/city-skills", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "combos" in d
        assert len(d["combos"]) == 54, f"expected 54 combos, got {len(d['combos'])}"

    def test_marketplace_industries(self):
        r = requests.get(f"{API}/marketplace/industries", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "industries" in d
        assert isinstance(d["industries"], list)
        assert all("label" in i and "count" in i for i in d["industries"])

    def test_marketplace_stats(self):
        r = requests.get(f"{API}/marketplace/stats", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("active_buyers", "industries", "cities_covered",
                  "engagements_total", "engagements_signed"):
            assert k in d

    def test_sitemap_xml(self):
        r = requests.get(f"{API}/sitemap.xml", timeout=15)
        assert r.status_code == 200
        assert "xml" in r.headers.get("content-type", "").lower()
        assert "<urlset" in r.text
        assert "</urlset>" in r.text

    def test_seo_hire_skill_still_in_server(self):
        r = requests.get(f"{API}/seo/hire/react-developers", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "title" in d
        # Talent list must be present (possibly empty)
        assert "talent" in d or "items" in d or "candidates" in d

    def test_seo_hire_city_still_in_server(self):
        r = requests.get(f"{API}/seo/hire-city/react-developers-london", timeout=15)
        assert r.status_code == 200


# ============================================================
# Milestone-already-paid returns 400 (edge)
# ============================================================
class TestAlreadyPaidCheckout:
    def test_checkout_on_paid_milestone_400(self, admin_sess, linked_project):
        """Mark a milestone paid directly then attempt checkout -> 400."""
        pid = linked_project["project"]["id"]
        r0 = admin_sess.get(f"{API}/projects/workspace/{pid}", timeout=15)
        ms = r0.json()["milestones"]
        target = next((m for m in ms if m.get("status") != "paid"), None)
        if not target:
            pytest.skip("no non-paid milestone available")
        # Force mark paid via /paid endpoint (admin has superadmin scope)
        r1 = admin_sess.post(
            f"{API}/projects/workspace/{pid}/milestones/{target['id']}/paid",
            timeout=15,
        )
        assert r1.status_code == 200, r1.text
        r2 = admin_sess.post(
            f"{API}/projects/workspace/{pid}/milestones/{target['id']}/checkout",
            json={"origin_url": "https://example.com"}, timeout=15,
        )
        assert r2.status_code == 400, r2.text
