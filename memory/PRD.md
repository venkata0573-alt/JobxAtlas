# TalentHub — PRD

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

## Implemented (2026-02-09, iteration 7 — auto-payout + employer overview)
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

- **Brand alignment across app**: Product **TalentHub**, brand **Geminista**, operator **Denkoit Softech Pvt. Ltd.** (Hyderabad, India, GSTIN 36AAGCD3748K1ZC). Header tagline, footer, contract, bank-transfer beneficiary, invoices copy and `/api/legal` all updated.
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
