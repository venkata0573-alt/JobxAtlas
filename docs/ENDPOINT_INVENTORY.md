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
- "Body scope/role check" is what the handler actually enforces at request time. Only comparisons whose left-hand receiver is literally the `user` variable are treated as authorization — loop-variable classifications like `u.get("role")` are excluded.
- "NO-AUTH" flag = no `Depends(get_current_user)`, no `_require_scope`/`has_admin_scope`, no `user["role"]`/`user.get("role")` comparison, no `admin_permissions` inspection. Unrelated `Depends(...)` (e.g. rate-limiter) do NOT suppress this flag. Some public routes are still gated by out-of-band checks (Stripe signature on the webhook, emailed token on `/reference-check/{token}`).
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
| POST | `/api/auth/register` | routes/auth.py:114 | — (public) |  | **NO-AUTH** |
| GET | `/api/auth/verify-email` | routes/auth.py:157 | — (public) |  | **NO-AUTH** |
| POST | `/api/auth/resend-verification` | routes/auth.py:175 | get_current_user |  |  |
| POST | `/api/auth/login` | routes/auth.py:186 | — (public) |  | **NO-AUTH** |
| POST | `/api/auth/logout` | routes/auth.py:197 | — (public) |  | **NO-AUTH** |
| GET | `/api/auth/me` | routes/auth.py:204 | get_current_user |  |  |
| PUT | `/api/profile` | routes/auth.py:209 | get_current_user |  |  |
| POST | `/api/profile/suggest-rate` | routes/auth.py:216 | get_current_user |  |  |
| POST | `/api/verification/company` | routes/auth.py:257 | get_current_user | body: role != 'employer' |  |
| POST | `/api/verification/bgv` | routes/auth.py:278 | get_current_user | body: role != 'talent' |  |
| GET | `/api/reference-check/{token}` | routes/auth.py:352 | — (public) |  | **NO-AUTH** |
| POST | `/api/reference-check/{token}` | routes/auth.py:375 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/stats` | routes/auth.py:413 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/timeseries` | routes/auth.py:443 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/timeseries/details` | routes/auth.py:524 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/timeseries/details/pdf` | routes/auth.py:668 | — (public) |  | **NO-AUTH** |
| POST | `/api/trust/verify-drill` | routes/auth.py:726 | — (public) |  | **NO-AUTH** |
| GET | `/api/trust/verify-drill/{signature}` | routes/auth.py:743 | — (public) |  | **NO-AUTH** |
| GET | `/api/admin/reference-checks/{talent_id}` | routes/auth.py:884 | get_current_user | has_admin_scope(user, 'moderation'); has_admin_scope(user, 'support') |  |
| GET | `/api/verification/me` | routes/auth.py:898 | get_current_user |  |  |
| POST | `/api/integrations/crm/connect` | routes/auth.py:972 | get_current_user | body: role not in ('employer', 'admin') |  |
| GET | `/api/integrations/crm` | routes/auth.py:998 | get_current_user |  |  |
| DELETE | `/api/integrations/crm/{provider}` | routes/auth.py:1006 | get_current_user |  |  |
| POST | `/api/integrations/crm/push-lead` | routes/auth.py:1020 | get_current_user |  |  |
| POST | `/api/integrations/crm/sync-now` | routes/auth.py:1166 | get_current_user | body: role not in ('employer', 'admin') |  |
| GET | `/api/integrations/crm/sync-log` | routes/auth.py:1175 | get_current_user |  |  |
| GET | `/api/seo/skills` | routes/marketplace.py:27 | — (public) |  | **NO-AUTH** |
| GET | `/api/seo/city-skills` | routes/marketplace.py:32 | — (public) |  | **NO-AUTH** |
| GET | `/api/sitemap.xml` | routes/marketplace.py:78 | — (public) |  | **NO-AUTH** |
| GET | `/api/marketplace/industries` | routes/marketplace.py:91 | — (public) |  | **NO-AUTH** |
| GET | `/api/marketplace/stats` | routes/marketplace.py:109 | — (public) |  | **NO-AUTH** |
| POST | `/api/shortlist` | routes/marketplace.py:157 | get_current_user | body: role != 'employer' |  |
| GET | `/api/shortlist` | routes/marketplace.py:182 | get_current_user | body: role != 'employer' |  |
| DELETE | `/api/shortlist/{talent_id}` | routes/marketplace.py:190 | get_current_user | body: role != 'employer' |  |
| POST | `/api/admin/project-leads/{lead_id}/convert` | routes/projects.py:134 | get_current_user | has_admin_scope(user, 'superadmin') |  |
| GET | `/api/admin/project-leads` | routes/projects.py:217 | get_current_user | has_admin_scope(user, 'support'); has_admin_scope(user, 'superadmin') |  |
| GET | `/api/projects/mine` | routes/projects.py:225 | get_current_user | body: role == 'admin'; body: role == 'employer' |  |
| GET | `/api/projects/workspace/{project_id}` | routes/projects.py:237 | get_current_user |  |  |
| PATCH | `/api/projects/workspace/{project_id}/phases/{phase_id}` | routes/projects.py:287 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/variances` | routes/projects.py:405 | get_current_user |  |  |
| GET | `/api/projects/workspace/{project_id}/alerts` | routes/projects.py:436 | get_current_user |  |  |
| GET | `/api/alerts/mine` | routes/projects.py:445 | get_current_user | body: role == 'admin'; body: role == 'employer' |  |
| POST | `/api/alerts/{alert_id}/read` | routes/projects.py:460 | get_current_user | body: role != 'admin' |  |
| POST | `/api/projects/workspace/{project_id}/risks` | routes/projects.py:474 | get_current_user |  |  |
| PATCH | `/api/projects/workspace/{project_id}/risks/{risk_id}` | routes/projects.py:499 | get_current_user |  |  |
| PUT | `/api/projects/workspace/{project_id}/raci` | routes/projects.py:525 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/milestones` | routes/projects.py:548 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/milestones/{milestone_id}/invoice` | routes/projects.py:585 | get_current_user | has_admin_scope(user, 'finance'); has_admin_scope(user, 'superadmin') |  |
| POST | `/api/projects/workspace/{project_id}/milestones/{milestone_id}/paid` | routes/projects.py:615 | get_current_user | has_admin_scope(user, 'finance'); has_admin_scope(user, 'superadmin') |  |
| GET | `/api/projects/workspace/{project_id}/invoices/{invoice_id}/pdf` | routes/projects.py:752 | get_current_user |  |  |
| POST | `/api/projects/workspace/{project_id}/milestones/{milestone_id}/checkout` | routes/projects.py:780 | get_current_user | body: role == 'admin' |  |
| GET | `/api/projects/milestone-payment/status/{session_id}` | routes/projects.py:866 | get_current_user |  |  |
| GET | `/api/invoices/mine` | routes/projects.py:903 | get_current_user | body: role == 'admin'; body: role == 'employer' |  |
| POST | `/api/billing/setup-checkout` | routes/projects.py:974 | get_current_user | body: role != 'employer' |  |
| GET | `/api/billing/setup-checkout/status/{session_id}` | routes/projects.py:1013 | get_current_user | body: role != 'employer' |  |
| POST | `/api/billing/setup` | routes/projects.py:1052 | get_current_user | body: role != 'employer' |  |
| GET | `/api/billing/status` | routes/projects.py:1090 | get_current_user | body: role != 'employer' |  |
| POST | `/api/admin/invoices/scan-overdue` | routes/projects.py:1326 | get_current_user | has_admin_scope(user, 'finance'); has_admin_scope(user, 'superadmin') |  |
| POST | `/api/admin/projects/{project_id}/save-as-template` | routes/projects.py:1354 | get_current_user | has_admin_scope(user, 'superadmin'); has_admin_scope(user, 'customization') |  |
| GET | `/api/admin/verifications-with-refs` | routes/projects.py:1412 | get_current_user | has_admin_scope(user, 'moderation'); has_admin_scope(user, 'support') |  |
| POST | `/api/deliverables/{deliverable_id}/request-revision` | routes/revisions.py:134 | get_current_user |  |  |
| POST | `/api/deliverables/{deliverable_id}/resubmit` | routes/revisions.py:188 | get_current_user |  |  |
| GET | `/api/deliverables/{deliverable_id}/revisions` | routes/revisions.py:217 | get_current_user |  |  |
| POST | `/api/deliverables/{deliverable_id}/dispute` | routes/revisions.py:235 | get_current_user |  |  |
| GET | `/api/admin/revisions` | routes/revisions.py:291 | get_current_user | has_admin_scope(user, 'moderation') |  |
| POST | `/api/admin/revisions/{grievance_id}/rule` | routes/revisions.py:312 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/employers-flagged` | routes/revisions.py:415 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/revisions/refund-analytics` | routes/revisions.py:428 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/deliverables/{deliverable_id}/revision-summary` | routes/revisions.py:496 | get_current_user |  |  |
| GET | `/api/talent/me/recovery-status` | routes/revisions.py:542 | get_current_user | body: role != 'talent' |  |
| POST | `/api/grievances/{grievance_id}/pay-fee` | routes/revisions.py:586 | get_current_user |  |  |
| GET | `/api/grievances/{grievance_id}/fee-status` | routes/revisions.py:668 | get_current_user | has_admin_scope(user, 'moderation') |  |
| POST | `/api/admin/grievances/{grievance_id}/refund-fee` | routes/revisions.py:736 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/revisions/refund-audit/pdf` | routes/revisions.py:929 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/admin/revisions/refund-audit/verify/{signature}` | routes/revisions.py:972 | get_current_user | has_admin_scope(user, 'moderation') |  |
| GET | `/api/talent` | server.py:231 | — (public) |  | **NO-AUTH** |
| GET | `/api/employers` | server.py:328 | get_current_user | body: role not in ('talent', 'admin') |  |
| GET | `/api/employers/{employer_id}` | server.py:381 | get_current_user | body: role not in ('talent', 'admin') |  |
| GET | `/api/earnings/mine` | server.py:403 | get_current_user | body: role != 'talent' |  |
| GET | `/api/talent/{talent_id}` | server.py:412 | get_current_user | body: role != 'employer' |  |
| GET | `/api/packages` | server.py:432 | — (public) |  | **NO-AUTH** |
| POST | `/api/payments/bank/initiate` | server.py:443 | get_current_user | body: role != 'employer' |  |
| POST | `/api/payments/bank/submit` | server.py:470 | get_current_user |  |  |
| GET | `/api/payments/mine` | server.py:488 | get_current_user |  |  |
| POST | `/api/payments/checkout` | server.py:495 | get_current_user | body: role != 'employer' |  |
| GET | `/api/payments/status/{session_id}` | server.py:542 | — (public) |  | **NO-AUTH** |
| POST | `/api/stripe/webhook` | server.py:557 | — (public) |  | **NO-AUTH** |
| POST | `/api/engagements` | server.py:602 | get_current_user | body: role != 'employer' |  |
| GET | `/api/engagements` | server.py:632 | get_current_user | body: role == 'employer' |  |
| GET | `/api/engagements/{eid}` | server.py:639 | get_current_user |  |  |
| POST | `/api/engagements/sign` | server.py:647 | get_current_user |  |  |
| POST | `/api/deliverables` | server.py:667 | get_current_user |  |  |
| GET | `/api/deliverables/{engagement_id}` | server.py:688 | get_current_user |  |  |
| POST | `/api/deliverables/{deliverable_id}/approve` | server.py:772 | get_current_user |  |  |
| POST | `/api/deliverables/{deliverable_id}/reject` | server.py:777 | get_current_user |  |  |
| POST | `/api/reviews` | server.py:783 | get_current_user |  |  |
| GET | `/api/reviews/user/{user_id}` | server.py:807 | — (public) |  | **NO-AUTH** |
| POST | `/api/grievances` | server.py:818 | — (public) |  | **NO-AUTH** |
| GET | `/api/payouts/mine` | server.py:874 | get_current_user | body: role != 'talent' |  |
| GET | `/api/referrals/mine` | server.py:886 | get_current_user |  |  |
| POST | `/api/referrals/claim` | server.py:896 | get_current_user |  |  |
| GET | `/api/messages/{engagement_id}` | server.py:937 | get_current_user |  |  |
| POST | `/api/messages` | server.py:946 | get_current_user |  |  |
| GET | `/api/seo/hire/{skill_slug}` | server.py:972 | — (public) |  | **NO-AUTH** |
| GET | `/api/employer/overview` | server.py:997 | get_current_user | body: role != 'employer' |  |
| GET | `/api/seo/hire-city/{slug}` | server.py:1344 | — (public) |  | **NO-AUTH** |
| GET | `/api/talent/me/rate-nudge` | server.py:1479 | get_current_user | body: role != 'talent' |  |
| POST | `/api/talent/me/rate-nudge/dismiss` | server.py:1488 | get_current_user | body: role != 'talent' |  |
| POST | `/api/shortlist/broadcast` | server.py:1508 | get_current_user | body: role != 'employer' |  |
| GET | `/api/projects/templates` | server.py:1881 | — (public) |  | **NO-AUTH** |
| GET | `/api/projects/templates/{template_id}` | server.py:1889 | — (public) |  | **NO-AUTH** |
| GET | `/api/projects/templates/{template_id}/team-suggestions` | server.py:1970 | — (public) |  | **NO-AUTH** |
| POST | `/api/projects/lead` | server.py:2025 | — (public) |  | **NO-AUTH** |
| GET | `/api/pricing/tiers` | server.py:2093 | — (public) |  | **NO-AUTH** |
| POST | `/api/pricing/quote` | server.py:2105 | — (public) |  | **NO-AUTH** |
| GET | `/api/auth/sse-token` | server.py:2115 | get_current_user |  |  |
| GET | `/api/talent/me/broadcasts` | server.py:2122 | get_current_user | body: role != 'talent' |  |
| GET | `/api/talent/me/broadcasts/stream` | server.py:2147 | get_current_user | body: role != 'talent' |  |
| GET | `/api/shortlist/broadcasts` | server.py:2200 | get_current_user | body: role != 'employer' |  |
| POST | `/api/talent/me/broadcasts/{broadcast_doc_id}/read` | server.py:2210 | get_current_user | body: role != 'talent' |  |
| POST | `/api/newsletter/signup` | server.py:2228 | — (public) |  | **NO-AUTH** |
| POST | `/api/files/upload` | server.py:2245 | get_current_user |  |  |
| POST | `/api/messages/upload` | server.py:2286 | get_current_user |  |  |
| GET | `/api/files/{file_id}` | server.py:2323 | get_current_user |  |  |
| GET | `/api/integrations/providers` | server.py:2343 | — (public) |  | **NO-AUTH** |
| POST | `/api/integrations/connect` | server.py:2348 | get_current_user |  |  |
| DELETE | `/api/integrations/{integration_id}` | server.py:2372 | get_current_user |  |  |
| POST | `/api/integrations/sync/{integration_id}` | server.py:2379 | get_current_user |  |  |
| POST | `/api/work/upload` | server.py:2399 | get_current_user |  |  |
| GET | `/api/work/items` | server.py:2425 | get_current_user |  |  |
| PUT | `/api/availability` | server.py:2432 | get_current_user |  |  |
| GET | `/api/availability/{user_id}` | server.py:2438 | get_current_user |  |  |
| GET | `/api/calendar/events` | server.py:2448 | get_current_user | body: role == 'employer'; body: role == 'talent' |  |
| POST | `/api/eoi` | server.py:2467 | get_current_user | body: role != 'talent' |  |
| GET | `/api/eoi` | server.py:2491 | get_current_user | body: role == 'talent'; body: role == 'employer' |  |
| POST | `/api/eoi/{eoi_id}/accept` | server.py:2503 | get_current_user | body: role != 'employer' |  |
| POST | `/api/eoi/{eoi_id}/withdraw` | server.py:2537 | get_current_user |  |  |
| GET | `/api/accounts/providers` | server.py:2568 | get_current_user |  |  |
| GET | `/api/accounts` | server.py:2574 | get_current_user |  |  |
| POST | `/api/accounts/connect` | server.py:2580 | get_current_user | body: role not in prov['for']; body: role != 'admin' |  |
| DELETE | `/api/accounts/{account_id}` | server.py:2605 | get_current_user |  |  |
| GET | `/api/pricing` | server.py:2613 | — (public) |  | **NO-AUTH** |
| GET | `/api/legal` | server.py:2651 | — (public) |  | **NO-AUTH** |
| GET | `/api/dashboard/metrics` | server.py:2673 | get_current_user |  |  |
| DELETE | `/api/work/items/{item_id}` | server.py:2735 | get_current_user |  |  |


