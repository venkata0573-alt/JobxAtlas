"""Auth + Profile routes: /auth/register, /auth/login, /auth/logout, /auth/me,
PUT /profile, POST /profile/suggest-rate."""
import secrets
from typing import Any, Dict, List, Optional
from fastapi import Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr

# F-11: config is the sole env boundary.
from config import settings
from deps import (
    api, db, logger, now, new_id, hash_pw, verify_pw, set_auth_cookies,
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
    base = settings.urls.app_base
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
    turnstile_token: Optional[str] = ""


async def _verify_turnstile(token: str, remote_ip: str = "") -> bool:
    """Verify Cloudflare Turnstile token server-side.

    S-08 (partial): TURNSTILE_SECRET_KEY is required-at-boot when
    ENV=production (enforced in config.Settings). In dev/test it is
    optional; if unset here, we fail-open so local dev keeps working —
    but we log a WARN each time so the bypass isn't silent. Full S-08
    still needs IP+email rate limiting and constant-time login response.
    """
    secret = settings.auth.turnstile_secret_key
    if not secret:
        logger.warning(
            "[S-08] TURNSTILE_SECRET_KEY unset (env=%s) — captcha check "
            "BYPASSED for remote_ip=%s. Set the secret to enforce.",
            settings.env, remote_ip or "-",
        )
        return True
    if not token:
        return False
    try:
        import asyncio, urllib.request, urllib.parse, json as _json
        def _post():
            data = urllib.parse.urlencode({
                "secret": secret, "response": token, "remoteip": remote_ip or "",
            }).encode()
            with urllib.request.urlopen(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify", data, timeout=6,
            ) as r:
                return _json.loads(r.read().decode())
        result = await asyncio.to_thread(_post)
        return bool(result.get("success"))
    except Exception:
        return False


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
    if not await _verify_turnstile(payload.turnstile_token or ""):
        raise HTTPException(400, "Captcha verification failed. Please try again.")
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
    # Attributes MUST mirror set_auth_cookies (deps.py:92-93): Chromium and
    # Firefox treat Set-Cookie deletion as a *new* cookie definition — if
    # Secure/SameSite differ, the browser keeps the original httpOnly Secure
    # cookie and the user stays logged in. See S-31.
    response.delete_cookie("access_token", path="/", secure=True, samesite="none")
    response.delete_cookie("refresh_token", path="/", secure=True, samesite="none")
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
    base = settings.urls.app_base
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
    # ---- BGV auto-approve rule ----
    # If the talent has ≥2 YES answers, 0 NO answers, and email is verified → auto-approve.
    talent_id = doc["talent_id"]
    all_refs = await db.reference_checks.find({"talent_id": talent_id}).to_list(50)
    yes_count = sum(1 for r in all_refs if r.get("response") == "yes")
    no_count  = sum(1 for r in all_refs if r.get("response") == "no")
    talent = await db.users.find_one({"id": talent_id}, {"_id": 0})
    if (talent and talent.get("role") == "talent"
        and talent.get("email_verified")
        and talent.get("verification_status") == "pending"
        and yes_count >= 2 and no_count == 0):
        await db.users.update_one(
            {"id": talent_id},
            {"$set": {"verification_status": "verified",
                      "verified_at": now().isoformat(),
                      "verified_by": "auto-bgv-rule",
                      "verification_notes": f"Auto-approved: {yes_count} YES, 0 NO, email verified."}},
        )
    return {"ok": True, "response": payload.response}


# ---------- Public trust page counts ----------
@api.get("/trust/stats")
async def public_trust_stats():
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    month_ago = (_dt.now(_tz.utc) - _td(days=30)).isoformat()
    verified_companies = await db.users.count_documents(
        {"role": "employer", "verification_status": "verified"}
    )
    verified_talents = await db.users.count_documents(
        {"role": "talent", "verification_status": "verified"}
    )
    refs_month = await db.reference_checks.count_documents(
        {"status": "answered", "answered_at": {"$gte": month_ago}}
    )
    refs_all = await db.reference_checks.count_documents({"status": "answered"})
    engagements_month = await db.engagements.count_documents(
        {"status": {"$in": ["contract_signed", "active", "completed"]},
         "created_at": {"$gte": month_ago}}
    )
    total_engagements = await db.engagements.count_documents({})
    return {
        "verified_companies": verified_companies,
        "verified_talents": verified_talents,
        "references_validated_last_30d": refs_month,
        "references_validated_total": refs_all,
        "engagements_last_30d": engagements_month,
        "engagements_total": total_engagements,
        "as_of": _dt.now(_tz.utc).isoformat(),
    }


@api.get("/trust/timeseries")
async def public_trust_timeseries():
    """30-day daily timeseries powering the animated charts on /trust.
    Buckets: refs_answered, engagements_signed, verified_talents, verified_companies.
    Days with no activity return 0 so the chart draws a full 30 pts.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    now = _dt.now(_tz.utc)
    start = (now - _td(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Prefill 30 buckets keyed by yyyy-mm-dd
    buckets: Dict[str, Dict[str, int]] = {}
    for i in range(30):
        d = (start + _td(days=i)).strftime("%Y-%m-%d")
        buckets[d] = {"date": d, "refs": 0, "engagements": 0, "verified_talents": 0, "verified_companies": 0}

    def _bucket_from(iso_val):
        if not iso_val:
            return None
        try:
            if isinstance(iso_val, str):
                dt = _dt.fromisoformat(iso_val.replace("Z", "+00:00"))
            else:
                dt = iso_val
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
            key = dt.strftime("%Y-%m-%d")
            return key if key in buckets else None
        except Exception:
            return None

    start_iso = start.isoformat()

    # References answered
    async for r in db.reference_checks.find(
        {"status": "answered", "answered_at": {"$gte": start_iso}},
        {"answered_at": 1, "_id": 0},
    ):
        k = _bucket_from(r.get("answered_at"))
        if k:
            buckets[k]["refs"] += 1

    # Engagements signed / active / completed
    async for e in db.engagements.find(
        {"status": {"$in": ["contract_signed", "active", "completed"]},
         "created_at": {"$gte": start_iso}},
        {"created_at": 1, "_id": 0},
    ):
        k = _bucket_from(e.get("created_at"))
        if k:
            buckets[k]["engagements"] += 1

    # Verifications (talent + company). Falls back to created_at when
    # verified_at is absent so historical seed data still lights up the chart.
    async for u in db.users.find(
        {"verification_status": "verified"},
        {"role": 1, "verified_at": 1, "created_at": 1, "_id": 0},
    ):
        ts = u.get("verified_at") or u.get("created_at")
        k = _bucket_from(ts)
        if not k:
            continue
        if u.get("role") == "talent":
            buckets[k]["verified_talents"] += 1
        elif u.get("role") == "employer":
            buckets[k]["verified_companies"] += 1

    return {"series": list(buckets.values()), "as_of": now.isoformat()}


def _initials(name: str) -> str:
    """Return anonymised initials from a full name. e.g. 'Ravi Shankar' → 'R.S.'"""
    if not name:
        return "—"
    parts = [p for p in str(name).strip().split() if p]
    if not parts:
        return "—"
    if len(parts) == 1:
        return (parts[0][0] + ".").upper()
    return ".".join(p[0].upper() for p in parts[:2]) + "."


@api.get("/trust/timeseries/details")
async def public_trust_timeseries_details(series: str = "refs"):
    """Anonymised drill-through items for a single /trust chart series.

    All rows are fully anonymised (initials + industry / role / response chip)
    so this endpoint is safe to expose publicly. Returns up to 300 rows across
    the same 30-day window as `/trust/timeseries` to keep the payload light.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    valid = {"refs", "engagements", "verified_talents", "verified_companies"}
    if series not in valid:
        raise HTTPException(400, f"series must be one of {sorted(valid)}")
    now = _dt.now(_tz.utc)
    start = (now - _td(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_iso = start.isoformat()

    def _fmt_day(iso_val):
        if not iso_val:
            return None
        try:
            if isinstance(iso_val, str):
                dt = _dt.fromisoformat(iso_val.replace("Z", "+00:00"))
            else:
                dt = iso_val
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None

    items: List[Dict[str, Any]] = []

    if series == "refs":
        # Reference-check answers. Anonymise both the talent and the reference.
        # response ∈ {yes, no, partial}
        talent_ids: List[str] = []
        docs = await db.reference_checks.find(
            {"status": "answered", "answered_at": {"$gte": start_iso}},
            {"_id": 0, "answered_at": 1, "response": 1, "ref_name": 1, "talent_id": 1},
        ).sort("answered_at", -1).to_list(300)
        for d in docs:
            if d.get("talent_id"):
                talent_ids.append(d["talent_id"])
        # Batch-fetch talent names
        talents_by_id: Dict[str, str] = {}
        if talent_ids:
            async for u in db.users.find(
                {"id": {"$in": list(set(talent_ids))}},
                {"_id": 0, "id": 1, "name": 1},
            ):
                talents_by_id[u["id"]] = u.get("name") or ""
        for d in docs:
            day = _fmt_day(d.get("answered_at"))
            if not day:
                continue
            items.append({
                "date": day,
                "primary": _initials(talents_by_id.get(d.get("talent_id"), "")),
                "secondary": f"Reference {_initials(d.get('ref_name') or '')}",
                "chip": (d.get("response") or "answered").lower(),
                "kind": "reference",
            })

    elif series == "engagements":
        # Signed / active / completed engagements. Anonymise employer + talent.
        docs = await db.engagements.find(
            {"status": {"$in": ["contract_signed", "active", "completed"]},
             "created_at": {"$gte": start_iso}},
            {"_id": 0, "created_at": 1, "status": 1, "hours_purchased": 1,
             "employer_id": 1, "talent_id": 1},
        ).sort("created_at", -1).to_list(300)
        uids: List[str] = []
        for d in docs:
            for k in ("employer_id", "talent_id"):
                if d.get(k):
                    uids.append(d[k])
        users_by_id: Dict[str, Dict[str, Any]] = {}
        if uids:
            async for u in db.users.find(
                {"id": {"$in": list(set(uids))}},
                {"_id": 0, "id": 1, "name": 1, "role": 1, "profile": 1},
            ):
                users_by_id[u["id"]] = u
        for d in docs:
            day = _fmt_day(d.get("created_at"))
            if not day:
                continue
            emp = users_by_id.get(d.get("employer_id"), {})
            tal = users_by_id.get(d.get("talent_id"), {})
            industry = (emp.get("profile") or {}).get("company_industry") or "Company"
            hours = d.get("hours_purchased") or 0
            items.append({
                "date": day,
                "primary": f"{_initials(tal.get('name') or '')} · {industry}",
                "secondary": f"{hours}h engagement",
                "chip": d.get("status") or "signed",
                "kind": "engagement",
            })

    elif series in ("verified_talents", "verified_companies"):
        role = "talent" if series == "verified_talents" else "employer"
        docs = await db.users.find(
            {"verification_status": "verified", "role": role},
            {"_id": 0, "name": 1, "verified_at": 1, "created_at": 1,
             "profile": 1, "id": 1},
        ).to_list(300)
        # Sort by verified_at desc (falls back to created_at)
        docs.sort(key=lambda u: (u.get("verified_at") or u.get("created_at") or ""), reverse=True)
        for d in docs:
            day = _fmt_day(d.get("verified_at") or d.get("created_at"))
            if not day:
                continue
            prof = d.get("profile") or {}
            if role == "talent":
                skills = prof.get("skills") or []
                primary_skill = skills[0] if skills else (prof.get("headline") or "Professional")
                secondary = f"{primary_skill} · {prof.get('location') or 'Global'}"
            else:
                secondary = f"{prof.get('company_industry') or 'Company'} · KYB"
            items.append({
                "date": day,
                "primary": _initials(d.get("name") or ""),
                "secondary": secondary,
                "chip": "verified",
                "kind": role,
            })

    return {"series": series, "items": items, "count": len(items),
            "window_start": start_iso, "as_of": now.isoformat()}


# ---------- Drill-through PDF export (signed) ----------
def _drill_signature(items: List[Dict[str, Any]], series: str, ts: str) -> str:
    """Deterministic SHA-256 of the rendered rows. Any tamper of the visible
    text changes the hash, which the /verify-drill endpoint detects."""
    import hashlib, json as _json
    canonical = _json.dumps(
        {"series": series, "ts": ts, "items": items},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    # S-04 (partial): fallback to "jobatlas-drill-v1" removed;
    # DRILL_SIGN_SECRET required at boot via config.CryptoSettings.
    # Remaining S-04 work: switch from sha256(secret+msg) to
    # hmac.new(secret, msg, sha256) + verify-endpoint recompute.
    salt = settings.crypto.drill_secret.encode()
    return hashlib.sha256(salt + canonical).hexdigest()


@api.get("/trust/timeseries/details/pdf")
async def public_trust_timeseries_pdf(series: str = "refs", q: str = "", request: Request = None):
    """Signed PDF of the (optionally filtered) drill-through list. Anyone can
    verify authenticity by scanning the QR code or hitting
    `POST /api/trust/verify-drill` with the hash + payload.
    """
    from datetime import datetime as _dt, timezone as _tz
    from fastapi.responses import Response as _R

    # Resolve the public base URL so the QR is scannable outside the network.
    base_url = settings.urls.public_base
    if not base_url and isinstance(request, Request):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        if host:
            base_url = f"{proto}://{host}"

    # Reuse the JSON endpoint's logic to keep behavior in sync.
    payload = await public_trust_timeseries_details(series=series)
    items = payload.get("items", [])
    # Apply the same search filter the client did — so the PDF matches what
    # the user is looking at.
    needle = (q or "").strip().lower()
    if needle:
        items = [it for it in items if
                 needle in (it.get("primary") or "").lower() or
                 needle in (it.get("secondary") or "").lower() or
                 needle in (it.get("chip") or "").lower() or
                 needle in (it.get("date") or "")]

    ts = _dt.now(_tz.utc).isoformat()
    sig = _drill_signature(items, series, ts)

    # Persist a receipt so /verify-drill can look up authenticity even years later.
    await db.drill_receipts.insert_one({
        "id": new_id(), "signature": sig, "series": series,
        "q": needle, "count": len(items), "ts": ts,
        "created_at": ts,
    })

    pdf_bytes = _render_drill_pdf(series=series, q=needle, items=items,
                                  ts=ts, signature=sig, base_url=base_url)
    fname = f"jobatlas-trust-{series}-{ts[:10]}.pdf"
    return _R(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Drill-Signature": sig},
    )


class DrillVerifyIn(BaseModel):
    signature: str
    series: str
    ts: str
    items: List[Dict[str, Any]]


@api.post("/trust/verify-drill")
async def public_verify_drill(payload: DrillVerifyIn):
    """Return authentic ✓ if the (signature, series, ts, items) triplet
    matches what we would generate now. Also checks the receipt log."""
    expected = _drill_signature(payload.items, payload.series, payload.ts)
    match = (expected == payload.signature)
    receipt = await db.drill_receipts.find_one(
        {"signature": payload.signature}, {"_id": 0, "signature": 1, "series": 1, "ts": 1, "count": 1}
    )
    return {
        "authentic": bool(match),
        "expected_signature": expected,
        "receipt_found": bool(receipt),
        "receipt": receipt,
    }


@api.get("/trust/verify-drill/{signature}")
async def public_verify_drill_lookup(signature: str):
    """Simple lookup landing hit by the QR code — confirms the receipt exists.
    A full tamper-check requires re-posting the items to /trust/verify-drill.
    """
    r = await db.drill_receipts.find_one(
        {"signature": signature},
        {"_id": 0, "signature": 1, "series": 1, "ts": 1, "count": 1, "q": 1},
    )
    return {"receipt_found": bool(r), "receipt": r}


def _render_drill_pdf(*, series: str, q: str, items: List[Dict[str, Any]],
                      ts: str, signature: str, base_url: str = "") -> bytes:
    """Branded PDF: Job Atlas header, drill metadata, day-grouped anonymised
    rows, QR code + SHA-256 signature footer for third-party verification."""
    import io, base64
    import qrcode
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.lib.utils import ImageReader

    VIOLET = colors.HexColor("#6B21A8")
    INK = colors.HexColor("#0B1B2B")
    VIOLET_50 = colors.HexColor("#F5F3FF")
    MUTED = colors.HexColor("#6B6B6B")

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=LETTER)
    W, H = LETTER
    _base_url = base_url  # closure-visible alias so ruff resolves the reference

    def _header(page_num: int):
        # Ink band
        c.setFillColor(INK)
        c.rect(0, H - 0.9 * inch, W, 0.9 * inch, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(0.6 * inch, H - 0.55 * inch, "Job Atlas · Trust")
        c.setFillColor(VIOLET)
        c.setFont("Helvetica", 9)
        c.drawString(0.6 * inch, H - 0.75 * inch,
                     f"DRILL-THROUGH · {series.upper().replace('_', ' ')}")
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 8)
        c.drawRightString(W - 0.6 * inch, H - 0.55 * inch,
                          f"Generated {ts[:19].replace('T', ' ')} UTC")
        c.drawRightString(W - 0.6 * inch, H - 0.75 * inch, f"Page {page_num}")

    def _footer(page_num: int):
        # QR + signature strip
        y = 0.55 * inch
        c.setStrokeColor(colors.HexColor("#e5e7eb"))
        c.line(0.6 * inch, y + 0.75 * inch, W - 0.6 * inch, y + 0.75 * inch)

        # QR code linking to verify endpoint
        verify_url = f"{_base_url}/api/trust/verify-drill/{signature}" if _base_url else f"/api/trust/verify-drill/{signature}"
        qr = qrcode.QRCode(version=1, box_size=6, border=1)
        qr.add_data(verify_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0B1B2B", back_color="white")
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        img_buf.seek(0)
        c.drawImage(ImageReader(img_buf), 0.6 * inch, y - 0.05 * inch, width=0.75 * inch, height=0.75 * inch)

        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(1.5 * inch, y + 0.6 * inch, "Signature · SHA-256")
        c.setFillColor(INK)
        c.setFont("Courier", 7)
        # Chunk signature so it wraps neatly
        sig1 = signature[:44]
        sig2 = signature[44:]
        c.drawString(1.5 * inch, y + 0.45 * inch, sig1)
        c.drawString(1.5 * inch, y + 0.32 * inch, sig2)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7)
        c.drawString(1.5 * inch, y + 0.15 * inch,
                     "Scan the QR or POST /api/trust/verify-drill to verify this document.")
        c.drawString(1.5 * inch, y + 0.03 * inch,
                     "Any edit to the text above invalidates the signature.")

    page = 1
    _header(page)
    y = H - 1.15 * inch

    # Metadata box
    c.setFillColor(VIOLET_50); c.rect(0.6 * inch, y - 0.7 * inch, W - 1.2 * inch, 0.65 * inch, stroke=0, fill=1)
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 10)
    c.drawString(0.75 * inch, y - 0.15 * inch, f"Series · {series.replace('_', ' ').title()}")
    c.setFillColor(MUTED); c.setFont("Helvetica", 9)
    c.drawString(0.75 * inch, y - 0.35 * inch, f"Rows · {len(items)}   Filter · {q or '(none)'}   Window · last 30 days")
    c.drawString(0.75 * inch, y - 0.52 * inch, "All names are anonymised to initials. This PDF is safe to share externally.")

    y -= 1.05 * inch

    # Group by day
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        by_day.setdefault(it.get("date") or "—", []).append(it)
    days = sorted(by_day.keys(), reverse=True)

    if not items:
        c.setFillColor(MUTED); c.setFont("Helvetica-Oblique", 11)
        c.drawString(0.75 * inch, y, "No matching rows in the last 30 days.")
        _footer(page); c.showPage(); c.save()
        return buf.getvalue()

    for day in days:
        # Day header
        if y < 1.6 * inch:
            _footer(page); c.showPage(); page += 1; _header(page); y = H - 1.15 * inch
        c.setFillColor(VIOLET); c.setFont("Helvetica-Bold", 10)
        c.drawString(0.6 * inch, y, day)
        c.setFillColor(MUTED); c.setFont("Helvetica", 8)
        c.drawRightString(W - 0.6 * inch, y, f"{len(by_day[day])} row(s)")
        y -= 0.18 * inch

        for it in by_day[day]:
            if y < 1.5 * inch:
                _footer(page); c.showPage(); page += 1; _header(page); y = H - 1.15 * inch
            c.setStrokeColor(colors.HexColor("#e5e7eb"))
            c.setFillColor(colors.white)
            c.rect(0.6 * inch, y - 0.32 * inch, W - 1.2 * inch, 0.34 * inch, stroke=1, fill=0)
            c.setFillColor(INK); c.setFont("Helvetica-Bold", 10)
            c.drawString(0.75 * inch, y - 0.1 * inch, (it.get("primary") or "—")[:70])
            c.setFillColor(MUTED); c.setFont("Helvetica", 8)
            c.drawString(0.75 * inch, y - 0.24 * inch, (it.get("secondary") or "")[:100])
            c.setFillColor(VIOLET); c.setFont("Helvetica-Bold", 8)
            c.drawRightString(W - 0.75 * inch, y - 0.16 * inch, (it.get("chip") or "").upper())
            y -= 0.4 * inch

        y -= 0.1 * inch

    _footer(page); c.showPage(); c.save()
    return buf.getvalue()


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


# ---------- CRM Integrations (connect-via-token) ----------
class CrmConnectIn(BaseModel):
    provider: str      # 'hubspot' | 'salesforce' | 'sharepoint' | 'slack'
    access_token: str
    instance_url: Optional[str] = ""    # required for Salesforce (e.g. https://myorg.my.salesforce.com)


async def _validate_crm_token(provider: str, token: str, instance_url: str = "") -> Dict[str, Any]:
    """Hit the provider's own API with the token to validate it. Returns
    a small dict with account metadata on success. Fails fast on any error."""
    import asyncio, urllib.request, urllib.error, json as _json
    def _get(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            return _json.loads(r.read().decode())
    try:
        if provider == "hubspot":
            info = await asyncio.to_thread(
                _get,
                "https://api.hubapi.com/oauth/v1/access-tokens/" + urllib.parse.quote(token),
                {},
            )
            return {"ok": True, "account_id": info.get("hub_id"), "user": info.get("user"),
                    "scopes": info.get("scopes")}
        if provider == "salesforce":
            if not instance_url:
                return {"ok": False, "error": "instance_url required"}
            info = await asyncio.to_thread(
                _get,
                instance_url.rstrip("/") + "/services/oauth2/userinfo",
                {"Authorization": f"Bearer {token}"},
            )
            return {"ok": True, "account_id": info.get("organization_id"),
                    "user": info.get("email"), "instance_url": instance_url}
        if provider == "slack":
            info = await asyncio.to_thread(
                _get, "https://slack.com/api/auth.test",
                {"Authorization": f"Bearer {token}"},
            )
            if not info.get("ok"):
                return {"ok": False, "error": info.get("error", "invalid")}
            return {"ok": True, "account_id": info.get("team_id"), "user": info.get("user")}
        if provider == "sharepoint":
            # SharePoint via Microsoft Graph — token is a Graph access token
            info = await asyncio.to_thread(
                _get, "https://graph.microsoft.com/v1.0/me",
                {"Authorization": f"Bearer {token}"},
            )
            return {"ok": True, "account_id": info.get("id"), "user": info.get("mail") or info.get("userPrincipalName")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": False, "error": "Unknown provider"}


import urllib.parse  # noqa: E402  (used by _validate_crm_token)


@api.post("/integrations/crm/connect")
async def connect_crm(payload: CrmConnectIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("employer", "admin"):
        raise HTTPException(403, "Employers only")
    if payload.provider not in ("hubspot", "salesforce", "sharepoint", "slack"):
        raise HTTPException(400, "Unknown provider")
    v = await _validate_crm_token(payload.provider, payload.access_token, payload.instance_url or "")
    if not v.get("ok"):
        raise HTTPException(400, f"Could not verify {payload.provider} token: {v.get('error')}")
    doc = {
        "id": new_id(), "user_id": user["id"], "provider": payload.provider,
        "access_token": payload.access_token,   # NOTE: consider KMS in prod
        "instance_url": payload.instance_url or "",
        "account_id": v.get("account_id"),
        "connected_user": v.get("user"),
        "scopes": v.get("scopes") or [],
        "connected_at": now().isoformat(),
    }
    await db.crm_integrations.update_one(
        {"user_id": user["id"], "provider": payload.provider},
        {"$set": doc}, upsert=True,
    )
    return {"ok": True, "provider": payload.provider,
            "account_id": v.get("account_id"), "connected_user": v.get("user")}


@api.get("/integrations/crm")
async def list_crm(user: dict = Depends(get_current_user)):
    items = await db.crm_integrations.find(
        {"user_id": user["id"]}, {"_id": 0, "access_token": 0},
    ).to_list(20)
    return {"items": items}


@api.delete("/integrations/crm/{provider}")
async def disconnect_crm(provider: str, user: dict = Depends(get_current_user)):
    r = await db.crm_integrations.delete_one({"user_id": user["id"], "provider": provider})
    return {"ok": True, "deleted": r.deleted_count}


class CrmPushLeadIn(BaseModel):
    provider: str
    talent_id: Optional[str] = ""
    talent_name: Optional[str] = ""
    email: Optional[str] = ""
    note: Optional[str] = ""


@api.post("/integrations/crm/push-lead")
async def push_lead_to_crm(payload: CrmPushLeadIn, user: dict = Depends(get_current_user)):
    """Push a shortlisted talent as a Contact/Lead into the connected CRM."""
    import asyncio, urllib.request, json as _json
    intg = await db.crm_integrations.find_one({"user_id": user["id"], "provider": payload.provider})
    if not intg:
        raise HTTPException(400, f"{payload.provider} is not connected")
    token = intg["access_token"]
    def _post(url, body, headers):
        req = urllib.request.Request(
            url, data=_json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return _json.loads(r.read().decode() or "{}")
    try:
        if payload.provider == "hubspot":
            body = {"properties": {
                "email": payload.email or "no-email@jobatlas.io",
                "firstname": (payload.talent_name or "").split(" ")[0],
                "lastname": " ".join((payload.talent_name or "").split(" ")[1:]) or "Prospect",
                "hs_lead_status": "NEW",
                "message": payload.note or f"Shortlisted from Job Atlas · talent id {payload.talent_id}",
            }}
            r = await asyncio.to_thread(_post, "https://api.hubapi.com/crm/v3/objects/contacts",
                                         body, {"Authorization": f"Bearer {token}"})
            return {"ok": True, "external_id": r.get("id")}
        if payload.provider == "salesforce":
            url = intg["instance_url"].rstrip("/") + "/services/data/v58.0/sobjects/Lead/"
            first, *rest = (payload.talent_name or "Prospect").split(" ")
            body = {
                "FirstName": first, "LastName": " ".join(rest) or "Prospect",
                "Email": payload.email or "no-email@jobatlas.io",
                "Company": "Job Atlas Shortlist",
                "Description": payload.note or f"talent {payload.talent_id}",
            }
            r = await asyncio.to_thread(_post, url, body, {"Authorization": f"Bearer {token}"})
            return {"ok": True, "external_id": r.get("id")}
        raise HTTPException(400, f"Push not supported for {payload.provider}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Push failed: {str(e)[:200]}")


# ---------- CRM nightly sync ----------
async def _sync_shortlists_to_crm(*, user_id: Optional[str] = None,
                                   provider_filter: Optional[str] = None,
                                   trigger: str = "cron") -> Dict[str, Any]:
    """For every employer with a connected CRM, push shortlist rows added
    since their `last_sync_at` (per provider). Deduped via db.crm_sync_log.

    Returns aggregate counts. `user_id` scopes to a single employer for the
    manual `/sync-now` endpoint. Curated demo talents are skipped — they have
    no real email or contact so a CRM push is meaningless.
    """
    q: Dict[str, Any] = {}
    if user_id:
        q["user_id"] = user_id
    if provider_filter:
        q["provider"] = provider_filter
    integrations = await db.crm_integrations.find(q).to_list(500)

    started = now().isoformat()
    pushed_total = 0
    skipped_total = 0
    failed_total = 0
    per_conn: List[Dict[str, Any]] = []

    for intg in integrations:
        uid = intg["user_id"]
        prov = intg["provider"]
        if prov not in ("hubspot", "salesforce"):
            continue  # only push-capable providers
        last_sync = intg.get("last_sync_at") or "1970-01-01T00:00:00+00:00"

        # New shortlist rows since last_sync
        rows = await db.shortlists.find(
            {"employer_id": uid, "created_at": {"$gt": last_sync}, "is_curated": {"$ne": True}},
        ).sort("created_at", 1).to_list(500)

        pushed = 0
        skipped = 0
        failed = 0
        for row in rows:
            tid = row.get("talent_id")
            # Idempotency: skip if already logged
            existing = await db.crm_sync_log.find_one({
                "user_id": uid, "provider": prov, "talent_id": tid, "status": "pushed"
            })
            if existing:
                skipped += 1
                continue
            try:
                push_payload = CrmPushLeadIn(
                    provider=prov,
                    talent_id=tid or "",
                    talent_name=row.get("talent_name") or "",
                    email=row.get("email") or "",
                    note=f"Auto-sync from Job Atlas shortlist · rate ${row.get('hourly_rate', '?')}/hr",
                )
                # Reconstruct a minimal fake user dict so push_lead_to_crm's
                # scope check passes.
                fake_user = {"id": uid, "role": "employer"}
                res = await push_lead_to_crm(push_payload, user=fake_user)
                await db.crm_sync_log.insert_one({
                    "id": new_id(), "user_id": uid, "provider": prov,
                    "talent_id": tid, "external_id": res.get("external_id"),
                    "status": "pushed", "at": now().isoformat(), "trigger": trigger,
                })
                pushed += 1
            except HTTPException as he:
                failed += 1
                await db.crm_sync_log.insert_one({
                    "id": new_id(), "user_id": uid, "provider": prov,
                    "talent_id": tid, "status": "failed",
                    "error": str(he.detail)[:300], "at": now().isoformat(), "trigger": trigger,
                })
            except Exception as e:  # noqa: BLE001
                failed += 1
                await db.crm_sync_log.insert_one({
                    "id": new_id(), "user_id": uid, "provider": prov,
                    "talent_id": tid, "status": "failed",
                    "error": str(e)[:300], "at": now().isoformat(), "trigger": trigger,
                })

        # Advance the watermark even if some rows failed — retry surfaces via /sync-log
        await db.crm_integrations.update_one(
            {"user_id": uid, "provider": prov},
            {"$set": {"last_sync_at": started, "last_sync_trigger": trigger,
                      "last_sync_result": {"pushed": pushed, "skipped": skipped, "failed": failed}}},
        )
        pushed_total += pushed
        skipped_total += skipped
        failed_total += failed
        per_conn.append({
            "user_id": uid, "provider": prov,
            "pushed": pushed, "skipped": skipped, "failed": failed,
        })

    return {"started_at": started, "connections": len(integrations),
            "pushed": pushed_total, "skipped": skipped_total, "failed": failed_total,
            "detail": per_conn, "trigger": trigger}


@api.post("/integrations/crm/sync-now")
async def sync_crm_now(user: dict = Depends(get_current_user)):
    """Manual CRM sync for the current employer. Runs the same routine the
    nightly cron uses, but scoped to the caller."""
    if user.get("role") not in ("employer", "admin"):
        raise HTTPException(403, "Employers only")
    return await _sync_shortlists_to_crm(user_id=user["id"], trigger="manual")


@api.get("/integrations/crm/sync-log")
async def list_crm_sync_log(user: dict = Depends(get_current_user), limit: int = 50):
    """Recent sync entries for the current employer — powers the UI 'last sync'
    strip. Returns newest first."""
    items = await db.crm_sync_log.find(
        {"user_id": user["id"]}, {"_id": 0},
    ).sort("at", -1).to_list(min(max(limit, 1), 200))
    return {"items": items, "count": len(items)}

