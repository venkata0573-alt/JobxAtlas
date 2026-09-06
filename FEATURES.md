# FEATURES.md — Job Atlas / Geminista feature inventory

Follow the sections top-to-bottom. Each section names any earlier sections it depends on so you can skip around, but the default order walks you from a fresh empty database through every user role and every feature surface.

Base URLs assumed:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000` (all endpoints prefixed `/api` unless noted)

Repeated conventions:
- **Auth** column values: `public` = no cookie; `auth` = any logged-in user; `role=X` = requires that role; `scope=Y` = requires `has_admin_scope(user, "Y")` in addition to `role=admin`; `role==admin only` = the endpoint checks role directly (no scope subdivision).
- **Env blockers** call out which `.env` variable a step requires. Missing keys marked in the intro: no `EMERGENT_LLM_KEY`, no `RESEND_API_KEY`, dummy Stripe test keys, no `SLACK_WEBHOOK_URL`, no `TURNSTILE_SECRET_KEY`.

---

## 1. Legal & Compliance pages

**What it does.** Renders static company legal documents (Terms, Privacy, Refund Policy, Acceptable Use, Cookie Notice) plus the Sub-Processor Register and the public DPIA. No backend data — the pages import their content from `frontend/src/legal/content.js`.

**Backend endpoints.** None. All content is client-side.

**Frontend entry points.**
- `/legal` → `frontend/src/pages/Legal.jsx`
- `/subprocessors` → `frontend/src/pages/SubProcessors.jsx`
- `/dpia` → `frontend/src/pages/DPIA.jsx`

**Data model.** None (static imports).

**Manual test steps.**
1. Visit `http://localhost:3000/legal`. You should see Terms, Privacy, Refund, AUP, Cookie Notice with company metadata (Denkoit Softech Pvt. Ltd., CIN `U93030TG2017PTC119844`).
2. Visit `/subprocessors`. Confirm the tables render by category (Payments, Cloud, Email, AI, Storage, BGV, Fraud, Integrations).
3. Visit `/dpia`. Confirm 6-section DPIA with the risk table + Grievance Officer contact.
4. First-load the site in an incognito window: the Cookie Consent banner should appear at the bottom with **Accept all / Necessary only / Customize**. Click **Necessary only**. Reload — banner should not reappear.

**Blocked locally.** Nothing.

---

## 2. Grievance officer submission

**What it does.** Public web-form for filing grievances (IT Rules 2021 / DPDP). Writes a record and logs the reference; no email is sent locally without `RESEND_API_KEY`.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/grievances` | `backend/server.py:818` | public |

**Frontend entry points.**
- `/grievance` → `frontend/src/pages/Grievance.jsx`

**Data model.** Writes `grievances` (kind unset for general grievances, `status="received"`, `contact_email`, `subject`, `description`, `engagement_id?`, `against_party_id?`, `incident_date?`, `source_ip`).

**Manual test steps.**
1. Visit `/grievance`. Fill Subject, Description, Contact email.
2. Submit. You should see a success card with a reference ID and `email_to: grievance@geminista.com`.
3. Verify in Mongo: `db.grievances.find({}, {ref:1, subject:1, status:1}).sort({_id:-1}).limit(1)`.

**Blocked locally.** Email routing to the officer requires `RESEND_API_KEY`. The DB record is created either way — check Mongo directly to confirm.

---

## 3. Auth: register, login, session, current user

**What it does.** Registers users (role `talent` or `employer`), issues httpOnly `access_token` + `refresh_token` cookies with `SameSite=None`. Login is email+bcrypt. `GET /api/auth/me` returns the cookie-hydrated user. Also handles logout and resend-verification.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | `backend/routes/auth.py:115` | public |
| POST | `/api/auth/login` | `backend/routes/auth.py:187` | public |
| POST | `/api/auth/logout` | `backend/routes/auth.py:198` | public |
| GET | `/api/auth/me` | `backend/routes/auth.py:205` | auth |
| PUT | `/api/profile` | `backend/routes/auth.py:210` | auth |
| POST | `/api/profile/suggest-rate` | `backend/routes/auth.py:217` | auth |
| GET | `/api/auth/verify-email?token=` | `backend/routes/auth.py:158` | public |
| POST | `/api/auth/resend-verification` | `backend/routes/auth.py:176` | auth |
| GET | `/api/verification/me` | `backend/routes/auth.py:899` | auth |
| GET | `/api/auth/sse-token` | `backend/server.py` (grep for `sse-token`) | auth |

**Frontend entry points.**
- `/login` → `frontend/src/pages/Login.jsx`
- `/register` → `frontend/src/pages/Register.jsx`
- `/verify-email?token=` → `frontend/src/pages/VerifyEmail.jsx`

**Data model.** Reads/writes `users` (email, password_hash, role, profile, hours_balance, verification fields, email_verification_token).

**Manual test steps.**
1. From an empty DB, visit `/register`. The industry dropdown fetches `GET /api/marketplace/industries` (0-user counts is fine).
2. Register a **talent** account: name `Alex Talent`, email `alex@test.local`, password `Passw0rd!`, role Talent. Turnstile widget will render a test token (or auto-pass — no `TURNSTILE_SECRET_KEY` means the backend accepts any/empty token; see `_verify_turnstile` at `auth.py:64`).
3. Submit. You should be redirected to `/talent`.
4. Log out (Header menu). Visit `/register` again and create an **employer** account: `EmpCo`, `emp@test.local`, role Employer, industry Technology.
5. Log out. Visit `/login` and log back in as `alex@test.local`. You should land on `/talent` (dashboard).
6. Create a third **admin** account by inserting directly into Mongo (no self-serve admin registration exists):
   ```
   mongosh <db>
   db.users.insertOne({id:"admin-1", email:"admin@test.local", role:"admin", name:"Root Admin",
     password_hash:"<bcrypt of Passw0rd!>", admin_permissions:["support","moderation","finance","customization","superadmin"],
     created_at: new Date().toISOString()})
   ```
   Generate a bcrypt hash from the backend REPL: `from passlib.hash import bcrypt; bcrypt.hash("Passw0rd!")`. Then log in at `/login` as `admin@test.local`.

**Blocked locally.**
- Email verification email delivery requires `RESEND_API_KEY`. The token is persisted on the user doc (`users.email_verification_token`). Bypass:
  ```
  db.users.findOne({email:"alex@test.local"}, {email_verification_token:1})
  ```
  Then open `http://localhost:3000/verify-email?token=<that>` to complete verification.
- Turnstile is disabled since no `TURNSTILE_SECRET_KEY`. `_verify_turnstile` returns True.
- `POST /api/profile/suggest-rate` requires `EMERGENT_LLM_KEY`. Without it, `ai_service.suggest_hourly_rate` returns the rule-based fallback `{low: max(15, base-15), mid: base, high: base+25}` where `base = 20 + years*6`. Fully exercisable locally, just without live LLM prose.

---

## 4. Trust Page (public metrics)