---

## 2. Routes with no authorization check

### 2a. Intentional public surface (33 routes)

Listed in `security/public_routes.yml`:`intentional_public`. Adding a new public
route without listing it here trips `backend/tests/test_public_surface.py`.

| Method | Path | file:line | Handler | Reason |
| --- | --- | --- | --- | --- |
| GET | `/api/customization/public` | routes/admin.py:452 | public_customization | Public tenant customization payload for header/hero. FEATURES §21. |
| POST | `/api/auth/register` | routes/auth.py:114 | register | Public registration; Turnstile-gated (fails open when TURNSTILE_SECRET_KEY unset). FEATURES §3. |
| GET | `/api/auth/verify-email` | routes/auth.py:157 | verify_email | Public email-verification token consumption; FEATURES §3. |
| POST | `/api/auth/login` | routes/auth.py:186 | login | Public login; bcrypt + Turnstile. FEATURES §3. |
| POST | `/api/auth/logout` | routes/auth.py:197 | logout | Idempotent cookie clear; FEATURES §3. |
| GET | `/api/reference-check/{token}` | routes/auth.py:352 | reference_check_get | Public referee form; gated by emailed one-time token in path. FEATURES §15. |
| POST | `/api/reference-check/{token}` | routes/auth.py:375 | reference_check_post | Public referee submit; same one-time token gate. FEATURES §15. |
| GET | `/api/trust/stats` | routes/auth.py:413 | public_trust_stats | Public /trust page metrics. FEATURES §4. |
| GET | `/api/trust/timeseries` | routes/auth.py:443 | public_trust_timeseries | Public /trust page timeseries. FEATURES §4. |
| GET | `/api/trust/timeseries/details` | routes/auth.py:524 | public_trust_timeseries_details | Public /trust drill-through. FEATURES §4. |
| GET | `/api/trust/timeseries/details/pdf` | routes/auth.py:668 | public_trust_timeseries_pdf | Public signed PDF export; writes a drill_receipts row. FEATURES §4. |
| POST | `/api/trust/verify-drill` | routes/auth.py:726 | public_verify_drill | Public tamper-check POST; FEATURES §4 (also listed as no-UI in FEATURES 'Dead ends'). |
| GET | `/api/trust/verify-drill/{signature}` | routes/auth.py:743 | public_verify_drill_lookup | Public signature lookup driven by QR code in the PDF. FEATURES §4. |
| GET | `/api/seo/skills` | routes/marketplace.py:27 | seo_skills | SEO skill index. Public marketing surface. |
| GET | `/api/seo/city-skills` | routes/marketplace.py:32 | seo_city_skills | SEO city×skill index. Public marketing surface. |
| GET | `/api/sitemap.xml` | routes/marketplace.py:78 | sitemap_xml | Public sitemap for crawlers. |
| GET | `/api/marketplace/industries` | routes/marketplace.py:91 | marketplace_industries | Public industry list for Register form + SEO. FEATURES §5/§8. |
| GET | `/api/marketplace/stats` | routes/marketplace.py:109 | marketplace_stats | Public marketplace stats. FEATURES §8. |
| GET | `/api/talent` | server.py:231 | list_talent | Public browse endpoint powering /browse. FEATURES §8. |
| GET | `/api/packages` | server.py:432 | get_packages | Public hour-package catalog for /employer/purchase. FEATURES §10. |
| GET | `/api/payments/status/{session_id}` | server.py:542 | payment_status | Polled by /payment/success without a session (session_id from Stripe URL). FEATURES §10. |
| POST | `/api/stripe/webhook` | server.py:557 | stripe_webhook | Gated by stripe.Webhook.construct_event signature verification at server.py:562. Cookie auth is inapplicable. |
| GET | `/api/reviews/user/{user_id}` | server.py:807 | reviews_for_user | Public reviews on talent card. FEATURES §11. |
| POST | `/api/grievances` | server.py:818 | submit_grievance | Public grievance-officer submission form. FEATURES §2. |
| GET | `/api/seo/hire/{skill_slug}` | server.py:972 | seo_hire | Public /hire/:slug landing page. FEATURES §8. |
| GET | `/api/seo/hire-city/{slug}` | server.py:1344 | seo_hire_city | Public /hire/city landing page. FEATURES §8. |
| GET | `/api/projects/templates` | server.py:1881 | list_project_templates | Public template catalog (Projects.jsx renders it before login). FEATURES §16. |
| GET | `/api/projects/templates/{template_id}` | server.py:1889 | get_project_template | Public template detail; consumed by anonymous browsing. FEATURES §16. |
| GET | `/api/pricing/tiers` | server.py:2093 | get_pricing_tiers | Public tiers subset of /api/pricing. FEATURES §10 (Dead ends: no UI caller). |
| POST | `/api/pricing/quote` | server.py:2105 | price_quote | Public quote calculator. FEATURES §10 (Dead ends: no UI caller). |
| POST | `/api/newsletter/signup` | server.py:2228 | newsletter_signup | Public newsletter waitlist from SEO landing pages. |
| GET | `/api/pricing` | server.py:2613 | get_pricing | Public /pricing page. FEATURES §10. |
| GET | `/api/legal` | server.py:2651 | get_legal | Public static legal metadata. FEATURES §1. |


