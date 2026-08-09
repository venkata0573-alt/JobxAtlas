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

## Implemented (2026-02-09)
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
