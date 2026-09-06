# ENDPOINT_INVENTORY.md — AST-derived route inventory

Built by AST-parsing `backend/`. Regenerate with `docs/scripts/render_inventory.py`.
Every file/line reference is exact.

- **174** routes registered on the shared APIRouter (`api = APIRouter(prefix="/api")` from `backend/deps.py:37`).
- **137** carry `Depends(get_current_user)` (via default, `Annotated[..., Depends(...)]`, or decorator-level `dependencies=`).
- **36** have no authentication or authorization check of any kind (see §2).
- **41** call `_require_scope` / `has_admin_scope` in the body.
- **3** admin routes gate on `role == "admin"` alone with no scope (S-09 pattern; see `SECURITY_BACKLOG.md`).
- **41** routes are in code but not documented in `FEATURES.md` tables.
- **1** endpoint in FEATURES.md tables has no corresponding route in code.
- **13** routes have an auth claim in FEATURES.md that diverges from what the handler actually enforces.
- **23** routes have a FEATURES.md auth claim the diff tool couldn't machine-verify (see §4d).

Methodology notes:
- The scanner detects `Depends(get_current_user)` in all three FastAPI shapes: positional/keyword defaults, `Annotated[dict, Depends(get_current_user)]`, and route-decorator `dependencies=[Depends(...)]`.
- "Body scope/role check" is what the handler actually enforces at request time. Four classes are detected: (1) `_require_scope`/`has_admin_scope` calls; (2) `user["role"]`/`user.get("role")`/`user.role` comparisons; (3) `user.get("admin_permissions", ...)` inspections; (4) **ownership** — `user["id"]`/`user.get("id")`/`user.id` comparisons via `==`/`!=`/`in`/`not in`. Only comparisons whose receiver is literally the `user` variable count — loop-variable shapes like `u.get("role")` or `row["owner_id"] == row["talent_id"]` are excluded.
- Ownership checks are STRICT (see `docs/scripts/route_scan.py::_find_ownership_checks`): the compare must be the test of an `if` at the top level of the function body; the body must unconditionally raise `HTTPException(401|403|404)` or return; membership (`in`/`not in`) RHS must be a literal tuple/list/set. A check nested inside another `if`, computed but never enforced, or comparing against a bare-Name RHS does NOT count. The inverse guards in `docs/scripts/tests/test_scanner.py` (S-28) lock these rules in.
- "NO-AUTH" flag = no `Depends(get_current_user)`, no scope/role/admin_perm/ownership check. Unrelated `Depends(...)` (e.g. rate-limiter) do NOT suppress this flag. Some public routes are still gated by out-of-band checks (Stripe signature on the webhook, emailed token on `/reference-check/{token}`).
- Diff verdicts are tri-state: **match** (docs & code agree), **mismatch** (real divergence), **unknown** (FEATURES.md claim is a free-form phrase the tool cannot parse).

---

## 1. Full route inventory