**What it does.** Public trust-signal page: verified counts, engagements signed, 30-day timeseries, drill-through rows (anonymised), and a signed PDF export with QR verification.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| GET | `/api/trust/stats` | `backend/routes/auth.py:414` | public |
| GET | `/api/trust/timeseries` | `backend/routes/auth.py:444` | public |
| GET | `/api/trust/timeseries/details?series=` | `backend/routes/auth.py:525` | public |
| GET | `/api/trust/timeseries/details/pdf?series=&q=` | `backend/routes/auth.py:669` | public |
| POST | `/api/trust/verify-drill` | `backend/routes/auth.py:727` | public |
| GET | `/api/trust/verify-drill/{signature}` | `backend/routes/auth.py:744` | public |

**Frontend entry points.**
- `/trust` → `frontend/src/pages/Trust.jsx`

**Data model.** Reads `users`, `reference_checks`, `engagements`. Writes `drill_receipts` on PDF export.

**Manual test steps.**
1. Visit `/trust`. All counts will be 0 or low right after step 3 in Auth. Charts should still render with 30 empty daily buckets.
2. After you complete steps in later sections (BGV, Engagements), reload — the counts and timeseries should reflect them.
3. Click a chart series (e.g. "Verified talents") → drill modal opens, calls `/trust/timeseries/details?series=verified_talents`.
4. Click **Download PDF** in the drill modal → hits `/trust/timeseries/details/pdf?series=...&q=...`. This inserts a row in `drill_receipts`.
5. Copy the signature from the receipt (`db.drill_receipts.find().sort({_id:-1}).limit(1)`) and open `http://localhost:8000/api/trust/verify-drill/<signature>` to confirm the lookup works.

**Blocked locally.** Nothing. The signature uses `DRILL_SIGN_SECRET` env with a hardcoded fallback so PDF signing runs even without secrets.

---

## 5. Talent profile

**What it does.** Talent edits their public profile (headline, bio, skills, years, hourly rate, location, avatar, portfolio images, industries, timezone, weekly capacity). Also fetches an AI rate suggestion.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| PUT | `/api/profile` | `backend/routes/auth.py:210` | auth |
| POST | `/api/profile/suggest-rate` | `backend/routes/auth.py:217` | auth |
| POST | `/api/files/upload` | see `backend/server.py` (grep `/files/upload`) | auth |
| GET | `/api/marketplace/industries` | `backend/routes/marketplace.py:91` | public |

**Frontend entry points.**
- `/talent/profile` → `frontend/src/pages/TalentProfile.jsx` (role=talent)

**Data model.** Writes `users.profile.*`.

**Manual test steps.** (Depends on Section 3 talent account.)
1. Log in as `alex@test.local`. Visit `/talent/profile`.
2. Fill Headline, Bio, comma-separated Skills (`React, TypeScript`), Years `5`, Hourly rate `60`, Location `Remote — India`.
3. Upload an avatar image (any `.png` < 3 MB) — should return a URL. Save.
4. Reload the page — values should persist. In Mongo: `db.users.findOne({email:"alex@test.local"}, {profile:1})`.
5. Click **Suggest rate**. Without `EMERGENT_LLM_KEY` you'll see the fallback range (`low=45, mid=50, high=75` for 5 years — the deterministic rule-based numbers).

**Blocked locally.** `POST /profile/suggest-rate` real LLM path requires `EMERGENT_LLM_KEY`. Fallback still returns a usable object.

---

## 6. Talent dashboard (widgets + broadcast inbox)

**What it does.** Talent home: KPIs, engagements list, rate-nudge banner, rate sanity-check card, hire-intent broadcast inbox (SSE-pushed), employer directory, recovery-status banner.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| GET | `/api/dashboard/metrics` | `backend/server.py` (grep) | auth |
| GET | `/api/engagements` | `backend/server.py` (grep) | auth |
| GET | `/api/employers` | `backend/server.py` (grep) | auth |
| GET | `/api/talent/me/rate-nudge` | `backend/server.py:1479` | role=talent |
| POST | `/api/talent/me/rate-nudge/dismiss` | `backend/server.py:1488` | role=talent |
| GET | `/api/talent/me/broadcasts` | `backend/server.py:2122` | role=talent |
| POST | `/api/talent/me/broadcasts/{id}/read` | `backend/server.py:2210` | role=talent |
| GET | `/api/talent/me/broadcasts/stream?token=` | `backend/server.py:2147` | role=talent (SSE token) |
| GET | `/api/talent/me/recovery-status` | `backend/routes/revisions.py:542` | role=talent |

**Frontend entry points.**
- `/talent` → `frontend/src/pages/TalentDashboard.jsx`

**Data model.** Reads `engagements`, `deliverables`, `reviews`, `rate_nudges`, `broadcasts`, `users`.

**Manual test steps.** (Depends on Section 5.)
1. Log in as talent. Visit `/talent`. You should see the greeting + empty engagements + Employer directory populated with `EmpCo`.
2. Recovery status will show green ("no penalties").
3. Rate nudge banner is hidden until you exercise Section 21 (Admin → rate-nudges/scan). To trigger it manually now:
   ```
   curl -X POST http://localhost:8000/api/admin/rate-nudges/scan --cookie "access_token=<admin cookie>"
   ```
4. Broadcast inbox is empty until Section 8.

**Blocked locally.** Real rate-nudge insertion requires `EMERGENT_LLM_KEY`; without it, the scan returns 0 nudges. You can seed one manually:
```
db.rate_nudges.insertOne({talent_id:"<alex id>", current_rate:60, suggested_low:75, suggested_mid:85, suggested_high:100,
  drift_pct:41, direction:"raise", rationale:"Manual test seed", created_at:new Date().toISOString()})
```
Reload `/talent` to see the banner.

---

## 7. Employer dashboard

**What it does.** Employer home: hours balance, KPIs, engagements list, projects, variance alert inbox, "Mix & Match" form to create a new engagement.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| GET | `/api/dashboard/metrics` | `backend/server.py` | auth |
| GET | `/api/engagements` | `backend/server.py` | auth |
| GET | `/api/talent` | `backend/server.py:231` | public |
| GET | `/api/employer/overview` | `backend/server.py` (grep) | role=employer |
| GET | `/api/projects/mine` | `backend/routes/projects.py:225` | auth (employer sees own) |
| GET | `/api/alerts/mine` | `backend/routes/projects.py:445` | auth |
| POST | `/api/engagements` | `backend/server.py:602` | role=employer |

**Frontend entry points.**
- `/employer` → `frontend/src/pages/EmployerDashboard.jsx`

**Data model.** Reads `users`, `engagements`, `deliverables`, `payouts`, `project_alerts`, `projects`. Writes `engagements` on create.

**Manual test steps.** (Depends on Sections 3 & 5 accounts.)
1. Log in as `emp@test.local`. Visit `/employer`.
2. Hours balance shows 0. Buy hours (Section 10) before creating an engagement.
3. Return here after buying hours to use the Mix & Match form.

**Blocked locally.** Nothing gates the dashboard itself.

---

## 8. Browse / discovery + Shortlist + Skill landing

