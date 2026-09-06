"""Phase 1b tests — FEATURES.md §3 (auth: register, login, session,
current user, email verification, profile, suggest-rate).

Coverage shape:
- One test per numbered manual step from FEATURES.md §3.
- Per endpoint: unauthenticated → 401 (or 403/400 where the handler
  short-circuits earlier), wrong role where applicable, cross-tenant
  where it applies.

Turnstile posture (S-08 partial). The .env.test seed sets
TURNSTILE_SECRET_KEY to Cloudflare's always-pass test secret. Register
via HTTP would need an outbound call to challenges.cloudflare.com from
the backend container, which is flaky in isolated test networks — so
the register-happy-path tests use **direct-import** of the handler and
monkey-patch `settings.auth.turnstile_secret_key = None` to force the
fail-open path (which config.py explicitly allows in env=test). The
fail-open path also logs a WARN — see test_verify_turnstile_fail_opens_
with_warn for the S-08 assertion.

Rate limiting is NOT tested — it does not exist yet (S-08 remaining
scope). Password reset is NOT tested — there is no password-reset
endpoint in the backend (a `forgotPasswordLink` testId exists in
frontend/src/constants/testIds/auth.js but no handler was ever written).

Skipped as duplicates of test_11_engagements.py or test_12_13_revisions.py:
none — auth surface has no overlap.
"""
from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# ============================================================================
# 1. Manual steps — FEATURES.md §3 (register → login → verify → resend → me)
# ============================================================================