| Method | Path | file:line | Dep | Body scope/role check | Flag |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/admin/me` | routes/admin.py:28 | get_current_user | body: role != 'admin'; body: admin_permissions inspected | **S-09** (role==admin only, no scope) |
| GET | `/api/admin/bank-transfers` | routes/admin.py:47 | get_current_user | _require_scope(user, 'finance') |  |
| POST | `/api/admin/bank-transfers/{payment_id}/approve` | routes/admin.py:57 | get_current_user | _require_scope(user, 'finance') |  |
| POST | `/api/admin/bank-transfers/{payment_id}/reject` | routes/admin.py:73 | get_current_user | _require_scope(user, 'finance') |  |
| GET | `/api/admin/reviews` | routes/admin.py:82 | get_current_user | _require_scope(user, 'moderation') |  |
| POST | `/api/admin/reviews/{rid}/approve` | routes/admin.py:89 | get_current_user | _require_scope(user, 'moderation') |  |
| POST | `/api/admin/reviews/{rid}/reject` | routes/admin.py:98 | get_current_user | _require_scope(user, 'moderation') |  |
| GET | `/api/admin/grievances` | routes/admin.py:107 | get_current_user | has_admin_scope(user, 'support'); has_admin_scope(user, 'moderation') |  |
| POST | `/api/admin/grievances/{gid}/resolve` | routes/admin.py:115 | get_current_user | has_admin_scope(user, 'support'); has_admin_scope(user, 'moderation') |  |
| POST | `/api/admin/payouts/run` | routes/admin.py:127 | get_current_user | _require_scope(user, 'finance') |  |
| GET | `/api/admin/payouts/runs` | routes/admin.py:162 | get_current_user | _require_scope(user, 'finance') |  |
| GET | `/api/admin/payouts/{run_id}` | routes/admin.py:168 | get_current_user | _require_scope(user, 'finance') |  |
| POST | `/api/admin/payouts/{payout_id}/mark-paid` | routes/admin.py:178 | get_current_user | _require_scope(user, 'finance') |  |
| POST | `/api/admin/rate-nudges/scan` | routes/admin.py:186 | get_current_user | body: role != 'admin' | **S-09** (role==admin only, no scope) |
| GET | `/api/admin/scheduler` | routes/admin.py:194 | get_current_user | body: role != 'admin' | **S-09** (role==admin only, no scope) |
| GET | `/api/admin/staff` | routes/admin.py:232 | get_current_user | _require_scope(user, 'superadmin'); body: admin_permissions inspected |  |
| POST | `/api/admin/staff` | routes/admin.py:242 | get_current_user | _require_scope(user, 'superadmin') |  |
| PATCH | `/api/admin/staff/{staff_id}` | routes/admin.py:264 | get_current_user | _require_scope(user, 'superadmin'); body: admin_permissions inspected |  |
| DELETE | `/api/admin/staff/{staff_id}` | routes/admin.py:296 | get_current_user | _require_scope(user, 'superadmin'); body: admin_permissions inspected |  |
| GET | `/api/admin/users` | routes/admin.py:315 | get_current_user | _require_scope(user, 'support') |  |
| GET | `/api/admin/users/{uid}` | routes/admin.py:335 | get_current_user | _require_scope(user, 'support') |  |
| POST | `/api/admin/users/{uid}/notes` | routes/admin.py:359 | get_current_user | _require_scope(user, 'support') |  |
| POST | `/api/admin/users/{uid}/adjust` | routes/admin.py:383 | get_current_user | _require_scope(user, 'support') |  |
| GET | `/api/admin/customization` | routes/admin.py:430 | get_current_user | _require_scope(user, 'customization') |  |
| PUT | `/api/admin/customization` | routes/admin.py:436 | get_current_user | _require_scope(user, 'customization') |  |
| GET | `/api/customization/public` | routes/admin.py:452 | — (public) |  | **NO-AUTH** |
| GET | `/api/admin/verifications` | routes/admin.py:473 | get_current_user | has_admin_scope(user, 'moderation'); has_admin_scope(user, 'support') |  |
| POST | `/api/admin/verifications/{uid}/approve` | routes/admin.py:486 | get_current_user | has_admin_scope(user, 'moderation') |  |
| POST | `/api/admin/verifications/{uid}/reject` | routes/admin.py:523 | get_current_user | has_admin_scope(user, 'moderation') |  |
| POST | `/api/auth/register` | routes/auth.py:127 | — (public) |  | **NO-AUTH** |
| GET | `/api/auth/verify-email` | routes/auth.py:170 | — (public) |  | **NO-AUTH** |
| POST | `/api/auth/resend-verification` | routes/auth.py:188 | get_current_user |  |  |
| POST | `/api/auth/login` | routes/auth.py:199 | — (public) |  | **NO-AUTH** |
| POST | `/api/auth/logout` | routes/auth.py:210 | — (public) |  | **NO-AUTH** |
| GET | `/api/auth/me` | routes/auth.py:217 | get_current_user |  |  |
| PUT | `/api/profile` | routes/auth.py:222 | get_current_user |  |  |
| POST | `/api/profile/suggest-rate` | routes/auth.py:229 | get_current_user |  |  |
| POST | `/api/verification/company` | routes/auth.py:270 | get_current_user | body: role != 'employer' |  |
| POST | `/api/verification/bgv` | routes/auth.py:291 | get_current_user | body: role != 'talent' |  |
| GET | `/api/reference-check/{token}` | routes/auth.py:365 | — (public) |  | **NO-AUTH** |
| POST | `/api/reference-check/{token}` | routes/auth.py:388 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/stats` | routes/auth.py:426 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/timeseries` | routes/auth.py:456 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/timeseries/details` | routes/auth.py:537 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/timeseries/details/pdf` | routes/auth.py:685 | — (public) |  | **NO-AUTH** |
| POST | `/api/trust/verify-drill` | routes/auth.py:743 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/verify-drill/{signature}` | routes/auth.py:760 | — (public) |  | **NO-AUTH** |
| GET | `/api/admin/reference-checks/{talent_id}` | routes/auth.py:901 | get_current_user | has_admin_scope(user, 'moderation'); has_admin_scope(user, 'support') |  |
| GET | `/api/verification/me` | routes/auth.py:915 | get_current_user |  |  |
| POST | `/api/integrations/crm/connect` | routes/auth.py:989 | get_current_user | body: role not in ('employer', 'admin') |  |
| GET | `/api/integrations/crm` | routes/auth.py:1015 | get_current_user |  |  |
| DELETE | `/api/integrations/crm/{provider}` | routes/auth.py:1023 | get_current_user |  |  |
| POST | `/api/integrations/crm/push-lead` | routes/auth.py:1037 | get_current_user |  |  |
| POST | `/api/integrations/crm/sync-now` | routes/auth.py:1183 | get_current_user | body: role not in ('employer', 'admin') |  |
| GET | `/api/integrations/crm/sync-log` | routes/auth.py:1192 | get_current_user |  |  |
| GET | `/api/seo/skills` | routes/marketplace.py:29 | — (public) |  | **NO-AUTH** |
| GET | `/api/seo/city-skills` | routes/marketplace.py:34 | — (public) |  | **NO-AUTH** |
| GET | `/api/sitemap.xml` | routes/marketplace.py:80 | — (public) |  | **NO-AUTH** |
| GET | `/api/marketplace/industries` | routes/marketplace.py:92 | — (public) |  | **NO-AUTH** |
| GET | `/api/marketplace/stats` | routes/marketplace.py:110 | — (public) |  | **NO-AUTH** |
| POST | `/api/shortlist` | routes/marketplace.py:158 | get_current_user | body: role != 'employer' |  |
| GET | `/api/shortlist` | routes/marketplace.py:183 | get_current_user | body: role != 'employer' |  |
| DELETE | `/api/shortlist/{talent_id}` | routes/marketplace.py:191 | get_current_user | body: role != 'employer' |  |
| POST | `/api/admin/project-leads/{lead_id}/convert` | routes/projects.py:136 | get_current_user | has_admin_scope(user, 'superadmin') |  |
| GET | `/api/admin/project-leads` | routes/projects.py:219 | get_current_user | has_admin_scope(user, 'support'); has_admin_scope(user, 'superadmin') |  |
| GET | `/api/projects/mine` | routes/projects.py:227 | get_current_user | body: role == 'admin'; body: role == 'employer' |  |
| GET | `/api/projects/workspace/{project_id}` | routes/projects.py:239 | get_current_user |  |  |
| PATCH | `/api/projects/workspace/{project_id}/phases/{phase_id}` | routes/projects.py:289 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/variances` | routes/projects.py:406 | get_current_user |  |  |
| GET | `/api/projects/workspace/{project_id}/alerts` | routes/projects.py:437 | get_current_user |  |  |
| GET | `/api/alerts/mine` | routes/projects.py:446 | get_current_user | body: role == 'admin'; body: role == 'employer' |  |
| POST | `/api/alerts/{alert_id}/read` | routes/projects.py:461 | get_current_user | body: role != 'admin'; body: ownership: user['id'] != a.get('employer_id') |  |
| POST | `/api/projects/workspace/{project_id}/risks` | routes/projects.py:475 | get_current_user |  |  |
| PATCH | `/api/projects/workspace/{project_id}/risks/{risk_id}` | routes/projects.py:500 | get_current_user |  |  |
| PUT | `/api/projects/workspace/{project_id}/raci` | routes/projects.py:526 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/milestones` | routes/projects.py:549 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/milestones/{milestone_id}/invoice` | routes/projects.py:586 | get_current_user | has_admin_scope(user, 'finance'); has_admin_scope(user, 'superadmin') |  |
| POST | `/api/projects/workspace/{project_id}/milestones/{milestone_id}/paid` | routes/projects.py:616 | get_current_user | has_admin_scope(user, 'finance'); has_admin_scope(user, 'superadmin') |  |
| GET | `/api/projects/workspace/{project_id}/invoices/{invoice_id}/pdf` | routes/projects.py:753 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/milestones/{milestone_id}/checkout` | routes/projects.py:781 | get_current_user | body: role == 'admin'; body: ownership: user['id'] == project.get('employer_id') |  |
| GET | `/api/projects/milestone-payment/status/{session_id}` | routes/projects.py:867 | get_current_user |  |  |
| GET | `/api/invoices/mine` | routes/projects.py:904 | get_current_user | body: role == 'admin'; body: role == 'employer' |  |
| POST | `/api/billing/setup-checkout` | routes/projects.py:975 | get_current_user | body: role != 'employer' |  |
| GET | `/api/billing/setup-checkout/status/{session_id}` | routes/projects.py:1014 | get_current_user | body: role != 'employer' |  |
| POST | `/api/billing/setup` | routes/projects.py:1053 | get_current_user | body: role != 'employer' |  |
| GET | `/api/billing/status` | routes/projects.py:1091 | get_current_user | body: role != 'employer' |  |
| POST | `/api/admin/invoices/scan-overdue` | routes/projects.py:1326 | get_current_user | has_admin_scope(user, 'finance'); has_admin_scope(user, 'superadmin') |  |
| POST | `/api/admin/projects/{project_id}/save-as-template` | routes/projects.py:1354 | get_current_user | has_admin_scope(user, 'superadmin'); has_admin_scope(user, 'customization') |  |
| GET | `/api/admin/verifications-with-refs` | routes/projects.py:1412 | get_current_user | has_admin_scope(user, 'moderation'); has_admin_scope(user, 'support') |  |
| POST | `/api/deliverables/{deliverable_id}/request-revision` | routes/revisions.py:135 | get_current_user |  |  |
| POST | `/api/deliverables/{deliverable_id}/resubmit` | routes/revisions.py:189 | get_current_user |  |  |
| GET | `/api/deliverables/{deliverable_id}/revisions` | routes/revisions.py:218 | get_current_user |  |  |
| POST | `/api/deliverables/{deliverable_id}/dispute` | routes/revisions.py:236 | get_current_user |  |  |
| GET | `/api/admin/revisions` | routes/revisions.py:292 | get_current_user | has_admin_scope(user, 'moderation') |  |
| POST | `/api/admin/revisions/{grievance_id}/rule` | routes/revisions.py:313 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/employers-flagged` | routes/revisions.py:416 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/revisions/refund-analytics` | routes/revisions.py:429 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/deliverables/{deliverable_id}/revision-summary` | routes/revisions.py:497 | get_current_user |  |  |
| GET | `/api/talent/me/recovery-status` | routes/revisions.py:543 | get_current_user | body: role != 'talent' |  |
| POST | `/api/grievances/{grievance_id}/pay-fee` | routes/revisions.py:587 | get_current_user | body: ownership: user['id'] != payer_id |  |
| GET | `/api/grievances/{grievance_id}/fee-status` | routes/revisions.py:669 | get_current_user | has_admin_scope(user, 'moderation'); body: ownership: user['id'] not in (g.get('talent_id'), g.get('employer_id')) |  |
| POST | `/api/admin/grievances/{grievance_id}/refund-fee` | routes/revisions.py:737 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/revisions/refund-audit/pdf` | routes/revisions.py:935 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/revisions/refund-audit/verify/{signature}` | routes/revisions.py:978 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/talent` | server.py:229 | — (public) |  | **NO-AUTH** |
| GET | `/api/employers` | server.py:326 | get_current_user | body: role not in ('talent', 'admin') |  |
| GET | `/api/employers/{employer_id}` | server.py:379 | get_current_user | body: role not in ('talent', 'admin') |  |
| GET | `/api/earnings/mine` | server.py:401 | get_current_user | body: role != 'talent' |  |
| GET | `/api/talent/{talent_id}` | server.py:410 | get_current_user | body: role != 'employer' |  |
| GET | `/api/packages` | server.py:430 | — (public) |  | **NO-AUTH** |
| POST | `/api/payments/bank/initiate` | server.py:441 | get_current_user | body: role != 'employer' |  |
| POST | `/api/payments/bank/submit` | server.py:468 | get_current_user |  |  |
| GET | `/api/payments/mine` | server.py:486 | get_current_user |  |  |
| POST | `/api/payments/checkout` | server.py:493 | get_current_user | body: role != 'employer' |  |
| GET | `/api/payments/status/{session_id}` | server.py:540 | — (public) |  | **NO-AUTH** |
| POST | `/api/stripe/webhook` | server.py:555 | — (public) |  | **NO-AUTH** |
| POST | `/api/engagements` | server.py:600 | get_current_user | body: role != 'employer' |  |
| GET | `/api/engagements` | server.py:630 | get_current_user | body: role == 'employer' |  |
| GET | `/api/engagements/{eid}` | server.py:637 | get_current_user | body: ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) |  |
| POST | `/api/engagements/sign` | server.py:645 | get_current_user | body: ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) |  |
| POST | `/api/deliverables` | server.py:665 | get_current_user | body: ownership: user['id'] != eng.get('talent_id') |  |
| GET | `/api/deliverables/{engagement_id}` | server.py:686 | get_current_user | body: ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) |  |
| POST | `/api/deliverables/{deliverable_id}/approve` | server.py:770 | get_current_user |  |  |
| POST | `/api/deliverables/{deliverable_id}/reject` | server.py:775 | get_current_user |  |  |
| POST | `/api/reviews` | server.py:781 | get_current_user | body: ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) |  |
| GET | `/api/reviews/user/{user_id}` | server.py:805 | — (public) |  | **NO-AUTH** |
| POST | `/api/grievances` | server.py:816 | — (public) |  | **NO-AUTH** |
| GET | `/api/payouts/mine` | server.py:872 | get_current_user | body: role != 'talent' |  |
| GET | `/api/referrals/mine` | server.py:884 | get_current_user |  |  |
| POST | `/api/referrals/claim` | server.py:894 | get_current_user |  |  |
| GET | `/api/messages/{engagement_id}` | server.py:935 | get_current_user | body: ownership: user['id'] not in (eng.get('employer_id'), eng.get('talent_id')) |  |
| POST | `/api/messages` | server.py:944 | get_current_user | body: ownership: user['id'] not in (eng.get('employer_id'), eng.get('talent_id')) |  |
| GET | `/api/seo/hire/{skill_slug}` | server.py:970 | — (public) |  | **NO-AUTH** |
| GET | `/api/employer/overview` | server.py:995 | get_current_user | body: role != 'employer' |  |
| GET | `/api/seo/hire-city/{slug}` | server.py:1342 | — (public) |  | **NO-AUTH** |
| GET | `/api/talent/me/rate-nudge` | server.py:1477 | get_current_user | body: role != 'talent' |  |
| POST | `/api/talent/me/rate-nudge/dismiss` | server.py:1486 | get_current_user | body: role != 'talent' |  |
| POST | `/api/shortlist/broadcast` | server.py:1506 | get_current_user | body: role != 'employer' |  |
| GET | `/api/projects/templates` | server.py:1879 | — (public) |  | **NO-AUTH** |
| GET | `/api/projects/templates/{template_id}` | server.py:1887 | — (public) |  | **NO-AUTH** |
| GET | `/api/projects/templates/{template_id}/team-suggestions` | server.py:1968 | — (public) |  | **NO-AUTH** |
| POST | `/api/projects/lead` | server.py:2023 | — (public) |  | **NO-AUTH** |
| GET | `/api/pricing/tiers` | server.py:2091 | — (public) |  | **NO-AUTH** |
| POST | `/api/pricing/quote` | server.py:2103 | — (public) |  | **NO-AUTH** |
| GET | `/api/auth/sse-token` | server.py:2113 | get_current_user |  |  |
| GET | `/api/talent/me/broadcasts` | server.py:2120 | get_current_user | body: role != 'talent' |  |
| GET | `/api/talent/me/broadcasts/stream` | server.py:2145 | get_current_user | body: role != 'talent' |  |
| GET | `/api/shortlist/broadcasts` | server.py:2198 | get_current_user | body: role != 'employer' |  |
| POST | `/api/talent/me/broadcasts/{broadcast_doc_id}/read` | server.py:2208 | get_current_user | body: role != 'talent' |  |
| POST | `/api/newsletter/signup` | server.py:2226 | — (public) |  | **NO-AUTH** |
| POST | `/api/files/upload` | server.py:2243 | get_current_user |  |  |
| POST | `/api/messages/upload` | server.py:2284 | get_current_user | body: ownership: user['id'] not in (eng.get('employer_id'), eng.get('talent_id')) |  |
| GET | `/api/files/{file_id}` | server.py:2321 | get_current_user |  |  |
| GET | `/api/integrations/providers` | server.py:2341 | — (public) |  | **NO-AUTH** |
| POST | `/api/integrations/connect` | server.py:2346 | get_current_user |  |  |
| DELETE | `/api/integrations/{integration_id}` | server.py:2370 | get_current_user |  |  |
| POST | `/api/integrations/sync/{integration_id}` | server.py:2377 | get_current_user |  |  |
| POST | `/api/work/upload` | server.py:2397 | get_current_user |  |  |
| GET | `/api/work/items` | server.py:2423 | get_current_user |  |  |
| PUT | `/api/availability` | server.py:2430 | get_current_user |  |  |
| GET | `/api/availability/{user_id}` | server.py:2436 | get_current_user |  |  |
| GET | `/api/calendar/events` | server.py:2446 | get_current_user | body: role == 'employer'; body: role == 'talent' |  |
| POST | `/api/eoi` | server.py:2465 | get_current_user | body: role != 'talent' |  |
| GET | `/api/eoi` | server.py:2489 | get_current_user | body: role == 'talent'; body: role == 'employer' |  |
| POST | `/api/eoi/{eoi_id}/accept` | server.py:2501 | get_current_user | body: role != 'employer' |  |
| POST | `/api/eoi/{eoi_id}/withdraw` | server.py:2535 | get_current_user | body: ownership: user['id'] != eoi['talent_id'] |  |
| GET | `/api/accounts/providers` | server.py:2566 | get_current_user |  |  |
| GET | `/api/accounts` | server.py:2572 | get_current_user |  |  |
| POST | `/api/accounts/connect` | server.py:2578 | get_current_user | body: role not in prov['for']; body: role != 'admin' |  |
| DELETE | `/api/accounts/{account_id}` | server.py:2603 | get_current_user |  |  |
| GET | `/api/pricing` | server.py:2611 | — (public) |  | **NO-AUTH** |
| GET | `/api/legal` | server.py:2649 | — (public) |  | **NO-AUTH** |
| GET | `/api/dashboard/metrics` | server.py:2671 | get_current_user |  |  |
| DELETE | `/api/work/items/{item_id}` | server.py:2733 | get_current_user |  |  |


