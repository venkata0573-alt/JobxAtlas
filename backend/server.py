from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import uuid
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any, Dict

import bcrypt
import jwt
import stripe
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, ConfigDict

# Local
from ai_service import suggest_hourly_rate
from work_integrations import parse_excel_bytes, parse_project_xml_bytes, list_supported_providers, fetch_from_provider
from storage_client import init_storage, put_object, get_object, APP_NAME as STORAGE_APP

# Shared deps (single source of truth for db + api router + auth helpers + constants)
from deps import (
    api, db, client, logger,
    MONGO_URL, DB_NAME, JWT_SECRET, JWT_ALGO, STRIPE_WEBHOOK_SECRET,
    hash_pw, verify_pw, now, new_id, create_token,
    get_current_user, set_auth_cookies,
    SEO_SKILLS, SEO_CITIES, EMPLOYER_INDUSTRIES, CITY_PRETTY,
    RATE_DRIFT_THRESHOLD_PCT,
)

# ---------- App bootstrapping ----------
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"

app = FastAPI(title="Job Atlas API")


# ---------- Utils moved to deps.py ----------
# hash_pw, verify_pw, now, create_token, new_id, get_current_user, set_auth_cookies
# are all imported from `deps` above.


# ---------- Models ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str  # 'talent' | 'employer'
    company_industry: Optional[str] = ""  # employer-only self-selected industry


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileIn(BaseModel):
    headline: Optional[str] = ""
    bio: Optional[str] = ""
    skills: List[str] = []
    years_experience: Optional[int] = 0
    hourly_rate: Optional[float] = 0.0
    location: Optional[str] = ""
    portfolio_url: Optional[str] = ""
    avatar_url: Optional[str] = ""
    company: Optional[str] = ""
    company_logo_url: Optional[str] = ""
    company_industry: Optional[str] = ""
    portfolio_images: List[str] = []
    timezone: Optional[str] = "UTC"
    weekly_capacity_hours: Optional[int] = 40


class AvailabilityIn(BaseModel):
    timezone: str = "UTC"
    slots: List[Dict[str, Any]] = []  # [{day:0-6, start:"09:00", end:"17:00"}]


class EOICreateIn(BaseModel):
    employer_id: Optional[str] = None  # None => open EOI to any employer
    message: str
    proposed_hours_per_week: int = 10
    start_date: Optional[str] = ""


class EOIActionIn(BaseModel):
    scope: Optional[str] = ""
    hours: Optional[int] = None


class RateSuggestIn(BaseModel):
    skills: List[str]
    years_experience: int
    location: Optional[str] = "Global"


class CheckoutIn(BaseModel):
    package_id: str
    origin_url: str


class BankTransferInitIn(BaseModel):
    package_id: str


class BankTransferSubmitIn(BaseModel):
    payment_id: str
    utr: str          # UTR / UPI transaction reference
    payer_note: Optional[str] = ""


class EngagementCreateIn(BaseModel):
    talent_id: str
    hours: int
    scope: str
    mode: str = "remote"                # "remote" | "onsite" | "hybrid"
    location: Optional[str] = ""        # required when mode != remote
    start_date: Optional[str] = ""
    end_date: Optional[str] = ""
    transport: Optional[str] = ""       # "employer" | "talent" | "mutual" | ""
    onsite_notes: Optional[str] = ""


class SignContractIn(BaseModel):
    engagement_id: str
    signature: str
    onsite_ack: Optional[bool] = False  # required True when mode != remote


class DeliverableIn(BaseModel):
    engagement_id: str
    title: str
    description: Optional[str] = ""
    link: Optional[str] = ""
    hours_claimed: Optional[float] = 0
    file_ids: List[str] = []           # optional attachments from /files/upload


class DeliverableActionIn(BaseModel):
    feedback: Optional[str] = ""


class ReviewIn(BaseModel):
    engagement_id: str
    rating: int                          # 1-5
    text: Optional[str] = ""


class GrievanceIn(BaseModel):
    subject: str
    engagement_id: Optional[str] = ""
    against_party_id: Optional[str] = ""
    description: str
    contact_email: EmailStr
    incident_date: Optional[str] = ""


class PayoutRunIn(BaseModel):
    period_start: str
    period_end: str
    currency: str = "usd"


class ReferralClaimIn(BaseModel):
    code: str


class MessageIn(BaseModel):
    engagement_id: str
    text: str


class IntegrationConnectIn(BaseModel):
    provider: str
    api_token: str
    workspace: Optional[str] = ""


class AccountConnectIn(BaseModel):
    provider: str
    handle: str        # e.g. LinkedIn URL, GitHub username, email
    api_token: Optional[str] = ""  # optional API/OAuth token
    metadata: Optional[Dict[str, Any]] = {}


# ---------- Hour Packages (server-side) ----------
# Company operates from India. Show USD via Stripe and INR for local bank transfer.
USD_TO_INR = 83
PACKAGES = {
    "starter_10":     {"name": "Starter",    "hours": 10,  "amount": 300.0,   "amount_inr": 300 * USD_TO_INR,   "currency": "usd"},
    "growth_50":      {"name": "Growth",     "hours": 50,  "amount": 1400.0,  "amount_inr": 1400 * USD_TO_INR,  "currency": "usd"},
    "scale_100":      {"name": "Scale",      "hours": 100, "amount": 2600.0,  "amount_inr": 2600 * USD_TO_INR,  "currency": "usd"},
    "enterprise_500": {"name": "Enterprise", "hours": 500, "amount": 12000.0, "amount_inr": 12000 * USD_TO_INR, "currency": "usd"},
}

# Receiving bank — Denkoit Softech Pvt. Ltd. (Job Atlas / Job Atlas)
COMPANY_BANK = {
    "beneficiary": "Denkoit Softech Pvt. Ltd.",
    "brand": "Job Atlas",
    "product": "Job Atlas",
    "bank": "ICICI Bank",
    "branch": "—",
    "account_number": "112405000771",
    "ifsc": "ICIC0001124",
    "swift": "ICICINBBCTS",
    "upi": "MSDENKOITSOFTECHPVTLTD.eazypay@icici",
    "gstin": "36AAGCD3748K1ZC",
    "note": "Quote the reference ID exactly when transferring so we can credit your hours quickly.",
}


# ---------- Auth Routes (extracted to routes/auth.py) ----------
# The endpoints /auth/register, /auth/login, /auth/logout, /auth/me,
# PUT /profile, POST /profile/suggest-rate now live in routes/auth.py and are
# registered onto the shared `api` router when server.py imports that module.
import routes.auth  # noqa: E402,F401  (registers endpoints via decorators)
import routes.admin  # noqa: E402,F401  (registers /admin/* endpoints)


# ---------- Browse Talent (public listing but contact hidden) ----------
@api.get("/talent")
async def list_talent(q: Optional[str] = None, skill: Optional[str] = None,
                      industry: Optional[str] = None, min_exp: int = 0):
    query = {"role": "talent"}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                        {"profile.headline": {"$regex": q, "$options": "i"}}]
    if skill:
        query["profile.skills"] = {"$regex": skill, "$options": "i"}
    if industry:
        # Match talents who have self-tagged this industry, OR who have delivered
        # engagements to an employer in this industry (past-work signal).
        past_work_employer_ids = await db.engagements.distinct(
            "employer_id",
            {"status": {"$in": ["contract_signed", "active", "completed"]}},
        )
        employers_in_industry = await db.users.distinct(
            "id",
            {"role": "employer", "id": {"$in": past_work_employer_ids},
             "profile.company_industry": industry},
        )
        talent_ids_via_engagements = await db.engagements.distinct(
            "talent_id",
            {"employer_id": {"$in": employers_in_industry},
             "status": {"$in": ["contract_signed", "active", "completed"]}},
        )
        query["$or"] = (query.get("$or", [])) + [
            {"profile.industries": industry},
            {"id": {"$in": talent_ids_via_engagements}},
        ]
    if min_exp:
        query["profile.years_experience"] = {"$gte": int(min_exp)}
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0, "email": 0, "integrations": 0})
    items = await cursor.to_list(200)
    return items


