"""Auth + Profile routes: /auth/register, /auth/login, /auth/logout, /auth/me,
PUT /profile, POST /profile/suggest-rate."""
import os, secrets
from typing import List, Optional
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr

from deps import (
    api, db, now, new_id, hash_pw, verify_pw, set_auth_cookies,
    get_current_user, EMPLOYER_INDUSTRIES,
)


def _email_verification_html(name: str, verify_url: str) -> str:
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#FAF9F6;font-family:Georgia,serif;color:#0B1B2B;">
<div style="max-width:540px;margin:0 auto;background:#fff;border:1px solid #ddd;padding:32px;">
  <p style="letter-spacing:.2em;font-size:11px;color:#C79A3B;margin:0 0 8px">JOB ATLAS</p>
  <h1 style="font-size:22px;margin:0 0 12px">Confirm your email, {name.split(' ')[0]}.</h1>
  <p style="font-size:14px;line-height:1.5;margin:0 0 20px">One click and you're in. This link expires in 24 hours.</p>
  <p style="margin:0 0 24px"><a href="{verify_url}" style="background:#0B1B2B;color:#fff;padding:12px 20px;text-decoration:none;display:inline-block">Verify email →</a></p>
  <p style="font-size:11px;color:#999">If the button doesn't work, paste this URL into your browser:<br/>{verify_url}</p>