---

## 2. Routes with no authorization check

### 2a. Intentional public surface (33 routes)

Listed in `security/public_routes.yml`:`intentional_public`. Adding a new public
route without listing it here trips `backend/tests/test_public_surface.py`.

| Method | Path | file:line | Handler | Reason |
| --- | --- | --- | --- | --- |
| GET | `/api/customization/public` | routes/admin.py:452 | public_customization | Public tenant customization payload for header/hero. FEATURES §21. |
| POST | `/api/auth/register` | routes/auth.py:127 | register | Public registration; Turnstile-gated (fails open when TURNSTILE_SECRET_KEY unset). FEATURES §3. |
| GET | `/api/auth/verify-email` | routes/auth.py:170 | verify_email | Public email-verification token consumption; FEATURES §3. |
| POST | `/api/auth/login` | routes/auth.py:199 | login | Public login; bcrypt + Turnstile. FEATURES §3. |
| POST | `/api/auth/logout` | routes/auth.py:210 | logout | Idempotent cookie clear; FEATURES §3. |
| GET | `/api/reference-check/{token}` | routes/auth.py:365 | reference_check_get | Public referee form; gated by emailed one-time token in path. FEATURES §15. |
| POST | `/api/reference-check/{token}` | routes/auth.py:388 | reference_check_post | Public referee submit; same one-time token gate. FEATURES §15. |
| GET | `/api/trust/stats` | routes/auth.py:426 | public_trust_stats | Public /trust page metrics. FEATURES §4. |
| GET | `/api/trust/timeseries` | routes/auth.py:456 | public_trust_timeseries | Public /trust page timeseries. FEATURES §4. |
| GET | `/api/trust/timeseries/details` | routes/auth.py:537 | public_trust_timeseries_details | Public /trust drill-through. FEATURES §4. |
| GET | `/api/trust/timeseries/details/pdf` | routes/auth.py:685 | public_trust_timeseries_pdf | Public signed PDF export; writes a drill_receipts row. FEATURES §4. |
| POST | `/api/trust/verify-drill` | routes/auth.py:743 | public_verify_drill | Public tamper-check POST; FEATURES §4 (also listed as no-UI in FEATURES 'Dead ends'). |
| GET | `/api/trust/verify-drill/{signature}` | routes/auth.py:760 | public_verify_drill_lookup | Public signature lookup driven by QR code in the PDF. FEATURES §4. |
| GET | `/api/seo/skills` | routes/marketplace.py:29 | seo_skills | SEO skill index. Public marketing surface. |
| GET | `/api/seo/city-skills` | routes/marketplace.py:34 | seo_city_skills | SEO city×skill index. Public marketing surface. |
| GET | `/api/sitemap.xml` | routes/marketplace.py:80 | sitemap_xml | Public sitemap for crawlers. |
| GET | `/api/marketplace/industries` | routes/marketplace.py:92 | marketplace_industries | Public industry list for Register form + SEO. FEATURES §5/§8. |
| GET | `/api/marketplace/stats` | routes/marketplace.py:110 | marketplace_stats | Public marketplace stats. FEATURES §8. |
| GET | `/api/talent` | server.py:229 | list_talent | Public browse endpoint powering /browse. FEATURES §8. |
| GET | `/api/packages` | server.py:430 | get_packages | Public hour-package catalog for /employer/purchase. FEATURES §10. |
| GET | `/api/payments/status/{session_id}` | server.py:540 | payment_status | Polled by /payment/success without a session (session_id from Stripe URL). FEATURES §10. |
| POST | `/api/stripe/webhook` | server.py:555 | stripe_webhook | Gated by stripe.Webhook.construct_event signature verification at server.py:562. Cookie auth is inapplicable. |
| GET | `/api/reviews/user/{user_id}` | server.py:805 | reviews_for_user | Public reviews on talent card. FEATURES §11. |
| POST | `/api/grievances` | server.py:816 | submit_grievance | Public grievance-officer submission form. FEATURES §2. |
| GET | `/api/seo/hire/{skill_slug}` | server.py:970 | seo_hire | Public /hire/:slug landing page. FEATURES §8. |
| GET | `/api/seo/hire-city/{slug}` | server.py:1342 | seo_hire_city | Public /hire/city landing page. FEATURES §8. |
| GET | `/api/projects/templates` | server.py:1879 | list_project_templates | Public template catalog (Projects.jsx renders it before login). FEATURES §16. |
| GET | `/api/projects/templates/{template_id}` | server.py:1887 | get_project_template | Public template detail; consumed by anonymous browsing. FEATURES §16. |
| GET | `/api/pricing/tiers` | server.py:2091 | get_pricing_tiers | Public tiers subset of /api/pricing. FEATURES §10 (Dead ends: no UI caller). |
| POST | `/api/pricing/quote` | server.py:2103 | price_quote | Public quote calculator. FEATURES §10 (Dead ends: no UI caller). |
| POST | `/api/newsletter/signup` | server.py:2226 | newsletter_signup | Public newsletter waitlist from SEO landing pages. |
| GET | `/api/pricing` | server.py:2611 | get_pricing | Public /pricing page. FEATURES §10. |
| GET | `/api/legal` | server.py:2649 | get_legal | Public static legal metadata. FEATURES §1. |