### 2b. Surprising — should probably require auth (3 routes)

Listed in `security/public_routes.yml`:`surprising_unauth`. Each row is a triage item.

| Method | Path | file:line | Handler | Why it's a surprise |
| --- | --- | --- | --- | --- |
| GET | `/api/projects/templates/{template_id}/team-suggestions` | server.py:1970 | suggest_team_for_template | S-24 (P1). Returns _CURATED_TALENT names + hourly rates + sell-rate/margin math to any unauthenticated caller — crown-jewel supply pool per CONTRACTOR_SPLIT.md. FEATURES §16 claims `auth`. |
| POST | `/api/projects/lead` | server.py:2025 | submit_project_lead | S-23 (P1). FEATURES §16 tables list this as `auth`. Currently anyone can POST a project_leads row with a forged employer_id. Lead-forgery + attribution poisoning + queue-spam vector. |
| GET | `/api/integrations/providers` | server.py:2343 | integration_providers | FEATURES §22 tables list this as `auth`. Low-sensitivity list of provider names, but the docs-vs-code claim disagrees. |



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
| DELETE | `/api/accounts/{account_id}` | server.py:2605 | disconnect_account | auth (no role/scope in body) |
| DELETE | `/api/admin/staff/{staff_id}` | routes/admin.py:296 | admin_delete_staff | _require_scope(user, 'superadmin'); admin_permissions check |
| DELETE | `/api/work/items/{item_id}` | server.py:2735 | delete_work_item | auth (no role/scope in body) |
| GET | `/api/accounts` | server.py:2574 | list_accounts | auth (no role/scope in body) |
| GET | `/api/accounts/providers` | server.py:2568 | account_providers | auth (no role/scope in body) |
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
| GET | `/api/employers/{employer_id}` | server.py:381 | get_employer_public | role not in ('talent', 'admin') |
| GET | `/api/files/{file_id}` | server.py:2323 | download_file | auth (no role/scope in body) |
| GET | `/api/legal` | server.py:2651 | get_legal | PUBLIC (no auth) |
| GET | `/api/messages/{engagement_id}` | server.py:937 | list_messages | auth (no role/scope in body) |
| GET | `/api/pricing/tiers` | server.py:2093 | get_pricing_tiers | PUBLIC (no auth) |
| GET | `/api/seo/city-skills` | routes/marketplace.py:32 | seo_city_skills | PUBLIC (no auth) |
| GET | `/api/seo/skills` | routes/marketplace.py:27 | seo_skills | PUBLIC (no auth) |
| GET | `/api/shortlist/broadcasts` | server.py:2200 | list_broadcast_history | role != 'employer' |
| GET | `/api/sitemap.xml` | routes/marketplace.py:78 | sitemap_xml | PUBLIC (no auth) |
| PATCH | `/api/admin/staff/{staff_id}` | routes/admin.py:264 | admin_update_staff | _require_scope(user, 'superadmin'); admin_permissions check |
| POST | `/api/accounts/connect` | server.py:2580 | connect_account | role not in prov['for']; role != 'admin' |
| POST | `/api/admin/bank-transfers/{payment_id}/approve` | routes/admin.py:57 | admin_bank_approve | _require_scope(user, 'finance') |
| POST | `/api/admin/bank-transfers/{payment_id}/reject` | routes/admin.py:73 | admin_bank_reject | _require_scope(user, 'finance') |
| POST | `/api/admin/grievances/{gid}/resolve` | routes/admin.py:115 | admin_resolve_grievance | has_admin_scope(user, 'support'); has_admin_scope(user, 'moderation') |
| POST | `/api/admin/rate-nudges/scan` | routes/admin.py:186 | admin_rate_nudge_scan | role != 'admin' |
| POST | `/api/admin/reviews/{rid}/approve` | routes/admin.py:89 | admin_approve_review | _require_scope(user, 'moderation') |
| POST | `/api/admin/reviews/{rid}/reject` | routes/admin.py:98 | admin_reject_review | _require_scope(user, 'moderation') |
| POST | `/api/admin/staff` | routes/admin.py:242 | admin_create_staff | _require_scope(user, 'superadmin') |
| POST | `/api/admin/users/{uid}/adjust` | routes/admin.py:383 | admin_adjust_user | _require_scope(user, 'support') |
| POST | `/api/admin/users/{uid}/notes` | routes/admin.py:359 | admin_add_note | _require_scope(user, 'support') |
| POST | `/api/engagements/sign` | server.py:647 | sign_contract | auth (no role/scope in body) |
| POST | `/api/messages` | server.py:946 | post_message | auth (no role/scope in body) |
| POST | `/api/messages/upload` | server.py:2286 | upload_message_attachment | auth (no role/scope in body) |
| POST | `/api/newsletter/signup` | server.py:2228 | newsletter_signup | PUBLIC (no auth) |
| POST | `/api/pricing/quote` | server.py:2105 | price_quote | PUBLIC (no auth) |
| PUT | `/api/admin/customization` | routes/admin.py:436 | admin_put_customization | _require_scope(user, 'customization') |


