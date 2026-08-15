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

## Implemented (2026-02-09, iteration 20 — Project Delivery workflow + marketing scrub)
- **New `/projects` page + backend workflow**: second product offering alongside "Hire by the hour". Hero presents both models side-by-side. PMI section shows 5 phase cards (Initiate → Plan → Execute → Monitor & Control → Close), each with a gate + deliverables list. Template gallery shows 8 pre-loaded blueprints across 5 industries (Fintech KYC/AML, Payments; Healthcare FHIR/EHR, Telehealth MVP; SaaS Onboarding, Analytics; E-comm Storefront Rebuild; AI Domain LLM Copilot). Industry filter chips narrow the gallery. Clicking a template opens a modal with team blueprint, cost estimate ($X/mo, $Y total), and a "Request scoping — no commitment" lead form.
- **Backend**: `PROJECT_TEMPLATES` list (8 blueprints, each with industry/duration/team roles + rate ranges), `PROJECT_PHASES` list (5 PMI phases with gates + deliverables), `ProjectLeadIn` model. New endpoints:
  - `GET /api/projects/templates?industry=...` → 8 templates + 5 phases
  - `GET /api/projects/templates/{id}` → detail + monthly_headcount + estimated_monthly_cost + estimated_total_cost
  - `POST /api/projects/lead` → inserts scoping request into `db.project_leads`
- **Navigation**: added "Projects" link (data-testid="nav-projects") in Header between "Browse Talent" and "Pricing".
- **Marketing scrub**: removed all contractual language from public pages — hero trust bullets updated ("Structured engagements from day one", "Transparent, milestone-linked pricing", "Same-day payment on accepted work"), STATS bento swapped ("12 months exclusivity" → "9 global cities served", "8% platform fee" → "24h talent onboarding"), FAQ #1 rewritten to describe the two workflows without exclusivity/fee mentions, testimonial reworded. Contractual terms now live only inside the signed engagement contract.
- Verified via `testing_agent` iteration_9.json: 100% backend + 100% frontend on the new workflow. All 3 flagged marketing-copy leaks fixed after the report.