# ---------- Browse Employers (talent-facing) ----------
@api.get("/employers")
async def list_employers(
    q: Optional[str] = None,
    industry: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Talent can discover companies actively on Job Atlas and raise an EOI
    directly. Only exposes public-facing fields: name, company, industry, city,
    hours_balance-derived buying signal. Never exposes email or contact info."""
    if user["role"] not in ("talent", "admin"):
        raise HTTPException(403, "Talent only")
    query: Dict[str, Any] = {"role": "employer"}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"profile.company_name": {"$regex": q, "$options": "i"}},
            {"profile.headline": {"$regex": q, "$options": "i"}},
        ]
    if industry:
        query["profile.company_industry"] = industry
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0, "email": 0,
                                    "integrations": 0, "connected_accounts": 0})
    raw = await cursor.to_list(300)
    # Return a lean, safe shape and a "buying signal" chip.
    open_role_map: Dict[str, int] = {}
    open_engs = await db.engagements.find(
        {"status": {"$in": ["pending_signatures", "contract_signed", "active"]}},
        {"employer_id": 1, "_id": 0},
    ).to_list(2000)
    for e in open_engs:
        open_role_map[e.get("employer_id")] = open_role_map.get(e.get("employer_id"), 0) + 1
    out = []
    for u in raw:
        p = u.get("profile") or {}
        out.append({
            "id": u["id"],
            "name": u.get("name"),
            "company_name": p.get("company_name") or u.get("name"),
            "company_industry": p.get("company_industry") or "",
            "company_size": p.get("company_size") or "",
            "location": p.get("location") or "",
            "headline": p.get("headline") or "",
            "hours_balance": int(u.get("hours_balance") or 0),
            "active_engagements": open_role_map.get(u["id"], 0),
            "created_at": u.get("created_at"),
        })
    # Sort: those with balance first (they're ready to hire), then most active.
    out.sort(key=lambda x: (-x["hours_balance"], -x["active_engagements"]))
    return {"items": out, "count": len(out)}


@api.get("/employers/{employer_id}")
async def get_employer_public(employer_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in ("talent", "admin"):
        raise HTTPException(403, "Talent only")
    u = await db.users.find_one({"id": employer_id, "role": "employer"},
                                 {"_id": 0, "password_hash": 0, "email": 0,
                                  "integrations": 0, "connected_accounts": 0})
    if not u:
        raise HTTPException(404, "Employer not found")
    p = u.get("profile") or {}
    return {
        "id": u["id"], "name": u.get("name"),
        "company_name": p.get("company_name") or u.get("name"),
        "company_industry": p.get("company_industry") or "",
        "company_size": p.get("company_size") or "",
        "location": p.get("location") or "",
        "headline": p.get("headline") or "",
        "hours_balance": int(u.get("hours_balance") or 0),
        "created_at": u.get("created_at"),
    }


@api.get("/earnings/mine")
async def my_earnings(user: dict = Depends(get_current_user), start: str = "", end: str = ""):
    if user["role"] != "talent":
        raise HTTPException(403, "Talent only")
    end_iso = end or now().isoformat()
    start_iso = start or (now() - timedelta(days=30)).isoformat()
    return await _compute_talent_earnings(user["id"], start_iso, end_iso)


@api.get("/talent/{talent_id}")
async def get_talent(talent_id: str, user: dict = Depends(get_current_user)):
    t = await db.users.find_one({"id": talent_id, "role": "talent"}, {"_id": 0, "password_hash": 0, "integrations": 0})
    if not t:
        raise HTTPException(404, "Talent not found")
    # Only reveal email if employer has purchased hours AND active engagement exists
    has_engagement = await db.engagements.find_one({"employer_id": user["id"], "talent_id": talent_id,
                                                     "status": {"$in": ["contract_signed", "active"]}})
    if user["role"] != "employer" or not has_engagement:
        t.pop("email", None)
    return t


# ---------- Stripe: purchase hour packages ----------
@api.get("/packages")
async def get_packages():
    return {"packages": PACKAGES, "bank": COMPANY_BANK, "usd_to_inr": USD_TO_INR,
            "upi_qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&margin=8&data=upi%3A%2F%2Fpay%3Fpa%3D{COMPANY_BANK['upi']}%26pn%3D{COMPANY_BANK['beneficiary'].replace(' ', '%20')}%26cu%3DINR"}


# ---------- Bank Transfer Flow (India) ----------
def _short_ref() -> str:
    return "TH-" + secrets.token_hex(4).upper()


@api.post("/payments/bank/initiate")
async def bank_initiate(payload: BankTransferInitIn, user: dict = Depends(get_current_user)):
    if user["role"] != "employer":
        raise HTTPException(403, "Only employers can purchase hours")
    pkg = PACKAGES.get(payload.package_id)
    if not pkg:
        raise HTTPException(400, "Invalid package")
    ref = _short_ref()
    pid = new_id()
    await db.payment_transactions.insert_one({
        "id": pid, "session_id": f"bank_{pid}", "user_id": user["id"],
        "package_id": payload.package_id, "hours": pkg["hours"],
        "amount": pkg["amount_inr"] * 100, "currency": "inr",
        "method": "bank_transfer", "reference": ref,
        "status": "awaiting_transfer", "payment_status": "pending",
        "created_at": now().isoformat(), "updated_at": now().isoformat(),
    })
    return {
        "payment_id": pid,
        "reference": ref,
        "package": pkg,
        "amount_inr": pkg["amount_inr"],
        "bank": COMPANY_BANK,
        "upi_qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&margin=8&data=upi%3A%2F%2Fpay%3Fpa%3D{COMPANY_BANK['upi']}%26pn%3D{COMPANY_BANK['beneficiary'].replace(' ', '%20')}%26am%3D{pkg['amount_inr']}%26tn%3D{ref}%26cu%3DINR",
    }


@api.post("/payments/bank/submit")
async def bank_submit(payload: BankTransferSubmitIn, user: dict = Depends(get_current_user)):
    rec = await db.payment_transactions.find_one({"id": payload.payment_id, "user_id": user["id"]})
    if not rec:
        raise HTTPException(404, "Payment not found")
    if rec.get("method") != "bank_transfer":
        raise HTTPException(400, "Not a bank-transfer payment")
    if not payload.utr.strip():
        raise HTTPException(400, "UTR / reference number is required")
    await db.payment_transactions.update_one({"id": payload.payment_id}, {"$set": {
        "utr": payload.utr.strip(),
        "payer_note": payload.payer_note or "",
        "status": "awaiting_verification",
        "updated_at": now().isoformat(),
    }})
    return {"ok": True, "status": "awaiting_verification"}


@api.get("/payments/mine")
async def my_payments(user: dict = Depends(get_current_user)):
    items = await db.payment_transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


# Admin: list pending bank transfers + approve
@api.post("/payments/checkout")
async def create_checkout(payload: CheckoutIn, user: dict = Depends(get_current_user)):
    if user["role"] != "employer":
        raise HTTPException(403, "Only employers can purchase hours")
    pkg = PACKAGES.get(payload.package_id)
    if not pkg:
        raise HTTPException(400, "Invalid package")
    origin = payload.origin_url.rstrip("/")
    session = stripe.checkout.Session.create(
        line_items=[{"price_data": {"currency": pkg["currency"],
                                     "product_data": {"name": f"Job Atlas {pkg['name']} - {pkg['hours']} hours"},
                                     "unit_amount": int(pkg["amount"] * 100)}, "quantity": 1}],
        mode="payment",
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"user_id": user["id"], "package_id": payload.package_id, "hours": str(pkg["hours"])},
    )
    await db.payment_transactions.insert_one({
        "id": new_id(), "session_id": session.id, "user_id": user["id"],
        "package_id": payload.package_id, "hours": pkg["hours"],
        "amount": pkg["amount"] * 100, "currency": pkg["currency"],
        "status": "initiated", "payment_status": "pending",
        "created_at": now().isoformat(), "updated_at": now().isoformat(),
    })
    return {"checkout_url": session.url, "session_id": session.id}


async def _credit_hours_if_paid(record: dict, session_obj) -> dict:
    if record.get("payment_status") == "paid":
        return record
    if session_obj.payment_status == "paid" or session_obj.status == "complete":
        upd = await db.payment_transactions.find_one_and_update(
            {"session_id": record["session_id"], "payment_status": {"$ne": "paid"}},
            {"$set": {"status": "completed", "payment_status": "paid",
                      "updated_at": now().isoformat()}},
            return_document=True,
        )
        if upd:
            await db.users.update_one({"id": record["user_id"]}, {"$inc": {"hours_balance": record["hours"]}})
            try:
                await _credit_referral_bonus(record["user_id"], int(record["hours"]))
            except Exception:
                pass
            return await db.payment_transactions.find_one({"session_id": record["session_id"]}, {"_id": 0})
    return record


@api.get("/payments/status/{session_id}")
async def payment_status(session_id: str):
    rec = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Not found")
    if rec.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            rec = await _credit_hours_if_paid(rec, s)
        except stripe.error.StripeError:
            pass
    return {"session_id": rec["session_id"], "status": rec["status"],
            "payment_status": rec["payment_status"], "hours": rec.get("hours", 0)}


@api.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Invalid signature")
    obj, t = event["data"]["object"], event["type"]
    if t == "checkout.session.completed":
        rec = await db.payment_transactions.find_one({"session_id": obj["id"]})
        if rec and rec.get("payment_status") != "paid":
            await db.payment_transactions.update_one(
                {"session_id": obj["id"], "payment_status": {"$ne": "paid"}},
                {"$set": {"status": "completed", "payment_status": "paid", "updated_at": now().isoformat()}})
            await db.users.update_one({"id": rec["user_id"]}, {"$inc": {"hours_balance": rec["hours"]}})
    return {"ok": True}


# ---------- Engagements & Contracts ----------
@api.post("/engagements")
async def create_engagement(payload: EngagementCreateIn, user: dict = Depends(get_current_user)):
    if user["role"] != "employer":
        raise HTTPException(403, "Only employers can create engagements")
    if user.get("hours_balance", 0) < payload.hours:
        raise HTTPException(400, "Insufficient hours balance. Purchase more hours first.")
    talent = await db.users.find_one({"id": payload.talent_id, "role": "talent"})
    if not talent:
        raise HTTPException(404, "Talent not found")
    if payload.mode not in ("remote", "onsite", "hybrid"):
        raise HTTPException(400, "mode must be remote, onsite or hybrid")
    if payload.mode != "remote" and not (payload.location or "").strip():
        raise HTTPException(400, "Location is required for on-site / hybrid engagements")
    eng = {
        "id": new_id(), "employer_id": user["id"], "employer_name": user["name"],
        "talent_id": payload.talent_id, "talent_name": talent["name"],
        "hours_allocated": payload.hours, "hours_used": 0,
        "scope": payload.scope, "status": "pending_signatures",
        "mode": payload.mode, "location": payload.location or "",
        "start_date": payload.start_date or "", "end_date": payload.end_date or "",
        "transport": payload.transport or "", "onsite_notes": payload.onsite_notes or "",
        "employer_signature": None, "talent_signature": None,
        "created_at": now().isoformat(),
        "exclusive_until": (now() + timedelta(days=365)).isoformat(),
    }
    await db.engagements.insert_one(eng)
    eng.pop("_id", None)
    return eng


@api.get("/engagements")
async def list_engagements(user: dict = Depends(get_current_user)):
    key = "employer_id" if user["role"] == "employer" else "talent_id"
    items = await db.engagements.find({key: user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api.get("/engagements/{eid}")
async def get_engagement(eid: str, user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": eid}, {"_id": 0})
    if not eng or user["id"] not in (eng["employer_id"], eng["talent_id"]):
        raise HTTPException(404, "Not found")
    return eng


@api.post("/engagements/sign")
async def sign_contract(payload: SignContractIn, user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": payload.engagement_id})
    if not eng or user["id"] not in (eng["employer_id"], eng["talent_id"]):
        raise HTTPException(404, "Engagement not found")
    if eng.get("mode", "remote") != "remote" and not payload.onsite_ack:
        raise HTTPException(400, "You must acknowledge the on-site health, safety and transport terms")
    field = "employer_signature" if user["id"] == eng["employer_id"] else "talent_signature"
    sig = {"name": payload.signature, "signed_at": now().isoformat(),
           "user_id": user["id"], "onsite_ack": bool(payload.onsite_ack)}
    update = {field: sig}
    other = eng.get("talent_signature") if field == "employer_signature" else eng.get("employer_signature")
    if other:
        update["status"] = "contract_signed"
        await db.users.update_one({"id": eng["employer_id"]}, {"$inc": {"hours_balance": -eng["hours_allocated"]}})
    await db.engagements.update_one({"id": payload.engagement_id}, {"$set": update})
    return await db.engagements.find_one({"id": payload.engagement_id}, {"_id": 0})


# ---------- Deliverables ----------
@api.post("/deliverables")
async def submit_deliverable(payload: DeliverableIn, user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": payload.engagement_id})
    if not eng or user["id"] != eng.get("talent_id"):
        raise HTTPException(403, "Only the engaged talent can submit deliverables")
    if eng.get("status") != "contract_signed":
        raise HTTPException(400, "Contract must be signed by both parties before submitting")
    doc = {
        "id": new_id(), "engagement_id": payload.engagement_id,
        "talent_id": user["id"], "employer_id": eng["employer_id"],
        "title": payload.title, "description": payload.description or "",
        "link": payload.link or "", "hours_claimed": float(payload.hours_claimed or 0),
        "file_ids": payload.file_ids or [],
        "status": "submitted", "feedback": "",
        "submitted_at": now().isoformat(), "reviewed_at": "",
    }
    await db.deliverables.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/deliverables/{engagement_id}")
async def list_deliverables(engagement_id: str, user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": engagement_id})
    if not eng or user["id"] not in (eng["employer_id"], eng["talent_id"]):
        raise HTTPException(404, "Not found")
    items = await db.deliverables.find({"engagement_id": engagement_id}, {"_id": 0}).sort("submitted_at", -1).to_list(500)
    return items


async def _act_deliverable(deliverable_id: str, user: dict, status: str, feedback: str) -> Dict[str, Any]:
    d = await db.deliverables.find_one({"id": deliverable_id})
    if not d:
        raise HTTPException(404, "Deliverable not found")
    if user["id"] != d.get("employer_id"):
        raise HTTPException(403, "Only the engaging employer can review deliverables")
    if d.get("status") != "submitted":
        raise HTTPException(400, "Deliverable already reviewed")
    upd = {"status": status, "feedback": feedback or "", "reviewed_at": now().isoformat()}
    await db.deliverables.update_one({"id": deliverable_id}, {"$set": upd})
    if status == "approved" and d.get("hours_claimed"):
        hours = float(d["hours_claimed"])
        await db.engagements.update_one({"id": d["engagement_id"]}, {"$inc": {"hours_used": hours}})
        # ---- AUTO-PAYOUT trigger ----
        talent = await db.users.find_one({"id": d["talent_id"]}) or {}
        rate = float((talent.get("profile") or {}).get("hourly_rate") or 0)
        # Rolling monthly volume for tier
        month_start = (now() - timedelta(days=30)).isoformat()
        prior = await db.deliverables.find({"talent_id": d["talent_id"], "status": "approved",
                                             "reviewed_at": {"$gte": month_start, "$lte": now().isoformat()}},
                                            {"_id": 0}).to_list(1000)
        month_hours = sum(float(x.get("hours_claimed") or 0) for x in prior)
        commission_pct = _pick_commission(month_hours)
        # Referral discount: 1% off commission for 6 months if talent was referred
        ref = await db.referrals.find_one({"referred_id": d["talent_id"], "status": "credited"})
        discount_active = False
        if ref and ref.get("credited_at"):
            if (now() - datetime.fromisoformat(ref["credited_at"].replace("Z", "+00:00"))).days <= 183:
                commission_pct = max(3, commission_pct - 1)
                discount_active = True
        # Multi-employer fee (once per month)
        month_employers = {x.get("employer_id") for x in prior if x.get("employer_id")}
        multi_fee_applied = 0.0
        if len(month_employers) > 1:
            already = await db.payouts.find_one({"talent_id": d["talent_id"], "multi_employer_fee": {"$gt": 0},
                                                  "created_at": {"$gte": month_start}})
            if not already:
                multi_fee_applied = MULTI_EMPLOYER_FEE_USD
        gross = round(rate * hours, 2)
        commission = round(gross * commission_pct / 100.0, 2)
        net = round(gross - commission - multi_fee_applied, 2)
        payout = {
            "id": new_id(), "run_id": None, "trigger": "deliverable_approved",
            "deliverable_id": deliverable_id, "engagement_id": d["engagement_id"],
            "talent_id": d["talent_id"], "talent_name": talent.get("name"),
            "hourly_rate": rate, "hours": hours,
            "employers_count": len(month_employers),
            "commission_pct": commission_pct, "referral_discount": discount_active,
            "gross": gross, "commission": commission,
            "multi_employer_fee": multi_fee_applied, "net": net, "currency": "usd",
            "status": "pending", "created_at": now().isoformat(),
        }
        await db.payouts.insert_one(payout)
    return await db.deliverables.find_one({"id": deliverable_id}, {"_id": 0})


@api.post("/deliverables/{deliverable_id}/approve")
async def approve_deliverable(deliverable_id: str, payload: DeliverableActionIn, user: dict = Depends(get_current_user)):
    return await _act_deliverable(deliverable_id, user, "approved", payload.feedback or "")


@api.post("/deliverables/{deliverable_id}/reject")
async def reject_deliverable(deliverable_id: str, payload: DeliverableActionIn, user: dict = Depends(get_current_user)):
    return await _act_deliverable(deliverable_id, user, "rejected", payload.feedback or "")


# ---------- Reviews ----------
@api.post("/reviews")
async def create_review(payload: ReviewIn, user: dict = Depends(get_current_user)):
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(400, "Rating must be between 1 and 5")
    eng = await db.engagements.find_one({"id": payload.engagement_id})
    if not eng or user["id"] not in (eng["employer_id"], eng["talent_id"]):
        raise HTTPException(404, "Engagement not found")
    reviewer_role = "employer" if user["id"] == eng["employer_id"] else "talent"
    reviewee_id = eng["talent_id"] if reviewer_role == "employer" else eng["employer_id"]
    existing = await db.reviews.find_one({"engagement_id": payload.engagement_id, "reviewer_id": user["id"]})
    if existing:
        raise HTTPException(400, "You have already reviewed this engagement")
    doc = {
        "id": new_id(), "engagement_id": payload.engagement_id,
        "reviewer_id": user["id"], "reviewer_name": user["name"], "reviewer_role": reviewer_role,
        "reviewee_id": reviewee_id, "rating": int(payload.rating), "text": payload.text or "",
        "status": "pending",     # pending | approved | rejected (moderated by admin)
        "created_at": now().isoformat(),
    }
    await db.reviews.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/reviews/user/{user_id}")
async def reviews_for_user(user_id: str):
    items = await db.reviews.find({"reviewee_id": user_id, "status": "approved"},
                                  {"_id": 0, "reviewer_id": 0}).sort("created_at", -1).to_list(200)
    return items


# ---------- Grievances ----------
GRIEVANCE_EMAIL = "grievance@talenthub.io"


@api.post("/grievances")
async def submit_grievance(payload: GrievanceIn, request: Request):
    doc = {
        "id": new_id(),
        "subject": payload.subject.strip()[:200],
        "engagement_id": payload.engagement_id or "",
        "against_party_id": payload.against_party_id or "",
        "description": payload.description.strip(),
        "contact_email": payload.contact_email.lower(),
        "incident_date": payload.incident_date or "",
        "status": "received",
        "created_at": now().isoformat(),
        "source_ip": request.client.host if request.client else "",
    }
    await db.grievances.insert_one(doc)
    logger.info(f"GRIEVANCE received (id={doc['id']}) — would email {GRIEVANCE_EMAIL} · from {doc['contact_email']}: {doc['subject']}")
    doc.pop("_id", None)
    return {"ok": True, "reference": doc["id"], "email_to": GRIEVANCE_EMAIL}


# ---------- Talent Payouts ----------
COMMISSION_TIERS = [(40, 8), (120, 6), (250, 5), (10**9, 4)]
MULTI_EMPLOYER_FEE_USD = 9.0


def _pick_commission(hours: float) -> int:
    for cap, pct in COMMISSION_TIERS:
        if hours <= cap:
            return pct
    return COMMISSION_TIERS[-1][1]


async def _compute_talent_earnings(talent_id: str, start_iso: str, end_iso: str) -> Dict[str, Any]:
    dels = await db.deliverables.find({
        "talent_id": talent_id, "status": "approved",
        "reviewed_at": {"$gte": start_iso, "$lte": end_iso},
    }, {"_id": 0}).to_list(1000)
    talent = await db.users.find_one({"id": talent_id}, {"_id": 0}) or {}
    rate = float((talent.get("profile") or {}).get("hourly_rate") or 0)
    hours = sum(float(d.get("hours_claimed") or 0) for d in dels)
    employers = {d.get("employer_id") for d in dels if d.get("employer_id")}
    commission_pct = _pick_commission(hours)
    gross = round(rate * hours, 2)
    commission = round(gross * commission_pct / 100.0, 2)
    multi_fee = MULTI_EMPLOYER_FEE_USD if len(employers) > 1 else 0.0
    net = round(gross - commission - multi_fee, 2)
    return {
        "talent_id": talent_id, "talent_name": talent.get("name"),
        "hourly_rate": rate, "hours": hours, "employers_count": len(employers),
        "commission_pct": commission_pct, "gross": gross,
        "commission": commission, "multi_employer_fee": multi_fee,
        "net": net, "currency": "usd", "deliverables": dels,
        "period_start": start_iso, "period_end": end_iso,
    }


@api.get("/payouts/mine")
async def my_payouts(user: dict = Depends(get_current_user)):
    if user["role"] != "talent":
        raise HTTPException(403, "Talent only")
    return await db.payouts.find({"talent_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


# ---------- Referrals ----------
def _ref_code(uid: str) -> str:
    return "TH-" + uid.replace("-", "")[:6].upper()


@api.get("/referrals/mine")
async def my_referral(user: dict = Depends(get_current_user)):
    code = _ref_code(user["id"])
    claims = await db.referrals.find({"referrer_id": user["id"]}, {"_id": 0}).to_list(500)
    earned = sum(float(c.get("bonus_hours") or 0) for c in claims if c.get("status") == "credited")
    return {"code": code, "share_url": f"/register?ref={code}",
            "reward": "2% of hours purchased in the first 90 days",
            "claims": claims, "total_bonus_hours": earned}


@api.post("/referrals/claim")
async def claim_referral(payload: ReferralClaimIn, user: dict = Depends(get_current_user)):
    code = payload.code.strip().upper()
    if not code.startswith("TH-"):
        raise HTTPException(400, "Invalid referral code")
    # Prevent self-referral
    if code == _ref_code(user["id"]):
        raise HTTPException(400, "Cannot use your own code")
    existing = await db.referrals.find_one({"referred_id": user["id"]})
    if existing:
        raise HTTPException(400, "You've already claimed a referral")
    # Find referrer
    all_users = await db.users.find({}, {"_id": 0, "id": 1}).to_list(5000)
    referrer_id = next((u["id"] for u in all_users if _ref_code(u["id"]) == code), None)
    if not referrer_id:
        raise HTTPException(404, "Referral code not found")
    doc = {
        "id": new_id(), "code": code,
        "referrer_id": referrer_id, "referred_id": user["id"],
        "referred_name": user.get("name", ""), "status": "pending",
        "bonus_hours": 0, "claimed_at": now().isoformat(),
        "expires_at": (now() + timedelta(days=90)).isoformat(),
    }
    await db.referrals.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "referral": doc}


# Hook this into checkout success (call from _credit_hours_if_paid)
async def _credit_referral_bonus(user_id: str, hours: int):
    ref = await db.referrals.find_one({"referred_id": user_id, "status": "pending"})
    if not ref or ref["expires_at"] < now().isoformat():
        return
    bonus = max(1, int(round(hours * 0.02)))
    await db.referrals.update_one({"id": ref["id"]}, {"$set": {"status": "credited",
                                                                "bonus_hours": bonus,
                                                                "credited_at": now().isoformat()}})
    await db.users.update_one({"id": ref["referrer_id"]}, {"$inc": {"hours_balance": bonus}})


# ---------- In-platform Messages ----------
@api.get("/messages/{engagement_id}")
async def list_messages(engagement_id: str, user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": engagement_id})
    if not eng or user["id"] not in (eng.get("employer_id"), eng.get("talent_id")):
        raise HTTPException(404, "Not found")
    items = await db.messages.find({"engagement_id": engagement_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    return items


@api.post("/messages")
async def post_message(payload: MessageIn, user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": payload.engagement_id})
    if not eng or user["id"] not in (eng.get("employer_id"), eng.get("talent_id")):
        raise HTTPException(404, "Engagement not found")
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "Message cannot be empty")
    # Basic PII / off-platform contact regex — flag but don't hard-block (moderation later)
    import re as _re
    flagged = bool(_re.search(r"(\+?\d[\d\s-]{7,}|\b[\w.+-]+@[\w-]+\.[\w.-]+\b|whatsapp|telegram|signal)", text.lower()))
    doc = {
        "id": new_id(), "engagement_id": payload.engagement_id,
        "sender_id": user["id"], "sender_name": user["name"],
        "text": text[:2000], "flagged": flagged, "created_at": now().isoformat(),
    }
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------- SEO skill landing pages ----------
# SEO_SKILLS, SEO_CITIES, EMPLOYER_INDUSTRIES are imported from `deps` at the
# top of this file. Do not redefine here.


@api.get("/seo/skills")
async def seo_skills():
    return {"skills": SEO_SKILLS}


@api.get("/seo/hire/{skill_slug}")
async def seo_hire(skill_slug: str):
    if skill_slug not in SEO_SKILLS:
        raise HTTPException(404, "Unknown skill")
    keyword = skill_slug.replace("-", " ")
    db_talent = await db.users.find(
        {"role": "talent", "profile.skills": {"$regex": keyword.split()[0], "$options": "i"}},
        {"_id": 0, "password_hash": 0, "email": 0, "integrations": 0},
    ).limit(12).to_list(12)
    curated = _curated_for(skill_slug, city=None, limit=12)
    seen, talent = set(), []
    for t in db_talent + curated:
        key = (t.get("name"), (t.get("profile") or {}).get("headline"))
        if key in seen:
            continue
        seen.add(key)
        talent.append(t)
    return {
        "slug": skill_slug, "keyword": keyword,
        "title": f"Hire {keyword.title()} by the hour — Job Atlas",
        "description": f"Hire vetted {keyword} on Job Atlas. Buy hours in bulk, sign contracts, integrate with Jira & Asana. From $29/mo.",
        "talent": talent,
    }


@api.get("/employer/overview")
async def employer_overview(user: dict = Depends(get_current_user)):
    if user["role"] != "employer":
        raise HTTPException(403, "Employers only")
    uid = user["id"]
    engs = await db.engagements.find({"employer_id": uid}, {"_id": 0}).to_list(500)
    talent_map: Dict[str, Dict[str, Any]] = {}
    hours_allocated_total = 0
    hours_used_total = 0.0
    for e in engs:
        tid = e["talent_id"]
        row = talent_map.setdefault(tid, {"talent_id": tid, "talent_name": e["talent_name"],
                                          "engagements": 0, "hours_allocated": 0,
                                          "hours_used": 0.0, "active": 0})
        row["engagements"] += 1
        row["hours_allocated"] += int(e.get("hours_allocated") or 0)
        row["hours_used"] += float(e.get("hours_used") or 0)
        if e.get("status") in ("contract_signed", "active"):
            row["active"] += 1
        hours_allocated_total += int(e.get("hours_allocated") or 0)
        hours_used_total += float(e.get("hours_used") or 0)

    pays = await db.payment_transactions.find({"user_id": uid, "payment_status": "paid"}, {"_id": 0}).to_list(500)
    total_spent = round(sum(float(p.get("amount") or 0) / 100.0 for p in pays), 2)
    total_hours_purchased = sum(int(p.get("hours") or 0) for p in pays)

    payouts = await db.payouts.find({}, {"_id": 0}).to_list(1000)
    triggered = [p for p in payouts if any(e["id"] == p.get("engagement_id") for e in engs)]
    total_paid_out = round(sum(float(p.get("gross") or 0) for p in triggered), 2)

    return {
        "resources": sorted(talent_map.values(), key=lambda r: -r["hours_allocated"]),
        "finances": {
            "hours_purchased": total_hours_purchased,
            "hours_allocated": hours_allocated_total,
            "hours_used": round(hours_used_total, 1),
            "hours_balance": int(user.get("hours_balance") or 0),
            "total_spent_usd": total_spent,
            "total_gross_paid_to_talent_usd": total_paid_out,
            "engagements": len(engs),
            "active_engagements": sum(1 for e in engs if e.get("status") in ("contract_signed", "active")),
        },
    }


SEO_CITIES = SEO_CITIES  # re-export for local references (imported from deps at top)


# ---------- Employer industry categories (used at registration + trust bar) ----------
# EMPLOYER_INDUSTRIES is imported from `deps` at the top of this file.


# ---------- Curated vetted-talent pool for SEO landing pages ----------
# Real-sounding, deterministic profiles that populate city×skill pages
# before organic sign-ups fill the DB. Each entry may match multiple cities
# via the "cities" list (typically home city + "remote").
_CITY_PRETTY = {"london": "London", "new-york": "New York", "san-francisco": "San Francisco",
                "berlin": "Berlin", "singapore": "Singapore", "dubai": "Dubai",
                "sydney": "Sydney", "toronto": "Toronto", "remote": "Remote"}

_CURATED_TALENT = [
    # React developers
    {"name": "Devon P.", "headline": "Senior React Engineer · Design-system builder",
     "skills": ["React", "TypeScript", "Next.js", "Tailwind"], "rate": 95, "years": 9,
     "cities": ["london", "remote"], "skill_slug": "react-developers", "avail": 25},
    {"name": "Alicia G.", "headline": "React + GraphQL specialist, ex-Stripe",
     "skills": ["React", "GraphQL", "Apollo", "TypeScript"], "rate": 130, "years": 11,
     "cities": ["new-york", "remote"], "skill_slug": "react-developers", "avail": 20},
    {"name": "Marc L.", "headline": "React Native + web, ships weekly",
     "skills": ["React", "React Native", "Redux", "Node"], "rate": 115, "years": 8,
     "cities": ["san-francisco", "remote"], "skill_slug": "react-developers", "avail": 30},
    {"name": "Ola K.", "headline": "React performance & migration lead",
     "skills": ["React", "Vite", "Vitest", "Playwright"], "rate": 88, "years": 7,
     "cities": ["berlin", "remote"], "skill_slug": "react-developers", "avail": 25},
    {"name": "Wei H.", "headline": "React engineer, Southeast Asia fintech",
     "skills": ["React", "Zustand", "MUI", "Node"], "rate": 78, "years": 6,
     "cities": ["singapore", "remote"], "skill_slug": "react-developers", "avail": 30},
    {"name": "Hassan A.", "headline": "React + Node full-stack, Gulf startups",
     "skills": ["React", "Next.js", "Node", "Postgres"], "rate": 82, "years": 8,
     "cities": ["dubai", "remote"], "skill_slug": "react-developers", "avail": 25},
    {"name": "Chloe W.", "headline": "React front-end lead, APAC time zone",
     "skills": ["React", "Recoil", "Vite", "Cypress"], "rate": 90, "years": 7,
     "cities": ["sydney", "remote"], "skill_slug": "react-developers", "avail": 30},
    {"name": "Nadia B.", "headline": "React + Next.js, e-commerce specialist",
     "skills": ["React", "Next.js", "Shopify Hydrogen"], "rate": 96, "years": 8,
     "cities": ["toronto", "remote"], "skill_slug": "react-developers", "avail": 25},

    # Python developers
    {"name": "Sofia M.", "headline": "FastAPI + Django · payments backends",
     "skills": ["Python", "FastAPI", "Django", "Postgres"], "rate": 105, "years": 10,
     "cities": ["london", "remote"], "skill_slug": "python-developers", "avail": 25},
    {"name": "Jamal K.", "headline": "Python data engineer, dbt + Airflow",
     "skills": ["Python", "Airflow", "dbt", "Snowflake"], "rate": 128, "years": 12,
     "cities": ["new-york", "remote"], "skill_slug": "python-developers", "avail": 20},
    {"name": "Priya S.", "headline": "Python ML + backend, ex-Twilio",
     "skills": ["Python", "PyTorch", "FastAPI"], "rate": 120, "years": 9,
     "cities": ["san-francisco", "remote"], "skill_slug": "python-developers", "avail": 25},
    {"name": "Lukas B.", "headline": "Python & Rust · high-throughput services",
     "skills": ["Python", "Rust", "Redis"], "rate": 100, "years": 8,
     "cities": ["berlin", "remote"], "skill_slug": "python-developers", "avail": 25},
    {"name": "Aarav R.", "headline": "Python + Postgres · SaaS backends",
     "skills": ["Python", "SQLAlchemy", "Postgres"], "rate": 82, "years": 7,
     "cities": ["singapore", "remote"], "skill_slug": "python-developers", "avail": 30},
    {"name": "Layla F.", "headline": "Python data pipelines, MENA",
     "skills": ["Python", "Pandas", "Kafka"], "rate": 85, "years": 8,
     "cities": ["dubai", "remote"], "skill_slug": "python-developers", "avail": 25},
    {"name": "Ben T.", "headline": "Python API architect, Sydney",
     "skills": ["Python", "FastAPI", "GraphQL"], "rate": 92, "years": 8,
     "cities": ["sydney", "remote"], "skill_slug": "python-developers", "avail": 30},
    {"name": "Mira A.", "headline": "Python backend + ML, Toronto",
     "skills": ["Python", "FastAPI", "scikit-learn"], "rate": 98, "years": 9,
     "cities": ["toronto", "remote"], "skill_slug": "python-developers", "avail": 25},

    # Node developers
    {"name": "Rhys O.", "headline": "Node + Nest microservices at scale",
     "skills": ["Node", "NestJS", "Postgres", "RabbitMQ"], "rate": 92, "years": 8,
     "cities": ["london", "remote"], "skill_slug": "node-developers", "avail": 25},
    {"name": "Emma Z.", "headline": "Node + serverless AWS specialist",
     "skills": ["Node", "AWS Lambda", "DynamoDB"], "rate": 118, "years": 9,
     "cities": ["new-york", "remote"], "skill_slug": "node-developers", "avail": 20},
    {"name": "Kenji I.", "headline": "Node.js + TypeScript, real-time apps",
     "skills": ["Node", "TypeScript", "Socket.IO"], "rate": 110, "years": 8,
     "cities": ["san-francisco", "remote"], "skill_slug": "node-developers", "avail": 25},
    {"name": "Ines V.", "headline": "Node + Fastify · European fintech",
     "skills": ["Node", "Fastify", "Postgres"], "rate": 88, "years": 7,
     "cities": ["berlin", "remote"], "skill_slug": "node-developers", "avail": 30},
    {"name": "Kai T.", "headline": "Node + GraphQL · APAC SaaS",
     "skills": ["Node", "Apollo Server", "MongoDB"], "rate": 80, "years": 7,
     "cities": ["singapore", "remote"], "skill_slug": "node-developers", "avail": 30},
    {"name": "Yara N.", "headline": "Node + Express, Middle East e-comm",
     "skills": ["Node", "Express", "Redis"], "rate": 78, "years": 6,
     "cities": ["dubai", "remote"], "skill_slug": "node-developers", "avail": 25},
    {"name": "Owen J.", "headline": "Node backend + DevOps, Sydney",
     "skills": ["Node", "Docker", "AWS"], "rate": 90, "years": 8,
     "cities": ["sydney", "remote"], "skill_slug": "node-developers", "avail": 25},
    {"name": "Sara D.", "headline": "Node + Prisma · fast APIs, Toronto",
     "skills": ["Node", "Prisma", "Postgres"], "rate": 95, "years": 8,
     "cities": ["toronto", "remote"], "skill_slug": "node-developers", "avail": 25},

    # UI designers
    {"name": "Isla F.", "headline": "UI designer · SaaS dashboards",
     "skills": ["Figma", "Design systems", "UI"], "rate": 80, "years": 7,
     "cities": ["london", "remote"], "skill_slug": "ui-designers", "avail": 30},
    {"name": "Cameron D.", "headline": "UI + brand systems, NYC",
     "skills": ["Figma", "UI", "Framer"], "rate": 105, "years": 9,
     "cities": ["new-york", "remote"], "skill_slug": "ui-designers", "avail": 25},
    {"name": "Tia W.", "headline": "UI designer for consumer apps",
     "skills": ["Figma", "UI", "iOS", "Android"], "rate": 90, "years": 6,
     "cities": ["san-francisco", "remote"], "skill_slug": "ui-designers", "avail": 30},
    {"name": "Jonas P.", "headline": "UI designer · fintech & health",
     "skills": ["Figma", "UI", "Design tokens"], "rate": 72, "years": 6,
     "cities": ["berlin", "remote"], "skill_slug": "ui-designers", "avail": 30},
    {"name": "Mei L.", "headline": "UI designer · APAC e-commerce",
     "skills": ["Figma", "UI", "Motion"], "rate": 68, "years": 6,
     "cities": ["singapore", "remote"], "skill_slug": "ui-designers", "avail": 30},
    {"name": "Fatima H.", "headline": "UI designer · Arabic + English",
     "skills": ["Figma", "UI", "RTL layouts"], "rate": 70, "years": 6,
     "cities": ["dubai", "remote"], "skill_slug": "ui-designers", "avail": 25},
    {"name": "Riley A.", "headline": "UI designer, product-led growth",
     "skills": ["Figma", "UI", "Illustration"], "rate": 78, "years": 6,
     "cities": ["sydney", "remote"], "skill_slug": "ui-designers", "avail": 30},
    {"name": "Anika R.", "headline": "UI designer · dashboards & CRM",
     "skills": ["Figma", "UI", "Sketch"], "rate": 82, "years": 7,
     "cities": ["toronto", "remote"], "skill_slug": "ui-designers", "avail": 30},

    # UX designers
    {"name": "Harper C.", "headline": "UX researcher + designer, London",
     "skills": ["UX research", "Figma", "Prototyping"], "rate": 92, "years": 8,
     "cities": ["london", "remote"], "skill_slug": "ux-designers", "avail": 25},
    {"name": "Diego M.", "headline": "UX designer, enterprise B2B",
     "skills": ["UX", "Figma", "Miro"], "rate": 115, "years": 9,
     "cities": ["new-york", "remote"], "skill_slug": "ux-designers", "avail": 20},
    {"name": "Sana V.", "headline": "UX lead · onboarding & retention",
     "skills": ["UX", "Figma", "Journey maps"], "rate": 108, "years": 8,
     "cities": ["san-francisco", "remote"], "skill_slug": "ux-designers", "avail": 25},
    {"name": "Klara N.", "headline": "UX + accessibility, Berlin",
     "skills": ["UX", "WCAG", "Figma"], "rate": 82, "years": 7,
     "cities": ["berlin", "remote"], "skill_slug": "ux-designers", "avail": 30},
    {"name": "Amir Q.", "headline": "UX designer for fintech, APAC",
     "skills": ["UX", "Figma", "Usability testing"], "rate": 76, "years": 6,
     "cities": ["singapore", "remote"], "skill_slug": "ux-designers", "avail": 30},
    {"name": "Nour E.", "headline": "UX designer, MENA multilingual",
     "skills": ["UX", "Figma", "Prototyping"], "rate": 78, "years": 7,
     "cities": ["dubai", "remote"], "skill_slug": "ux-designers", "avail": 25},
    {"name": "Grace T.", "headline": "UX designer, healthcare + edtech",
     "skills": ["UX", "Figma", "User interviews"], "rate": 85, "years": 7,
     "cities": ["sydney", "remote"], "skill_slug": "ux-designers", "avail": 30},
    {"name": "Ravi K.", "headline": "UX lead · analytics + design",
     "skills": ["UX", "Figma", "Amplitude"], "rate": 90, "years": 8,
     "cities": ["toronto", "remote"], "skill_slug": "ux-designers", "avail": 25},

    # Data scientists
    {"name": "Elena R.", "headline": "Data scientist, causal inference",
     "skills": ["Python", "R", "SQL", "Bayesian stats"], "rate": 130, "years": 10,
     "cities": ["london", "remote"], "skill_slug": "data-scientists", "avail": 20},
    {"name": "Marcus O.", "headline": "Data scientist · ML + LLMs, NYC",
     "skills": ["Python", "PyTorch", "LLMs", "MLflow"], "rate": 155, "years": 11,
     "cities": ["new-york", "toronto", "remote"], "skill_slug": "data-scientists", "avail": 20},
    {"name": "Ivy L.", "headline": "Data scientist · forecasting SaaS",
     "skills": ["Python", "Prophet", "XGBoost"], "rate": 140, "years": 9,
     "cities": ["san-francisco", "remote"], "skill_slug": "data-scientists", "avail": 20},
    {"name": "Tobias W.", "headline": "Data scientist · NLP, Berlin",
     "skills": ["Python", "spaCy", "Transformers"], "rate": 110, "years": 8,
     "cities": ["berlin", "remote"], "skill_slug": "data-scientists", "avail": 25},
    {"name": "Farah S.", "headline": "Data science + BI, APAC banking",
     "skills": ["Python", "SQL", "PowerBI"], "rate": 102, "years": 8,
     "cities": ["singapore", "remote"], "skill_slug": "data-scientists", "avail": 25},
    {"name": "Adam Z.", "headline": "Data scientist · retail analytics",
     "skills": ["Python", "SQL", "Tableau"], "rate": 96, "years": 7,
     "cities": ["dubai", "remote"], "skill_slug": "data-scientists", "avail": 25},
    {"name": "Lachlan B.", "headline": "Data scientist · geospatial + ML",
     "skills": ["Python", "PostGIS", "sklearn"], "rate": 108, "years": 8,
     "cities": ["sydney", "remote"], "skill_slug": "data-scientists", "avail": 25},

    # DevOps engineers
    {"name": "Ayo K.", "headline": "DevOps · AWS + Terraform, ex-Monzo",
     "skills": ["AWS", "Terraform", "Kubernetes"], "rate": 125, "years": 10,
     "cities": ["london", "remote"], "skill_slug": "devops-engineers", "avail": 20},
    {"name": "Nikhil V.", "headline": "Platform engineer · GCP + Argo",
     "skills": ["GCP", "Kubernetes", "ArgoCD"], "rate": 148, "years": 10,
     "cities": ["new-york", "remote"], "skill_slug": "devops-engineers", "avail": 20},
    {"name": "Casey H.", "headline": "SRE · observability + cost control",
     "skills": ["AWS", "Datadog", "Prometheus"], "rate": 135, "years": 9,
     "cities": ["san-francisco", "remote"], "skill_slug": "devops-engineers", "avail": 20},
    {"name": "Stefan A.", "headline": "DevOps · Docker, Kubernetes, EU",
     "skills": ["Kubernetes", "Docker", "GitLab CI"], "rate": 110, "years": 9,
     "cities": ["berlin", "remote"], "skill_slug": "devops-engineers", "avail": 25},
    {"name": "Xin Y.", "headline": "DevOps + platform, APAC startups",
     "skills": ["AWS", "Terraform", "Ansible"], "rate": 98, "years": 8,
     "cities": ["singapore", "remote"], "skill_slug": "devops-engineers", "avail": 25},
    {"name": "Omar S.", "headline": "DevOps + security, MENA cloud",
     "skills": ["AWS", "Kubernetes", "Vault"], "rate": 100, "years": 8,
     "cities": ["dubai", "remote"], "skill_slug": "devops-engineers", "avail": 25},
    {"name": "Zara C.", "headline": "SRE · reliability + CI/CD, Sydney",
     "skills": ["AWS", "CircleCI", "Kubernetes"], "rate": 112, "years": 9,
     "cities": ["sydney", "remote"], "skill_slug": "devops-engineers", "avail": 25},
    {"name": "Ethan G.", "headline": "DevOps · IaC + FinOps, Toronto",
     "skills": ["Terraform", "AWS", "CloudFormation"], "rate": 118, "years": 9,
     "cities": ["toronto", "remote"], "skill_slug": "devops-engineers", "avail": 25},

    # Product managers
    {"name": "Rosie A.", "headline": "Senior product manager · B2B SaaS",
     "skills": ["Roadmapping", "Discovery", "Metrics"], "rate": 128, "years": 10,
     "cities": ["london", "remote"], "skill_slug": "product-managers", "avail": 20},
    {"name": "Trevor N.", "headline": "PM · fintech + payments, NYC",
     "skills": ["Product", "Payments", "Compliance"], "rate": 160, "years": 12,
     "cities": ["new-york", "remote"], "skill_slug": "product-managers", "avail": 20},
    {"name": "Nora J.", "headline": "PM · growth + PLG, SF",
     "skills": ["Product", "Growth", "Experimentation"], "rate": 150, "years": 10,
     "cities": ["san-francisco", "remote"], "skill_slug": "product-managers", "avail": 20},
    {"name": "Julian B.", "headline": "PM · developer tools, Berlin",
     "skills": ["Product", "DevTools", "APIs"], "rate": 118, "years": 9,
     "cities": ["berlin", "remote"], "skill_slug": "product-managers", "avail": 25},
    {"name": "Aisha M.", "headline": "PM · e-commerce, APAC",
     "skills": ["Product", "E-commerce", "A/B"], "rate": 105, "years": 8,
     "cities": ["singapore", "remote"], "skill_slug": "product-managers", "avail": 25},

    # Figma designers
    {"name": "Mila V.", "headline": "Figma design-system specialist",
     "skills": ["Figma", "Design systems", "Tokens"], "rate": 78, "years": 7,
     "cities": ["london", "remote"], "skill_slug": "figma-designers", "avail": 30},
    {"name": "Ryan H.", "headline": "Figma + Framer motion, NYC",
     "skills": ["Figma", "Framer", "Motion"], "rate": 92, "years": 7,
     "cities": ["new-york", "remote"], "skill_slug": "figma-designers", "avail": 25},
    {"name": "Selin K.", "headline": "Figma templates · marketing sites",
     "skills": ["Figma", "Web design", "Webflow"], "rate": 72, "years": 6,
     "cities": ["berlin", "remote"], "skill_slug": "figma-designers", "avail": 30},

    # Mobile developers
    {"name": "Aditya P.", "headline": "iOS Swift + SwiftUI, ex-Revolut",
     "skills": ["Swift", "SwiftUI", "iOS"], "rate": 118, "years": 9,
     "cities": ["london", "remote"], "skill_slug": "mobile-developers", "avail": 25},
    {"name": "Bianca L.", "headline": "React Native + Flutter, NYC",
     "skills": ["React Native", "Flutter", "TypeScript"], "rate": 130, "years": 10,
     "cities": ["new-york", "remote"], "skill_slug": "mobile-developers", "avail": 20},
    {"name": "Rafi M.", "headline": "Android Kotlin + Compose",
     "skills": ["Kotlin", "Compose", "Android"], "rate": 95, "years": 8,
     "cities": ["singapore", "remote"], "skill_slug": "mobile-developers", "avail": 25},

    # WordPress developers
    {"name": "Beatrice O.", "headline": "WordPress + WooCommerce, London",
     "skills": ["WordPress", "WooCommerce", "PHP"], "rate": 62, "years": 8,
     "cities": ["london", "remote"], "skill_slug": "wordpress-developers", "avail": 30},
    {"name": "Dylan W.", "headline": "Headless WordPress + Next.js",
     "skills": ["WordPress", "Next.js", "GraphQL"], "rate": 78, "years": 7,
     "cities": ["new-york", "remote"], "skill_slug": "wordpress-developers", "avail": 30},

    # Salesforce consultants
    {"name": "Meera S.", "headline": "Salesforce consultant · Sales Cloud",
     "skills": ["Salesforce", "Apex", "Sales Cloud"], "rate": 118, "years": 9,
     "cities": ["london", "remote"], "skill_slug": "salesforce-consultants", "avail": 25},
    {"name": "Kevin R.", "headline": "Salesforce architect · Service Cloud",
     "skills": ["Salesforce", "Service Cloud", "Flow"], "rate": 140, "years": 11,
     "cities": ["new-york", "remote"], "skill_slug": "salesforce-consultants", "avail": 20},
    {"name": "Lior D.", "headline": "Salesforce dev · Lightning + Apex",
     "skills": ["Salesforce", "Lightning", "Apex"], "rate": 105, "years": 8,
     "cities": ["dubai", "remote"], "skill_slug": "salesforce-consultants", "avail": 25},
]


def _curated_to_public(entry: dict, force_city: Optional[str] = None) -> dict:
    """Format a curated talent entry to match the public shape returned by /api/seo endpoints."""
    display_city = force_city or (entry["cities"][0] if entry["cities"] else "remote")
    return {
        "id": f"curated-{entry['skill_slug']}-{entry['name'].replace(' ', '-').replace('.', '')}",
        "name": entry["name"],
        "role": "talent",
        "curated": True,
        "profile": {
            "headline": entry["headline"],
            "skills": entry["skills"],
            "hourly_rate": entry["rate"],
            "years_experience": entry["years"],
            "location": _CITY_PRETTY.get(display_city, display_city.title()),
            "available_hours_per_week": entry["avail"],
            "verified": True,
        },
    }


def _curated_for(skill_slug: str, city: Optional[str] = None, limit: int = 24) -> list:
    """Return curated talent for a skill (and optional city).
    Match rule: profile is included if it targets the requested skill AND
    (a) its cities list contains the requested city (local),
    OR (b) its cities list contains "remote" (remote talent serving that market).
    Local matches are ranked first."""
    local, remote = [], []
    for e in _CURATED_TALENT:
        if e["skill_slug"] != skill_slug:
            continue
        cs = e["cities"]
        if not city:
            local.append(e)
            continue
        if city in cs:
            local.append(e)
        elif "remote" in cs:
            remote.append(e)
    ordered = local + remote
    out = []
    for e in ordered[:limit]:
        # For local matches use the city; for remote-only, keep the profile's home city
        display_city = city if (city and city in e["cities"]) else e["cities"][0]
        out.append(_curated_to_public(e, force_city=display_city))
    return out


@api.get("/seo/city-skills")
async def seo_city_skills():
    combos = []
    for c in SEO_CITIES:
        for s in SEO_SKILLS[:6]:
            combos.append({"slug": f"{s}-{c}", "skill": s, "city": c})
    return {"combos": combos}


@api.get("/seo/hire-city/{slug}")
async def seo_hire_city(slug: str):
    # Slug format: {skill-slug}-{city}. Skill slugs contain hyphens, so we
    # match the LONGEST valid skill prefix followed by a valid city suffix.
    skill_slug, city = None, None
    for s in sorted(SEO_SKILLS, key=len, reverse=True):
        if slug.startswith(s + "-"):
            tail = slug[len(s) + 1:]
            if tail in SEO_CITIES:
                skill_slug, city = s, tail
                break
    if not skill_slug:
        raise HTTPException(404, "Unknown skill/city combo")
    keyword = skill_slug.replace("-", " ")
    city_pretty = _CITY_PRETTY.get(city, city.title())
    db_talent = await db.users.find(
        {"role": "talent",
         "profile.skills": {"$regex": keyword.split()[0], "$options": "i"},
         "profile.location": {"$regex": city_pretty, "$options": "i"}},
        {"_id": 0, "password_hash": 0, "email": 0, "integrations": 0},
    ).limit(12).to_list(12)
    curated = _curated_for(skill_slug, city=city, limit=12)
    # De-dupe by (name, headline) so any manual dupes don't repeat
    seen = set()
    talent = []
    for t in db_talent + curated:
        key = (t.get("name"), (t.get("profile") or {}).get("headline"))
        if key in seen:
            continue
        seen.add(key)
        talent.append(t)
    return {
        "slug": slug, "skill": skill_slug, "city": city, "keyword": keyword, "city_pretty": city_pretty,
        "title": f"Hire {keyword.title()} in {city_pretty} — Job Atlas",
        "description": f"Hire vetted {keyword} available in {city_pretty} on Job Atlas. Purchase hours, sign contracts, track work in Jira and Asana.",
        "talent": talent,
    }


# ---------- Sitemap autogeneration ----------
STATIC_SITEMAP_PATHS = [
    ("/",          "1.0", "weekly"),
    ("/browse",    "0.9", "daily"),
    ("/pricing",   "0.9", "monthly"),
    ("/register",  "0.8", "monthly"),
    ("/login",     "0.6", "yearly"),
    ("/legal",     "0.5", "yearly"),
    ("/grievance", "0.4", "yearly"),
]


def _build_sitemap_xml(origin: str) -> str:
    origin = origin.rstrip("/")
    now_iso = now().date().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, prio, freq in STATIC_SITEMAP_PATHS:
        lines.append(f"  <url><loc>{origin}{path}</loc>"
                     f"<lastmod>{now_iso}</lastmod>"
                     f"<changefreq>{freq}</changefreq>"
                     f"<priority>{prio}</priority></url>")
    # Skill-only landing pages (12)
    for s in SEO_SKILLS:
        lines.append(f"  <url><loc>{origin}/hire/{s}</loc>"
                     f"<lastmod>{now_iso}</lastmod>"
                     f"<changefreq>weekly</changefreq>"
                     f"<priority>0.8</priority></url>")
    # City × skill landing pages (54 = 9 cities × 6 top skills)
    for c in SEO_CITIES:
        for s in SEO_SKILLS[:6]:
            lines.append(f"  <url><loc>{origin}/hire/{s}-{c}</loc>"
                         f"<lastmod>{now_iso}</lastmod>"
                         f"<changefreq>weekly</changefreq>"
                         f"<priority>0.7</priority></url>")
    lines.append("</urlset>")
    return "\n".join(lines)


@api.get("/sitemap.xml")
async def sitemap_xml(request: Request):
    """Dynamically generated sitemap covering all static + SEO landing routes."""
    from fastapi.responses import Response as _XmlResponse
    # Prefer the explicit env var, then the forwarded host (ingress), then the raw host header
    origin = os.environ.get("PUBLIC_SITE_URL")
    if not origin:
        fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        fwd_proto = request.headers.get("x-forwarded-proto", "https")
        origin = f"{fwd_proto}://{fwd_host}" if fwd_host else str(request.base_url).rstrip("/")
    return _XmlResponse(content=_build_sitemap_xml(origin), media_type="application/xml")


# ---------- Marketplace stats (live buyer counter) ----------
@api.get("/marketplace/industries")
async def marketplace_industries():
    """Returns the canonical list of employer industries + a live count per industry
    (0 for industries no one has claimed yet). Used by the Landing trust bar and
    the employer registration industry picker."""
    counts = {i: 0 for i in EMPLOYER_INDUSTRIES}
    pipeline = [
        {"$match": {"role": "employer", "profile.company_industry": {"$in": EMPLOYER_INDUSTRIES}}},
        {"$group": {"_id": "$profile.company_industry", "n": {"$sum": 1}}},
    ]
    async for row in db.users.aggregate(pipeline):
        counts[row["_id"]] = int(row["n"])
    return {
        "industries": [{"label": i, "count": counts[i]} for i in EMPLOYER_INDUSTRIES],
        "total_labelled_employers": sum(counts.values()),
    }


@api.get("/marketplace/stats")
async def marketplace_stats():
    """Live counts for the Landing trust bar. Aggregates real employer sign-ups
    with a small baseline so an empty DB still reads credibly on day 1."""
    active_buyers = await db.users.count_documents({"role": "employer"})
    engagements = await db.engagements.count_documents({})
    signed_engagements = await db.engagements.count_documents(
        {"status": {"$in": ["contract_signed", "active", "completed"]}}
    )
    industries_used = len(await db.users.distinct(
        "profile.company_industry",
        {"role": "employer", "profile.company_industry": {"$in": EMPLOYER_INDUSTRIES}},
    ))
    # Baseline padding for a credible day-1 number, capped so it becomes irrelevant once the DB grows
    baseline = 42
    active_buyers_display = max(active_buyers, baseline) if active_buyers < baseline else active_buyers
    return {
        "active_buyers": active_buyers,
        "active_buyers_display": active_buyers_display,
        "industries": len(EMPLOYER_INDUSTRIES),
        "industries_active": industries_used,
        "cities_covered": len(SEO_CITIES),
        "engagements_total": engagements,
        "engagements_signed": signed_engagements,
    }


# ---------- Rate Nudge (drift monitor) ----------
# RATE_DRIFT_THRESHOLD_PCT imported from deps at top of file.


class RateNudgeScanIn(BaseModel):
    dry_run: bool = False


async def _scan_and_record_rate_nudges(request: Optional[Request] = None) -> Dict[str, Any]:
    """Iterate all talents, refresh their AI rate suggestion, and log a nudge
    doc whenever the current rate drifts more than ±15% from the AI mid.
    Also fires an outbound email via Resend when configured."""
    from mailer import send_email, rate_nudge_html
    # Build the dashboard link for the CTA in the email
    if request is not None:
        fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        fwd_proto = request.headers.get("x-forwarded-proto", "https")
        origin = os.environ.get("PUBLIC_SITE_URL") or (f"{fwd_proto}://{fwd_host}" if fwd_host else "")
    else:
        origin = os.environ.get("PUBLIC_SITE_URL") or ""
    dashboard_url = f"{origin.rstrip('/')}/talent" if origin else "/talent"

    talents = await db.users.find({"role": "talent"}, {"_id": 0}).to_list(2000)
    checked = 0
    nudged = 0
    emailed = 0
    email_failures = 0
    for t in talents:
        p = t.get("profile") or {}
        current = float(p.get("hourly_rate") or 0)
        skills = p.get("skills") or []
        years = int(p.get("years_experience") or 0)
        if not skills or current <= 0:
            continue
        checked += 1
        try:
            sug = await suggest_hourly_rate(skills, years, p.get("location") or "Global")
        except Exception:
            continue
        mid = float(sug.get("mid") or 0)
        if mid <= 0:
            continue
        drift_pct = ((mid - current) / current) * 100.0
        if abs(drift_pct) < RATE_DRIFT_THRESHOLD_PCT:
            continue
        direction = "raise" if drift_pct > 0 else "lower"
        nudge_doc = {
            "id": new_id(),
            "talent_id": t["id"],
            "talent_name": t.get("name"),
            "talent_email": t.get("email"),
            "current_rate": current,
            "suggested_low": int(sug.get("low") or 0),
            "suggested_mid": int(mid),
            "suggested_high": int(sug.get("high") or 0),
            "drift_pct": round(drift_pct, 1),
            "direction": direction,
            "rationale": (sug.get("rationale") or "")[:280],
            "delivered_via": "in_app",
            "email_status": "pending",
            "email_id": None,
            "created_at": now().isoformat(),
        }

        # Send the outbound email (best-effort, non-blocking-per-talent)
        html = rate_nudge_html(
            talent_name=t.get("name") or "",
            current_rate=current, mid=int(mid),
            low=int(sug.get("low") or 0), high=int(sug.get("high") or 0),
            drift_pct=drift_pct, direction=direction,
            dashboard_url=dashboard_url,
            rationale=(sug.get("rationale") or "")[:200],
        )
        subject = (f"Your rate looks {abs(round(drift_pct))}% "
                   f"{'below' if direction == 'raise' else 'above'} market — Job Atlas")
        mail_result = await send_email(to=t.get("email"), subject=subject, html=html)
        if mail_result.get("sent"):
            emailed += 1
            nudge_doc["delivered_via"] = "email+in_app"
            nudge_doc["email_status"] = "sent"
            nudge_doc["email_id"] = mail_result.get("id")
        else:
            email_failures += 1
            nudge_doc["email_status"] = mail_result.get("reason", "failed")

        await db.rate_nudges.update_one(
            {"talent_id": t["id"]},
            {"$set": nudge_doc}, upsert=True,
        )
        nudged += 1
    return {"checked": checked, "nudged": nudged, "emailed": emailed,
            "email_failures": email_failures,
            "threshold_pct": RATE_DRIFT_THRESHOLD_PCT,
            "scanned_at": now().isoformat()}


@api.get("/talent/me/rate-nudge")
async def get_my_rate_nudge(user: dict = Depends(get_current_user)):
    """Returns the most recent nudge for the logged-in talent, if any."""
    if user.get("role") != "talent":
        return {"nudge": None}
    doc = await db.rate_nudges.find_one({"talent_id": user["id"]}, {"_id": 0})
    return {"nudge": doc}


@api.post("/talent/me/rate-nudge/dismiss")
async def dismiss_rate_nudge(user: dict = Depends(get_current_user)):
    if user.get("role") != "talent":
        raise HTTPException(403, "Talent only")
    await db.rate_nudges.delete_one({"talent_id": user["id"]})
    return {"ok": True}


# ---------- Shortlist (employer saves talent profiles before purchasing hours) ----------
class ShortlistIn(BaseModel):
    talent_id: str
    talent_name: str
    headline: Optional[str] = ""
    location: Optional[str] = ""
    hourly_rate: Optional[float] = 0.0
    skills: List[str] = []
    context: Optional[str] = ""     # e.g. the city×skill slug they came from
    is_curated: bool = False


@api.post("/shortlist")
async def add_to_shortlist(payload: ShortlistIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "employer":
        raise HTTPException(403, "Only employers can shortlist")
    doc = {
        "id": new_id(),
        "employer_id": user["id"],
        "talent_id": payload.talent_id,
        "talent_name": payload.talent_name,
        "headline": payload.headline or "",
        "location": payload.location or "",
        "hourly_rate": float(payload.hourly_rate or 0),
        "skills": payload.skills or [],
        "context": payload.context or "",
        "is_curated": bool(payload.is_curated),
        "created_at": now().isoformat(),
    }
    # One record per (employer, talent) — upsert
    await db.shortlists.update_one(
        {"employer_id": user["id"], "talent_id": payload.talent_id},
        {"$set": doc}, upsert=True,
    )
    total = await db.shortlists.count_documents({"employer_id": user["id"]})
    return {"ok": True, "count": total}


@api.get("/shortlist")
async def list_shortlist(user: dict = Depends(get_current_user)):
    if user.get("role") != "employer":
        raise HTTPException(403, "Only employers can view a shortlist")
    items = await db.shortlists.find({"employer_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": items, "count": len(items)}


@api.delete("/shortlist/{talent_id}")
async def remove_from_shortlist(talent_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "employer":
        raise HTTPException(403, "Only employers can modify a shortlist")
    await db.shortlists.delete_one({"employer_id": user["id"], "talent_id": talent_id})
    total = await db.shortlists.count_documents({"employer_id": user["id"]})
    return {"ok": True, "count": total}


DEFAULT_BROADCAST_TEMPLATE = (
    "Hi — I'm ready to bring you on for a paid engagement through Job Atlas. "
    "I've reserved hours in my platform balance and would love to send you a signed contract "
    "as soon as you confirm your availability. Reply here to talk scope, timelines and start date."
)


class ShortlistBroadcastIn(BaseModel):
    message: Optional[str] = ""
    subject: Optional[str] = ""


@api.post("/shortlist/broadcast")
async def broadcast_to_shortlist(payload: ShortlistBroadcastIn, request: Request,
                                  user: dict = Depends(get_current_user)):
    """Send a single 'I'm ready to hire' note to every talent on the employer's shortlist.
    Records a `broadcasts` doc per (employer, talent) pair (upsert-latest) and — when
    RESEND_API_KEY is set — also emails the talent. Safe no-op email in dev."""
    if user.get("role") != "employer":
        raise HTTPException(403, "Only employers can broadcast")
    items = await db.shortlists.find({"employer_id": user["id"]}, {"_id": 0}).to_list(500)
    if not items:
        raise HTTPException(400, "Your shortlist is empty — add talents before broadcasting")

    from mailer import send_email
    message = (payload.message or DEFAULT_BROADCAST_TEMPLATE).strip()
    subject = (payload.subject or f"{user.get('name') or 'A hiring employer'} is ready to hire you on Job Atlas").strip()

    # Origin for email CTA
    fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    fwd_proto = request.headers.get("x-forwarded-proto", "https")
    origin = os.environ.get("PUBLIC_SITE_URL") or (f"{fwd_proto}://{fwd_host}" if fwd_host else "")
    login_url = f"{origin.rstrip('/')}/login" if origin else "/login"

    delivered = 0
    emailed = 0
    email_failures = 0
    broadcast_id = new_id()

    for it in items:
        # Skip curated (synthetic) talents — no real inbox to deliver to
        if it.get("is_curated"):
            continue
        talent = await db.users.find_one({"id": it["talent_id"]}, {"_id": 0, "password_hash": 0})
        if not talent:
            continue

        doc = {
            "id": new_id(),
            "broadcast_id": broadcast_id,
            "employer_id": user["id"],
            "employer_name": user.get("name") or "An employer",
            "talent_id": talent["id"],
            "talent_email": talent.get("email"),
            "subject": subject,
            "message": message,
            "read": False,
            "email_status": "pending",
            "created_at": now().isoformat(),
        }

        if talent.get("email"):
            html = _broadcast_email_html(
                employer_name=doc["employer_name"], talent_name=talent.get("name") or "there",
                message=message, login_url=login_url,
            )
            mail_result = await send_email(to=talent["email"], subject=subject, html=html)
            if mail_result.get("sent"):
                emailed += 1
                doc["email_status"] = "sent"
                doc["email_id"] = mail_result.get("id")
            else:
                email_failures += 1
                doc["email_status"] = mail_result.get("reason", "failed")

        await db.broadcasts.insert_one(doc)
        # Push over SSE so the talent sees the note without reloading
        await _push_broadcast_to_talent(talent["id"], {
            "type": "broadcast",
            "id": doc["id"],
            "employer_name": doc["employer_name"],
            "subject": subject,
            "message": message,
            "created_at": doc["created_at"],
        })
        delivered += 1

    # Also log a summary of this broadcast run for the employer's history view
    await db.broadcast_runs.insert_one({
        "id": broadcast_id,
        "employer_id": user["id"],
        "employer_name": user.get("name") or "An employer",
        "subject": subject,
        "message": message,
        "delivered": delivered,
        "emailed": emailed,
        "email_failures": email_failures,
        "skipped_curated": sum(1 for it in items if it.get("is_curated")),
        "total_shortlist": len(items),
        "created_at": now().isoformat(),
    })

    return {
        "ok": True,
        "broadcast_id": broadcast_id,
        "delivered": delivered,
        "emailed": emailed,
        "email_failures": email_failures,
        "skipped_curated": sum(1 for it in items if it.get("is_curated")),
        "total_shortlist": len(items),
    }


def _broadcast_email_html(*, employer_name: str, talent_name: str,
                          message: str, login_url: str) -> str:
    first = (talent_name or "there").split(" ")[0]
    safe_msg = (message or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/></head>
<body style="margin:0;background:#FAF9F6;font-family:Georgia,serif;color:#0B1B2B;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FAF9F6;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border:1px solid #E5E7EB;">
        <tr><td style="padding:32px 32px 8px 32px;">
          <p style="margin:0 0 4px 0;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;color:#C79A3B;text-transform:uppercase;">New hire request</p>
          <h1 style="margin:0;font-size:24px;line-height:1.2;">Hey {first} — {employer_name} is ready to hire you.</h1>
        </td></tr>
        <tr><td style="padding:16px 32px 0 32px;font-size:15px;line-height:1.55;color:#333;">
          <blockquote style="margin:0 0 20px 0;padding:16px;background:#FDF6E3;border-left:3px solid #C79A3B;font-style:italic;">{safe_msg}</blockquote>
          <p style="margin:0 0 24px 0;font-size:14px;color:#555;">
            Sign in to Job Atlas to reply, review the scope, and countersign the engagement contract when you&apos;re ready.
          </p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
            <tr><td style="background:#0B1B2B;border-radius:2px;">
              <a href="{login_url}" style="display:inline-block;padding:14px 28px;color:#FFFFFF;text-decoration:none;font-weight:700;font-size:14px;font-family:Arial,sans-serif;">
                Open Job Atlas →
              </a>
            </td></tr>
          </table>
          <p style="margin:0 0 12px 0;font-size:12px;color:#999;font-family:'Courier New',monospace;letter-spacing:1px;text-transform:uppercase;">
            Sent by Job Atlas · operated by Denkoit Softech Pvt. Ltd.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


# ---------- Project Delivery workflow (PMI-based, longer engagements) ----------
PROJECT_TEMPLATES = [
    {"id": "fintech-kyc-aml", "industry": "Financial Services & Fintech",
     "title": "KYC / AML Platform Build", "duration_months": 6,
     "summary": "Compliance-grade identity verification & transaction monitoring for a regulated fintech.",
     "team": [
        {"role": "Program Manager", "count": 1, "rate_range": [140, 180]},
        {"role": "Solutions Architect", "count": 1, "rate_range": [130, 170]},
        {"role": "Senior Backend Engineer", "count": 2, "rate_range": [100, 145]},
        {"role": "Compliance Specialist", "count": 1, "rate_range": [95, 140]},
        {"role": "QA Automation Lead", "count": 1, "rate_range": [80, 120]},
     ]},
    {"id": "fintech-payments-integration", "industry": "Financial Services & Fintech",
     "title": "Payment Gateway Integration", "duration_months": 3,
     "summary": "Stripe / Adyen / regional PSP integration with reconciliation and dispute tooling.",
     "team": [
        {"role": "Tech Lead", "count": 1, "rate_range": [120, 160]},
        {"role": "Senior Backend Engineer", "count": 2, "rate_range": [100, 140]},
        {"role": "Frontend Engineer", "count": 1, "rate_range": [80, 120]},
     ]},
    {"id": "healthcare-fhir-ehr", "industry": "Healthcare & Life Sciences",
     "title": "FHIR / HL7 EHR Integration", "duration_months": 9,
     "summary": "Interoperability layer for a hospital network — FHIR-first, HIPAA-compliant.",
     "team": [
        {"role": "Program Manager", "count": 1, "rate_range": [140, 180]},
        {"role": "HL7/FHIR Architect", "count": 1, "rate_range": [140, 190]},
        {"role": "Senior Integration Engineer", "count": 2, "rate_range": [110, 150]},
        {"role": "Security & Compliance Lead", "count": 1, "rate_range": [120, 165]},
     ]},
    {"id": "healthcare-telehealth-mvp", "industry": "Healthcare & Life Sciences",
     "title": "Telehealth MVP", "duration_months": 4,
     "summary": "Video visits, e-prescriptions, patient portal — launch-ready in a quarter.",
     "team": [
        {"role": "Product Manager", "count": 1, "rate_range": [110, 150]},
        {"role": "Mobile Engineer", "count": 2, "rate_range": [95, 140]},
        {"role": "Backend Engineer", "count": 1, "rate_range": [100, 140]},
        {"role": "UX Designer", "count": 1, "rate_range": [85, 125]},
     ]},
    {"id": "saas-onboarding-revamp", "industry": "SaaS & Enterprise Software",
     "title": "B2B Onboarding Revamp", "duration_months": 3,
     "summary": "Cut activation friction — new sign-up, empty states, in-app education, and analytics.",
     "team": [
        {"role": "Product Manager", "count": 1, "rate_range": [110, 150]},
        {"role": "Senior Product Designer", "count": 1, "rate_range": [95, 140]},
        {"role": "Full-stack Engineer", "count": 2, "rate_range": [90, 130]},
     ]},
    {"id": "saas-analytics-dashboard", "industry": "SaaS & Enterprise Software",
     "title": "Analytics Dashboard Build", "duration_months": 4,
     "summary": "Self-serve reporting with drill-through and exportable data models.",
     "team": [
        {"role": "Data Engineer", "count": 1, "rate_range": [110, 150]},
        {"role": "Full-stack Engineer", "count": 2, "rate_range": [95, 135]},
        {"role": "Product Designer", "count": 1, "rate_range": [85, 125]},
     ]},
    {"id": "ecomm-storefront-rebuild", "industry": "E-commerce & Retail",
     "title": "Storefront Rebuild (Headless)", "duration_months": 6,
     "summary": "Move from monolithic to Shopify Hydrogen / Next.js headless with a 40% Core Web Vitals lift.",
     "team": [
        {"role": "Tech Lead", "count": 1, "rate_range": [120, 160]},
        {"role": "Senior Frontend Engineer", "count": 2, "rate_range": [95, 135]},
        {"role": "Commerce Solutions Engineer", "count": 1, "rate_range": [100, 140]},
        {"role": "UX Designer", "count": 1, "rate_range": [85, 125]},
     ]},
    {"id": "ai-llm-copilot", "industry": "AI & Data Platforms",
     "title": "Domain LLM Copilot", "duration_months": 5,
     "summary": "RAG-based domain assistant with evaluation harness, guardrails, and observability.",
     "team": [
        {"role": "ML Lead", "count": 1, "rate_range": [140, 185]},
        {"role": "Senior ML Engineer", "count": 2, "rate_range": [120, 160]},
        {"role": "Data Engineer", "count": 1, "rate_range": [110, 150]},
        {"role": "MLOps Engineer", "count": 1, "rate_range": [115, 155]},
     ]},
]

# PMI-based lifecycle: 5 process groups, each with typical deliverables/gates
PROJECT_PHASES = [
    {"id": "initiate", "name": "Initiate",
     "gate": "Project Charter signed by sponsor",
     "deliverables": ["Project charter", "Stakeholder register", "High-level scope"]},
    {"id": "plan", "name": "Plan",
     "gate": "Baselines approved (Scope, Schedule, Cost)",
     "deliverables": ["Scope statement + WBS", "Schedule / Gantt", "Cost baseline",
                       "Risk register", "Communications plan", "Quality & procurement plans", "RACI"]},
    {"id": "execute", "name": "Execute",
     "gate": "First milestone accepted",
     "deliverables": ["Team assembled & onboarded", "Sprint / iteration cadence", "Change requests logged",
                       "Milestone deliverables shipped"]},
    {"id": "monitor", "name": "Monitor & Control",
     "gate": "Weekly status + variance report",
     "deliverables": ["EVM report", "Risk burn-down", "Change control", "Quality audits"]},
    {"id": "close", "name": "Close",
     "gate": "Sponsor sign-off + lessons learned",
     "deliverables": ["Formal acceptance", "Handover pack", "Lessons learned",
                       "Post-implementation review"]},
]


@api.get("/projects/templates")
async def list_project_templates(industry: Optional[str] = None):
    items = PROJECT_TEMPLATES
    if industry:
        items = [t for t in items if t["industry"] == industry]
    return {"templates": items, "count": len(items), "phases": PROJECT_PHASES}


@api.get("/projects/templates/{template_id}")
async def get_project_template(template_id: str):
    for t in PROJECT_TEMPLATES:
        if t["id"] == template_id:
            avg_rate = sum(sum(s["rate_range"]) / 2 * s["count"] for s in t["team"]) / max(1, sum(s["count"] for s in t["team"]))
            monthly_headcount = sum(s["count"] for s in t["team"])
            est_monthly = int(monthly_headcount * avg_rate * 160)  # 160 hrs/month
            return {**t, "phases": PROJECT_PHASES, "monthly_headcount": monthly_headcount,
                    "estimated_monthly_cost": est_monthly,
                    "estimated_total_cost": est_monthly * t["duration_months"]}
    raise HTTPException(404, "Template not found")


def _match_talent_for_role(role: str, industry: str, seen_ids: set) -> Optional[dict]:
    """Pick the best-fit talent for a role slot. Prefers real DB users, falls
    back to the curated pool. Uses skill keyword overlap + industry match."""
    role_kw = role.lower().split()
    # Skill-hint map for common role names
    hints = {
        "engineer": ["Node", "Python", "React", "TypeScript"],
        "designer": ["Figma", "UI", "UX"],
        "architect": ["AWS", "Python", "Node"],
        "manager": ["Product", "Roadmapping"],
        "data": ["Python", "SQL", "Pandas"],
        "ml": ["Python", "PyTorch", "LLMs"],
        "devops": ["AWS", "Terraform", "Kubernetes"],
        "qa": ["Cypress", "Playwright", "Vitest"],
        "mobile": ["Swift", "React Native", "Flutter"],
    }
    kw = []
    for k, v in hints.items():
        if k in role_kw or k in role.lower():
            kw = v; break
    # Assemble a scored candidate list from curated pool
    scored = []
    for e in _CURATED_TALENT:
        if e["name"].replace(" ", "-").replace(".", "") in seen_ids:
            continue
        score = 0
        if kw and any(k in e["skills"] for k in kw):
            score += 3
        if industry.lower().split()[0] in " ".join(e["skills"]).lower():
            score += 1
        # Role name hint
        if any(w in e["headline"].lower() for w in role_kw if len(w) > 3):
            score += 2
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], -x[1]["years"]))
    if not scored:
        return None
    e = scored[0][1]
    seen_ids.add(e["name"].replace(" ", "-").replace(".", ""))
    return {
        "id": f"curated-{e['skill_slug']}-{e['name'].replace(' ', '-').replace('.', '')}",
        "name": e["name"], "headline": e["headline"], "rate": e["rate"],
        "years": e["years"], "location": e["cities"][0], "skills": e["skills"],
        "available_hours_per_week": e["avail"], "curated": True, "verified": True,
    }


@api.get("/projects/templates/{template_id}/team-suggestions")
async def suggest_team_for_template(template_id: str):
    """Auto-suggest a specific vetted talent for each seat in the template's team."""
    template = next((t for t in PROJECT_TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise HTTPException(404, "Template not found")
    seen = set()
    seats = []
    for slot in template["team"]:
        for i in range(slot["count"]):
            suggestion = _match_talent_for_role(slot["role"], template["industry"], seen)
            seats.append({
                "role": slot["role"],
                "seat_index": i + 1,
                "rate_range": slot["rate_range"],
                "suggested_talent": suggestion,  # may be None if pool exhausted
            })
    return {"template_id": template_id, "seats": seats, "count": len(seats)}


class ProjectSeatIn(BaseModel):
    role: str
    seat_index: int
    talent_id: Optional[str] = None
    talent_name: Optional[str] = None
    rate: Optional[float] = None
    locked: bool = False


class ProjectLeadIn(BaseModel):
    template_id: str
    company_name: str
    contact_name: str
    contact_email: EmailStr
    duration_months: int
    notes: Optional[str] = ""
    assigned_team: Optional[List[ProjectSeatIn]] = None
    estimated_monthly_cost: Optional[float] = None
    estimated_total_cost: Optional[float] = None


@api.post("/projects/lead")
async def submit_project_lead(payload: ProjectLeadIn):
    """Employer submits a scoping request against a template. Creates a lead
    doc for the Job Atlas ops team to follow up on."""
    template = next((t for t in PROJECT_TEMPLATES if t["id"] == payload.template_id), None)
    if not template:
        raise HTTPException(400, "Unknown template_id")
    doc = {
        "id": new_id(),
        "template_id": payload.template_id,
        "template_title": template["title"],
        "industry": template["industry"],
        "company_name": payload.company_name,
        "contact_name": payload.contact_name,
        "contact_email": payload.contact_email.lower(),
        "duration_months": int(payload.duration_months),
        "notes": (payload.notes or "")[:1000],
        "assigned_team": [s.dict() for s in (payload.assigned_team or [])],
        "estimated_monthly_cost": float(payload.estimated_monthly_cost or 0),
        "estimated_total_cost": float(payload.estimated_total_cost or 0),
        "status": "new",
        "created_at": now().isoformat(),
    }
    await db.project_leads.insert_one(doc)
    return {"ok": True, "id": doc["id"], "message": "Thanks — our scoping team will reach out within 1 business day."}


@api.get("/auth/sse-token")
async def get_sse_token(user: dict = Depends(get_current_user)):
    """Short-lived token that a browser EventSource can pass via ?token=…
    because EventSource can't set custom headers cross-origin."""
    return {"token": create_token(user["id"], "access")}


@api.get("/talent/me/broadcasts")
async def list_my_broadcasts(user: dict = Depends(get_current_user)):
    if user.get("role") != "talent":
        return {"items": [], "count": 0, "unread": 0}
    items = await db.broadcasts.find({"talent_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    unread = sum(1 for x in items if not x.get("read"))
    return {"items": items, "count": len(items), "unread": unread}


# ---------- Real-time broadcast stream (Server-Sent Events) ----------
# One asyncio.Queue per (talent_id, connection). Broadcast endpoint fans out to
# every queue subscribed to the target talent_id.
import asyncio as _asyncio
_broadcast_subscribers: Dict[str, List[_asyncio.Queue]] = {}


async def _push_broadcast_to_talent(talent_id: str, event: dict):
    subs = _broadcast_subscribers.get(talent_id, [])
    for q in list(subs):
        try:
            q.put_nowait(event)
        except _asyncio.QueueFull:
            pass


@api.get("/talent/me/broadcasts/stream")
async def stream_my_broadcasts(request: Request):
    """SSE stream: talent connects on dashboard mount; server pushes JSON events
    the moment a new broadcast is delivered. Query-param `?token=<jwt>` also
    supported (EventSource in browsers can't set cookies cross-origin cleanly)."""
    import asyncio, json
    from fastapi.responses import StreamingResponse

    # Auth: try cookie first, then ?token= query param (SSE-safe)
    token = request.cookies.get("access_token") or request.query_params.get("token", "")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    except Exception:
        raise HTTPException(401, "Invalid token")
    if not user or user.get("role") != "talent":
        raise HTTPException(403, "Talent only")

    queue: "asyncio.Queue[dict]" = asyncio.Queue(maxsize=64)
    _broadcast_subscribers.setdefault(user["id"], []).append(queue)

    async def event_gen():
        # Initial hello so the client knows the connection is live
        yield f": connected\ndata: {json.dumps({'type':'hello','talent_id':user['id']})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment so ingress proxies don't drop the connection
                    yield ": keepalive\n\n"
        finally:
            try:
                _broadcast_subscribers.get(user["id"], []).remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@api.get("/shortlist/broadcasts")
async def list_broadcast_history(user: dict = Depends(get_current_user)):
    """Employer-facing broadcast history — every send is a fresh doc since
    the send endpoint now uses insert_one (not upsert)."""
    if user.get("role") != "employer":
        raise HTTPException(403, "Only employers can view broadcast history")
    runs = await db.broadcast_runs.find({"employer_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"runs": runs, "count": len(runs)}


@api.post("/talent/me/broadcasts/{broadcast_doc_id}/read")
async def mark_broadcast_read(broadcast_doc_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "talent":
        raise HTTPException(403, "Talent only")
    await db.broadcasts.update_one(
        {"id": broadcast_doc_id, "talent_id": user["id"]},
        {"$set": {"read": True, "read_at": now().isoformat()}},
    )
    return {"ok": True}


# ---------- Newsletter / "Get listed" signup ----------
class NewsletterIn(BaseModel):
    email: EmailStr
    kind: str = "get_listed"           # get_listed | newsletter | notify
    context: Optional[str] = ""        # e.g. skill+city slug they came from


@api.post("/newsletter/signup")
async def newsletter_signup(payload: NewsletterIn, request: Request):
    doc = {
        "id": new_id(), "email": payload.email.lower(),
        "kind": payload.kind, "context": payload.context or "",
        "source_ip": request.client.host if request.client else "",
        "created_at": now().isoformat(),
    }
    await db.newsletter_signups.update_one(
        {"email": doc["email"], "kind": doc["kind"], "context": doc["context"]},
        {"$setOnInsert": doc}, upsert=True,
    )
    logger.info(f"Newsletter signup ({payload.kind}): {payload.email} — {payload.context}")
    return {"ok": True}


# ---------- Generic file upload (avatars, deliverable attachments, etc.) ----------
@api.post("/files/upload")
async def upload_file(file: UploadFile = File(...), kind: str = Form("generic"),
                      user: dict = Depends(get_current_user)):
    """Generic authenticated file upload. `kind` may be 'avatar' | 'portfolio' |
    'deliverable' | 'generic'. Returns {file_id, url, name, content_type, size}."""
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 10 MB")
    ext = (file.filename or "bin").rsplit(".", 1)[-1].lower()
    allowed = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "csv", "svg"}
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}")
    fid = new_id()
    path = f"{STORAGE_APP}/{kind}/{user['id']}/{fid}.{ext}"
    ctype = file.content_type or "application/octet-stream"
    try:
        result = put_object(path, data, ctype)
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {e}")
    await db.files.insert_one({
        "id": fid, "storage_path": result["path"], "original_filename": file.filename,
        "content_type": ctype, "size": len(data), "kind": kind,
        "user_id": user["id"], "created_at": now().isoformat(), "is_deleted": False,
    })
    # Avatar → also patch the user profile
    if kind == "avatar":
        avatar_url = f"/api/files/{fid}"
        await db.users.update_one({"id": user["id"]}, {"$set": {"profile.avatar_url": avatar_url}})
    if kind == "company_logo":
        logo_url = f"/api/files/{fid}"
        await db.users.update_one({"id": user["id"]}, {"$set": {"profile.company_logo_url": logo_url}})
    if kind == "portfolio":
        img_url = f"/api/files/{fid}"
        await db.users.update_one({"id": user["id"]},
                                  {"$push": {"profile.portfolio_images": {"$each": [img_url], "$slice": -6}}})
    # Public read allowed for these kinds so they can display everywhere
    return {"file_id": fid, "url": f"/api/files/{fid}",
            "name": file.filename, "content_type": ctype, "size": len(data)}


# ---------- Chat attachments ----------
@api.post("/messages/upload")
async def upload_message_attachment(engagement_id: str = Form(...), file: UploadFile = File(...),
                                    user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": engagement_id})
    if not eng or user["id"] not in (eng.get("employer_id"), eng.get("talent_id")):
        raise HTTPException(404, "Engagement not found")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 10 MB")
    ext = (file.filename or "bin").rsplit(".", 1)[-1].lower()
    allowed = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "csv"}
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}")
    path = f"{STORAGE_APP}/attachments/{user['id']}/{new_id()}.{ext}"
    ctype = file.content_type or "application/octet-stream"
    try:
        result = put_object(path, data, ctype)
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {e}")
    attachment_id = new_id()
    await db.files.insert_one({
        "id": attachment_id, "storage_path": result["path"], "original_filename": file.filename,
        "content_type": ctype, "size": len(data), "engagement_id": engagement_id,
        "user_id": user["id"], "created_at": now().isoformat(), "is_deleted": False,
    })
    doc = {
        "id": new_id(), "engagement_id": engagement_id,
        "sender_id": user["id"], "sender_name": user["name"],
        "text": f"[attachment: {file.filename}]", "flagged": False,
        "attachment_id": attachment_id, "attachment_name": file.filename,
        "attachment_type": ctype, "created_at": now().isoformat(),
    }
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/files/{file_id}")
async def download_file(file_id: str, user: dict = Depends(get_current_user)):
    rec = await db.files.find_one({"id": file_id, "is_deleted": False})
    if not rec:
        raise HTTPException(404, "File not found")
    # Avatars are readable by any authenticated user (used in profile displays)
    if rec.get("kind") in ("avatar", "company_logo", "portfolio"):
        data, ctype = get_object(rec["storage_path"])
        from fastapi.responses import Response
        return Response(content=data, media_type=rec.get("content_type", ctype))
    # Otherwise scope to engagement participants or uploader
    eng = await db.engagements.find_one({"id": rec.get("engagement_id")}) if rec.get("engagement_id") else None
    allowed_ids = {rec.get("user_id")}
    if eng:
        allowed_ids |= {eng.get("employer_id"), eng.get("talent_id")}
    if user["id"] not in allowed_ids:
        raise HTTPException(403, "Not allowed")
    data, ctype = get_object(rec["storage_path"])
    from fastapi.responses import Response
    return Response(content=data, media_type=rec.get("content_type", ctype))
@api.get("/integrations/providers")
async def integration_providers():
    return list_supported_providers()


@api.post("/integrations/connect")
async def connect_integration(payload: IntegrationConnectIn, user: dict = Depends(get_current_user)):
    integ = {"id": new_id(), "provider": payload.provider,
             "workspace": payload.workspace, "connected_at": now().isoformat(),
             "token_masked": (payload.api_token[:4] + "***" + payload.api_token[-4:]) if len(payload.api_token) > 8 else "***"}
    # Store token in separate secure collection
    await db.integration_tokens.insert_one({"id": integ["id"], "user_id": user["id"],
                                            "provider": payload.provider, "api_token": payload.api_token,
                                            "workspace": payload.workspace})
    await db.users.update_one({"id": user["id"]}, {"$push": {"integrations": integ}})
    # Attempt to fetch initial items
    try:
        items = fetch_from_provider(payload.provider, payload.api_token, payload.workspace)
        for it in items:
            it["id"] = new_id()
            it["user_id"] = user["id"]
            it["source"] = payload.provider
            it["synced_at"] = now().isoformat()
            await db.work_items.insert_one(it)
    except Exception as e:
        logger.warning(f"Provider fetch failed: {e}")
    return integ


@api.delete("/integrations/{integration_id}")
async def disconnect_integration(integration_id: str, user: dict = Depends(get_current_user)):
    await db.integration_tokens.delete_one({"id": integration_id, "user_id": user["id"]})
    await db.users.update_one({"id": user["id"]}, {"$pull": {"integrations": {"id": integration_id}}})
    return {"ok": True}


@api.post("/integrations/sync/{integration_id}")
async def sync_integration(integration_id: str, user: dict = Depends(get_current_user)):
    token_doc = await db.integration_tokens.find_one({"id": integration_id, "user_id": user["id"]})
    if not token_doc:
        raise HTTPException(404, "Integration not found")
    try:
        items = fetch_from_provider(token_doc["provider"], token_doc["api_token"], token_doc.get("workspace", ""))
        count = 0
        for it in items:
            it["id"] = new_id()
            it["user_id"] = user["id"]
            it["source"] = token_doc["provider"]
            it["synced_at"] = now().isoformat()
            await db.work_items.insert_one(it)
            count += 1
        return {"synced": count}
    except Exception as e:
        raise HTTPException(500, f"Sync failed: {e}")


@api.post("/work/upload")
async def upload_work_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    data = await file.read()
    fname = (file.filename or "").lower()
    items: List[Dict[str, Any]] = []
    if fname.endswith((".xlsx", ".xls")):
        items = parse_excel_bytes(data)
    elif fname.endswith((".xml", ".mpp")):
        # .mpp binary can't be parsed here; user should export as XML
        if fname.endswith(".mpp"):
            raise HTTPException(400, "MS Project .mpp binary is not supported directly. Please export as XML from MS Project (File → Save As → XML) and re-upload.")
        items = parse_project_xml_bytes(data)
    else:
        raise HTTPException(400, "Unsupported file type. Upload .xlsx, .xls, or .xml (MS Project XML export).")
    inserted = 0
    for it in items:
        it["id"] = new_id()
        it["user_id"] = user["id"]
        it["source"] = "upload:" + fname.rsplit(".", 1)[-1]
        it["source_file"] = file.filename
        it["synced_at"] = now().isoformat()
        await db.work_items.insert_one(it)
        inserted += 1
    return {"inserted": inserted, "items": inserted}


@api.get("/work/items")
async def list_work_items(user: dict = Depends(get_current_user)):
    items = await db.work_items.find({"user_id": user["id"]}, {"_id": 0}).sort("synced_at", -1).to_list(500)
    return items


# ---------- Availability / Calendar ----------
@api.put("/availability")
async def set_availability(payload: AvailabilityIn, user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"availability": payload.model_dump()}})
    return payload.model_dump()


@api.get("/availability/{user_id}")
async def get_availability(user_id: str, user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "availability": 1, "name": 1, "profile": 1, "role": 1})
    if not u:
        raise HTTPException(404, "User not found")
    return {"user": {"id": user_id, "name": u.get("name"), "role": u.get("role"),
                     "timezone": (u.get("profile") or {}).get("timezone", "UTC")},
            "availability": u.get("availability") or {"timezone": "UTC", "slots": []}}


@api.get("/calendar/events")
async def calendar_events(user: dict = Depends(get_current_user)):
    key = "employer_id" if user["role"] == "employer" else "talent_id"
    engs = await db.engagements.find({key: user["id"]}, {"_id": 0}).to_list(500)
    events = []
    for e in engs:
        events.append({
            "type": "engagement", "id": e["id"],
            "title": f"{e.get('employer_name') if user['role']=='talent' else e.get('talent_name')} · {e.get('hours_allocated')}h",
            "date": e.get("created_at"), "status": e.get("status"),
        })
    items = await db.work_items.find({"user_id": user["id"], "due_date": {"$ne": ""}}, {"_id": 0}).to_list(500)
    for w in items:
        events.append({"type": "task", "id": w["id"], "title": w["title"],
                       "date": w.get("due_date"), "source": w.get("source", "")})
    return events


# ---------- EOI (Expression of Interest) ----------
@api.post("/eoi")
async def create_eoi(payload: EOICreateIn, user: dict = Depends(get_current_user)):
    if user["role"] != "talent":
        raise HTTPException(403, "Only talent can raise an EOI")
    employer_name = None
    if payload.employer_id:
        emp = await db.users.find_one({"id": payload.employer_id, "role": "employer"})
        if not emp:
            raise HTTPException(404, "Employer not found")
        employer_name = emp["name"]
    doc = {
        "id": new_id(), "talent_id": user["id"], "talent_name": user["name"],
        "employer_id": payload.employer_id, "employer_name": employer_name,
        "message": payload.message,
        "proposed_hours_per_week": int(payload.proposed_hours_per_week),
        "start_date": payload.start_date or "",
        "status": "open",
        "created_at": now().isoformat(),
    }
    await db.eois.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/eoi")
async def list_eoi(user: dict = Depends(get_current_user)):
    if user["role"] == "talent":
        q = {"talent_id": user["id"]}
    elif user["role"] == "employer":
        q = {"$or": [{"employer_id": user["id"]}, {"employer_id": None}]}
    else:
        q = {}
    items = await db.eois.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api.post("/eoi/{eoi_id}/accept")
async def accept_eoi(eoi_id: str, payload: EOIActionIn, user: dict = Depends(get_current_user)):
    if user["role"] != "employer":
        raise HTTPException(403, "Only employers can accept EOIs")
    eoi = await db.eois.find_one({"id": eoi_id})
    if not eoi:
        raise HTTPException(404, "EOI not found")
    if eoi.get("status") != "open":
        raise HTTPException(400, "EOI is not open")
    hours = int(payload.hours or eoi.get("proposed_hours_per_week", 10))
    if user.get("hours_balance", 0) < hours:
        raise HTTPException(400, "Insufficient hours balance. Purchase more hours first.")
    talent = await db.users.find_one({"id": eoi["talent_id"], "role": "talent"})
    if not talent:
        raise HTTPException(404, "Talent no longer available")
    eng = {
        "id": new_id(), "employer_id": user["id"], "employer_name": user["name"],
        "talent_id": talent["id"], "talent_name": talent["name"],
        "hours_allocated": hours, "hours_used": 0,
        "scope": payload.scope or eoi.get("message", ""),
        "status": "pending_signatures",
        "employer_signature": None, "talent_signature": None,
        "created_at": now().isoformat(),
        "exclusive_until": (now() + timedelta(days=365)).isoformat(),
        "from_eoi_id": eoi_id,
    }
    await db.engagements.insert_one(eng)
    await db.eois.update_one({"id": eoi_id}, {"$set": {"status": "accepted",
                                                       "accepted_by_employer_id": user["id"],
                                                       "engagement_id": eng["id"]}})
    eng.pop("_id", None)
    return eng


@api.post("/eoi/{eoi_id}/withdraw")
async def withdraw_eoi(eoi_id: str, user: dict = Depends(get_current_user)):
    eoi = await db.eois.find_one({"id": eoi_id})
    if not eoi or eoi["talent_id"] != user["id"]:
        raise HTTPException(404, "EOI not found")
    await db.eois.update_one({"id": eoi_id}, {"$set": {"status": "withdrawn"}})
    return {"ok": True}


# ---------- Pricing ----------
# ---------- Connected Accounts (business/personal identities) ----------
ACCOUNT_PROVIDERS = [
    # Individual talent
    {"id": "linkedin",   "name": "LinkedIn",         "for": ["talent", "employer"], "handle_label": "Profile URL"},
    {"id": "github",     "name": "GitHub",           "for": ["talent"],             "handle_label": "Username"},
    {"id": "gitlab",     "name": "GitLab",           "for": ["talent"],             "handle_label": "Username"},
    {"id": "dribbble",   "name": "Dribbble",         "for": ["talent"],             "handle_label": "Username"},
    {"id": "behance",    "name": "Behance",          "for": ["talent"],             "handle_label": "Username"},
    {"id": "google",     "name": "Google Workspace", "for": ["talent", "employer"], "handle_label": "Email"},
    {"id": "microsoft",  "name": "Microsoft 365",    "for": ["talent", "employer"], "handle_label": "Email"},
    {"id": "slack",      "name": "Slack",            "for": ["employer"],           "handle_label": "Workspace URL"},
    {"id": "teams",      "name": "MS Teams",         "for": ["employer"],           "handle_label": "Tenant"},
    # Business identities & payouts
    {"id": "company",    "name": "Company website",  "for": ["employer"],           "handle_label": "Domain / URL"},
    {"id": "stripe_pay", "name": "Stripe (payouts)", "for": ["talent"],             "handle_label": "Connected account ID"},
    {"id": "payoneer",   "name": "Payoneer",         "for": ["talent"],             "handle_label": "Payee ID"},
    {"id": "wise",       "name": "Wise",             "for": ["talent"],             "handle_label": "Recipient ID"},
    {"id": "plaid",      "name": "Bank via Plaid",   "for": ["employer"],           "handle_label": "Institution"},
]


@api.get("/accounts/providers")
async def account_providers(user: dict = Depends(get_current_user)):
    role = user.get("role", "talent")
    return [p for p in ACCOUNT_PROVIDERS if role in p["for"] or role == "admin"]


@api.get("/accounts")
async def list_accounts(user: dict = Depends(get_current_user)):
    items = await db.connected_accounts.find({"user_id": user["id"]}, {"_id": 0, "api_token": 0}).to_list(200)
    return items


@api.post("/accounts/connect")
async def connect_account(payload: AccountConnectIn, user: dict = Depends(get_current_user)):
    prov = next((p for p in ACCOUNT_PROVIDERS if p["id"] == payload.provider), None)
    if not prov:
        raise HTTPException(400, "Unknown provider")
    if user["role"] not in prov["for"] and user["role"] != "admin":
        raise HTTPException(403, f"{prov['name']} is not available for your role")
    if not payload.handle.strip():
        raise HTTPException(400, "Handle is required")
    doc = {
        "id": new_id(), "user_id": user["id"], "provider": payload.provider,
        "provider_name": prov["name"],
        "handle": payload.handle.strip(),
        "api_token": payload.api_token or "",
        "metadata": payload.metadata or {},
        "connected_at": now().isoformat(),
        "verified": False,
    }
    # Upsert: allow one connection per provider per user
    await db.connected_accounts.delete_many({"user_id": user["id"], "provider": payload.provider})
    await db.connected_accounts.insert_one(doc)
    doc.pop("api_token", None); doc.pop("_id", None)
    return doc


@api.delete("/accounts/{account_id}")
async def disconnect_account(account_id: str, user: dict = Depends(get_current_user)):
    r = await db.connected_accounts.delete_one({"id": account_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api.get("/pricing")
async def get_pricing():
    return {
        "brand": {
            "product": "Job Atlas",
            "brand": "Job Atlas",
            "operator": "Denkoit Softech Pvt. Ltd.",
            "gstin": "36AAGCD3748K1ZC",
        },
        "platform_fee_pct": 8,
        "compare": {"upwork": 20, "fiverr": 20, "freelancer": 10},
        "free_trial": True,
        "plans": [
            {"id": "free", "name": "Free trial", "price": 0, "period": "forever while evaluating",
             "features": ["Unlimited profile browsing", "AI rate suggestions",
                          "Up to 3 signed engagements", "All integrations", "Calendar & availability"]},
            {"id": "starter", "name": "Starter", "price": 29, "period": "per employer / month",
             "features": ["Everything in Free", "Unlimited engagements",
                          "Team seats (up to 5)", "Priority support", "8% platform fee on hours purchased"]},
            {"id": "growth", "name": "Growth", "price": 99, "period": "per employer / month",
             "features": ["Everything in Starter", "Advanced integrations (SAP, ServiceNow)",
                          "SSO / SAML", "Dedicated success manager", "6% platform fee on hours purchased"]},
        ],
        "talent_commission": {
            "note": "Percentage deducted from talent's hourly rate at payout. Lower than market. Volume discounts apply monthly.",
            "tiers": [
                {"upto_hours": 40,   "commission_pct": 8,  "label": "Up to 40h / mo"},
                {"upto_hours": 120,  "commission_pct": 6,  "label": "40 – 120h / mo"},
                {"upto_hours": 250,  "commission_pct": 5,  "label": "120 – 250h / mo"},
                {"upto_hours": 9999, "commission_pct": 4,  "label": "250h+ / mo"},
            ],
            "compare_talent": {"upwork": 10, "fiverr": 20, "toptal": 15},
            "multi_employer_fee": {"amount_usd": 9, "amount_inr": 749,
                                   "condition": "Active engagements with more than 1 employer in the same month"},
        }
    }


@api.get("/legal")
async def get_legal():
    return {
        "company": {
            "legal_name": "Denkoit Softech Pvt. Ltd.",
            "brand": "Job Atlas",
            "product": "Job Atlas",
            "registered_office": "Hyderabad, Telangana, India",
            "gstin": "36AAGCD3748K1ZC",
            "grievance_email": "grievance@talenthub.io",
            "support_email": "hello@talenthub.io",
        },
        "documents": [
            {"id": "terms",   "title": "Terms of Service",  "updated": "2026-02-09"},
            {"id": "privacy", "title": "Privacy Policy",    "updated": "2026-02-09"},
            {"id": "refund",  "title": "Refund Policy",     "updated": "2026-02-09"},
            {"id": "acceptable_use", "title": "Acceptable Use", "updated": "2026-02-09"},
            {"id": "exclusivity", "title": "12-Month Exclusivity Terms", "updated": "2026-02-09"},
        ],
    }


@api.get("/dashboard/metrics")
async def dashboard_metrics(user: dict = Depends(get_current_user)):
    """Unified dashboard aggregates. Shape shared across roles;
    a few keys are role-specific but always present (0 default)."""
    uid = user["id"]
    role = user["role"]

    # Engagements (as employer or talent)
    key = "employer_id" if role == "employer" else "talent_id"
    engs = await db.engagements.find({key: uid}, {"_id": 0}).to_list(500)
    status_counts: Dict[str, int] = {}
    hours_contracted = 0
    active_count = 0
    for e in engs:
        s = e.get("status", "pending_signatures")
        status_counts[s] = status_counts.get(s, 0) + 1
        hours_contracted += int(e.get("hours_allocated") or 0)
        if s in ("contract_signed", "active"):
            active_count += 1

    # Payments (employer)
    hours_purchased = 0
    total_spent = 0.0
    if role == "employer":
        pays = await db.payment_transactions.find({"user_id": uid, "payment_status": "paid"}, {"_id": 0}).to_list(500)
        for p in pays:
            hours_purchased += int(p.get("hours") or 0)
            total_spent += float(p.get("amount") or 0) / 100.0

    # Work items
    items = await db.work_items.find({"user_id": uid}, {"_id": 0}).to_list(1000)
    by_status: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    hours_logged = 0.0
    upcoming: List[Dict[str, Any]] = []
    for w in items:
        by_status[w.get("status", "open")] = by_status.get(w.get("status", "open"), 0) + 1
        by_source[w.get("source", "unknown")] = by_source.get(w.get("source", "unknown"), 0) + 1
        hours_logged += float(w.get("hours_logged") or 0)
        if w.get("due_date"):
            upcoming.append({"title": w["title"], "due_date": w["due_date"], "source": w.get("source", ""), "status": w.get("status", "open")})
    upcoming.sort(key=lambda x: x["due_date"])
    upcoming = upcoming[:6]

    return {
        "role": role,
        "engagements_total": len(engs),
        "engagements_active": active_count,
        "engagements_by_status": status_counts,
        "hours_purchased": hours_purchased,
        "hours_balance": int(user.get("hours_balance") or 0),
        "hours_contracted": hours_contracted,
        "hours_logged": round(hours_logged, 1),
        "total_spent_usd": round(total_spent, 2),
        "work_items_total": len(items),
        "work_items_by_status": by_status,
        "work_items_by_source": by_source,
        "integrations_connected": len(user.get("integrations", []) or []),
        "upcoming": upcoming,
    }


@api.delete("/work/items/{item_id}")
async def delete_work_item(item_id: str, user: dict = Depends(get_current_user)):
    await db.work_items.delete_one({"id": item_id, "user_id": user["id"]})
    return {"ok": True}


@app.on_event("startup")
async def startup():
    # Initialize object storage (non-fatal if it fails; attachment routes will 500)
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.warning(f"Storage init failed: {e}")
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.engagements.create_index("id", unique=True)
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.work_items.create_index("user_id")
    await db.eois.create_index("id", unique=True)
    await db.eois.create_index("talent_id")
    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@talenthub.io")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@2026")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": new_id(), "email": admin_email, "name": "Admin",
            "role": "admin", "password_hash": hash_pw(admin_password),
            "created_at": now().isoformat(),
            "profile": {}, "hours_balance": 0, "integrations": [],
            "admin_permissions": ["superadmin"],
        })
        logger.info(f"Seeded admin: {admin_email} (superadmin)")
    # Backfill: any admin missing admin_permissions gets superadmin (existing sole admin)
    await db.users.update_many(
        {"role": "admin", "$or": [{"admin_permissions": {"$exists": False}},
                                   {"admin_permissions": {"$size": 0}}]},
        {"$set": {"admin_permissions": ["superadmin"]}},
    )

    # ----- Migrate legacy industry labels to standardised taxonomy -----
    try:
        from deps import LEGACY_INDUSTRY_MAP
        migrated = 0
        for legacy, new_label in LEGACY_INDUSTRY_MAP.items():
            r = await db.users.update_many(
                {"role": "employer", "profile.company_industry": legacy},
                {"$set": {"profile.company_industry": new_label}},
            )
            migrated += r.modified_count
        if migrated:
            logger.info(f"Migrated {migrated} employer(s) to standardised industry labels")
    except Exception as e:
        logger.warning(f"Industry migration skipped: {e}")

    # Start the monthly rate-nudge scheduler
    global _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        _scheduler = AsyncIOScheduler(timezone="UTC")

        async def _monthly_nudge_job():
            logger.info("[scheduler] monthly rate-nudge scan starting")
            try:
                result = await _scan_and_record_rate_nudges(request=None)
                logger.info(f"[scheduler] monthly rate-nudge scan done: {result}")
                await db.job_runs.insert_one({
                    "id": new_id(), "job": "monthly_rate_nudge_scan",
                    "at": now().isoformat(), "result": result,
                })
            except Exception as e:
                logger.exception(f"[scheduler] monthly rate-nudge scan failed: {e}")

        # 1st of every month at 09:00 UTC
        _scheduler.add_job(
            _monthly_nudge_job,
            CronTrigger(day=1, hour=9, minute=0),
            id="monthly_rate_nudge_scan",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        _scheduler.start()
        logger.info("[scheduler] rate-nudge scheduler started (cron: day=1 09:00 UTC)")
    except Exception as e:
        logger.warning(f"[scheduler] failed to start: {e}")


_scheduler = None


@app.on_event("shutdown")
async def shutdown():
    global _scheduler
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    client.close()


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
