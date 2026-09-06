# PROJECT_STATUS.md — Job Atlas hardening programme

Last updated: end of Phase 1a. Read alongside `SECURITY_BACKLOG.md`,
`VALIDATION_PROCESS.md`, `CONTRACTOR_SPLIT.md`, `CLAUDE.md`.

---

## 1. Where we are

| Phase | Status |
| --- | --- |
| 0 — Repo self-describing + endpoint inventory | **Done** |
| 0.5 — Scanner hardening + policy files | **Done** |
| 1a — Test harness | **Done** |
| 1b — Convert FEATURES.md into tests (23 sections) | Not started |
| 1c — Playwright E2E | Not started |
| 1d — CI gate (`make verify`) | Partial — targets exist, no CI |
| 2 — Fix loop (S-01…S-25, F-01…F-09) | Not started |
| 3 — Standing commands | Files written, not exercised |
| 4 — Contractor split (`F-03` → `atlas-core`) | Blocked on Phase 2 |

---

## 2. What exists now

### Documentation and policy
- `CLAUDE.md` — repo constitution, 10 invariants, definition of done.
- `SECURITY_BACKLOG.md` — 25 security items (S-01…S-25), 8 feature items (F-01…F-08).
- `VALIDATION_PROCESS.md` — the four-phase programme.
- `CONTRACTOR_SPLIT.md` — how to hire without shipping the moat.
- `docs/ENDPOINT_INVENTORY.md` — AST-derived, regenerable.
- `security/public_routes.yml` — the blessed unauthenticated surface.
- `security/csrf_exempt.yml` — default-deny exemptions, one entry (Stripe webhook). CLAUDE.md invariant #7 is now anchored to this file — adding an exemption requires the same review as a P0 change.

### Tooling
- `docs/scripts/{route_scan,features_scan,diff,render_inventory}.py` — parameterised, CI-runnable.
- Scanner correctness fixes: `Annotated[..., Depends(...)]`, decorator-level `dependencies=`,
  positional-vs-kwonly defaults alignment, skip counting, unrelated-`Depends` no longer suppresses
  the NO-AUTH flag.

### Harness
- `docker-compose.test.yml` — mongo (tmpfs), stripe-mock, backend :18000, frontend :13000.
- `.env.test` — every variable the code actually reads, derived by grep, not by guess.
- `backend/tests/{seed,conftest,sitecustomize,test_00_smoke}.py`, `backend/Dockerfile.test`,
  `frontend/Dockerfile.test`, `Makefile`.
- Personas: `admin-all`, `admin-noscope`, `talent-clean`, `talent-flagged`, `employer-card`,
  `employer-nocard`.
- Invariant tests: `test_public_surface.py`, `test_csrf_surface.py` (17 passed, 1 ratchet/skip).
- No application code has been modified. That is still true and should stay true until Phase 2.

---

## 3. Findings so far

### From the inventory (Phase 0)
- **S-23 (P0)** `POST /api/projects/lead` — unauthenticated, trusts client `employer_id`.
- **S-24 (P1)** `GET /api/projects/templates/{id}/team-suggestions` — leaks `_CURATED_TALENT`
  names + hourly rates to anyone.
- **S-25 (P1)** `GET /api/grievances/{gid}/fee-status` — moderation scope only; payer may be
  unable to poll their own fee status. **Still unverified.**
- **S-09** confirmed: three `/api/admin/*` routes gate on `role == "admin"` with no scope.
- FEATURES.md drift: `/engagements/{id}/sign` documented at the wrong path; `/api/messages*`,
  `/api/accounts*`, `/api/employers/{id}`, `/api/files/{id}`, `/api/work/items/{id}`,
  `/api/shortlist/broadcasts` undocumented entirely.

### From the harness (Phase 1a) — new
- **F-01 upgraded.** `emergentintegrations==0.2.0` is not on PyPI. This is not a boot *risk*, it is
  a confirmed **fresh-install blocker**. Nobody can `pip install -r requirements.txt` today.
