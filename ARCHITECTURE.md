# ARCHITECTURE.md — Job Atlas backend, ground truth

Written for the engineer who cloned this today and needs to ship a change tomorrow. Every claim points at a file and line. Where the code does something surprising or contradictory, that is called out plainly.

The stack is a single FastAPI process (Motor + APScheduler in-process), one MongoDB database, a React 18 SPA on `craco`, and Stripe for money. Everything runs from `backend/server.py` — routes are split into `backend/routes/*.py` but share the same APIRouter instance from `backend/deps.py:37`.

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
│  │  - CORSMiddleware     │◄──┤ backend/deps.py:37                   │ │
│  │  server.py:2886       │   │                                      │ │
│  └───────────────────────┘   │  routes/auth.py       (21 endpoints) │ │
│                              │  routes/admin.py      (~30 endpoints)│ │
│                              │  routes/marketplace.py (~5 endpoints)│ │
│                              │  routes/projects.py   (~40 endpoints)│ │
│                              │  routes/revisions.py  (~15 endpoints)│ │
│                              │  routes/engagements.py (unused shell)│ │
│                              │  + inline server.py routes           │ │
│                              └────┬────────────┬────────────────────┘ │
│                                   │            │                      │
│  ┌─────────────────┐  ┌───────────▼──────┐  ┌──▼───────────┐          │
│  │ APScheduler     │  │  Motor client    │  │  Stripe SDK  │          │
│  │  3 cron jobs    │  │  deps.py:33-34   │  │  (sync)      │          │
│  │  server.py:2794 │  │                  │  │  server.py:40│          │
│  └────────┬────────┘  └─────────┬────────┘  └──────┬───────┘          │
└───────────┼─────────────────────┼──────────────────┼──────────────────┘
            │                     │                  │
      wakes │              queries│                  │ REST
            │                     ▼                  ▼
            │            ┌────────────────┐  ┌──────────────┐
            └───────────►│  MongoDB       │  │  Stripe API  │
                         │  40+ collections│  │  Checkout    │
                         │  5 indexes total│  │  Refund      │
                         │                 │  │  Webhook     │
                         └────────────────┘  └──────┬───────┘
                                                    │ POST /api/stripe/webhook
                                                    └───────► back into FastAPI
    Optional external calls (silent-fail if unset):
      Resend (mailer.py)      RESEND_API_KEY
      Slack webhook           SLACK_WEBHOOK_URL       (projects.py:1117)
      Cloudflare Turnstile    TURNSTILE_SECRET_KEY    (auth.py:60)
      Anthropic via
        emergentintegrations  EMERGENT_LLM_KEY        (ai_service.py:10)
      HubSpot / Salesforce /
        Slack / SharePoint    per-employer bearer tokens
      Monday / Asana / Trello
        / Jira / ClickUp      per-user API tokens
```

Key non-obvious facts up front:
- `emergentintegrations` (imported at `ai_service.py:6`) is not on PyPI. `requirements.txt` does not pin it. If the sandbox image doesn't provide it out-of-band, the module import fails and `routes/auth.py` blows up on import (it imports `suggest_hourly_rate` at `routes/auth.py:47`).
- Every write in the system uses `str(uuid.uuid4())` as the app-level primary key (via `new_id()` in `deps.py:59`); Mongo's `_id: ObjectId` is treated as noise and stripped from reads with `{"_id": 0}`.
- Only five collections have indexes (`server.py:2749-2755`). Everything else — `deliverables`, `payouts`, `reviews`, `revision_requests`, `grievances`, `projects`, `project_milestones`, `broadcasts`, `notifications`, etc. — is queried on unindexed fields.
- Auth cookies are `SameSite=None; Secure; HttpOnly` (`deps.py:94-95`) with no CSRF token anywhere. Every state-mutating POST is CSRF-exposed by design.

---

## 1. Boot sequence

Command: `uvicorn server:app` (no factory; the module-level `app` at `server.py:42` is imported directly).

Order of events, in the order Python executes them:

1. **`server.py:1-5`** — `load_dotenv(ROOT_DIR / ".env")` reads env vars *before any other imports*. The identical dotenv call runs again inside `deps.py:6-10` — harmless idempotent double-load, but worth knowing when you're debugging why an env var appears set only sometimes.
2. **`server.py:17`** — `import stripe`. The Stripe SDK loads but does not connect.
3. **`server.py:25-27`** — three local imports fire, in order:
   - `from ai_service import suggest_hourly_rate` (`ai_service.py:6` transitively imports `emergentintegrations.llm.chat`). If the package is missing, boot dies here with `ModuleNotFoundError`.
   - `from work_integrations import ...` — pulls the requests-based sync adapters.
   - `from storage_client import init_storage, put_object, get_object, APP_NAME as STORAGE_APP` — loads without contacting the storage service.
4. **`server.py:30-37`** — `from deps import (...)`. This is the moment the app becomes reachable to Mongo.
   - `deps.py:26-28` reads three env vars via `os.environ[...]` (no default). `MONGO_URL`, `DB_NAME`, `JWT_SECRET`. Missing any of these → `KeyError` at import → uvicorn worker never becomes ready. There is no friendly error message.
   - `deps.py:30` reads `STRIPE_WEBHOOK_SECRET` with a `""` default (optional at boot, but any webhook attempt will then fail signature verification).
   - `deps.py:33-34` constructs `AsyncIOMotorClient(MONGO_URL)` and selects `client[DB_NAME]`. Motor connects lazily on first query; a bad URL survives import and surfaces as 500s later.
   - `deps.py:37` creates the shared `api = APIRouter(prefix="/api")`.
5. **`server.py:40`** — `stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"`. The fallback string is not a valid Stripe key; any `stripe.*` call will 401 from Stripe.
6. **`server.py:42`** — `app = FastAPI(title="Job Atlas API")`.
7. **`server.py:223-227`** — the five route modules import in order: `routes.auth`, `routes.admin`, `routes.marketplace`, `routes.projects`, `routes.revisions`. Each `from deps import api, ...` at the top, then decorates handlers with `@api.post(...)` / `@api.get(...)`. Because they mutate the same shared router object, order does not matter for routing but does matter for anything that depends on module-import side effects (there are none — the modules only register handlers). `routes/__init__.py` is a 6-line placeholder; it does not do package-level wiring.
8. **`server.py:2740-2867`** — the `@app.on_event("startup")` handler runs after uvicorn reports "Application startup complete":
   - Optional `init_storage()` call, wrapped in try/except (non-fatal).
   - Six `db.<col>.create_index(...)` calls at `server.py:2749-2755` for `users.email` (unique), `users.id` (unique), `engagements.id` (unique), `payment_transactions.session_id` (unique), `work_items.user_id`, `eois.id` (unique), `eois.talent_id`. That is the entire set of indexes in the codebase.
   - **Admin seeder** at `server.py:2757-2768`: reads `ADMIN_EMAIL` (default `admin@talenthub.io` — note this is not the branded `geminista.com` used elsewhere) and `ADMIN_PASSWORD` (default `Admin@2026`). If no user with that email exists, inserts one with `admin_permissions: ["superadmin"]`. Idempotent because it checks first.
   - **Legacy industry backfill** at `server.py:2777-2789`: rewrites old `buyer archetype` labels to the new industry taxonomy using `LEGACY_INDUSTRY_MAP` from `deps.py:132-145`. Runs every startup.
   - **APScheduler** at `server.py:2794-2867`:
     - `_scheduler = AsyncIOScheduler(timezone="UTC")` (line 2796).
     - Adds three jobs (all `misfire_grace_time=3600`, `replace_existing=True`):
       - `monthly_rate_nudge_scan` — `CronTrigger(day=1, hour=9, minute=0)`, invokes `_scan_and_record_rate_nudges` (server.py:2801 wraps it late-bound).
       - `daily_overdue_invoice_scan` — `CronTrigger(hour=8, minute=0)`, invokes `scan_overdue_invoices` late-imported from `routes.projects` at line 2824.
       - `nightly_crm_sync` — `CronTrigger(hour=2, minute=0)`, invokes `_sync_shortlists_to_crm(trigger="cron")` late-imported from `routes.auth` at line 2846.
     - `_scheduler.start()` at line 2864. Failure is caught and logged as a warning at line 2867 — the app boots even if scheduling is broken.