**What it does.** Public talent search with filters (search, skill, industry, verified-only). Employers can save candidates to a shortlist and broadcast an "I'm ready to hire" note to shortlisted talent. Skill-slug SEO pages (`/hire/react-developers`, `/hire/react-developers-london`) mix real DB talent with a curated pool from `_CURATED_TALENT` in `server.py`.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| GET | `/api/talent?q=&skill=&industry=&verified_only=` | `backend/server.py:231` | public |
| GET | `/api/talent/{id}` | `backend/server.py` (grep) | auth |
| GET | `/api/employers` | `backend/server.py` (grep) | auth |
| GET | `/api/marketplace/industries` | `backend/routes/marketplace.py:91` | public |
| GET | `/api/marketplace/stats` | `backend/routes/marketplace.py` (grep) | public |
| GET | `/api/seo/hire/{skill_slug}` | `backend/server.py:972` | public |
| GET | `/api/seo/hire-city/{slug}` | `backend/server.py:1340` | public |
| POST | `/api/shortlist` | `backend/routes/marketplace.py:157` | role=employer |
| GET | `/api/shortlist` | `backend/routes/marketplace.py:182` | role=employer |
| DELETE | `/api/shortlist/{talent_id}` | `backend/routes/marketplace.py:190` | role=employer |
| POST | `/api/shortlist/broadcast` | `backend/server.py:1508` | role=employer |

**Frontend entry points.**
- `/browse` → `frontend/src/pages/BrowseTalent.jsx`
- `/hire/:slug` → `frontend/src/pages/SkillLanding.jsx`
- `/employer/shortlist` → `frontend/src/pages/Shortlist.jsx`

**Data model.** Reads `users`, `engagements`, `reviews`. Writes `shortlists`, `broadcasts`.

**Manual test steps.** (Depends on Section 5 talent + Section 3 employer.)
1. As nobody (log out), visit `/browse`. You should see the talent card for Alex.
2. Toggle **Verified only** on — the card disappears because Alex isn't BGV-verified yet.
3. Visit `/hire/react-developers`. You'll see Alex plus a curated pool. Click a card to open the preview modal.
4. Log in as employer. Visit `/employer/shortlist` — empty state → link back to `/browse`.
5. From `/browse` click Alex's card → shortlist button. Return to `/employer/shortlist` — Alex now appears with hourly rate + skills.
6. Click **Broadcast** → type "Ready to hire — 20h/wk, starting Monday." → send. Response should list `delivered:1, emailed:0, skipped_curated:0`.
7. Log back in as Alex → `/talent` → Hire-Intent Inbox should show the message (via `GET /talent/me/broadcasts`).

**Blocked locally.** Broadcast emails need `RESEND_API_KEY` (they're skipped silently). SSE push and in-app inbox work fine.

---

## 9. EOI (expression of interest)

**What it does.** Talent raises an EOI to a specific employer (or open). Employer sees incoming EOIs and can accept → auto-creates an engagement. Talent can withdraw open EOIs.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/eoi` | `backend/server.py:2467` | auth (talent flow) |
| GET | `/api/eoi` | `backend/server.py:2491` | auth |
| POST | `/api/eoi/{id}/accept` | `backend/server.py:2503` | role=employer |
| POST | `/api/eoi/{id}/withdraw` | `backend/server.py:2537` | role=talent |

**Frontend entry points.**
- `/eoi` → `frontend/src/pages/EOI.jsx`

**Data model.** Reads/writes `eois`. Writes `engagements` on accept.

**Manual test steps.** (Depends on Section 8 broadcast — talent knows employer ID.)
1. Log in as Alex. Visit `/eoi`. Enter employer ID (from `db.users.findOne({email:"emp@test.local"}, {id:1})`), hours/week `20`, start date, message `Interested in the broadcast`. Submit.
2. Log in as employer. Visit `/eoi`. You should see the incoming EOI. Click **Accept →**. The response returns an engagement id.
3. Visit `/employer` — the engagement now appears.

**Blocked locally.** Nothing.

---

## 10. Purchase hours + Stripe/Bank payments

**What it does.** Employer buys hour packs (10/50/100/500). Card path uses Stripe Checkout Session; bank path renders UPI/wire details and takes a UTR submission for admin approval.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/payments/checkout` | `backend/server.py:495` | role=employer |
| POST | `/api/payments/bank/initiate` | `backend/server.py:443` | role=employer |
| POST | `/api/payments/bank/submit` | `backend/server.py:470` | role=employer |
| GET | `/api/payments/mine` | `backend/server.py:488` | role=employer |
| GET | `/api/payments/status/{session_id}` | `backend/server.py:542` | public (polled) |
| POST | `/api/stripe/webhook` | `backend/server.py:557` | public (Stripe signature) |
| GET | `/api/packages` | `backend/server.py` (grep) | public |
| GET | `/api/pricing` | `backend/server.py:2613` | public |

**Frontend entry points.**
- `/pricing` → `frontend/src/pages/Pricing.jsx`
- `/employer/purchase` → `frontend/src/pages/PurchaseHours.jsx`
- `/payment/success?session_id=` → `frontend/src/pages/PaymentSuccess.jsx`
- `/payment/cancel` → `frontend/src/pages/PaymentCancel.jsx`

**Data model.** Reads/writes `payment_transactions`. Writes `users.hours_balance` on webhook.

**Manual test steps.** (Depends on Section 3 employer.)
1. Log in as employer. Visit `/pricing` — confirm the plans + comparison table render.
2. Visit `/employer/purchase`. Card tab: click **Buy** on any pack. With dummy Stripe keys, this call returns 500 (`StripeError: Invalid API Key`).
3. Bank transfer tab: click **Show bank details** for a pack → the panel renders with beneficiary + UPI QR + reference id. Fill UTR `TESTUTR001` and submit — `POST /payments/bank/submit` returns success. The transaction is stored with `status="submitted"`.
4. Verify: `db.payment_transactions.find().pretty()`.

**Blocked locally.**
- Stripe Checkout requires a real `STRIPE_SECRET_KEY`. Bypass for local testing: skip Stripe entirely by using the bank flow, then admin-approve it (Section 21). Or credit hours directly:
  ```
  db.users.updateOne({email:"emp@test.local"}, {$inc:{hours_balance: 100}})
  ```
- Stripe webhook: with a real key you'd use `stripe listen --forward-to localhost:8000/api/stripe/webhook`. Without one, you can synthesise an event but signature verification will reject it (that's `stripe.Webhook.construct_event`). Skip the webhook path locally — use the direct DB credit above.

---

## 11. Engagements + contract signing + deliverables