### 2b. Surprising — should probably require auth (3 routes)

Listed in `security/public_routes.yml`:`surprising_unauth`. Each row is a triage item.

| Method | Path | file:line | Handler | Why it's a surprise |
| --- | --- | --- | --- | --- |
| GET | `/api/projects/templates/{template_id}/team-suggestions` | server.py:1968 | suggest_team_for_template | S-24 (P1). Returns _CURATED_TALENT names + hourly rates + sell-rate/margin math to any unauthenticated caller — crown-jewel supply pool per CONTRACTOR_SPLIT.md. FEATURES §16 claims `auth`. |
| POST | `/api/projects/lead` | server.py:2023 | submit_project_lead | S-23 (P1). FEATURES §16 tables list this as `auth`. Currently anyone can POST a project_leads row with a forged employer_id. Lead-forgery + attribution poisoning + queue-spam vector. |
| GET | `/api/integrations/providers` | server.py:2341 | integration_providers | FEATURES §22 tables list this as `auth`. Low-sensitivity list of provider names, but the docs-vs-code claim disagrees. |



---

## 3. Admin routes that gate on `role == "admin"` alone (no scope) — S-09

CLAUDE.md invariant #6: *"Any new admin endpoint uses `_require_scope(user, "<scope>")`. `role == "admin"` alone is a bug."*
SECURITY_BACKLOG.md S-09 flags `POST /admin/rate-nudges/scan` and `GET /admin/scheduler` at `admin.py:186-211` explicitly. The AST scan confirms:

