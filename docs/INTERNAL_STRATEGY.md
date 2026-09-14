# INTERNAL_STRATEGY.md — Job Atlas

**NDA-only.** Do not share, quote, or excerpt without written permission from
the operator (Denkoit Softech Pvt. Ltd.). Contents:

- §1 Security posture — every S- and F- item bucketed and sequenced. Reading
  this end-to-end tells you where the ship-blocking vulnerabilities are and
  in what order they're being closed.
- §2 Contractor strategy — the tiered model, sharing patterns, and the
  argument for the sequence. Reading this tells you which parts of the
  business can be handed out and which cannot.

Split out from `docs/ENGINEERING_HANDBOOK.md` on purpose so the boundary is
structural: only forward the handbook. If someone needs the strategy, they
need a separate access grant.

Every bucketed item below was verified against `SECURITY_BACKLOG.md` and
`PROJECT_STATUS.md` at the time of writing. If a claim can't be verified
from the code (backlog entry describes intent, not observed state), it is
called out inline.

---

## 1. Security posture

`SECURITY_BACKLOG.md` catalogues 44 items (S-01…S-31, F-01…F-15, with gaps
where numbers were retired). This section restates each item's current
lifecycle state in three buckets. **Closed** and **partial** claims are
sourced from strike-throughs / "PARTIAL" markers in the backlog file plus
the `PROJECT_STATUS.md §2.F11` closure log; **open** is the residual.

### Snapshot

- **Closed**: 10 items (S-05, S-15, S-25, S-26, S-27, S-28, S-31, F-01, F-08, F-10).
- **Partial**: 4 items (S-02, S-04, S-08, S-20) — the F-11 sweep did half
  the fix; the other half is called out inline.
- **Open**: 30 items (20 S- + 10 F-).

### Closed

| ID | Landed | What closed it | One-line why it's closed |
| --- | --- | --- | --- |
| S-05 | F-11 (`4a85b96`) | Stripe secret-key fallback removed | `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` are `Field(alias=...)` in `config.StripeSettings` with no defaults; boot fails aggregately. Sweep found 11 read sites (not 1) — all now via `settings.stripe.secret_key`. |
| S-15 | F-11 (`4a85b96`) | LLM key ≠ storage token | `STORAGE_TOKEN` is its own required field; `storage_client.py` reads `settings.storage.token`. `init_storage`'s `if not EMERGENT_KEY: raise` guard is gone. |
| S-25 | scanner-fix (S-28) | Scanner false positive | Handler always enforced `user["id"] in (talent_id, employer_id) OR moderation`. `docs/scripts/route_scan.py` misread the handler; scanner extended to recognise ownership patterns (see S-28). |
| S-27 | F-11 (`4a85b96`) | Storage-URL fallback removed | `INTEGRATION_PROXY_URL` is `Field(alias=...)` with no default; the `integrations.emergentagent.com` fallback string is gone from `storage_client.py`. |
| S-28 | 2026-09-06 | Scanner ownership-check blind spot fixed | `_collect_body_checks` extended with an `ownership_checks` class; 10 new tests + 4 inverse-guard canaries. 13 routes now attribute ownership; zero unauth→protected reclassifications. |
| S-31 | `0e5fd5a` (2026-09-07) | Logout cookie attribute-match | `response.delete_cookie` in `/api/auth/logout` now mirrors the set-time attributes (`path="/"`, `secure=True`, `samesite="none"`), so Chromium recognises the deletion as attribute-matching and evicts the httpOnly Secure cookie. Regression guard: `test_03_auth.py::TestLogout::test_deletion_attributes_match_the_set_cookie`. |
| F-08 | F-11 (`22329d1`) | SPA env-var config boundary | `frontend/src/config.js` is the sole `process.env.REACT_APP_*` reader; SPA renders a red banner and throws on missing `REACT_APP_BACKEND_URL`. 13 sites swept across 10 files. |
| F-10 | F-11 (`4a85b96`) | Rate-drift threshold env-tunable | `settings.business_rules.rate_drift_threshold_pct: int = Field(default=15, alias="RATE_DRIFT_THRESHOLD_PCT")` in `config.BusinessRules`. Was hardcoded at `deps.py:153`. |
| F-01 | commit `9ba2368` (2026-09-13) | emergentintegrations optional | `ai_service.py` wraps the import in `try/except ImportError`; suggest_hourly_rate falls back to rule-based rates. Package removed from `requirements.txt`; Dockerfile.test shim removed. Regression guard: `test_f01_optional_import.py`. |
| S-26 | commit `cabf1d0` (2026-09-14) | Bearer branch removed; cookie-only | `deps.get_current_user` reads the `access_token` cookie and nothing else. SSE endpoint's own `?token=` inline decode is scoped to that one route and unaffected. Regression guards: `test_s26_no_bearer.py`, `test_s26_sse_still_works.py`. |

