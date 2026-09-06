# CONFIG_INVENTORY.md — every env read, catalogued

Phase 1 of F-11. Produced by grepping `os.environ` / `os.getenv` across `backend/`
and `process.env` across `frontend/src/`. Regenerate by re-running the same greps
against HEAD — nothing here is AST-derived, everything is line-anchored to the
paths listed.

- **Backend**: 49 read sites across 9 files → **30 distinct env vars**
  + 1 hardcoded literal (`RATE_DRIFT_THRESHOLD_PCT`, F-10 in SECURITY_BACKLOG.md)
  that logically belongs with the business-rule ladder but is not env-read today.
- **Frontend**: 13 read sites across 10 files → **2 distinct env vars**.
- **CRM / work-provider tokens** (HubSpot, Salesforce, Monday, Asana, Trello, Jira,
  ClickUp, SharePoint) are **per-row values in Mongo**, not env — nothing to move.
  See `crm_integrations.access_token` (per S-06) and `integration_tokens`.

---

## 1. Summary — variables grouped by owning service

| Service | Var count | Required at boot | Optional | Silent fallback / fail-open (targeted by F-11) |
| --- | --- | --- | --- | --- |
| Mongo | 2 | `MONGO_URL`, `DB_NAME` | — | — |
| Auth / JWT | 3 | `JWT_SECRET` | `ADMIN_EMAIL` | `ADMIN_PASSWORD` (S-20 — hardcoded `Admin@2026`) |
| Stripe | 2 | — | `STRIPE_WEBHOOK_SECRET` | `STRIPE_SECRET_KEY` (S-05 — falls back to `sk_test_emergent`) |
| Mail (Resend) | 2 | — | `RESEND_API_KEY`, `SENDER_EMAIL` | — (silent-fail no-op is intentional per CLAUDE.md landmine list) |
| Slack | 1 | — | `SLACK_WEBHOOK_URL` | — (silent-fail intentional) |
| Storage | 2 | — | — | `INTEGRATION_PROXY_URL` (S-27 — falls back to `integrations.emergentagent.com`) · `EMERGENT_LLM_KEY` borrowed as storage token (S-15) |
| LLM | 1 | — | `EMERGENT_LLM_KEY` | — (silent-fail intentional; but see S-15 coupling with storage) |
| Turnstile | 1 | — | — | `TURNSTILE_SECRET_KEY` (S-08 — fail-open when unset) |
| CORS | 1 | — | — | `CORS_ORIGINS` (S-02 — falls back to `"*"`) |
| Crypto / Signing | 2 | — | — | `REFUND_AUDIT_SIGN_SECRET`, `DRILL_SIGN_SECRET` (S-04-adjacent — hardcoded `jobatlas-*-v1` salts, nested fallback) |
| Public URLs | 3 | — | `APP_BASE_URL`, `PUBLIC_BASE_URL`, `PUBLIC_SITE_URL` | — |
| Business rules | 11 | — | all 11 have defaults matching FEATURES.md §12 | — (H-8: `.env.test` values match defaults exactly) |
| Business rules (F-10) | (+1) | — | — | `RATE_DRIFT_THRESHOLD_PCT = 15` **hardcoded** at `deps.py:153`, no env read today |
| Frontend | 2 | — | `REACT_APP_TURNSTILE_SITE_KEY` | `REACT_APP_BACKEND_URL` (F-08 — silent `"undefined/api"` when unset) |

**Total: 30 backend env vars + 1 hardcoded + 2 frontend = 33 config values.**

---

## 2. Backend — per variable, every read site

Columns:
- **Var** — the exact env key
- **file:line** — every read site
- **Current default** — literal fallback (`—` = hard-required, `KeyError` at import if unset)
- **Breaks when unset** — observable failure mode
- **Notes** — backlog id, quirks, cross-refs

### 2.1 Mongo

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `MONGO_URL` | `backend/deps.py:26` | — (KeyError) | Worker never ready at import | Motor client at `deps.py:33` |
| `DB_NAME` | `backend/deps.py:27` | — (KeyError) | Worker never ready at import | `client[DB_NAME]` at `deps.py:34` |

### 2.2 Auth / JWT / Admin seeder

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `JWT_SECRET` | `backend/deps.py:28` | — (KeyError) | Worker never ready at import | Used by `create_token` / `get_current_user` |
| `ADMIN_EMAIL` | `backend/server.py:2757` | `"admin@talenthub.io"` | Silent — brand-drift (not `geminista.com`) | S-20-adjacent (per PROJECT_STATUS.md §3) |
| `ADMIN_PASSWORD` | `backend/server.py:2758` | `"Admin@2026"` | Silent — hardcoded default seed shipped | **S-20** — F-11 removes default; seeder skips-with-WARN if unset |