9. **`server.py:2884`** — `app.include_router(api)` runs *after* the startup event registration. Because `app.on_event` and `app.include_router` are declarative, order does not matter for FastAPI, but visually the router is mounted at the bottom of the file, not the top.
10. **`server.py:2886-2891`** — `app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])`. The default `"*"` split into `["*"]` is contradictory with `allow_credentials=True` per the CORS spec — browsers refuse credentialed requests to `*` origins. In practice you must set `CORS_ORIGINS` in the env or the SPA cannot authenticate.

### What breaks and where

| Failure | Symptom |
| --- | --- |
| `MONGO_URL` / `DB_NAME` / `JWT_SECRET` unset | Import-time `KeyError` in `deps.py:26-28`; worker never becomes ready. |
| Mongo unreachable at runtime | Import succeeds; first query 500s. |
| `emergentintegrations` missing | Import-time `ModuleNotFoundError` at `ai_service.py:6`, cascades through `routes/auth.py:47`. Whole app dies. |
| `STRIPE_SECRET_KEY` unset | Fallback `"sk_test_emergent"` used; every Stripe call returns 401 from Stripe. |
| `STRIPE_WEBHOOK_SECRET` unset | Webhook signature verification fails at `server.py:562`. |
| `RESEND_API_KEY` unset | `mailer.py:24` sets `_resend = None`; every `send_email` returns `{"sent": False, ...}` silently. |
| `EMERGENT_LLM_KEY` unset | `ai_service.py:15-17` returns the rule-based fallback; scheduler and `/profile/suggest-rate` both work but do not use the LLM. |
| `TURNSTILE_SECRET_KEY` unset | `_verify_turnstile` returns True (`auth.py:64-65`); captcha bypassed. |
| `SLACK_WEBHOOK_URL` unset | `_slack_notify` early-returns silently (`projects.py:1117-1135`). |
| Scheduler start throws | Logged as warning at `server.py:2867`; app continues without cron. |
| `CORS_ORIGINS` unset | Defaults to `"*"` but `allow_credentials=True`; browser blocks the SPA. |
| `APP_BASE_URL` unset | Email templates render relative links (`auth.py:35,300`, `projects.py:365,1259`); recipients click into nothing. |
| `PUBLIC_BASE_URL` unset | Audit-PDF verification URLs render empty (`auth.py:678`, `revisions.py:952`); QR codes point nowhere. |
| `PUBLIC_SITE_URL` unset | SEO sitemap and rate-nudge email origins fall back to request-derived hosts (`marketplace.py:82`, `server.py:1400,1402,1527`); nightly emails may land with wrong hostnames behind a proxy. |
| `INTEGRATION_PROXY_URL` unset | **Data-protection exposure — see SECURITY_BACKLOG.md S-27.** `storage_client.py:6` silently falls through to a hardcoded `https://integrations.emergentagent.com` and every user upload (avatars, portfolio, dispute evidence, government ID from KYB) routes to a third-party host with no warning. Fix: hard-fail at boot when unset. |
| `SENDER_EMAIL` unset | Resend "from" header defaults to `onboarding@resend.dev` (`mailer.py:14`); outbound mail looks like a Resend demo. |

---

## 2. Module map

Every file in `backend/`, one line of "who owns what" plus the import edges.

### `backend/deps.py` (173 lines)
Owns the singletons: `client`, `db`, `api` router, `JWT_SECRET`, admin scope catalog, marketplace constants, `now/new_id/hash_pw/verify_pw/create_token/get_current_user/set_auth_cookies/has_admin_scope`. Zero cross-route imports. Everyone imports from this.

### `backend/server.py` (2892 lines)
The kitchen sink. Owns app bootstrap (line 42), CORS (line 2886), startup + shutdown handlers (2740, 2873), APScheduler (2794), admin seeder (2757), Stripe webhook (`/api/stripe/webhook` at 558), all hours-purchase + payments routes (443-550), file uploads, engagements CRUD, deliverables, reviews, payouts helpers, dashboard metrics, SEO landing pages (972, 1340), employer/talent list endpoints, EOI (2467), broadcasts (1508, 2122, 2147), rate-nudge scanner (`_scan_and_record_rate_nudges` at 1391), curated talent constant `_CURATED_TALENT` (~200 rows around line 1049). Imports `routes.auth`, `routes.admin`, `routes.marketplace`, `routes.projects`, `routes.revisions` at 223-227 (module-level, one-way).

