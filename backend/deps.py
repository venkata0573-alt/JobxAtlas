"""Shared dependencies + utilities for Job Atlas backend.

Everything that must be reusable across route modules lives here so route files
can `from deps import ...` without creating circular imports with server.py.
"""
import uuid
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from motor.motor_asyncio import AsyncIOMotorClient

# F-11: config is the sole env boundary. Constants below are thin
# proxies for settings.* so existing `from deps import X` imports keep
# working without a wider sweep of consumers.
from config import settings


# ---------- Config (sourced from backend/config.py) ----------
MONGO_URL = settings.mongo.url
DB_NAME = settings.mongo.db_name
JWT_SECRET = settings.auth.jwt_secret
JWT_ALGO = "HS256"
STRIPE_WEBHOOK_SECRET = settings.stripe.webhook_secret

# ---------- Clients ----------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# The single API router — every route module attaches to this so path prefixes stay consistent.
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jobatlas")


# ---------- Utility functions ----------
def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception:
        return False


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def create_token(user_id: str, kind: str = "access") -> str:
    exp = now() + (timedelta(minutes=60 * 24 * 7) if kind == "refresh" else timedelta(hours=12))
    payload = {"sub": user_id, "type": kind, "exp": exp}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def get_current_user(request: Request) -> dict:
    # S-26 CLOSED: cookie-only. The legacy `Authorization: Bearer` branch
    # is gone — no first-party client sends one (`grep -rn "Authorization"
    # frontend/src/` returns nothing), and the SSE `/talent/me/broadcasts/stream`
    # endpoint reads a `?token=` query param with its own inline jwt.decode
    # rather than going through here. Regression guard: tests/test_s26_no_bearer.py.
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        if payload.get("type") != "access":
            raise HTTPException(401, "Invalid token")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(401, "User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def set_auth_cookies(resp: Response, uid: str):
    access = create_token(uid, "access")
    refresh = create_token(uid, "refresh")
    resp.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    resp.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


# ---------- Domain constants (marketplace-facing lists) ----------
SEO_SKILLS = [
    "react-developers", "python-developers", "node-developers", "ui-designers",
    "ux-designers", "data-scientists", "devops-engineers", "product-managers",
    "figma-designers", "mobile-developers", "wordpress-developers", "salesforce-consultants",
]

SEO_CITIES = [
    "london", "new-york", "san-francisco", "berlin", "singapore",
    "dubai", "sydney", "toronto", "remote",
]

EMPLOYER_INDUSTRIES = [
    "Financial Services & Fintech",
    "Healthcare & Life Sciences",
    "SaaS & Enterprise Software",
    "E-commerce & Retail",
    "Media & Entertainment",
    "Education & EdTech",
    "Marketing & Advertising",
    "Manufacturing & Industrial",
    "Real Estate & PropTech",
    "Travel & Hospitality",
    "Energy & CleanTech",
    "Legal & Professional Services",
    "Non-profit & Public Sector",
    "Logistics & Supply Chain",
    "Cybersecurity",
    "AI & Data Platforms",
]

# Backwards-compat map: rewrites the earlier "buyer archetype" labels to the
# standardised industry taxonomy. Applied on startup so existing employer records
# retain their trust-bar visibility.
LEGACY_INDUSTRY_MAP = {
    "Series-B fintechs":       "Financial Services & Fintech",
    "PE-backed platforms":     "SaaS & Enterprise Software",
    "Health-tech scale-ups":   "Healthcare & Life Sciences",
    "YC-backed marketplaces":  "E-commerce & Retail",
    "Global consultancies":    "Legal & Professional Services",
    "Public-sector innovation":"Non-profit & Public Sector",
    "Series-A SaaS teams":     "SaaS & Enterprise Software",
    "Family-office ventures":  "Financial Services & Fintech",
    "Cross-border e-commerce": "E-commerce & Retail",
    "DTC brand houses":        "E-commerce & Retail",
    "Regulated data-cos":      "AI & Data Platforms",
    "ClimateTech pilots":      "Energy & CleanTech",
}

CITY_PRETTY = {
    "london": "London", "new-york": "New York", "san-francisco": "San Francisco",
    "berlin": "Berlin", "singapore": "Singapore", "dubai": "Dubai",
    "sydney": "Sydney", "toronto": "Toronto", "remote": "Remote",
}

# F-10 CLOSED: was hardcoded here; now env-tunable via settings.
RATE_DRIFT_THRESHOLD_PCT = settings.business_rules.rate_drift_threshold_pct


# ---------- Admin permission scopes ----------
# Fine-grained scopes an admin staff member can hold. Superadmin implies all.
ADMIN_SCOPES = [
    {"id": "support",       "label": "Customer Support",  "desc": "View users, log support notes, help resolve grievances."},
    {"id": "finance",       "label": "Finance & Payouts", "desc": "Approve bank transfers, run payouts, mark paid."},
    {"id": "moderation",    "label": "Moderation",        "desc": "Review reviews & grievances, resolve disputes."},
    {"id": "customization", "label": "Customization",     "desc": "Edit landing content, feature flags, pricing tiers."},
    {"id": "superadmin",    "label": "Superadmin",        "desc": "Manage admin staff, permissions, all scopes."},
]
ADMIN_SCOPE_IDS = {s["id"] for s in ADMIN_SCOPES}


def has_admin_scope(user: dict, scope: str) -> bool:
    if not user or user.get("role") != "admin":
        return False
    perms = user.get("admin_permissions") or []
    return "superadmin" in perms or scope in perms
