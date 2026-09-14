"""S-26 companion: the SSE broadcast stream keeps working via `?token=`.

The S-26 Bearer-removal only touches `deps.get_current_user`. The SSE
endpoint `/talent/me/broadcasts/stream` was already independent — it reads
`access_token` from cookie OR `?token=` query param, then does its own
inline `jwt.decode`, never routing through `get_current_user`.

These tests prove the SSE auth surface is unchanged after S-26:

1. `test_sse_accepts_query_token` — mint a JWT via `create_token`, hit the
   stream with `?token=<jwt>`, assert 200 + `text/event-stream`.
2. `test_sse_accepts_cookie` — the cookie-only path still works.
3. `test_sse_rejects_unauth` — no token, no cookie → 401 (proves the
   endpoint isn't accidentally wide-open now).
4. `test_sse_rejects_non_talent` — an employer's JWT via `?token=` gets 403.

We stream only enough to consume the `hello` frame the server sends
immediately, then close. No sleeps, no long-running assertions.
"""
from __future__ import annotations

from pathlib import Path
import sys

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from deps import create_token  # noqa: E402

from tests import seed as seed_mod  # noqa: E402


async def _first_sse_frame(client, url):
    """Open a streaming request and return (status_code, first_frame_bytes).

    The endpoint yields a `: connected\\ndata: {...}\\n\\n` frame as the
    first thing, so we can prove the auth passed and the stream started
    without waiting on the keepalive timer.
    """
    async with client.stream("GET", url) as r:
        if r.status_code != 200:
            body = await r.aread()
            return r.status_code, body
        buf = b""
        async for chunk in r.aiter_bytes():
            buf += chunk
            if b"\n\n" in buf:
                return r.status_code, buf
        return r.status_code, buf


async def test_sse_accepts_query_token(anon_client):
    """SSE with ?token=<jwt> — the browser EventSource path."""
    token = create_token(seed_mod.TALENT_CLEAN_ID)
    status, first_frame = await _first_sse_frame(
        anon_client, f"/api/talent/me/broadcasts/stream?token={token}",
    )
    assert status == 200, f"SSE rejected with valid ?token=: {status} / {first_frame[:200]!r}"
    assert b"hello" in first_frame, (
        f"SSE opened but didn't send the initial hello frame: {first_frame[:200]!r}"
    )


async def test_sse_accepts_cookie(talent_clean_client):
    """SSE via cookie — no query param needed when the browser can carry it."""
    status, first_frame = await _first_sse_frame(
        talent_clean_client, "/api/talent/me/broadcasts/stream",
    )
    assert status == 200, f"SSE rejected via cookie auth: {status} / {first_frame[:200]!r}"
    assert b"hello" in first_frame


async def test_sse_rejects_unauth(anon_client):
    """No cookie, no ?token= → 401."""
    r = await anon_client.get("/api/talent/me/broadcasts/stream")
    assert r.status_code == 401, r.text


async def test_sse_rejects_non_talent(anon_client):
    """A valid JWT for a non-talent role → 403 Talent only."""
    token = create_token(seed_mod.EMPLOYER_CARD_ID)
    r = await anon_client.get(
        f"/api/talent/me/broadcasts/stream?token={token}"
    )
    assert r.status_code == 403, r.text
