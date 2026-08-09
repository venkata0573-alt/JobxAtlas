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

# ---------- Setup ----------
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="TalentHub API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("talenthub")


# ---------- Utils ----------
def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception:
        return False


def now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(user_id: str, kind: str = "access") -> str:
    exp = now() + (timedelta(minutes=60 * 24 * 7) if kind == "refresh" else timedelta(hours=12))
    payload = {"sub": user_id, "type": kind, "exp": exp}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def new_id() -> str:
    return str(uuid.uuid4())


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


# ---------- Models ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str  # 'talent' | 'employer'


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

# Receiving bank — Denkoit Softech Pvt. Ltd. (Geminista / TalentHub)
COMPANY_BANK = {
    "beneficiary": "Denkoit Softech Pvt. Ltd.",
    "brand": "Geminista",
    "product": "TalentHub",
    "bank": "ICICI Bank",
    "branch": "—",
    "account_number": "112405000771",
    "ifsc": "ICIC0001124",
    "swift": "ICICINBBCTS",
    "upi": "MSDENKOITSOFTECHPVTLTD.eazypay@icici",
    "gstin": "36AAGCD3748K1ZC",
    "note": "Quote the reference ID exactly when transferring so we can credit your hours quickly.",
}


# ---------- Auth Routes ----------
@api.post("/auth/register")
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower()
    if payload.role not in ("talent", "employer"):
        raise HTTPException(400, "role must be talent or employer")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(400, "Email already registered")
    uid = new_id()
    doc = {
        "id": uid, "email": email, "name": payload.name, "role": payload.role,
        "password_hash": hash_pw(payload.password),
        "created_at": now().isoformat(),
        "profile": {"headline": "", "bio": "", "skills": [], "years_experience": 0,
                    "hourly_rate": 0.0, "location": "", "portfolio_url": "",
                    "avatar_url": "", "company": ""},
        "hours_balance": 0,
        "integrations": [],
        "availability": {"timezone": "UTC", "slots": [
            {"day": 1, "start": "09:00", "end": "17:00"},
            {"day": 2, "start": "09:00", "end": "17:00"},
            {"day": 3, "start": "09:00", "end": "17:00"},
            {"day": 4, "start": "09:00", "end": "17:00"},
            {"day": 5, "start": "09:00", "end": "17:00"},
        ]},
    }
    await db.users.insert_one(doc)
    set_auth_cookies(response, uid)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return doc


@api.post("/auth/login")
async def login(payload: LoginIn, response: Response):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_pw(payload.password, user.get("password_hash", "")):
        raise HTTPException(401, "Invalid email or password")
    set_auth_cookies(response, user["id"])
    user.pop("password_hash", None); user.pop("_id", None)
    return user


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


# ---------- Profile ----------
@api.put("/profile")
async def update_profile(payload: ProfileIn, user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"profile": payload.model_dump()}})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return updated


@api.post("/profile/suggest-rate")
async def suggest_rate(payload: RateSuggestIn, user: dict = Depends(get_current_user)):
    result = await suggest_hourly_rate(payload.skills, payload.years_experience, payload.location or "Global")
    return result


