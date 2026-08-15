"""Admin routes — physically extracted from server.py.

All /admin/* endpoints live here. Shared helpers (_scan_and_record_rate_nudges,
_scheduler ref) still live in server.py — they're imported below at first-use time
to avoid an import cycle at module load.
"""
from typing import Any, Dict, List, Optional
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from deps import (
    api, db, now, new_id, get_current_user, logger,
    hash_pw, ADMIN_SCOPES, ADMIN_SCOPE_IDS, has_admin_scope,
)


def _require_scope(user: dict, scope: str):
    if not has_admin_scope(user, scope):
        raise HTTPException(403, f"Requires admin scope: {scope}")


class PayoutRunIn(BaseModel):
    period_start: str
    period_end: str
    currency: str = "usd"


@api.get("/admin/me")
async def admin_me(user: dict = Depends(get_current_user)):
    """Returns current admin identity + granted scopes so the UI knows which
    tabs to render."""
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    perms = user.get("admin_permissions") or []
    if "superadmin" in perms:
        effective = list(ADMIN_SCOPE_IDS)
    else:
        effective = [p for p in perms if p in ADMIN_SCOPE_IDS]
    return {
        "id": user["id"], "name": user.get("name"), "email": user.get("email"),
        "admin_permissions": perms,
        "effective_scopes": effective,
        "scopes_catalog": ADMIN_SCOPES,
    }


