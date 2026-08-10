"""Admin routes — physically extracted from server.py.

All /admin/* endpoints live here. Shared helpers (_scan_and_record_rate_nudges,
_scheduler ref) still live in server.py — they're imported below at first-use time
to avoid an import cycle at module load.
"""
from typing import Any, Dict, List, Optional
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from deps import api, db, now, new_id, get_current_user, logger


class PayoutRunIn(BaseModel):
    period_start: str
    period_end: str
    currency: str = "usd"


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


@api.post("/admin/payouts/run")
async def admin_run_payouts(payload: PayoutRunIn, user: dict = Depends(get_current_user)):
    from server import _compute_talent_earnings  # late import to avoid cycle
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
