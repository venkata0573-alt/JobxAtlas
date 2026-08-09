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
    company: Optional[str] = ""  # employer only
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


class EngagementCreateIn(BaseModel):
    talent_id: str
    hours: int
    scope: str


class SignContractIn(BaseModel):
    engagement_id: str
    signature: str  # typed name


class IntegrationConnectIn(BaseModel):
    provider: str
    api_token: str
    workspace: Optional[str] = ""


# ---------- Hour Packages (server-side) ----------
PACKAGES = {
    "starter_10": {"name": "Starter", "hours": 10, "amount": 300.0, "currency": "usd"},
    "growth_50": {"name": "Growth", "hours": 50, "amount": 1400.0, "currency": "usd"},
    "scale_100": {"name": "Scale", "hours": 100, "amount": 2600.0, "currency": "usd"},
    "enterprise_500": {"name": "Enterprise", "hours": 500, "amount": 12000.0, "currency": "usd"},
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
    return PACKAGES


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
    eng = {
        "id": new_id(), "employer_id": user["id"], "employer_name": user["name"],
        "talent_id": payload.talent_id, "talent_name": talent["name"],
        "hours_allocated": payload.hours, "hours_used": 0,
        "scope": payload.scope, "status": "pending_signatures",
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
    field = "employer_signature" if user["id"] == eng["employer_id"] else "talent_signature"
    sig = {"name": payload.signature, "signed_at": now().isoformat(), "user_id": user["id"]}
    update = {field: sig}
    other = eng.get("talent_signature") if field == "employer_signature" else eng.get("employer_signature")
    if other:
        update["status"] = "contract_signed"
        # Deduct hours from employer balance at signing
        await db.users.update_one({"id": eng["employer_id"]}, {"$inc": {"hours_balance": -eng["hours_allocated"]}})
    await db.engagements.update_one({"id": payload.engagement_id}, {"$set": update})
    return await db.engagements.find_one({"id": payload.engagement_id}, {"_id": 0})


# ---------- Third-party integrations & work log ----------
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
@api.get("/pricing")
async def get_pricing():
    return {
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
        ]
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