| Method | Path | file:line | Body check |
| --- | --- | --- | --- |
| GET | `/api/admin/me` | routes/admin.py:28 | role != 'admin' |
| POST | `/api/admin/rate-nudges/scan` | routes/admin.py:186 | role != 'admin' |
| GET | `/api/admin/scheduler` | routes/admin.py:194 | role != 'admin' |


`GET /api/admin/me` is arguably fine as-is (identity/scopes lookup), but a proposed
"every `/admin/*` route has a scope dependency" pytest will need it on the allow-list.

---

## 4. Drift vs `FEATURES.md`

### 4a. In code, missing from FEATURES.md tables (41)

Routes that exist in the backend but do not appear in any FEATURES.md pipe table.
Some are mentioned in narrative prose but never in a machine-checkable table.

| Method | Path | file:line | Handler | Actual authz |
| --- | --- | --- | --- | --- |
| DELETE | `/api/accounts/{account_id}` | server.py:2603 | disconnect_account | auth (no role/scope in body) |
| DELETE | `/api/admin/staff/{staff_id}` | routes/admin.py:296 | admin_delete_staff | _require_scope(user, 'superadmin'); admin_permissions check |
| DELETE | `/api/work/items/{item_id}` | server.py:2733 | delete_work_item | auth (no role/scope in body) |
| GET | `/api/accounts` | server.py:2572 | list_accounts | auth (no role/scope in body) |
| GET | `/api/accounts/providers` | server.py:2566 | account_providers | auth (no role/scope in body) |
| GET | `/api/admin/bank-transfers` | routes/admin.py:47 | admin_bank_list | _require_scope(user, 'finance') |
| GET | `/api/admin/customization` | routes/admin.py:430 | admin_get_customization | _require_scope(user, 'customization') |
| GET | `/api/admin/grievances` | routes/admin.py:107 | admin_list_grievances | has_admin_scope(user, 'support'); has_admin_scope(user, 'moderation') |
| GET | `/api/admin/me` | routes/admin.py:28 | admin_me | role != 'admin'; admin_permissions check |
| GET | `/api/admin/reviews` | routes/admin.py:82 | admin_list_reviews | _require_scope(user, 'moderation') |
| GET | `/api/admin/scheduler` | routes/admin.py:194 | admin_scheduler_status | role != 'admin' |
| GET | `/api/admin/staff` | routes/admin.py:232 | admin_list_staff | _require_scope(user, 'superadmin'); admin_permissions check |
| GET | `/api/admin/users` | routes/admin.py:315 | admin_list_users | _require_scope(user, 'support') |
| GET | `/api/admin/users/{uid}` | routes/admin.py:335 | admin_user_detail | _require_scope(user, 'support') |
| GET | `/api/customization/public` | routes/admin.py:452 | public_customization | PUBLIC (no auth) |
| GET | `/api/employers/{employer_id}` | server.py:379 | get_employer_public | role not in ('talent', 'admin') |
| GET | `/api/files/{file_id}` | server.py:2321 | download_file | auth (no role/scope in body) |
| GET | `/api/legal` | server.py:2649 | get_legal | PUBLIC (no auth) |
| GET | `/api/messages/{engagement_id}` | server.py:935 | list_messages | ownership: user['id'] not in (eng.get('employer_id'), eng.get('talent_id')) |
| GET | `/api/pricing/tiers` | server.py:2091 | get_pricing_tiers | PUBLIC (no auth) |
| GET | `/api/seo/city-skills` | routes/marketplace.py:34 | seo_city_skills | PUBLIC (no auth) |
| GET | `/api/seo/skills` | routes/marketplace.py:29 | seo_skills | PUBLIC (no auth) |
| GET | `/api/shortlist/broadcasts` | server.py:2198 | list_broadcast_history | role != 'employer' |
| GET | `/api/sitemap.xml` | routes/marketplace.py:80 | sitemap_xml | PUBLIC (no auth) |
| PATCH | `/api/admin/staff/{staff_id}` | routes/admin.py:264 | admin_update_staff | _require_scope(user, 'superadmin'); admin_permissions check |
| POST | `/api/accounts/connect` | server.py:2578 | connect_account | role not in prov['for']; role != 'admin' |
| POST | `/api/admin/bank-transfers/{payment_id}/approve` | routes/admin.py:57 | admin_bank_approve | _require_scope(user, 'finance') |
| POST | `/api/admin/bank-transfers/{payment_id}/reject` | routes/admin.py:73 | admin_bank_reject | _require_scope(user, 'finance') |
| POST | `/api/admin/grievances/{gid}/resolve` | routes/admin.py:115 | admin_resolve_grievance | has_admin_scope(user, 'support'); has_admin_scope(user, 'moderation') |
| POST | `/api/admin/rate-nudges/scan` | routes/admin.py:186 | admin_rate_nudge_scan | role != 'admin' |
| POST | `/api/admin/reviews/{rid}/approve` | routes/admin.py:89 | admin_approve_review | _require_scope(user, 'moderation') |
| POST | `/api/admin/reviews/{rid}/reject` | routes/admin.py:98 | admin_reject_review | _require_scope(user, 'moderation') |
| POST | `/api/admin/staff` | routes/admin.py:242 | admin_create_staff | _require_scope(user, 'superadmin') |
| POST | `/api/admin/users/{uid}/adjust` | routes/admin.py:383 | admin_adjust_user | _require_scope(user, 'support') |
| POST | `/api/admin/users/{uid}/notes` | routes/admin.py:359 | admin_add_note | _require_scope(user, 'support') |
| POST | `/api/engagements/sign` | server.py:645 | sign_contract | ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) |
| POST | `/api/messages` | server.py:944 | post_message | ownership: user['id'] not in (eng.get('employer_id'), eng.get('talent_id')) |
| POST | `/api/messages/upload` | server.py:2284 | upload_message_attachment | ownership: user['id'] not in (eng.get('employer_id'), eng.get('talent_id')) |
| POST | `/api/newsletter/signup` | server.py:2226 | newsletter_signup | PUBLIC (no auth) |
| POST | `/api/pricing/quote` | server.py:2103 | price_quote | PUBLIC (no auth) |
| PUT | `/api/admin/customization` | routes/admin.py:436 | admin_put_customization | _require_scope(user, 'customization') |