**What it does.** Employer creates an engagement (contract layer) allocating hours + hourly rate + mode (remote/onsite/hybrid). Both parties sign. Talent submits deliverables; employer approves/rejects/requests revision. Approval triggers a payout row.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/engagements` | `backend/server.py:602` | role=employer |
| GET | `/api/engagements` | `backend/server.py` | auth |
| GET | `/api/engagements/{id}` | `backend/server.py` | auth (party) |
| POST | `/api/engagements/{id}/sign` | `backend/server.py` (grep `/sign`) | auth (party) |
| POST | `/api/deliverables` | `backend/server.py:584` | role=talent |
| GET | `/api/deliverables/{engagement_id}` | `backend/server.py:605` | auth (party) |
| POST | `/api/deliverables/{id}/approve` | `backend/server.py:670` | role=employer |
| POST | `/api/deliverables/{id}/reject` | `backend/server.py:675` | role=employer |
| POST | `/api/reviews` | `backend/server.py:681` | auth (party) |
| GET | `/api/reviews/user/{uid}` | `backend/server.py:705` | public |

**Frontend entry points.**
- `/engagement/:id` → `frontend/src/pages/EngagementDetail.jsx`

**Data model.** Writes `engagements`, `deliverables`, `payouts`, `reviews`.

**Manual test steps.** (Depends on Sections 9 or 10 + hours balance.)
1. If Section 9 accepted an EOI you already have an engagement id. Otherwise, ensure employer has ≥ 20 hours (see Section 10 direct credit). Log in as employer, `/employer`, use Mix & Match: pick Alex, hours `20`, scope `Rebuild dashboard`, mode Remote → Submit.
2. Visit `/engagement/<id>`. Sign as employer (name + agree checkbox). Log in as Alex, visit the same URL, sign as talent.
3. As Alex, submit a deliverable: Title `Dashboard v1`, Link `https://example.com/pr/1`, Description, Hours claimed `5`.
4. Log in as employer. Open the engagement — click **Approve** on the deliverable. Response should include a `payout_id`.
5. Verify: `db.payouts.find({engagement_id:"<id>"})` shows a payout row with commission calc.
6. Post a review (rating + text). It writes to `reviews` with `status="pending_moderation"`.

**Blocked locally.** Payout row is created locally; actual Stripe Connect payout is not implemented for real money movement. Nothing else blocked.

---

## 12. Revisions & penalty ladder

**What it does.** Employer requests revisions on a deliverable (justification 20–2000 chars, priority minor/major/blocking). Talent resubmits. Revision counter escalates on the deliverable and on the talent's profile: revision 3+ = `under_review`, revision 5+ = `excessive_revisions` (visibility -20, rate bias -10%). Employer's own abuse pattern flag fires at 5 revisions across ≥ 3 talents in 60 days.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/deliverables/{id}/request-revision` | `backend/routes/revisions.py:134` | role=employer (party) |
| POST | `/api/deliverables/{id}/resubmit` | `backend/routes/revisions.py:188` | role=talent (party) |
| GET | `/api/deliverables/{id}/revisions` | `backend/routes/revisions.py:217` | auth (party or moderation admin) |
| GET | `/api/deliverables/{id}/revision-summary` | `backend/routes/revisions.py:496` | auth (party or moderation admin) |
| GET | `/api/talent/me/recovery-status` | `backend/routes/revisions.py:542` | role=talent |

**Frontend entry points.**
- All embedded in `/engagement/:id` → `frontend/src/pages/EngagementDetail.jsx` (revision buttons + resubmit modal + thread).

**Data model.** Writes `revision_requests`, `deliverables.revision_count/status`, `users.profile.revision_flags/under_review/excessive_revisions/visibility_score/rate_bias_pct/clean_streak`.

**Manual test steps.** (Depends on Section 11 signed engagement.)
1. As talent, submit a second deliverable.
2. As employer, on the same deliverable click **Request revision**, justification `Please add totals row`, priority Minor. Repeat 5 times, each time the talent resubmits, until `revision_count == 5`.
3. As talent, check `/talent` — the Recovery banner should show `excessive_revisions=true`, visibility 80, rate bias -10%.
4. Verify: `db.users.findOne({email:"alex@test.local"}, {profile:1}).profile.revision_flags`.
5. The `/engagement/:id` page should now show the **Raise dispute** button on that deliverable (Section 13).

**Blocked locally.** Nothing.

---

## 13. Disputes & arbitration (revision-based)

**What it does.** When revisions ≥ 5, talent can open a `revision_dispute` grievance. Full revision thread is copied into `grievances`. Admin (moderation scope) rules for talent or employer; the loser owes the arbitration fee (`REVISION_DISPUTE_FEE_USD`, default $49). Ruling is final (no appeal endpoint).

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/deliverables/{id}/dispute` | `backend/routes/revisions.py:235` | role=talent |
| GET | `/api/admin/revisions` | `backend/routes/revisions.py:291` | scope=moderation |
| POST | `/api/admin/revisions/{gid}/rule` | `backend/routes/revisions.py:312` | scope=moderation |
| GET | `/api/admin/employers-flagged` | `backend/routes/revisions.py:415` | scope=moderation |

**Frontend entry points.**
- Talent side: `frontend/src/pages/EngagementDetail.jsx` (Raise dispute modal).
- Admin side: `frontend/src/pages/Admin.jsx` → Revisions tab (`RevisionsPanel`).

**Data model.** Writes `grievances` (kind `revision_dispute`, with `dispute_fee`), `deliverables.dispute_grievance_id`, and on ruling reverses talent penalty flags.

**Manual test steps.** (Depends on Section 12.)
1. Log in as Alex on the engagement page → **Raise dispute** → reason (≥ 20 chars). Confirms with a $49 fee note. Submit → grievance created.
2. Verify: `db.grievances.find({kind:"revision_dispute"}).pretty()`.
3. Log in as admin. `/admin` → Revisions tab → find the open dispute → click **Rule for talent** (or employer) + notes. Fee ownership is stamped on the grievance.
4. If ruled for talent, refresh `/talent` — the penalty flags should be cleared.

**Blocked locally.** Nothing gates the ruling itself.

---

## 14. Dispute-fee payment + admin refund + refund audit

