"""Shared pytest fixtures for the Phase 1a backend test suite.

Provides:
  - `backend_url`     : the base URL of the running test backend
  - `db`              : Motor client for direct DB assertions/mutations
  - `clean_db`        : (autouse) drops all collections + reseeds before each test
  - `anon_client`     : httpx.AsyncClient with no cookies
  - `client_factory`  : async callable → httpx.AsyncClient authenticated as any persona,
                        **cookie-only** — no Bearer header, ever
  - `admin_all_client` / `admin_noscope_client` / `talent_clean_client` /
    `talent_flagged_client` / `employer_card_client` / `employer_nocard_client`
    — one prebuilt cookie-authed client per persona for convenience
  - `sse_token_for_talent_clean` : JWT string for the SSE `?token=` query param

The clean_db fixture is `autouse` so every test starts from the deterministic
seed state. Tests that mutate the DB do not need to clean up.

Auth policy: the SPA is cookie-only (`grep -rn "Authorization" frontend/src/`
returns zero matches). This harness matches that policy. The Bearer branch at
`deps.py:72-74` is tracked as S-26 (P0 candidate) for removal. If any test needs
a JWT out-of-band it goes through `sse_token_for_talent_clean` (query param,
not header) — never re-add a Bearer factory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio

# Make `backend/` importable so seed.py + deps.py resolve.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from tests import seed as seed_mod  # noqa: E402


# ---------- basic knobs -----------------------------------------------------

@pytest.fixture(scope="session")
def backend_url() -> str:
    """Base URL of the running backend.

    Inside the backend container the app listens on HTTPS :8443 (compose maps
    it to host 18443). Both work from inside the container thanks to loopback;
    only the host publish is different. Override with `TEST_BACKEND_URL` if you
    run pytest against a differently-mapped stack.

    Must be HTTPS. The backend sets `SameSite=None; Secure` on the auth cookie,
    and httpx's standard cookie jar will refuse to ship a Secure cookie over
    plain HTTP. This is why the harness runs the backend on TLS — see
    docker-compose.test.yml and backend/Dockerfile.test cert generation."""
    return os.environ.get("TEST_BACKEND_URL", "https://localhost:8443")


@pytest_asyncio.fixture(scope="session")
async def db():
    """Motor client bound to the pytest-asyncio session event loop.

    We deliberately do NOT reuse `deps.db` here. `deps.db` was constructed at
    Python import time — before pytest-asyncio spun up its session loop — so
    every await against it fails with "attached to a different loop". Instead
    we build our own client inside the fixture body so it binds lazily to the
    loop pytest-asyncio hands us.

    We also rebind `seed_mod.db` to this client so seed.py's writes use the
    same loop as the assertions that read them back. The running backend
    process is untouched — it keeps its own Motor client on its own loop."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    seed_mod.db = db  # rebind so seed.seed() uses this loop's client
    try:
        yield db
    finally:
        client.close()


# ---------- clean state per test --------------------------------------------

# Collections the seeder writes to. Drop these + reseed between tests to keep
# state deterministic without dropping the whole database (which would also
# remove server-side indexes created by server.py:2749 on boot).
_SEEDED_COLLECTIONS = (
    "users",
    "engagements",
    "deliverables",
    "projects",
    "project_milestones",
    "project_invoices",
    "grievances",
    # Also clear anything a test might have written that we don't want leaking
    # between tests:
    "payouts",
    "reviews",
    "payment_transactions",
    "revision_requests",
    "dispute_fee_transactions",
    "refund_audit_receipts",
    "notifications",
    "broadcasts",
    "eois",
    "shortlists",
    "rate_nudges",
    "audit_log",
    "support_notes",
    "reference_checks",
    "project_leads",
    "project_variances",
    "project_alerts",
    "project_risks",
    # §11 messaging + attachments; tests here write to both.
    "messages",
    "files",
)


@pytest_asyncio.fixture(autouse=True)
async def clean_db(db) -> AsyncIterator[None]:
    """Drop-and-reseed before each test. Autouse."""
    for c in _SEEDED_COLLECTIONS:
        await db[c].delete_many({})
    await seed_mod.seed()
    yield


# ---------- httpx clients ---------------------------------------------------