- **F-09 (documentation debt today; becomes P1 the day this app is deployed).**
  The app is currently local-only and never deployed, so no production configuration is at risk.
  On deploy, this graduates to a P1 correctness bug: anyone configuring prod from ARCHITECTURE.md
  sets variables nothing reads, and the **penalty and recovery ladder silently runs on hardcoded
  defaults**. Fix as a doc-only PR now to avoid ever shipping the trap.

  Eight variables are documented under names the code does not read:

  | ARCHITECTURE.md says | Code actually reads |
  | --- | --- |
  | `REVIEW_FLAG_THRESHOLD` | `REVISION_REVIEW_THRESHOLD` |
  | `PENALTY_THRESHOLD` | `REVISION_PENALTY_THRESHOLD` |
  | `RECOVERY_UNDER_REVIEW` | `REVISION_RECOVERY_UNDER_REVIEW` |
  | `RECOVERY_EXCESSIVE` | `REVISION_RECOVERY_EXCESSIVE` |
  | `VISIBILITY_PENALTY` | `REVISION_VISIBILITY_PENALTY` |
  | `RATE_NUDGE_PENALTY_PCT` | `REVISION_RATE_NUDGE_PENALTY` |
  | `EMPLOYER_FLAG_TALENTS` | `EMPLOYER_FLAG_UNIQUE_TALENTS` |
  | `EMPLOYER_FLAG_WINDOW_D` | `EMPLOYER_FLAG_WINDOW_DAYS` |

  Five more variables are read by code and absent from ARCHITECTURE.md: `APP_BASE_URL`,
  `PUBLIC_BASE_URL`, `PUBLIC_SITE_URL`, `INTEGRATION_PROXY_URL`, `SENDER_EMAIL`.

  **Verified:** `.env.test` uses the code-correct names and its numeric values match FEATURES.md §12
  exactly (revision 3+ → `under_review`, 5+ → `excessive_revisions`, visibility −20, rate bias −10%,
  5 revisions × 3 talents × 60 days, $49 dispute fee). See §5 harness debt for the caveat that
  matching-defaults exactly means a config-read regression is invisible until §12 tests land.

---

## 4. The one thing to fix before Phase 1b

**The harness authenticates with `Authorization: Bearer`, not the cookie.**

`deps.py:72-74` accepts both. The browser uses the httpOnly cookie; the tests use a bearer header.
That means:

1. **No test will ever exercise the cookie path** — the path every real user takes.
2. **CSRF cannot be tested at all.** Bearer auth is inherently CSRF-immune, so a test suite that
   only sends bearer tokens will pass with or without the S-01 fix. The `test_csrf_surface.py`
   ratchet is measuring a surface the tests never touch.
3. **S-01, S-07 (token revocation), and cookie flag correctness are all untestable** as things stand.

There is also a prior question: **why does the API accept bearer tokens at all?** If no first-party
client sends one, dual auth is unnecessary attack surface, and it means an XSS that reads a token
from anywhere gets full API access without needing the httpOnly cookie. If it exists only for the
SSE endpoint's `?token=` query param, scope it to that route.

Track as **S-26 (P0 candidate)** — recorded in `SECURITY_BACKLOG.md`. Evidence:

- `grep -rn "Authorization" frontend/src/` → **zero matches**. No first-party client sends a Bearer token, so the Bearer branch of `deps.py:72-74` has no legitimate consumer.
- The httpOnly cookie is the only defence against XSS-driven token theft. Dual auth means an XSS that reads a token from anywhere in the DOM gets full API access, defeating the point of `httpOnly`.
- Once S-01's CSRF middleware lands it will (correctly) only enforce on cookie-authed requests. Bearer callers will slip past it silently — so the S-01 fix is incomplete until S-26 is resolved.
- **Zero legitimate consumers on the server side.** The SSE endpoint at `server.py:2147` was previously suspected to justify Bearer, but verification (2026-08-30) shows it reads the cookie first, then a `?token=` query param, and does its own inline `jwt.decode` — it never touches `get_current_user`, so removing the Bearer branch has no effect on it. Every other `Authorization: Bearer` in backend is an **outbound** call (HubSpot/Salesforce/Monday/Asana/Jira), which is unaffected.