### 4b. In FEATURES.md tables, missing from code (1)

| Method | Path | FEATURES section | Location claim | Auth claim |
| --- | --- | --- | --- | --- |
| POST | `/api/engagements/{id}/sign` | §11. Engagements + contract signing + deliverables | `backend/server.py` (grep `/sign`) | auth (party) |


### 4c. Auth-claim mismatches (13)

Docs and code disagree on the authz shape:

| Method | Path | file:line | Code enforces | FEATURES claims |
| --- | --- | --- | --- | --- |
| GET | `/api/integrations/providers` | server.py:2343 | PUBLIC (no auth) | auth |
| GET | `/api/payments/mine` | server.py:488 | auth (no role/scope in body) | role=employer |
| GET | `/api/projects/templates/{}/team-suggestions` | server.py:1970 | PUBLIC (no auth) | auth |
| GET | `/api/talent/me/broadcasts/stream` | server.py:2147 | role != 'talent' | role=talent (SSE token) |
| POST | `/api/deliverables` | server.py:667 | auth (no role/scope in body) | role=talent |
| POST | `/api/deliverables/{}/approve` | server.py:772 | auth (no role/scope in body) | role=employer |
| POST | `/api/deliverables/{}/dispute` | routes/revisions.py:235 | auth (no role/scope in body) | role=talent |
| POST | `/api/deliverables/{}/reject` | server.py:777 | auth (no role/scope in body) | role=employer |
| POST | `/api/deliverables/{}/request-revision` | routes/revisions.py:134 | auth (no role/scope in body) | role=employer (party) |
| POST | `/api/deliverables/{}/resubmit` | routes/revisions.py:188 | auth (no role/scope in body) | role=talent (party) |
| POST | `/api/eoi/{}/withdraw` | server.py:2537 | auth (no role/scope in body) | role=talent |
| POST | `/api/payments/bank/submit` | server.py:470 | auth (no role/scope in body) | role=employer |
| POST | `/api/projects/lead` | server.py:2025 | PUBLIC (no auth) | auth |