`F-09` and `F-11` don't appear as backlog rows — `F-09` closed via F-11's
sweep (per `PROJECT_STATUS.md §2.F11`); `F-11` is a work-package label,
not a backlog item.

### Partial — half-done, other half tracked

| ID | Done | Still open |
| --- | --- | --- |
| S-02 | Default removed (F-11); `CORS_ORIGINS` required at boot; field validator refuses `"*"` as an entry. Backlog row still describes the OLD state (`server.py:2886-2891`), so the SECURITY_BACKLOG.md text is stale but the code is fixed. | Per-env origin allowlist validation (e.g. reject `http://` in production). |
| S-04 | Fallback chain collapsed (F-11) — two independent required fields (`REFUND_AUDIT_SIGN_SECRET`, `DRILL_SIGN_SECRET`). Hardcoded `"jobatlas-refund-v1"` gone. | Primitive is still `sha256(salt + msg)` (length-extendable), not `hmac.new(secret, canonical, sha256)`. Verify endpoint still does a lookup instead of recomputing + `hmac.compare_digest`. Canary: `test_verify_detects_tampering_via_recompute` (xfail strict=True). |
| S-08 | Turnstile required at boot when `ENV=production` (F-11); dev/test fail-open path now logs `[S-08] TURNSTILE_SECRET_KEY unset ...` so it's not silent. | IP + email rate limiting (SlowAPI/Redis) on `/auth/login`, `/auth/register`, `/auth/resend-verification`, `/reference-check/{token}`. Constant-time login response (prevent user enumeration). |
| S-20 | `ADMIN_PASSWORD` default removed (F-11); seeder skip-with-WARN when unset — no hardcoded credential ever inserted. | `ADMIN_EMAIL` still defaults to legacy `admin@talenthub.io` (brand drift). No force-rotation on first login. Seeder does not refuse to re-run when `ENV=production` and a superadmin already exists. |

### Open — the residual, grouped by priority

