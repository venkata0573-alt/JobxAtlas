# PROJECT_STATUS.md — Job Atlas hardening programme

Last updated: 2026-09-13 (post Phase 1c v2 + dev stack). Read alongside
`SECURITY_BACKLOG.md`, `VALIDATION_PROCESS.md`, `CONTRACTOR_SPLIT.md`, `CLAUDE.md`.

---

## 1. Where we are

| Phase | Status |
| --- | --- |
| 0 — Repo self-describing + endpoint inventory | **Done** |
| 0.5 — Scanner hardening + policy files | **Done** (extended 2026-09-06 by S-28 close — scanner recognises `user["id"]`-based ownership). |
| 1a — Test harness | **Done** |
| 1b — Convert FEATURES.md into tests (23 sections) | **Substantially done** — §3 auth, §6 marketplace, §7 shortlist, §8 EOI, §10 hours purchase, §11 engagements, §12–13 revisions, §14 grievances/refunds, §17 milestone payments, plus test_config, test_public_surface, test_csrf_surface, test_stripe_fixtures. **321 tests collected, baseline 313 pass / 3 pre-existing S-11 canaries / 1 CSRF skip / 4 xfailed.** |
| 1c — Playwright E2E | **Done** (v2, commit `3dcdb46`, 2026-09-06). 13 specs under `frontend/e2e/`, drive real UI (API-fallback paths removed). Reseeded per-run via `backend/tests/e2e_reset.py`. |
| 1d — CI gate (`make verify`) | Partial — `test-backend` + `e2e` are real; `test-frontend` + `security-scan` still placeholders. No CI runner wired yet. |
| 2 — Fix loop | **F-11 (config) landed 2026-09-06**, **S-31 (logout cookie attribute-match) landed 2026-09-07**, **F-01 (optional emergentintegrations import) landed 2026-09-13 (commit `9ba2368`)**. Closed since original PROJECT_STATUS: **S-05, S-15, S-25, S-27, S-28, S-31, F-01, F-08, F-10**. Partial: S-02, S-04, S-08, S-20. See §2.F11 and the SECURITY_BACKLOG.md strike-through rows for the full list. |
| 3 — Standing commands | Files written, not exercised |
| 4 — Contractor split (`F-03` → `atlas-core`) | Blocked on Phase 2 |
| — Local dev stack (parallel to Phase 1) | **Done** 2026-09-06 (commit `8c221f8`). `docker-compose.dev.yml` + `.env.dev.example` + `docs/LOCAL_SETUP.md` + Makefile `up-dev`/`down-dev`/`seed-dev`. Real Stripe (test mode via `stripe listen`), Resend, Turnstile; local mongo (named volume, persists); storage-mock retained because no real cloud-storage integration exists. |

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
- ~~No application code has been modified.~~ **F-11 is the first app-code change** (see §2.F11).

### 2.F11 — Config centralisation reference

Phase-table row summarises the outcome; the details below only cover what a
reader needs and can't derive from the code today.

- **Enforcement mechanism** (survives future refactors): the AST scan
  `backend/tests/test_config.py::test_no_module_outside_config_reads_os_environ`
  fails if any file under `backend/` (excluding `config.py` and `tests/`)
  reads `os.environ`/`os.getenv`. Same rule on the frontend side lives in
  `frontend/src/config.js` (the SPA refuses to mount with a visible red
  banner when `REACT_APP_BACKEND_URL` is unset).
- **Failure shape**: every required env var missing produces ONE
  `RuntimeError` at import listing all missing vars grouped by service. Not
  a scattered `KeyError` per module.
- **Deliberate design choice** worth remembering: `ENV` has no default.
  Silently defaulting to "development" in a prod deploy would neuter S-08's
  production-Turnstile enforcement — the highest-consequence config bug the
  module can prevent, so we make missing `ENV` a boot failure like any other
  required var.
- **Backlog partials still open** (fully closed items are struck through in
  the phase table above; these are the "yes but"s that need finishing):
  - S-02 — default removed, per-env origin validation still open.
  - S-04 — fallback chain collapsed, HMAC + verify-side recompute still open.
  - S-08 — prod-required + WARN logs done, rate limiting + constant-time
    login still open.
  - S-20 — password default removed + seeder skips, force-rotate on first
    login + prod-superadmin-check still open.