@api.get("/admin/bank-transfers")
async def admin_bank_list(user: dict = Depends(get_current_user)):
    _require_scope(user, "finance")
    items = await db.payment_transactions.find(
        {"method": "bank_transfer", "payment_status": {"$ne": "paid"}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    return items


@api.post("/admin/bank-transfers/{payment_id}/approve")
async def admin_bank_approve(payment_id: str, user: dict = Depends(get_current_user)):
    _require_scope(user, "finance")
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
    _require_scope(user, "finance")
    await db.payment_transactions.update_one({"id": payment_id}, {"$set": {
        "status": "rejected", "payment_status": "rejected", "updated_at": now().isoformat(),
    }})
    return {"ok": True}


@api.get("/admin/reviews")
async def admin_list_reviews(user: dict = Depends(get_current_user)):
    _require_scope(user, "moderation")
    items = await db.reviews.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api.post("/admin/reviews/{rid}/approve")
async def admin_approve_review(rid: str, user: dict = Depends(get_current_user)):
    _require_scope(user, "moderation")
    r = await db.reviews.update_one({"id": rid}, {"$set": {"status": "approved"}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api.post("/admin/reviews/{rid}/reject")
async def admin_reject_review(rid: str, user: dict = Depends(get_current_user)):
    _require_scope(user, "moderation")
    r = await db.reviews.update_one({"id": rid}, {"$set": {"status": "rejected"}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api.get("/admin/grievances")
async def admin_list_grievances(user: dict = Depends(get_current_user)):
    if not (has_admin_scope(user, "support") or has_admin_scope(user, "moderation")):
        raise HTTPException(403, "Requires support or moderation scope")
    items = await db.grievances.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@api.post("/admin/grievances/{gid}/resolve")
async def admin_resolve_grievance(gid: str, user: dict = Depends(get_current_user)):
    if not (has_admin_scope(user, "support") or has_admin_scope(user, "moderation")):
        raise HTTPException(403, "Requires support or moderation scope")
    r = await db.grievances.update_one({"id": gid}, {"$set": {"status": "resolved",
                                                              "resolved_at": now().isoformat(),
                                                              "resolved_by": user["id"]}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api.post("/admin/payouts/run")
async def admin_run_payouts(payload: PayoutRunIn, user: dict = Depends(get_current_user)):
    from server import _compute_talent_earnings  # late import to avoid cycle
    _require_scope(user, "finance")
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
    _require_scope(user, "finance")
    return await db.payout_runs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.get("/admin/payouts/{run_id}")
async def admin_run_detail(run_id: str, user: dict = Depends(get_current_user)):
    _require_scope(user, "finance")
    run = await db.payout_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Run not found")
    items = await db.payouts.find({"run_id": run_id}, {"_id": 0}).to_list(1000)
    return {"run": run, "payouts": items}


@api.post("/admin/payouts/{payout_id}/mark-paid")
async def admin_mark_paid(payout_id: str, user: dict = Depends(get_current_user)):
    _require_scope(user, "finance")
    r = await db.payouts.update_one({"id": payout_id}, {"$set": {"status": "paid",
                                                                 "paid_at": now().isoformat()}})
    return {"ok": True}


@api.post("/admin/rate-nudges/scan")
async def admin_rate_nudge_scan(request: Request, user: dict = Depends(get_current_user)):
    from server import _scan_and_record_rate_nudges  # late import to avoid cycle
    if user.get("role") != "admin":
        raise HTTPException(403, "Admins only")
    return await _scan_and_record_rate_nudges(request=request)


@api.get("/admin/scheduler")
async def admin_scheduler_status(user: dict = Depends(get_current_user)):
    """Reports the state of the APScheduler + next fire time for the monthly nudge."""
    from server import _scheduler  # late import to avoid cycle
    if user.get("role") != "admin":
        raise HTTPException(403, "Admins only")
    if not _scheduler or not _scheduler.running:
        return {"running": False, "jobs": []}
    jobs = []
    for j in _scheduler.get_jobs():
        jobs.append({
            "id": j.id, "name": j.name,
            "next_run_time": str(j.next_run_time) if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    last = await db.job_runs.find({"job": "monthly_rate_nudge_scan"},
                                   {"_id": 0}).sort("at", -1).limit(1).to_list(1)
    return {"running": True, "jobs": jobs, "last_run": last[0] if last else None}


# ---------- Staff management (superadmin only) ----------
class StaffCreateIn(BaseModel):
    email: EmailStr
    name: str
    password: str
    admin_permissions: List[str] = []


class StaffUpdateIn(BaseModel):
    admin_permissions: Optional[List[str]] = None
    name: Optional[str] = None
    password: Optional[str] = None


def _sanitize_scopes(scopes: List[str]) -> List[str]:
    return sorted({s for s in scopes if s in ADMIN_SCOPE_IDS})


@api.get("/admin/staff")
async def admin_list_staff(user: dict = Depends(get_current_user)):
    _require_scope(user, "superadmin")
    admins = await db.users.find({"role": "admin"},
                                  {"_id": 0, "password_hash": 0}).sort("created_at", 1).to_list(200)
    for a in admins:
        a["admin_permissions"] = a.get("admin_permissions") or []
    return {"staff": admins, "scopes_catalog": ADMIN_SCOPES}


@api.post("/admin/staff")
async def admin_create_staff(payload: StaffCreateIn, user: dict = Depends(get_current_user)):
    _require_scope(user, "superadmin")
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email already registered")
    scopes = _sanitize_scopes(payload.admin_permissions)
    if not scopes:
        raise HTTPException(400, "Grant at least one scope")
    doc = {
        "id": new_id(), "email": email, "name": payload.name,
        "role": "admin", "password_hash": hash_pw(payload.password),
        "created_at": now().isoformat(),
        "profile": {}, "hours_balance": 0, "integrations": [],
        "admin_permissions": scopes,
        "created_by": user["id"],
    }
    await db.users.insert_one(doc)
    doc.pop("password_hash", None); doc.pop("_id", None)
    return doc


@api.patch("/admin/staff/{staff_id}")
async def admin_update_staff(staff_id: str, payload: StaffUpdateIn,
                              user: dict = Depends(get_current_user)):
    _require_scope(user, "superadmin")
    target = await db.users.find_one({"id": staff_id, "role": "admin"})
    if not target:
        raise HTTPException(404, "Admin not found")
    updates: Dict[str, Any] = {}
    if payload.admin_permissions is not None:
        scopes = _sanitize_scopes(payload.admin_permissions)
        # Guard: cannot strip superadmin from yourself (avoid lockout)
        if staff_id == user["id"] and "superadmin" not in scopes:
            raise HTTPException(400, "You cannot remove your own superadmin scope")
        # Guard: don't allow removing the last superadmin
        if "superadmin" in (target.get("admin_permissions") or []) and "superadmin" not in scopes:
            other_sa = await db.users.count_documents(
                {"role": "admin", "admin_permissions": "superadmin",
                 "id": {"$ne": staff_id}}
            )
            if other_sa == 0:
                raise HTTPException(400, "At least one superadmin is required")
        updates["admin_permissions"] = scopes
    if payload.name is not None:
        updates["name"] = payload.name.strip()[:80]
    if payload.password:
        updates["password_hash"] = hash_pw(payload.password)
    if not updates:
        return {"ok": True, "updated": 0}
    await db.users.update_one({"id": staff_id}, {"$set": updates})
    return {"ok": True, "updated": 1}


@api.delete("/admin/staff/{staff_id}")
async def admin_delete_staff(staff_id: str, user: dict = Depends(get_current_user)):
    _require_scope(user, "superadmin")
    if staff_id == user["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    target = await db.users.find_one({"id": staff_id, "role": "admin"})
    if not target:
        raise HTTPException(404, "Admin not found")
    if "superadmin" in (target.get("admin_permissions") or []):
        other_sa = await db.users.count_documents(
            {"role": "admin", "admin_permissions": "superadmin", "id": {"$ne": staff_id}}
        )
        if other_sa == 0:
            raise HTTPException(400, "At least one superadmin is required")
    await db.users.delete_one({"id": staff_id})
    return {"ok": True}


# ---------- Support console (support scope) ----------
@api.get("/admin/users")
async def admin_list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_scope(user, "support")
    query: Dict[str, Any] = {}
    if role in ("talent", "employer", "admin"):
        query["role"] = role
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"profile.company_name": {"$regex": q, "$options": "i"}},
        ]
    items = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(200)
    return {"items": items, "count": len(items)}


@api.get("/admin/users/{uid}")
async def admin_user_detail(uid: str, user: dict = Depends(get_current_user)):
    _require_scope(user, "support")
    u = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(404, "User not found")
    engs = await db.engagements.find(
        {"$or": [{"talent_id": uid}, {"employer_id": uid}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    eois = await db.eois.find({"talent_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(50)
    payments = await db.payment_transactions.find(
        {"user_id": uid}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    notes = await db.support_notes.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {
        "user": u, "engagements": engs, "eois": eois,
        "payments": payments, "notes": notes,
    }


class SupportNoteIn(BaseModel):
    text: str


@api.post("/admin/users/{uid}/notes")
async def admin_add_note(uid: str, payload: SupportNoteIn, user: dict = Depends(get_current_user)):
    _require_scope(user, "support")
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "Empty note")
    target = await db.users.find_one({"id": uid}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(404, "User not found")
    doc = {
        "id": new_id(), "user_id": uid, "text": text[:2000],
        "author_id": user["id"], "author_name": user.get("name"),
        "created_at": now().isoformat(),
    }
    await db.support_notes.insert_one(doc)
    doc.pop("_id", None)
    return doc


class UserAdjustIn(BaseModel):
    hours_delta: Optional[int] = None
    reason: Optional[str] = ""


@api.post("/admin/users/{uid}/adjust")
async def admin_adjust_user(uid: str, payload: UserAdjustIn, user: dict = Depends(get_current_user)):
    """Support can add/subtract hours as a goodwill gesture. Logged as an audit event."""
    _require_scope(user, "support")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if payload.hours_delta:
        await db.users.update_one({"id": uid}, {"$inc": {"hours_balance": int(payload.hours_delta)}})
        await db.audit_log.insert_one({
            "id": new_id(), "actor_id": user["id"], "actor_name": user.get("name"),
            "target_user_id": uid, "kind": "hours_adjust",
            "hours_delta": int(payload.hours_delta), "reason": (payload.reason or "")[:500],
            "created_at": now().isoformat(),
        })
    return {"ok": True}


# ---------- Customization (customization scope) ----------
# Site-wide settings persisted in a single doc. Public GET is available (below)
# so the landing pages can read feature flags; PUT requires customization scope.
DEFAULT_CUSTOMIZATION = {
    "hero_headline": "Grow with the world's most rigorously vetted talent.",
    "hero_subline":  "Job Atlas pairs individuals and companies on structured, milestone-linked engagements — hourly or full project delivery.",
    "cta_primary_label": "Browse talent",
    "cta_secondary_label": "See projects",
    "features": {
        "projects_workflow": True,
        "rate_nudges": True,
        "broadcasts_sse": True,
        "referral_program": True,
    },
    "support_email": "support@jobatlas.io",
    "support_hours": "Mon-Fri 09:00-19:00 UTC",
}


async def _get_customization_doc() -> dict:
    doc = await db.site_customization.find_one({"id": "site"}, {"_id": 0})
    if not doc:
        doc = {"id": "site", **DEFAULT_CUSTOMIZATION,
               "updated_at": now().isoformat(), "updated_by": None}
        await db.site_customization.insert_one(doc)
        doc.pop("_id", None)
    return doc


@api.get("/admin/customization")
async def admin_get_customization(user: dict = Depends(get_current_user)):
    _require_scope(user, "customization")
    return await _get_customization_doc()


@api.put("/admin/customization")
async def admin_put_customization(payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    _require_scope(user, "customization")
    allowed = {"hero_headline", "hero_subline", "cta_primary_label",
               "cta_secondary_label", "features", "support_email", "support_hours"}
    updates = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No editable fields provided")
    updates["updated_at"] = now().isoformat()
    updates["updated_by"] = user["id"]
    await db.site_customization.update_one(
        {"id": "site"}, {"$set": updates, "$setOnInsert": {"id": "site"}}, upsert=True
    )
    return await _get_customization_doc()


@api.get("/customization/public")
async def public_customization():
    """Public read-only view of the customization doc for the landing pages."""
    doc = await _get_customization_doc()
    # Only expose safe fields to the public.
    return {
        "hero_headline": doc.get("hero_headline"),
        "hero_subline": doc.get("hero_subline"),
        "cta_primary_label": doc.get("cta_primary_label"),
        "cta_secondary_label": doc.get("cta_secondary_label"),
        "features": doc.get("features") or {},
        "support_email": doc.get("support_email"),
        "support_hours": doc.get("support_hours"),
    }


# ---------- Profile verification approvals (moderation scope) ----------
class VerificationDecisionIn(BaseModel):
    notes: Optional[str] = ""


@api.get("/admin/verifications")
async def admin_list_pending_verifications(status: Optional[str] = "pending",
                                            user: dict = Depends(get_current_user)):
    if not (has_admin_scope(user, "moderation") or has_admin_scope(user, "support")):
        raise HTTPException(403, "Requires moderation or support scope")
    q = {}
    if status in ("pending", "verified", "rejected", "none"):
        q["verification_status"] = status
    items = await db.users.find(q, {"_id": 0, "password_hash": 0,
                                     "email_verification_token": 0}).sort("verification_submitted_at", 1).to_list(200)
    return {"items": items, "count": len(items)}


@api.post("/admin/verifications/{uid}/approve")
async def admin_approve_verification(uid: str, payload: VerificationDecisionIn,
                                       user: dict = Depends(get_current_user)):
    if not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Requires moderation scope")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    updates = {
        "verification_status": "verified",
        "verified_at": now().isoformat(),
        "verified_by": user["id"],
        "verification_notes": (payload.notes or "")[:500],
    }
    perks_granted = {}
    # KYB perks — only granted once per employer, tracked via kyb_perks_granted
    if target.get("role") == "employer" and not target.get("kyb_perks_granted"):
        updates["hero_placement"] = True
        updates["kyb_perks_granted"] = True
        updates["kyb_perks_granted_at"] = now().isoformat()
        perks_granted = {"hours_credited": 10, "hero_placement": True}
    await db.users.update_one({"id": uid}, {"$set": updates})
    if perks_granted:
        # Increment hours_balance separately (Mongo $inc + $set can't share a top-level path with the field)
        await db.users.update_one({"id": uid}, {"$inc": {"hours_balance": 10}})
        await db.audit_log.insert_one({
            "id": new_id(),
            "actor_id": user["id"], "actor_name": user.get("name"),
            "target_user_id": uid,
            "kind": "kyb_perks_granted",
            "perks": perks_granted,
            "created_at": now().isoformat(),
        })
    return {"ok": True, "user_id": uid, "status": "verified",
            "perks_granted": perks_granted}


@api.post("/admin/verifications/{uid}/reject")
async def admin_reject_verification(uid: str, payload: VerificationDecisionIn,
                                      user: dict = Depends(get_current_user)):
    if not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Requires moderation scope")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if not payload.notes:
        raise HTTPException(400, "Please include a rejection reason so the user can fix it")
    await db.users.update_one(
        {"id": uid},
        {"$set": {"verification_status": "rejected",
                  "verification_notes": payload.notes[:500],
                  "verification_decided_at": now().isoformat(),
                  "verified_by": user["id"]}},
    )
    return {"ok": True, "user_id": uid, "status": "rejected"}