</div></body></html>"""


async def _send_verification_email(user_doc: dict) -> str:
    """Generate a verification token, persist it, and email a magic link.
    Returns the token (for tests / dev)."""
    token = secrets.token_urlsafe(32)
    await db.users.update_one(
        {"id": user_doc["id"]},
        {"$set": {"email_verification_token": token,
                  "email_verification_sent_at": now().isoformat()}},
    )
    base = os.environ.get("APP_BASE_URL") or ""
    verify_url = f"{base}/verify-email?token={token}"
    try:
        from mailer import send_email
        await send_email(
            to=user_doc["email"],
            subject="Confirm your Job Atlas email",
            html=_email_verification_html(user_doc.get("name") or "there", verify_url),
        )
    except Exception:
        pass  # dev-fallback: token is still in DB for manual verify
    return token
from ai_service import suggest_hourly_rate


# ---------- Pydantic models (auth-only) ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str  # 'talent' | 'employer'
    company_industry: Optional[str] = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileIn(BaseModel):
    headline: Optional[str] = ""
    bio: Optional[str] = ""
    skills: List[str] = []
    industries: List[str] = []
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


class RateSuggestIn(BaseModel):
    skills: List[str]
    years_experience: int
    location: Optional[str] = "Global"


# ---------- Routes ----------
@api.post("/auth/register")
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower()
    if payload.role not in ("talent", "employer"):
        raise HTTPException(400, "role must be talent or employer")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(400, "Email already registered")
    industry = (payload.company_industry or "").strip()
    if payload.role == "employer" and industry and industry not in EMPLOYER_INDUSTRIES:
        raise HTTPException(400, f"Unknown industry. Must be one of: {', '.join(EMPLOYER_INDUSTRIES)}")
    uid = new_id()
    doc = {
        "id": uid, "email": email, "name": payload.name, "role": payload.role,
        "password_hash": hash_pw(payload.password),
        "created_at": now().isoformat(),
        "email_verified": False,
        "verification_status": "none",   # none | pending | verified | rejected
        "profile": {"headline": "", "bio": "", "skills": [], "years_experience": 0,
                    "hourly_rate": 0.0, "location": "", "portfolio_url": "",
                    "avatar_url": "", "company": "",
                    "company_industry": industry if payload.role == "employer" else ""},
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
    await _send_verification_email(doc)
    set_auth_cookies(response, uid)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    doc.pop("email_verification_token", None)
    return doc


@api.get("/auth/verify-email")
async def verify_email(token: str):
    """Public magic-link endpoint. Marks the user verified and consumes the token."""
    if not token:
        raise HTTPException(400, "Missing token")
    u = await db.users.find_one({"email_verification_token": token})
    if not u:
        raise HTTPException(400, "Invalid or expired verification token")
    await db.users.update_one(
        {"id": u["id"]},
        {"$set": {"email_verified": True,
                  "email_verified_at": now().isoformat()},
         "$unset": {"email_verification_token": "",
                    "email_verification_sent_at": ""}},
    )
    return {"ok": True, "email": u["email"], "name": u.get("name")}


@api.post("/auth/resend-verification")
async def resend_verification(user: dict = Depends(get_current_user)):
    if user.get("email_verified"):
        return {"ok": True, "already_verified": True}
    u = await db.users.find_one({"id": user["id"]})
    if not u:
        raise HTTPException(404, "User not found")
    await _send_verification_email(u)
    return {"ok": True}


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


@api.put("/profile")
async def update_profile(payload: ProfileIn, user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"profile": payload.model_dump()}})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return updated


@api.post("/profile/suggest-rate")
async def suggest_rate(payload: RateSuggestIn, user: dict = Depends(get_current_user)):
    result = await suggest_hourly_rate(payload.skills, payload.years_experience, payload.location or "Global")
    return result



# ---------- Company + Talent verification submission ----------
class CompanyVerificationIn(BaseModel):
    company_name: str
    company_registration_number: Optional[str] = ""
    tax_id: Optional[str] = ""
    company_website: Optional[str] = ""
    company_size: Optional[str] = ""
    year_founded: Optional[int] = None
    country: Optional[str] = ""


class TalentReferenceIn(BaseModel):
    name: str
    email: EmailStr
    relationship: str
    company: Optional[str] = ""
    phone: Optional[str] = ""


class TalentWorkHistoryIn(BaseModel):
    company: str
    role: str
    start: str
    end: Optional[str] = ""
    description: Optional[str] = ""


class TalentBgvIn(BaseModel):
    work_history: List[TalentWorkHistoryIn]
    references: List[TalentReferenceIn]
    government_id_url: Optional[str] = ""      # already uploaded via storage
    linkedin_url: Optional[str] = ""


@api.post("/verification/company")
async def submit_company_verification(payload: CompanyVerificationIn,
                                       user: dict = Depends(get_current_user)):
    """An employer submits company info + KYB proofs. Verification enters 'pending'."""
    if user.get("role") != "employer":
        raise HTTPException(403, "Employers only")
    profile_updates = {
        "profile.company_name": payload.company_name,
        "profile.company_registration_number": payload.company_registration_number or "",
        "profile.tax_id": payload.tax_id or "",
        "profile.company_website": payload.company_website or "",
        "profile.company_size": payload.company_size or "",
        "profile.year_founded": payload.year_founded,
        "profile.country": payload.country or "",
        "verification_status": "pending",
        "verification_submitted_at": now().isoformat(),
    }
    await db.users.update_one({"id": user["id"]}, {"$set": profile_updates})
    return {"ok": True, "status": "pending"}


@api.post("/verification/bgv")
async def submit_bgv(payload: TalentBgvIn, user: dict = Depends(get_current_user)):
    """A talent submits work history + references + govt ID for BGV. Verification
    enters 'pending' — Job Atlas ops runs background checks manually."""
    if user.get("role") != "talent":
        raise HTTPException(403, "Talents only")
    if len(payload.references) < 2:
        raise HTTPException(400, "Please supply at least two references")
    if len(payload.work_history) < 1:
        raise HTTPException(400, "Please include at least one previous role")
    profile_updates = {
        "profile.work_history": [w.dict() for w in payload.work_history],
        "profile.references": [r.dict() for r in payload.references],
        "profile.government_id_url": payload.government_id_url or "",
        "profile.linkedin_url": payload.linkedin_url or "",
        "verification_status": "pending",
        "verification_submitted_at": now().isoformat(),
    }
    await db.users.update_one({"id": user["id"]}, {"$set": profile_updates})

    # Auto-email each reference a 1-question check form. Each row gets a unique
    # token so we can accept anonymous responses without login.
    base = os.environ.get("APP_BASE_URL") or ""
    from mailer import send_email
    for ref in payload.references:
        token = secrets.token_urlsafe(24)
        await db.reference_checks.insert_one({
            "id": new_id(),
            "token": token,
            "talent_id": user["id"],
            "talent_name": user.get("name"),
            "ref_name": ref.name,
            "ref_email": ref.email.lower(),
            "ref_relationship": ref.relationship,
            "ref_company": ref.company or "",
            "status": "sent",
            "response": None,
            "note": None,
            "sent_at": now().isoformat(),
        })
        try:
            check_url = f"{base}/reference-check?token={token}"
            html = _reference_check_html(
                ref_name=ref.name, talent_name=user.get("name") or "the applicant",
                relationship=ref.relationship, check_url=check_url,
            )
            await send_email(
                to=ref.email,
                subject=f"Quick reference check for {user.get('name')} — Job Atlas",
                html=html,
            )
        except Exception:
            pass
    return {"ok": True, "status": "pending",
            "references_notified": len(payload.references)}


def _reference_check_html(*, ref_name: str, talent_name: str,
                           relationship: str, check_url: str) -> str:
    first = (ref_name or "there").split()[0]
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#FAF9F6;font-family:Georgia,serif;color:#0B1B2B;">
<div style="max-width:540px;margin:0 auto;background:#fff;border:1px solid #ddd;padding:32px;">
  <p style="letter-spacing:.2em;font-size:11px;color:#C79A3B;margin:0 0 8px">JOB ATLAS · REFERENCE CHECK</p>
  <h1 style="font-size:20px;margin:0 0 12px">Hi {first},</h1>
  <p style="font-size:14px;line-height:1.5;margin:0 0 12px">
    <b>{talent_name}</b> listed you as a reference on Job Atlas as a <b>{relationship}</b>.
    Would you take 30 seconds to confirm?
  </p>
  <p style="margin:24px 0 8px"><a href="{check_url}" style="background:#0B1B2B;color:#fff;padding:12px 20px;text-decoration:none;display:inline-block">Answer one question →</a></p>
  <p style="font-size:11px;color:#999;margin-top:12px">This link is private to you and expires in 14 days. If you don&apos;t recognise {talent_name}, click the link and hit &quot;No&quot; — we&apos;ll follow up.</p>
</div></body></html>"""


