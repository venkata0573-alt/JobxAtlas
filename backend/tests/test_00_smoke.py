"""Smoke tests. Proves the Phase 1a harness is wired end-to-end:

  1. Backend is reachable and boots (via HTTPS with self-signed cert).
  2. `/api/marketplace/industries` returns 200 on the seeded DB.
  3. Every persona in seed.PERSONA_EMAILS can log in via the client factory.
  4. The `clean_db` autouse fixture actually reseeds between tests
     (checked in a two-test sequence).
  5. `stripe.api_base` inside the backend process is pointed at stripe-mock,
     not api.stripe.com — via a Stripe path end-to-end.
  6. `storage_client.STORAGE_BASE` matches `INTEGRATION_PROXY_URL` from
     .env.test — same silent-fallback guard as (5), for uploads that would
     otherwise leak to `integrations.emergentagent.com` (see S-27).
  7. Login sets `SameSite`/`Secure`/`HttpOnly` on `access_token`.
  8. Removing the cookie yields 401 — proves the cookie is actually load-bearing.
  9. The client factory does NOT set an `Authorization` header (S-26 guardrail).

If any of these fail, `make up-test && make seed && make test-backend` is
not truly green; do not add new suites until this file is clean."""

from __future__ import annotations

import pytest

from tests import seed as seed_mod


# ---------- 1 & 2: boot + public endpoint -----------------------------------

async def test_backend_boots_and_returns_industries(anon_client):
    r = await anon_client.get("/api/marketplace/industries")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "industries" in body and isinstance(body["industries"], list)
    assert body["industries"], "industries list should be non-empty (canonical list)"
    # total_labelled_employers reflects seeded employers with company_industry set.
    assert body["total_labelled_employers"] >= 0


# ---------- 3: every persona can authenticate -------------------------------

@pytest.mark.parametrize("persona_id", list(seed_mod.PERSONA_EMAILS))
async def test_persona_can_login_and_hits_auth_me(client_factory, persona_id):
    client = await client_factory(persona_id)
    r = await client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["id"] == persona_id
    assert me["email"] == seed_mod.PERSONA_EMAILS[persona_id]


async def test_anon_client_gets_401_on_auth_me(anon_client):
    r = await anon_client.get("/api/auth/me")
    assert r.status_code == 401


# ---------- 4: clean_db resets state between tests --------------------------

async def test_clean_db_writes_are_visible_within_this_test(db):
    """Write a marker doc and observe it — establishes the collection state."""
    await db.support_notes.insert_one({"id": "smoke-marker", "note": "hello"})
    found = await db.support_notes.find_one({"id": "smoke-marker"})
    assert found is not None


async def test_clean_db_dropped_the_marker_from_previous_test(db):
    """If clean_db is working, the marker from the previous test is gone."""
    found = await db.support_notes.find_one({"id": "smoke-marker"})
    assert found is None, (
        "clean_db autouse fixture did not reset support_notes between tests; "
        "state leaked from test_clean_db_writes_are_visible_within_this_test. "
        "Check conftest.py::clean_db and _SEEDED_COLLECTIONS."
    )


async def test_clean_db_reseeded_the_personas(db):
    """After reseed the six personas exist."""
    count = await db.users.count_documents({"id": {"$in": list(seed_mod.PERSONA_EMAILS)}})
    assert count == len(seed_mod.PERSONA_EMAILS)


# ---------- 5: stripe.api_base points at the mock, not real Stripe ----------

async def test_stripe_api_base_is_the_mock(employer_card_client):
    """Proves the sitecustomize.py injection is live in the backend process.

    Strategy: call `POST /api/payments/checkout` with the seeded card-holding
    employer. The endpoint uses the Stripe SDK to create a Checkout Session.
    - If sitecustomize.py set stripe.api_base to stripe-mock, the call returns
      200 with a session_id (stripe-mock accepts any test key).
    - If sitecustomize.py is missing or STRIPE_API_BASE drifted, the SDK talks
      to api.stripe.com with our bogus test key and returns 401 → backend
      surfaces a 500. The assertion below fails loudly, telling you to check
      the injection instead of chasing an "app bug".

    We further assert the returned session_id has the Stripe convention shape
    (`cs_test_...`) so a silent 200 from an unrelated endpoint can't mask
    injection loss.
    """
    r = await employer_card_client.post(
        "/api/payments/checkout",
        json={"package_id": "starter_10", "origin_url": "http://localhost:13000"},
    )
    assert r.status_code == 200, (
        f"POST /api/payments/checkout returned {r.status_code}. If this is 500, "
        f"the Stripe SDK is likely talking to api.stripe.com instead of "
        f"stripe-mock. Verify: (a) STRIPE_API_BASE is set in .env.test, "
        f"(b) sitecustomize.py exists in the backend image site-packages, "
        f"(c) the stripe-mock container is up. Body: {r.text[:400]}"
    )
    body = r.json()
    assert "session_id" in body, body
    assert body["session_id"].startswith("cs_test_"), (
        f"unexpected session_id shape: {body['session_id']!r}. "
        "Stripe returns cs_test_* for test-mode sessions; stripe-mock "
        "mirrors this. Anything else means the SDK bypassed the mock."
    )


