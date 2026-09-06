# CONTRACTOR_SPLIT.md — hiring without handing over the business

Right now the answer to "can I give a contractor part of this?" is **no**: `server.py` is 2,892
lines containing auth, Stripe, pricing constants, the penalty-ladder rules, the curated-talent
list, and the admin seeder in one file. Any contractor who touches anything sees everything.

The fix is not access control. It is **architecture**. You make the crown jewels a dependency
rather than a directory.

---

## What is actually secret

Be honest about this first — it changes what you have to protect.

| Tier | Contents | Share? |
| --- | --- | --- |
| **Crown jewels** | Penalty/recovery ladder + thresholds (§6), pricing/`PACKAGES`, commission + payout math, `_CURATED_TALENT`, CRM sync logic, Stripe account wiring, admin scope model | Never |
| **Sensitive** | Auth, `deps.py`, webhook handler, encryption/KMS, refund + audit-signature paths | Never |
| **Neutral** | Projects workspace, RACI/variance/risks, calendar, referrals, SEO pages, work-provider adapters, the entire React SPA, native shell | Shareable per work package |
| **Public anyway** | API shape (the SPA reveals it), UI, copy | Already public |

Realistically the moat is the **rules + data + Stripe account**, not the CRUD. Protect the rules
absolutely; be pragmatic about the rest.

---

## Target structure

```
atlas-core/            PRIVATE — never shared with any contractor
  deps.py, auth, payments, webhook, rules/ (penalty ladder, pricing, commission),
  crypto/, admin scopes, seeder
  → published as a private wheel: atlas-core==0.x  (CodeArtifact / GH Packages / Gemfury)

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

`F-03` in the backlog (splitting `server.py`) is the prerequisite for all of this. Do it before
you hire, not after.

---

## The three sharing patterns

### 1. Frontend / mobile contractor → give them the contract, not the backend
They get `atlas-frontend` + `atlas-contracts`. They run `docker compose -f docker-compose.mock.yml up`
and develop against a Prism mock generated from your OpenAPI spec. They never receive backend source,
never receive a DB, never receive an API key. Their PR is validated by your Playwright suite against
the real backend in **your** CI.

This is the cleanest split and covers most hires. The SPA is ~all of the visible product and none of
the moat.

### 2. Backend contractor → give them a plugin repo + the core as a wheel
Example work package: "build the Scheduler admin tab and the missing `/admin/*` UI endpoints" (F-04).

```
atlas-plugin-scheduler/
  pyproject.toml         → atlas-core==0.4.2 (from your private index, read-only token)
  src/scheduler/routes.py
  tests/
  docker-compose.yml     → mongo + core (installed as a wheel, not source)
```

They import `require_scope("superadmin")`, `db`, `api`. They can call the rules; they cannot read
them. Wheels can be shipped as compiled bytecode if you want an extra layer, though treat that as
friction, not security.

### 3. Full-trust senior hire → full repo, but only after F-03
Some work (auth, payments, the rules engine) genuinely cannot be split. For that person, use an NDA
and controls rather than partition. Do not try to fake a split there — you will ship a worse product.

---

## Non-negotiable controls, whichever pattern

| Control | Detail |
| --- | --- |
| Repo access | Per-repo, read + PR only. No org-wide access. No `main` push. `CODEOWNERS` on `atlas-core` = you. |
| Secrets | Contractor never gets prod or even staging secrets. Their compose file uses generated local ones. Stripe = test mode with a restricted key, or the mock. |
| Data | Synthetic seed only. Never a prod dump — you hold government IDs, reference-check emails, and CRM bearer tokens. A prod dump to a contractor is a reportable breach. |
| Environments | Ephemeral preview env per PR, torn down on merge. No standing access. |
| CI | Contractor's CI runs tests; **your** CI runs `make verify` + `/security-sweep` and holds the deploy keys. |
| Scope | Written work package: the FEATURES.md section, the acceptance tests, the definition of done from CLAUDE.md. Paid against tests passing. |
| Legal | NDA + IP assignment signed before repo invite. Contractor-owned-by-default is the default in many jurisdictions — assign it explicitly. |
| Offboarding | Same-day: revoke repo, revoke package-index token, rotate any shared secret, bump `token_version` on their accounts, audit `audit_log`. |

---

## Sequence

1. Land P0 security fixes (`S-01`…`S-08`). Don't invite anyone into a CSRF-open codebase.
2. Land `F-03`: split `server.py` by domain, zero behaviour change, suite green.
3. Extract `atlas-core` (rules + auth + payments + crypto) and publish the wheel.
4. Generate `openapi.json` into `atlas-contracts`; stand up the Prism mock.
5. Write the first work package (I'd start with F-04, the missing admin UI — neutral, self-contained,
   well-specified in FEATURES.md).
6. Hire against that package. Evaluate on the PR, then widen scope.

---

## Work packages ready to hand out today

| Package | Source of truth | Tier | Pattern |
| --- | --- | --- | --- |
| Missing admin UI: Scheduler tab, rate-nudge trigger, scan-overdue, save-as-template | F-04, FEATURES.md §21 | Neutral | Frontend + contracts |
| Playwright E2E suite for §3, 6, 7, 8, 11 | VALIDATION_PROCESS.md 1c | Neutral | Frontend |
| Capacitor store submission: icons, splash, screenshots, push endpoint | NATIVE_APP_GUIDE.md | Neutral | Mobile |
| Work-provider adapters → async httpx + retries + real error surfacing | S-13, `work_integrations.py` | Neutral | Backend plugin |
| Mongo indexes + pagination caps on all list endpoints | S-12 | Neutral | Backend plugin |
| Projects workspace polish (variance, risks, RACI tabs) | FEATURES.md §16 | Neutral | Frontend |
| Anything in auth, payments, revisions, admin scopes, `deps.py` | — | Crown/Sensitive | **You only** |
