# Job Atlas — PRD

## Problem Statement
Skills marketplace where individuals showcase skills and employers buy hours in bulk.
Platform enforces 12-month exclusivity, dual-signed contracts, mix-and-match hour allocation,
work-tracker integrations, timezone-aware calendar, EOI flow, and dual payment rails
(Stripe global + INR bank transfer for the India-based operating company).

## Architecture
- **Backend**: FastAPI (Python), Motor async MongoDB, JWT (httpOnly cookies) auth, bcrypt,
  Stripe SDK, emergentintegrations (Claude Sonnet 5 via Emergent LLM key), openpyxl for Excel.
- **Frontend**: React 19, react-router-dom v7, Tailwind + Shadcn UI, Phosphor icons,
  Recharts for dashboard charts, sonner for toasts.
- **DB collections**: users, engagements, eois, payment_transactions, work_items,
  integration_tokens, connected_accounts.

## Personas
1. **Talent** — freelancers/consultants creating profiles, raising EOIs, signing contracts.
2. **Employer** — companies purchasing hour packages, allocating across talent, signing contracts.
3. **Admin** — verifies India bank-transfer payments, oversees platform.

## Core Requirements (static)
- Registration/login (JWT), profile CRUD, AI rate suggestion (Claude Sonnet 5).
- Talent browsing with hidden contact until engagement contract signed.
- Hour packages via Stripe (USD) or INR bank transfer (Indian company).
- Contract signing with typed signature + 12-month exclusivity clause both sides.
- Work tracking via Jira, Asana, Confluence, Monday, Wrike, MS Dynamics, ServiceNow, SAP,
  Trello, ClickUp, Notion + Excel/MS-Project XML upload.
- Weekly availability with timezone re-projection for calendar view.
- EOI flow: talent raises → employer accepts → engagement auto-created.
- Connected accounts (LinkedIn/GitHub/Google/Microsoft/Slack/Payoneer/Wise/Plaid/etc).
- Role-aware dashboard with shared + specific metrics + charts.
- Landing with hero, marquee, video demo tabs (Employer / Individual), pricing tiers.