**P0 — do not launch without these** (per SECURITY_BACKLOG.md's own header):

| ID | Issue |
| --- | --- |
| S-01 | CSRF middleware not registered. Cookies are `SameSite=None; Secure` with no CSRF token; every state-mutating request is forgeable from any origin. Exemption policy already scaffolded in `security/csrf_exempt.yml`. |
| S-03 | Stripe webhook has three related defects: **(a)** dispute-fee branch swallows exceptions and returns 200 (S-03(a)); **(b)** no `event.id` dedup — Stripe retries can double-process the same event (S-03(b)); **(c)** hours-purchase branch's `$inc hours_balance` is not gated on the atomic update result — TOCTOU under concurrent delivery (S-03(c)). Canaries: `test_dispute_fee_branch_raises_5xx_when_helper_throws`, `test_concurrent_replay_may_double_credit`. |
| S-06 | Plaintext third-party tokens in Mongo (`crm_integrations.access_token`, `integration_tokens`). One DB read = full access to customer HubSpot / Salesforce / Jira. |
| S-07 | No JWT revocation. Logout only clears cookies (attribute-matched post-S-31, but the token itself stays valid). Stolen access token lives 12h. No refresh rotation. |

**P1 — exploitable, bounded**:

| ID | Issue |
| --- | --- |
| S-09 | Two admin endpoints bypass the scope system (`POST /admin/rate-nudges/scan`, `GET /admin/scheduler` at `admin.py:186-211`) — check `role == "admin"` directly. Any admin — even one with `admin_permissions=[]` — passes. |
| S-10 | Prompt-injection via talent-controlled `skills` / `location` interpolated straight into the LLM rate-suggestion prompt (`ai_service.py::suggest_hourly_rate`). |
| S-11 | Ownership / IDOR audit not done. Handlers check `role`, not "does this row belong to this user." Three canary tests (`test_11_engagements.py::TestDeliverables{Create,Approve,Reject}::test_cross_tenant_..._returns_404_per_s11`) fail loudly today; clear when `load_owned(collection, id, user)` helper lands. |
| S-12 | Unbounded / unindexed queries = trivial DoS. Only 7 collections have indexes; 35+ collscan. |
| S-13 | Blocking sync I/O inside `async def` — Stripe SDK, `urllib`, `requests`, ReportLab. One slow upstream stalls the whole worker. |
| S-14 | File-upload path unvalidated. No content-type allowlist, magic-byte sniff, size cap, or EXIF strip. Government-ID objects served from guessable paths. |
| S-16 | No global 401/403 handling in the SPA. Expired session silently renders empty pages. |
| S-23 | `POST /api/projects/lead` unauthenticated and trusts client-supplied `employer_id`. Lead forgery, attribution poisoning, unbounded ops-queue spam. |
| S-24 | `GET /api/projects/templates/{id}/team-suggestions` returns `_CURATED_TALENT` names + hourly rates to any unauthenticated caller. Scrapeable supply pool + sell-rate/margin math. |
| ~~S-26~~ | ~~`deps.py::get_current_user` accepts `Authorization: Bearer` alongside the cookie~~. **CLOSED — commit `cabf1d0` (2026-09-14).** Bearer branch deleted; cookie-only. Regression guards in `backend/tests/test_s26_no_bearer.py` and `test_s26_sse_still_works.py` (SSE endpoint's own inline decode unaffected). |

**P2 — hardening**:

| ID | Issue |
| --- | --- |
| S-17 | No security headers (HSTS, X-Content-Type-Options, Referrer-Policy, CSP). |
| S-18 | No structured audit trail for admin actions beyond hours/KYB. |
| S-19 | No global exception handler; 500s are invisible. |
| S-21 | APScheduler in-process with memory jobstore — duplicates on scale-out. |
| S-22 | PII retention undefined (reference_checks, government-ID objects, crm_sync_log). Needed for GDPR/DPA answer. |
| S-29 | Scanner blind spot #2 — helper-delegated authorization (`_load_project_or_404`, `_load_deliverable_and_authorize`) not detected. All 11 affected handlers verified genuinely protected; tooling-only fix. |
| S-30 | Missing role gate on `POST /api/integrations/crm/push-lead`. Verified there's no cross-tenant write path (the OAuth token comes from the caller's own session-scoped integration), so this is doc-drift + a semantic role gate rather than a data-loss vector. |

**F- items (feature/correctness)**, open:

| ID | Issue |
| --- | --- |
| ~~F-01~~ | ~~`emergentintegrations==0.2.0` fresh-install blocker~~. **CLOSED — commit `9ba2368` (2026-09-13).** `ai_service.py` wraps the import in `try/except ImportError` and routes to the rule-based fallback; package removed from `requirements.txt`; Dockerfile.test shim removed. |
| F-02 | Dead `routes/engagements.py` (40 lines); real endpoints live in `server.py`. Either finish the extraction or delete the file. |
| F-03 | Split `server.py` (2,906 lines) by domain. Prerequisite for the contractor split in §2. |
| F-04 | Missing admin UI: Scheduler tab, rate-nudge trigger, scan-overdue, save-as-template. |
| F-05 | Dual-credit path (PaymentSuccess polling + Stripe webhook both credit hours) — companion to S-03(c). |
| F-06 | BGV auto-approval silently requires `email_verified`. Surface the blocker in the admin UI instead of failing silently. |
| F-07 | Revision counter never decrements; recovery only clears flags. Confirm intended product behaviour and state in `FEATURES.md §12`. |
| F-12 | 32 undocumented feature routes missing from FEATURES.md pipe tables (all have live SPA callers verified by grep). Six small doc-only PRs. |
| F-13 | 4 dead-code endpoints (`customization/public`, `pricing/tiers`, `pricing/quote`, `shortlist/broadcasts`) — zero SPA callers. Delete + prune tests + update `security/public_routes.yml`. |
| F-14 | Admin login has no auto-redirect to `/admin`. `Login.jsx` handles employer + talent; admin falls into `/`. Filed 2026-09-06 in Phase 1c v2. |
| F-15 | Password-reset backend endpoint doesn't exist — only a frontend testid + link placeholder. Users who click get a dead page. |

### Fix order (from PROJECT_STATUS.md §6, cross-checked against backlog state)

1. ~~**S-26** — delete the Bearer branch in `deps.py::get_current_user`.~~
   **DONE — commit `cabf1d0` (2026-09-14).** Cookie-only. Regression guards
   in `test_s26_no_bearer.py` + `test_s26_sse_still_works.py`.
2. **S-01** — register the CSRF default-deny middleware; wire it against the
   existing `security/csrf_exempt.yml` (single entry: Stripe webhook). Remove
   the skip on `test_csrf_surface.py`. Now unblocked by S-26 — one auth path
   to reason about.
3. ~~**Phase 1d** — wire `make security-scan` + CI runner.~~ **DONE** — see
   `PROJECT_STATUS.md §1`. Real `make security-scan` runs gitleaks (hard) +
   bandit / pip-audit / semgrep (report-only). CI merge gate lives at
   `.github/workflows/verify.yml`.
4. **P0 fix loop**, remaining: `S-07` (token revocation + refresh rotation) →
   `S-03` (webhook idempotency + all three sub-defects) → `S-04` (HMAC +
   verify recompute) → `S-08` (rate limiting + constant-time login) → `S-06`
   (envelope-encrypt third-party tokens at rest).
5. **P1 backlog** by number.
6. ~~**F-01** — replace `emergentintegrations` top-level import in
   `ai_service.py` with an optional guard so `pip install -r
   backend/requirements.txt` succeeds outside the test image.~~ **DONE —
   commit `9ba2368` (2026-09-13).**
7. **F-03** — split `server.py`. Prerequisite for the contractor split.
8. **Extract `atlas-core`**, publish the wheel, generate
   `atlas-contracts/openapi.json`, stand up the Prism mock. Then hire against
   a first work package (F-04 admin UI is the natural starting point).
9. **Cloud-storage integration** — a real S3/R2/GCS/Supabase target behind
   the existing three-function `storage_client.py` shape. Neutral-tier;
   shareable as a backend plugin work package once `atlas-core` exists.

Rationale for the sequence: S-26 → S-01 is dictated by "one auth path is
easier to reason about". The rest of the P0 loop is ranked by blast radius
(token theft > money loss > forgeable audit > credential enumeration > token
storage). F-03 comes last in the fix loop because the split needs the P0
auth+money surfaces to have stabilised — you don't refactor a module while
it's actively being patched.

---

## 2. Contractor strategy

Consolidated from `CONTRACTOR_SPLIT.md`. The argument in one sentence: the
answer to "can I give a contractor part of this?" is **no** until F-03
lands, because everything sensitive lives inside `server.py` (2,906 lines
containing auth, Stripe, pricing constants, penalty-ladder rules, the
curated-talent list, and the admin seeder). The fix is architecture, not
access control — make the crown jewels a dependency rather than a directory.

### What is actually secret

| Tier | Contents | Share? |
| --- | --- | --- |
| **Crown jewels** | Penalty/recovery ladder + thresholds (§6 in ARCH.md), pricing/`PACKAGES`, commission + payout math, `_CURATED_TALENT`, CRM sync logic, Stripe account wiring, admin scope model | Never |
| **Sensitive** | Auth, `deps.py`, `config.py`, webhook handler, encryption/KMS, refund + audit-signature paths, `security/*.yml` policy files | Never |
| **Neutral** | Projects workspace, RACI/variance/risks, calendar, referrals, SEO pages, work-provider adapters, the entire React SPA, native shell | Shareable per work package |
| **Public anyway** | API shape (the SPA reveals it), UI, copy | Already public |

Realistic moat: **rules + data + Stripe account.** Protect absolutely; be
pragmatic about the CRUD.

### Target structure (post-F-03)

```
atlas-core/            PRIVATE — never shared with any contractor
  deps.py, config.py, auth, payments, webhook, rules/, crypto/, admin scopes,
  seeder, security/csrf_exempt.yml + security/public_routes.yml
  → published as a private wheel: atlas-core==0.x  (CodeArtifact / GH Packages)

atlas-contracts/       SHARED — the only thing most contractors need
  openapi.json (generated from FastAPI: app.openapi())
  json-schemas/, example payloads, seed fixtures (synthetic data only)
  docker-compose.mock.yml → Prism mock server on :8000

atlas-frontend/        SHAREABLE per work package
  the React SPA. Talks only to REACT_APP_BACKEND_URL. Runs fully against the mock.

atlas-mobile/          SHAREABLE — Capacitor shell, push, biometric (NATIVE_APP_GUIDE.md)

atlas-plugins/         SHAREABLE per module — backend work packages
  projects/, work_integrations/, seo/, calendar/, referrals/
  each imports `from atlas_core.sdk import api, get_current_user, db, require_scope`
  and nothing else. The wheel is installed; the source is not in their repo.
```

### The three sharing patterns

1. **Frontend / mobile contractor** — hand them `atlas-frontend` +
   `atlas-contracts`. They run `docker compose -f docker-compose.mock.yml
   up` and develop against a Prism mock generated from your OpenAPI spec.
   No backend source, no DB, no API key. Their PR is validated by your
   Playwright suite against the real backend in **your** CI. Covers most
   hires — the SPA is ~all of the visible product and none of the moat.

2. **Backend contractor** — plugin repo + core as a wheel. Example: "build
   the Scheduler admin tab and the missing `/admin/*` UI endpoints" (F-04).
   They import `require_scope("superadmin")`, `db`, `api` from
   `atlas_core.sdk`. They can call the rules; they cannot read them.
   Wheels can be shipped as compiled bytecode for an extra layer, though
   treat that as friction, not security.

3. **Full-trust senior hire** — full repo, but only after F-03. For work
   that genuinely cannot be split (auth, payments, the rules engine), use
   NDA + controls rather than partition. Don't try to fake a split there.

### Non-negotiable controls, whichever pattern

| Control | Detail |
| --- | --- |
| Repo access | Per-repo, read + PR only. No org-wide access. No `main` push. `CODEOWNERS` on `atlas-core` = you. |
| Secrets | Contractor never gets prod or staging secrets. Their compose uses generated local ones. Stripe = test mode with a restricted key, or the mock. |
| Data | Synthetic seed only. Never a prod dump — you hold government IDs, reference-check emails, and CRM bearer tokens. A prod dump to a contractor is a reportable breach. |
| Environments | Ephemeral preview env per PR, torn down on merge. No standing access. |
| CI | Contractor's CI runs tests; **your** CI runs `make verify` + `/security-sweep` and holds the deploy keys. |
| Scope | Written work package: FEATURES.md section, acceptance tests, definition of done from CLAUDE.md. Paid against tests passing. |
| Legal | NDA + IP assignment signed before repo invite. Contractor-owned-by-default is the default in many jurisdictions — assign it explicitly. |
| Offboarding | Same-day: revoke repo, revoke package-index token, rotate any shared secret, bump `token_version` on their accounts, audit `audit_log`. |

### Sequence

1. Close the P0 fixes still open (see §1). Don't invite anyone into a
   CSRF-open codebase.
2. Land F-03: split `server.py` by domain, zero behaviour change, `make
   verify` green.
3. Extract `atlas-core` (rules + auth + payments + crypto + `config.py` +
   `security/*.yml`) and publish the wheel.
4. Generate `openapi.json` into `atlas-contracts`; stand up the Prism mock.
5. Write the first work package — F-04 (missing admin UI) is the natural
   starting point: neutral, self-contained, well-specified in
   `FEATURES.md §21`.
6. Hire against that package. Evaluate on the PR, then widen scope.

### Work packages ready to hand out today (against the mock)

| Package | Source of truth | Tier | Pattern |
| --- | --- | --- | --- |
| Missing admin UI: Scheduler tab, rate-nudge trigger, scan-overdue, save-as-template | F-04, `FEATURES.md §21` | Neutral | Frontend + contracts |
| Capacitor store submission: icons, splash, screenshots, push endpoint | `NATIVE_APP_GUIDE.md` | Neutral | Mobile |
| Work-provider adapters → async httpx + retries + real error surfacing | S-13, `work_integrations.py` | Neutral | Backend plugin |
| Mongo indexes + pagination caps on all list endpoints | S-12 | Neutral | Backend plugin |
| Projects workspace polish (variance, risks, RACI tabs) | `FEATURES.md §16` | Neutral | Frontend |
| Real cloud-storage integration (`storage_client.py` → S3/R2/GCS/Supabase, keep the 3-function shape) | `backend/storage_client.py`, `docs/LOCAL_SETUP.md §Storage` | Neutral | Backend plugin |
| Anything in auth, payments, revisions, admin scopes, `deps.py`, `config.py`, `security/*.yml` | — | Crown / Sensitive | **You only** |

### Shareable artifacts already in the repo

Safe to hand to a contractor without giving them any moat surface:

- `security/csrf_exempt.yml` + `security/public_routes.yml` — policy files the
  invariant tests ratchet against. Read-only reference.
- `docs/scripts/` — parameterised AST scanners: `route_scan.py`,
  `features_scan.py`, `render_inventory.py`, `coverage_gaps.py`, `diff.py`
  + `docs/scripts/tests/test_scanner.py` (22 tests including the S-28
  canary).
- `docker-compose.dev.yml` + `.env.dev.example` + `docs/LOCAL_SETUP.md` —
  hand-driven dev stack. A frontend contractor can bring it up locally
  without ever seeing backend source.
- `backend/tests/seed.py` — fixed synthetic personas + engagements +
  grievances. Idempotent; contractor tests against the mock can trust
  these ids.
- `docs/ENDPOINT_INVENTORY.md` — AST-derived, regenerable. Reveals nothing
  the SPA doesn't already reveal.