class TestManualSteps:
    """Each step maps to a numbered item in the FEATURES.md §3 walkthrough.
    Registration uses direct-import (see file docstring); login/logout/me
    use the HTTP client factory the SPA also uses."""

    async def test_step_1_industries_endpoint_returns_list_for_register_dropdown(
        self, anon_client,
    ):
        """Register page fetches GET /api/marketplace/industries on load.
        Endpoint returns {industries: [{label, count}, ...], total_labelled_employers}."""
        r = await anon_client.get("/api/marketplace/industries")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict) and "industries" in body, (
            f"Register page's industry dropdown expects the {{industries: [...]}}"
            f" shape; got: {body}"
        )
        assert body["industries"], "Empty list would render an empty dropdown"
        assert "label" in body["industries"][0]

    async def test_step_2_register_talent_via_direct_import(
        self, db, monkeypatch,
    ):
        """Direct-import to bypass the Turnstile outbound call (see file
        docstring). Simulates the /register page happy path for a talent."""
        from config import settings
        from routes.auth import register
        from routes.auth import RegisterIn
        from fastapi import Response

        object.__setattr__(settings.auth, "turnstile_secret_key", None)
        try:
            r = await register(
                RegisterIn(
                    email="test-register-talent@atlas-test.example.com",
                    password="Passw0rd!",
                    name="Alex Talent",
                    role="talent",
                ),
                Response(),
            )
        finally:
            # Restore the test seed's Turnstile value.
            object.__setattr__(
                settings.auth, "turnstile_secret_key",
                "1x0000000000000000000000000000000AA",
            )
        assert r["role"] == "talent"
        assert r["email"] == "test-register-talent@atlas-test.example.com"
        assert r["email_verified"] is False
        # Verification token is persisted (email is silently-no-op without
        # RESEND_API_KEY; the manual test says "grab it from Mongo").
        u = await db.users.find_one({"id": r["id"]})
        assert u.get("email_verification_token"), (
            "Registration must persist a verification token so the manual "
            "verify-email step can proceed."
        )

    async def test_step_3_login_redirects_to_talent_by_role(
        self, client_factory, db,
    ):
        """Login as the seeded talent-clean; response body carries the role
        so the SPA can pick the right dashboard route."""
        c = await client_factory(seed_mod.TALENT_CLEAN_ID)
        r = await c.get("/api/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "talent"

    async def test_step_4_register_employer_industry_gets_stored(
        self, db, monkeypatch,
    ):
        from config import settings
        from routes.auth import register, RegisterIn
        from fastapi import Response

        object.__setattr__(settings.auth, "turnstile_secret_key", None)
        try:
            r = await register(
                RegisterIn(
                    email="test-register-employer@atlas-test.example.com",
                    password="Passw0rd!",
                    name="EmpCo",
                    role="employer",
                    company_industry="Financial Services & Fintech",
                ),
                Response(),
            )
        finally:
            object.__setattr__(
                settings.auth, "turnstile_secret_key",
                "1x0000000000000000000000000000000AA",
            )
        assert r["role"] == "employer"
        u = await db.users.find_one({"id": r["id"]})
        assert u["profile"]["company_industry"] == "Financial Services & Fintech"

    async def test_step_5_login_hits_auth_me_returns_user(
        self, client_factory,
    ):
        """Round-trip login → /auth/me. This is the smoke test the harness
        already does; asserted here as the §3 manual step."""
        c = await client_factory(seed_mod.EMPLOYER_CARD_ID)
        r = await c.get("/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == seed_mod.PERSONA_EMAILS[seed_mod.EMPLOYER_CARD_ID]
        # Password hash must NEVER be returned.
        assert "password_hash" not in body

    async def test_step_6_admin_login_returns_admin_permissions(
        self, admin_all_client,
    ):
        """Manual step 6 = "insert an admin doc directly into Mongo, then
        log in". The harness seeds admin-all; this asserts the seeded admin
        can log in and /auth/me reflects the permissions."""
        r = await admin_all_client.get("/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "admin"
        assert "superadmin" in (body.get("admin_permissions") or [])


# ============================================================================
# 2. POST /auth/register — negatives + Turnstile
# ============================================================================

class TestRegister:
    async def test_bad_role_rejected(self, db, monkeypatch):
        """role must be talent|employer."""
        from config import settings
        from routes.auth import register, RegisterIn
        from fastapi import Response

        object.__setattr__(settings.auth, "turnstile_secret_key", None)
        try:
            with pytest.raises(HTTPException) as exc:
                await register(
                    RegisterIn(
                        email="test-badrole@atlas-test.example.com",
                        password="Passw0rd!",
                        name="X",
                        role="superuser",
                    ),
                    Response(),
                )
            assert exc.value.status_code == 400
            assert "role" in exc.value.detail.lower()
        finally:
            object.__setattr__(
                settings.auth, "turnstile_secret_key",
                "1x0000000000000000000000000000000AA",
            )

    async def test_duplicate_email_rejected(self, db, monkeypatch):
        """A seeded persona's email cannot be re-used."""
        from config import settings
        from routes.auth import register, RegisterIn
        from fastapi import Response

        object.__setattr__(settings.auth, "turnstile_secret_key", None)
        try:
            with pytest.raises(HTTPException) as exc:
                await register(
                    RegisterIn(
                        email=seed_mod.PERSONA_EMAILS[seed_mod.TALENT_CLEAN_ID],
                        password="Passw0rd!",
                        name="Duplicate",
                        role="talent",
                    ),
                    Response(),
                )
            assert exc.value.status_code == 400
            assert "already" in exc.value.detail.lower()
        finally:
            object.__setattr__(
                settings.auth, "turnstile_secret_key",
                "1x0000000000000000000000000000000AA",
            )

    async def test_unknown_employer_industry_rejected(self, db, monkeypatch):
        """Employer with a company_industry outside EMPLOYER_INDUSTRIES → 400."""
        from config import settings
        from routes.auth import register, RegisterIn
        from fastapi import Response

        object.__setattr__(settings.auth, "turnstile_secret_key", None)
        try:
            with pytest.raises(HTTPException) as exc:
                await register(
                    RegisterIn(
                        email="test-badindustry@atlas-test.example.com",
                        password="Passw0rd!",
                        name="X",
                        role="employer",
                        company_industry="Extraterrestrial Mining",
                    ),
                    Response(),
                )
            assert exc.value.status_code == 400
            assert "industry" in exc.value.detail.lower()
        finally:
            object.__setattr__(
                settings.auth, "turnstile_secret_key",
                "1x0000000000000000000000000000000AA",
            )

    async def test_register_http_empty_turnstile_rejected(self, anon_client):
        """Via HTTP with .env.test's TURNSTILE_SECRET_KEY set and no token
        provided: _verify_turnstile hits `if not token: return False` (auth.py:80),
        register returns 400 'Captcha verification failed'. This proves the
        fail-CLOSED path works when the secret is configured."""
        r = await anon_client.post(
            "/api/auth/register",
            json={"email": "test-noturnstile@atlas-test.example.com",
                  "password": "Passw0rd!", "name": "X", "role": "talent",
                  "turnstile_token": ""},
        )
        assert r.status_code == 400, r.text
        assert "captcha" in r.text.lower()


# ============================================================================
# 3. S-08 partial: Turnstile fail-open path logs a WARN
# ============================================================================

class TestTurnstileFailOpenLogsWarn:
    """S-08 partial (per SECURITY_BACKLOG.md and the F-11 sweep). When
    TURNSTILE_SECRET_KEY is unset in dev/test, `_verify_turnstile` returns
    True (fail-open) but MUST log a WARNING naming S-08, the env, and
    remote_ip. A silent bypass would be worse than the current state."""

    async def test_fail_open_returns_true_and_emits_S08_warn(
        self, caplog, monkeypatch,
    ):
        from config import settings
        from routes.auth import _verify_turnstile

        object.__setattr__(settings.auth, "turnstile_secret_key", None)
        try:
            with caplog.at_level(logging.WARNING):
                result = await _verify_turnstile(
                    token="ignored-by-fail-open",
                    remote_ip="203.0.113.42",
                )
        finally:
            object.__setattr__(
                settings.auth, "turnstile_secret_key",
                "1x0000000000000000000000000000000AA",
            )
        assert result is True, (
            "Fail-open path must return True; S-08 explicitly accepts this "
            "in dev/test with the WARN as the compensating control."
        )
        s08_warns = [rec for rec in caplog.records
                     if rec.levelno == logging.WARNING and "[S-08]" in rec.message]
        assert s08_warns, (
            f"No [S-08] WARN captured. A silent fail-open is exactly what "
            f"the S-08 partial fix in F-11 was meant to eliminate. "
            f"caplog messages: {[r.message for r in caplog.records]}"
        )
        # The WARN must name the env AND the remote_ip so ops can reconstruct
        # what got through.
        msg = s08_warns[0].message
        assert "203.0.113.42" in msg, f"remote_ip missing from WARN: {msg!r}"
        assert "test" in msg or "development" in msg, (
            f"env tag missing from WARN: {msg!r}"
        )

    async def test_secret_set_missing_token_returns_false(self, monkeypatch):
        """Fail-CLOSED baseline: with the secret set (.env.test default) and
        no token supplied, _verify_turnstile returns False. Ensures the
        fail-open path only fires when the secret is unset."""
        from config import settings
        from routes.auth import _verify_turnstile

        # The .env.test seed is already the correct config; assert directly.
        assert settings.auth.turnstile_secret_key, (
            ".env.test is expected to set TURNSTILE_SECRET_KEY; test "
            "prerequisite failed."
        )
        result = await _verify_turnstile(token="", remote_ip="203.0.113.42")
        assert result is False


# ============================================================================
# 4. GET /auth/verify-email — token consumption
# ============================================================================

class TestVerifyEmail:
    async def test_valid_token_marks_verified_and_consumes_token(self, db):
        # Seed a user with a known verification token
        await db.users.update_one(
            {"id": seed_mod.TALENT_CLEAN_ID},
            {"$set": {"email_verified": False,
                      "email_verification_token": "seed-verify-token-abc123"}},
        )
        from routes.auth import verify_email
        r = await verify_email(token="seed-verify-token-abc123")
        assert r["ok"] is True
        assert r["email"] == seed_mod.PERSONA_EMAILS[seed_mod.TALENT_CLEAN_ID]
        u = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        assert u["email_verified"] is True
        assert "email_verification_token" not in u, (
            "Token must be $unset on successful verify (auth.py:182-183)"
        )

    async def test_missing_token_rejected(self):
        from routes.auth import verify_email
        with pytest.raises(HTTPException) as exc:
            await verify_email(token="")
        assert exc.value.status_code == 400
        assert "missing" in exc.value.detail.lower()

    async def test_invalid_token_rejected(self):
        from routes.auth import verify_email
        with pytest.raises(HTTPException) as exc:
            await verify_email(token="not-a-real-token-in-any-user-doc")
        assert exc.value.status_code == 400
        assert "invalid" in exc.value.detail.lower() or "expired" in exc.value.detail.lower()


# ============================================================================
# 5. POST /auth/resend-verification — auth-required, respects already-verified
# ============================================================================

class TestResendVerification:
    async def test_anon_returns_401(self, anon_client):
        r = await anon_client.post("/api/auth/resend-verification")
        assert r.status_code == 401, r.text

    async def test_already_verified_short_circuits(
        self, talent_clean_client, db,
    ):
        """talent_clean is seeded as verified; resend should no-op."""
        r = await talent_clean_client.post("/api/auth/resend-verification")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("already_verified") is True

    async def test_unverified_user_re_persists_token(self, talent_clean_client, db):
        """Force unverified, resend, verify token got re-persisted."""
        await db.users.update_one(
            {"id": seed_mod.TALENT_CLEAN_ID},
            {"$set": {"email_verified": False},
             "$unset": {"email_verification_token": ""}},
        )
        r = await talent_clean_client.post("/api/auth/resend-verification")
        assert r.status_code == 200
        u = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        assert u.get("email_verification_token"), (
            "resend-verification must generate + persist a fresh token"
        )


# ============================================================================
# 6. POST /auth/login — negatives
# ============================================================================

class TestLogin:
    async def test_unknown_email_returns_401(self, anon_client):
        r = await anon_client.post(
            "/api/auth/login",
            json={"email": "does-not-exist@atlas-test.example.com",
                  "password": "Passw0rd!"},
        )
        assert r.status_code == 401, r.text
        # Message must NOT distinguish "unknown email" from "wrong password"
        # (see S-08 remaining scope: user enumeration hardening).
        # This test asserts current behaviour, not the fix.

    async def test_wrong_password_returns_401(self, anon_client):
        r = await anon_client.post(
            "/api/auth/login",
            json={"email": seed_mod.PERSONA_EMAILS[seed_mod.TALENT_CLEAN_ID],
                  "password": "not-the-right-password"},
        )
        assert r.status_code == 401, r.text

    async def test_response_never_leaks_password_hash(self, anon_client):
        r = await anon_client.post(
            "/api/auth/login",
            json={"email": seed_mod.PERSONA_EMAILS[seed_mod.TALENT_CLEAN_ID],
                  "password": seed_mod.FIXTURE_PASSWORD},
        )
        assert r.status_code == 200, r.text
        assert "password_hash" not in r.text


# ============================================================================
# 7. POST /auth/logout — clears cookies
# ============================================================================

class TestLogout:
    async def test_public_but_clears_cookies(self, talent_clean_client):
        r = await talent_clean_client.post("/api/auth/logout")
        assert r.status_code == 200
        # Assert the response includes cookie-clear directives.
        set_cookie = r.headers.get_list("set-cookie")
        assert any("access_token=" in c and "Max-Age=0" in c for c in set_cookie), (
            f"access_token cookie must be cleared on logout; got {set_cookie}"
        )
        assert any("refresh_token=" in c and "Max-Age=0" in c for c in set_cookie), (
            f"refresh_token cookie must be cleared on logout; got {set_cookie}"
        )


# ============================================================================
# 8. GET /auth/me — auth-required
# ============================================================================

class TestAuthMe:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_never_returns_password_hash(self, employer_card_client):
        r = await employer_card_client.get("/api/auth/me")
        assert r.status_code == 200
        assert "password_hash" not in r.text


# ============================================================================
# 9. PUT /profile — auth-required, arbitrary body validation
# ============================================================================

class TestProfileUpdate:
    async def test_anon_401(self, anon_client):
        r = await anon_client.put(
            "/api/profile",
            json={"headline": "New headline"},
        )
        assert r.status_code == 401

    async def test_talent_can_update_own_profile(self, talent_clean_client, db):
        r = await talent_clean_client.put(
            "/api/profile",
            json={"headline": "Senior full-stack — updated",
                  "bio": "Updated bio", "skills": ["React", "Go"],
                  "years_experience": 6, "hourly_rate": 75,
                  "location": "Remote"},
        )
        assert r.status_code == 200, r.text
        u = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        assert u["profile"]["headline"] == "Senior full-stack — updated"
        assert u["profile"]["skills"] == ["React", "Go"]


# ============================================================================
# 10. POST /profile/suggest-rate — auth-required, LLM-fallback path
# ============================================================================

class TestSuggestRate:
    async def test_anon_401(self, anon_client):
        r = await anon_client.post(
            "/api/profile/suggest-rate",
            json={"skills": ["React"], "years_experience": 5},
        )
        assert r.status_code == 401

    async def test_returns_fallback_shape_regardless_of_llm(
        self, talent_clean_client,
    ):
        """.env.test has EMERGENT_LLM_KEY set to a non-real value; the
        LlmChat call will TypeError on the shim, and ai_service falls back
        to rule-based rates. Asserting the shape lets the test pass whether
        or not a real LLM answers."""
        r = await talent_clean_client.post(
            "/api/profile/suggest-rate",
            json={"skills": ["React"], "years_experience": 5,
                  "location": "Remote"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("low", "mid", "high", "currency"):
            assert k in body, f"suggest-rate response missing '{k}': {body}"
        assert body["low"] <= body["mid"] <= body["high"]


# ============================================================================
# 11. GET /verification/me — auth-required
# ============================================================================

class TestVerificationMe:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/verification/me")
        assert r.status_code == 401

    async def test_talent_returns_verification_state(self, talent_clean_client):
        r = await talent_clean_client.get("/api/verification/me")
        assert r.status_code == 200, r.text


# ============================================================================
# 12. GET /auth/sse-token — issues a short-lived token for the SSE endpoint
# ============================================================================

class TestSseTokenEndpoint:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/auth/sse-token")
        assert r.status_code == 401

    async def test_talent_gets_token(self, talent_clean_client):
        r = await talent_clean_client.get("/api/auth/sse-token")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("token"), f"sse-token endpoint must return a token: {body}"
