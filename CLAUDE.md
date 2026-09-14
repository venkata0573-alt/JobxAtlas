# CLAUDE.md — Job Atlas / Geminista

Read `ARCHITECTURE.md` and `FEATURES.md` before any change. They are ground truth. If code
contradicts them, fix the code **or** update the doc in the same PR — never leave them diverged.

## Stack
FastAPI (single process, Motor + APScheduler in-process) · MongoDB · React 18 SPA (craco) · Stripe.
Backend at `backend/` on the host, `/app/backend/` inside the container. Frontend at `frontend/`
on the host, `/app/` inside the container (Dockerfile.test:23 copies `frontend/` → `/app/`, not
`/app/frontend/`). All routes share one `APIRouter` from `deps.py` (`api = APIRouter(prefix="/api")`).

## Hard invariants — never break these
1. Every app-level PK is `str(uuid.uuid4())` via `new_id()` (`deps.py`). Never expose Mongo `_id`.
2. Every read projects `{"_id": 0}`.
3. Auth is the httpOnly `access_token` cookie set at login (`deps.py:set_auth_cookies`). Never move
   a token into localStorage or a URL. **Known deviation: S-26 (open).** `deps.py:get_current_user`
   still accepts an `Authorization: Bearer` header alongside the cookie — no first-party frontend
   sends one (`grep -rn "Authorization" frontend/src/` returns nothing), so the branch is legacy
   attack surface. Do not send Bearer tokens from any new code; the branch is scheduled to be
   removed under S-26 before S-01's CSRF middleware lands.
4. Route modules import from `deps` only. `routes/*` → `server.py` imports must stay **inside handler
   bodies** (cycle break, see `admin.py:129,188,197`). Never hoist them to module level.
5. `routes/engagements.py` is a placeholder — its docstring lists endpoints that BELONG there but
   currently live in `server.py`. Do not add endpoints there until F-03 physically extracts them.
6. Any new admin endpoint uses `_require_scope(user, "<scope>")`. `role == "admin"` alone is a bug.
7. CSRF protection: the middleware from S-01 is **not yet registered** (test at
   `test_csrf_surface.py` currently skips with an S-01 note). The exemption policy is already
   locked in at `security/csrf_exempt.yml` — exact (method, path) pairs with a written
   justification per entry. Adding an entry requires the same review as a P0 change. When the
   S-01 middleware lands, it must consult this file, not accept its own exemption list.
8. New collection ⇒ new index in the startup block (`server.py`, the `@app.on_event("startup")`
   handler around the index-creation cluster near the bottom of the file). No exceptions.
9. No new synchronous network/PDF call inside `async def`. Wrap in `asyncio.to_thread` or use `httpx`.
   Legacy sync `requests` / `urllib` in `storage_client.py`, `work_integrations.py`,
   `routes/auth.py::_validate_crm_token` is tracked as S-13; don't grow the list.
10. Money paths are append-only + idempotent. Never delete a `payment_transactions` row.
11. `backend/config.py` is the **only** module that reads the process environment (`os.environ`,
    `os.getenv`). Enforced by `backend/tests/test_config.py::test_no_module_outside_config_reads_os_environ`
    (AST scan of `backend/`). Same rule on the frontend: `frontend/src/config.js` is the only
    reader of `process.env.REACT_APP_*`. Missing required vars fail boot with a single aggregated
    `RuntimeError` listing every gap.

## Definition of done for any task
- [ ] Behaviour matches the relevant `FEATURES.md` section (or that section is updated).
- [ ] Test added under `backend/tests/` (pytest+httpx) or `frontend/e2e/` (Playwright).
- [ ] `test_result.md` status_history appended per the protocol block in that file.
- [ ] No new entry in `SECURITY_BACKLOG.md` introduced; if the change closes one, mark it CLOSED.
- [ ] `make verify` green.

## Known landmines (do not "fix" by accident)
- **`_scheduler = None` module-level default** near the bottom of `server.py` runs before the startup
  handler assigns it. Not a bug — the guard makes the shutdown handler safe if startup didn't complete.
- **PaymentSuccess polling + Stripe webhook both credit hours — and only one branch is safe.** The
  polling path (`server.py::_credit_hours_if_paid`) uses `find_one_and_update(... {"$ne": "paid"})`
  and only `$inc`s if the update returned a document — atomically correct. The webhook path
  around line 590 does the atomic `update_one` but then unconditionally `$inc`s `hours_balance`
  regardless of whether that update matched anything — TOCTOU. Two concurrent webhook deliveries
  (Stripe retry + a coincident polling call, or two workers behind a load balancer) both pass the
  Python-level `payment_status != "paid"` check and both `$inc`. This is **S-03(c)** in the backlog;
  the xfail `test_concurrent_replay_may_double_credit` documents it empirically. If you touch either
  branch, gate every `$inc` on the update result, not on the snapshot read.