### 4b. In FEATURES.md tables, missing from code (1)

| Method | Path | FEATURES section | Location claim | Auth claim |
| --- | --- | --- | --- | --- |
| POST | `/api/engagements/{id}/sign` | §11. Engagements + contract signing + deliverables | `backend/server.py` (grep `/sign`) | auth (party) |


### 4c. Auth-claim mismatches (13)

Docs and code disagree on the authz shape:

| Method | Path | file:line | Code enforces | FEATURES claims |
| --- | --- | --- | --- | --- |
| GET | `/api/integrations/providers` | server.py:2341 | PUBLIC (no auth) | auth |
| GET | `/api/payments/mine` | server.py:486 | auth (no role/scope in body) | role=employer |
| GET | `/api/projects/templates/{}/team-suggestions` | server.py:1968 | PUBLIC (no auth) | auth |
| GET | `/api/talent/me/broadcasts/stream` | server.py:2145 | role != 'talent' | role=talent (SSE token) |
| POST | `/api/deliverables` | server.py:665 | ownership: user['id'] != eng.get('talent_id') | role=talent |
| POST | `/api/deliverables/{}/approve` | server.py:770 | auth (no role/scope in body) | role=employer |
| POST | `/api/deliverables/{}/dispute` | routes/revisions.py:236 | auth (no role/scope in body) | role=talent |
| POST | `/api/deliverables/{}/reject` | server.py:775 | auth (no role/scope in body) | role=employer |
| POST | `/api/deliverables/{}/request-revision` | routes/revisions.py:135 | auth (no role/scope in body) | role=employer (party) |
| POST | `/api/deliverables/{}/resubmit` | routes/revisions.py:189 | auth (no role/scope in body) | role=talent (party) |
| POST | `/api/eoi/{}/withdraw` | server.py:2535 | ownership: user['id'] != eoi['talent_id'] | role=talent |
| POST | `/api/payments/bank/submit` | server.py:468 | auth (no role/scope in body) | role=employer |
| POST | `/api/projects/lead` | server.py:2023 | PUBLIC (no auth) | auth |