### 2.3 Stripe

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `STRIPE_SECRET_KEY` | `backend/server.py:40` · `routes/projects.py:788,983,1020,1059,1103,1143` · `routes/revisions.py:594,712,759,769` | `"sk_test_emergent"` (server.py:40); `""` in projects.py; `None` in revisions.py | Silent 401s from Stripe on every call | **S-05** — 11 read sites across 3 files. F-11 makes required at boot and every call site reads `settings.stripe.secret_key` |
| `STRIPE_WEBHOOK_SECRET` | `backend/deps.py:30` | `""` | Webhook signature verification 400s at `server.py:562` | F-11 makes required (per S-05 fix scope) |

### 2.4 Mail (Resend)

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `RESEND_API_KEY` | `backend/mailer.py:13` | `""` | Silent — `mailer.py:24` sets `_resend = None`; every `send_email` returns `{"sent": False}` and logs `[mailer:noop]` | Intentional silent-fail per CLAUDE.md landmine list |
| `SENDER_EMAIL` | `backend/mailer.py:14` | `"onboarding@resend.dev"` | Wrong "from" address used | Resend's shared sandbox address |

### 2.5 Slack

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `SLACK_WEBHOOK_URL` | `backend/routes/projects.py:1122` | `None` | Silent — `_slack_notify` early-returns | Read via `import os` **inside the function**, not module-level. F-11 sweep replaces with `settings.slack.webhook_url` module-import |

### 2.6 Storage (S-15, S-27)

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `INTEGRATION_PROXY_URL` | `backend/storage_client.py:6` | `"https://integrations.emergentagent.com"` | Silent — all avatars, portfolio, dispute evidence, government ID route to 3rd-party host | **S-27** — F-11 makes required at boot |
| `EMERGENT_LLM_KEY` (storage-borrow) | `backend/storage_client.py:8` | `""` | `init_storage` raises `RuntimeError("EMERGENT_LLM_KEY missing")` at first upload (line 18-19) | **S-15** — F-11 introduces `STORAGE_TOKEN` (new required var), drops the RuntimeError, updates mock's init payload to expect `storage_token` |

### 2.7 LLM

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `EMERGENT_LLM_KEY` (LLM use) | `backend/ai_service.py:10` | `""` | Silent — `suggest_hourly_rate` returns rule-based fallback | Optional. S-15 coupling with storage broken by F-11 |

### 2.8 Turnstile (S-08)

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `TURNSTILE_SECRET_KEY` | `backend/routes/auth.py:63` | `None` | Silent — `_verify_turnstile` returns `True`; captcha bypassed | **S-08 (partial)** — F-11 makes conditionally required when `ENV=production`; keeps fail-open in dev but logs loudly (WARN) when path taken |

### 2.9 CORS (S-02)

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `CORS_ORIGINS` | `backend/server.py:2889` | `"*"` (split → `["*"]`) | Silent — but browser rejects credentialed requests to wildcard origins per CORS spec | **S-02 (partial)** — F-11 makes required non-empty list. S-02's full fix (explicit-origin allowlist validation) remains open |

### 2.10 Crypto / Signing (S-04)

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `REFUND_AUDIT_SIGN_SECRET` | `backend/routes/revisions.py:863` | Nested: falls through to `DRILL_SIGN_SECRET`, then to literal `"jobatlas-refund-v1"` | Silent — signature computable by anyone knowing the constant | **S-04 (partial)** — F-11 makes required (no fallback). S-04's full fix (switch to `hmac.new()` + verify-endpoint recompute) remains open |
| `DRILL_SIGN_SECRET` | `backend/routes/auth.py:664` · `backend/routes/revisions.py:864` (nested) | `"jobatlas-drill-v1"` | Silent — same forge risk | Both a standalone read (auth.py) and a fallback in the REFUND_AUDIT nested lookup. F-11 makes required |

### 2.11 Public URLs

| Var | file:line | Current default | Breaks when unset | Notes |
| --- | --- | --- | --- | --- |
| `APP_BASE_URL` | `backend/routes/auth.py:35,300` · `backend/routes/projects.py:365,1259` | `""` | Broken email verification links, broken PDF permalinks | Used to build outbound URLs in emails |
| `PUBLIC_BASE_URL` | `backend/routes/auth.py:678` · `backend/routes/revisions.py:952` | `""` | Broken QR-code deep links in signed PDFs | Distinct from APP_BASE_URL despite similar name — public site vs API |
| `PUBLIC_SITE_URL` | `backend/server.py:1400,1402,1527` · `backend/routes/marketplace.py:82` | `""` (with `X-Forwarded-*` derivation fallback in server.py) | Fallback to `X-Forwarded-Proto/Host` header. If neither set → empty `origin`, broken redirects | Distinct again — SPA origin |

### 2.12 Business rules (revision + refund ladder)