### `backend/routes/__init__.py` (6 lines)
Placeholder. Only exists to make `routes/` a package.

### `backend/routes/auth.py` (1183 lines)
Auth + verification + CRM. Endpoints: register, login, logout, `/auth/me`, `/profile`, `/profile/suggest-rate`, email verification, `/verification/{company,bgv,me}`, public `/reference-check/{token}` (GET+POST), `/trust/{stats,timeseries,timeseries/details,timeseries/details/pdf,verify-drill,verify-drill/{sig}}`, `/admin/reference-checks/{talent_id}`, `/integrations/crm/*` (connect, list, disconnect, push-lead, sync-now, sync-log). ~21 endpoints plus the nightly `_sync_shortlists_to_crm` helper (line 1067). Imports `suggest_hourly_rate` from `ai_service` at line 47.

### `backend/routes/admin.py` (541 lines)
Admin console API. Endpoints: `/admin/me`, users listing + notes + hours-adjust, bank-transfer approve/reject, reviews approve/reject, grievances list + resolve, payouts run + runs + mark-paid, rate-nudge scan trigger, scheduler status, customization GET/PUT + public `/customization/public`, verifications approve/reject, staff CRUD. Imports `_compute_talent_earnings`, `_scan_and_record_rate_nudges`, `_scheduler` from `server` late-bound inside handler bodies (lines 129, 188, 197) — this is deliberate cycle-breaking: `server.py` imports `routes.admin` at module load, so `routes.admin` cannot import `server` at module load without a cycle. Late imports work because they run at request time, after both modules are fully loaded.

### `backend/routes/engagements.py` (40 lines)
**Shell file.** The engagements API actually lives in `server.py` (`POST /api/engagements` at 602, sign/deliverables/approve at 670-681). This file exists as a placeholder for a future refactor and is not registered anywhere useful. Do not add endpoints here without also wiring the router — nothing imports from it.

### `backend/routes/marketplace.py` (196 lines)
Public marketplace metadata. `/marketplace/industries` (line 91), `/marketplace/stats`, sitemap.xml, `/seo/skills`, `/seo/city-skills`, shortlist CRUD (`POST/GET/DELETE /shortlist` at 157/182/190). Imports SEO constants from `deps` at line 23.

### `backend/routes/projects.py` (1440 lines)
Projects + invoicing + auto-collect. Endpoints: `/admin/project-leads` list + convert (134, 217); `/projects/mine`, `/projects/workspace/{id}` load (225, 237); phase advance (287), variance log (405), risk register (474, 499), RACI (525), milestones (548, 585, 615, 780); invoice PDF (752); milestone-payment status polling (866); `/invoices/mine` (903); Stripe SetupIntent flows for card-on-file (`/billing/setup-checkout`, `/billing/setup`, `/billing/status` at 974-1090); overdue invoice daemon `scan_overdue_invoices` (1209) + manual trigger endpoint (1326); template save (1354); admin verification-with-refs (1412). Imports Slack helper `_slack_notify` at 1117; late imports `from deps import logger` inside handler bodies at 398, 894, 1134, 1291 (already imported globally — redundant).

### `backend/routes/revisions.py` (1117 lines)
Revision loop + disputes + refunds + audit PDF. Endpoints: request-revision (134), resubmit (188), list/summary (217, 496), open dispute (235), admin revisions list + rule (291, 312), flagged employers (415), refund analytics (429), recovery status (542), pay dispute fee (586), fee status (668), `mark_dispute_fee_paid` helper (701 — called from the Stripe webhook via server.py:572), admin refund fee (736), refund audit PDF (929), verify-signature (972). The `_refund_audit_signature` at ~856 uses `sha256(secret + msg)` (not HMAC) with hardcoded fallback `jobatlas-refund-v1` when both `REFUND_AUDIT_SIGN_SECRET` and `DRILL_SIGN_SECRET` are missing.

### `backend/ai_service.py` (50 lines)
Only exports `suggest_hourly_rate`. Uses `emergentintegrations.llm.chat.LlmChat` with model `anthropic/claude-sonnet-4-5-20250929` (line 33). Fallback path (line 47-50) returns a deterministic rule-based range when `EMERGENT_LLM_KEY` is missing or the call raises.

### `backend/mailer.py`
Wraps the Resend SDK. `_resend` client is initialised only if `RESEND_API_KEY` is set (`mailer.py:13-24`); otherwise every call returns `{"sent": False, "id": None, "reason": "..."}`. The blocking Resend SDK call is wrapped in `asyncio.to_thread` (line 34), so it does not stall the event loop.

### `backend/storage_client.py`
Talks to an external object store over sync `requests` (lines 20, 29, 34, 45, 48). Used for avatar / portfolio / evidence uploads. `EMERGENT_LLM_KEY` doubles as the auth token here (line 8) — confusingly named.

### `backend/work_integrations.py`
Provider adapters for Monday / Asana / Trello / ClickUp / Jira / Confluence. All use the synchronous `requests` library with a 15s timeout (lines 77, 89, 101, 108, 117, 134). On any failure returns a stub sample so the UI can render (67-71). Called from `server.py:2349` and `:2380` inside `async def` handlers — see §9 for the blocking-I/O implication.

### Cross-module call summary
- `server.py` → `routes.*`: module-level (`server.py:223-227`).
- `routes.admin.py` → `server.py`: late/handler-scoped only (129, 188, 197) — cycle break.
- `server.py` → `routes.projects.scan_overdue_invoices`: late inside scheduler job body at `server.py:2824`.
- `server.py` → `routes.auth._sync_shortlists_to_crm`: late inside scheduler job body at `server.py:2846`.
- `server.py:572` (Stripe webhook) → `routes.revisions.mark_dispute_fee_paid`: called by fully-qualified name; the module was already registered at import so this is fine, but it means the webhook path silently depends on `revisions.py` staying importable.

---

## 3. Request lifecycle (authenticated route)

Walk of `GET /api/talent/me/broadcasts` as a representative authenticated call.