The right fix is cookie-only: delete the Bearer branch in `deps.py:72-74`. This is a small, self-contained diff and should land **before** S-01, so the CSRF middleware has one auth path to reason about instead of two.

Harness fix, before any Phase 1b test is written: run the backend over TLS in the test stack
(self-signed cert + `verify=False` in httpx) or set `COOKIE_SECURE=false` via env in test only, so
`SameSite=None; Secure` cookies work over the loopback. Then make the client factory **cookie-only**.
Do NOT ship a Bearer opt-in fixture "for convenience" — that's the exact escape hatch that got us the
untested-cookie-path problem to begin with. The SSE endpoint uses `?token=` (not Bearer), so its
tests can use a dedicated query-param fixture without reintroducing header-based auth.

---

## 5. Other harness debt (accepted, tracked)

| # | Compromise | Risk | Action |
| --- | --- | --- | --- |
| H-1 | `emergentintegrations` replaced by a two-class shim in the test image | Tests run against an import surface prod doesn't have | Closes when F-01 lands. Until then, no test may assert LLM behaviour. |
| H-2 | `stripe-mock` has no healthcheck (`service_started` only) | Race on slow machines | Acceptable; `test_stripe_api_base_is_the_mock` catches it. |
| H-3 | `pytest-asyncio==1.4.0` (test image only). The original ask was to hard-pin to `1.2.0`, but 1.2.0 declares `pytest<9` and conflicts with the pinned `pytest==9.1.1` in `requirements.txt`. 1.4.0 is the earliest release that supports pytest 9. `pytest-cov==6.0.0` has the same story (5.x declares `pytest<9`). | Silent breakage on next pytest-asyncio / pytest-cov major bump | Kept as-is until we upgrade pytest itself. Revisit both pins on any pytest version bump. |
| H-4 | `asyncio_default_test_loop_scope = session` | Cross-test state leakage through the Motor client | Acceptable for now. Per-test DB drop still isolates data. Revisit if flakes appear. |
| H-5 | passlib/bcrypt 4.x warning noise | Cosmetic; will mask real warnings later | Pin `bcrypt<4` in the F-01 PR. |
| H-6 | Legacy `test_iteration*.py`, `backend_test.py` excluded from `make test-backend` | Dead tests rot and confuse | Delete them when the section they cover is converted in 1b. Don't leave them lying around. |
| H-7 | `stripe-mock` returns canned fixtures | **Cannot test webhook signature verification (S-03) or the refund `payment_intent` path** | Money-path tests need locally-signed payloads with a test `STRIPE_WEBHOOK_SECRET`. Do not assume 1b covers money. |
| ~~H-8~~ | ~~`.env.test` values match code defaults exactly.~~ **CLOSED — F-11 (2026-09-05, commit `4a85b96`).** `.env.test` now seeds `REVISION_REVIEW_THRESHOLD=4` (non-default vs code default 3); `test_config.py` (Phase 1b step 6) asserts `settings.business_rules.revision_review_threshold == 4`, proving the config path is live. **Finding surfaced during the F-11 sweep:** changing 3→4 broke **zero** active tests, because the only ladder assertion in the repo is `test_iteration33_revisions.py:196` (`test_third_revision_triggers_under_review`) — which lives in the legacy `test_iteration*.py` suite explicitly excluded from `make test-backend` (per H-6). **The revision penalty ladder has no coverage in the active harness at all.** Phase 1b ordering therefore reorders: §12 (revision ladder) and §13 (dispute/fee) must come before §3/§6/§7/§8, so the ladder gains coverage before we depend on it for any other feature test. |
| H-9 | `clean_db` in `backend/tests/conftest.py` is autouse function-scoped: it drops + reseeds the shared Mongo before every test. Under the pytest.ini default `-n 2 --dist loadscope`, two workers hit the same backend and one worker's drop invalidates the other worker's live JWT for the ~5ms window before the reseed lands — non-deterministic 401 "User not found" flakes. Fix in place: `-n 0` on the Makefile invocation (pytest.ini documents `-n 0` as the sanctioned serial mode). | Test-suite serial execution as coverage grows. | Serial runtime exceeds 60 s. Then either per-worker DB namespacing (needs backend to switch DB by header — an app-level change, out of no-app-code-change scope) or a Makefile split into `test-backend-unit` (parallel; scanner/public-surface/csrf tests) and `test-backend-integration` (serial; smoke + §11 + future §XX). Interim mitigation: keep the serial suite small enough that runtime stays under a minute. |