All defaults match FEATURES.md §12 ladder values verbatim. `.env.test` re-states each explicitly (H-8 caveat).

| Var | file:line | Default | Notes |
| --- | --- | --- | --- |
| `REVISION_REVIEW_THRESHOLD` | `revisions.py:29` | `3` | Under-review threshold |
| `REVISION_PENALTY_THRESHOLD` | `revisions.py:30` | `5` | Excessive-revisions threshold |
| `REVISION_DISPUTE_FEE_USD` | `revisions.py:31` | `49` | Dispute fee amount |
| `REVISION_VISIBILITY_PENALTY` | `revisions.py:32` | `20` | Visibility score penalty |
| `REVISION_RATE_NUDGE_PENALTY` | `revisions.py:33` | `10` (percent) | Rate bias nudge |
| `EMPLOYER_FLAG_UNIQUE_TALENTS` | `revisions.py:34` | `3` | Distinct-talents threshold |
| `EMPLOYER_FLAG_WINDOW_DAYS` | `revisions.py:35` | `60` | Sliding-window duration |
| `REVISION_RECOVERY_UNDER_REVIEW` | `revisions.py:38` | `3` | Clean approvals to lift under-review |
| `REVISION_RECOVERY_EXCESSIVE` | `revisions.py:39` | `5` | Clean approvals to lift excessive |
| `PROVEN_RELIABLE_DAYS` | `revisions.py:41` | `90` | Days without penalty |
| `REFUND_ALERT_THRESHOLD_PCT` | `revisions.py:480` | `20` | Rolling refund-rate alert |
| **F-10** `RATE_DRIFT_THRESHOLD_PCT` | `deps.py:153` | `15` **(hardcoded literal, no env read today)** | F-11 makes env-tunable in `BusinessRules` with default `15`. Closes F-10 |

---

## 3. Frontend — per variable, every read site

### 3.1 `REACT_APP_BACKEND_URL` (F-08 — silent `"undefined/api"` when unset)

10 read sites, 8 files. F-11 replaces all with `import { BACKEND_URL } from '@/config'` and adds a top-level assertion that throws + renders a visible boot-error banner when unset.

| file:line |
| --- |
| `frontend/src/lib/api.js:3` |
| `frontend/src/pages/Trust.jsx:253` |
| `frontend/src/pages/Invoices.jsx:41` |
| `frontend/src/pages/ProjectWorkspace.jsx:554` |
| `frontend/src/pages/Admin.jsx:1070` |
| `frontend/src/pages/EngagementDetail.jsx:321` |
| `frontend/src/pages/BrowseTalent.jsx:125,163` |
| `frontend/src/pages/TalentProfile.jsx:95,226,251` |
| `frontend/src/pages/TalentDashboard.jsx:60` |

### 3.2 `REACT_APP_TURNSTILE_SITE_KEY`

Single site, currently defaults to Cloudflare's public always-passes test key.

| file:line | Current default | Notes |
| --- | --- | --- |
| `frontend/src/pages/Register.jsx:11` | `"1x00000000000000000000AA"` (Cloudflare public test key) | Optional in F-11's `config.js`. Keep default to preserve local-dev ergonomics |

---

## 4. Cross-cutting observations

### 4.1 Silent-fallback sites F-11 targets (in one place, for cross-ref)

| ID | file:line | Fallback |
| --- | --- | --- |
| S-02 | `server.py:2889` | `CORS_ORIGINS` → `"*"` |
| S-04 | `revisions.py:863-864` | `REFUND_AUDIT_SIGN_SECRET` → `DRILL_SIGN_SECRET` → `"jobatlas-refund-v1"` |
| S-05 | `server.py:40` | `STRIPE_SECRET_KEY` → `"sk_test_emergent"` |
| S-08 | `auth.py:63` | `TURNSTILE_SECRET_KEY` unset → return `True` |
| S-15 | `storage_client.py:8` + `:18-19` | Storage borrows `EMERGENT_LLM_KEY`; refuses init when empty |
| S-20 | `server.py:2758` | `ADMIN_PASSWORD` → `"Admin@2026"` |
| S-27 | `storage_client.py:6` | `INTEGRATION_PROXY_URL` → `"https://integrations.emergentagent.com"` |
| F-08 | `lib/api.js:3` (+ 12 more sites) | `REACT_APP_BACKEND_URL` unset → `"undefined/api"` |
| F-10 | `deps.py:153` | `RATE_DRIFT_THRESHOLD_PCT` hardcoded to `15`, no env read at all |

### 4.2 F-09 name drift (documented in PROJECT_STATUS.md §3)