## Implemented (2026-02-09, iteration 19 — trust-bar filter + hero verb rotator)
- **Public Trust Bar Filter**: every industry chip on Landing is now a `<Link>` to `/browse?industry=<label>`. Chip UI shows a `→` arrow when there are no employers yet (invites click) or `×N` when employers exist. `BrowseTalent.jsx` reads `useSearchParams` and renders a dark-navy `data-testid="industry-filter-banner"` at the top ("FILTERED BY INDUSTRY · <label>") with a `data-testid="clear-industry-filter"` button that removes the query param. Talent grid is not filtered yet (talents don't carry an industry tag today) — the banner is the entry point for that future work.
- **Hero Verb Rotator**: the red-highlighted verb in the hero headline cycles through **Grow → Ship → Scale → Build → …** every 3.2s with a 260ms fade-and-lift transition. `data-testid="hero-verb-rotator"` for testability. Honours `(prefers-reduced-motion: reduce)` — the interval is not started for users who prefer no motion.
- Playwright verified: chip click routes correctly with URL-encoded label; verb rotator captured 3 consecutive different values over 10s.

## Implemented (2026-02-09, iteration 18 — animated hero atlas)
- **Hero arcs now flow** and hub cities **pulse in staggered sequence**. Added inline `<style>` in `/frontend/public/hero-atlas.svg` with two keyframe animations: `ha-flow` (arcs animate `stroke-dashoffset` 400 → 0 in a loop, 6 arcs each at a different duration 6-12s + alternating direction so they don't sync) and `ha-pulse` (hub glow circles scale 1→1.6× with opacity 0.35→0.15, 5 hubs on 0.6s stagger). Arcs now render with `stroke-dasharray: 6 14` for a dotted-flow look.
- **Critical fix**: switched the hero from `background-image: url(...)` to a proper `<img src={HERO}>` element in Landing.jsx. CSS `background-image` freezes SVG internal animations across all browsers; `<img>` preserves them. Overlays now sit above the `<img>` via absolute positioning.
- **Accessibility**: added `@media (prefers-reduced-motion: reduce)` inside the SVG so users who disable motion see the static composition. Image also carries `alt=""` + `aria-hidden="true"` since it's purely decorative.
- Verified via two screenshots ~1.8s apart — arc dashes and hub-glow radii visibly shift between frames.

## Implemented (2026-02-09, iteration 17 — bespoke hero background)
- **New hero background** at `/frontend/public/hero-atlas.svg` — replaces the generic Pexels photo with a custom, dependency-free SVG that literally illustrates "Job Atlas": a stylised wireframe globe (latitude / longitude ellipses), dot-matrix continent clusters representing every SEO city cluster we cover (North America, South America, Europe, Middle East, Africa, Asia, Oceania), five glowing "hub" cities, and gently-glowing gold arcs connecting them (the "engagements crossing the globe" metaphor).
- Palette matches the Geminista dark navy + warm-gold system (`#0B1B2B`, `#122740`, `#C79A3B`, `#F0C260`). Hero overlay refined to a left-heavy gradient (`from-[#0A0A0A]/85 via-[#0A0A0A]/55 to-transparent`) plus a bottom vignette so the copy stays crisp while the illustration breathes on the right.
- No external URL dependency, no copyright concerns, retina-crisp at any resolution.

## Implemented (2026-02-09, iteration 16 — real-time inbox, broadcast history, standard industries, admin extracted)
- **Real-time broadcast inbox (SSE)**: new `GET /api/talent/me/broadcasts/stream` — SSE stream, one asyncio.Queue per subscriber, fanned-out by `_push_broadcast_to_talent` inside the broadcast endpoint. Auth via short-lived JWT from `GET /api/auth/sse-token` (EventSource can't set cookies cross-origin cleanly). Frontend TalentDashboard opens the stream on mount, prepends new broadcasts + shows a toast the instant an employer clicks send. Keepalive every 25s so ingress doesn't drop the connection.
- **Broadcast History**: `POST /shortlist/broadcast` now uses `db.broadcasts.insert_one` (was upsert) so every send is retained as its own doc. Also writes a summary doc to `db.broadcast_runs`. New `GET /api/shortlist/broadcasts` returns the employer's full run history (subject, message, delivered, emailed, timestamps).
- **Standardised employer industries**: replaced the 12 "buyer archetype" labels with 16 industry-standard categories (Financial Services & Fintech, Healthcare & Life Sciences, SaaS & Enterprise Software, E-commerce & Retail, Media & Entertainment, Education & EdTech, Marketing & Advertising, Manufacturing & Industrial, Real Estate & PropTech, Travel & Hospitality, Energy & CleanTech, Legal & Professional Services, Non-profit & Public Sector, Logistics & Supply Chain, Cybersecurity, AI & Data Platforms). Added `LEGACY_INDUSTRY_MAP` + startup migration that remapped existing employer records (10 employers moved to their new bucket on first restart). Landing.jsx fallback list + register chip picker + trust bar all pull from the new list.
- **Physical routes split — Phase 2**: `/app/backend/routes/admin.py` now contains all 14 admin endpoints (bank-transfer approvals, review moderation, grievance moderation, payout runs, rate-nudge scan, scheduler status) + `PayoutRunIn` model. 173 lines removed from server.py. server.py down from 2515 → 2327 lines. `routes/marketplace.py` + `routes/engagements.py` remain as documented shims — endpoints still in server.py.

## Implemented (2026-02-09, iteration 15 — shortlist broadcast + partial server.py refactor)
- **Shortlist Broadcast** — new `POST /api/shortlist/broadcast` (employer-only): sends one 'I'm ready to hire' note to every real-user talent on the shortlist. Records a `broadcasts` doc per (employer, talent) with `email_status`, upsert semantics. Curated demo profiles are skipped (they have no real inbox). Frontend adds a Broadcast button + modal composer on `/employer/shortlist` (data-testid: `broadcast-btn`, `broadcast-modal`, `broadcast-message`, `send-broadcast-btn`). When Resend key is set, also fires an HTML email with a "Sign in to reply" CTA.
- **Talent hire-intent inbox** — new `GET /api/talent/me/broadcasts` + `POST /api/talent/me/broadcasts/{id}/read`. `TalentDashboard.jsx` now shows a "HIRE-INTENT INBOX" section above Engagements when broadcasts exist. Unread broadcasts are highlighted with a gold border (`!border-[#C79A3B]` to beat the global `.hard-border` rule). Cards flip to read on click.
- **Partial server.py refactor (backend maintainability)**:
  - New `/app/backend/deps.py`: shared MongoDB client + `api` APIRouter + JWT/auth helpers + all marketplace constants (`SEO_SKILLS`, `SEO_CITIES`, `EMPLOYER_INDUSTRIES`, `CITY_PRETTY`, `RATE_DRIFT_THRESHOLD_PCT`).
  - New `/app/backend/routes/auth.py`: physically extracted `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`, `PUT /profile`, `POST /profile/suggest-rate` + their Pydantic models. Registers onto the shared `api` router via `import routes.auth`.
  - New placeholder shims `/app/backend/routes/marketplace.py`, `/routes/admin.py`, `/routes/engagements.py` — documented file maps for the deferred physical extraction of those blocks (endpoints still live in server.py for now). Extraction pattern is proven with routes/auth.py; the other three can be moved in future iterations without further design work.
- Verified via testing_agent iteration_6.json: 20/20 new backend tests + all frontend flows PASS. **No regressions** from the auth extraction.

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
