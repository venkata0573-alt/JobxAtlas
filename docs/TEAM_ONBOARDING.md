# TEAM_ONBOARDING.md

Day-one guide for an engineer who has never seen this codebase. Read this end-to-end, run through §3, then start on whatever branch you were pointed at.

---

## 1. What Job Atlas is

Job Atlas (brand: Geminista, operator: Denkoit Softech Pvt. Ltd.) is a two-sided marketplace where **employers hire specialist talent by the hour for short engagements**. Derived from `FEATURES.md`.

**Employers** buy blocks of hours via Stripe Checkout (`starter_10` / `growth_50` / `scale_100` / `enterprise_500`, plus bank transfer). They browse talent, shortlist, send "broadcasts" or accept talent-initiated EOIs, sign a contract, receive deliverables, and approve or request revisions. Larger work runs as a **project** with milestones — each is its own Stripe invoice with a card-on-file auto-collect path when overdue.

**Talent** builds a verified profile (reference-check BGV, KYB for companies), gets discovered via SEO pages + broadcasts + EOI, submits deliverables, gets paid via an admin-triggered payout run, and accrues "Trusted Partner" / "Proven Reliable" badges.

**Money flow:** employer pays → hours credited → allocated to an engagement → talent submits → employer approves → payout row written → admin batches into a run.

**Dispute path:** 5 revisions on a deliverable unlocks a grievance; talent pays a $49 arbitration fee via Stripe; a moderation admin rules; losing party owes; if talent wins the penalty ladder clears and the fee is refunded.

**Admin** is a scope-gated console: support, finance, moderation, customization, superadmin.

---

## 2. Architecture in one page

Single-process FastAPI backend + MongoDB + React 18 SPA + Stripe. All backend routes are registered on the shared `api = APIRouter(prefix="/api")` from `backend/deps.py`; route modules under `backend/routes/*.py` import that router and decorate handlers against it. Auth is a `SameSite=None; Secure; HttpOnly` cookie set by `deps.py::set_auth_cookies`.

**Request path:** browser (`withCredentials: true` axios) → CORS middleware → APIRouter → `Depends(get_current_user)` (cookie → JWT decode → `db.users.find_one`) → role/scope check inside the handler body → Motor async Mongo call → JSON response.

**Money path:** Stripe SDK is synchronous, called from `async def` handlers. Webhooks arrive at `POST /api/stripe/webhook` and dispatch by `metadata.kind` (`dispute_fee` / `milestone` / default = hours purchase). All three branches guard on `payment_status: {"$ne": "paid"}`.

**Cron:** three APScheduler jobs run in-process — monthly rate-nudge scan, daily overdue-invoice scan, nightly CRM sync.

**Config:** every env var flows through `backend/config.py` (typed pydantic-settings). Same rule frontend-side in `frontend/src/config.js`. Any other module reading `os.environ` fails a CI ratchet.

Full anchors: `ARCHITECTURE.md`.

---

## 3. Getting it running

Copy the walkthrough in `docs/LOCAL_SETUP.md`; the traps below are what people actually hit.

```
cp .env.dev.example .env.dev
$EDITOR .env.dev                 # fill the REPLACE_… placeholders
make up-dev                       # builds + boots mongo, backend, frontend, storage-mock
make seed-dev                     # inserts 6 personas (all password Passw0rd!)
stripe listen \                   # in a separate terminal, keep open
  --forward-to https://localhost:8443/api/stripe/webhook \
  --skip-verify
open http://localhost:3000
```

Personas + which flow each is for: `docs/LOCAL_SETUP.md §Personas`.

### Traps we've all hit

- **Mongo cold-start race.** First `make up-dev` may log a transient `ServerSelectionTimeoutError` and the admin seeder can no-op. Retry `make down-dev && make up-dev`; if still stuck, `make down-dev-hard` then `make up-dev`.
- **Chrome self-signed cert.** Backend HTTPS on `:8443` uses a self-signed cert. First API call fails with `ERR_CERT_AUTHORITY_INVALID`. Visit `https://localhost:8443/api/marketplace/industries`, click **Advanced → Proceed**, trust sticks for the session.
- **Port conflicts on 3000 / 27017.** Local `yarn start` or `mongod` will collide. Stop the local process, or edit `ports:` in `docker-compose.dev.yml`.
- **`.local` email rejected.** Pydantic `EmailStr` refuses `.local` (RFC 6762 mDNS reserved). `ADMIN_EMAIL=admin@dev.local` → admin never logs in. Keep the example's `admin@example.com`.
- **Service worker cache.** `frontend/public/sw.js` caches the app shell; a hard reload after a UI edit can still serve the cached shell. Fix: DevTools → Application → Service Workers → **Unregister**, then Cmd-Shift-R. Or incognito.
- **`STRIPE_WEBHOOK_SECRET` rotates every `stripe listen` run.** Copy the new `whsec_…` from its first output line into `.env.dev`, then `make down-dev && make up-dev`.

---

## 4. How we work

- **One backlog item per branch, one branch per PR.** Branch name = backlog id (e.g. `sec/S-26-drop-bearer`, `feat/F-04-scheduler-tab`).
- **Failing test first, then the fix.** Backend tests go in `backend/tests/`, browser tests in `frontend/e2e/`.
- **One domain per PR.** Auth, money, projects, revisions, admin — pick one. Don't ship a diff that spans two.
- **`make verify` green before merge.** Today that's `test-backend` (313 pass baseline) + `e2e` (13 pass baseline); the `test-frontend` and `security-scan` legs are placeholders that always pass.
- **Commit and push at the end of every session.** Even work-in-progress. This repo has a rolling reconciliation habit — long-lived local branches drift out of sync with docs.
- **Every closed backlog item gets struck through in `SECURITY_BACKLOG.md`** with the fix commit sha, so `git blame` traces closures back to the change.