### 4d. Auth-claim unknowns (23)

FEATURES.md uses a free-form phrase (e.g. "auth (party)", "auth (payer/other party/admin)")
that the diff tool can't machine-verify against code. Not necessarily wrong — needs a human eye.

| Method | Path | file:line | Code enforces | FEATURES claims |
| --- | --- | --- | --- | --- |
| GET | `/api/deliverables/{}` | server.py:688 | auth (no role/scope in body) | auth (party) |
| GET | `/api/deliverables/{}/revision-summary` | routes/revisions.py:496 | auth (no role/scope in body) | auth (party or moderation admin) |
| GET | `/api/deliverables/{}/revisions` | routes/revisions.py:217 | auth (no role/scope in body) | auth (party or moderation admin) |
| GET | `/api/engagements/{}` | server.py:639 | auth (no role/scope in body) | auth (party) |
| GET | `/api/grievances/{}/fee-status` | routes/revisions.py:668 | has_admin_scope(user, 'moderation') | auth (payer/other party/admin) |
| GET | `/api/invoices/mine` | routes/projects.py:903 | role == 'admin'; role == 'employer' | auth (admin sees all, employer sees own) |
| GET | `/api/projects/mine` | routes/projects.py:225 | role == 'admin'; role == 'employer' | auth (employer sees own) |
| GET | `/api/projects/workspace/{}` | routes/projects.py:237 | auth (no role/scope in body) | auth (admin or `employer_id==user.id`) |
| GET | `/api/projects/workspace/{}/alerts` | routes/projects.py:436 | auth (no role/scope in body) | auth (party) |
| GET | `/api/projects/workspace/{}/invoices/{}/pdf` | routes/projects.py:752 | auth (no role/scope in body) | auth (party) |
| PATCH | `/api/projects/workspace/{}/phases/{}` | routes/projects.py:287 | auth (no role/scope in body) | auth (party) |
| PATCH | `/api/projects/workspace/{}/risks/{}` | routes/projects.py:499 | auth (no role/scope in body) | auth (party) |
| POST | `/api/alerts/{}/read` | routes/projects.py:460 | role != 'admin' | auth (party) |
| POST | `/api/eoi` | server.py:2467 | role != 'talent' | auth (talent flow) |
| POST | `/api/grievances/{}/pay-fee` | routes/revisions.py:586 | auth (no role/scope in body) | auth (payer) |
| POST | `/api/integrations/crm/push-lead` | routes/auth.py:1020 | auth (no role/scope in body) | employer/admin |
| POST | `/api/integrations/crm/sync-now` | routes/auth.py:1166 | role not in ('employer', 'admin') | employer/admin |
| POST | `/api/projects/workspace/{}/milestones` | routes/projects.py:548 | auth (no role/scope in body) | auth (party) |
| POST | `/api/projects/workspace/{}/milestones/{}/checkout` | routes/projects.py:780 | role == 'admin' | admin OR `employer_id==user.id` |
| POST | `/api/projects/workspace/{}/risks` | routes/projects.py:474 | auth (no role/scope in body) | auth (party) |
| POST | `/api/projects/workspace/{}/variances` | routes/projects.py:405 | auth (no role/scope in body) | auth (party) |
| POST | `/api/reviews` | server.py:783 | auth (no role/scope in body) | auth (party) |
| PUT | `/api/projects/workspace/{}/raci` | routes/projects.py:525 | auth (no role/scope in body) | auth (party) |


