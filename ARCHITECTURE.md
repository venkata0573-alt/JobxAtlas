# ARCHITECTURE.md — Job Atlas backend, ground truth

Written for the engineer who cloned this today and needs to ship a change tomorrow. Every claim points at a file (and, where the target is stable, a symbol name) rather than a raw line number — line numbers drift on every refactor and are the first thing to rot. Where the code does something surprising or contradictory, that is called out plainly.

The stack is a single FastAPI process (Motor + APScheduler in-process), one MongoDB database, a React 18 SPA on `craco`, and Stripe for money. Everything is registered on the shared `APIRouter` from `backend/deps.py` (the module-level `api = APIRouter(prefix="/api")`); route modules under `backend/routes/*.py` import that router and decorate handlers against it.

---

## Layer diagram

```
                  ┌─────────────────────────────────────────┐
                  │  React SPA (frontend/src)               │
                  │  - axios base = REACT_APP_BACKEND_URL/api│
                  │  - withCredentials: true (cookies)       │
                  │  - Sonner toasts, react-router-dom       │
                  └─────────────────────────┬───────────────┘
                                            │  HTTPS + cookies
                                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│  FastAPI app  (backend/server.py)                                     │
│  ┌───────────────────────┐   ┌──────────────────────────────────────┐ │
│  │ Middleware            │   │ Single APIRouter (prefix="/api")     │ │
│  │  - CORSMiddleware     │◄──┤ backend/deps.py (module-level `api`) │ │
│  │  server.py bottom     │   │                                      │ │
│  └───────────────────────┘   │  routes/auth.py       (~30 endpoints)│ │
│                              │  routes/admin.py      (~30 endpoints)│ │
│                              │  routes/marketplace.py (~9 endpoints)│ │
│                              │  routes/projects.py   (~40 endpoints)│ │
│                              │  routes/revisions.py  (~20 endpoints)│ │
│                              │  routes/engagements.py (unused shell)│ │
│                              │  + inline server.py routes           │ │
│                              └────┬────────────┬────────────────────┘ │
│                                   │            │                      │
│  ┌─────────────────┐  ┌───────────▼──────┐  ┌──▼───────────┐          │
│  │ APScheduler     │  │  Motor client    │  │  Stripe SDK  │          │
│  │  3 cron jobs    │  │  deps.py         │  │  (sync)      │          │
│  │  in startup     │  │                  │  │  server.py   │          │
│  └────────┬────────┘  └─────────┬────────┘  └──────┬───────┘          │
└───────────┼─────────────────────┼──────────────────┼──────────────────┘
            │                     │                  │
      wakes │              queries│                  │ REST
            │                     ▼                  ▼
            │            ┌────────────────┐  ┌──────────────┐
            └───────────►│  MongoDB       │  │  Stripe API  │
                         │  40+ collections│  │  Checkout    │
                         │  7 indexes total│  │  Refund      │
                         │                 │  │  Webhook     │
                         └────────────────┘  └──────┬───────┘
                                                    │ POST /api/stripe/webhook
                                                    └───────► back into FastAPI
    Optional external calls (silent-fail if unset — but see §7 for the
    post-F-11 nuance around Turnstile):
      Resend (mailer.py)      RESEND_API_KEY
      Slack webhook           SLACK_WEBHOOK_URL       (routes/projects.py::_slack_notify)
      Cloudflare Turnstile    TURNSTILE_SECRET_KEY    (routes/auth.py::_verify_turnstile)
      Anthropic via
        emergentintegrations  EMERGENT_LLM_KEY        (ai_service.py::suggest_hourly_rate)
      HubSpot / Salesforce /
        Slack / SharePoint    per-employer bearer tokens
      Monday / Asana / Trello
        / Jira / ClickUp      per-user API tokens
```

Key non-obvious facts up front:
- `emergentintegrations` (imported at `ai_service.py:5` as `from emergentintegrations.llm.chat import LlmChat, UserMessage`) is not on PyPI and is not shipped alongside `requirements.txt`. It is a **confirmed fresh-install blocker** (F-01) — `pip install -r backend/requirements.txt` fails from any clean checkout. The test image (`backend/Dockerfile.test`) strips it from the requirements file and installs a two-class shim into site-packages so imports resolve. `routes/auth.py` transitively depends on it via `from ai_service import suggest_hourly_rate`.
- Every write in the system uses `str(uuid.uuid4())` as the app-level primary key (via `new_id()` in `deps.py`); Mongo's `_id: ObjectId` is treated as noise and stripped from reads with `{"_id": 0}`.
- Only seven collections have indexes (created in the `@app.on_event("startup")` handler in `server.py`). Everything else — `deliverables`, `payouts`, `reviews`, `revision_requests`, `grievances`, `projects`, `project_milestones`, `broadcasts`, `notifications`, etc. — is queried on unindexed fields.
- Auth cookies are `SameSite=None; Secure; HttpOnly` (set in `deps.py::set_auth_cookies`, with matching attributes on the deletion side after S-31 closed). There is **no CSRF middleware registered yet** — the exemption policy in `security/csrf_exempt.yml` is scaffolding for S-01. Every state-mutating POST is CSRF-exposed until S-01 lands.

---

## 1. Boot sequence

Command: `uvicorn server:app` (no factory; the module-level `app` in `server.py` is imported directly).

**Environment authority: `backend/config.py`.** As of F-11, config.py is the sole
module in `backend/` that reads the process environment. Every other module
imports typed settings via `from config import settings`. There is no
`os.environ` / `os.getenv` call anywhere else in `backend/`, and
`backend/tests/test_config.py::test_no_module_outside_config_reads_os_environ`
enforces this by AST-scanning `backend/` on every test run. The env-var → typed
field mapping lives in `.env.example` (human-friendly, grouped by service) and
`docs/CONFIG_INVENTORY.md` (per-var provenance). Do NOT duplicate env var names
in this doc.

Order of events, in the order Python executes them:

1. **`from config import settings`** near the top of `server.py`. This is the module that fires pydantic-settings' `.env` file load and every env-var read. If any required var is missing or invalid (e.g. `CORS_ORIGINS='*'`), config.py's `_build_settings` factory raises **one aggregated `RuntimeError`** naming every problem at once — grouped by service — instead of forcing whack-a-mole.
2. **Three local imports fire, in order** (all near the top of `server.py`):
   - `from ai_service import suggest_hourly_rate` — this transitively runs `from emergentintegrations.llm.chat import LlmChat, UserMessage` at `ai_service.py:5`. If the package is missing (see F-01), boot dies here with `ModuleNotFoundError`.
   - `from work_integrations import ...` — pulls the requests-based sync adapters.
   - `from storage_client import init_storage, put_object, get_object, APP_NAME as STORAGE_APP` — loads without contacting the storage service.