### 4d. Auth-claim unknowns (23)

FEATURES.md uses a free-form phrase (e.g. "auth (party)", "auth (payer/other party/admin)")
that the diff tool can't machine-verify against code. Not necessarily wrong — needs a human eye.

| Method | Path | file:line | Code enforces | FEATURES claims |
| --- | --- | --- | --- | --- |
| GET | `/api/deliverables/{}` | server.py:686 | ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) | auth (party) |
| GET | `/api/deliverables/{}/revision-summary` | routes/revisions.py:497 | auth (no role/scope in body) | auth (party or moderation admin) |
| GET | `/api/deliverables/{}/revisions` | routes/revisions.py:218 | auth (no role/scope in body) | auth (party or moderation admin) |
| GET | `/api/engagements/{}` | server.py:637 | ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) | auth (party) |
| GET | `/api/grievances/{}/fee-status` | routes/revisions.py:669 | has_admin_scope(user, 'moderation'); ownership: user['id'] not in (g.get('talent_id'), g.get('employer_id')) | auth (payer/other party/admin) |
| GET | `/api/invoices/mine` | routes/projects.py:904 | role == 'admin'; role == 'employer' | auth (admin sees all, employer sees own) |
| GET | `/api/projects/mine` | routes/projects.py:227 | role == 'admin'; role == 'employer' | auth (employer sees own) |
| GET | `/api/projects/workspace/{}` | routes/projects.py:239 | auth (no role/scope in body) | auth (admin or `employer_id==user.id`) |
| GET | `/api/projects/workspace/{}/alerts` | routes/projects.py:437 | auth (no role/scope in body) | auth (party) |
| GET | `/api/projects/workspace/{}/invoices/{}/pdf` | routes/projects.py:753 | auth (no role/scope in body) | auth (party) |
| PATCH | `/api/projects/workspace/{}/phases/{}` | routes/projects.py:289 | auth (no role/scope in body) | auth (party) |
| PATCH | `/api/projects/workspace/{}/risks/{}` | routes/projects.py:500 | auth (no role/scope in body) | auth (party) |
| POST | `/api/alerts/{}/read` | routes/projects.py:461 | role != 'admin'; ownership: user['id'] != a.get('employer_id') | auth (party) |
| POST | `/api/eoi` | server.py:2465 | role != 'talent' | auth (talent flow) |
| POST | `/api/grievances/{}/pay-fee` | routes/revisions.py:587 | ownership: user['id'] != payer_id | auth (payer) |
| POST | `/api/integrations/crm/push-lead` | routes/auth.py:1037 | auth (no role/scope in body) | employer/admin |
| POST | `/api/integrations/crm/sync-now` | routes/auth.py:1183 | role not in ('employer', 'admin') | employer/admin |
| POST | `/api/projects/workspace/{}/milestones` | routes/projects.py:549 | auth (no role/scope in body) | auth (party) |
| POST | `/api/projects/workspace/{}/milestones/{}/checkout` | routes/projects.py:781 | role == 'admin'; ownership: user['id'] == project.get('employer_id') | admin OR `employer_id==user.id` |
| POST | `/api/projects/workspace/{}/risks` | routes/projects.py:475 | auth (no role/scope in body) | auth (party) |
| POST | `/api/projects/workspace/{}/variances` | routes/projects.py:406 | auth (no role/scope in body) | auth (party) |
| POST | `/api/reviews` | server.py:781 | ownership: user['id'] not in (eng['employer_id'], eng['talent_id']) | auth (party) |
| PUT | `/api/projects/workspace/{}/raci` | routes/projects.py:526 | auth (no role/scope in body) | auth (party) |