- **Commits**: `4a85b96` (backend sweep), `6448200` (initial doc updates),
  `22329d1` (frontend sweep).

---

## 3. Findings so far

### From the inventory (Phase 0)
- **S-23 (P0)** `POST /api/projects/lead` — unauthenticated, trusts client `employer_id`.
- **S-24 (P1)** `GET /api/projects/templates/{id}/team-suggestions` — leaks `_CURATED_TALENT`
  names + hourly rates to anyone.
- ~~**S-25 (P1)** `GET /api/grievances/{gid}/fee-status` — moderation scope only; payer may be
  unable to poll their own fee status.~~ **CLOSED 2026-09-06 as scanner false positive.**
  The handler has always enforced `user["id"] in (talent_id, employer_id) OR has_admin_scope("moderation")` — the payer path is reachable. Root cause was in `docs/scripts/route_scan.py::_collect_body_checks`, which didn't recognise `user["id"]`-based ownership patterns and classified the endpoint as moderation-only. Fix tracked and delivered as **S-28** (closed same day; scanner extended with an `ownership_checks` class + 10 new tests + 4 inverse-guard canaries).
- **S-09** confirmed: three `/api/admin/*` routes gate on `role == "admin"` with no scope.
- FEATURES.md drift: `/engagements/{id}/sign` documented at the wrong path; `/api/messages*`,
  `/api/accounts*`, `/api/employers/{id}`, `/api/files/{id}`, `/api/work/items/{id}`,
  `/api/shortlist/broadcasts` undocumented entirely.

### From the harness (Phase 1a) — new
- **F-01 upgraded.** `emergentintegrations==0.2.0` is not on PyPI. This is not a boot *risk*, it is
  a confirmed **fresh-install blocker**. Nobody can `pip install -r requirements.txt` today.
- ~~**F-09**~~ **CLOSED — F-11 (2026-09-06).** The historical fix scope was
  "rename the drifted names in ARCHITECTURE.md §6." The stricter close criterion
  applied here is that **§6 no longer lists raw env var names at all** — a
  same-named list would just recreate the same drift condition F-09 originally
  described. §6 now uses config-field paths (`revision_review_threshold`, etc.)
  as the identifier, with a header that says: "This section deliberately does
  NOT list env var names — the env-var → typed field mapping lives in
  `.env.example` and `docs/CONFIG_INVENTORY.md`. Rename a field in config.py
  and the alias, the doc, and this table all update from a single source."
  Renaming a field now surfaces as an IDE/type-check failure at every consumer,
  not as free-form doc drift.

  Historical evidence (pre-F-11): eight variables under wrong names + five
  undocumented — see git history for the specific table.

---

## 4. Auth surface — Bearer branch still open

The harness half is done. The backend serves HTTPS on `:18443` in the test stack (self-signed
cert + `verify=False` in httpx), so `SameSite=None; Secure` cookies ride the loopback and the
Playwright suite drives the real cookie path end-to-end. No Bearer opt-in fixture ever shipped.
CSRF and cookie-flag correctness are testable now — `test_csrf_surface.py` skips only because
the S-01 middleware itself is still open, not because the tests can't reach it.

The remaining open question is **S-26**: `deps.py:get_current_user` still accepts an
`Authorization: Bearer` header alongside the cookie, even though `grep -rn "Authorization"
frontend/src/` returns zero matches. No first-party client sends a Bearer token; the only
inbound `Authorization: Bearer` refs are outbound integrations (HubSpot / Salesforce / Monday /
Asana / Jira), and the SSE endpoint reads a `?token=` query param with its own inline
`jwt.decode` — it never touches `get_current_user`.

Fix is the one-line delete of the Bearer branch, sequenced **before S-01** so the CSRF
middleware only has to reason about the cookie path. Full argument + evidence in
`SECURITY_BACKLOG.md` under S-26.

---

## 5. Other harness debt (accepted, tracked)