3. **`from deps import (...)`** — this is the moment the app becomes reachable to Mongo.
   - `deps.py` exports `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `STRIPE_WEBHOOK_SECRET` as thin proxies for `settings.mongo.url` / `.mongo.db_name` / `.auth.jwt_secret` / `.stripe.webhook_secret`. The module no longer reads env directly.
   - `deps.py` constructs `AsyncIOMotorClient(MONGO_URL)` at module load and selects `client[DB_NAME]`. Motor connects lazily on first query; a bad URL survives import and surfaces as 500s later.
   - `deps.py` creates the shared `api = APIRouter(prefix="/api")`.
4. **`stripe.api_key = settings.stripe.secret_key`** at the top of `server.py`. The old silent fallback (`sk_test_emergent`, S-05) is gone — a missing `STRIPE_SECRET_KEY` fails boot at step 1.
5. **`app = FastAPI(title="Job Atlas API")`**, immediately after.
6. **The five route modules import**, in this order: `routes.auth`, `routes.admin`, `routes.marketplace`, `routes.projects`, `routes.revisions`. Each `from deps import api, ...` at the top, then decorates handlers with `@api.post(...)` / `@api.get(...)`. Because they mutate the same shared router object, order does not matter for routing but does matter for anything that depends on module-import side effects (there are none — the modules only register handlers). `routes/__init__.py` is a 6-line placeholder; it does not do package-level wiring.
7. **The `@app.on_event("startup")` handler runs** after uvicorn reports "Application startup complete":
   - Optional `init_storage()` call, wrapped in try/except (non-fatal). Post-F-11 this no longer depends on `EMERGENT_LLM_KEY` — S-15 split `STORAGE_TOKEN` into its own required field.
   - Seven `db.<col>.create_index(...)` calls for `users.email` (unique), `users.id` (unique), `engagements.id` (unique), `payment_transactions.session_id` (unique), `work_items.user_id`, `eois.id` (unique), `eois.talent_id`. That is the entire set of indexes in the codebase.
   - **Admin seeder** (S-20 partial). Reads `settings.auth.admin_email` and `settings.auth.admin_password`. **`admin_password` has no default** — if unset, the seeder logs `WARNING: ADMIN_PASSWORD unset — skipping admin seeder for <email>` and skips the insert entirely; there is no `Admin@2026` fallback. `admin_email` still defaults to the legacy `admin@talenthub.io` (S-20 remainder).
   - **Legacy industry backfill**: rewrites old `buyer archetype` labels to the new industry taxonomy using `LEGACY_INDUSTRY_MAP` from `deps.py`. Runs every startup.
   - **APScheduler** — three cron jobs (all `misfire_grace_time=3600`, `replace_existing=True`):
     - `monthly_rate_nudge_scan` — `CronTrigger(day=1, hour=9, minute=0)` invokes `_scan_and_record_rate_nudges`.
     - `daily_overdue_invoice_scan` — `CronTrigger(hour=8, minute=0)` invokes `scan_overdue_invoices` late-imported from `routes.projects`.
     - `nightly_crm_sync` — `CronTrigger(hour=2, minute=0)` invokes `_sync_shortlists_to_crm(trigger="cron")` late-imported from `routes.auth`.
     - `_scheduler.start()`. Failure is caught and logged as a warning — the app boots even if scheduling is broken.
8. **`app.include_router(api)`** runs *after* the startup event registration (physically at the bottom of `server.py`). Because `app.on_event` and `app.include_router` are declarative, order does not matter for FastAPI, but visually the router is mounted at the bottom of the file, not the top.
9. **CORS middleware** is added last: `app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=settings.urls.cors_origins, allow_methods=["*"], allow_headers=["*"])`. The old `"*"` fallback (S-02) is gone. `CORS_ORIGINS` is required at boot as a comma-separated list; `config.UrlSettings`'s field validator rejects `"*"` as an entry.

### What breaks and where

Post-F-11, every required-var miss produces the same shape: **one `RuntimeError` at
config-module import, listing every missing variable grouped by service, with a
pointer at `.env.example`.** No more scattered `KeyError` / silent fallback / late-
symptom failure modes.

| Failure | Symptom |
| --- | --- |
| Any REQUIRED var unset (Mongo, Stripe, JWT, storage token, storage URL, CORS, crypto salts, ENV) | Config-module import raises `RuntimeError` naming every missing var at once. Worker never becomes ready. Message ends `Set the missing variables (see .env.example for descriptions).` |
| `CORS_ORIGINS='*'` (or empty CSV) | Config-module import raises `RuntimeError` with `CORS_ORIGINS must not contain '*' — allow_credentials=True forbids wildcard origins (S-02)`. Wildcard values are refused explicitly. |
| `ENV=production` and `TURNSTILE_SECRET_KEY` unset | Config-module import raises `RuntimeError` from the Settings model_validator naming `TURNSTILE_SECRET_KEY` under "Environment / global". |
| Mongo unreachable at runtime | Import succeeds; first query 500s. |
| `emergentintegrations` missing | Import-time `ModuleNotFoundError` at `ai_service.py:5`, cascades through `routes/auth.py` (`from ai_service import suggest_hourly_rate`). Whole app dies. (F-01) |
| `RESEND_API_KEY` unset (optional) | `mailer.py` sets `_resend = None`; every `send_email` returns `{"sent": False, ...}` and logs `[mailer:noop]`. Intentional silent-fail. |
| `EMERGENT_LLM_KEY` unset (optional) | `ai_service.py::suggest_hourly_rate` returns the rule-based fallback. Intentional silent-fail. |
| `TURNSTILE_SECRET_KEY` unset in dev/test (S-08 partial) | `_verify_turnstile` fail-opens with `WARNING [S-08] TURNSTILE_SECRET_KEY unset (env=<value>) — captcha check BYPASSED for remote_ip=<ip>`. In `ENV=production` this branch is unreachable — config refuses to boot. |
| `SLACK_WEBHOOK_URL` unset (optional) | `_slack_notify` early-returns silently. Intentional. |
| `ADMIN_PASSWORD` unset (S-20 partial) | Admin seeder logs `WARNING: ADMIN_PASSWORD unset — skipping admin seeder for <email>` and skips the insert. No hardcoded credential is ever inserted. |
| `APP_BASE_URL` / `PUBLIC_BASE_URL` / `PUBLIC_SITE_URL` unset (optional) | Email templates and audit-PDF QR codes render with empty base URLs; recipients click into nothing. Currently optional; may be tightened later. |
| Scheduler start throws | Logged as warning; app continues without cron. |

---

## 2. Module map

Every file in `backend/`, one line of "who owns what" plus the import edges.

### `backend/deps.py` (171 lines)
Owns the singletons: `client`, `db`, `api` router, `JWT_SECRET`, admin scope catalog, marketplace constants, `now/new_id/hash_pw/verify_pw/create_token/get_current_user/set_auth_cookies/has_admin_scope`. Zero cross-route imports. Everyone imports from this.

### `backend/config.py` (310 lines)
The sole environment boundary (F-11). Ten nested `BaseSettings` classes (`MongoSettings`, `StripeSettings`, `MailSettings`, `SlackSettings`, `StorageSettings`, `LLMSettings`, `AuthSettings`, `CryptoSettings`, `UrlSettings`, `BusinessRules`), one top-level `Settings`, and a `_build_settings()` factory that aggregates every missing-var error into a single `RuntimeError`. `settings: Settings = _build_settings()` at module bottom is the exported singleton.

### `backend/server.py` (2,906 lines)
The kitchen sink. Owns app bootstrap (`app = FastAPI(...)`), CORS middleware (added at file bottom), the `@app.on_event("startup")` + `("shutdown")` handlers, admin seeder inside startup, APScheduler configuration inside startup, the Stripe webhook (`@api.post("/stripe/webhook")` → `stripe_webhook`), all hours-purchase + payments routes (`/payments/*`), file uploads, engagements CRUD, deliverables, reviews, payouts helpers, dashboard metrics, SEO landing pages (`/seo/hire/{skill}` + `/seo/hire-city/{slug}`), employer/talent list endpoints, EOI (`/eoi` + `/eoi/{id}/accept` + `/eoi/{id}/withdraw`), broadcasts (`/shortlist/broadcast` + `/talent/me/broadcasts` + the SSE variant), rate-nudge scanner (`_scan_and_record_rate_nudges`), curated talent constant `_CURATED_TALENT` (~250 rows). Imports `routes.auth`, `routes.admin`, `routes.marketplace`, `routes.projects`, `routes.revisions` at module level (one-way).

### `backend/routes/__init__.py` (6 lines)
Placeholder. Only exists to make `routes/` a package.

### `backend/routes/auth.py` (1,204 lines)
Auth + verification + CRM. Endpoints: register, login, logout, `/auth/me`, `/profile`, `/profile/suggest-rate`, email verification, `/verification/{company,bgv,me}`, public `/reference-check/{token}` (GET+POST), `/trust/{stats,timeseries,timeseries/details,timeseries/details/pdf,verify-drill,verify-drill/{sig}}`, `/admin/reference-checks/{talent_id}`, `/integrations/crm/*` (connect, list, disconnect, push-lead, sync-now, sync-log). Plus the nightly `_sync_shortlists_to_crm` helper. Imports `suggest_hourly_rate` from `ai_service` at module top (the F-01 transitive-fail path).

### `backend/routes/admin.py` (541 lines)
Admin console API. Endpoints: `/admin/me`, users listing + notes + hours-adjust, bank-transfer approve/reject, reviews approve/reject, grievances list + resolve, payouts run + runs + mark-paid, rate-nudge scan trigger, scheduler status, customization GET/PUT + public `/customization/public`, verifications approve/reject, staff CRUD. Imports `_compute_talent_earnings`, `_scan_and_record_rate_nudges`, `_scheduler` from `server` late-bound inside handler bodies (`admin.py:129,188,197`) — this is deliberate cycle-breaking: `server.py` imports `routes.admin` at module load, so `routes.admin` cannot import `server` at module load without a cycle. Late imports work because they run at request time, after both modules are fully loaded.

### `backend/routes/engagements.py` (40 lines)
**Shell file.** The engagements API actually lives in `server.py` (`POST /api/engagements`, `/engagements/sign`, `/deliverables`, `/deliverables/{id}/approve`, etc.). This file exists as a placeholder for a future refactor (F-03) and is not registered anywhere useful. The docstring lists every endpoint that belongs here. Do not add endpoints here without also wiring the router — nothing imports from it.

### `backend/routes/marketplace.py` (197 lines)
Public marketplace metadata. `/marketplace/industries`, `/marketplace/stats`, `sitemap.xml`, `/seo/skills`, `/seo/city-skills`, shortlist CRUD (`POST/GET/DELETE /shortlist`). Imports SEO constants from `deps`.

### `backend/routes/projects.py` (1,440 lines)
Projects + invoicing + auto-collect. Endpoints: `/admin/project-leads` list + convert; `/projects/mine`, `/projects/workspace/{id}` load; phase advance, variance log, risk register, RACI, milestones; invoice PDF; milestone-payment status polling; `/invoices/mine`; Stripe SetupIntent flows for card-on-file (`/billing/setup-checkout`, `/billing/setup`, `/billing/status`); overdue invoice daemon `scan_overdue_invoices` + manual trigger endpoint; template save; admin verification-with-refs. Imports Slack helper `_slack_notify`.

### `backend/routes/revisions.py` (1,123 lines)
Revision loop + disputes + refunds + audit PDF. Endpoints: request-revision, resubmit, list/summary, open dispute, admin revisions list + rule, flagged employers, refund analytics, recovery status, pay dispute fee, fee status, `mark_dispute_fee_paid` helper (called from the Stripe webhook via late import in `server.py`), admin refund fee, refund audit PDF, verify-signature. The `_refund_audit_signature` helper still uses `sha256(secret + msg)` (not HMAC) — S-04 partial: F-11 collapsed the fallback chain to two independent required fields (`REFUND_AUDIT_SIGN_SECRET`, `DRILL_SIGN_SECRET`), but the length-extendable hash primitive and the verify-endpoint's lookup-instead-of-recompute behaviour are unchanged.

### `backend/ai_service.py` (53 lines)
Only exports `suggest_hourly_rate`. Uses `emergentintegrations.llm.chat.LlmChat` with model `anthropic/claude-sonnet-4-5-20250929`. Fallback path returns a deterministic rule-based range when `EMERGENT_LLM_KEY` is missing or the call raises.

### `backend/mailer.py` (85 lines)
Wraps the Resend SDK. `_resend` client is initialised only if `RESEND_API_KEY` is set; otherwise every `send_email` call returns `{"sent": False, "id": None, "reason": "..."}`. The blocking Resend SDK call is wrapped in `asyncio.to_thread` inside `send_email`, so it does not stall the event loop.

### `backend/storage_client.py` (65 lines)
Talks to an external object store over sync `requests` (five call sites across `init_storage`, `put_object`, `get_object`, and their 404 retry paths). Used for avatar / portfolio / evidence uploads. **S-15 closed**: `STORAGE_TOKEN` is now its own required env var (was `EMERGENT_LLM_KEY` reused across LLM and storage). **S-27 closed**: `INTEGRATION_PROXY_URL` is required at boot with no fallback to `integrations.emergentagent.com`.

### `backend/work_integrations.py` (208 lines)
Provider adapters for Monday / Asana / Trello / ClickUp / Jira / Confluence. All use the synchronous `requests` library with a 15s timeout — six sync call sites, one per provider, at `work_integrations.py:77,89,101,108,117,134`. On any failure returns a stub sample so the UI can render. Called from `server.py`'s `connect_integration` / `sync_integration` handlers inside `async def` — see §9 for the blocking-I/O implication.

### Cross-module call summary
- `server.py` → `routes.*`: module-level (five imports at the top of `server.py`).
- `routes.admin.py` → `server.py`: late/handler-scoped only (`admin.py:129,188,197`) — cycle break.
- `server.py` → `routes.projects.scan_overdue_invoices`: late inside the `daily_overdue_invoice_scan` scheduler job body.
- `server.py` → `routes.auth._sync_shortlists_to_crm`: late inside the `nightly_crm_sync` scheduler job body.
- `server.py` → `routes.revisions.mark_dispute_fee_paid`: late inside the Stripe webhook's `kind == "dispute_fee"` branch. Called by fully-qualified name; the module was already registered at import so this is fine, but it means the webhook path silently depends on `revisions.py` staying importable.
- `server.py` → `routes.revisions.is_proven_reliable / _record_clean_approval / _reset_clean_streak`: late inside talent-card computation and deliverable-approve flows.

---

## 3. Request lifecycle (authenticated route)

Walk of `GET /api/talent/me/broadcasts` as a representative authenticated call.

1. **TCP / TLS + HTTP** — uvicorn accepts, hands to Starlette.
2. **CORS middleware** (added at the bottom of `server.py`). If the origin is allowed and `withCredentials` is set, `Access-Control-Allow-Origin` echoes the origin and `Allow-Credentials: true` is added. Preflight `OPTIONS` returns 200. Wildcard origins are refused at config load (S-02).
3. **Router match** — the shared `api = APIRouter(prefix="/api")` from `deps.py` resolves the path.
4. **Cookie extraction + JWT decode** — the handler declares `user: dict = Depends(get_current_user)`. `deps.py::get_current_user`:
   - Read `access_token` cookie.
   - **Fallback: `Authorization: Bearer <token>` header** — this is S-26 legacy attack surface. No first-party client sends a Bearer token (verified: `grep -rn "Authorization" frontend/src/` returns nothing). The branch is scheduled to be removed before S-01's CSRF middleware lands.
   - No token → 401 "Not authenticated".
   - `jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])`. HS256, 12h expiry for access tokens / 7d for refresh (both set in `deps.py::create_token`).
   - Enforce `type == "access"`. Refresh tokens can't authenticate directly.
   - Lookup `db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})`. This is one Mongo round-trip on every authenticated request. `users.id` is unique-indexed (startup handler) so it's cheap.
   - Expired signature → 401 "Token expired"; any other JWT error → 401 "Invalid token".
   - **No token_version field, no revocation list, no refresh rotation.** Logout clears cookies with the correct attributes post-S-31 (path/secure/samesite mirrored), but a stolen access token remains valid until its 12h expiry (S-07).
5. **Scope / role check** — done inside the handler body, not via a dependency. Two patterns:
   - Role: `if user.get("role") != "talent": raise HTTPException(403, ...)`.
   - Scope: `_require_scope(user, "moderation")` in `revisions.py` and `admin.py`, or `has_admin_scope(user, "finance")` from `deps.py`. Superadmin implies all scopes.
   - Two admin endpoints — `POST /admin/rate-nudges/scan` and `GET /admin/scheduler` at `admin.py:186-211` — check `user.get("role") != "admin"` directly and bypass scopes entirely. Any admin can trigger them regardless of assigned scopes. Tracked as S-09.
6. **Business logic** — Mongo I/O via Motor's async driver (`await db.<col>.find(...)`, `await ... .to_list(N)`).
7. **Response serialization** — FastAPI serializes the returned dict as JSON. Mongo `_id` fields are usually projected out with `{"_id": 0}`; when they aren't, the raw `ObjectId` is stringified inconsistently.
8. **Error handling** — `HTTPException` is caught by FastAPI's default handler and returned as `{"detail": "..."}`. Un-caught exceptions become 500. There is no global exception middleware; the Slack helper never logs 500s.
9. **Set-Cookie on login/register** — `deps.py::set_auth_cookies` writes:
   ```
   access_token=...; Path=/; Max-Age=43200; HttpOnly; Secure; SameSite=None
   refresh_token=...; Path=/; Max-Age=604800; HttpOnly; Secure; SameSite=None
   ```
   No `Domain` attribute (so cookies are host-scoped). `Secure` means these cookies never work over HTTP; the local dev server must be HTTPS or a proxy that adds Secure at the edge, otherwise the browser refuses to store them. `SameSite=None` + no CSRF middleware (still open — S-01) = every state-changing endpoint is CSRF-open.

### Which routes use which dependency

- `Depends(get_current_user)` — nearly every non-public endpoint.
- `_require_scope(user, "<scope>")` — used inside `admin.py` (support/finance/moderation/customization/superadmin) and `revisions.py` (moderation).
- `has_admin_scope(user, "<scope>")` — used inside `projects.py` (finance for invoice issue/paid, superadmin/customization for save-as-template).
- Role checks (`user.get("role") == "..."`) — used in `auth.py`, `server.py`, `projects.py`, `revisions.py` for talent/employer/admin gating.

---

## 4. Data model

App-level identity is always a `str` UUID from `new_id()` in `deps.py`. Every read strips `_id` with `{"_id": 0}`. Only these indexes exist (created in the startup handler):

| Collection | Index | Uniqueness |
| --- | --- | --- |
| `users.email` | asc | unique |
| `users.id` | asc | unique |
| `engagements.id` | asc | unique |
| `payment_transactions.session_id` | asc | unique |
| `work_items.user_id` | asc | non-unique |
| `eois.id` | asc | unique |
| `eois.talent_id` | asc | non-unique |

Everything else — `deliverables`, `payouts`, `reviews`, `grievances`, `revision_requests`, `projects`, `project_milestones`, `project_invoices`, `project_variances`, `project_alerts`, `project_risks`, `dispute_fee_transactions`, `refund_audit_receipts`, `drill_receipts`, `reference_checks`, `broadcasts`, `notifications`, `support_notes`, `audit_log`, `site_customization`, `crm_integrations`, `crm_sync_log`, `integration_tokens`, `shortlists`, `rate_nudges`, `job_runs`, `referrals`, `newsletter_signups`, `custom_project_templates`, `payment_reminders`, `payout_runs`, `connected_accounts`, `files`, `project_leads` — is queried on unindexed fields. This is fine at demo scale; at any real volume, `deliverables.find({"engagement_id": ...})` and `revision_requests.find({"deliverable_id": ...})` will collscan. Tracked as S-12.

### Collection catalog

**Identity / access**
- `users` — the everything table. Fields: `id`, `email`, `password_hash`, `role` (`talent|employer|admin`), `name`, `hours_balance`, `hero_placement`, `admin_permissions[]`, `email_verified`, `email_verification_token`, `verification_status`, `stripe_customer_id`, `stripe_payment_method_id`, and the nested `profile` blob (headline, bio, skills, hourly_rate, portfolio_images, work_history, references, government_id_url, availability, revision_flags, visibility_score, rate_bias_pct, clean_streak, abusive_pattern_flag, …). Written by nearly every module. Read by everything.
- `support_notes` — support-team notes per user; written from `admin.py`.
- `audit_log` — trail of hours adjustments and KYB perks grants (`admin.py`).
- `site_customization` — hero, CTAs, feature flags; admin write, public read via `/customization/public`.

**Marketplace**
- `shortlists` — `{employer_id, talent_id, headline, hourly_rate, skills, is_curated, created_at}`. `marketplace.py`, read by nightly CRM sync.
- `broadcasts` — hire-intent inbox row per (employer_id, talent_id). Written by `POST /api/shortlist/broadcast`, read by talent inbox (`GET /api/talent/me/broadcasts`) and SSE stream (`/api/talent/me/broadcasts/stream`).
- `eois` — expressions of interest. `POST/GET/POST /eoi[/{id}/accept][/{id}/withdraw]`. Indexed on `id` and `talent_id`.
- `newsletter_signups` — waitlist emails from skill landing pages.
- `referrals` — `{referrer_id, referred_id, code, status, bonus_hours}`.

**Contracts**
- `engagements` — the contract layer. `{id, employer_id, employer_name, talent_id, talent_name, hours_allocated, hours_used, hourly_rate, scope, mode, employer_signature, talent_signature, status}`. `id` unique-indexed.
- `deliverables` — talent submissions against an engagement. `{id, engagement_id, talent_id, title, link, description, hours_claimed, status, revision_count, latest_revision_id, dispute_grievance_id, …}`. Queried on `engagement_id` (unindexed).
- `reviews` — post-engagement reviews with `status="pending"` gating.
- `payouts` — commission-calculated payout row per approved deliverable. Written at deliverable-approve time.
- `payout_runs` — aggregate of payouts generated by an admin run.

**Payments**
- `payment_transactions` — `{id, session_id, user_id, amount_cents, kind, payment_status, package_id, hours, project_id, milestone_id, invoice_id, created_at}`. `session_id` is unique-indexed. `kind` field discriminates hours-package vs milestone; dispute fees don't use this collection.
- `payment_reminders` — audit trail of overdue-invoice email + auto-charge attempts.

**Projects**
- `project_leads` — scoping requests before conversion.
- `projects` — active engagement + phases + RACI + budget rollup.
- `project_milestones` — `{project_id, name, amount, percent, due_date, status, invoiced_at, paid_at}`.
- `project_invoices` — invoice metadata + ref.
- `project_variances`, `project_risks`, `project_alerts` — the workspace tabs.
- `custom_project_templates` — templates promoted from successful projects.

**Revisions / disputes / refunds**
- `revision_requests` — one per employer revision request. `{deliverable_id, employer_id, talent_id, revision_number, priority, justification, status, resubmitted_at, ...}`. Referenced from `deliverables.latest_revision_id`.
- `grievances` — polymorphic: `kind` is either unset (general grievance) or `"revision_dispute"`. Disputes carry `dispute_fee: {amount_usd, payment_status, owed_by_id, session_id, payment_intent_id, refund_id, ...}`.
- `dispute_fee_transactions` — Stripe checkout / paid / refunded state per fee payment attempt.
- `refund_audit_receipts` — signature + row-count receipt written when the admin refund audit PDF is generated.
- `notifications` — inbox rows created on dispute ruling and refund actions.

**Verification**
- `reference_checks` — one per emailed referee. `{token, talent_id, ref_email, response, status, answered_at}`. Referenced from `users.profile.references`.
- `drill_receipts` — signature receipt from public trust drill PDFs (`auth.py::public_trust_timeseries_pdf`).

**Integrations**
- `crm_integrations` — per-employer bearer token for HubSpot/Salesforce/Slack/SharePoint. **Plain-text token storage — S-06.**
- `crm_sync_log` — per-talent push/skip/fail log.
- `integration_tokens` — API tokens for work providers (Monday/Asana/Trello/…). **Plain-text — S-06.**
- `work_items` — unified work log across providers + Excel/MSP uploads. `user_id` is indexed.
- `connected_accounts` — portfolio + payout providers (LinkedIn/GitHub/Stripe Connect/Payoneer/Wise/Plaid).
- `files` — file upload metadata for avatars, portfolio images, deliverable attachments.

**Rate nudges + scheduler**
- `rate_nudges` — one row per talent flagged as drifted; upserted by scan. Displayed on talent dashboard.
- `job_runs` — audit trail of every APScheduler job execution. Read by `/admin/scheduler`.

### Relationships (in text)
```
users.id ─┬─◀ engagements.employer_id, engagements.talent_id
          ├─◀ deliverables.talent_id
          ├─◀ payouts.talent_id
          ├─◀ reviews.reviewer_id / reviewee_id
          ├─◀ referrals.referrer_id / referred_id
          ├─◀ grievances.talent_id / employer_id / ruled_by_id
          ├─◀ shortlists.employer_id / talent_id
          ├─◀ broadcasts.talent_id
          ├─◀ eois.talent_id / employer_id
          ├─◀ payment_transactions.user_id
          ├─◀ projects.employer_id, project_leads.employer_id
          ├─◀ work_items.user_id, integration_tokens.user_id, crm_integrations.user_id
          ├─◀ reference_checks.talent_id
          ├─◀ notifications.user_id
          └─◀ audit_log.actor_id / subject_id

engagements.id ─┬─◀ deliverables.engagement_id
                ├─◀ reviews.engagement_id
                ├─◀ eois.engagement_id (nullable, filled on accept)
                └─◀ grievances.engagement_id

deliverables.id ─┬─◀ revision_requests.deliverable_id
                 └─◀ grievances.deliverable_id

projects.id ─┬─◀ project_milestones.project_id
             ├─◀ project_invoices.project_id
             ├─◀ project_variances.project_id
             ├─◀ project_risks.project_id
             └─◀ project_alerts.project_id

project_milestones.id ─◀ project_invoices.milestone_id, payment_transactions.milestone_id
grievances.id          ─◀ dispute_fee_transactions.grievance_id
```

No cascading deletes anywhere. "Deletes" are almost always status transitions.

---

## 5. Money flow

Three Stripe Checkout kinds — hours purchase, project milestone, dispute arbitration fee — plus admin-triggered refunds and the signed audit PDF. All Checkout calls hit the synchronous Stripe SDK from inside `async def` handlers; see §9.

### 5.1 Hours package purchase

- **Amount origin**: the `PACKAGES` dict near the top of `server.py`. Hardcoded USD amounts per pack (`starter_10`, `growth_50`, `scale_100`, `enterprise_500`).
- **Session create**: `POST /api/payments/checkout` in `server.py`. Calls `stripe.checkout.Session.create(mode="payment", ...)` with metadata `{user_id, package_id, hours}`. **No `kind` field** — hours purchases are the default branch in the webhook.
- **Redirect URLs**: success `{origin}/payment/success?session_id={CHECKOUT_SESSION_ID}`, cancel `{origin}/payment/cancel`.
- **DB write on create**: insert `payment_transactions` with `status="initiated"`, `payment_status="pending"`.
- **Webhook**: `POST /api/stripe/webhook` (`stripe_webhook` in `server.py`).
  - `stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)` — signature failure → 400.
  - On `checkout.session.completed`, reads `event.data.object.metadata`.
  - `kind == "dispute_fee"` → dispute branch (see 5.3).
  - `kind == "milestone"` → milestone branch (see 5.2).
  - Default branch: `db.payment_transactions.update_one({"session_id": sid, "payment_status": {"$ne": "paid"}}, {"$set": {"payment_status": "paid", ...}})` then `db.users.update_one({"id": user_id}, {"$inc": {"hours_balance": hours}})`. **This is S-03(c)**: the `$inc` runs unconditionally after the update — it is not gated on the update-matched-a-row result — so two concurrent webhook deliveries can both pass the Python `payment_status != "paid"` check and both $inc. See CLAUDE.md landmine list.
- **Idempotency**: the `$ne: "paid"` guard prevents double-crediting *of the same session* only when the update actually matched. There is no `event.id` dedup table (S-03(b)).
- **Frontend poll**: `PaymentSuccess.jsx` polls `GET /api/payments/status/{sid}` every 2s up to 12 times. That endpoint calls `_credit_hours_if_paid` in `server.py`, which uses `find_one_and_update` and only `$inc`s if the update returned a document — this branch is atomically correct, unlike the webhook branch above. Two parallel credit paths, one correct and one racy.

### 5.2 Project milestone payment

- **Amount origin**: `project_milestones.amount` (float USD), stored when the admin issues the invoice via `POST /api/projects/workspace/{id}/milestones/{mid}/invoice`.
- **Session create**: `POST /api/projects/workspace/{id}/milestones/{mid}/checkout` (`create_milestone_checkout` in `projects.py`). Calls `stripe.checkout.Session.create(...)` with metadata `{kind: "milestone", project_id, milestone_id, invoice_id, user_id}`.
- **Redirect**: success `{origin}/projects/{project_id}/workspace?paid={CHECKOUT_SESSION_ID}`, cancel `?cancel=1`.
- **DB write on create**: `payment_transactions` row with `kind="milestone"`.
- **Webhook branch** (in `stripe_webhook`): updates `payment_transactions.payment_status`, `project_milestones.status="paid"` + `paid_at`, `project_invoices.status="paid"` + `paid_at`. All three under the same `$ne: "paid"` guard.
- **Frontend poll**: `ProjectWorkspace.jsx` calls `GET /api/projects/milestone-payment/status/{sid}` on the `?paid=` redirect and refreshes the workspace.

### 5.3 Dispute arbitration fee

- **Amount origin**: `settings.business_rules.revision_dispute_fee_usd` (default $49; see `config.py::BusinessRules`), used when a talent opens the dispute and on the fee-payment path in `revisions.py`.
- **Session create**: `POST /api/grievances/{gid}/pay-fee` (`pay_dispute_fee` in `revisions.py`). Uses a local `_stripe` alias (the same SDK) with metadata `{kind: "dispute_fee", grievance_id}`. Idempotent — if a valid session already exists for the grievance it's reused rather than recreated.
- **DB write on create**: upserts `dispute_fee_transactions` row and stamps `grievances.dispute_fee.stripe_session_id`.
- **Webhook branch** (`kind == "dispute_fee"` in `stripe_webhook`): awaits `mark_dispute_fee_paid(session_id)` from `revisions.py::mark_dispute_fee_paid`, which:
  - Reads `dispute_fee_transactions` by session_id; early-returns if already paid.
  - Fetches the Stripe session to pull `payment_intent` for future refund.
  - Updates `dispute_fee_transactions` and `grievances.dispute_fee` to `payment_status="paid"`.
- **Silent-failure — S-03(a) partial**: the webhook's try/except around `mark_dispute_fee_paid` now `logger.exception(...)`s the failure (was a bare `pass`) but *still returns `{"ok": True}` to Stripe*. If Mongo is briefly unavailable, Stripe records the event as delivered but the fee is never marked paid, and no retry queue exists. The observability is better; the money-loss vector is unchanged.

### 5.4 Refund path

- **Endpoint**: `POST /api/admin/grievances/{gid}/refund-fee` (`admin_refund_fee` in `revisions.py`), requires `has_admin_scope(user, "moderation")`.
- **Fetch payment_intent**: if not cached on the grievance, `_stripe.checkout.Session.retrieve(session_id)` pulls `payment_intent`.
- **Stripe call**: `_stripe.Refund.create(payment_intent=pi_id, reason="requested_by_customer", metadata={...})`. No `await` — sync SDK call blocks the loop.
- **DB writes**:
  - `grievances`: `dispute_fee.payment_status="refunded"`, `refund_id`, `refunded_at`, `refunded_by_id`, `refund_reason`.
  - `dispute_fee_transactions`: same shape.
- **Notifications**: email via `send_email` and `notifications` row of type `dispute_fee_refunded`.

### 5.5 Signed audit PDF

- **Endpoint**: `GET /api/admin/revisions/refund-audit/pdf?days=N` (`admin_refund_audit_pdf` in `revisions.py`), `scope=moderation`.
- **Signature function** (`_refund_audit_signature` in `revisions.py`):
  ```python
  def _refund_audit_signature(rows, period_start, period_end):
      salt = settings.crypto.refund_audit_secret.encode()   # required at boot, S-04 partial
      canonical = json.dumps({...}, sort_keys=True, separators=(",", ":")).encode()
      return hashlib.sha256(salt + canonical).hexdigest()
  ```
  - This is **not HMAC**. `sha256(salt + msg)` is vulnerable to length-extension. Post-F-11 the fallback chain and the hardcoded `"jobatlas-refund-v1"` default are gone — the secret is now required at boot — but the primitive itself is still the length-extendable `sha256(secret + msg)`, and the verify endpoint below does a lookup instead of a recompute. Full S-04 fix requires switching to `hmac.new(secret, canonical, sha256)` and having the verify endpoint recompute + `hmac.compare_digest`.
- **Receipt**: a row lands in `refund_audit_receipts` with the signature and issuer metadata.
- **Verify endpoint**: `GET /api/admin/revisions/refund-audit/verify/{sig}` (`admin_refund_audit_verify`) is a simple lookup — it does *not* recompute the hash to detect tampering; it only confirms a receipt with that signature was issued.

---

## 6. Business rule engine

Every threshold is a typed field in `backend/config.py:BusinessRules`. Defaults
match FEATURES.md §12 verbatim. **This section deliberately does NOT list env
var names** — that would recreate the F-09 drift condition (docs naming
variables the code doesn't read). The env var → typed field mapping lives in
`.env.example` (grouped by service, one comment per variable) and
`docs/CONFIG_INVENTORY.md` (per-var provenance). Rename a field in config.py
and the alias, the doc, and this table all update from a single source. If a
name in this table diverges from a field in `BusinessRules`, that's the bug —
fix the doc, not the code.

Enforcement lives in `routes/revisions.py`; the reversal ("recovery") lives in
the deliverable-approve flow in `server.py`. All settings referenced below live
under `settings.business_rules.<field>` (see `backend/config.py:BusinessRules`).

| Rule | Config field | Default | Enforced at | Reversed at |
| --- | --- | --- | --- | --- |
| Revision counter | — | — | `revisions.py::request_revision` increments `deliverables.revision_count` | Never decremented; only cleared on dispute ruling for talent |
| Amber flag `under_review` | `revision_review_threshold` | 3 | `revisions.py::request_revision` when count reaches threshold | consecutive clean approvals — `revision_recovery_under_review` default 3 |
| Red flag `excessive_revisions` | `revision_penalty_threshold` | 5 | `revisions.py::request_revision` when count reaches threshold | consecutive clean approvals — `revision_recovery_excessive` default 5; also cleared on dispute ruling in talent's favour (`revisions.py::admin_rule_dispute`) |
| Visibility deduction | `revision_visibility_penalty` | 20 | Subtracted from `profile.visibility_score` (default 100) when `excessive_revisions` fires | Restored to 100 on recovery or talent-favourable ruling |
| Rate bias | `revision_rate_nudge_penalty` | 10 | `profile.rate_bias_pct = -10` when `excessive_revisions` fires | Reset to 0 on recovery or talent ruling |
| "Proven Reliable" badge window | `proven_reliable_days` | 90 | Checked against `profile.recovery_cleared_at` in badge computation | Expires 90 days after last recovery |
| Employer abuse flag | `employer_flag_unique_talents` × `employer_flag_window_days` | 3 talents × 60 days | Scan runs at revision-request time when the current talent hits the penalty threshold; queries `revision_requests` in the rolling window (`revisions.py::_maybe_flag_employer`) | Manual admin action; no automatic timeout |
| Dispute right | `revision_penalty_threshold` | 5 | `POST /api/deliverables/{id}/dispute` at `revisions.py::raise_dispute` requires `revision_count >= 5` | Not applicable — dispute is a one-way transition |
| Dispute fee | `revision_dispute_fee_usd` | 49 | Loser owes; set at ruling (`revisions.py::admin_rule_dispute`) | Admin refund |
| Refund rate alert | `refund_alert_threshold_pct` | 20 | 30-day rolling refund rate computed in `/admin/revisions/refund-analytics` (`revisions.py::admin_refund_analytics`); comparison logic within the endpoint | — |
| Rate drift threshold | `rate_drift_threshold_pct` | 15 | Compared to `\|drift_pct\|` in `_scan_and_record_rate_nudges` (`server.py`); a nudge row is upserted when exceeded | Nudge cleared when talent updates rate |

### Trusted Partner + Verified badges

Computed at `GET /api/talent` (in `server.py`) per talent:
- `is_verified` = `verification_status == "verified"`.
- `is_trusted_partner` = compound rule; check the talent-card computation in the `/api/talent` handler. Usually a mix of completed_engagements + avg_rating + verified.
- `is_proven_reliable` = `now() - profile.recovery_cleared_at < settings.business_rules.proven_reliable_days` (default 90).
- `excessive_revisions` — echoed from `profile.excessive_revisions`.

### Recovery playbook

Deliverable approval (in `server.py`, the `POST /deliverables/{deliverable_id}/approve` handler) invokes `_record_clean_approval` / `_reset_clean_streak` from `routes.revisions` via late imports. Approving with `revision_count == 0` on the deliverable increments `profile.clean_streak`; a reject or revision resets it to 0. When the streak crosses `settings.business_rules.revision_recovery_under_review`, amber lifts; when it crosses `settings.business_rules.revision_recovery_excessive`, red lifts, `visibility_score` restores to 100, `rate_bias_pct` resets to 0, and `recovery_cleared_at` is stamped (drives the 90-day badge).

---

## 7. External integrations

| Service | Env | Data leaving system | Code path | Failure handling | Sync/async |
| --- | --- | --- | --- | --- | --- |
| **Stripe API** | `STRIPE_SECRET_KEY` (S-05 closed — no fallback; required at boot) | Customer id, session metadata (user_id, package_id, project_id, milestone_id, invoice_id, grievance_id), payment method | Sync `stripe.*` calls in `server.py` (3 sites — `POST /payments/checkout`, `GET /payments/status/{id}`, webhook), `routes/projects.py` (~10 sites across milestone checkout, SetupIntent card-on-file, off-session PaymentIntent), `routes/revisions.py` (~5 sites across pay-fee, refund) | Raises `stripe.error.StripeError` up to handler; most handlers do not catch it, so it becomes 500. Webhook handler catches inside dispute branch (`logger.exception`) but still returns 200 to Stripe. | **Sync SDK inside async handlers** — blocks event loop |
| **Stripe Webhook** | `STRIPE_WEBHOOK_SECRET` | Nothing outbound | `server.py::stripe_webhook` | Signature failure → 400 | Sync `construct_event` inside async handler |
| **Resend (email)** | `RESEND_API_KEY` | Recipient email, subject, HTML body (verification tokens, dispute rulings, refund notices, rate nudges, invoice reminders) | `mailer.py::send_email` | `_resend is None` short-circuits and returns `{"sent": False, ...}`. Every caller ignores the return value. | Wrapped in `asyncio.to_thread` — non-blocking |
| **Slack incoming webhook** | `SLACK_WEBHOOK_URL` | Variance-breach text, invoice-overdue mirroring | `projects.py::_slack_notify` | No URL → early return. Exceptions logged, swallowed. | `asyncio.to_thread` — non-blocking |
| **Cloudflare Turnstile** | `TURNSTILE_SECRET_KEY` | Token from browser, remote IP | `auth.py::_verify_turnstile` | **Post-F-11**: config refuses to boot when `ENV=production` and the key is unset. In dev/test, unset key logs `[S-08] TURNSTILE_SECRET_KEY unset (env=<...>) — captcha check BYPASSED` and returns True. Exception in the HTTP call → returns False. Uses `urllib.request` synchronously. | Sync `urllib` inside async — blocks briefly |
| **Anthropic via `emergentintegrations`** | `EMERGENT_LLM_KEY` | Talent's `skills` list, `years_experience`, `location` (raw f-string interpolation — S-10 prompt-injection risk) | `ai_service.py::suggest_hourly_rate`, model `claude-sonnet-4-5-20250929` | Missing key → rule-based fallback (`{low: max(15, base-15), mid: base, high: base+25}`). Exception → same fallback. | `await chat.send_message(...)` — awaited; assumed non-blocking |
| **HubSpot** | Per-employer bearer | Talent name, email, rate on push-lead | `auth.py::_validate_crm_token`, `auth.py::push_lead_to_crm` | Try/except with 400 on validation failure; log entry in `crm_sync_log` | Sync `urllib` inside async |
| **Salesforce** | Per-employer bearer + instance URL | Same as HubSpot; sends as Lead | Same file | Same | Same |
| **Slack (CRM)** | Per-employer bot token | `auth.test` call to validate; no lead push | Same | Same | Same |
| **SharePoint** | Per-employer bearer | `me` call to validate | Same | Same | Same |
| **Monday/Asana/Trello/ClickUp/Jira/Confluence** | Per-user API tokens | GraphQL / REST queries | `work_integrations.py::_fetch_*` — six sync `requests.get/post` sites at `work_integrations.py:77,89,101,108,117,134` | On failure returns stub sample so UI keeps rendering | **Sync `requests` inside async** — blocks 15s max |
| **Object storage** | `STORAGE_TOKEN` + `INTEGRATION_PROXY_URL` (S-15 + S-27 closed — no more `EMERGENT_LLM_KEY` reuse, no fallback URL) | Avatars, portfolio images, deliverable attachments | `storage_client.py::init_storage / put_object / get_object` — five sync `requests` sites | Missing token or URL → boot fails at config load. `init_storage()` runs in startup try/except; upload endpoints 500 if it fails | Sync `requests`, blocks the loop during uploads |
| **BGV (background verification)** | — | No third-party vendor is called. Reference emails go via Resend only. | `auth.py::submit_bgv` + reference-check flow | Auto-approval based on reference responses; if a real BGV vendor was ever intended, none is wired | N/A |

---

## 8. Background jobs

Three cron jobs under a single `AsyncIOScheduler(timezone="UTC")` created inside the `@app.on_event("startup")` handler in `server.py`, started after all three jobs are added. All `misfire_grace_time=3600`, `replace_existing=True`. Every run inserts a `job_runs` doc so `/admin/scheduler` can display the last run.

1. **`monthly_rate_nudge_scan`** — 1st of month, 09:00 UTC. Wrapper is a nested `async def` inside the startup handler; body is `server.py::_scan_and_record_rate_nudges`. Iterates all `role=talent` users with non-empty skills, calls `suggest_hourly_rate`, upserts `rate_nudges` if |drift| > `RATE_DRIFT_THRESHOLD_PCT` (default 15). Sends an email via Resend (silent if unset).
2. **`daily_overdue_invoice_scan`** — 08:00 UTC. Wrapper late-imports `scan_overdue_invoices` from `routes.projects`. For each unpaid invoice: send a reminder email every 3 days; after 7 days overdue, attempt off-session `PaymentIntent.create(off_session=True, confirm=True)` if the employer has a `stripe_payment_method_id`. Mirrors to Slack.
3. **`nightly_crm_sync`** — 02:00 UTC. Wrapper late-imports `_sync_shortlists_to_crm(trigger="cron")` from `routes.auth`. For each employer with a `crm_integrations` row, push new shortlist rows to HubSpot/Salesforce since `last_sync_at`, deduping via `crm_sync_log`.

### Multi-instance safety

**None.** APScheduler runs entirely in-process with a memory-backed job store. If you scale to two uvicorn workers or two containers, all three jobs fire in every instance — rate nudges get scanned N times, invoice reminders get emailed N times, CRM pushes get duplicated. There is no distributed lock, no jobstore backed by Mongo (would need `MongoDBJobStore`), no leader election. Deployment must pin this app to a single instance or move the scheduler out. Tracked as S-21.

---

## 9. Async correctness (blocking I/O inside `async def`)

The FastAPI event loop is a single asyncio loop per worker. Every synchronous network call inside an `async def` handler stalls that loop for every other request. This codebase has a lot of them — tracked as S-13. High-impact groupings:

- **Stripe SDK (sync)** — every `stripe.*` call site in `server.py`, `routes/projects.py`, and `routes/revisions.py`. Under normal Stripe latency (100-500ms) this is tolerable at low RPS; under an outage each call locks the worker for the full timeout.
- **`urllib.request` in Turnstile + CRM validation** — `auth.py::_verify_turnstile`, `_validate_crm_token`, and `push_lead_to_crm`. Synchronous, no explicit timeout on some paths.
- **`requests` in work-integrations adapters** — six sites in `work_integrations.py` (`work_integrations.py:77,89,101,108,117,134`), 15s timeout each; called from `server.py`'s `connect_integration` / `sync_integration` handlers inside `async def` without any `to_thread` wrapper.
- **`requests` in `storage_client.py`** — five sites across init, put, get (and their 404 retry paths); also called from async without offloading. Big files stall the loop.
- **ReportLab PDF generation** inside async handlers: `auth.py::_render_drill_pdf` (called from `public_trust_timeseries_pdf`), `revisions.py::_render_refund_audit_pdf` (called from `admin_refund_audit_pdf`), `projects.py::_render_invoice_pdf` (called from `download_invoice_pdf`). All sync; large PDFs will freeze the worker.

Two things *are* offloaded correctly:
- **Resend email** — `mailer.py::send_email` wraps its blocking SDK call in `asyncio.to_thread`.
- **Slack webhook** — `projects.py::_slack_notify` uses `asyncio.to_thread`.

Everything else is a latent starvation bug. The right fix is either `httpx.AsyncClient` for HTTP, or blanket `await asyncio.to_thread(...)` around the sync calls.

There are no `time.sleep` calls in the async paths that I found.

---

## 10. Frontend ↔ backend contract

- **Axios instance**: `frontend/src/lib/api.js`.
  ```js
  const BASE = process.env.REACT_APP_BACKEND_URL;
  const api = axios.create({ baseURL: `${BASE}/api`, withCredentials: true });
  ```
  Env var reads live only in `frontend/src/config.js` (F-11 close — same rule as backend/config.py); the SPA refuses to mount with a visible red banner when `REACT_APP_BACKEND_URL` is unset (F-08 close). No more silent `undefined/api` requests.
- **Cookies**: `withCredentials: true` sends the httpOnly `access_token` cookie on every request. CORS on the backend must echo the exact origin (not `*`) with `Allow-Credentials: true` — see §1.
- **Error formatting**: `formatErr(e)` in `frontend/src/lib/api.js` unwraps `e.response.data.detail`. It handles Pydantic's array-of-errors shape and stringifies otherwise. There is **no global response interceptor** — 401/403 are not automatically redirected to login; each page decides whether to catch or ignore (S-16).
- **Auth context**: `frontend/src/context/AuthContext.jsx`. On mount, `api.get("/auth/me")` — `null` = loading, `false` = guest, object = logged in. `logout()` posts `/auth/logout` then sets `user=false`. `refresh()` re-fetches `/auth/me`.
- **Protected routes**: `frontend/src/components/ProtectedRoute.jsx`. Redirects to `/login` for guests, to `/` if role doesn't match (admin bypasses all role checks — an admin sees talent + employer pages fine).
- **Toasts**: `sonner`, mounted in `frontend/src/App.js`. Individual pages call `toast.success/error(formatErr(e))`.

### Frontend calls with no backend
Nothing found. All axios calls in `frontend/src/pages/*` resolve to an existing handler.

### Backend endpoints with no frontend caller
- `POST /api/trust/verify-drill` — only the GET-signature form is used by the QR path.
- `GET /api/admin/reference-checks/{talent_id}` — the Verifications tab uses `/admin/verifications-with-refs` instead.
- `POST /api/admin/rate-nudges/scan` and `GET /api/admin/scheduler` — no UI button, curl-only.
- `POST /api/admin/invoices/scan-overdue` — no UI button.
- `POST /api/admin/projects/{id}/save-as-template` — no UI button in `ProjectWorkspace.jsx`.
- `GET /api/pricing/tiers` — `/api/pricing` already includes the tiers, so the frontend uses the aggregate.
- `POST /api/pricing/quote` — `PurchaseHours.jsx` computes bundle math client-side.

### Environment coupling in the SPA
- `REACT_APP_BACKEND_URL` — required. Enforced at mount (F-08 close).
- `REACT_APP_TURNSTILE_SITE_KEY` — used by `Register.jsx`; defaults to Cloudflare's `1x00000000000000000000AA` test key when unset. Frontend loads the widget script from Cloudflare's CDN with a 6-second timeout; if the CDN load fails, the submit button re-enables without a token. In dev/test the backend accepts empty tokens with a WARN log; in production the backend refuses to boot without `TURNSTILE_SECRET_KEY`, so this path is unreachable there.

---

## Appendix: surprising things

Written down so the next engineer doesn't have to re-derive them.

1. **`engagements.py` (40 lines) is dead code.** All engagement endpoints live in `server.py`. Don't add code to `routes/engagements.py` expecting it to be wired.
2. **Two admin endpoints escape the scope system.** `POST /admin/rate-nudges/scan` and `GET /admin/scheduler` at `admin.py:186-211` check `user.get("role") != "admin"` directly. Any admin — even one with `admin_permissions=[]` — passes. Tracked as S-09.
3. **`_refund_audit_signature` is `sha256(salt + msg)`, not HMAC.** Post-F-11 the fallback chain and hardcoded `"jobatlas-refund-v1"` default are gone (secret is required at boot), but the length-extendable primitive and the verify-endpoint's lookup-instead-of-recompute behaviour are unchanged. S-04 partial.
4. **The Stripe dispute-fee webhook still swallows the failure and returns 200.** The `try/except` around `mark_dispute_fee_paid` in `stripe_webhook` now `logger.exception`s the failure (was a bare `pass`) but still tells Stripe everything is fine. Money loss is now observable in logs; the retry queue is still missing.
5. **No JWT revocation. No `token_version` field.** Logout clears cookies with attribute-matched flags post-S-31, but a stolen access token remains valid for its 12h expiry. S-07 open.
6. **Cookies are `SameSite=None`, and no CSRF middleware is registered yet.** `security/csrf_exempt.yml` is scaffolding for S-01; the middleware itself hasn't landed. Every mutation is CSRF-exposed today.
7. **Only 7 collections are indexed.** Everything else collscans. Fine at demo scale, not at real scale. S-12.
8. **`emergentintegrations` is a confirmed fresh-install blocker.** `pip install -r backend/requirements.txt` fails on any clean checkout. The test image installs a two-class shim; anyone running the backend outside that image must reproduce it. F-01.
9. **`storage_client.py` used to reuse `EMERGENT_LLM_KEY` as its auth token; F-11 split this into `STORAGE_TOKEN`.** No more shared secret across LLM and storage. S-15 CLOSED.
10. **The default admin email is `admin@talenthub.io`**, from an earlier product name; the rest of the codebase brands as Geminista / `geminista.com`. Don't be surprised when the seed row doesn't match the outward-facing brand. S-20 remainder.
11. **CORS `"*"` cannot be configured any more.** F-11 removed the fallback; the field validator on `settings.urls.cors_origins` refuses `"*"` as an entry, and `CORS_ORIGINS` is required at boot. S-02 partial (default removed; per-env origin validation still open).
12. **APScheduler is in-process with a memory jobstore.** Do not run multiple workers/replicas without moving the scheduler out — you'll get N-fold duplicate emails and CRM pushes. S-21.
13. **The rate-nudge scanner and manual `POST /profile/suggest-rate` interpolate talent-controlled `skills` and `location` straight into the LLM prompt** in `ai_service.py::suggest_hourly_rate`. Prompt injection lets talent inflate their own rate. S-10.
14. **`_scheduler = None` is a module-level default in `server.py`** placed after the startup handler that assigns it — both statements are module-level, so the `None` runs first at import time and the startup handler overwrites it on boot. This is what makes the shutdown handler safe when startup didn't complete. Confusing but not a bug.
15. **Late imports of `logger` inside `projects.py` handlers** are redundant — `logger` is already imported at module top via `deps`. Harmless.
16. **The `Authorization: Bearer` branch in `deps.py::get_current_user` still exists** even though no first-party client sends one (`grep -rn "Authorization" frontend/src/` returns nothing). S-26 — scheduled to be removed before S-01 lands.
