"""Auth + Profile routes: /auth/register, /auth/login, /auth/logout, /auth/me,
PUT /profile, POST /profile/suggest-rate."""
from typing import List, Optional
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr

from deps import (
    api, db, now, new_id, hash_pw, verify_pw, set_auth_cookies,
    get_current_user, EMPLOYER_INDUSTRIES,
)
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


@api.put("/profile")
async def update_profile(payload: ProfileIn, user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"profile": payload.model_dump()}})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return updated


@api.post("/profile/suggest-rate")
async def suggest_rate(payload: RateSuggestIn, user: dict = Depends(get_current_user)):
    result = await suggest_hourly_rate(payload.skills, payload.years_experience, payload.location or "Global")
    return result