# ---------- Browse Talent (public listing but contact hidden) ----------
@api.get("/talent")
async def list_talent(q: Optional[str] = None, skill: Optional[str] = None, min_exp: int = 0):
    query = {"role": "talent"}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                        {"profile.headline": {"$regex": q, "$options": "i"}}]
    if skill:
        query["profile.skills"] = {"$regex": skill, "$options": "i"}
    if min_exp:
        query["profile.years_experience"] = {"$gte": int(min_exp)}
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0, "email": 0, "integrations": 0})
    items = await cursor.to_list(200)
    # Hide sensitive contact until purchased (email removed; keep name display)
    return items


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
@api.get("/admin/bank-transfers")
async def admin_bank_list(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    items = await db.payment_transactions.find(
        {"method": "bank_transfer", "payment_status": {"$ne": "paid"}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    return items


@api.post("/admin/bank-transfers/{payment_id}/approve")
async def admin_bank_approve(payment_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    rec = await db.payment_transactions.find_one({"id": payment_id})
    if not rec:
        raise HTTPException(404, "Not found")
    if rec.get("payment_status") == "paid":
        return {"ok": True, "already": True}
    await db.payment_transactions.update_one({"id": payment_id}, {"$set": {
        "status": "completed", "payment_status": "paid", "verified_by": user["id"],
        "updated_at": now().isoformat(),
    }})
    await db.users.update_one({"id": rec["user_id"]}, {"$inc": {"hours_balance": rec["hours"]}})
    return {"ok": True}


@api.post("/admin/bank-transfers/{payment_id}/reject")
async def admin_bank_reject(payment_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    await db.payment_transactions.update_one({"id": payment_id}, {"$set": {
        "status": "rejected", "payment_status": "rejected", "updated_at": now().isoformat(),
    }})
    return {"ok": True}


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
                                     "product_data": {"name": f"TalentHub {pkg['name']} - {pkg['hours']} hours"},
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


@api.get("/admin/reviews")
async def admin_list_reviews(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    items = await db.reviews.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api.post("/admin/reviews/{rid}/approve")
async def admin_approve_review(rid: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    r = await db.reviews.update_one({"id": rid}, {"$set": {"status": "approved"}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api.post("/admin/reviews/{rid}/reject")
async def admin_reject_review(rid: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    r = await db.reviews.update_one({"id": rid}, {"$set": {"status": "rejected"}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


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


@api.get("/admin/grievances")
async def admin_list_grievances(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    items = await db.grievances.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@api.post("/admin/grievances/{gid}/resolve")
async def admin_resolve_grievance(gid: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    r = await db.grievances.update_one({"id": gid}, {"$set": {"status": "resolved",
                                                              "resolved_at": now().isoformat(),
                                                              "resolved_by": user["id"]}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


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


@api.post("/admin/payouts/run")
async def admin_run_payouts(payload: PayoutRunIn, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    run_id = new_id()
    talents = await db.users.find({"role": "talent"}, {"_id": 0, "id": 1}).to_list(2000)
    payouts: List[Dict[str, Any]] = []
    total_net = 0.0
    for t in talents:
        e = await _compute_talent_earnings(t["id"], payload.period_start, payload.period_end)
        if e["hours"] <= 0:
            continue
        doc = {
            "id": new_id(), "run_id": run_id, "talent_id": e["talent_id"],
            "talent_name": e["talent_name"], "hourly_rate": e["hourly_rate"],
            "hours": e["hours"], "employers_count": e["employers_count"],
            "commission_pct": e["commission_pct"], "gross": e["gross"],
            "commission": e["commission"], "multi_employer_fee": e["multi_employer_fee"],
            "net": e["net"], "currency": payload.currency,
            "period_start": payload.period_start, "period_end": payload.period_end,
            "status": "pending", "created_at": now().isoformat(),
        }
        await db.payouts.insert_one(doc)
        payouts.append({k: v for k, v in doc.items() if k != "_id"})
        total_net += float(e["net"])
    run_doc = {
        "id": run_id, "period_start": payload.period_start, "period_end": payload.period_end,
        "currency": payload.currency, "count": len(payouts), "total_net": round(total_net, 2),
        "created_by": user["id"], "created_at": now().isoformat(), "status": "generated",
    }
    await db.payout_runs.insert_one(run_doc)
    run_doc.pop("_id", None)
    return {"run": run_doc, "payouts": payouts}


@api.get("/admin/payouts/runs")
async def admin_list_runs(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await db.payout_runs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.get("/admin/payouts/{run_id}")
async def admin_run_detail(run_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    run = await db.payout_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Run not found")
    items = await db.payouts.find({"run_id": run_id}, {"_id": 0}).to_list(1000)
    return {"run": run, "payouts": items}


@api.post("/admin/payouts/{payout_id}/mark-paid")
async def admin_mark_paid(payout_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    r = await db.payouts.update_one({"id": payout_id}, {"$set": {"status": "paid",
                                                                 "paid_at": now().isoformat()}})
    return {"ok": True}


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
SEO_SKILLS = [
    "react-developers", "python-developers", "node-developers", "ui-designers",
    "ux-designers", "data-scientists", "devops-engineers", "product-managers",
    "figma-designers", "mobile-developers", "wordpress-developers", "salesforce-consultants",
]


@api.get("/seo/skills")
async def seo_skills():
    return {"skills": SEO_SKILLS}


@api.get("/seo/hire/{skill_slug}")
async def seo_hire(skill_slug: str):
    if skill_slug not in SEO_SKILLS:
        raise HTTPException(404, "Unknown skill")
    keyword = skill_slug.replace("-", " ")
    talent = await db.users.find(
        {"role": "talent", "profile.skills": {"$regex": keyword.split()[0], "$options": "i"}},
        {"_id": 0, "password_hash": 0, "email": 0, "integrations": 0},
    ).limit(24).to_list(24)
    return {
        "slug": skill_slug, "keyword": keyword,
        "title": f"Hire {keyword.title()} by the hour — TalentHub",
        "description": f"Hire vetted {keyword} on TalentHub. Buy hours in bulk, sign contracts, integrate with Jira & Asana. From $29/mo.",
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


SEO_CITIES = ["london", "new-york", "san-francisco", "berlin", "singapore", "dubai", "sydney", "toronto", "remote"]


@api.get("/seo/city-skills")
async def seo_city_skills():
    combos = []
    for c in SEO_CITIES:
        for s in SEO_SKILLS[:6]:
            combos.append({"slug": f"{s}-{c}", "skill": s, "city": c})
    return {"combos": combos}


@api.get("/seo/hire-city/{slug}")
async def seo_hire_city(slug: str):
    # Slug format: {skill-slug}-{city}
    parts = slug.rsplit("-", 1)
    if len(parts) != 2:
        raise HTTPException(400, "Invalid slug — expected 'skill-city'")
    skill_slug, city = parts
    if skill_slug not in SEO_SKILLS or city not in SEO_CITIES:
        raise HTTPException(404, "Unknown skill/city combo")
    keyword = skill_slug.replace("-", " ")
    city_pretty = city.replace("-", " ").title()
    talent = await db.users.find(
        {"role": "talent", "profile.skills": {"$regex": keyword.split()[0], "$options": "i"}},
        {"_id": 0, "password_hash": 0, "email": 0, "integrations": 0},
    ).limit(24).to_list(24)
    return {
        "slug": slug, "skill": skill_slug, "city": city, "keyword": keyword, "city_pretty": city_pretty,
        "title": f"Hire {keyword.title()} in {city_pretty} — TalentHub",
        "description": f"Hire vetted {keyword} available in {city_pretty} on TalentHub. Purchase hours, sign contracts, track work in Jira and Asana.",
        "talent": talent,
    }


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
            "product": "TalentHub",
            "brand": "Geminista",
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
            "brand": "Geminista",
            "product": "TalentHub",
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
        })
        logger.info(f"Seeded admin: {admin_email}")


@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