| # | Compromise | Risk | Action |
| --- | --- | --- | --- |
| ~~H-1~~ | ~~`emergentintegrations==0.2.0` is a fresh-install blocker + shim in the test image~~ **CLOSED — F-01 (commit `9ba2368`, 2026-09-13).** `ai_service.py` now wraps the import in `try/except ImportError` and routes to the rule-based fallback when `_HAS_LLM = False`. Package removed from `backend/requirements.txt`; shim RUN block removed from `backend/Dockerfile.test`; test image rebuilt from scratch and confirmed booting cleanly with no `emergentintegrations` in `site-packages`. Regression guard: `backend/tests/test_f01_optional_import.py`. Post-fix baseline: `make test-backend` 315 passed / `make e2e` 13/13. | — | — |
| H-2 | `stripe-mock` has no healthcheck (`service_started` only) | Race on slow machines | Acceptable; `test_stripe_api_base_is_the_mock` catches it. |
| H-3 | `pytest-asyncio==1.4.0` (test image only). The original ask was to hard-pin to `1.2.0`, but 1.2.0 declares `pytest<9` and conflicts with the pinned `pytest==9.1.1` in `requirements.txt`. 1.4.0 is the earliest release that supports pytest 9. `pytest-cov==6.0.0` has the same story (5.x declares `pytest<9`). | Silent breakage on next pytest-asyncio / pytest-cov major bump | Kept as-is until we upgrade pytest itself. Revisit both pins on any pytest version bump. |
| H-4 | `asyncio_default_test_loop_scope = session` | Cross-test state leakage through the Motor client | Acceptable for now. Per-test DB drop still isolates data. Revisit if flakes appear. |
| H-5 | passlib/bcrypt 4.x warning noise | Cosmetic; will mask real warnings later | Pin `bcrypt<4` as its own small PR — the F-01 close didn't touch bcrypt, so this needs a dedicated fix. |
| H-6 | Legacy `test_iteration*.py`, `backend_test.py` excluded from `make test-backend` | Dead tests rot and confuse | Delete them when the section they cover is converted in 1b. Don't leave them lying around. |
| H-7 | `stripe-mock` returns canned fixtures | **Cannot test webhook signature verification (S-03) or the refund `payment_intent` path** | Money-path tests need locally-signed payloads with a test `STRIPE_WEBHOOK_SECRET`. Do not assume 1b covers money. |
| ~~H-8~~ | ~~`.env.test` values match code defaults exactly.~~ **CLOSED — F-11 (2026-09-05, commit `4a85b96`).** `.env.test` now seeds `REVISION_REVIEW_THRESHOLD=4` (non-default vs code default 3); `test_config.py` (Phase 1b step 6) asserts `settings.business_rules.revision_review_threshold == 4`, proving the config path is live. **Finding surfaced during the F-11 sweep:** changing 3→4 broke **zero** active tests, because the only ladder assertion in the repo is `test_iteration33_revisions.py:196` (`test_third_revision_triggers_under_review`) — which lives in the legacy `test_iteration*.py` suite explicitly excluded from `make test-backend` (per H-6). **The revision penalty ladder has no coverage in the active harness at all.** Phase 1b ordering therefore reorders: §12 (revision ladder) and §13 (dispute/fee) must come before §3/§6/§7/§8, so the ladder gains coverage before we depend on it for any other feature test. |
| H-9 | `clean_db` in `backend/tests/conftest.py` is autouse function-scoped: it drops + reseeds the shared Mongo before every test. Under the pytest.ini default `-n 2 --dist loadscope`, two workers hit the same backend and one worker's drop invalidates the other worker's live JWT for the ~5ms window before the reseed lands — non-deterministic 401 "User not found" flakes. Fix in place: `-n 0` on the Makefile invocation (pytest.ini documents `-n 0` as the sanctioned serial mode). | Test-suite serial execution as coverage grows. | Serial runtime exceeds 60 s. Then either per-worker DB namespacing (needs backend to switch DB by header — an app-level change, out of no-app-code-change scope) or a Makefile split into `test-backend-unit` (parallel; scanner/public-surface/csrf tests) and `test-backend-integration` (serial; smoke + §11 + future §XX). Interim mitigation: keep the serial suite small enough that runtime stays under a minute. |

---

## 6. What's next, in order

App is local-only, never deployed. Prod-verification steps and live-exploit hotfixes
(previously items 1 and 2) are not applicable — dropped from this list.