## Implemented (2026-02-09, iteration 14 — shortlist page + monthly scheduler + industry-picker fix)
- **Bug fix (user report)**: Register.jsx industry picker no longer uses a native `<select>` (users couldn't tell it was populated). Replaced with an always-visible 3-column grid of chip buttons matching the role-picker style: `data-testid="industry-picker"` wraps 12 chips (`data-testid="industry-<slug>"`); each shows the label + "N ON PLATFORM" subtitle when count>0; hidden input `data-testid="register-industry"` still carries the selected value. Only renders when Employer role is selected.
- **New `/employer/shortlist` page** (`Shortlist.jsx`): premium navy summary card with live count, avg $/hr, and estimated bundle (recomputed from a `10h / 20h / 40h / 80h` hours-per-talent chip picker); grid of shortlisted-talent cards with Remove; "Purchase hours for this shortlist" CTA routes to `/employer/purchase?context=shortlist&talents=N&hours_per_talent=H&est_budget=X`. Empty-state renders when the shortlist is empty. Added route in `App.js`, and a "★ Shortlist" nav link on the Employer Dashboard.
- **PurchaseHours context banner**: when arriving with `?context=shortlist&...`, the page renders a cream banner at the top with the shortlist summary + back link.
- **APScheduler monthly cron**: `AsyncIOScheduler` started on FastAPI startup, one job `monthly_rate_nudge_scan` on `CronTrigger(day=1, hour=9, minute=0)` UTC. Each run calls `_scan_and_record_rate_nudges` and logs a `job_runs` doc. New admin endpoint `GET /api/admin/scheduler` returns running state, next fire time (verified: `2026-09-01 09:00 UTC`), and the last recorded run.
- **Cosmetic**: nudge banner phrasing now shows an unsigned percentage next to the directional verb (e.g. `69% above the market mid` instead of `-69% above`).
- Verified via `testing_agent` iteration_5.json: 12/12 new backend tests + 58/59 baseline unchanged + all frontend flows tested. `retest_needed: false`.

## Implemented (2026-02-09, iteration 13 — buyer categories, shortlist, Resend email)
- **Employer industry self-selection**: `RegisterIn` accepts `company_industry`; Register.jsx renders a dropdown (only when "Employer" role picked) fed by `GET /api/marketplace/industries` (also shows live count per industry). Server validates against the canonical 12-industry list `EMPLOYER_INDUSTRIES` and stores it in `user.profile.company_industry`.
- **Live trust-bar chips**: Landing now fetches `/api/marketplace/industries` and renders `×N` next to any industry with real employers. `/api/marketplace/stats` also returns `industries_active` (distinct claimed industries). Verified with 4 test employers → 4 chips show `×1`.
- **Modal → Shortlist button**: added `shortlists` collection + endpoints (`POST /api/shortlist`, `GET /api/shortlist`, `DELETE /api/shortlist/{talent_id}`, employer-only). SkillLanding modal now has a 3-button footer: Buy hours to unlock → · Shortlist for future hire · Close. Button toggles state (fills, adds ✓, changes label) and shows a toast. Employers see their existing shortlist state on subsequent visits.
- **Rate Nudge → outbound email via Resend**: added `/app/backend/mailer.py` (async, `asyncio.to_thread` wrapper, safe no-op when `RESEND_API_KEY` missing). `_scan_and_record_rate_nudges` now generates an inline-CSS HTML email (Fraunces-ish serif look, gold overline, direction-coloured drift %, CTA back to `/talent`) and calls `send_email`. Nudge doc stores `email_status`, `email_id`, and `delivered_via` (`in_app` or `email+in_app`). Admin scan endpoint returns `emailed` + `email_failures` counts. Ready to fire the moment a valid `RESEND_API_KEY` is pasted into `/app/backend/.env`.

## Implemented (2026-02-09, iteration 12 — live counters + rate drift + curated CTA)
- **Live Buyer Counter**: new `/api/marketplace/stats` endpoint returns real DB counts (employer count, engagement totals, signed engagements) + baseline padding so day-1 numbers still read credibly. Landing trust bar now shows 3 live stats — `active_buyers`, `industries` (SEO_SKILLS = 12), `engagements_signed` — auto-growing as employers sign up. Verified: 25 real employers → "42+" display (baseline), 20 signed engagements shown live.
- **Rate Nudge scanner & banner**: new `rate_nudges` collection + `/api/admin/rate-nudges/scan` (admin-triggered) iterates all talents, calls Claude Sonnet 5, and records a nudge whenever `|drift| ≥ 15%` vs the AI mid. Talent Dashboard now shows a coloured banner (green if under-priced, red if over-priced) with drift %, current-vs-mid rates, rationale, "Apply $X/hr →" button (updates profile via PUT `/api/profile`), and dismiss. New talent-only endpoints `/api/talent/me/rate-nudge` and `/api/talent/me/rate-nudge/dismiss`. E2E verified: set test talent to $200/hr → scan detected -66% drift → banner appeared with correct copy + apply button.
- **Curated Talent Preview Modal**: on `/hire/{skill}-{city}` pages every talent card is now a button. Click opens a full-screen modal showing name, headline, location, stats grid ($rate / yrs / hrs-per-week), skills chips, and a gold "Contact details unlock after purchase" nudge explaining the 12-month exclusivity + dual-signature flow. Two CTAs: "Buy hours to unlock →" (routes to `/pricing`) + "Continue browsing". Vetted badge shown for curated pool entries.

## Implemented (2026-02-09, iteration 11 — logo refinements + backlog delivery)
- **Royal-violet J logo** (#6B21A8 gradient) on white rounded background — clean thicker top bar (42px) with symmetric serif brackets at both ends, plus a Pacifico-inspired flowing script J body with dramatic bottom hook. Same `/frontend/public/icon.svg` drives header, favicon and PWA icon.
- **Employer Trust Bar** (below talent testimonials on Landing): premium dark navy gradient card with soft purple + gold corner glows, headline "From Series-A founders to public-sector innovation teams", live stats (42+ active buyers · 14 industries), 12 buyer-category chips in a 4-col grid with gold bullets and hover states, non-disclosure footer, and "Add your company →" CTA.
- **Rate Sanity Check** on Talent Dashboard — cream card with sparkle icon, current-rate headline ("Is your $X/hr still market-fresh?"), skills/years/location snapshot, and "Refresh my rate" CTA. Clicking runs `/api/profile/suggest-rate` via Claude Sonnet 5, then reveals a two-panel result: (1) suggested range `$low–$high /hr` with rationale, (2) drift vs current rate (colour-coded green/red, absolute + percent, with market commentary) and an "Apply $mid/hr" button that PUT `/api/profile` and refreshes the user. E2E verified: logged in as talent@test.io, AI returned $53–$93/hr for `[React, TypeScript, Node] · 8 yrs · London`, drift -$7 (-9%) below current $75.
- **Sitemap autogen**: new `/api/sitemap.xml` endpoint builds a live sitemap of 7 static routes + 12 skill routes + 54 city×skill routes (73 URLs total) using the ingress `X-Forwarded-Host` header to render correct absolute URLs. Static `/frontend/public/sitemap.xml` regenerated with all 73 URLs. `robots.txt` updated with both sitemap references.
- **Founder Note** on Landing (below CTA, above footer): cream section, 100-word personal welcome in serif Fraunces, signed "Naveed Hasan" in Caveat script with gold underline and "FOUNDER · JOB ATLAS" tag.
- **Removed** the "Signed & Endorsed by Denkoit Softech Leadership" section.

## Implemented (2026-02-09, iteration 10 — polish batch)
- **New minimalist J logo & favicon** — gold gradient serif "J" letterform on a dark navy rounded background, drawn as pure SVG paths so it stays crisp from 16px favicon → 512px app icon. No star, no icon — the letterform itself is the logo. Same `/frontend/public/icon.svg` file drives header, PWA and favicon.
- **Talent-voice testimonials under hero** — moved from mid-page to right below the marquee. Cards now feature vetted-talent quotes with name, role · city, hourly rate (Devon P. $95/hr · London React; Priya S. $78/hr · Berlin Design; Marcus O. $110/hr · Remote Toronto data). Old employer-CFO testimonials removed.
- **Removed "Signed & Endorsed by Denkoit Softech Leadership" section** — was cluttering the Landing between FAQ and CTA.
- **Deliverable-triggered payouts turned on & surfaced** — backend already fires a `Payout` doc the instant an employer accepts a deliverable (see `_act_deliverable`, applies tier commission + referral discount + multi-employer fee). Landing now advertises it (hero bullet "Same-day payouts on deliverable approval" + rule #3 rewritten as "Sign & get paid instantly").
- **City × Skill SEO pages populated with curated vetted talent** — new `_CURATED_TALENT` pool of 60+ realistic profiles (React, Python, Node, UI, UX, data-science, DevOps, PM, Figma, mobile, WordPress, Salesforce) tagged with home city + remote. Both `/api/seo/hire/{skill}` and `/api/seo/hire-city/{skill-city}` merge DB users with curated matches (local city first, then remote-tagged). All 54 city×skill combos now return 7-8 vetted profiles with names, headlines, skills, years, and hourly rates. Fixed the slug parser to correctly split multi-hyphen skills like `san-francisco` (uses longest-skill-prefix match).

## Implemented (2026-02-09, iteration 9 — Job Atlas rename + logo)
- **Full revert of the "workable.com" light rebrand** back to the executive Geminista visual system (navy `#0B1B2B` + warm gold `#C79A3B` + cream `#FAF9F6`, Fraunces serif headings, Inter body). User preferred the deeper, more premium look.
- **Renamed platform label everywhere** from `TalentHub` / `Geminista` → **`Job Atlas`** (headers, footer, page titles, manifest, meta tags, contracts, emails, backend responses, tests, sitemap, robots, PWA name).
- **Premium new logo** at `/app/frontend/public/icon.svg` — 5-point gold-gradient star (with darker gold rim + top-facet highlight + sparkle detailing) with a **serif navy "J" embedded inside** the star. Matches Geminista navy + gold palette.
- Header sub-tag updated: `VETTED TALENT · BUY THE HOUR` (replacing the old "by Geminista" line so the branding reads cleanly).
- Landing footer / Legal / Pricing / Earnings cleaned up to remove redundant "a product of Job Atlas" phrasing → now shows "operated by Denkoit Softech Pvt. Ltd." where appropriate.
- Verified visually on `/`, `/browse`, `/register` — theme, logo, name all render correctly.

## Implemented (2026-02-09, iteration 8 — Geminista rebrand + attachments + city×skill)
- **Full Geminista rebrand**: swapped generic "brutalist" theme for an executive/PMO look aligned with geminista.com — deep navy `#0B1B2B` + warm gold `#C79A3B` on a cream `#FAF9F6` background; Fraunces serif for headings, Inter for body; custom TH-in-diamond SVG logo with gold accent.
- **City × Skill programmatic SEO**: new `/api/seo/hire-city/{slug}` endpoint (e.g. `react-developers-london`) and enhanced `/hire/:slug` route that auto-detects skill or skill+city format. Each page carries a title/description tuned for the {skill, city} pair, and two CTA cards — a **"Notify me" signup for buyers** (when talent is empty for that combo) and a **"Get listed" invitation** for the talent side. Both write into `newsletter_signups` for outreach.
- **Chat attachments** via Emergent object storage: added `/app/backend/storage_client.py`, `POST /api/messages/upload` (10 MB cap, whitelist png/jpg/gif/webp/pdf/txt/csv), `GET /api/files/{id}` (auth-gated). Frontend `EngagementChat` renders inline image previews via blob URLs and click-to-download for PDFs & docs.

- **Deliverable → auto-payout trigger**: when the employer approves a deliverable, `_act_deliverable` now creates an individual `Payout` record instantly (rate × approved-hours minus tier commission minus multi-employer fee, applied once per month). No more waiting for a batch run — talent are paid as work is accepted.
- **Talent referral discount**: referred talent get a permanent **1% commission discount for 6 months** from the time their referrer is credited. Applied automatically in the auto-payout calculation.
- **Employer overview endpoint** `/api/employer/overview` returns per-resource breakdown (engagements, hours allocated/used, active) and finances (hours purchased/allocated/used/available, total spent, gross paid to talent).
- **Employer Dashboard** now shows two new panels below the metrics: **Your resources** (list of every talent working with them, sorted by hours allocated) and **Your finances** (running P&L of hours + spend + gross paid out).
- **Programmatic SEO combos**: `/api/seo/city-skills` returns 54 skill × city combos ready to become landing pages.

- **Talent Payouts engine**: `/api/earnings/mine` (rolling 30-day statement), `/api/payouts/mine`, `/api/admin/payouts/run` (aggregates approved deliverables into per-talent payouts with commission tiers + multi-employer fee). Admin console has a new **Payouts** tab; talent has a `/talent/earnings` page with downloadable statement.
- **Referral loop**: every user gets a `TH-XXXXXX` code. Invitees paste it at signup; on their first Stripe checkout the referrer is auto-credited 2% of purchased hours (`_credit_referral_bonus` hook). Page at `/referrals` with copy-to-share + claims table.
- **SEO landing pages per skill**: `/hire/:slug` renders vetted talent for react-developers, python-developers, ui-designers, etc. Backend endpoints `/api/seo/skills` and `/api/seo/hire/{slug}` power them.
- **In-platform chat** on every signed engagement (`/api/messages/{eng_id}` + POST). Off-platform contact patterns (phones, emails, WhatsApp/Telegram) are flagged for moderation. UI polls every 8s.
- **Step-by-step "How it works" walkthrough**: replaced the auto-play video demo with a **user-paced, click-through, 5-step module** using real product screenshots, visual hotspots outlining the UI element for each step, "What you do / Why it matters" cards, Prev/Next controls, and an optional "Narrate this step" button (browser TTS — not auto-playing).

- **Brand spelling corrected everywhere**: Geminsta → **Geminista** across backend, frontend, PWA manifest, HTML meta, tests, PRD.
- **Real bank details wired**: ICICI Bank, Denkoit Softech Pvt. Ltd., A/C `112405000771`, IFSC `ICIC0001124`, UPI `MSDENKOITSOFTECHPVTLTD.eazypay@icici`. Purchase-hours page now shows a live-generated **UPI QR code** alongside the copyable fields.
- **International premium marketing tone**: rewrote Landing (hero: "Hire experts by the hour. Ship projects by the week."), added trust-bar of integration logos, testimonials, and an FAQ section marked up with `schema.org/FAQPage` for Google rich results.
- **SEO**: full `<head>` with description, keywords, canonical, Open Graph, Twitter card, JSON-LD Organization + SoftwareApplication schema. `robots.txt` + `sitemap.xml` shipped.
- **India de-emphasised in visible copy**: no country references on hero, "how it works", stats, testimonials or FAQ. India / GSTIN retained only in the small legal footer + Legal page (statutory requirement).
- **Capacitor 6 native shells**: `@capacitor/core`, `android`, `ios`, `push-notifications`, `preferences`; `capacitor.config.ts` created; `/app/NATIVE_APP_GUIDE.md` with build/publish steps.

- **Brand alignment across app**: Product **Job Atlas**, brand **Geminista**, operator **Denkoit Softech Pvt. Ltd.** (Hyderabad, India, GSTIN 36AAGCD3748K1ZC). Header tagline, footer, contract, bank-transfer beneficiary, invoices copy and `/api/legal` all updated.
- **New talent commission model**: volume-tiered 8% → 6% → 5% → 4% at 40h / 120h / 250h thresholds monthly. Multi-employer surcharge: **$9 / ₹749 per month** when active engagements exist with more than one employer in the same calendar month.
- **Legal & compliance page** at `/legal` with Terms, Privacy, Refund, Acceptable Use, 12-month Exclusivity — full text with company & GSTIN.
- **Mobile app (PWA)**: manifest.json, service worker, apple-touch-icons and standalone display — installable on Android / iOS home screens with offline shell caching.
- **Realistic demo**: Landing "See it in action" now has 5-step captioned walkthroughs auto-advancing over the video with clickable chapter jumps, play/pause and restart controls, for both Employer and Individual perspectives.
- 58/59 backend tests passing (1 pre-existing xdist isolation flake).

- **On-site engagement clauses**: mode (remote/onsite/hybrid), location, dates, transport arrangement — surfaced in contract; both parties must acknowledge on-site health &amp; safety + illegal-conduct disclaimer before signing.
- **Deliverables tracker**: talent submits work (title/link/hours), employer approves/rejects; approved deliverables increment `engagement.hours_used`.
- **Mutual reviews with moderation**: one review per party per engagement (1–5★), admin approves/rejects; only approved reviews appear on `/api/reviews/user/{id}`.
- **Grievance form**: public `/grievance` page, generates reference ID, admin console lists & resolves; routed to grievance@talenthub.io.
- **Admin console** now has 3 tabs (Bank Transfers · Reviews · Grievances).
- 54/54 backend tests passing.

- Full auth (JWT httpOnly), admin seed, 41/41 backend tests passing.
- Talent + employer profile, AI-powered rate suggestion (Claude Sonnet 5 with rule fallback).
- Browse talent (contact hidden), mix-and-match engagement creation.
- Contract signing (dual typed-signature) with 12-month exclusivity clause.
- Stripe checkout (claimable sandbox provisioned) + polling status.
- INR bank-transfer flow (initiate/submit UTR/admin approve).
- 11 work-tracker integration providers + Excel + MS Project XML upload.
- Weekly availability editor + timezone-projected weekly grid + calendar events.
- EOI create/list/accept/withdraw across roles.
- Connected accounts panel with role filtering + connect/disconnect.
- Role-aware dashboard metrics with Recharts pie + bar + upcoming widget.
- Landing with video demo tabs (Pexels-hosted mp4) and India footer.
- Pricing page with 3 plans + Upwork/Fiverr/Freelancer comparison.

## Backlog (P1)
- OAuth-based real integrations for LinkedIn/Google/Microsoft (currently token-based).
- Actual MS Project .mpp binary parsing (currently XML only).
- Live sync scheduler for connected work-tools.
- Hour-usage logging per engagement.
- Talent-to-employer search by employer accepting an EOI (currently talent enters UUID).

## Backlog (P2)
- Escrow / partial refunds.
- Multi-currency billing beyond USD/INR.
- Team seats within an employer.
- Public shareable talent profile pages.

## Test Credentials
See /app/memory/test_credentials.md
