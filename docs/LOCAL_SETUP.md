# LOCAL_SETUP.md — hand-driven dev stack

A running local copy of Job Atlas that you click through in a browser with
your own credentials. Parallel to the test stack (`docker-compose.test.yml`
+ mocks); different compose project, different ports, different Mongo.

**Never enter production credentials into this stack.** Stripe stays in
test mode. Any `sk_live_…` value would let hand-driven checkouts hit real
cards.

---

## Prerequisites

- **Docker Desktop** (or any Docker with Compose v2). Verify: `docker compose version`.
- **Stripe CLI** for webhook forwarding: <https://docs.stripe.com/stripe-cli> — `brew install stripe/stripe-cli/stripe` on macOS.
- A GitHub-signup-tier account with Stripe, Resend, and (optionally) Cloudflare. Free tier is enough for all of them.
- **openssl** on your PATH (already installed on macOS/Linux) — used to generate secrets.

---

## Step 1 — bootstrap the env file

```
cp .env.dev.example .env.dev
$EDITOR .env.dev
```

`.env.dev` is git-ignored (see `.gitignore`) — only `.env.dev.example` is
tracked. Every value in the example is a placeholder; replace the ones marked
`REPLACE_…` before booting.

Quick fills you can do without leaving the terminal:

```
openssl rand -hex 32   # JWT_SECRET
openssl rand -hex 32   # REFUND_AUDIT_SIGN_SECRET
openssl rand -hex 32   # DRILL_SIGN_SECRET  (must differ from above)
```

The rest come from the service dashboards below.

---

## Step 2 — sign up for the real services

Every row below tells you the signup URL, exactly which value to copy, and
which env var in `.env.dev` it sets. Skip a row only if the notes explicitly
say "optional".

### Stripe (test mode — required for anything money-related)

| Value | Where to get it | Env var |
| --- | --- | --- |
| Secret key | <https://dashboard.stripe.com/test/apikeys> — "Secret key" starting with `sk_test_`. | `STRIPE_SECRET_KEY` |
| Webhook signing secret | Output of `stripe listen` — see below. Starts with `whsec_`. | `STRIPE_WEBHOOK_SECRET` |

First-time Stripe CLI setup:

```
stripe login                # opens a browser, links CLI to your Stripe account
```

Then, in a terminal you keep open for the whole dev session:

```
stripe listen \
  --forward-to https://localhost:8443/api/stripe/webhook \
  --skip-verify
```

`--skip-verify` is because the backend serves a self-signed cert on
`:8443` (see Step 3). The first line of `stripe listen` output prints:

```
> Ready! Your webhook signing secret is whsec_abc123…
```

Paste that value into `STRIPE_WEBHOOK_SECRET` in `.env.dev` and run
`make down-dev && make up-dev` so the backend picks it up. The secret
rotates every time you start `stripe listen`, so expect to redo this once
per dev session.

Test-mode card numbers (Stripe never charges these):
<https://docs.stripe.com/testing#cards>. `4242 4242 4242 4242` with any
future date + any CVC + any ZIP works for the standard flow.

### Resend (outbound email — verification, notifications)

| Value | Where to get it | Env var |
| --- | --- | --- |
| API key | <https://resend.com/api-keys> — "Create API Key", full access, copy the `re_…` value once (you can't view it again). | `RESEND_API_KEY` |
| Verified sender | <https://resend.com/domains> — add a domain, add the DNS records Resend prints, wait for status "Verified". Then use `noreply@<your-domain>` (or any address at that domain). | `SENDER_EMAIL` |

Leave `RESEND_API_KEY` blank if you don't want to hook up email — the
mailer silently no-ops (logs `[mailer:noop]`) and every send returns
`sent=False`. Registration still works; the verification link just never
arrives. Resend refuses unverified senders with a 403; if you set the key
without verifying, registration fails at the send.

### Cloudflare Turnstile (captcha on register/login)

Two paths — either works in dev:

**Path A — Cloudflare's published test keys (recommended for dev, zero signup):**

```
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA
REACT_APP_TURNSTILE_SITE_KEY=1x00000000000000000000AA   # in docker-compose.dev.yml default
```

The site key `1x00…AA` always renders; the secret `1x00…000AA` always
returns success from Cloudflare's verify endpoint. No account needed. This
is what the example file ships with.

**Path B — a real Turnstile site (only if you want to exercise the actual
verification path):**

| Value | Where to get it | Env var |
| --- | --- | --- |
| Site key + Secret key | <https://dash.cloudflare.com> → Turnstile → "Add site". Hostname: `localhost`. Widget mode: Managed. Copy both keys from the site's detail page. | `TURNSTILE_SECRET_KEY` (backend) + `REACT_APP_TURNSTILE_SITE_KEY` (frontend — override in `.env.dev` and it flows through compose interpolation). |

### MongoDB — pick one

**Option A — the bundled container (recommended for dev, zero signup):**

Leave `MONGO_URL=mongodb://mongo:27017` and `DB_NAME=atlas_dev` as they
appear in the example. Data lives in a named volume (`atlas-dev-mongo`)
and survives `make down-dev`. `make down-dev-hard` nukes it.

