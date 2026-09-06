# VALIDATION_PROCESS.md — running this repo through Claude Code end to end

You have three excellent docs and zero tests. That is the whole problem. The docs describe
~23 feature areas and 150+ endpoints that nobody can prove still work after a change.
The goal of this process is to convert `FEATURES.md` into executable tests, then let Claude Code
fix against a green/red signal instead of vibes.

---

## Phase 0 — make the repo self-describing (½ day, do it once)

Drop into the repo root:

```
CLAUDE.md                  # constitution — attached
SECURITY_BACKLOG.md        # ranked issues — attached
.claude/commands/          # slash commands — below
Makefile                   # verify / seed / e2e targets
```

Then:

```bash
claude
> Read CLAUDE.md, ARCHITECTURE.md, FEATURES.md, SECURITY_BACKLOG.md.
> Produce docs/ENDPOINT_INVENTORY.md: every route, from a real AST parse of backend/
> (not from the docs), with method, path, file:line, auth dependency, and the scope or
> role check found inside the handler body. Flag every route where you cannot find any
> authorization check. Do not modify any source file.
```

That inventory is your baseline. Diff it against `FEATURES.md` — the delta is your first bug list.

---

## Phase 1 — build the harness before fixing anything (2–3 days)

### 1a. Deterministic environment

```bash
# docker-compose.test.yml: mongo:7 + backend + frontend + stripe-mock
make up-test
```

Requirements:
- Mongo runs in a throwaway container, dropped between suites.
- `stripe-mock` (or Stripe CLI in test mode) replaces live Stripe.
- A `seed.py` that creates: 1 admin (all scopes), 1 scope-less admin, 2 talents, 2 employers,
  1 engagement, 1 deliverable, 1 project + milestone + invoice, 1 grievance. Idempotent.
- `.env.test` with every var set — including the ones that currently fail open
  (`TURNSTILE_SECRET_KEY`, `REFUND_AUDIT_SIGN_SECRET`, `CORS_ORIGINS`).

### 1b. Turn FEATURES.md into tests

`FEATURES.md` already has numbered manual test steps per section. Convert them section by section —
this is the highest-leverage Claude Code task in the whole project.

```
> Read FEATURES.md section 11 (Engagements + contract signing + deliverables).
> Write backend/tests/test_11_engagements.py using pytest + httpx.AsyncClient against the
> test container. One test per numbered manual step. Use the seeded fixtures in
> backend/tests/conftest.py. For every endpoint in the section's table, also write a
> negative test: unauthenticated, wrong role, and cross-tenant (another user's resource id).
> Do not modify application code. If a test fails, leave it failing and add it to
> test_result.md status_history with agent "testing".
```

Run that prompt 23 times, once per section, in separate sessions. Budget one section per session —
context stays clean and each PR is reviewable.

Coverage targets before you write a single fix:
| Layer | Target |
| --- | --- |
| Auth + authz negative tests | 100% of routes |
| Money paths (§10, §14, §17) | 100%, incl. webhook replay + double-credit |
| Business rule ladder (§12, §13) | every threshold + every recovery transition |
| Everything else | happy path + one failure path |

### 1c. Frontend E2E

```
> Using FEATURES.md sections 3, 6, 7, 8, 11, write Playwright specs in frontend/e2e/.
> Cover: register both roles, login, shortlist, EOI, engagement sign, deliverable submit,
> revision request, dispute. Use data-testid attributes; add them where missing.
```

### 1d. Gate it

```make
verify: lint typecheck test-backend test-frontend e2e security-scan
security-scan:
	gitleaks detect --no-git
	bandit -r backend/ -ll
	pip-audit && yarn npm audit --severity high
	semgrep --config p/owasp-top-ten --config p/python backend/
```

CI must run `make verify` on every PR. Nothing merges red.

---

## Phase 2 — the fix loop

One backlog item per session. The prompt shape that works:

```
> Fix S-01 (CSRF) from SECURITY_BACKLOG.md.
> Constraints from CLAUDE.md apply — read it first.
> Steps, in order:
>   1. Write backend/tests/test_sec_01_csrf.py proving the hole exists today (cross-origin
>      POST with a valid cookie succeeds). Run it. It must PASS before the fix.
>   2. Implement the fix as FastAPI middleware in backend/middleware/csrf.py. Do not edit
>      route handlers.
>   3. Invert the test: cross-origin POST now 403, same-origin with X-CSRF-Token 200.
>   4. Update frontend/src/lib/api.js to attach the header.
>   5. Run make verify. All 23 feature suites must stay green.
>   6. Append to test_result.md per its protocol. Mark S-01 CLOSED in SECURITY_BACKLOG.md.
> Show me the diff before writing anything to disk.
```

Rules that keep this from going sideways:
- **Never** let a single session fix more than one backlog item.
- **Never** let it refactor and fix in the same PR. `F-03` (splitting `server.py`) is its own PR
  with zero behaviour change, proven by the test suite passing untouched.
- If a fix requires editing more than ~5 files, stop and re-scope.
- Run `/security-sweep` (below) after each P0 merge to check nothing regressed.

Recommended order: **S-05 → S-02 → S-01 → S-07 → S-03 → S-04 → S-08 → S-06** then P1 by number.
(Config hard-fails first, because they make every later test honest.)

---

## Phase 3 — standing commands

Put these in `.claude/commands/`.

### `.claude/commands/validate-e2e.md`
```
Run the full validation sweep. Do not modify source.
1. make up-test && make seed
2. Run backend/tests/ and frontend/e2e/. Capture failures.
3. For each failure: classify as (a) genuine regression, (b) stale test vs intentional
   behaviour change, (c) environment/flake. Cite file:line evidence for each classification.
4. Cross-check the live route table against FEATURES.md; report routes present in code but
   absent from the doc, and vice versa.
5. Write the result to test_result.md following the protocol block in that file, agent "testing".
6. Output a ranked fix list. Do not fix anything.
```

### `.claude/commands/security-sweep.md`
```
Audit only, no edits. For the paths I name (or all of backend/routes/ if none):
1. Every route: is there an auth dependency, a role check, AND a resource-ownership check?
   Table the answer. Missing ownership check = finding.
2. Every Mongo query built from user input: can a dict/operator be injected ($ne, $gt, $where)?
3. Every response body: does it leak password_hash, tokens, _id, or another tenant's data?
4. Every secret read from env: is there a fallback default? Fallbacks are findings.
5. Every sync network/PDF call inside async def.
6. Every unbounded find()/to_list() without a cap.
Output a table: severity, file:line, exploit sketch, one-line fix. Append new items to
SECURITY_BACKLOG.md with fresh IDs. Do not duplicate existing IDs.
```

### `.claude/commands/money-audit.md`
```
Trace every code path that can change users.hours_balance, project_milestones.status,
project_invoices.status, or grievances.dispute_fee.payment_status. For each: what triggers it,
what guards idempotency, what happens on partial failure, and whether Stripe would retry.
Produce a state machine per money object. Flag any path where Stripe returns success but the
DB is not updated, or vice versa. No edits.
```

### `.claude/commands/feature-parity.md`
```
For FEATURES.md section $ARGUMENTS: verify every endpoint in the table exists at the stated
file:line, every frontend entry point exists, and every manual test step is covered by an
automated test. Report drift. Update FEATURES.md line references if they moved. No behaviour changes.
```

---

## Phase 4 — keep it flawless

- Every PR runs `make verify` + `/security-sweep` on the changed paths.
- Weekly: `/validate-e2e` on `main`.
- Monthly: rotate secrets, `pip-audit` + `yarn audit`, review `audit_log` for unexpected admin actions.
- Before any release: full suite + a Stripe test-mode purchase, refund, and webhook replay by hand.
