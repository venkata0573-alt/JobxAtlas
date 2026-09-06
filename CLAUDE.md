# CLAUDE.md — Job Atlas / Geminista

Read `ARCHITECTURE.md` and `FEATURES.md` before any change. They are ground truth. If code
contradicts them, fix the code **or** update the doc in the same PR — never leave them diverged.

## Stack
FastAPI (single process, Motor + APScheduler in-process) · MongoDB · React 18 SPA (craco) · Stripe.
Backend `/app/backend`, frontend `/app/frontend`. All routes share one `APIRouter` from `deps.py:37`.

## Hard invariants — never break these
1. Every app-level PK is `str(uuid.uuid4())` via `new_id()` (`deps.py:59`). Never expose Mongo `_id`.
2. Every read projects `{"_id": 0}`.
3. Auth is the httpOnly `access_token` cookie. Never move a token into localStorage or a URL.
4. Route modules import from `deps` only. `routes/*` → `server.py` imports must stay **inside handler
   bodies** (cycle break, see `admin.py:129,188,197`). Never hoist them to module level.
5. `routes/engagements.py` is dead. Do not add endpoints there.
6. Any new admin endpoint uses `_require_scope(user, "<scope>")`. `role == "admin"` alone is a bug.
7. CSRF protection is default-deny middleware over every non-GET request.
   Exemptions live in `security/csrf_exempt.yml` as exact (method, path)
   pairs with a written justification per entry. Adding an entry requires
   the same review as a P0 change. Do not exempt a route by editing the
   middleware.
8. New collection ⇒ new index in the startup block (`server.py:2749`). No exceptions.
9. No new synchronous network/PDF call inside `async def`. Wrap in `asyncio.to_thread` or use `httpx`.
10. Money paths are append-only + idempotent. Never delete a `payment_transactions` row.

## Definition of done for any task
- [ ] Behaviour matches the relevant `FEATURES.md` section (or that section is updated).
- [ ] Test added under `backend/tests/` (pytest+httpx) or `frontend/e2e/` (Playwright).
- [ ] `test_result.md` status_history appended per the protocol block in that file.
- [ ] No new entry in `SECURITY_BACKLOG.md` introduced; if the change closes one, mark it CLOSED.
- [ ] `make verify` green.

## Known landmines (do not "fix" by accident)
- `_scheduler = None` at `server.py:2870` runs before the startup handler assigns it. Not a bug.
- `PaymentSuccess.jsx` polling and the Stripe webhook both credit hours. Both are guarded by
  `payment_status: {"$ne": "paid"}`. Keep both guards if you touch either path.
- `emergentintegrations` is not on PyPI and not in `requirements.txt`. Boot dies at `ai_service.py:6`
  if the image doesn't provide it. Treat it as an optional import (see backlog F-01).
- Turnstile, Resend, Slack, LLM all **fail open / silent**. Do not add a new silent-fail dependency.

## Working style
- One issue per branch, one branch per PR. Branch name = backlog id, e.g. `sec/S-03-csrf`.
- Write the failing test first, then the fix.
- Never touch more than one domain (auth / money / projects / revisions / admin) in a single PR.
- Never commit `.env`, seed dumps, or Stripe keys. `git secrets`/gitleaks runs in CI.