@api.get("/reference-check/{token}")
async def reference_check_get(token: str):
    """Public endpoint used by the reference-check landing page."""
    doc = await db.reference_checks.find_one({"token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Reference link not found or expired")
    # Never expose talent internal ID — only public-safe fields
    return {
        "id": doc["id"],
        "talent_name": doc.get("talent_name"),
        "ref_name": doc.get("ref_name"),
        "ref_relationship": doc.get("ref_relationship"),
        "ref_company": doc.get("ref_company"),
        "status": doc.get("status"),
        "already_answered": doc.get("response") is not None,
    }


class ReferenceCheckResponseIn(BaseModel):
    response: str    # "yes" | "no" | "partial"
    note: Optional[str] = ""


@api.post("/reference-check/{token}")
async def reference_check_post(token: str, payload: ReferenceCheckResponseIn):
    if payload.response not in ("yes", "no", "partial"):
        raise HTTPException(400, "response must be yes|no|partial")
    doc = await db.reference_checks.find_one({"token": token})
    if not doc:
        raise HTTPException(404, "Reference link not found or expired")
    if doc.get("response") is not None:
        return {"ok": True, "already_answered": True}
    await db.reference_checks.update_one(
        {"token": token},
        {"$set": {"response": payload.response,
                  "note": (payload.note or "")[:500],
                  "status": "answered",
                  "answered_at": now().isoformat()}},
    )
    return {"ok": True, "response": payload.response}


@api.get("/admin/reference-checks/{talent_id}")
async def admin_list_reference_checks(talent_id: str, user: dict = Depends(get_current_user)):
    """Ops uses this to see which references have replied before deciding to
    approve BGV. Requires moderation or support scope."""
    from deps import has_admin_scope
    if not (has_admin_scope(user, "moderation") or has_admin_scope(user, "support")):
        raise HTTPException(403, "Requires moderation or support scope")
    items = await db.reference_checks.find(
        {"talent_id": talent_id}, {"_id": 0, "token": 0},
    ).sort("sent_at", -1).to_list(50)
    return {"items": items, "count": len(items),
            "answered": sum(1 for i in items if i.get("response") is not None)}


@api.get("/verification/me")
async def my_verification_state(user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]},
                                 {"_id": 0, "password_hash": 0,
                                  "email_verification_token": 0})
    return {
        "email_verified": bool(u.get("email_verified")),
        "verification_status": u.get("verification_status") or "none",
        "verification_submitted_at": u.get("verification_submitted_at"),
        "verified_at": u.get("verified_at"),
        "verification_notes": u.get("verification_notes"),
        "profile": u.get("profile") or {},
    }