**What it does.** Loser pays the $49 dispute fee via Stripe Checkout; the webhook calls `mark_dispute_fee_paid`. Admin can refund via `stripe.Refund.create`. An admin refund-analytics endpoint returns 30-day paid/refunded/refund_rate. Admin can also download a signed PDF audit of all refunds; signature uses `_refund_audit_signature` (documented as sha256(secret+msg) with hardcoded fallback `jobatlas-refund-v1`).

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/grievances/{gid}/pay-fee` | `backend/routes/revisions.py:586` | auth (payer) |
| GET | `/api/grievances/{gid}/fee-status` | `backend/routes/revisions.py:668` | auth (payer/other party/admin) |
| POST | `/api/admin/grievances/{gid}/refund-fee` | `backend/routes/revisions.py:736` | scope=moderation |
| GET | `/api/admin/revisions/refund-analytics` | `backend/routes/revisions.py:429` | scope=moderation |
| GET | `/api/admin/revisions/refund-audit/pdf?days=` | `backend/routes/revisions.py:929` | scope=moderation |
| GET | `/api/admin/revisions/refund-audit/verify/{sig}` | `backend/routes/revisions.py:972` | scope=moderation |

**Frontend entry points.**
- Payer-side pay/status: `frontend/src/pages/EngagementDetail.jsx` (FeeCard within the revision thread).
- Admin refund + analytics: `frontend/src/pages/Admin.jsx` (Revisions tab + RefundAnalyticsCard).

**Data model.** `grievances.dispute_fee`, `dispute_fee_transactions`, `refund_audit_receipts`.

**Manual test steps.** (Depends on Section 13.)
1. As the losing party, on `/engagement/:id` click **Pay $49 fee** → the endpoint returns a Stripe checkout URL. With dummy keys it returns 500.
2. To bypass Stripe locally, mark the fee paid directly:
   ```
   const g = db.grievances.findOne({kind:"revision_dispute"});
   db.grievances.updateOne({_id:g._id}, {$set:{"dispute_fee.payment_status":"paid","dispute_fee.paid_at":new Date().toISOString(),"dispute_fee.payment_intent_id":"pi_manual_test"}});
   db.dispute_fee_transactions.insertOne({grievance_id:g.id, session_id:"cs_manual", payer_id:g.dispute_fee.owed_by_id, amount_cents:4900, status:"completed", payment_status:"paid", payment_intent_id:"pi_manual_test", paid_at:new Date().toISOString(), created_at:new Date().toISOString()});
   ```
3. As admin, `/admin` → Revisions tab → Refund analytics card should now show `1 paid, 0 refunded, refund_rate 0%`.
4. Click **Refund** on the paid grievance and enter a reason ≥ 10 chars. Stripe refund call will 500 without a live key. To exercise the local audit path only, update Mongo directly:
   ```
   db.grievances.updateOne({_id:g._id}, {$set:{"dispute_fee.payment_status":"refunded","dispute_fee.refunded_at":new Date().toISOString(),"dispute_fee.refund_reason":"manual","dispute_fee.refunded_by_id":"admin-1"}});
   db.dispute_fee_transactions.updateOne({grievance_id:g.id}, {$set:{payment_status:"refunded", refund_reason:"manual", refunded_at:new Date().toISOString(), refunded_by_id:"admin-1"}});
   ```
5. Click **Download PDF audit** — hits `/admin/revisions/refund-audit/pdf?days=30`. A row lands in `refund_audit_receipts`. Copy the signature and open `/admin/revisions/refund-audit/verify/<sig>` to confirm lookup.

**Blocked locally.** Live Stripe refund needs `STRIPE_SECRET_KEY`. The audit signature uses `REFUND_AUDIT_SIGN_SECRET` / `DRILL_SIGN_SECRET` with a hardcoded fallback so the PDF still generates.

---

## 15. Background verification (talent) + Company KYB (employer) + reference checks

**What it does.** Talent submits BGV (work_history, ≥ 2 references, gov ID URL, LinkedIn URL). System auto-emails each reference a token link; on ≥ 2 YES + 0 NO + email_verified, the talent is auto-approved. Employer submits KYB (company reg, tax id, etc.), admin approves manually. Verified employers get 10 free hours + hero placement.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/verification/company` | `backend/routes/auth.py:258` | role=employer |
| POST | `/api/verification/bgv` | `backend/routes/auth.py:279` | role=talent |
| GET | `/api/verification/me` | `backend/routes/auth.py:899` | auth |
| GET | `/api/reference-check/{token}` | `backend/routes/auth.py:353` | public |
| POST | `/api/reference-check/{token}` | `backend/routes/auth.py:376` | public |
| GET | `/api/admin/verifications?status=` | `backend/routes/admin.py:473` | scope=support OR moderation |
| GET | `/api/admin/verifications-with-refs?status=` | `backend/routes/projects.py:1412` | scope=support OR moderation |
| POST | `/api/admin/verifications/{uid}/approve` | `backend/routes/admin.py:486` | scope=moderation |
| POST | `/api/admin/verifications/{uid}/reject` | `backend/routes/admin.py:523` | scope=moderation |
| GET | `/api/admin/reference-checks/{talent_id}` | `backend/routes/auth.py:885` | scope=support OR moderation |

**Frontend entry points.**
- `/verify` → `frontend/src/pages/Verification.jsx` (role-aware Company vs BGV form).
- `/reference-check?token=` → `frontend/src/pages/ReferenceCheck.jsx` (public referee form).
- Admin queue at `/admin` → Verifications tab (VerificationsPanel).

**Data model.** Writes `users.verification_status/profile.*`, `reference_checks`, `audit_log` on KYB perks grant.

**Manual test steps.** (Depends on Sections 3 & 5.)
1. Log in as `emp@test.local`. Visit `/verify`. Fill KYB: company `EmpCo Ltd`, reg `12345`, tax id `TAX123`, website, size, year, country. Submit → `verification_status="pending"`.
2. Log in as admin. `/admin` → Verifications → find `EmpCo Ltd` → Approve. Backend grants 10 hours + `hero_placement=true`. Verify: `db.users.findOne({email:"emp@test.local"}, {verification_status:1, hours_balance:1, hero_placement:1})`.
3. Log in as Alex. Visit `/verify`. Fill BGV: add one work history row + two references (`Reviewer A / a@test.local`, `Reviewer B / b@test.local`), gov ID URL, LinkedIn URL. Submit.
4. Locally there's no email delivery — pull the tokens from Mongo:
   ```
   db.reference_checks.find({talent_id:"<alex id>"}, {token:1, ref_name:1})
   ```
5. Open two browser tabs at `/reference-check?token=<token1>` and `<token2>`. Each: select **Yes**, note "Great work". Submit.
6. Alex must also have `email_verified=true` for the auto-approval rule. Set it via the email-verification bypass in Section 3.
7. Reload `/talent`. Alex should show verified. Verify: `db.users.findOne({email:"alex@test.local"}, {verification_status:1, verified_at:1})`.
8. As admin, Verifications tab, filter Verified — Alex should appear.

**Blocked locally.** Reference-check email delivery needs `RESEND_API_KEY`. Bypass: read tokens from Mongo as shown.

---

## 16. Project leads → Projects → workspace (phases / RACI / variance / risks / milestones)