- **`emergentintegrations` is an optional import.** F-01 CLOSED (commit `9ba2368`,
  2026-09-13). `ai_service.py` wraps `from emergentintegrations.llm.chat import ...` in
  `try/except ImportError` and sets `_HAS_LLM = False` on failure; `suggest_hourly_rate`
  gates on `not _HAS_LLM or not EMERGENT_LLM_KEY` and routes to the existing rule-based
  fallback. The package is no longer in `backend/requirements.txt`, and the two-class
  shim previously injected by `backend/Dockerfile.test` has been removed. `pip install -r
  backend/requirements.txt` from a fresh checkout now succeeds; the test image and any
  other clean container boot cleanly. Regression guard: `backend/tests/test_f01_optional_import.py`
  simulates the package absent via a `sys.meta_path` blocker and asserts clean import +
  rate-shaped fallback. If you set `EMERGENT_LLM_KEY` in a live dev/prod environment
  where you've also installed a real `emergentintegrations` package, the LLM path fires
  normally — no behaviour change for that case.
- **Silent-fail dependencies are mixed now.** Post-F-11 the picture is:
  - **Turnstile — fails CLOSED in production** (`config.py` refuses to boot without the key when
    `ENV=production`) and fails OPEN with a `[S-08]` WARN log in dev/test. Not silent anymore.
  - **Resend, Slack** still fail silent (`mailer.py` logs `[mailer:noop]`, `_slack_notify`
    early-returns) — intentional dev ergonomics.
  - **LLM** still fails silent (`ai_service.py` wraps in try/except and falls back to rule-based
    rates on any exception).
  Do not add a *new* silent-fail dependency.

## Test stacks and how to run them

Two Docker Compose stacks, deliberately separate compose projects so they can run at once.

### Test stack — hermetic, mocks only
- Compose file: `docker-compose.test.yml` (project `atlas-test`).
- Ports: backend `18443` (HTTPS), frontend `13000`, mongo not published, stripe-mock/storage-mock
  container-only.
- Env: `.env.test` (not committed — same shape as `.env.example`).
- Boot: `make up-test`; teardown: `make down-test` (tmpfs mongo wiped every up).
- Backend suite: `make test-backend` — **321 collected**, current baseline 313 passed / 3
  pre-existing S-11 canaries / 1 CSRF skip (invariant #7) / 4 xfailed. Runs the modules listed in
  the `test-backend` recipe; the legacy `test_iteration*.py` and `backend_test.py` are excluded
  (H-6).
- E2E: `make e2e` — **13 Playwright tests** across `frontend/e2e/*.spec.js`. Reseeds mutable
  collections via `backend/tests/e2e_reset.py` + `seed.py` before running so runs are
  reproducible. Playwright installs on the host (see the target comment for why).
- Coverage gaps: `make coverage-gaps` regenerates `docs/scripts/.artifacts/coverage.json` and
  runs the gap report — the pytest-inline coverage from `test-backend` alone reads ~1% because
  it only sees pytest imports, not the running backend process.
- `make verify` = `test-backend` + `test-frontend` (placeholder — no frontend unit tests yet) +
  `e2e` + `security-scan` (placeholder — Phase 1d wires gitleaks + bandit + pip-audit + semgrep).
  Today "verify green" means test-backend green + e2e green; the two placeholders always pass.

### Dev stack — real services, hand-driven
- Compose file: `docker-compose.dev.yml` (project `atlas-dev`).
- Ports: backend `8443` (HTTPS, self-signed), frontend `3000`, mongo `27017` (published for
  `mongosh`), storage-mock container-only.
- Env: `.env.dev` (git-ignored — copy from `.env.dev.example` first). `make up-dev` refuses to
  boot without it and prints the bootstrap one-liner.
- Real Stripe (test mode) — webhooks arrive via `stripe listen --forward-to
  https://localhost:8443/api/stripe/webhook --skip-verify` running on the host. No stripe-mock
  in this stack. `STRIPE_WEBHOOK_SECRET` rotates every `stripe listen` session — expect to
  update `.env.dev` + `make down-dev && make up-dev` roughly once per dev day.
- Real Resend for outbound mail (requires a verified sender on your domain).
- Uses the same seed personas as tests (`make seed-dev`) — passwords all `Passw0rd!`, emails at
  `@atlas-test.example.com`. Full login table in `docs/LOCAL_SETUP.md`.
- **First-boot cert trust.** The backend serves a self-signed cert on `:8443`. Chrome blocks the
  SPA's first API call with `ERR_CERT_AUTHORITY_INVALID`. Visit
  `https://localhost:8443/api/marketplace/industries` directly, click Advanced → Proceed, and
  the trust sticks for the session.
- **Cold-start mongo race.** On the very first `make up-dev` the mongo container's tmpfs isn't
  written yet, so the backend's boot-time admin seeder can race the Motor client's connection
  pool warm-up and log a transient `ServerSelectionTimeoutError`. It self-heals on the next
  boot; if a subsequent `make up-dev` still fails, `make down-dev-hard` and try again.
- Storage in dev is the local `storage-mock` — no real cloud provider is wired to
  `backend/storage_client.py` yet (it speaks a proprietary API shape). Uploads never leave
  your laptop.

Full walkthrough (signups, key → env var mapping, troubleshooting): `docs/LOCAL_SETUP.md`.

## Working style
- One issue per branch, one branch per PR. Branch name = backlog id, e.g. `sec/S-03-csrf`.
- Write the failing test first, then the fix.
- Never touch more than one domain (auth / money / projects / revisions / admin) in a single PR.
- Never commit `.env`, seed dumps, or Stripe keys. `git secrets`/gitleaks runs in CI.
