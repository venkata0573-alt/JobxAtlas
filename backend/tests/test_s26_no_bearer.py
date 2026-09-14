"""S-26: server must NOT accept `Authorization: Bearer <jwt>` for authentication.

The Bearer branch in `deps.get_current_user` was legacy attack surface — no
first-party frontend sends a Bearer token (`grep -rn "Authorization"
frontend/src/` returns nothing), and the only place a `?token=` query-param
JWT is legitimately used is the SSE `/talent/me/broadcasts/stream` endpoint,
which does its own inline `jwt.decode` and never touches `get_current_user`.

Removing the Bearer branch is the S-26 fix. These tests lock it in:

1. `test_bearer_only_is_rejected_401` — a valid JWT presented ONLY as a
   Bearer header (no cookie) must return 401. Before the fix this returned
   200. After the fix, cookie-only.
2. `test_cookie_only_still_works` — the same JWT presented as the
   `access_token` cookie continues to authenticate the user.
3. `test_bearer_ignored_when_cookie_present` — if a request supplies BOTH a
   cookie AND a Bearer header, the cookie is used and the Bearer is ignored.
   This isn't a critical safety property but it's the natural post-fix
   behaviour (the Bearer branch simply doesn't exist), and asserting it
   prevents a future refactor from silently reintroducing a "cookie or
   bearer, whichever wins" reading path.

Regression window: without a test, someone re-adding the Bearer branch for
some new integration wouldn't be caught until an S-01 CSRF-middleware audit
long after the fact.
"""
from __future__ import annotations

from pathlib import Path
import sys

# Test module needs to import `deps.create_token` to mint a valid JWT that
# the running backend (a separate process, same JWT_SECRET) will accept.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from deps import create_token  # noqa: E402

from tests import seed as seed_mod  # noqa: E402


async def test_bearer_only_is_rejected_401(anon_client):
    """A valid JWT as a Bearer header, no cookie — must return 401.

    Before the S-26 fix this returned 200 (the Bearer branch at
    deps.py:69-72 read the header and populated the user). After the fix,
    cookie-only: no cookie = no auth = 401.
    """
    token = create_token(seed_mod.TALENT_CLEAN_ID)
    r = await anon_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401, (
        f"S-26 violation: server accepted a Bearer token with no cookie. "
        f"Got {r.status_code}: {r.text[:200]}. Delete the Bearer branch in "
        f"deps.get_current_user."
    )


async def test_cookie_only_still_works(talent_clean_client):
    """Sanity: the cookie-only path continues to authenticate.

    Uses the shared `talent_clean_client` fixture — that fixture logs in
    via POST /api/auth/login, so its cookie jar already has `access_token`.
    """
    r = await talent_clean_client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    assert r.json().get("id") == seed_mod.TALENT_CLEAN_ID


async def test_bearer_ignored_when_cookie_present(talent_clean_client):
    """A Bearer header alongside a cookie is silently ignored — the cookie
    wins because the Bearer branch no longer exists.

    Uses a deliberately-invalid Bearer value to prove the point: if the
    server were still reading the header, this request would fail. It
    doesn't, because the cookie is the only path.
    """
    r = await talent_clean_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer this-is-not-a-real-jwt-and-must-be-ignored"},
    )
    assert r.status_code == 200, (
        f"S-26 regression: cookie-authed request was rejected because of the "
        f"Bearer header. Got {r.status_code}: {r.text[:200]}."
    )
    assert r.json().get("id") == seed_mod.TALENT_CLEAN_ID