Inspect the DB from your host: `mongosh mongodb://localhost:27017/atlas_dev`.

**Option B — MongoDB Atlas free tier (M0):**

1. Sign up at <https://www.mongodb.com/cloud/atlas/register>.
2. Create an M0 cluster (free forever).
3. Add your IP to the access list (Network Access → Add IP).
4. Create a DB user (Database Access → Add New Database User).
5. Cluster → Connect → Drivers → copy the SRV connection string.

```
MONGO_URL=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority
DB_NAME=atlas_dev
```

The bundled `mongo` container still starts (harmless, no one connects) —
you can trim it from `docker-compose.dev.yml` later if you want.

### Storage — no signup, mock is bundled

`backend/storage_client.py` speaks a proprietary API shape (an "emergent"
storage proxy), not S3/R2/GCS/Supabase. No real cloud-storage integration
is wired today — tracked in the backlog.

For dev, `docker-compose.dev.yml` runs a local in-memory `storage-mock`
container (source: `backend/tests/_storage_mock/app.py`). Uploads never
leave your laptop; they vanish when the container restarts. Perfect for
hand-driving. **Do not point anything shared at this.**

If you need real cloud storage before the backlog item lands, wrap
`backend/storage_client.py`'s three functions (`init_storage`, `put_object`,
`get_object`) around your provider's SDK — same input/output shape, same
tests should still pass.

### Slack, LLM — optional

- `SLACK_WEBHOOK_URL`: leave blank. Ops notifications silently no-op —
  `routes/projects.py::_slack_notify` early-returns.
- `EMERGENT_LLM_KEY`: leave the placeholder. `ai_service.py`'s rate-suggestion
  path wraps the LLM call in a `try/except` and falls back to rule-based
  numbers, so a bad key never breaks a flow.

---

## Step 3 — boot the stack

```
make up-dev
```

First run rebuilds the two shared images (`backend/Dockerfile.test`,
`frontend/Dockerfile.test`) — takes 2–3 minutes. Subsequent boots are
seconds. Target refuses to run if `.env.dev` is missing.

When healthy:

- **Frontend**: <http://localhost:3000>
- **Backend**: <https://localhost:8443> (self-signed cert — see below)
- **Mongo**: `mongodb://localhost:27017/atlas_dev` for `mongosh`

**One-time cert trust.** The backend serves HTTPS with a self-signed
certificate (SameSite=None cookies require Secure, which requires HTTPS).
The first time the SPA calls the backend, the browser blocks the request
with `ERR_CERT_AUTHORITY_INVALID`. Visit `https://localhost:8443/api/marketplace/industries`
directly, click "Advanced" → "Proceed to localhost", and the trust
sticks for the session. The SPA works from that point on.

Follow logs:

```
make dev-logs
```

Stop everything (mongo volume preserved so accounts survive):

```
make down-dev
```

Full nuke (drops the mongo volume too — every hand-entered account gone):

```
make down-dev-hard
```

---

## Step 4 — seed personas so you have accounts to log in as

```
make seed-dev
```

Idempotent — safe to run repeatedly. Inserts the same fixtures the test
stack uses, mapped by `backend/tests/seed.py`.

### Personas

Every login below uses password **`Passw0rd!`** (from `FIXTURE_PASSWORD`
in `backend/tests/seed.py` — treat it as fixture data, not a credential).

| Email | Password | Role | Notes |
| --- | --- | --- | --- |
| `admin-all@atlas-test.example.com` | `Passw0rd!` | admin | Every scope (support/finance/moderation/customization/superadmin). |
| `admin-noscope@atlas-test.example.com` | `Passw0rd!` | admin | `admin_permissions=[]` — for testing S-09 (role check without scope). |
| `talent-clean@atlas-test.example.com` | `Passw0rd!` | talent | Verified, no flags. Use for the golden-path flows. |
| `talent-flagged@atlas-test.example.com` | `Passw0rd!` | talent | `revision_count=5`, `excessive_revisions=True`, `visibility=80`. Use for §12 revision-ladder scenarios. |
| `employer-card@atlas-test.example.com` | `Passw0rd!` | employer | `hours_balance=1000`, `stripe_payment_method_id` set. Use for purchase / assemble / broadcast flows. |
| `employer-nocard@atlas-test.example.com` | `Passw0rd!` | employer | `hours_balance=100`, no card on file. Use for "add card first" edge cases. |

Seeded objects (attached to the personas above):

| ID | What | Owner(s) |
| --- | --- | --- |
| `seed-engagement-signed` | Engagement, contract signed by both parties. | `employer-card` ↔ `talent-clean` |
| `seed-deliverable-submitted` | One submitted deliverable on that engagement. | `talent-clean` submitted → `employer-card` reviews |
| `seed-project-open` + `seed-milestone-1` + `seed-invoice-open` | Open project with one issued, unpaid invoice. | `employer-card` |
| `seed-grievance-open` | Open revision-dispute grievance; dispute fee unpaid. | `employer-card` |

### What to click to test what