**Delivered since the previous revision** (2026-09-05 → 2026-09-13):
- ~~Doc-only ARCH.md fix (F-09)~~ CLOSED under F-11 — §6 no longer lists raw env var names.
- ~~Harness cookie-only fix~~ Done — backend serves HTTPS on `:18443` in the test stack,
  Playwright drives the browser cookie path end-to-end. Bearer opt-in fixture never shipped.
- ~~Phase 1b~~ Substantially done — see §1 for the section list.
- ~~S-25 verification~~ CLOSED 2026-09-06 as a scanner false positive; scanner blind
  spot filed and fixed as S-28.
- ~~Phase 1c~~ Done (v2). 13 specs green.
- ~~S-31~~ CLOSED 2026-09-07 (commit `0e5fd5a`) — logout cookie attribute-mismatch.
- **New capability**: hand-driven dev stack landed (`docker-compose.dev.yml` + `docs/LOCAL_SETUP.md`),
  parallel to the test stack, targeting real services.

**Still to go, in order:**

1. **S-26** — delete the `Authorization: Bearer` branch in `deps.py:get_current_user`. Small
   self-contained diff. Do this **before S-01** so the CSRF middleware only has to reason about
   the cookie path. Verified 2026-08-30 that no server-side code depends on inbound Bearer.
2. **S-01** — register the CSRF default-deny middleware. `security/csrf_exempt.yml` already
   lists the one legitimate exemption (Stripe webhook). Once this lands, remove the skip on
   `backend/tests/test_csrf_surface.py`.
3. **Phase 1d** — wire `security-scan`: pin gitleaks + bandit + pip-audit + semgrep into the
   Makefile target and CI. Add a GitHub Actions workflow (or equivalent) so `make verify` runs
   on every PR. Until then the two placeholder legs of `verify` (test-frontend, security-scan)
   silently pass.
4. **P0 fix loop, remaining**: `S-07` (token revocation + refresh rotation) → `S-03` (webhook
   idempotency + TOCTOU fix per S-03(a)(b)(c)) → `S-04` (HMAC + verify recompute) → `S-08`
   (rate limiting on auth surface) → `S-06` (envelope-encrypt third-party tokens at rest).
5. **P1 backlog** by number (`S-09`, `S-10`, `S-11`, `S-12`, `S-13`, `S-14`, `S-16`, `S-23`,
   `S-24`, `S-26` if not yet done). Notable: S-11 has three canary tests in
   `backend/tests/test_11_engagements.py::TestDeliverables*` that flip green when the
   `load_owned` helper lands.
6. ~~**F-01** — replace `emergentintegrations` top-level import in `ai_service.py` with an
   optional guard so a fresh `pip install -r backend/requirements.txt` succeeds outside the
   test image.~~ **DONE — commit `9ba2368` (2026-09-13).**
7. **F-03** — split `server.py` (currently 2,906 lines) by domain. Zero behaviour change, suite
   green. Prerequisite for the contractor split.
8. **Extract `atlas-core`**, publish the wheel, generate `atlas-contracts/openapi.json`, stand
   up the Prism mock. Then hire against a first work package (F-04 admin UI is the natural
   starting point).
9. **Cloud-storage integration** — the dev-stack storage-mock papers over the gap; production
   needs a real S3/R2/GCS/Supabase target behind the existing three-function
   `storage_client.py` shape. Neutral-tier, shareable as a backend plugin work package.

---

## 7. Standing rules

- App-code changes follow the CLAUDE.md working style: one backlog item per branch, failing
  test first, one domain per PR, `make verify` green before merge. The old "no app code
  before Phase 1b" freeze is lifted — Phase 1b landed and F-11/S-31 have already exercised
  the new normal.
- One backlog item per branch, per PR. Branch name = backlog id (e.g. `sec/S-26-drop-bearer`).
- Every new finding gets an ID in `SECURITY_BACKLOG.md` the day it's found.
- Every accepted compromise gets a row in §5 above with a named closing condition.
- Every closed item is struck through in `SECURITY_BACKLOG.md` (not deleted) with the fix
  commit sha, so `git blame` and future auditors can trace closures back to the change.