`.env.test` already uses the code-correct names (verified line-by-line above). The
drift lives in `ARCHITECTURE.md §6`, which F-11's step 7 fixes. Eight renames
(`REVIEW_FLAG_THRESHOLD` → `REVISION_REVIEW_THRESHOLD`, etc.) and five additions
(`APP_BASE_URL`, `PUBLIC_BASE_URL`, `PUBLIC_SITE_URL`, `INTEGRATION_PROXY_URL`,
`SENDER_EMAIL`).

### 4.3 `EMERGENT_LLM_KEY` — the double-duty coupling (S-15)

Currently read at **two independent sites**:
- `ai_service.py:10` → LLM suggested-rate API (optional, silent-fail is fine)
- `storage_client.py:8` → object-storage `/init` payload (**load-bearing** — refuses to init when empty)

F-11 introduces `STORAGE_TOKEN` as a distinct required var. `EMERGENT_LLM_KEY`
becomes purely optional and only read by `ai_service.py`. The storage mock
(`backend/tests/_storage_mock/app.py:39-45`) accepts any payload key today — F-11
updates it to expect `storage_token` in the init body so the API-shape check is
accurate. `.env.test` gains a `STORAGE_TOKEN=` line.

### 4.4 `STRIPE_SECRET_KEY` — 11 read sites, all patchable

Every `stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") ...` in
`server.py`, `routes/projects.py`, and `routes/revisions.py` becomes a single
`stripe.api_key = settings.stripe.secret_key` post-F-11. No behavioural change
because the value is required at boot.

### 4.5 `os` imported inside functions

`routes/projects.py:1120` does `import os` inside `_slack_notify`. Harmless
today, but the F-11 sweep replaces the env read and can drop the local `import
os` (module-level `from config import settings` covers it). Flag so the sweep
diff catches it.

### 4.6 Nested `os.environ.get(...)` fallback (`revisions.py:863-864`)

```python
salt = os.environ.get("REFUND_AUDIT_SIGN_SECRET",
                      os.environ.get("DRILL_SIGN_SECRET", "jobatlas-refund-v1")).encode()
```

Two-level fallback: primary → secondary env → hardcoded literal. F-11 splits
these into two independent required fields (`settings.crypto.refund_audit_secret`
and `settings.crypto.drill_secret`). Any code that today depends on the primary
falling through to the secondary must now provide the primary explicitly — flag
for the sweep; `.env.test` already sets both.

### 4.7 What F-11 does NOT read from env (per-row DB values, out of scope)

Per S-06, CRM and work-provider tokens (HubSpot, Salesforce, Monday, Asana,
Trello, Jira, ClickUp, SharePoint) are per-employer / per-user rows in Mongo:
`crm_integrations.access_token`, `integration_tokens`. No env vars, nothing to
centralise. The `IntegrationSettings` nested model in the F-11 plan is
therefore only a placeholder for future org-wide integration config — it starts
empty.

---

## 5. Config-inventory → config.py target shape (preview only; final design in step 2)

Groupings the inventory suggests, one nested `BaseModel` per service:

```
Settings
├── env: Literal["development", "test", "production"]   # gates conditional-required (S-08)
├── mongo:        MongoSettings          (MONGO_URL, DB_NAME)
├── stripe:       StripeSettings         (secret_key, webhook_secret)
├── mail:         MailSettings           (resend_api_key?, sender_email)
├── slack:        SlackSettings          (webhook_url?)
├── storage:      StorageSettings        (proxy_url, token)          # was EMERGENT_LLM_KEY — S-15
├── llm:          LLMSettings            (emergent_llm_key?)          # optional, silent-fail intentional
├── auth:         AuthSettings           (jwt_secret, turnstile_secret_key?*, admin_email, admin_password?**)
│                                        # * conditional-required if env=production
│                                        # ** never has a default; seeder skips-WARN if unset
├── crypto:       CryptoSettings         (refund_audit_secret, drill_secret)
├── urls:         UrlSettings            (app_base, public_base, public_site, cors_origins: list[str])
├── business_rules: BusinessRules        (11 revision-ladder fields + RATE_DRIFT_THRESHOLD_PCT for F-10)
└── integrations: IntegrationSettings    (empty for now; per S-06 tokens live in Mongo)
```

Frontend `src/config.js`:

```
export const BACKEND_URL = <required, throw + render banner if unset>;    // F-08
export const TURNSTILE_SITE_KEY = <optional, default = Cloudflare test key>;
```

---

## 6. Test-harness impact (informational — actioned in step 6)

- `.env.test` needs three additions:
  1. `STORAGE_TOKEN=<test-value>` (S-15)
  2. `ENV=test` (drives conditional-required for Turnstile per correction A)
  3. `REVISION_REVIEW_THRESHOLD=4` (H-8 non-default, closes H-8)
- `backend/tests/_storage_mock/app.py:39-45` updates the init payload field name
  from `emergent_key` to `storage_token` (both sides in the same PR).
- `backend/tests/test_config.py` (new file) — per step 6 of the plan.