1. **TCP / TLS + HTTP** — uvicorn accepts, hands to Starlette.
2. **CORS middleware** (`server.py:2886-2891`). If the origin is allowed and `withCredentials` is set, `Access-Control-Allow-Origin` echoes the origin and `Allow-Credentials: true` is added. Preflight `OPTIONS` returns 200. The `"*"` default cannot coexist with credentials — see §1.
3. **Router match** — the shared `api = APIRouter(prefix="/api")` from `deps.py:37` resolves the path.
4. **Cookie extraction + JWT decode** — the handler declares `user: dict = Depends(get_current_user)`. `deps.py:69-88`:
   - Read `access_token` cookie (line 70).
   - Fallback: `Authorization: Bearer <token>` header (72-74).
   - No token → 401 "Not authenticated".
   - `jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])` (line 78). HS256, 12h expiry (`deps.py:64`).
   - Enforce `type == "access"` (79). Refresh tokens can't authenticate directly.
   - Lookup `db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})` (81). This is one Mongo round-trip on every authenticated request. `users.id` is unique-indexed (`server.py:2750`) so it's cheap.
   - Expired signature → 401 "Token expired"; any other JWT error → 401 "Invalid token".
   - **No token_version field, no revocation list, no refresh rotation.** Logout only clears cookies client-side (`routes/auth.py:198-201`); a stolen access token remains valid until its 12h expiry.
5. **Scope / role check** — done inside the handler body, not via a dependency. Two patterns:
   - Role: `if user.get("role") != "talent": raise HTTPException(403, ...)`.
   - Scope: `_require_scope(user, "moderation")` in `revisions.py` and `admin.py`, or `has_admin_scope(user, "finance")` from `deps.py:168-172`. Superadmin implies all scopes.
   - Two admin endpoints — `POST /admin/rate-nudges/scan` and `GET /admin/scheduler` at `admin.py:186-211` — check `user.get("role") != "admin"` directly and bypass scopes entirely. Any admin can trigger them regardless of assigned scopes. Flagged in the earlier security review.
6. **Business logic** — Mongo I/O via Motor's async driver (`await db.<col>.find(...)`, `await ... .to_list(N)`).
7. **Response serialization** — FastAPI serializes the returned dict as JSON. Mongo `_id` fields are usually projected out with `{"_id": 0}`; when they aren't, the raw `ObjectId` is stringified inconsistently.
8. **Error handling** — `HTTPException` is caught by FastAPI's default handler and returned as `{"detail": "..."}`. Un-caught exceptions become 500. There is no global exception middleware; the Slack helper never logs 500s.
9. **Set-Cookie on login/register** — `set_auth_cookies` (`deps.py:91-95`) writes:
   ```
   access_token=...; Path=/; Max-Age=43200; HttpOnly; Secure; SameSite=None
   refresh_token=...; Path=/; Max-Age=604800; HttpOnly; Secure; SameSite=None
   ```
   No `Domain` attribute (so cookies are host-scoped). `Secure` means these cookies never work over HTTP; the local dev server must be HTTPS or a proxy that adds Secure at the edge, otherwise the browser refuses to store them. `SameSite=None` + no CSRF middleware = every state-changing endpoint is CSRF-open.

### Which routes use which dependency

- `Depends(get_current_user)` — nearly every non-public endpoint.
- `_require_scope(user, "<scope>")` — used inside `admin.py` (support/finance/moderation/customization/superadmin) and `revisions.py` (moderation).
- `has_admin_scope(user, "<scope>")` — used inside `projects.py` (finance for invoice issue/paid, superadmin/customization for save-as-template).
- Role checks (`user.get("role") == "..."`) — used in `auth.py`, `server.py`, `projects.py`, `revisions.py` for talent/employer/admin gating.

---

## 4. Data model

App-level identity is always a `str` UUID from `new_id()` (`deps.py:59-60`). Every read strips `_id` with `{"_id": 0}`. Only these indexes exist (`server.py:2749-2755`):

| Collection | Index | Uniqueness |
| --- | --- | --- |
| `users.email` | asc | unique |
| `users.id` | asc | unique |
| `engagements.id` | asc | unique |
| `payment_transactions.session_id` | asc | unique |
| `work_items.user_id` | asc | non-unique |
| `eois.id` | asc | unique |
| `eois.talent_id` | asc | non-unique |

Everything else — `deliverables`, `payouts`, `reviews`, `grievances`, `revision_requests`, `projects`, `project_milestones`, `project_invoices`, `project_variances`, `project_alerts`, `project_risks`, `dispute_fee_transactions`, `refund_audit_receipts`, `drill_receipts`, `reference_checks`, `broadcasts`, `notifications`, `support_notes`, `audit_log`, `site_customization`, `crm_integrations`, `crm_sync_log`, `integration_tokens`, `shortlists`, `rate_nudges`, `job_runs`, `referrals`, `newsletter_signups`, `custom_project_templates`, `payment_reminders`, `payout_runs`, `connected_accounts`, `files`, `project_leads` — is queried on unindexed fields. This is fine at demo scale; at any real volume, `deliverables.find({"engagement_id": ...})` and `revision_requests.find({"deliverable_id": ...})` will collscan.

### Collection catalog

**Identity / access**
- `users` — the everything table. Fields: `id`, `email`, `password_hash`, `role` (`talent|employer|admin`), `name`, `hours_balance`, `hero_placement`, `admin_permissions[]`, `email_verified`, `email_verification_token`, `verification_status`, `stripe_customer_id`, `stripe_payment_method_id`, and the nested `profile` blob (headline, bio, skills, hourly_rate, portfolio_images, work_history, references, government_id_url, availability, revision_flags, visibility_score, rate_bias_pct, clean_streak, abusive_pattern_flag, …). Written by nearly every module. Read by everything.
- `support_notes` — support-team notes per user; written by `admin.py:359`.
- `audit_log` — trail of hours adjustments and KYB perks grants; `admin.py:398`.
- `site_customization` — hero, CTAs, feature flags; `admin.py:436` write, `/customization/public` read.

**Marketplace**
- `shortlists` — `{employer_id, talent_id, headline, hourly_rate, skills, is_curated, created_at}`. `marketplace.py:157/182/190`, read by nightly CRM sync.
- `broadcasts` — hire-intent inbox row per (employer_id, talent_id). Written by `server.py:1508` (shortlist broadcast), read by talent inbox (`server.py:2122`) and SSE stream (`:2147`).
- `eois` — expressions of interest. `server.py:2467+`. Indexed on `id` and `talent_id`.
- `newsletter_signups` — waitlist emails from skill landing pages.
- `referrals` — `{referrer_id, referred_id, code, status, bonus_hours}`. `server.py:886/896`.

