"""Revision workflow — employer requests changes on submitted deliverables.

Every request is immutable, visible to employer + talent + Job Atlas admins.
Auto-penalties on the talent kick in at 3 (amber) and 5 (red + dispute right).
Auto-flag on the employer kicks in at ≥5-revision escalations on 3+ different
talents within 60 days.

Endpoints exposed:
    POST /deliverables/{id}/request-revision   (employer)
    POST /deliverables/{id}/resubmit           (talent, replaces the old resubmit path)
    GET  /deliverables/{id}/revisions          (parties + admin-moderation)
    POST /revisions/{grievance_id_seed}/dispute (talent, only when >=5 revisions)
    GET  /admin/revisions                       (admin, moderation scope)
    POST /admin/revisions/{grievance_id}/rule   (admin, moderation)
    GET  /admin/employers-flagged               (admin, moderation)

The dispute fee is recorded as a payable on the *losing* side once an admin rules.
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from deps import api, db, new_id, now, get_current_user, has_admin_scope


# ---- Config knobs (env-overridable for tests) --------------------------------
REVIEW_FLAG_THRESHOLD   = int(os.environ.get("REVISION_REVIEW_THRESHOLD", "3"))
PENALTY_THRESHOLD       = int(os.environ.get("REVISION_PENALTY_THRESHOLD", "5"))
DISPUTE_FEE_USD         = float(os.environ.get("REVISION_DISPUTE_FEE_USD", "49"))
VISIBILITY_PENALTY      = int(os.environ.get("REVISION_VISIBILITY_PENALTY", "20"))
RATE_NUDGE_PENALTY_PCT  = float(os.environ.get("REVISION_RATE_NUDGE_PENALTY", "10"))
EMPLOYER_FLAG_TALENTS   = int(os.environ.get("EMPLOYER_FLAG_UNIQUE_TALENTS", "3"))
EMPLOYER_FLAG_WINDOW_D  = int(os.environ.get("EMPLOYER_FLAG_WINDOW_DAYS", "60"))


# ---- Payloads ---------------------------------------------------------------
class RequestRevisionIn(BaseModel):
    justification: str = Field(min_length=20, max_length=2000)
    priority: str = Field(default="minor")            # minor | major | blocking
    attachment_url: Optional[str] = ""


class ResubmitIn(BaseModel):
    link: str = Field(min_length=1, max_length=2000)
    hours_claimed: float = Field(ge=0, le=1000)
    notes: Optional[str] = ""
    file_ids: Optional[List[str]] = []


class DisputeIn(BaseModel):
    reason: str = Field(min_length=20, max_length=2000)


class RuleIn(BaseModel):
    ruling: str                                        # 'talent' | 'employer'
    notes: str = Field(min_length=10, max_length=2000)


# ---- Helpers ----------------------------------------------------------------
async def _apply_talent_penalty(*, talent_id: str, level: str,
                                 deliverable_id: str, engagement_id: str) -> None:
    """Set / lift talent-side flags after a threshold is crossed. Idempotent."""
    talent = await db.users.find_one({"id": talent_id}) or {}
    flags = list((talent.get("profile") or {}).get("revision_flags") or [])
    # Already flagged for this deliverable? Skip.
    if any(f.get("deliverable_id") == deliverable_id and f.get("level") == level
           and not f.get("cleared_at") for f in flags):
        return
    flags.append({
        "deliverable_id": deliverable_id, "engagement_id": engagement_id,
        "level": level, "at": now().isoformat(),
    })
    update = {"profile.revision_flags": flags}
    if level == "under_review":
        update["profile.under_review"] = True
    if level == "excessive_revisions":
        update["profile.excessive_revisions"] = True
        # Drop visibility score (default to 100 if missing).
        current = int((talent.get("profile") or {}).get("visibility_score") or 100)
        update["profile.visibility_score"] = max(0, current - VISIBILITY_PENALTY)
        # AI rate nudge -10% (persisted as a bias the /profile/suggest-rate
        # endpoint honours; existing endpoints already read it if present).
        update["profile.rate_bias_pct"] = -RATE_NUDGE_PENALTY_PCT
        # Trusted-partner ribbon is derived by /api/talent; we simply signal here
        # and the endpoint respects `excessive_revisions` (see marketplace hook).
    await db.users.update_one({"id": talent_id}, {"$set": update})


async def _maybe_flag_employer(employer_id: str) -> None:
    """After each escalation, count distinct talents this employer has taken to
    the PENALTY threshold in the last N days. If ≥ EMPLOYER_FLAG_TALENTS,
    stamp `abusive_pattern_flag` on the employer for admin review."""
    since = (now() - timedelta(days=EMPLOYER_FLAG_WINDOW_D)).isoformat()
    talents = set()
    async for r in db.revision_requests.find(
        {"employer_id": employer_id, "revision_number": {"$gte": PENALTY_THRESHOLD},
         "created_at": {"$gte": since}},
        {"talent_id": 1},
    ):
        if r.get("talent_id"):
            talents.add(r["talent_id"])
    if len(talents) >= EMPLOYER_FLAG_TALENTS:
        await db.users.update_one(
            {"id": employer_id},
            {"$set": {"profile.abusive_pattern_flag": True,
                      "profile.abusive_pattern_flagged_at": now().isoformat(),
                      "profile.abusive_pattern_talents": list(talents)}},
        )


async def _load_deliverable_and_authorize(deliverable_id: str, user: dict,
                                           allowed_roles: tuple) -> dict:
    d = await db.deliverables.find_one({"id": deliverable_id})
    if not d:
        raise HTTPException(404, "Deliverable not found")
    if user["id"] == d.get("employer_id") and "employer" in allowed_roles:
        return d
    if user["id"] == d.get("talent_id") and "talent" in allowed_roles:
        return d
    if user.get("role") == "admin" and has_admin_scope(user, "moderation") and "admin" in allowed_roles:
        return d
    raise HTTPException(403, "Not authorised for this deliverable")


# ---- Endpoints --------------------------------------------------------------
@api.post("/deliverables/{deliverable_id}/request-revision")
async def request_revision(deliverable_id: str, payload: RequestRevisionIn,
                            user: dict = Depends(get_current_user)):
    """Employer opens a new revision cycle on a submitted deliverable."""
    d = await _load_deliverable_and_authorize(deliverable_id, user, ("employer",))
    if d.get("status") not in ("submitted", "revision_resubmitted"):
        raise HTTPException(400, "Revision can only be requested on submitted or resubmitted work")
    if payload.priority not in ("minor", "major", "blocking"):
        raise HTTPException(400, "priority must be minor | major | blocking")

    existing_count = int(d.get("revision_count") or 0)
    revision_number = existing_count + 1

    rev = {
        "id": new_id(),
        "deliverable_id": deliverable_id,
        "engagement_id": d.get("engagement_id"),
        "employer_id": d["employer_id"],
        "talent_id": d["talent_id"],
        "revision_number": revision_number,
        "justification": payload.justification,
        "priority": payload.priority,
        "attachment_url": payload.attachment_url or "",
        "status": "open",
        "created_at": now().isoformat(),
        "resubmitted_at": "",
    }
    await db.revision_requests.insert_one(rev)
    await db.deliverables.update_one(
        {"id": deliverable_id},
        {"$set": {"status": "revision_requested",
                  "latest_revision_id": rev["id"]},
         "$inc": {"revision_count": 1}},
    )

    # Penalty ladder
    if revision_number >= PENALTY_THRESHOLD:
        await _apply_talent_penalty(
            talent_id=d["talent_id"], level="excessive_revisions",
            deliverable_id=deliverable_id, engagement_id=d.get("engagement_id"),
        )
        await _maybe_flag_employer(d["employer_id"])
    elif revision_number >= REVIEW_FLAG_THRESHOLD:
        await _apply_talent_penalty(
            talent_id=d["talent_id"], level="under_review",
            deliverable_id=deliverable_id, engagement_id=d.get("engagement_id"),
        )

    rev.pop("_id", None)
    return {"revision": rev, "revision_count": revision_number,
            "penalty_triggered": revision_number >= REVIEW_FLAG_THRESHOLD,
            "dispute_available": revision_number >= PENALTY_THRESHOLD}


@api.post("/deliverables/{deliverable_id}/resubmit")
async def resubmit_deliverable(deliverable_id: str, payload: ResubmitIn,
                                user: dict = Depends(get_current_user)):
    """Talent posts a new version in response to the latest revision request."""
    d = await _load_deliverable_and_authorize(deliverable_id, user, ("talent",))
    if d.get("status") != "revision_requested":
        raise HTTPException(400, "No open revision request on this deliverable")
    latest_id = d.get("latest_revision_id")
    if not latest_id:
        raise HTTPException(400, "No revision to respond to")
    await db.revision_requests.update_one(
        {"id": latest_id},
        {"$set": {"status": "resubmitted",
                  "resubmitted_at": now().isoformat(),
                  "resubmit_link": payload.link,
                  "resubmit_hours": payload.hours_claimed,
                  "resubmit_notes": payload.notes or "",
                  "resubmit_file_ids": payload.file_ids or []}},
    )
    await db.deliverables.update_one(
        {"id": deliverable_id},
        {"$set": {"status": "revision_resubmitted",
                  "link": payload.link,
                  "hours_claimed": float(payload.hours_claimed),
                  "resubmitted_at": now().isoformat()}},
    )
    return {"ok": True, "revision_id": latest_id}


@api.get("/deliverables/{deliverable_id}/revisions")
async def list_revisions(deliverable_id: str, user: dict = Depends(get_current_user)):
    """Full audit trail — visible to both parties and Job Atlas admins."""
    d = await _load_deliverable_and_authorize(deliverable_id, user, ("employer", "talent", "admin"))
    items = await db.revision_requests.find(
        {"deliverable_id": deliverable_id}, {"_id": 0},
    ).sort("revision_number", 1).to_list(50)
    return {
        "deliverable_id": deliverable_id,
        "revision_count": int(d.get("revision_count") or 0),
        "review_threshold": REVIEW_FLAG_THRESHOLD,
        "penalty_threshold": PENALTY_THRESHOLD,
        "dispute_available": int(d.get("revision_count") or 0) >= PENALTY_THRESHOLD,
        "dispute_fee_usd": DISPUTE_FEE_USD,
        "items": items,
    }


@api.post("/deliverables/{deliverable_id}/dispute")
async def raise_dispute(deliverable_id: str, payload: DisputeIn,
                         user: dict = Depends(get_current_user)):
    """Talent escalates once the deliverable has accumulated ≥ PENALTY_THRESHOLD
    revisions. Creates a grievance with the full revision thread attached and
    records a `dispute_fee` payable on the losing side (settled by the admin
    ruling)."""
    d = await _load_deliverable_and_authorize(deliverable_id, user, ("talent",))
    rc = int(d.get("revision_count") or 0)
    if rc < PENALTY_THRESHOLD:
        raise HTTPException(400, f"Dispute is available only after {PENALTY_THRESHOLD} revisions")
    # Prevent duplicate open disputes
    existing = await db.grievances.find_one(
        {"deliverable_id": deliverable_id, "kind": "revision_dispute",
         "status": {"$in": ["new", "in_review"]}},
    )
    if existing:
        raise HTTPException(400, "A dispute is already open on this deliverable")

    thread = await db.revision_requests.find(
        {"deliverable_id": deliverable_id}, {"_id": 0},
    ).sort("revision_number", 1).to_list(50)

    ref = f"REVDIS-{new_id()[:8].upper()}"
    doc = {
        "id": new_id(),
        "ref": ref,
        "kind": "revision_dispute",
        "deliverable_id": deliverable_id,
        "engagement_id": d.get("engagement_id"),
        "raised_by_id": user["id"],
        "raised_by_role": "talent",
        "employer_id": d["employer_id"],
        "talent_id": d["talent_id"],
        "reason": payload.reason,
        "revision_thread": thread,
        "status": "new",
        "created_at": now().isoformat(),
        "dispute_fee": {
            "amount_usd": DISPUTE_FEE_USD,
            "currency": "usd",
            "status": "pending",           # pending | owed_by_talent | owed_by_employer | waived
        },
    }
    await db.grievances.insert_one(doc)
    doc.pop("_id", None)
    return {"grievance": doc, "ref": ref}


@api.get("/admin/revisions")
async def admin_list_revisions(status: str = "", user: dict = Depends(get_current_user)):
    """Moderation queue for open revision cycles + disputes."""
    if not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Requires moderation scope")

    # Open revision cycles (not yet resubmitted)
    revs = await db.revision_requests.find(
        {"status": {"$in": ["open", "resubmitted"]}}, {"_id": 0},
    ).sort("created_at", -1).to_list(500)

    # Active disputes
    dispute_q = {"kind": "revision_dispute"}
    if status:
        dispute_q["status"] = status
    disputes = await db.grievances.find(dispute_q, {"_id": 0}).sort("created_at", -1).to_list(500)

    return {"revisions": revs, "disputes": disputes,
            "counts": {"open_revisions": len(revs), "disputes": len(disputes)}}


@api.post("/admin/revisions/{grievance_id}/rule")
async def admin_rule_dispute(grievance_id: str, payload: RuleIn,
                              user: dict = Depends(get_current_user)):
    """Admin decides the dispute. Ruling in favour of the talent reverses the
    visibility penalty and shifts the fee to the employer, and vice-versa."""
    if not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Requires moderation scope")
    if payload.ruling not in ("talent", "employer"):
        raise HTTPException(400, "ruling must be 'talent' or 'employer'")

    g = await db.grievances.find_one({"id": grievance_id, "kind": "revision_dispute"})
    if not g:
        raise HTTPException(404, "Dispute not found")
    if g.get("status") in ("resolved", "rejected"):
        raise HTTPException(400, "Dispute already ruled")

    fee_owner = "employer" if payload.ruling == "talent" else "talent"
    fee_status = f"owed_by_{fee_owner}"

    await db.grievances.update_one(
        {"id": grievance_id},
        {"$set": {"status": "resolved",
                  "ruling": payload.ruling,
                  "ruling_notes": payload.notes,
                  "ruled_by_id": user["id"],
                  "ruled_at": now().isoformat(),
                  "dispute_fee.status": fee_status}},
    )

    talent_id = g.get("talent_id")
    deliverable_id = g.get("deliverable_id")

    # Whichever way we ruled, close the open revision cycle on the deliverable
    # so it doesn't sit "revision_requested" forever after arbitration.
    if deliverable_id:
        await db.deliverables.update_one(
            {"id": deliverable_id, "status": {"$in": ["revision_requested", "revision_resubmitted"]}},
            {"$set": {"status": "dispute_resolved",
                      "dispute_ruling": payload.ruling,
                      "dispute_closed_at": now().isoformat()}},
        )

    if payload.ruling == "talent":
        # Reverse talent penalty on the disputed deliverable
        talent = await db.users.find_one({"id": talent_id}) or {}
        prof = talent.get("profile") or {}
        flags = [f for f in (prof.get("revision_flags") or [])
                 if f.get("deliverable_id") != g.get("deliverable_id")]
        # Reset visibility if no other excessive flags remain
        still_excessive = any(f.get("level") == "excessive_revisions" for f in flags)
        update = {"profile.revision_flags": flags,
                  "profile.excessive_revisions": still_excessive,
                  "profile.under_review": any(f.get("level") == "under_review" for f in flags)}
        if not still_excessive:
            update["profile.visibility_score"] = 100
            update["profile.rate_bias_pct"] = 0
        await db.users.update_one({"id": talent_id}, {"$set": update})

    return {"ok": True, "ruling": payload.ruling, "fee_status": fee_status,
            "fee_usd": DISPUTE_FEE_USD}


@api.get("/admin/employers-flagged")
async def admin_flagged_employers(user: dict = Depends(get_current_user)):
    """List of employers auto-flagged for revision abuse (≥5 revisions on
    ≥3 distinct talents within the rolling 60-day window)."""
    if not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Requires moderation scope")
    items = await db.users.find(
        {"role": "employer", "profile.abusive_pattern_flag": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "profile": 1},
    ).to_list(500)
    return {"items": items, "count": len(items)}


@api.get("/deliverables/{deliverable_id}/revision-summary")
async def revision_summary(deliverable_id: str, user: dict = Depends(get_current_user)):
    """Lightweight probe the UI uses to decide whether to show buttons."""
    d = await _load_deliverable_and_authorize(deliverable_id, user, ("employer", "talent", "admin"))
    return {
        "revision_count": int(d.get("revision_count") or 0),
        "status": d.get("status"),
        "review_threshold": REVIEW_FLAG_THRESHOLD,
        "penalty_threshold": PENALTY_THRESHOLD,
        "dispute_fee_usd": DISPUTE_FEE_USD,
        "latest_revision_id": d.get("latest_revision_id"),
    }