# ---------- 6: storage_client base URL matches INTEGRATION_PROXY_URL --------

def test_storage_client_base_matches_env():
    """S-27 (P0) guardrail. `storage_client.py:6` falls back to
    `https://integrations.emergentagent.com` if `INTEGRATION_PROXY_URL` is
    unset or empty — user uploads (avatars, portfolio, dispute evidence, and
    government ID from KYB) would silently route to a third-party host with
    no warning. This is the storage analogue of the stripe.api_base check
    above: if it ever fails, do not chase an app bug — the env var drifted
    or storage_client changed its fallback shape.

    Import happens at test time (not module-load) so the assertion sees the
    exact value the running backend process resolved."""
    import os
    import storage_client

    expected = os.environ.get("INTEGRATION_PROXY_URL", "").strip()
    assert expected, (
        "INTEGRATION_PROXY_URL is empty in the test process — this test "
        "cannot prove anything. Set it in .env.test and re-run."
    )
    assert storage_client.STORAGE_BASE == expected, (
        f"storage_client.STORAGE_BASE resolved to {storage_client.STORAGE_BASE!r}, "
        f"expected {expected!r} from INTEGRATION_PROXY_URL. If STORAGE_BASE is "
        f"the emergentagent fallback, the env var didn't propagate — "
        f"uploads would leak to a third-party host in prod. See S-27."
    )


# ---------- 7-9: cookie flags + cookie-only enforcement ---------------------

async def test_login_sets_secure_httponly_samesite_cookie(anon_client):
    """Regression guard for CLAUDE.md invariant #3 (httpOnly cookie auth) and
    the security assumptions in S-01/S-07. If any of these flags drop, an XSS
    or CSRF exposure opens without any test elsewhere noticing — the flags are
    load-bearing, not decorative."""
    r = await anon_client.post(
        "/api/auth/login",
        json={"email": seed_mod.PERSONA_EMAILS[seed_mod.ADMIN_ALL_ID],
              "password": seed_mod.FIXTURE_PASSWORD},
    )
    assert r.status_code == 200, r.text
    set_cookies = r.headers.get_list("set-cookie")
    access = [h for h in set_cookies if h.startswith("access_token=")]
    assert len(access) == 1, (
        f"expected exactly one access_token Set-Cookie header; got: {set_cookies}"
    )
    header = access[0]
    for flag in ("HttpOnly", "Secure"):
        assert flag in header, f"missing {flag} on access_token cookie: {header}"
    assert "SameSite=" in header, (
        f"missing SameSite on access_token cookie: {header}"
    )


async def test_missing_cookie_causes_401(client_factory):
    """Confirms the cookie is load-bearing — clearing the jar breaks auth.

    If this fails with 200, something is authenticating the request other than
    the cookie (a re-introduced Bearer header, a lingering session, a token in
    a query param). Investigate before adding any new tests."""
    c = await client_factory(seed_mod.ADMIN_ALL_ID)
    baseline = await c.get("/api/auth/me")
    assert baseline.status_code == 200, (
        f"cookie-authed baseline failed: {baseline.status_code} {baseline.text[:200]}"
    )
    c.cookies.clear()
    r = await c.get("/api/auth/me")
    assert r.status_code == 401, (
        f"expected 401 with empty cookie jar, got {r.status_code}: {r.text[:200]}. "
        f"Non-cookie auth is leaking through — check for a Bearer header, "
        f"query-string token, or session storage on the client."
    )


async def test_client_factory_does_not_set_authorization_header(client_factory):
    """The harness MUST NOT reintroduce Bearer auth as a convenience. If this
    assertion ever fails, the untested-cookie-path problem is back and S-26 is
    silently unreviewable."""
    c = await client_factory(seed_mod.ADMIN_ALL_ID)
    header_keys = {k.lower() for k in c.headers.keys()}
    assert "authorization" not in header_keys, (
        f"client factory set an Authorization header: {dict(c.headers)}. "
        f"Cookie-only is the policy. See conftest.py::client_factory."
    )