- **Login flow / logout** — sign in as any persona at `/login`. `admin-all` lands on `/` (doesn't auto-redirect to `/admin` — this is F-14 in `SECURITY_BACKLOG.md`); talents land on `/talent`, employers on `/employer`.
- **Purchase hours** — `employer-card` → `/employer/purchase` → click any package's "Buy". Stripe Checkout opens in test mode. Card `4242 4242 4242 4242`, any future date, any CVC. After paying, Stripe fires `checkout.session.completed` — `stripe listen` forwards it to the backend, hours land in your balance. If nothing happens, check the `stripe listen` terminal for a webhook signature error (usually means `STRIPE_WEBHOOK_SECRET` in `.env.dev` doesn't match the current `stripe listen` run — rotate + `make down-dev && make up-dev`).
- **Marketplace / shortlist / broadcast** — `employer-card` → `/hire/react-developers` → click a talent card → "Shortlist" in modal → "Send broadcast" from the shortlist. Also `employer-card` → `/employer/browse` for the raw list (currently no shortlist button on that page — filed under Phase 1c v2 notes in `test_result.md`).
- **EOI (Expression of Interest)** — `talent-clean` → `/talent/eoi` → fill for `employer-card` → submit. Then log in as `employer-card` → `/employer/eois` → accept.
- **Engagement sign / deliver / approve** — after accepting an EOI or via `seed-engagement-signed`. Employer signs contract → talent signs → talent submits deliverable → employer approves.
- **Revision cycle** — on an approved deliverable, employer requests revision → talent resubmits. Excessive revisions trigger `talent-flagged`-style state.
- **Grievance / refund** — `seed-grievance-open` is pre-created for `employer-card`; visit `/employer/grievances` to walk it forward. Dispute-fee Stripe Checkout uses the same test cards.
- **Admin console** — sign in as `admin-all`, then manually visit `/admin` (no auto-redirect — F-14).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `make up-dev` says ".env.dev not found" | You skipped Step 1. | `cp .env.dev.example .env.dev` and edit. |
| Backend container restart-loops with `Config error — required environment variables missing or invalid` in logs. | A `REPLACE_…` value from the example wasn't replaced, or a required var is blank. | `make dev-logs` → the aggregated error lists every missing var. Fix in `.env.dev`, then `make down-dev && make up-dev`. |
| Frontend loads but every API call is `net::ERR_CERT_AUTHORITY_INVALID`. | You haven't accepted the self-signed cert yet. | Visit `https://localhost:8443/api/marketplace/industries` in the same browser, click Advanced → Proceed. |
| Stripe Checkout completes but hours never land. | `STRIPE_WEBHOOK_SECRET` in `.env.dev` doesn't match the current `stripe listen` output (it rotates per session). | Copy the `whsec_…` from `stripe listen`'s startup banner into `.env.dev`, then `make down-dev && make up-dev`. |
| Registration hangs, no verification email. | `RESEND_API_KEY` blank (mailer no-ops) or `SENDER_EMAIL` is not a verified sender on your Resend domain. | Verify the domain at <https://resend.com/domains>, use an address at that domain in `SENDER_EMAIL`. |
| "Turnstile failed" on register/login. | You set `TURNSTILE_SECRET_KEY` to a real key but left `REACT_APP_TURNSTILE_SITE_KEY` on the default test site key, or vice-versa — mismatched pair. | Both must be from the same source: both test keys, or both from your Turnstile site. |
| Ports 3000 / 8443 / 27017 conflict with something you were already running. | Local yarn dev server / another mongo. | Stop the conflicting process, or edit the `ports:` sections in `docker-compose.dev.yml`. |
| Test stack + dev stack collide. | They can't — separate compose projects (`atlas-test` vs `atlas-dev`), separate networks, distinct ports. If you see collisions someone edited the port map. | Reset with `make down-test && make down-dev`. |

---

## What's different from the test stack

| Aspect | test stack | dev stack |
| --- | --- | --- |
| Compose project name | `atlas-test` | `atlas-dev` |
| Mongo storage | tmpfs (wiped every `up-test`) | named volume (persists) |
| Stripe | `stripe-mock` container, `STRIPE_API_BASE` overrides SDK | real `api.stripe.com` (test mode), `stripe listen` forwards webhooks |
| Backend port (host) | `18443` | `8443` |
| Frontend port (host) | `13000` | `3000` |
| Uvicorn `--reload` | off (determinism) | on (edit backend/, container picks up) |
| Frontend HMR bind-mounts | none (bundle stable) | `frontend/src`, `public`, config files |
| Coverage tracing | on (`COVERAGE_PROCESS_START` set) | off |
| Turnstile | published test keys (always pass) | your choice (test keys or real dev-scope site) |

Both stacks share:

- The two Dockerfiles (`backend/Dockerfile.test`, `frontend/Dockerfile.test`) — dev-safe because the two test-only injections (`STRIPE_API_BASE`, `COVERAGE_PROCESS_START`) are gated on env vars that dev leaves unset.
- The seed script (`backend/tests/seed.py`) — same personas, same passwords.
- The `storage-mock` container — no real cloud storage is wired yet.