@pytest_asyncio.fixture
async def anon_client(backend_url) -> AsyncIterator[httpx.AsyncClient]:
    # verify=False: the backend runs with a self-signed cert generated at image
    # build time (backend/Dockerfile.test). NEVER set this against a real backend.
    async with httpx.AsyncClient(base_url=backend_url, timeout=10.0, verify=False) as c:
        yield c


PersonaId = str
ClientFactory = Callable[[PersonaId], "httpx.AsyncClient"]


@pytest_asyncio.fixture
async def client_factory(backend_url) -> AsyncIterator[ClientFactory]:
    """Yield an async factory that returns an authenticated httpx client for
    a given persona id. Callers must `await` the factory.

        client = await client_factory(seed.TALENT_CLEAN_ID)
    """
    clients: list[httpx.AsyncClient] = []

    async def _make(persona_id: str) -> httpx.AsyncClient:
        email = seed_mod.PERSONA_EMAILS.get(persona_id)
        if not email:
            raise KeyError(
                f"unknown persona {persona_id!r}. Known: {list(seed_mod.PERSONA_EMAILS)}"
            )
        # verify=False: self-signed cert in the test image (see backend/Dockerfile.test).
        c = httpx.AsyncClient(base_url=backend_url, timeout=10.0, verify=False)
        r = await c.post(
            "/api/auth/login",
            json={"email": email, "password": seed_mod.FIXTURE_PASSWORD},
        )
        if r.status_code != 200:
            await c.aclose()
            raise AssertionError(
                f"login failed for {persona_id!r} "
                f"({r.status_code}): {r.text[:200]}"
            )
        # Cookie-only. httpx's jar has already stored `access_token` from the
        # login response's Set-Cookie; because base_url is HTTPS the Secure
        # attribute doesn't block it. Do NOT extract to a Bearer header —
        # S-26 (P0 candidate) tracks removal of the server-side Bearer branch,
        # and the whole point of Phase 1a→1b cookie-first is that the tests
        # exercise the same auth path the browser does. A "convenience"
        # Bearer opt-in is exactly how the untested-cookie-path problem returns.
        if "access_token" not in c.cookies:
            await c.aclose()
            raise AssertionError(
                f"login for {persona_id!r} returned 200 but no access_token in "
                f"cookie jar. Set-Cookie headers: {r.headers.get_list('set-cookie')}"
            )
        clients.append(c)
        return c

    yield _make

    for c in clients:
        await c.aclose()


# ---------- convenience per-persona fixtures --------------------------------

def _persona_fixture(persona_id: str):
    @pytest_asyncio.fixture
    async def _fx(client_factory):
        return await client_factory(persona_id)
    return _fx


admin_all_client       = _persona_fixture(seed_mod.ADMIN_ALL_ID)
admin_noscope_client   = _persona_fixture(seed_mod.ADMIN_NOSCOPE_ID)
talent_clean_client    = _persona_fixture(seed_mod.TALENT_CLEAN_ID)
talent_flagged_client  = _persona_fixture(seed_mod.TALENT_FLAGGED_ID)
employer_card_client   = _persona_fixture(seed_mod.EMPLOYER_CARD_ID)
employer_nocard_client = _persona_fixture(seed_mod.EMPLOYER_NOCARD_ID)


# ---------- SSE ?token= fixture ---------------------------------------------

@pytest_asyncio.fixture
async def sse_token_for_talent_clean(client_factory) -> str:
    """Returns the raw JWT string that the SSE endpoint accepts as `?token=`.

    Rationale: `server.py:2147` (`GET /api/talent/me/broadcasts/stream`) reads
    the cookie first, then a `?token=` query param, and does its own inline
    `jwt.decode`. It never calls `get_current_user`, so the Bearer branch of
    `deps.py:72-74` is irrelevant to it. Tests hitting SSE from a client that
    can't send cookies (EventSource) should attach `?token=<this>` to the URL.

    This fixture does NOT put the token into any header. If a future test
    wants Bearer auth, that's a review conversation — it's a S-26 regression."""
    c = await client_factory(seed_mod.TALENT_CLEAN_ID)
    token = c.cookies.get("access_token")
    assert token, "login should have set access_token cookie"
    return token
