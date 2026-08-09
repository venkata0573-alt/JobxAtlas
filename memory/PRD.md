# TalentHub — Skills Marketplace Platform

## Problem Statement (verbatim)
Build a platform where people showcase their skills; platform recommends hourly rate based
on experience/skill; employers purchase hours and mix-and-match talent; employers cannot
directly hire (nor talent directly work for) counterparties introduced through the platform
for at least 12 months; all contractual terms must be signed by both parties. Later additions:
pull work-tracking data from Monday, Wrike, MS Dynamics, ServiceNow, SAP, Jira, Asana,
Confluence, Trello, ClickUp, Notion (plus Excel/.xlsx and MS Project XML uploads). Crisp
dashboards with two role-specific views and shared components.

## Users
- **Talent** — showcases skills, gets AI-suggested rate, signs contracts, tracks work
- **Employer** — buys hour packages, mixes-and-matches talent, signs contracts, tracks work
- **Admin** — seeded on startup (`admin@talenthub.io / Admin@2026`)

## Architecture
- **Frontend**: React 19 + React Router + Tailwind + shadcn/ui + Phosphor icons + Recharts + sonner
- **Backend**: FastAPI + Motor(Mongo) + PyJWT + bcrypt + Stripe + emergentintegrations (Claude Sonnet 4.5)
- **Payments**: Stripe claimable sandbox
- **DB collections**: users, engagements, payment_transactions, integration_tokens, work_items, eois

## Implemented (2026-02)
- JWT httpOnly cookie auth (register, login, logout, me)
- Role-based access (talent/employer/admin)
- Talent profile with AI-powered rate suggestion (Claude Sonnet 4.5)
- Talent browse/search (contact hidden until engagement)
- Stripe hour package purchase (4 tiers: 10/50/100/500)
- Payment status polling + webhook credit
- Engagement lifecycle: create → typed-signature contract (both sides) → active + hours deducted
- 12-month exclusivity clause & UI warnings
- Third-party integrations (11 providers): Monday, Wrike, MS Dynamics, ServiceNow, SAP,
  Asana, Jira, Confluence, Trello, ClickUp, Notion
- File uploads: Excel (.xlsx/.xls) and MS Project XML
- Unified work log
- Role-aware dashboard metrics endpoint with shared components (Pie/Bar/Upcoming)
- Bento landing page (Swiss Brutalist theme)

## Backlog / Next
- P1: Real-time notifications on countersign / new engagement
- P1: Talent EOI (expression of interest) flow (endpoints scaffolded but no UI yet)
- P1: Emergent Google Social Login
- P2: Per-engagement time tracker + timesheet approval
- P2: Admin console (moderation, integrity checks for exclusivity breaches)
- P2: Encrypt integration tokens at rest
- P2: Rate limiting / brute-force lockout on `/api/auth/login`

## Env & Setup
- Backend env: MONGO_URL, DB_NAME, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, EMERGENT_LLM_KEY,
  STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_ACCOUNT_ID, STRIPE_WEBHOOK_SECRET
- Frontend env: REACT_APP_BACKEND_URL
- Test card: 4242 4242 4242 4242

## Testing
- Backend: 21/21 pytest passing (auth, profile, AI rate, browse, packages, checkout,
  engagements+signing with balance deduction, integrations, work upload, dashboard metrics)