**Contracts**
- `engagements` — the contract layer. `{id, employer_id, employer_name, talent_id, talent_name, hours_allocated, hours_used, hourly_rate, scope, mode, employer_signature, talent_signature, status}`. `id` unique-indexed.
- `deliverables` — talent submissions against an engagement. `{id, engagement_id, talent_id, title, link, description, hours_claimed, status, revision_count, latest_revision_id, dispute_grievance_id, …}`. Queried on `engagement_id` (unindexed).
- `reviews` — post-engagement reviews with `status="pending_moderation"` gating.
- `payouts` — commission-calculated payout row per approved deliverable. Written at deliverable-approve time.
- `payout_runs` — aggregate of payouts generated by an admin run.

**Payments**
- `payment_transactions` — `{id, session_id, user_id, amount_cents, kind, payment_status, package_id, hours, project_id, milestone_id, invoice_id, created_at}`. `session_id` is unique-indexed. `kind` field discriminates hours-package vs milestone; dispute fees don't use this collection.
- `payment_reminders` — audit trail of overdue-invoice email + auto-charge attempts.

**Projects**
- `project_leads` — scoping requests before conversion. `projects.py:134` reads on `id` (unindexed).
- `projects` — active engagement + phases + RACI + budget rollup. `projects.py:225/237`.
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
- `drill_receipts` — signature receipt from public trust drill PDFs (`auth.py:702`).

**Integrations**
- `crm_integrations` — per-employer bearer token for HubSpot/Salesforce/Slack/SharePoint. **Plain-text token storage.**
- `crm_sync_log` — per-talent push/skip/fail log.
- `integration_tokens` — API tokens for work providers (Monday/Asana/Trello/…). **Plain-text.**
- `work_items` — unified work log across providers + Excel/MSP uploads. `user_id` is indexed.
- `connected_accounts` — portfolio + payout providers (LinkedIn/GitHub/Stripe Connect/Payoneer/Wise/Plaid). `server.py:2568+`.
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

- **Amount origin**: `PACKAGES` dict at `server.py:196-201`. Hardcoded USD amounts per pack (`starter_10`, `growth_50`, `scale_100`, `enterprise_500`).
- **Session create**: `POST /api/payments/checkout` (`server.py:495-540`). Calls `stripe.checkout.Session.create(mode="payment", ...)` at line 503 with metadata `{user_id, package_id, hours}`. **No `kind` field** — hours purchases are the default branch in the webhook.
- **Redirect URLs** (line 508-509): success `{origin}/payment/success?session_id={CHECKOUT_SESSION_ID}`, cancel `{origin}/payment/cancel`.
- **DB write on create** (line 512-518): insert `payment_transactions` with `status="initiated"`, `payment_status="pending"`.
- **Webhook**: `POST /api/stripe/webhook` at `server.py:557`.
  - Line 562: `stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)`.
  - Line 566-598: on `checkout.session.completed`, reads `event.data.object.metadata`.
  - Line 569 `kind == "dispute_fee"` → dispute branch (see 5.3).
  - Line 577 `kind == "milestone"` → milestone branch (see 5.2).
  - Line 591-597 default branch: `db.payment_transactions.update_one({"session_id": sid, "payment_status": {"$ne": "paid"}}, {"$set": {"payment_status": "paid", ...}})` then `db.users.update_one({"id": user_id}, {"$inc": {"hours_balance": hours}})`.
- **Idempotency**: the `$ne: "paid"` guard prevents double-crediting *of the same session*. There is no `event.id` dedup table, so if Stripe retries the same event twice within the same session, the guard still catches it. If the retry is for a different session that shouldn't have credited (unlikely but possible), nothing detects that.
- **Frontend poll**: `PaymentSuccess.jsx` polls `GET /api/payments/status/{sid}` every 2s up to 12 times (server.py:542). That endpoint itself calls `stripe.checkout.Session.retrieve` (line 549) and — if the webhook hasn't fired yet — self-crediting logic runs. This gives two parallel code paths that credit hours: webhook or polled retrieve, both guarded by the same `$ne` check.

### 5.2 Project milestone payment

- **Amount origin**: `project_milestones.amount` (float USD), stored when the admin issues the invoice via `POST /api/projects/workspace/{id}/milestones/{mid}/invoice` (`projects.py:585`).
- **Session create**: `POST /api/projects/workspace/{id}/milestones/{mid}/checkout` (`projects.py:780-863`). `stripe.checkout.Session.create(...)` at line 825, metadata `{kind: "milestone", project_id, milestone_id, invoice_id, user_id}`.
- **Redirect** (line 835-836): success `{origin}/projects/{project_id}/workspace?paid={CHECKOUT_SESSION_ID}`, cancel `?cancel=1`.
- **DB write on create**: `payment_transactions` row with `kind="milestone"`.
- **Webhook branch**: `server.py:577-590` — updates `payment_transactions.payment_status`, `project_milestones.status="paid"` + `paid_at`, `project_invoices.status="paid"` + `paid_at`. All three under the same `$ne: "paid"` guard.
- **Frontend poll**: `ProjectWorkspace.jsx` calls `GET /api/projects/milestone-payment/status/{sid}` on the `?paid=` redirect and refreshes the workspace.

### 5.3 Dispute arbitration fee

- **Amount origin**: env `REVISION_DISPUTE_FEE_USD` (default $49), used at `revisions.py:230` when a talent opens the dispute and at `:505` on the fee-payment path.
- **Session create**: `POST /api/grievances/{gid}/pay-fee` (`revisions.py:586-667`). Uses a local `_stripe` alias (the same SDK) at line 648 with metadata `{kind: "dispute_fee", grievance_id}`. Idempotent — if a valid session already exists for the grievance it's reused rather than recreated.
- **DB write on create**: upserts `dispute_fee_transactions` row and stamps `grievances.dispute_fee.stripe_session_id`.
- **Webhook branch**: `server.py:569-575`. When `kind == "dispute_fee"`, awaits `mark_dispute_fee_paid(session_id)` from `routes.revisions:701-729`, which:
  - Reads `dispute_fee_transactions` by session_id (line 705); early-returns if already paid.
  - Fetches the Stripe session to pull `payment_intent` for future refund.
  - Updates `dispute_fee_transactions` and `grievances.dispute_fee` to `payment_status="paid"`.
