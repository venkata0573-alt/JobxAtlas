"""Idempotent synthetic seeder for the Phase 1a test stack.

Run inside the backend container:
    docker compose -f docker-compose.test.yml exec -T backend python tests/seed.py

Or directly (from repo root, with a Mongo reachable at MONGO_URL / DB_NAME):
    python backend/tests/seed.py

Every id is a fixed, human-readable constant exported from this module so
tests can import them and never depend on Faker/random values. All fixtures
share the password `Passw0rd!` — bcrypt hashed once at import time.

Personas & fixtures created:
  - admin_all       — admin with every scope (support/finance/moderation/customization/superadmin)
  - admin_noscope   — admin with admin_permissions=[] (for S-09 tests: role=='admin' without scope)
  - talent_clean    — clean profile, verified
  - talent_flagged  — revision_count=5, excessive_revisions=True, visibility=80
  - employer_card   — hours_balance=1000, stripe_payment_method_id set
  - employer_nocard — hours_balance=100, no card
  - engagement_signed     — employer_card ↔ talent_clean, both signatures, contract_signed
  - deliverable_submitted — one deliverable against engagement_signed, submitted
  - project_open + milestone_1 + invoice_open — one issued invoice, unpaid
  - grievance_open        — revision_dispute, dispute_fee unpaid
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python backend/tests/seed.py` from repo root: ensure backend/ is on
# sys.path so `import deps` resolves.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from passlib.hash import bcrypt  # noqa: E402

# Import the app's own Mongo client so DB_NAME / MONGO_URL match what the
# backend uses at runtime. deps.py raises KeyError at import if MONGO_URL,
# DB_NAME or JWT_SECRET are unset — same failure surface as the app.
from deps import db  # noqa: E402


# ---------------------------------------------------------------------------
# Fixed IDs. Tests import these directly. Do NOT randomize.
# ---------------------------------------------------------------------------

ADMIN_ALL_ID       = "seed-admin-all"
ADMIN_NOSCOPE_ID   = "seed-admin-noscope"
TALENT_CLEAN_ID    = "seed-talent-clean"
TALENT_FLAGGED_ID  = "seed-talent-flagged"
EMPLOYER_CARD_ID   = "seed-employer-card"
EMPLOYER_NOCARD_ID = "seed-employer-nocard"

ENGAGEMENT_SIGNED_ID     = "seed-engagement-signed"
DELIVERABLE_SUBMITTED_ID = "seed-deliverable-submitted"
PROJECT_OPEN_ID          = "seed-project-open"
MILESTONE_1_ID           = "seed-milestone-1"
INVOICE_OPEN_ID          = "seed-invoice-open"
GRIEVANCE_OPEN_ID        = "seed-grievance-open"

FIXTURE_PASSWORD = "Passw0rd!"
_PASSWORD_HASH = bcrypt.hash(FIXTURE_PASSWORD)  # ~200ms; compute once


PERSONA_EMAILS: dict[str, str] = {
    ADMIN_ALL_ID:       "admin-all@atlas-test.example.com",
    ADMIN_NOSCOPE_ID:   "admin-noscope@atlas-test.example.com",
    TALENT_CLEAN_ID:    "talent-clean@atlas-test.example.com",
    TALENT_FLAGGED_ID:  "talent-flagged@atlas-test.example.com",
    EMPLOYER_CARD_ID:   "employer-card@atlas-test.example.com",
    EMPLOYER_NOCARD_ID: "employer-nocard@atlas-test.example.com",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Persona docs
# ---------------------------------------------------------------------------

def _admin_all_doc() -> dict:
    return {
        "id": ADMIN_ALL_ID,
        "email": PERSONA_EMAILS[ADMIN_ALL_ID],
        "password_hash": _PASSWORD_HASH,
        "role": "admin",
        "name": "Admin All-Scopes",
        "admin_permissions": ["support", "finance", "moderation", "customization", "superadmin"],
        "email_verified": True,
        "verification_status": "verified",
        "created_at": _now_iso(),
    }


def _admin_noscope_doc() -> dict:
    return {
        "id": ADMIN_NOSCOPE_ID,
        "email": PERSONA_EMAILS[ADMIN_NOSCOPE_ID],
        "password_hash": _PASSWORD_HASH,
        "role": "admin",
        "name": "Admin No-Scope",
        # Explicit empty list — S-09 tests assert this admin cannot pass any
        # `_require_scope(user, "X")` call but CAN pass role=='admin' checks.
        "admin_permissions": [],
        "email_verified": True,
        "verification_status": "verified",
        "created_at": _now_iso(),
    }


def _talent_clean_doc() -> dict:
    return {
        "id": TALENT_CLEAN_ID,
        "email": PERSONA_EMAILS[TALENT_CLEAN_ID],
        "password_hash": _PASSWORD_HASH,
        "role": "talent",
        "name": "Talent Clean",
        "email_verified": True,
        "verification_status": "verified",
        "verified_at": _now_iso(),
        "hours_balance": 0,
        "profile": {
            "headline": "Full-stack engineer",
            "bio": "Seeded clean-record talent",
            "skills": ["React", "Python"],
            "years_experience": 5,
            "hourly_rate": 60,
            "location": "Remote — Test",
            "visibility_score": 100,
            "rate_bias_pct": 0,
            "clean_streak": 0,
            "revision_flags": {},
            "under_review": False,
            "excessive_revisions": False,
            "abusive_pattern_flag": False,
        },
        "created_at": _now_iso(),
    }


def _talent_flagged_doc() -> dict:
    return {
        "id": TALENT_FLAGGED_ID,
        "email": PERSONA_EMAILS[TALENT_FLAGGED_ID],
        "password_hash": _PASSWORD_HASH,
        "role": "talent",
        "name": "Talent Flagged",
        "email_verified": True,
        "verification_status": "verified",
        "verified_at": _now_iso(),
        "hours_balance": 0,
        "profile": {
            "headline": "Senior IC",
            "bio": "Seeded flagged talent at penalty threshold",
            "skills": ["React", "TypeScript"],
            "years_experience": 7,
            "hourly_rate": 80,
            "location": "Remote — Test",
            "visibility_score": 80,     # 100 - REVISION_VISIBILITY_PENALTY(20)
            "rate_bias_pct": -10,       # -REVISION_RATE_NUDGE_PENALTY(10)
            "clean_streak": 0,
            "revision_flags": {
                "excessive_revisions_at": _now_iso(),
                "under_review_at": _now_iso(),
            },
            "under_review": True,
            "excessive_revisions": True,
            "abusive_pattern_flag": False,
        },
        "created_at": _now_iso(),
    }


def _employer_card_doc() -> dict:
    return {
        "id": EMPLOYER_CARD_ID,
        "email": PERSONA_EMAILS[EMPLOYER_CARD_ID],
        "password_hash": _PASSWORD_HASH,
        "role": "employer",
        "name": "Employer Card-On-File",
        "email_verified": True,
        "verification_status": "verified",
        "verified_at": _now_iso(),
        "hours_balance": 1000,          # enough to create engagements
        "stripe_customer_id": "cus_seed_card_on_file",
        "stripe_payment_method_id": "pm_seed_card_on_file",
        "hero_placement": True,
        "profile": {"company_name": "CardCo", "company_industry": "Technology"},
        "created_at": _now_iso(),
    }


def _employer_nocard_doc() -> dict:
    return {
        "id": EMPLOYER_NOCARD_ID,
        "email": PERSONA_EMAILS[EMPLOYER_NOCARD_ID],
        "password_hash": _PASSWORD_HASH,
        "role": "employer",
        "name": "Employer No-Card",
        "email_verified": True,
        "verification_status": "verified",
        "verified_at": _now_iso(),
        "hours_balance": 100,           # small buffer; still enough to sign
        "profile": {"company_name": "NoCardCo", "company_industry": "Technology"},
        "created_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Business objects (all attached to fixed personas above)
# ---------------------------------------------------------------------------

def _engagement_signed_doc() -> dict:
    return {
        "id": ENGAGEMENT_SIGNED_ID,
        "employer_id": EMPLOYER_CARD_ID,
        "employer_name": "Employer Card-On-File",
        "talent_id": TALENT_CLEAN_ID,
        "talent_name": "Talent Clean",
        "hours_allocated": 20,
        "hours_used": 0,
        "hourly_rate": 60,
        "scope": "Seed engagement — build test coverage widget",
        "mode": "remote",
        "location": "",
        "start_date": "",
        "end_date": "",
        "transport": "",
        "onsite_notes": "",
        "status": "contract_signed",
        "employer_signature": {
            "name": "Employer Card-On-File",
            "signed_at": _now_iso(),
            "user_id": EMPLOYER_CARD_ID,
            "onsite_ack": False,
        },
        "talent_signature": {
            "name": "Talent Clean",
            "signed_at": _now_iso(),
            "user_id": TALENT_CLEAN_ID,
            "onsite_ack": False,
        },
        "created_at": _now_iso(),
        "exclusive_until": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
    }


def _deliverable_submitted_doc() -> dict:
    return {
        "id": DELIVERABLE_SUBMITTED_ID,
        "engagement_id": ENGAGEMENT_SIGNED_ID,
        "talent_id": TALENT_CLEAN_ID,
        "employer_id": EMPLOYER_CARD_ID,
        "title": "Seed deliverable — v1",
        "description": "Submitted, awaiting employer decision",
        "link": "https://example.test/seed-v1",
        "hours_claimed": 5,
        "file_ids": [],
        "status": "submitted",
        "feedback": "",
        "revision_count": 0,
        "latest_revision_id": None,
        "dispute_grievance_id": None,
        "created_at": _now_iso(),
    }


def _project_doc() -> dict:
    return {
        "id": PROJECT_OPEN_ID,
        "employer_id": EMPLOYER_CARD_ID,
        "title": "Seed project",
        "industry": "Technology",
        "status": "active",
        "phases": [
            {"name": "Discovery", "status": "in_progress", "signoff": None},
            {"name": "Delivery", "status": "pending", "signoff": None},
        ],
        "created_at": _now_iso(),
    }


def _milestone_doc() -> dict:
    return {
        "id": MILESTONE_1_ID,
        "project_id": PROJECT_OPEN_ID,
        "name": "Milestone 1 — Discovery signoff",
        "amount": 1000.0,
        "percent": 25,
        "due_date": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "status": "invoiced",
        "invoiced_at": _now_iso(),
        "paid_at": None,
    }


def _invoice_doc() -> dict:
    return {
        "id": INVOICE_OPEN_ID,
        "project_id": PROJECT_OPEN_ID,
        "milestone_id": MILESTONE_1_ID,
        "employer_id": EMPLOYER_CARD_ID,
        "amount": 1000.0,
        "currency": "usd",
        "ref": "INV-SEED-0001",
        "status": "open",
        "issued_at": _now_iso(),
        "due_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "paid_at": None,
    }


def _grievance_doc() -> dict:
    dispute_fee_usd = int(os.environ.get("REVISION_DISPUTE_FEE_USD", "49"))
    return {
        "id": GRIEVANCE_OPEN_ID,
        "kind": "revision_dispute",
        "ref": "GR-SEED-0001",
        "engagement_id": ENGAGEMENT_SIGNED_ID,
        "deliverable_id": DELIVERABLE_SUBMITTED_ID,
        "talent_id": TALENT_FLAGGED_ID,
        "employer_id": EMPLOYER_CARD_ID,
        "reason": "Seed dispute — testing fee lifecycle",
        "status": "open",
        "ruling": None,
        "dispute_fee": {
            "amount_usd": dispute_fee_usd,
            "owed_by_id": TALENT_FLAGGED_ID,
            "payment_status": "unpaid",
            "session_id": None,
            "payment_intent_id": None,
            "refund_id": None,
            "paid_at": None,
        },
        "created_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Idempotent upserts
# ---------------------------------------------------------------------------

async def _upsert(collection: str, doc: dict) -> None:
    await db[collection].update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


async def seed() -> dict[str, int]:
    counts: dict[str, int] = {}

    for doc in (
        _admin_all_doc(),
        _admin_noscope_doc(),
        _talent_clean_doc(),
        _talent_flagged_doc(),
        _employer_card_doc(),
        _employer_nocard_doc(),
    ):
        await _upsert("users", doc)
    counts["users"] = 6

    await _upsert("engagements", _engagement_signed_doc())
    counts["engagements"] = 1

    await _upsert("deliverables", _deliverable_submitted_doc())
    counts["deliverables"] = 1

    await _upsert("projects", _project_doc())
    await _upsert("project_milestones", _milestone_doc())
    await _upsert("project_invoices", _invoice_doc())
    counts["projects"] = 1
    counts["project_milestones"] = 1
    counts["project_invoices"] = 1

    await _upsert("grievances", _grievance_doc())
    counts["grievances"] = 1

    return counts


async def _main() -> int:
    counts = await seed()
    total = sum(counts.values())
    print(f"seeded {total} docs across {len(counts)} collections: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