The 11 hard invariants (cookie-only auth, `_id: 0` projection, config.py as the sole env boundary, etc.) live in `CLAUDE.md`. Read them before your first PR.

---

## 5. Directory map

One line per significant file. Full inventory in `docs/ENDPOINT_INVENTORY.md`.

**Backend**
- `backend/server.py` — kitchen sink; most routes still live here (F-03 will split). App bootstrap, CORS, Stripe webhook, hours purchase, engagements/deliverables, EOI, SEO pages, curated talent.
- `backend/deps.py` — singletons: Motor client, `api` router, JWT helpers, `get_current_user`, `set_auth_cookies`, admin-scope catalog. Everyone imports from here.
- `backend/config.py` — sole env boundary. Ten nested pydantic-settings classes.
- `backend/routes/auth.py` — auth + email verification + BGV + CRM.
- `backend/routes/admin.py` — admin console; cycle-breaks into `server.py` via late imports.
- `backend/routes/marketplace.py` — marketplace metadata + shortlist CRUD.
- `backend/routes/projects.py` — projects, milestones, invoices, auto-collect.
- `backend/routes/revisions.py` — revision ladder, disputes, refund, audit PDF.
- `backend/routes/engagements.py` — **shell file, dead**. Endpoints live in `server.py`.
- `backend/ai_service.py` — LLM rate suggest. Imports `emergentintegrations` (F-01 fresh-install blocker — test image shims it).
- `backend/mailer.py` — Resend wrapper; silent no-op when key unset.
- `backend/storage_client.py` — object-storage client (dev = local mock; no real provider wired).
- `backend/work_integrations.py` — Monday/Asana/Trello/ClickUp/Jira/Confluence adapters.
- `backend/tests/` — pytest suite; `seed.py` builds the personas.

**Frontend**
- `frontend/src/App.js` — router + provider tree + toasts.
- `frontend/src/config.js` — sole env-var reader (`REACT_APP_*`).
- `frontend/src/context/AuthContext.jsx` — auth state.
- `frontend/src/lib/api.js` — axios instance + `formatErr`.
- `frontend/src/pages/` — one file per route. `frontend/src/components/ProtectedRoute.jsx` — role gate.
- `frontend/src/legal/content.js` — static legal content.
- `frontend/e2e/` — Playwright specs. `frontend/public/sw.js` — service worker (see §3).

**Repo root**
- `docker-compose.test.yml` — hermetic test stack (mocks, tmpfs mongo).
- `docker-compose.dev.yml` — dev stack (real Stripe test-mode + Resend + Turnstile).
- `Makefile` — `up-test`, `test-backend`, `e2e`, `up-dev`, `seed-dev`, `down-dev-hard`.
- `security/*.yml` — policy files the invariant tests ratchet against.
- `docs/scripts/` — AST scanners (route inventory, features-drift, coverage gaps).
- Root docs: `CLAUDE.md`, `ARCHITECTURE.md`, `FEATURES.md`, `PROJECT_STATUS.md`, `SECURITY_BACKLOG.md`, `CONTRACTOR_SPLIT.md`.

---

## 6. Current state, honestly

Full picture: `PROJECT_STATUS.md`.

Baseline as of this write:
- **Backend**: 321 tests collected, 313 pass + 3 pre-existing S-11 cross-tenant canaries + 1 CSRF skip (invariant is scaffolding — middleware not registered yet) + 4 xfailed.
- **E2E**: 13 Playwright specs, all green post-S-31.

Covered by tests: auth + email verification, marketplace, EOI, engagements sign/deliver/approve, revision ladder, dispute + refund audit, grievances, hours purchase (Stripe webhook signed via a JS/Python fixture pair), milestone payments, config-boundary AST scan, public-route + CSRF-exempt ratchets.

Not yet covered: frontend unit tests (none exist), the `security-scan` Makefile leg (placeholder). CI runner isn't wired — `make verify` runs locally only. The dev stack's `storage-mock` papers over the fact that no real cloud-storage provider is wired to `storage_client.py` (it speaks a proprietary shape); uploads work locally, production would 500.

---

## 7. What not to touch without discussion

Message first if a PR would edit any of these — each is a one-wrong-line-has-real-user-impact surface.

- **`backend/routes/auth.py`** — cookie mechanics, JWT, refresh, CRM token validation. Wrong attribute logs everyone out (see S-31 history) or leaks tokens.
- **Money paths** — `server.py::stripe_webhook` + `_credit_hours_if_paid`, `routes/projects.py` milestone checkout + off-session PaymentIntent, `routes/revisions.py` pay-fee + refund. Append-only + idempotent. A wrong `$inc` credits real dollars.
- **`backend/routes/revisions.py` penalty ladder** — visibility, rate bias, dispute right, refund thresholds. Product rule; needs a `FEATURES.md §12` update in the same PR.
- **`backend/routes/admin.py` + `backend/deps.py` scope catalog** — permission model. Admin endpoint without `_require_scope(...)` is a bug (S-09).
- **`backend/config.py`** — sole env boundary. A hoisted `os.environ` defeats production Turnstile enforcement. AST scan blocks this, but only as far as its exemption list.
- **`backend/deps.py`** — every module imports from here. Rename ripples everywhere; wrong edit stops the whole app booting.
- **`security/*.yml`** — CSRF-exempt + public-route policy files. Adding an entry is P0-weight review.
