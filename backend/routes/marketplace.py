"""Marketplace routes — first physical extraction from server.py.

Contains:
  Public / SEO
    GET  /seo/skills
    GET  /seo/city-skills
    GET  /sitemap.xml
  Marketplace stats (Landing trust bar)
    GET  /marketplace/industries
    GET  /marketplace/stats

Not yet moved (still in server.py because they require the curated-talent
list and SSE state):
    GET  /seo/hire/{skill_slug}
    GET  /seo/hire-city/{slug}
    POST /shortlist, GET /shortlist, DELETE /shortlist/{talent_id}
    POST /shortlist/broadcast
    GET/POST talent broadcast endpoints (SSE)
"""
from fastapi import Request
from fastapi.responses import Response as _XmlResponse

from deps import api, db, now, SEO_SKILLS, SEO_CITIES, EMPLOYER_INDUSTRIES


# ---------- SEO index endpoints ----------
@api.get("/seo/skills")
async def seo_skills():
    return {"skills": SEO_SKILLS}


@api.get("/seo/city-skills")
async def seo_city_skills():
    combos = []
    for c in SEO_CITIES:
        for s in SEO_SKILLS[:6]:
            combos.append({"slug": f"{s}-{c}", "skill": s, "city": c})
    return {"combos": combos}


# ---------- Sitemap ----------
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
    for s in SEO_SKILLS:
        lines.append(f"  <url><loc>{origin}/hire/{s}</loc>"
                     f"<lastmod>{now_iso}</lastmod>"
                     f"<changefreq>weekly</changefreq>"
                     f"<priority>0.8</priority></url>")
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
    import os
    origin = os.environ.get("PUBLIC_SITE_URL")
    if not origin:
        fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        fwd_proto = request.headers.get("x-forwarded-proto", "https")
        origin = f"{fwd_proto}://{fwd_host}" if fwd_host else str(request.base_url).rstrip("/")
    return _XmlResponse(content=_build_sitemap_xml(origin), media_type="application/xml")


# ---------- Marketplace stats ----------
@api.get("/marketplace/industries")
async def marketplace_industries():
    """Canonical list of employer industries + live count per industry (0 for
    industries no one has claimed yet). Powers the Landing trust bar and the
    employer registration industry picker."""
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



# ---------- Shortlist CRUD ----------
# (Broadcast POST + SSE stream endpoints stay in server.py because they touch
# module-level _broadcast_subscribers queues.)
from typing import List, Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel

from deps import new_id, get_current_user


class ShortlistIn(BaseModel):
    talent_id: str
    talent_name: str
    headline: Optional[str] = ""
    location: Optional[str] = ""
    hourly_rate: Optional[float] = 0.0
    skills: List[str] = []
    context: Optional[str] = ""
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
