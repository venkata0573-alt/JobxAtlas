"""Shared dependencies + utilities for Job Atlas backend.

Everything that must be reusable across route modules lives here so route files
can `from deps import ...` without creating circular imports with server.py.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from motor.motor_asyncio import AsyncIOMotorClient


# ---------- Config ----------
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

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
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
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
    "Series-B fintechs",
    "PE-backed platforms",
    "Health-tech scale-ups",
    "YC-backed marketplaces",
    "Global consultancies",
    "Public-sector innovation",
    "Series-A SaaS teams",
    "Family-office ventures",
    "Cross-border e-commerce",
    "DTC brand houses",
    "Regulated data-cos",
    "ClimateTech pilots",
]

CITY_PRETTY = {
    "london": "London", "new-york": "New York", "san-francisco": "San Francisco",
    "berlin": "Berlin", "singapore": "Singapore", "dubai": "Dubai",
    "sydney": "Sydney", "toronto": "Toronto", "remote": "Remote",
}

RATE_DRIFT_THRESHOLD_PCT = 15
