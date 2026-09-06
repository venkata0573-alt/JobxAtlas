# UNDOCUMENTED_ROUTES.md — triage of §4a + §4d from ENDPOINT_INVENTORY.md

Snapshot as of `docs/ENDPOINT_INVENTORY.md` regeneration on 2026-09-06
(commit `f23e075` — post-S-28 scanner fix). Regenerate the underlying
inventory with `python docs/scripts/render_inventory.py` and re-run this
triage if the counts drift.

Methodology:
- **§4a "only in code" (41 routes)**: for each, `grep -rn` the SPA path
  under `frontend/src/**/*.{js,jsx}` with the `/api` prefix stripped
  (axios's `baseURL` adds it), then classify against the three buckets
  the F-11 task defined — **(a) undocumented feature**, **(b) internal /
  admin-no-UI (F-04 candidate)**, **(c) dead code**.
- **§4d "auth unknowns" (23 routes)**: read the FEATURES.md claim
  verbatim, the code-enforces column verbatim, and give the verdict a
  human eye would give — **match**, **mismatch**, or **still-unknown**.
  Group by claim shape; a shape that accounts for ≥3 routes is a
  candidate for another scanner fix in the same shape as S-28.
- **Cross-check**: any route in §4a whose auth column is `PUBLIC (no
  auth)` is called out first — that combination (unauthenticated **and**
  undocumented) is exactly how S-23 was found.

No code changes. No test additions. This is a documentation + backlog
delta only.

---

## 1. Cross-check — unauth AND undocumented

**8 routes in §4a have `PUBLIC (no auth)` in the actual-authz column.**
All 8 are already listed in `security/public_routes.yml:intentional_public`
(verified — the top-of-doc "36 unauth" count is unchanged, and §2b's
"surprising" bucket stays at 3, none of which came from §4a). No new
S-23-style finding.

| Method | Path | file:line | Reason it's public |
| --- | --- | --- | --- |
| GET | `/api/customization/public` | routes/admin.py:452 | Read-only tenant customization surface. Zero SPA callers — see §2 row for the deletion note. |
| GET | `/api/legal` | server.py:2649 | Legal-page content service, hit by the /legal SPA route + email footers. |
| POST | `/api/newsletter/signup` | server.py:2226 | Marketing signup form (SkillLanding page). |
| GET | `/api/pricing/tiers` | server.py:2091 | Public pricing page config. **F-04 dead-code candidate** — SPA uses `/api/pricing`, not `/tiers`. |
| POST | `/api/pricing/quote` | server.py:2103 | External quote API. **F-04 dead-code candidate** — no SPA caller. |
| GET | `/api/seo/skills` | routes/marketplace.py:29 | SEO landing-page enumeration. Called by crawlers, not the SPA. |
| GET | `/api/seo/city-skills` | routes/marketplace.py:34 | Same — SEO index for SkillLanding. |
| GET | `/api/sitemap.xml` | routes/marketplace.py:80 | Search-engine sitemap. |

**None promoted to a new backlog item.** Three of the eight (`/customization/public`,
`/pricing/tiers`, `/pricing/quote`) get flagged for F-04 (below) but on
the "unused endpoint" axis, not on "unauth surprise."

---

## 2. §4a triage — 41 routes in code, missing from FEATURES.md tables

Column key:
- **Caller**: frontend file(s) that hit the path (grep result, `/api`
  prefix stripped). `— none` = no SPA caller found.
- **Class**: **(a)** undocumented feature — write a FEATURES.md row for
  it in the named section; **(b)** internal / admin-no-UI — F-04
  candidate (endpoint exists but no UI trigger); **(c)** dead code — no
  caller anywhere, delete.

| Method | Path | file:line | Caller | Class | Where in FEATURES.md |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/accounts` | server.py:2572 | pages/Accounts.jsx · components/Header.jsx | **(a)** | §22 Integrations (extend "Work + CRM" table with the connected-accounts list) |
| GET | `/api/accounts/providers` | server.py:2566 | pages/Accounts.jsx | **(a)** | §22 Integrations |
| POST | `/api/accounts/connect` | server.py:2578 | pages/Accounts.jsx | **(a)** | §22 Integrations |
| DELETE | `/api/accounts/{account_id}` | server.py:2603 | pages/Accounts.jsx | **(a)** | §22 Integrations |
| GET | `/api/admin/bank-transfers` | routes/admin.py:47 | pages/Admin.jsx | **(a)** | §21 Admin panel (Finance tab) |
| POST | `/api/admin/bank-transfers/{payment_id}/approve` | routes/admin.py:57 | pages/Admin.jsx | **(a)** | §21 Admin panel (Finance) |
| POST | `/api/admin/bank-transfers/{payment_id}/reject` | routes/admin.py:73 | pages/Admin.jsx | **(a)** | §21 Admin panel (Finance) |
| GET | `/api/admin/customization` | routes/admin.py:430 | pages/Admin.jsx | **(a)** | §21 Admin panel (Customization tab) |
| PUT | `/api/admin/customization` | routes/admin.py:436 | pages/Admin.jsx | **(a)** | §21 Admin panel (Customization) |
| GET | `/api/admin/grievances` | routes/admin.py:107 | pages/Admin.jsx | **(a)** | §21 Admin panel (Grievances tab) |
| POST | `/api/admin/grievances/{gid}/resolve` | routes/admin.py:115 | pages/Admin.jsx | **(a)** | §21 Admin panel (Grievances) |
| GET | `/api/admin/me` | routes/admin.py:28 | pages/Admin.jsx | **(a)** | §21 Admin panel (self-lookup for tab visibility) |
| POST | `/api/admin/rate-nudges/scan` | routes/admin.py:186 | — none | **(b)** | Already listed in F-04 backlog ("scheduler endpoints without UI") |
| GET | `/api/admin/reviews` | routes/admin.py:82 | pages/Admin.jsx | **(a)** | §21 Admin panel (Reviews tab) |
| POST | `/api/admin/reviews/{rid}/approve` | routes/admin.py:89 | pages/Admin.jsx | **(a)** | §21 Admin panel (Reviews) |
| POST | `/api/admin/reviews/{rid}/reject` | routes/admin.py:98 | pages/Admin.jsx | **(a)** | §21 Admin panel (Reviews) |
| GET | `/api/admin/scheduler` | routes/admin.py:194 | — none | **(b)** | Already in F-04 (scheduler introspection, curl-only) |
| GET | `/api/admin/staff` | routes/admin.py:232 | pages/Admin.jsx | **(a)** | §21 Admin panel (Staff/Permissions tab) |
| POST | `/api/admin/staff` | routes/admin.py:242 | pages/Admin.jsx | **(a)** | §21 Admin panel (Staff) |
| PATCH | `/api/admin/staff/{staff_id}` | routes/admin.py:264 | pages/Admin.jsx | **(a)** | §21 Admin panel (Staff — update scopes) |
| DELETE | `/api/admin/staff/{staff_id}` | routes/admin.py:296 | pages/Admin.jsx | **(a)** | §21 Admin panel (Staff — remove) |
| GET | `/api/admin/users` | routes/admin.py:315 | pages/Admin.jsx | **(a)** | §21 Admin panel (Users tab) |
| GET | `/api/admin/users/{uid}` | routes/admin.py:335 | pages/Admin.jsx | **(a)** | §21 Admin panel (Users — detail) |
| POST | `/api/admin/users/{uid}/notes` | routes/admin.py:359 | pages/Admin.jsx | **(a)** | §21 Admin panel (Users — support notes) |
| POST | `/api/admin/users/{uid}/adjust` | routes/admin.py:383 | pages/Admin.jsx | **(a)** | §21 Admin panel (Users — hours adjust) |
| GET | `/api/customization/public` | routes/admin.py:452 | — none | **(c)** | Truly dead. SPA never reads it; admin uses `/admin/customization` (auth) for the read too. Delete or wire into Landing. |
| POST | `/api/engagements/sign` | server.py:645 | pages/EngagementDetail.jsx | **(a)** | §11 Engagements — table currently lists `/engagements/{id}/sign` (see §4b). Fix the FEATURES.md row to match the real path. |
| GET | `/api/employers/{employer_id}` | server.py:379 | pages/Admin.jsx · pages/Projects.jsx · pages/TalentDashboard.jsx | **(a)** | §7 Employer dashboard AND §21 Admin panel (used by both). Cross-linked profile lookup. |
| GET | `/api/files/{file_id}` | server.py:2321 | components/EngagementChat.jsx · pages/EngagementDetail.jsx · pages/TalentProfile.jsx | **(a)** | §11 Engagements — attachment download (referenced by EngagementDetail's `frontend/src/pages/EngagementDetail.jsx:321` link). |
| GET | `/api/legal` | server.py:2649 | 8 callers (Legal, DPIA, SubProcessors, Footer, CookieConsent, DemoTabs, legal/content.js, App) | **(a)** | §1 Legal & Compliance — currently narrative only; add explicit row. |
| GET | `/api/messages/{engagement_id}` | server.py:935 | components/EngagementChat.jsx | **(a)** | §11 Engagements — messaging is called out but not tabled |
| POST | `/api/messages` | server.py:944 | components/EngagementChat.jsx | **(a)** | §11 Engagements |
| POST | `/api/messages/upload` | server.py:2284 | components/EngagementChat.jsx | **(a)** | §11 Engagements (attachment upload) |
| POST | `/api/newsletter/signup` | server.py:2226 | pages/SkillLanding.jsx | **(a)** | §8 Browse / discovery (marketing) OR add a new "§8b Marketing signups" section |
| POST | `/api/pricing/quote` | server.py:2103 | — none | **(b)/(c)** | Already in F-04. Truly no caller — delete unless the intent is a future partner API. |
| GET | `/api/pricing/tiers` | server.py:2091 | — none | **(b)/(c)** | Already in F-04. SPA `Pricing.jsx` uses `/api/pricing` (singular), not `/tiers`. Delete or route the SPA at it. |
| GET | `/api/seo/skills` | routes/marketplace.py:29 | — none (crawler-only) | **(b)** | §8 Browse / discovery — currently narrative only; add a "public / SEO" sub-row. |
| GET | `/api/seo/city-skills` | routes/marketplace.py:34 | — none (crawler-only) | **(b)** | §8 Browse / discovery — same as above |
| GET | `/api/shortlist/broadcasts` | server.py:2198 | — none | **(c)** | The SPA does have a "Broadcast" feature but calls the SSE endpoint (`/api/talent/me/broadcasts/stream`) and a scoped list, not this employer-side history endpoint. Delete or wire into an employer-history panel. |
| GET | `/api/sitemap.xml` | routes/marketplace.py:80 | — none (search engines) | **(b)** | §8 Browse / discovery — add a public/SEO sub-row |
| DELETE | `/api/work/items/{item_id}` | server.py:2733 | pages/Integrations.jsx | **(a)** | §22 Integrations (Work-item cleanup) |

**Counts (41 total):**
- **(a) undocumented feature — 32 routes.** All have live SPA callers.
  Break-down by section: 19 admin panel (§21), 4 accounts/integrations
  (§22), 3 engagement messaging (§11), 1 file download (§11), 1
  employer profile lookup (§7 + §21 + §16), 1 engagement-sign
  path-fix (§11 — reconciles §4b), 1 legal (§1), 1 newsletter (§8),
  1 work-item delete (§22).
- **(b) internal / admin-no-UI — 5 routes.** `/admin/scheduler`,
  `/admin/rate-nudges/scan` (both already in F-04 no-UI list);
  `/seo/skills`, `/seo/city-skills`, `/sitemap.xml` (crawler-only,
  intentional public — no SPA caller expected).
- **(c) dead code — 2 routes.** `/customization/public` (no SPA read;
  admin panel uses the authenticated `/admin/customization` instead);
  `/shortlist/broadcasts` (no caller found — the SPA's broadcast UI
  uses the SSE endpoint + a scoped list, not this employer-side
  history endpoint).
- **(b)/(c) overlap — 2 routes.** `/pricing/tiers` and `/pricing/quote`
  are both already flagged in F-04 as no-UI AND my grep confirms zero
  SPA callers — same-endpoint different-lens; delete or wire up.

Sanity: 32 + 5 + 2 + 2 = 41 ✓

---

## 3. §4d triage — 23 auth-claim unknowns

Column key:
- **Claim shape**: exact FEATURES.md phrase that diff.py couldn't parse.
- **Code enforces**: verbatim from ENDPOINT_INVENTORY.md §4d column.
- **Verdict** with human-eye reading:
  - **MATCH (ownership)** — code has an ownership check the diff tool
    can't tie to the free-form `party` phrase. Post-S-28 the check is
    visible; the diff verdict just needs the phrase parser to catch up.
  - **MATCH (via helper)** — the handler delegates authz to a helper
    like `_load_project_or_404` or `_load_deliverable_and_authorize`.
    Scanner walks only the handler body, so the check is invisible. Same
    shape of blind spot as S-28. Filed as **S-29** below.
  - **MATCH (role check)** — code has a role check the phrase parser
    can't tie to the docs wording.
  - **MISMATCH** — real divergence. Add to backlog.

| Method | Path | file:line | Claim shape | Code enforces | Verdict |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/deliverables/{}` | server.py:686 | `auth (party)` | `ownership: user['id'] not in (eng['employer_id'], eng['talent_id'])` | **MATCH (ownership)** |
| GET | `/api/deliverables/{}/revision-summary` | routes/revisions.py:497 | `auth (party or moderation admin)` | `auth (no role/scope in body)` | **MATCH (via helper)** — `_load_deliverable_and_authorize` at revisions.py:120 handles party + moderation admin. **S-29 blind spot.** |
| GET | `/api/deliverables/{}/revisions` | routes/revisions.py:218 | `auth (party or moderation admin)` | `auth (no role/scope in body)` | **MATCH (via helper)** — same helper. **S-29.** |
| GET | `/api/engagements/{}` | server.py:637 | `auth (party)` | `ownership: user['id'] not in (eng['employer_id'], eng['talent_id'])` | **MATCH (ownership)** |
| GET | `/api/grievances/{}/fee-status` | routes/revisions.py:669 | `auth (payer/other party/admin)` | `has_admin_scope('moderation'); ownership: user['id'] not in (g['talent_id'], g['employer_id'])` | **MATCH (ownership + scope)** — the S-25 canary, now correctly attributed post-S-28. |
| GET | `/api/invoices/mine` | routes/projects.py:904 | `auth (admin sees all, employer sees own)` | `role == 'admin'; role == 'employer'` | **MATCH (role check)** — code and docs agree; the phrase describes query-side filtering. |
| GET | `/api/projects/mine` | routes/projects.py:227 | `auth (employer sees own)` | `role == 'admin'; role == 'employer'` | **MATCH (role check)** — code additionally supports admin (docs incomplete but not wrong). Minor doc gap: add "admin sees all" to the FEATURES.md row. |
| GET | `/api/projects/workspace/{}` | routes/projects.py:239 | `auth (admin or employer_id==user.id)` | `auth (no role/scope in body)` | **MATCH (via helper)** — `_load_project_or_404` at projects.py:62 enforces `_can_view_project`. **S-29.** |
| GET | `/api/projects/workspace/{}/alerts` | routes/projects.py:437 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — same helper. **S-29.** |
| GET | `/api/projects/workspace/{}/invoices/{}/pdf` | routes/projects.py:753 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — same. **S-29.** |
| PATCH | `/api/projects/workspace/{}/phases/{}` | routes/projects.py:289 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — same. **S-29.** |
| PATCH | `/api/projects/workspace/{}/risks/{}` | routes/projects.py:500 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — same. **S-29.** |
| POST | `/api/alerts/{}/read` | routes/projects.py:461 | `auth (party)` | `role != 'admin'; ownership: user['id'] != a.get('employer_id')` | **MATCH (ownership + role)** |
| POST | `/api/eoi` | server.py:2465 | `auth (talent flow)` | `role != 'talent'` | **MATCH (role check)** |
| POST | `/api/grievances/{}/pay-fee` | routes/revisions.py:587 | `auth (payer)` | `ownership: user['id'] != payer_id` | **MATCH (ownership)** |
| POST | `/api/integrations/crm/push-lead` | routes/auth.py:1037 | `employer/admin` | `auth (no role/scope in body)` | **MISMATCH.** Any authenticated user can push a CRM lead. Talent-role callers included. See **S-30** below. |
| POST | `/api/integrations/crm/sync-now` | routes/auth.py:1183 | `employer/admin` | `role not in ('employer', 'admin')` | **MATCH (role check)** — code is exactly the docs claim; scanner phrase parser doesn't recognise `X/Y` as `role in {X, Y}`. Same pattern as S-30 in structure, but here the code is correct. |
| POST | `/api/projects/workspace/{}/milestones` | routes/projects.py:549 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — `_load_project_or_404`. **S-29.** |
| POST | `/api/projects/workspace/{}/milestones/{}/checkout` | routes/projects.py:781 | `admin OR employer_id==user.id` | `role == 'admin'; ownership: user['id'] == project.get('employer_id')` | **MATCH (ownership + role)** |
| POST | `/api/projects/workspace/{}/risks` | routes/projects.py:475 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — `_load_project_or_404`. **S-29.** |
| POST | `/api/projects/workspace/{}/variances` | routes/projects.py:406 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — same. **S-29.** |
| POST | `/api/reviews` | server.py:781 | `auth (party)` | `ownership: user['id'] not in (eng['employer_id'], eng['talent_id'])` | **MATCH (ownership)** |
| PUT | `/api/projects/workspace/{}/raci` | routes/projects.py:526 | `auth (party)` | `auth (no role/scope in body)` | **MATCH (via helper)** — same. **S-29.** |

**Bucket totals — 23 unknowns:**
| Verdict | Count | Route class |
| --- | --- | --- |
| MATCH (ownership check now visible post-S-28) | 6 | `/deliverables/{}`, `/engagements/{}`, `/reviews`, `/alerts/{}/read`, `/grievances/{}/pay-fee`, `/projects/workspace/{}/milestones/{}/checkout` |
| MATCH (role check the phrase parser doesn't grok) | 5 | `/invoices/mine`, `/projects/mine`, `/eoi`, `/integrations/crm/sync-now`, `/grievances/{}/fee-status` (compound) |
| MATCH (via helper — S-29 blind spot) | 11 | 9× `/projects/workspace/{}/*` (root, alerts, invoices/{}/pdf, phases PATCH, risks PATCH, milestones POST, risks POST, variances POST, raci PUT) + 2× `/deliverables/{}/{revisions, revision-summary}` |
| MISMATCH (real backlog item) | 1 | `/integrations/crm/push-lead` → **S-30** |

---

## 4. Patterns and new backlog items

### Pattern A — helper-delegated authorization (11 routes)

`_load_project_or_404` (`projects.py:62`) and
`_load_deliverable_and_authorize` (`revisions.py:120`) both call
`raise HTTPException(...)` inside the helper. The route handlers await
the helper's return value and use it as the loaded document, never
re-checking authorization. The scanner walks each handler's own AST
tree, so it sees no scope/role/ownership check in the handler body —
even though the auth check is centralised and correct.

Same class of blind spot as S-28 (which taught the scanner to detect
`user["id"]` ownership shapes). The fix is a second scanner enhancement
that follows same-module helper calls whose names match a pattern like
`_load_*_or_404` / `_load_*_and_authorize` / `_require_*` and merges
their body checks into the caller's.

Filed as **S-29 (new)** below.

### Pattern B — role disjunction in prose (5 routes)

FEATURES.md uses `employer/admin`, `admin sees all, employer sees own`,
`admin OR employer_id==user.id`. Code implements the exact set —
`role in ('employer', 'admin')` or a whitelist branch — but diff.py's
`auth_matches` only understands `role=X`, `role=X OR role=Y`, and
`scope=X`. The prose forms fall through to `unknown`.

Not urgent (all 5 verdicts are MATCH), but a follow-up scanner
enhancement could parse `X/Y` and `X or Y` into role sets. If the
pattern grows past 8-10 routes it graduates to a proper S-XX entry.

### Pattern C — one real mismatch

`POST /api/integrations/crm/push-lead` (`auth.py:1037`) — docs say
"employer/admin"; code is `auth (no role/scope in body)`. Talent
callers can push a CRM lead. Filed as **S-30 (new)** below.

---

## 5. Additions to `SECURITY_BACKLOG.md` (all filed 2026-09-06)

### S-29 (P2, tooling — FILED) — Scanner blind spot #2: helper-delegated auth not detected

- **Where**: `docs/scripts/route_scan.py::_collect_body_checks`
  (11 handlers currently mis-classified as `auth (no role/scope in body)`
  — see UNDOCUMENTED_ROUTES.md §3, "MATCH (via helper)" rows).
- **Issue**: The scanner walks each handler function's own AST tree
  only. Handlers that delegate authorization to a same-module helper
  (`_load_project_or_404`, `_load_deliverable_and_authorize`) look
  auth-less to the scanner even though the check is centralised and
  correct. Not a code vulnerability — every affected handler is
  properly protected.
- **Fix**: Two-pass scan. First pass builds a map of module-level
  helpers that raise `HTTPException(401|403|404)` on the `user` arg
  (name pattern `_load_*_or_404` / `_load_*_and_authorize` /
  `_require_*` — narrow enough to avoid false attribution). Second pass,
  when a handler `await`s or calls one of these helpers with `user` as
  an argument, merges the helper's body checks into the caller's.
  Add synthetic-fixture tests in `docs/scripts/tests/test_scanner.py`
  mirroring the S-28 pattern: (positive) `_load_project_or_404`-style
  helper counts; (inverse) helper that doesn't raise, helper called
  without `user`, helper with generic name like `load_thing`.

### S-30 (P2, real mismatch — FILED after severity re-check) — `/api/integrations/crm/push-lead` unrestricted

- **Initial concern**: could this be a cross-tenant CRM write? A talent
  authenticating and pushing a lead into ANOTHER EMPLOYER's connected
  CRM would be a P0 (customer-data write to a third-party system under
  someone else's OAuth token).
- **Severity re-check (2026-09-06)**: **NO cross-tenant write path.**
  Handler at `auth.py:1041` looks up the CRM integration via
  `db.crm_integrations.find_one({"user_id": user["id"], "provider":
  payload.provider})` — the OAuth token is scoped to the CALLER's
  session, not addressable via the payload. `CrmPushLeadIn` carries
  `{provider, talent_id?, talent_name?, email?, note?}` — zero
  `employer_id` / `integration_id` fields. A talent calling this
  endpoint either 400s (no CRM connected on their own account) or
  pushes a lead into their OWN CRM. Not a data-loss vector.
- **Filed severity**: P2 (doc-drift + semantic role gate). See
  SECURITY_BACKLOG.md S-30 for the entry with this evidence inline.
- **Fix**: Add `if user.get("role") not in ("employer", "admin"): raise
  HTTPException(403, "employer or admin only")` at the top of the
  handler. Matches the shape already used by `/api/integrations/crm/
  sync-now` (auth.py:1183). One-line fix; add a Phase 1b test asserting
  a talent client gets 403.

## 6. Additions to the F-XX feature/correctness backlog (all filed 2026-09-06)

### F-12 (P2, docs — FILED) — Undocumented features (32 routes across §21, §11, §22, §7, §1, §8)

- **Where**: `FEATURES.md` sections named in UNDOCUMENTED_ROUTES.md §2
  ("Where in FEATURES.md" column, class **(a)** rows only).
- **Issue**: 32 routes exist in code with live SPA callers but no
  FEATURES.md pipe-table row. Split by section:
    - **§21 Admin panel** — 19 routes (bank-transfers, customization,
      grievances, admin/me, reviews, staff, users, users/notes,
      users/adjust)
    - **§22 Integrations** — 5 routes (accounts×4 + work/items DELETE)
    - **§11 Engagements** — 5 routes (messages×3, files/{id}, engagements/sign
      path fix reconciling §4b)
    - **§7 Employer dashboard + §21 + §16** — 1 route (employers/{id};
      cross-referenced)
    - **§1 Legal & Compliance** — 1 route (`/api/legal`; currently
      narrative only)
    - **§8 Browse / discovery** — 1 route (newsletter/signup)
- **Fix**: One PR per section (six small PRs), each adding pipe-table
  rows. No code changes.

### F-13 (P3, dead code — FILED) — Delete 4 uncalled routes

- **Where**: `backend/routes/admin.py:452` (`public_customization`);
  `backend/server.py:2091` (`get_pricing_tiers`); `backend/server.py:2103`
  (`price_quote`); `backend/server.py:2198` (`list_broadcast_history`).
- **Issue**: Zero SPA callers verified by grep; two (`pricing/tiers`,
  `pricing/quote`) are already in F-04's no-UI list. Endpoints unused =
  attack surface without value.
- **Fix**: Confirm no external caller (marketing site? partner API?),
  then delete + prune tests. Update `security/public_routes.yml` to
  remove the `intentional_public` entries for the three PUBLIC ones
  (`/customization/public`, `/pricing/tiers`, `/pricing/quote`) once
  the routes are gone.

### F-04 (existing — SCOPE EXTENDED 2026-09-06)

F-04 originally listed 7 no-UI endpoints. This triage found **two more**
(`/api/customization/public`, `/api/shortlist/broadcasts`) that fit the
same shape. F-04's row in SECURITY_BACKLOG.md is now updated to say
"9 backend endpoints with no UI" with the two additions inline. F-13
overlaps on the two `/pricing/*` endpoints — deliberate: F-04 asks
"build UI or delete?", F-13 asks "delete outright." When F-04 is worked
the F-13 rows may resolve as byproducts.

---

## 7. What this triage did NOT cover

- **§4b (1 route)** — `POST /api/engagements/{id}/sign` in FEATURES.md
  vs `POST /api/engagements/sign` in code. Trivial doc-path fix; folded
  into F-12's §11 sub-task.
- **§4c (13 routes)** — auth-claim mismatches. These are already flagged
  in the inventory and mostly overlap with S-11 / S-23 / S-24. Out of
  scope for this pass (the task asked for §4a + §4d only).
- **The 33 intentional-public §2a routes** — already blessed by
  `security/public_routes.yml`; no triage needed.