- **Silent-failure bug (already noted in the security review)**: the webhook's try/except around `mark_dispute_fee_paid` at `server.py:573-575` catches all exceptions and *still returns `{"ok": True}` at line 575*. If Mongo is briefly unavailable, Stripe records the event as delivered but the fee is never marked paid. There is no retry queue.

### 5.4 Refund path

- **Endpoint**: `POST /api/admin/grievances/{gid}/refund-fee` (`revisions.py:736-835`), requires `has_admin_scope(user, "moderation")`.
- **Fetch payment_intent**: if not cached on the grievance, `_stripe.checkout.Session.retrieve(session_id)` at line 714 pulls `payment_intent`.
- **Stripe call**: `_stripe.Refund.create(payment_intent=pi_id, reason="requested_by_customer", metadata={...})` at line 772. No `await` — sync SDK call blocks the loop.
- **DB writes**:
  - `grievances` (line 785-792): `dispute_fee.payment_status="refunded"`, `refund_id`, `refunded_at`, `refunded_by_id`, `refund_reason`.
  - `dispute_fee_transactions` (line 793-798): same shape.
- **Notifications**: email via `send_email` (line 806-816) and `notifications` row (line 825-832) of type `dispute_fee_refunded`.

### 5.5 Signed audit PDF

- **Endpoint**: `GET /api/admin/revisions/refund-audit/pdf?days=N` (`revisions.py:929-969`), `scope=moderation`.
- **Signature function** (`revisions.py:856-865`):
  ```python
  def _refund_audit_signature(rows, period_start, period_end):
      salt = os.environ.get(
          "REFUND_AUDIT_SIGN_SECRET",
          os.environ.get("DRILL_SIGN_SECRET", "jobatlas-refund-v1")
      ).encode()
      canonical = json.dumps({...}, sort_keys=True, separators=(",", ":")).encode()
      return hashlib.sha256(salt + canonical).hexdigest()
  ```
  - This is **not HMAC**. `sha256(salt + msg)` is vulnerable to length-extension. With the hardcoded fallback constant `"jobatlas-refund-v1"`, the "secret" is public. The signature is worthless as a tamper check without setting a real secret and moving to `hmac.new(secret, msg, sha256)`.
- **Receipt**: a row lands in `refund_audit_receipts` with the signature and issuer metadata.
- **Verify endpoint**: `GET /api/admin/revisions/refund-audit/verify/{sig}` (`revisions.py:972-981`) is a simple lookup — it does *not* recompute the hash to detect tampering; it only confirms a receipt with that signature was issued.

---

## 6. Business rule engine

All numbers are env-tunable but every one has a hardcoded default. Enforcement lives in `routes/revisions.py`; the reversal ("recovery") lives in the deliverable-approve flow in `server.py`.

| Rule | Env | Default | Enforced at | Reversed at |
| --- | --- | --- | --- | --- |
| Revision counter | — | — | `revisions.py:134` (`request-revision`) increments `deliverables.revision_count` | Never decremented; only cleared on dispute ruling for talent |
| Amber flag `under_review` | `REVISION_REVIEW_THRESHOLD` | 3 | `revisions.py:134` when count reaches threshold | 3 consecutive clean approvals — `REVISION_RECOVERY_UNDER_REVIEW` default 3 |
| Red flag `excessive_revisions` | `REVISION_PENALTY_THRESHOLD` | 5 | `revisions.py:134` when count reaches threshold | 5 consecutive clean approvals — `REVISION_RECOVERY_EXCESSIVE` default 5; also cleared on dispute ruling in talent's favour (`revisions.py:312`) |
| Visibility deduction | `REVISION_VISIBILITY_PENALTY` | 20 | Subtracted from `profile.visibility_score` (default 100) when `excessive_revisions` fires | Restored to 100 on recovery or talent-favourable ruling |
| Rate bias | `REVISION_RATE_NUDGE_PENALTY` | 10 | `profile.rate_bias_pct = -10` when `excessive_revisions` fires | Reset to 0 on recovery or talent ruling |
| "Proven Reliable" badge window | `PROVEN_RELIABLE_DAYS` | 90 | Checked against `profile.recovery_cleared_at` in badge computation | Expires 90d after last recovery |
| Employer abuse flag | `EMPLOYER_FLAG_UNIQUE_TALENTS` × `EMPLOYER_FLAG_WINDOW_DAYS` | 3 talents × 60 days | Scan runs at revision-request time when the current talent hits `REVISION_PENALTY_THRESHOLD`; queries revision_requests in the rolling window (`revisions.py` around the abuse-check block) | Manual admin action; no automatic timeout |
| Dispute right | `REVISION_PENALTY_THRESHOLD` | 5 | `POST /api/deliverables/{id}/dispute` at `revisions.py:235` requires `revision_count >= 5` | Not applicable — a dispute is a one-way transition |
| Dispute fee | `REVISION_DISPUTE_FEE_USD` | 49 | Loser owes; set at ruling (`revisions.py:312`) | Admin refund |
| Refund rate alert | `REFUND_ALERT_THRESHOLD_PCT` | 20 | 30-day rolling refund_rate computed in `/admin/revisions/refund-analytics` (`revisions.py:429`); comparison logic within the endpoint | — |

### Trusted Partner + Verified badges

Computed at `GET /api/talent` (`server.py:231-324`) per talent:
- `is_verified` = `verification_status == "verified"`.
- `is_trusted_partner` = compound rule; check the talent-card computation in server.py near line 260-290. Usually a mix of completed_engagements + avg_rating + verified.
- `is_proven_reliable` = `now() - profile.recovery_cleared_at < PROVEN_RELIABLE_DAYS` (default 90).
- `excessive_revisions` — echoed from `profile.excessive_revisions`.

### Recovery playbook

Deliverable approval (`server.py:670`) increments `profile.clean_streak` when `revision_count == 0` on the approved deliverable. On reject or revision, streak resets to 0. When streak crosses `REVISION_RECOVERY_UNDER_REVIEW`, amber lifts; when it crosses `REVISION_RECOVERY_EXCESSIVE`, red lifts, `visibility_score` restores to 100, `rate_bias_pct` resets to 0, and `recovery_cleared_at` is stamped (drives the 90-day badge).

---

## 7. External integrations