---

## 5. Cross-references to `SECURITY_BACKLOG.md`

Every YAML entry in `security/public_routes.yml` may carry a `backlog_id`. The
renderer builds this table from those pointers so a reviewer can walk from a
scan finding to the ranked backlog and back.

| Backlog ID | Method | Path | file:line | Inventory § | Summary |
| --- | --- | --- | --- | --- | --- |
| S-23 | POST | `/api/projects/lead` | server.py:2025 | §2b | S-23 (P1). FEATURES §16 tables list this as `auth`. Currently anyone can POST a project_leads row with a forged employer_id. Lead-forgery + attribution poisoning + queue-spam vector. |
| S-24 | GET | `/api/projects/templates/{template_id}/team-suggestions` | server.py:1970 | §2b | S-24 (P1). Returns _CURATED_TALENT names + hourly rates + sell-rate/margin math to any unauthenticated caller — crown-jewel supply pool per CONTRACTOR_SPLIT.md. FEATURES §16 claims `auth`. |


---

## 6. Reproduce

```
python3 docs/scripts/route_scan.py
python3 docs/scripts/features_scan.py
python3 docs/scripts/diff.py
python3 docs/scripts/render_inventory.py
```

All four accept `--backend`, `--features`, `--routes`, `--diff`, `--public-yaml`, `--out` as appropriate; defaults are repo-relative. Artifacts land under `docs/scripts/.artifacts/`.