---

## 5. Cross-references to `SECURITY_BACKLOG.md`

Every YAML entry in `security/public_routes.yml` may carry a `backlog_id`. The
renderer builds this table from those pointers so a reviewer can walk from a
scan finding to the ranked backlog and back.

| Backlog ID | Method | Path | file:line | Inventory § | Summary |
| --- | --- | --- | --- | --- | --- |
| S-23 | POST | `/api/projects/lead` | server.py:2023 | §2b | S-23 (P1). FEATURES §16 tables list this as `auth`. Currently anyone can POST a project_leads row with a forged employer_id. Lead-forgery + attribution poisoning + queue-spam vector. |
| S-24 | GET | `/api/projects/templates/{template_id}/team-suggestions` | server.py:1968 | §2b | S-24 (P1). Returns _CURATED_TALENT names + hourly rates + sell-rate/margin math to any unauthenticated caller — crown-jewel supply pool per CONTRACTOR_SPLIT.md. FEATURES §16 claims `auth`. |


---

## 6. Reproduce

```
python3 docs/scripts/route_scan.py
python3 docs/scripts/features_scan.py
python3 docs/scripts/diff.py
python3 docs/scripts/render_inventory.py
```

All four accept `--backend`, `--features`, `--routes`, `--diff`, `--public-yaml`, `--out` as appropriate; defaults are repo-relative. Artifacts land under `docs/scripts/.artifacts/`.