**What it does.** Employers submit scoping requests (project leads) from `Projects.jsx`. A superadmin converts a lead into a project, which auto-seeds 4 phases + 4 milestones (25% each), a seed RACI, an empty risk register, and an empty variance log. The project workspace lets employer + talent + admin move phases, log variances (fires an alert at ±10%), add risks, edit RACI, and add milestones.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/projects/lead` | `backend/routes/projects.py` (grep `def create_lead`) | auth |
| GET | `/api/projects/templates` | `backend/routes/projects.py` (grep) | public |
| GET | `/api/projects/templates/{id}` | `backend/routes/projects.py` | public |
| GET | `/api/projects/templates/{id}/team-suggestions` | `backend/routes/projects.py` | auth |
| GET | `/api/admin/project-leads` | `backend/routes/projects.py:217` | scope=support OR superadmin |
| POST | `/api/admin/project-leads/{id}/convert` | `backend/routes/projects.py:134` | scope=superadmin |
| GET | `/api/projects/mine` | `backend/routes/projects.py:225` | auth |
| GET | `/api/projects/workspace/{id}` | `backend/routes/projects.py:237` | auth (admin or `employer_id==user.id`) |
| PATCH | `/api/projects/workspace/{id}/phases/{pid}` | `backend/routes/projects.py:287` | auth (party) |
| POST | `/api/projects/workspace/{id}/variances` | `backend/routes/projects.py:405` | auth (party) |
| GET | `/api/projects/workspace/{id}/alerts` | `backend/routes/projects.py:436` | auth (party) |
| GET | `/api/alerts/mine` | `backend/routes/projects.py:445` | auth |
| POST | `/api/alerts/{id}/read` | `backend/routes/projects.py:460` | auth (party) |
| POST | `/api/projects/workspace/{id}/risks` | `backend/routes/projects.py:474` | auth (party) |
| PATCH | `/api/projects/workspace/{id}/risks/{rid}` | `backend/routes/projects.py:499` | auth (party) |
| PUT | `/api/projects/workspace/{id}/raci` | `backend/routes/projects.py:525` | auth (party) |
| POST | `/api/projects/workspace/{id}/milestones` | `backend/routes/projects.py:548` | auth (party) |
| POST | `/api/admin/projects/{id}/save-as-template` | `backend/routes/projects.py:1354` | scope=superadmin OR customization |

**Frontend entry points.**
- `/projects` → `frontend/src/pages/Projects.jsx`
- `/projects/:id/workspace` → `frontend/src/pages/ProjectWorkspace.jsx`

**Data model.** Writes `project_leads`, `projects`, `project_milestones`, `project_variances`, `project_alerts`, `project_risks`.

**Manual test steps.** (Depends on Section 15 employer KYB approved so hero-placement applies + Section 3 admin.)
1. Log in as employer. Visit `/projects`. Pick a PMI template → assemble team (lock/unlock seats, reshuffle) → submit as a lead.
2. Verify: `db.project_leads.find().pretty()`.
3. Log in as admin. `/admin` → Project Leads → find lead → **Convert**. Backend inserts `projects` doc + 4 milestones.
4. Note the returned project id, then visit `/projects/<id>/workspace` (logged in as either the employer or the admin — the workspace loader blocks other users).
5. Phases tab: advance phase 1 to `in_progress` and add a sign-off name. `db.projects` should reflect the change.
6. Variance tab: post a variance with actual hours 20% over planned → fires a `project_alerts` row. Check `/alerts/mine`.
7. Risks tab: add a risk (title, likelihood H, impact H, mitigation).
8. RACI tab: edit an activity's assignments (R/A/C/I) and save.
9. Milestones tab: add a custom milestone (name, amount, due date).

**Blocked locally.** Slack notifications on variance breach need `SLACK_WEBHOOK_URL` (skipped silently). Email notifications need `RESEND_API_KEY`.

---

## 17. Project milestones — invoicing + Stripe checkout + auto-collect

**What it does.** Admin (finance) issues an invoice against a milestone. Employer either pays via Stripe Checkout on the milestone or via the auto-collect card on file (once attached via SetupIntent). Overdue invoices trigger email reminders (3-day cadence) and off-session Stripe charges (after 7 days) via a daily scheduled job.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| POST | `/api/projects/workspace/{id}/milestones/{mid}/invoice` | `backend/routes/projects.py:585` | scope=finance OR superadmin |
| POST | `/api/projects/workspace/{id}/milestones/{mid}/paid` | `backend/routes/projects.py:615` | scope=finance OR superadmin |
| POST | `/api/projects/workspace/{id}/milestones/{mid}/checkout` | `backend/routes/projects.py:780` | admin OR `employer_id==user.id` |
| GET | `/api/projects/milestone-payment/status/{sid}` | `backend/routes/projects.py:866` | auth |
| GET | `/api/projects/workspace/{id}/invoices/{iid}/pdf` | `backend/routes/projects.py:752` | auth (party) |
| GET | `/api/invoices/mine` | `backend/routes/projects.py:903` | auth (admin sees all, employer sees own) |
| POST | `/api/billing/setup-checkout` | `backend/routes/projects.py:974` | role=employer |
| GET | `/api/billing/setup-checkout/status/{sid}` | `backend/routes/projects.py:1013` | role=employer |
| POST | `/api/billing/setup` | `backend/routes/projects.py:1052` | role=employer |
| GET | `/api/billing/status` | `backend/routes/projects.py:1090` | role=employer |
| POST | `/api/admin/invoices/scan-overdue` | `backend/routes/projects.py:1326` | scope=finance OR superadmin |

**Frontend entry points.**
- `/projects/:id/workspace` (Milestones tab) → `frontend/src/pages/ProjectWorkspace.jsx`
- `/invoices` → `frontend/src/pages/Invoices.jsx`

**Data model.** Writes `project_invoices`, `project_milestones`, `payment_transactions`, `payment_reminders`, `users.stripe_*`.

**Manual test steps.** (Depends on Section 16 project + Section 3 admin with finance scope.)
1. As admin, `/projects/<id>/workspace` → Milestones tab → **Invoice** on milestone 1. Verify: `db.project_invoices.find({project_id:"<id>"})`.
2. Log in as employer. Visit `/invoices` — the invoice row appears with status Open.
3. Click **Download PDF** — the invoice PDF renders (ReportLab).
4. Click **Pay** on milestone → `POST /milestones/{mid}/checkout` → returns Stripe URL → 500 without a live key. Bypass: mark the milestone paid manually as admin:
   ```
   curl -X POST http://localhost:8000/api/projects/workspace/<id>/milestones/<mid>/paid --cookie "access_token=<admin>"
   ```
   Reload `/invoices` — status becomes Paid.
5. Auto-collect card setup: `POST /billing/setup-checkout` needs Stripe. Skip locally.
6. Trigger overdue scan manually as admin: `POST /admin/invoices/scan-overdue`. It walks all unpaid invoices, inserts `payment_reminders` rows.

**Blocked locally.** Stripe Checkout + SetupIntent + off-session charges need `STRIPE_SECRET_KEY`. Overdue scan itself runs; email reminders inside it need `RESEND_API_KEY`; Slack mirror needs `SLACK_WEBHOOK_URL`.

---

## 18. Earnings & payouts (talent)

**What it does.** Rolling 30-day earnings statement for talent (hours, gross, commission tier %, multi-employer fee, net). Lists prior payout runs. Downloadable plain-text statement.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| GET | `/api/earnings/mine` | `backend/server.py:403` | role=talent |
| GET | `/api/payouts/mine` | `backend/server.py:874` | role=talent |
| POST | `/api/admin/payouts/run` | `backend/routes/admin.py:127` | scope=finance |
| GET | `/api/admin/payouts/runs` | `backend/routes/admin.py:162` | scope=finance |
| GET | `/api/admin/payouts/{run_id}` | `backend/routes/admin.py:168` | scope=finance |
| POST | `/api/admin/payouts/{pid}/mark-paid` | `backend/routes/admin.py:178` | scope=finance |

**Frontend entry points.**
- `/talent/earnings` → `frontend/src/pages/Earnings.jsx`

**Data model.** Reads `deliverables`, `engagements`, `users`, `payouts`, `payout_runs`.

**Manual test steps.** (Depends on Section 11 approved deliverable.)
1. Log in as Alex. Visit `/talent/earnings`. Rolling 30-day KPIs should show the hours from the approved deliverable, gross = hours × rate, commission tier applied.
2. Click **Download statement** — writes a `.txt` file locally.
3. As admin (finance scope), `/admin` → Payouts tab → set date range → **Run payouts**. Verify `db.payout_runs` and `db.payouts`.
4. Click **Mark paid** on the payout — status flips to paid.

**Blocked locally.** Nothing. Real money movement (Stripe Connect) is not implemented.

---

## 19. Referrals

**What it does.** Each user gets a referral code. Others can claim it (self-referral blocked). On the referred talent's first ≥ 6-hour approved deliverable, a bonus is credited via `_credit_referral_bonus`.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| GET | `/api/referrals/mine` | `backend/server.py:886` | auth |
| POST | `/api/referrals/claim` | `backend/server.py:896` | auth |

**Frontend entry points.**
- `/referrals` → `frontend/src/pages/Referral.jsx`

**Data model.** Writes `referrals`.

**Manual test steps.** (Depends on Section 3 two accounts.)
1. Log in as Alex, visit `/referrals`. Copy the referral code.
2. Register a third user (or use the employer). Visit `/referrals` → paste Alex's code → Apply. Verify `db.referrals.find({referrer_id:"<alex id>"})` shows a pending row.
3. After that referred user gets an approved deliverable ≥ 6 hours, `_credit_referral_bonus` flips the row to `credited` and adds `bonus_hours`.

**Blocked locally.** Nothing.

---

## 20. Calendar & availability

**What it does.** Personal weekly availability (timezone + slots per day). Aggregates upcoming events from engagements and EOIs.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| PUT | `/api/availability` | `backend/server.py:2432` | auth |
| GET | `/api/availability/{uid}` | `backend/server.py:2438` | auth |
| GET | `/api/calendar/events` | `backend/server.py:2448` | auth |

**Frontend entry points.**
- `/calendar` → `frontend/src/pages/Calendar.jsx`

**Data model.** Writes `users.profile.availability`.

**Manual test steps.**
1. Log in as anyone. Visit `/calendar`. Pick a timezone. Add slots (Day, Start, End). Save.
2. Verify: `db.users.findOne({email:"..."}, {"profile.availability":1})`.
3. Upcoming events list should include the engagement from Section 11.

**Blocked locally.** Nothing.

---

## 21. Admin panel (all tabs)

**What it does.** Single-page admin console with tabs driven by scopes. Read `frontend/src/pages/Admin.jsx` `TAB_CATALOG` (line 13) for the visible tab set.

**Backend endpoints.** (Grouped; already enumerated per section above.)
- Support: `/admin/users`, `/admin/users/{uid}`, `/admin/users/{uid}/notes`, `/admin/users/{uid}/adjust` (scope=support).
- Project Leads: `/admin/project-leads`, `/admin/project-leads/{id}/convert` (support / superadmin).
- Verifications: `/admin/verifications`, `/admin/verifications-with-refs`, `/admin/verifications/{uid}/approve`, `/admin/verifications/{uid}/reject` (support/moderation).
- Revisions: `/admin/revisions`, `/admin/revisions/{gid}/rule`, `/admin/employers-flagged`, `/admin/revisions/refund-analytics`, `/admin/grievances/{gid}/refund-fee`, `/admin/revisions/refund-audit/pdf`, `/admin/revisions/refund-audit/verify/{sig}` (moderation).
- Bank Transfers: `/admin/bank-transfers`, `/admin/bank-transfers/{pid}/approve`, `/admin/bank-transfers/{pid}/reject` (finance).
- Payouts: `/admin/payouts/run`, `/admin/payouts/runs`, `/admin/payouts/{id}`, `/admin/payouts/{pid}/mark-paid` (finance).
- Reviews: `/admin/reviews`, `/admin/reviews/{rid}/approve`, `/admin/reviews/{rid}/reject` (moderation).
- Grievances: `/admin/grievances`, `/admin/grievances/{gid}/resolve` (support/moderation).
- Customization: `/admin/customization` (GET/PUT, customization) + public `/customization/public` (no auth).
- Staff & Roles: `/admin/staff`, `/admin/staff/{id}` (superadmin).
- Identity: `GET /admin/me` (`role==admin` only).
- Rate-nudge trigger + scheduler introspection: `POST /admin/rate-nudges/scan`, `GET /admin/scheduler` — both `role==admin` only (no scope subdivision).

**Frontend entry points.**
- `/admin` → `frontend/src/pages/Admin.jsx` (tabs render inline components).

**Data model.** Reads/writes across nearly every collection listed above; additionally writes `support_notes`, `audit_log`, `site_customization`.

**Manual test steps.** (Depends on Section 3 admin account.)
1. Log in as admin. Visit `/admin`. All 10 tabs should be visible if you assigned all scopes.
2. Support tab: search Alex → open detail → add a support note. Adjust hours (+5 goodwill) — `db.audit_log` gets a `hours_adjust` row.
3. Bank Transfers tab: approve the transfer from Section 10 → employer's hours_balance increments.
4. Reviews tab: approve the review from Section 11 → status becomes `approved`, visible on `/browse`.
5. Grievances tab: resolve the Section 2 grievance.
6. Customization tab: edit hero headline → save → check `/` for the updated text.
7. Staff tab: create a new admin `mod@test.local` with only `moderation` scope. Log in as them → confirm only Verifications, Revisions, Reviews, and Grievances tabs render.
8. Trigger `POST /admin/rate-nudges/scan` from the CLI (there's no UI button):
   ```
   curl -X POST http://localhost:8000/api/admin/rate-nudges/scan --cookie "access_token=<admin>"
   ```
9. Fetch `GET /admin/scheduler` similarly to inspect the three cron jobs.

**Blocked locally.** Rate-nudge scan without `EMERGENT_LLM_KEY` returns `nudged=0` because the LLM call fails through to the rule-based fallback and drift usually stays under 15%. Emails need `RESEND_API_KEY`. Stripe refunds need `STRIPE_SECRET_KEY`.

---

## 22. Integrations (Work + CRM)

**What it does.** Two integration systems:
- **Work integrations** (any user): connect Monday / Asana / Trello / ClickUp / Jira / Confluence via API token; upload Excel / MS Project XML; unified work-log view.
- **CRM integrations** (employer): connect HubSpot / Salesforce / Slack / SharePoint via bearer token; push shortlisted talent to CRM; nightly auto-sync of new shortlist rows; sync log ribbon.

**Backend endpoints.**
| Method | Path | File:line | Auth |
| --- | --- | --- | --- |
| GET | `/api/integrations/providers` | `backend/server.py` (grep) | auth |
| POST | `/api/integrations/connect` | `backend/server.py:2348` | auth |
| POST | `/api/integrations/sync/{id}` | `backend/server.py:2379` | auth |
| DELETE | `/api/integrations/{id}` | `backend/server.py:2372` | auth |
| POST | `/api/work/upload` | `backend/server.py` (grep) | auth |
| GET | `/api/work/items` | `backend/server.py` (grep) | auth |
| POST | `/api/integrations/crm/connect` | `backend/routes/auth.py:973` | role=employer OR role=admin |
| GET | `/api/integrations/crm` | `backend/routes/auth.py:999` | auth |
| DELETE | `/api/integrations/crm/{provider}` | `backend/routes/auth.py:1007` | auth |
| POST | `/api/integrations/crm/push-lead` | `backend/routes/auth.py:1021` | employer/admin |
| POST | `/api/integrations/crm/sync-now` | `backend/routes/auth.py:1167` | employer/admin |
| GET | `/api/integrations/crm/sync-log?limit=` | `backend/routes/auth.py:1176` | auth |

**Frontend entry points.**
- `/integrations` → `frontend/src/pages/Integrations.jsx`
- `/accounts` → `frontend/src/pages/Accounts.jsx` (portfolio / payout provider connect)

**Data model.** Writes `integration_tokens`, `users.integrations`, `crm_integrations`, `crm_sync_log`, `work_items`, `connected_accounts`.

**Manual test steps.**
1. Log in as any user. Visit `/integrations`. Providers list loads.
2. Pick a provider and paste an obviously bad token → connect. Backend validates against the provider API; on failure it still stores a stub connection so you can see the row (fallback stub).
3. Upload an Excel file with columns `task, status, due_date, assignee, hours` → row appears in the unified log.
4. As employer, in the CRM section, connect HubSpot with a fake token → validation fails → row not stored. To exercise the sync path, seed a row directly:
   ```
   db.crm_integrations.insertOne({user_id:"<empId>", provider:"hubspot", access_token:"fake", validated:false, last_sync_at:null, created_at:new Date().toISOString()});
   ```
5. Click **Sync now** → returns aggregate counts; log rows land in `crm_sync_log`.

**Blocked locally.** All CRM token validation calls hit real vendor APIs. Bypass: seed `crm_integrations` directly. Push-lead + real sync require real tokens.

---

## 23. Scheduled jobs (APScheduler)

**What it does.** Three cron jobs registered in `backend/server.py` (grep `scheduler.add_job`):

| Job id | Trigger | Function | job_runs? |
| --- | --- | --- | --- |
| `monthly_rate_nudge_scan` | 1st of month, 09:00 UTC | `_scan_and_record_rate_nudges()` (`backend/server.py:1391`) | yes |
| `daily_overdue_invoice_scan` | Daily 08:00 UTC | `scan_overdue_invoices()` (`backend/routes/projects.py:1209`) | yes |
| `nightly_crm_sync` | Daily 02:00 UTC | `_sync_shortlists_to_crm(trigger="cron")` (`backend/routes/auth.py:1067`) | yes |

**Manual test steps.**
1. Introspect state: `GET /api/admin/scheduler` (see Section 21).
2. Trigger each job manually:
   - Rate nudges: `POST /api/admin/rate-nudges/scan` (role=admin).
   - Overdue invoices: `POST /api/admin/invoices/scan-overdue` (scope=finance).
   - CRM sync: `POST /api/integrations/crm/sync-now` (employer/admin).
3. After each, check `db.job_runs.find({job:"<id>"}).sort({at:-1}).limit(1)`.

**Blocked locally.**
- Rate nudges: `EMERGENT_LLM_KEY` (LLM), `RESEND_API_KEY` (email).
- Overdue invoices: `STRIPE_SECRET_KEY` (off-session charge), `RESEND_API_KEY` (reminders), `SLACK_WEBHOOK_URL` (mirroring).
- CRM sync: real vendor tokens; without them the loop no-ops per employer.

All three jobs still insert `job_runs` rows locally, so the audit trail is exercisable.

---

## Dead ends & gaps

The following are backend features with no frontend surface, or frontend surfaces that call missing endpoints. Everything here was verified in the actual code paths.

### Backend without a frontend caller
- `POST /api/trust/verify-drill` (`backend/routes/auth.py:727`) — only the `GET /api/trust/verify-drill/{signature}` lookup form is used by the Trust drill PDF QR code; the POST tamper-check has no UI.
- `GET /api/admin/reference-checks/{talent_id}` (`backend/routes/auth.py:885`) — the Verifications tab uses `/admin/verifications-with-refs` instead, which returns the same data joined; the raw per-talent list endpoint is unused.
- `POST /api/admin/rate-nudges/scan` and `GET /api/admin/scheduler` (`backend/routes/admin.py:186, 194`) — there is no Scheduler tab or "Trigger rate nudges" button in `Admin.jsx`. These are reachable only by curl.
- `POST /api/admin/invoices/scan-overdue` (`backend/routes/projects.py:1326`) — same story; no button.
- `POST /api/admin/projects/{id}/save-as-template` (`backend/routes/projects.py:1354`) — endpoint is wired but `ProjectWorkspace.jsx` has no "save as template" button.
- `GET /api/pricing/tiers` (`backend/server.py:2093`) — `Pricing.jsx` fetches only `/api/pricing`, whose response already contains the tiers.
- `POST /api/pricing/quote` — no frontend caller; `PurchaseHours.jsx` computes bundle math client-side.

### Frontend features that depend on non-existent behaviour locally
- Rate-nudge banner and rate sanity-check card on `TalentDashboard.jsx` — depend on `rate_nudges` rows that only get created by a manual scan trigger. Without `EMERGENT_LLM_KEY` no nudge is created (the LLM path is skipped and drift stays under threshold), so the banner never appears unless you seed a row.
- `Shortlist.jsx` **CRM Push** button — only renders when `/api/integrations/crm` returns items. Without real CRM tokens (or a manual DB seed), this button is invisible.
- `EngagementDetail.jsx` **Pay $49 fee** — the modal is shown, but hitting the button returns a Stripe 500 without `STRIPE_SECRET_KEY`. Bypass in Section 14.
- `Invoices.jsx` **Enable auto-collect** banner — links to a Stripe SetupIntent Checkout that 500s locally.
- `PurchaseHours.jsx` card tab — same Stripe blocker; bank tab is the local-testable path.

### Repo-wide known gaps flagged in code but not addressed
- `crm_integrations.access_token` is stored plaintext (comment TODO for envelope encryption / KMS in `backend/routes/auth.py:993-995`).
- `integration_tokens` (work provider tokens) also plaintext.
- No `POST /admin/rate-nudges/scan` scope check — uses `role == "admin"` (see the earlier security review).
- No JWT revocation / token_version — logout only clears cookies client-side.
- `_refund_audit_signature` (`backend/routes/revisions.py`) uses `sha256(secret + msg)` with a hardcoded fallback `jobatlas-refund-v1` — the PDF signature is generated even when no secret is set.
- Auto-approval rule for BGV silently requires `email_verified=true` on the talent; if you never verify email (blocked by `RESEND_API_KEY`), auto-approval never fires even with 2 YES references.