---

## 6. What's next, in order

App is local-only, never deployed. Prod-verification steps and live-exploit hotfixes
(previously items 1 and 2) are not applicable — dropped from this list.

1. **Doc-only ARCH.md correctness fix (F-09).** Rename the eight env-var entries in
   ARCHITECTURE.md §6 to the code-correct `REVISION_*` / `EMPLOYER_FLAG_UNIQUE_TALENTS` /
   `EMPLOYER_FLAG_WINDOW_DAYS` names. Add the five undocumented ones (`APP_BASE_URL`,
   `PUBLIC_BASE_URL`, `PUBLIC_SITE_URL`, `INTEGRATION_PROXY_URL`, `SENDER_EMAIL`).
   No code change; unblocks a future deploy from stepping on the trap.
2. **Fix the harness to be cookie-only** (§4). Terminate TLS in the test stack or
   allow non-secure cookies via env in test only. Client factory sends the cookie and
   nothing else. Do not ship a Bearer opt-in fixture — "for convenience" is exactly
   how the untested-cookie-path problem comes back. SSE tests use a dedicated
   `?token=` fixture (the endpoint reads its own query param at `server.py:2147`;
   it never touched the Bearer branch). Nothing in 1b is trustworthy until this lands —
   the whole cookie/CSRF surface is unexercised today.
3. **Phase 1b begins.** One FEATURES.md section per session, Sonnet, template in
   `VALIDATION_PROCESS.md` §1b. Ordering — **§11 → §12 → §13 → §10 → §14 → §17 →
   §3/§6/§7/§8**. §11 (engagements) first because it touches auth, ownership, and
   state transitions. **§12 (revision ladder) and §13 (dispute/fee) must land
   before §3/§6/§7/§8 rather than after** — the F-11 sweep confirmed the ladder
   has zero coverage in the active harness (H-8 finding, §5), so any feature test
   built on top would depend on unverified behaviour. Add signed-payload Stripe
   fixtures before reaching §10/§14/§17.
4. ~~Hard-pin `pytest-asyncio==1.2.0`~~ Already pinned to `1.4.0` — see §5 H-3. `-rs` added to `make verify`.
5. **Verify S-25** against `EngagementDetail.jsx` — quick grep to confirm the payer
   path is actually reachable. Documents whether S-25 is a scanner miss (as suspected)
   or was a real bug hiding behind the misdiagnosis.
6. **Phase 1c** Playwright, then **1d** CI gate. Nothing merges red from that point.
7. **Phase 2** fix loop: `S-05 → S-02 → S-26 → S-01 → S-07 → S-03 → S-04 → S-08 → S-06`,
   then P1 by number. **S-26 lands before S-01**, not after — removing Bearer
   acceptance in `deps.py:72-74` is a small self-contained diff, and doing it first
   means the S-01 CSRF middleware has one auth path to reason about instead of two.
   Verified 2026-08-30: no server-side code depends on inbound Bearer (SSE uses its
   own `?token=` decode; all other `Authorization: Bearer` refs are outbound).
8. **F-03** (split `server.py`), then extract `atlas-core`, then hire.

---

## 7. Standing rules

- No application code changes until Phase 1b is complete, except a live-exploit hotfix.
- One backlog item per branch, per PR. Branch name = backlog id.
- Every new finding gets an ID in `SECURITY_BACKLOG.md` the day it's found.
- Every accepted compromise gets a row in §5 above with a named closing condition.