| Service | Env | Data leaving system | Code path | Failure handling | Sync/async |
| --- | --- | --- | --- | --- | --- |
| **Stripe API** | `STRIPE_SECRET_KEY` (fallback `sk_test_emergent`) | Customer id, session metadata (user_id, package_id, project_id, milestone_id, invoice_id, grievance_id), payment method | Sync `stripe.*` calls at `server.py:503, 549, 562, 991, 1035, 1067, 1075, 1155`; `projects.py:825, 991, 1000, 1024, 1030, 1035, 1067, 1076`; `revisions.py:648, 714, 772` | Raises `stripe.error.StripeError` up to handler; most handlers do not catch it, so it becomes 500. Webhook handler at `server.py:573-575` catches inside dispute branch but returns 200. | **Sync SDK inside async handlers** — blocks event loop |
| **Stripe Webhook** | `STRIPE_WEBHOOK_SECRET` | Nothing outbound | `server.py:557-598` | Signature failure → 400 | Sync `construct_event` inside async handler |
| **Resend (email)** | `RESEND_API_KEY` | Recipient email, subject, HTML body (verification tokens, dispute rulings, refund notices, rate nudges, invoice reminders) | `mailer.py:27+` `send_email` | `_resend is None` short-circuits and returns `{"sent": False, ...}`. Every caller ignores the return value. | Wrapped in `asyncio.to_thread` (mailer.py:34) — non-blocking |
| **Slack incoming webhook** | `SLACK_WEBHOOK_URL` | Variance-breach text, invoice-overdue mirroring | `projects.py:1117-1135` `_slack_notify` | No URL → early return. Exceptions logged, swallowed. | `asyncio.to_thread` — non-blocking |
| **Cloudflare Turnstile** | `TURNSTILE_SECRET_KEY` | Token from browser, remote IP | `auth.py:60-81` `_verify_turnstile` | No key → returns True (bypass). Exception → returns False. Uses `urllib.request` synchronously. | Sync `urllib` inside async — blocks briefly |
| **Anthropic via `emergentintegrations`** | `EMERGENT_LLM_KEY` | Talent's `skills` list, `years_experience`, `location` (raw f-string interpolation — see security review for prompt-injection risk) | `ai_service.py:13-50` `suggest_hourly_rate`, model `claude-sonnet-4-5-20250929` | Missing key → rule-based fallback (`{low: max(15, base-15), mid: base, high: base+25}`). Exception → same fallback. | `await chat.send_message(...)` — awaited; assumed non-blocking |
| **HubSpot** | Per-employer bearer | Talent name, email, rate on push-lead | `auth.py:920-966` `_validate_crm_token`, push-lead at `:1020-1090` | Try/except with 400 on validation failure; log entry in `crm_sync_log` | Sync `urllib` inside async |
| **Salesforce** | Per-employer bearer + instance URL | Same as HubSpot; sends as Lead | Same file | Same | Same |
| **Slack (CRM)** | Per-employer bot token | `auth.test` call to validate; no lead push | Same | Same | Same |
| **SharePoint** | Per-employer bearer | `me` call to validate | Same | Same | Same |
| **Monday/Asana/Trello/ClickUp/Jira/Confluence** | Per-user API tokens | GraphQL / REST queries | `work_integrations.py:75-134` | On failure returns stub sample so UI keeps rendering (67-71) | **Sync `requests` inside async** — blocks 15s max |
| **Object storage** | `EMERGENT_LLM_KEY` (reused as auth to `STORAGE_URL`) | Avatars, portfolio images, deliverable attachments | `storage_client.py:20, 29, 34, 45, 48` | Missing key → `init_storage` raises `RuntimeError` at startup; the startup handler catches it (`server.py:2745-2748`) so upload endpoints return 500 | Sync `requests`, blocks the loop during uploads |
| **BGV (background verification)** | — | No third-party vendor is called. Reference emails go via Resend only. | `auth.py:278-408` | Auto-approval based on reference responses; if a real BGV vendor was ever intended, none is wired | N/A |

---

## 8. Background jobs

Three cron jobs under a single `AsyncIOScheduler(timezone="UTC")` (`server.py:2796`), started in the startup handler at `:2864`. All `misfire_grace_time=3600`, `replace_existing=True`. Every run inserts a `job_runs` doc so `/admin/scheduler` can display the last run.

1. **`monthly_rate_nudge_scan`** — 1st of month, 09:00 UTC. Wrapper at `server.py:2811`; body is `_scan_and_record_rate_nudges` at `server.py:1391`. Iterates all `role=talent` users with non-empty skills, calls `suggest_hourly_rate`, upserts `rate_nudges` if |drift| > `RATE_DRIFT_THRESHOLD_PCT` (default 15). Sends an email via Resend (silent if unset).
2. **`daily_overdue_invoice_scan`** — 08:00 UTC. Wrapper at `server.py:2834`; late-imports `scan_overdue_invoices` from `routes.projects:1209`. For each unpaid invoice: send a reminder email every 3 days; after 7 days overdue, attempt off-session `PaymentIntent.create(off_session=True, confirm=True)` if the employer has a `stripe_payment_method_id`. Mirrors to Slack.
3. **`nightly_crm_sync`** — 02:00 UTC. Wrapper at `server.py:2856`; late-imports `_sync_shortlists_to_crm(trigger="cron")` from `routes.auth:1067`. For each employer with a `crm_integrations` row, push new shortlist rows to HubSpot/Salesforce since `last_sync_at`, deduping via `crm_sync_log`.

### Multi-instance safety

**None.** APScheduler runs entirely in-process with a memory-backed job store. If you scale to two uvicorn workers or two containers, all three jobs fire in every instance — rate nudges get scanned N times, invoice reminders get emailed N times, CRM pushes get duplicated. There is no distributed lock, no jobstore backed by Mongo (would need `MongoDBJobStore`), no leader election. Deployment must pin this app to a single instance or move the scheduler out.

---

## 9. Async correctness (blocking I/O inside `async def`)

The FastAPI event loop is a single asyncio loop per worker. Every synchronous network call inside an `async def` handler stalls that loop for every other request. This codebase has a lot of them. High-impact ones:

- **Stripe SDK (sync)** — every one of these blocks: `server.py:503, 549, 562, 991, 1035, 1067, 1075, 1155`; `projects.py:825, 991, 1000, 1024, 1030, 1035, 1067, 1076`; `revisions.py:648, 714, 772`. Under normal Stripe latency (100-500ms) this is tolerable at low RPS; under an outage it will lock the worker for the full timeout.
- **`urllib.request` in `_verify_turnstile`** (`auth.py:75`) and CRM token validation (`auth.py:932, 942, 949, 958`) — synchronous, no timeout override; Cloudflare defaults apply.
- **`requests` in work-integrations adapters** (`work_integrations.py:77, 89, 101, 108, 117, 134`) — 15s timeout; called from `server.py:2349` (`connect_integration`) and `:2380` (`sync_integration`) inside `async def` without any `to_thread` wrapper.
- **`requests` in `storage_client.py`** (`:20, 29, 34, 45, 48`) — object uploads / downloads; also called from async without offloading. Big files stall the loop.
- **ReportLab PDF generation** inside async handlers: `auth.py:669` (`public_trust_timeseries_pdf` → `_render_drill_pdf`), `revisions.py:930` (`admin_refund_audit_pdf` → `_render_refund_audit_pdf`), `projects.py:753` (invoice PDF → `_render_invoice_pdf`). All sync; large PDFs will freeze the worker.

Two things *are* offloaded correctly:
- **Resend email** — `send_email` wraps its blocking SDK call in `asyncio.to_thread` (`mailer.py:34`).
- **Slack webhook** — `_slack_notify` uses `asyncio.to_thread` (`projects.py:1117-1135`).

Everything else is a latent starvation bug. The right fix is either `httpx.AsyncClient` for HTTP, or blanket `await asyncio.to_thread(...)` around the sync calls.

There are no `time.sleep` calls in the async paths that I found.

---

## 10. Frontend ↔ backend contract

- **Axios instance**: `frontend/src/lib/api.js:5-8`.
  ```js
  const BASE = process.env.REACT_APP_BACKEND_URL;
  const api = axios.create({ baseURL: `${BASE}/api`, withCredentials: true });
  ```
  Env var is `REACT_APP_BACKEND_URL`. Missing → `baseURL` becomes `"undefined/api"` and every request fails; the SPA does not check.
- **Cookies**: `withCredentials: true` sends the httpOnly `access_token` cookie on every request. CORS on the backend must echo the exact origin (not `*`) with `Allow-Credentials: true` — see §1.
- **Error formatting**: `formatErr(e)` at `frontend/src/lib/api.js:10-16` unwraps `e.response.data.detail`. It handles Pydantic's array-of-errors shape and stringifies otherwise. There is **no global response interceptor** — 401/403 are not automatically redirected to login; each page decides whether to catch or ignore.
- **Auth context**: `frontend/src/context/AuthContext.jsx:1-20`. On mount, `api.get("/auth/me")` — `null` = loading, `false` = guest, object = logged in. `logout()` posts `/auth/logout` then sets `user=false`. `refresh()` re-fetches `/auth/me`.
- **Protected routes**: `frontend/src/components/ProtectedRoute.jsx`. Redirects to `/login` for guests, to `/` if role doesn't match (admin bypasses all role checks — an admin sees talent + employer pages fine).
- **Toasts**: `sonner` at `frontend/src/App.js:87`. Individual pages call `toast.success/error(formatErr(e))`.

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
- `REACT_APP_BACKEND_URL` — required.
- `REACT_APP_TURNSTILE_SITE_KEY` — used by `Register.jsx`; defaults to Cloudflare's `1x00000000000000000000AA` test key when unset. Frontend loads the widget script from Cloudflare's CDN with a 6-second timeout; if the CDN load fails, the submit button re-enables without a token and the backend accepts empty tokens (since `TURNSTILE_SECRET_KEY` is also unset).

---

## Appendix: surprising things

Written down so the next engineer doesn't have to re-derive them.

1. **`engagements.py` (40 lines) is dead code.** All engagement endpoints live in `server.py`. Don't add code to `routes/engagements.py` expecting it to be wired.
2. **Two admin endpoints escape the scope system.** `POST /admin/rate-nudges/scan` and `GET /admin/scheduler` at `admin.py:187-211` check `user.get("role") != "admin"` directly. Any admin — even one with `admin_permissions=[]` — passes.
3. **`_refund_audit_signature` is `sha256(salt + msg)`, not HMAC**, and falls back to the hardcoded string `"jobatlas-refund-v1"` when both env secrets are missing. The "signed" PDF is effectively unsigned in default deployments.
4. **The Stripe dispute-fee webhook swallows exceptions and returns 200.** `server.py:573-575` catches errors from `mark_dispute_fee_paid` and still tells Stripe everything is fine. Silent payment loss.
5. **No JWT revocation. No `token_version` field.** Logout only clears cookies (`auth.py:198-201`). Stolen access tokens live 12h.
6. **Cookies are `SameSite=None` with no CSRF token.** Every mutation is CSRF-exposed.
7. **Only 5 collections are indexed.** Everything else collscans. Fine at demo scale, not at real scale.
8. **`emergentintegrations` is not on PyPI and isn't in `requirements.txt`.** If it's not preinstalled in the runtime image, boot fails at `ai_service.py:6` → `routes/auth.py:47`.
9. **`storage_client.py` reuses `EMERGENT_LLM_KEY` as its auth token.** Same env, different service.
10. **The default admin email is `admin@talenthub.io`**, from an earlier product name; the rest of the codebase brands as Geminista / `geminista.com`. Don't be surprised when the seed row doesn't match the outward-facing brand.
11. **CORS default of `"*"` cannot serve credentialed requests.** `CORS_ORIGINS` must be set to a comma-separated origin list or the SPA cannot authenticate.
12. **APScheduler is in-process with a memory jobstore.** Do not run multiple workers/replicas without moving the scheduler out — you'll get N-fold duplicate emails and CRM pushes.
13. **The rate-nudge scanner and manual `POST /profile/suggest-rate` interpolate talent-controlled `skills` and `location` straight into the LLM prompt** (`ai_service.py:26, 28`). Prompt injection lets talent inflate their own rate. See the security review for the fix.
14. **`_scheduler` is declared `= None` on line 2870**, *after* the startup handler that assigns it (line 2796). Both statements are module-level, so the None assignment runs first at import time and the startup handler overwrites it on boot. Confusing but not a bug.
15. **Late imports of `logger` inside handlers** at `projects.py:398, 894, 1134, 1291` are redundant — `logger` is already imported at module top via `deps`. Harmless.
