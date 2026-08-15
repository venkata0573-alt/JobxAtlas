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
from fastapi import Depends, HTTPException, Request
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
# Talent recovery playbook: how many clean, revision-free approvals in a row
# lift each penalty tier. Reject resets the streak to 0.
RECOVERY_UNDER_REVIEW   = int(os.environ.get("REVISION_RECOVERY_UNDER_REVIEW", "3"))
RECOVERY_EXCESSIVE      = int(os.environ.get("REVISION_RECOVERY_EXCESSIVE", "5"))
# How long a recovered talent keeps the "Proven Reliable" chip.
PROVEN_RELIABLE_DAYS    = int(os.environ.get("PROVEN_RELIABLE_DAYS", "90"))


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
    # Stamp grievance id on the deliverable so the UI can look up the fee card
    # without a broader list endpoint.
    await db.deliverables.update_one(
        {"id": deliverable_id},
        {"$set": {"dispute_grievance_id": doc["id"], "dispute_ref": ref,
                  "dispute_opened_at": doc["created_at"]}},
    )
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
                  "dispute_fee.status": fee_status,
                  "dispute_fee.payment_status": "unpaid"}},
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

    # Notify the losing party via email + inbox so they can pay the fee.
    payer_id = g.get("employer_id") if payload.ruling == "talent" else talent_id
    try:
        payer = await db.users.find_one({"id": payer_id}) or {}
        payer_email = payer.get("email") or ""
        if payer_email:
            # Lazy import to avoid a hard mailer dep in this module
            from mailer import send_email  # noqa: WPS433
            await send_email(
                to=payer_email,
                subject=f"Job Atlas · Arbitration fee due · {g.get('ref')}",
                html=(
                    f"<p>Hi {payer.get('name') or ''},</p>"
                    f"<p>Your revision dispute <b>{g.get('ref')}</b> has been ruled in favour of the "
                    f"<b>{payload.ruling}</b>. A <b>${DISPUTE_FEE_USD:.0f}</b> arbitration fee is now owed.</p>"
                    f"<p>You can settle it inside your Job Atlas dashboard under Grievances, or use the "
                    f"secure Stripe link that will appear on the case card.</p>"
                    f"<p>Ruling note: <em>{payload.notes}</em></p>"
                    f"<p>— Job Atlas Trust &amp; Safety</p>"
                ),
            )
    except Exception as _mail_err:
        # Best-effort — never let a mailer failure block the ruling itself.
        try:
            import logging as _lg
            _lg.getLogger(__name__).warning(
                "[dispute-fee] email to %s failed: %s", payer_id, _mail_err,
            )
        except Exception:
            pass

    await db.notifications.insert_one({
        "id": new_id(), "user_id": payer_id,
        "type": "dispute_fee_due",
        "grievance_id": grievance_id, "ref": g.get("ref"),
        "amount_usd": DISPUTE_FEE_USD,
        "message": f"Dispute {g.get('ref')} was ruled in favour of the {payload.ruling}. ${DISPUTE_FEE_USD:.0f} arbitration fee due.",
        "created_at": now().isoformat(), "read": False,
    })

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


@api.get("/admin/revisions/refund-analytics")
async def admin_refund_analytics(user: dict = Depends(get_current_user)):
    """30-day daily series of paid vs refunded arbitration fees, plus a rolling
    refund-rate so Trust & Safety can spot runaway refund patterns early."""
    if not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Requires moderation scope")

    start = (now() - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    buckets: dict = {}
    for i in range(30):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        buckets[d] = {"date": d, "paid": 0, "refunded": 0}

    def _fmt(ts):
        if not ts:
            return None
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            key = dt.strftime("%Y-%m-%d")
            return key if key in buckets else None
        except Exception:
            return None

    start_iso = start.isoformat()

    # Paid: any dispute_fee_transactions row that hit `paid` in the window.
    async for tx in db.dispute_fee_transactions.find(
        {"paid_at": {"$gte": start_iso}},
        {"_id": 0, "paid_at": 1},
    ):
        k = _fmt(tx.get("paid_at"))
        if k:
            buckets[k]["paid"] += 1

    # Refunded: same rows once they later transitioned to refunded.
    async for tx in db.dispute_fee_transactions.find(
        {"refunded_at": {"$gte": start_iso}},
        {"_id": 0, "refunded_at": 1},
    ):
        k = _fmt(tx.get("refunded_at"))
        if k:
            buckets[k]["refunded"] += 1

    series = list(buckets.values())
    for r in series:
        r["refund_rate_pct"] = round(r["refunded"] / r["paid"] * 100, 1) if r["paid"] else 0

    total_paid = sum(r["paid"] for r in series)
    total_refunded = sum(r["refunded"] for r in series)
    rolling_rate = round(total_refunded / total_paid * 100, 1) if total_paid else 0
    alert_threshold = int(os.environ.get("REFUND_ALERT_THRESHOLD_PCT", "20"))

    return {
        "series": series,
        "totals": {
            "paid_30d": total_paid,
            "refunded_30d": total_refunded,
            "refund_rate_pct": rolling_rate,
            "amount_refunded_usd": round(total_refunded * DISPUTE_FEE_USD, 2),
        },
        "alert": {"threshold_pct": alert_threshold,
                  "breached": rolling_rate >= alert_threshold and total_paid > 0},
        "as_of": now().isoformat(),
    }


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


# ---- Talent Recovery Playbook ------------------------------------------------
async def _record_clean_approval(talent_id: str) -> None:
    """Called from _act_deliverable on APPROVE (revision_count==0). Increments
    the talent's clean-streak; auto-lifts under_review at RECOVERY_UNDER_REVIEW
    and excessive_revisions at RECOVERY_EXCESSIVE. Never touches active
    revision_flags entries — those stay in the audit log."""
    talent = await db.users.find_one({"id": talent_id}) or {}
    prof = talent.get("profile") or {}
    streak = int(prof.get("clean_streak") or 0) + 1
    updates: dict = {"profile.clean_streak": streak,
                     "profile.last_clean_approval_at": now().isoformat()}
    if prof.get("excessive_revisions") and streak >= RECOVERY_EXCESSIVE:
        updates["profile.excessive_revisions"] = False
        updates["profile.visibility_score"] = 100
        updates["profile.rate_bias_pct"] = 0
        updates["profile.recovery_cleared_at"] = now().isoformat()
        streak = 0
        updates["profile.clean_streak"] = 0
    elif prof.get("under_review") and not prof.get("excessive_revisions") and streak >= RECOVERY_UNDER_REVIEW:
        updates["profile.under_review"] = False
        updates["profile.recovery_cleared_at"] = now().isoformat()
        streak = 0
        updates["profile.clean_streak"] = 0
    await db.users.update_one({"id": talent_id}, {"$set": updates})


async def _reset_clean_streak(talent_id: str) -> None:
    await db.users.update_one({"id": talent_id},
                               {"$set": {"profile.clean_streak": 0,
                                         "profile.last_streak_reset_at": now().isoformat()}})


@api.get("/talent/me/recovery-status")
async def my_recovery_status(user: dict = Depends(get_current_user)):
    """Talent-facing progress card: how many clean approvals until their
    penalty is lifted, plus the raw flags."""
    if user.get("role") != "talent":
        raise HTTPException(403, "Talent only")
    prof = (user.get("profile") or {})
    streak = int(prof.get("clean_streak") or 0)
    if prof.get("excessive_revisions"):
        need = RECOVERY_EXCESSIVE
        target = "excessive_revisions"
    elif prof.get("under_review"):
        need = RECOVERY_UNDER_REVIEW
        target = "under_review"
    else:
        return {"has_penalty": False, "clean_streak": streak,
                "target": None, "needed": 0, "progress_pct": 0}
    return {
        "has_penalty": True,
        "target": target,
        "clean_streak": streak,
        "needed": need,
        "remaining": max(need - streak, 0),
        "progress_pct": min(int(streak / need * 100), 100),
        "visibility_score": int(prof.get("visibility_score") or 100),
        "rate_bias_pct": float(prof.get("rate_bias_pct") or 0),
    }


# ---- Fee Collection Flow (Stripe checkout for the losing party) -------------
class FeePayIn(BaseModel):
    origin_url: str = Field(default="")


def _fee_recipient(g: dict) -> Optional[str]:
    """Return the user_id that owes the fee based on grievance state."""
    status = (g.get("dispute_fee") or {}).get("status") or ""
    if status == "owed_by_talent":
        return g.get("talent_id")
    if status == "owed_by_employer":
        return g.get("employer_id")
    return None


@api.post("/grievances/{grievance_id}/pay-fee")
async def pay_dispute_fee(grievance_id: str, payload: FeePayIn,
                           request: Request,
                           user: dict = Depends(get_current_user)):
    """The losing party creates a Stripe Checkout Session to settle the
    $DISPUTE_FEE_USD arbitration fee. Idempotent — reuses the existing session
    while payment is pending."""
    import stripe as _stripe
    _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not _stripe.api_key:
        raise HTTPException(500, "Stripe not configured")

    g = await db.grievances.find_one({"id": grievance_id, "kind": "revision_dispute"})
    if not g:
        raise HTTPException(404, "Dispute not found")
    if g.get("status") != "resolved":
        raise HTTPException(400, "Dispute is not resolved yet")

    payer_id = _fee_recipient(g)
    if not payer_id:
        raise HTTPException(400, "Fee has no owner (waived?)")
    if payer_id != user["id"]:
        raise HTTPException(403, "Only the losing party can pay this fee")

    fee = g.get("dispute_fee") or {}
    if fee.get("payment_status") == "paid":
        return {"already_paid": True, "amount_usd": fee.get("amount_usd", DISPUTE_FEE_USD)}

    # Reuse an open session if present
    existing_session_id = fee.get("stripe_session_id")
    if existing_session_id:
        try:
            s = _stripe.checkout.Session.retrieve(existing_session_id)
            status = s.get("status") if isinstance(s, dict) else getattr(s, "status", None)
            if status not in ("complete", "expired"):
                return {"checkout_url": s.url, "session_id": s.id}
            if status == "expired":
                # Clean up the stale row so the sync log is accurate.
                await db.dispute_fee_transactions.update_one(
                    {"session_id": existing_session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"status": "expired", "payment_status": "expired",
                              "expired_at": now().isoformat()}},
                )
        except Exception:
            pass  # fall through and create a fresh session

    origin = (payload.origin_url or "").rstrip("/") or _origin_from_request(request)
    amount_cents = int(round(float(fee.get("amount_usd") or DISPUTE_FEE_USD) * 100))

    session = _stripe.checkout.Session.create(
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Job Atlas · Dispute arbitration fee · {g.get('ref')}"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{origin}/grievance/{grievance_id}?fee=paid&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/grievance/{grievance_id}?fee=cancelled",
        customer_email=user.get("email"),
        metadata={"kind": "dispute_fee", "grievance_id": grievance_id,
                  "payer_id": user["id"], "grievance_ref": g.get("ref", "")},
    )

    await db.grievances.update_one(
        {"id": grievance_id},
        {"$set": {"dispute_fee.stripe_session_id": session.id,
                  "dispute_fee.payment_status": "pending",
                  "dispute_fee.session_created_at": now().isoformat()}},
    )
    await db.dispute_fee_transactions.insert_one({
        "id": new_id(), "grievance_id": grievance_id, "session_id": session.id,
        "payer_id": user["id"], "amount_cents": amount_cents,
        "status": "initiated", "payment_status": "pending",
        "created_at": now().isoformat(),
    })
    return {"checkout_url": session.url, "session_id": session.id,
            "amount_usd": amount_cents / 100.0}


@api.get("/grievances/{grievance_id}/fee-status")
async def dispute_fee_status(grievance_id: str, user: dict = Depends(get_current_user)):
    g = await db.grievances.find_one(
        {"id": grievance_id, "kind": "revision_dispute"},
        {"_id": 0, "dispute_fee": 1, "talent_id": 1, "employer_id": 1,
         "status": 1, "ruling": 1, "ref": 1},
    )
    if not g:
        raise HTTPException(404, "Not found")
    # Parties + admin can see
    if user["id"] not in (g.get("talent_id"), g.get("employer_id")) and not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Not authorised")
    fee = g.get("dispute_fee") or {}
    return {
        "ref": g.get("ref"),
        "status": g.get("status"),
        "ruling": g.get("ruling"),
        "fee": {
            "amount_usd": fee.get("amount_usd", DISPUTE_FEE_USD),
            "status": fee.get("status"),
            "payment_status": fee.get("payment_status", "unpaid"),
            "paid_at": fee.get("paid_at"),
            "owed_by": _fee_recipient(g),
        },
    }


def _origin_from_request(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}" if host else ""


async def mark_dispute_fee_paid(session_id: str) -> None:
    """Stripe webhook helper — called from server.py when checkout.session.completed
    fires with metadata.kind='dispute_fee'."""
    tx = await db.dispute_fee_transactions.find_one({"session_id": session_id})
    if not tx or tx.get("payment_status") == "paid":
        return
    now_iso = now().isoformat()
    # Fetch the underlying payment_intent so admins can later refund with a single click.
    payment_intent_id = None
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        if _stripe.api_key:
            s = _stripe.checkout.Session.retrieve(session_id)
            payment_intent_id = s.get("payment_intent") if isinstance(s, dict) else getattr(s, "payment_intent", None)
    except Exception:
        pass
    await db.dispute_fee_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"status": "completed", "payment_status": "paid",
                  "paid_at": now_iso, "payment_intent_id": payment_intent_id}},
    )
    await db.grievances.update_one(
        {"id": tx["grievance_id"]},
        {"$set": {"dispute_fee.payment_status": "paid",
                  "dispute_fee.paid_at": now_iso,
                  "dispute_fee.paid_by_id": tx["payer_id"],
                  "dispute_fee.payment_intent_id": payment_intent_id}},
    )


class RefundIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


@api.post("/admin/grievances/{grievance_id}/refund-fee")
async def admin_refund_fee(grievance_id: str, payload: RefundIn,
                            user: dict = Depends(get_current_user)):
    """One-click refund of a paid arbitration fee. Admin-moderation only. If
    new evidence surfaces after the ruling, we credit the payer's card via
    `stripe.Refund.create(payment_intent=...)` and stamp the audit trail."""
    if not has_admin_scope(user, "moderation"):
        raise HTTPException(403, "Requires moderation scope")

    g = await db.grievances.find_one({"id": grievance_id, "kind": "revision_dispute"})
    if not g:
        raise HTTPException(404, "Dispute not found")
    fee = g.get("dispute_fee") or {}
    if fee.get("payment_status") == "refunded":
        raise HTTPException(400, "Fee already refunded")
    if fee.get("payment_status") != "paid":
        raise HTTPException(400, "Fee has not been paid yet")

    pi_id = fee.get("payment_intent_id")
    # If the webhook lookup missed the payment_intent, try to fetch it now.
    if not pi_id and fee.get("stripe_session_id"):
        try:
            import stripe as _stripe
            _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
            s = _stripe.checkout.Session.retrieve(fee["stripe_session_id"])
            pi_id = s.get("payment_intent") if isinstance(s, dict) else getattr(s, "payment_intent", None)
        except Exception:
            pass
    if not pi_id:
        raise HTTPException(400, "No payment_intent on file — cannot refund automatically")

    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        if not _stripe.api_key:
            raise HTTPException(500, "Stripe not configured")
        refund = _stripe.Refund.create(
            payment_intent=pi_id,
            reason="requested_by_customer",
            metadata={"grievance_id": grievance_id, "admin_id": user["id"],
                      "grievance_ref": g.get("ref", "")},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Stripe refund failed: {str(e)[:250]}")

    refund_id = refund.get("id") if isinstance(refund, dict) else getattr(refund, "id", None)
    now_iso = now().isoformat()
    await db.grievances.update_one(
        {"id": grievance_id},
        {"$set": {"dispute_fee.payment_status": "refunded",
                  "dispute_fee.refund_id": refund_id,
                  "dispute_fee.refunded_at": now_iso,
                  "dispute_fee.refunded_by_id": user["id"],
                  "dispute_fee.refund_reason": payload.reason}},
    )
    await db.dispute_fee_transactions.update_one(
        {"grievance_id": grievance_id, "payment_status": "paid"},
        {"$set": {"payment_status": "refunded", "refund_id": refund_id,
                  "refunded_at": now_iso, "refund_reason": payload.reason,
                  "refunded_by_id": user["id"]}},
    )

    # Notify the payer
    payer_id = fee.get("paid_by_id")
    try:
        payer = await db.users.find_one({"id": payer_id}) or {}
        if payer.get("email"):
            from mailer import send_email  # noqa: WPS433
            await send_email(
                to=payer["email"],
                subject=f"Job Atlas · Arbitration fee refunded · {g.get('ref')}",
                html=(
                    f"<p>Hi {payer.get('name') or ''},</p>"
                    f"<p>Good news — the arbitration fee for dispute <b>{g.get('ref')}</b> has been "
                    f"refunded to your card. It should appear within 5–10 business days.</p>"
                    f"<p>Reason: <em>{payload.reason}</em></p>"
                    f"<p>— Job Atlas Trust &amp; Safety</p>"
                ),
            )
    except Exception as _mail_err:
        try:
            import logging as _lg
            _lg.getLogger(__name__).warning("[refund] email to %s failed: %s", payer_id, _mail_err)
        except Exception:
            pass

    if payer_id:
        await db.notifications.insert_one({
            "id": new_id(), "user_id": payer_id,
            "type": "dispute_fee_refunded",
            "grievance_id": grievance_id, "ref": g.get("ref"),
            "amount_usd": fee.get("amount_usd", DISPUTE_FEE_USD),
            "message": f"Arbitration fee for {g.get('ref')} refunded. Reason: {payload.reason}",
            "created_at": now_iso, "read": False,
        })

    return {"ok": True, "refund_id": refund_id, "refunded_at": now_iso,
            "amount_usd": fee.get("amount_usd", DISPUTE_FEE_USD)}


# ---- Reputation Boost Ribbon ("Proven Reliable") ----------------------------
def is_proven_reliable(profile: dict) -> bool:
    """A talent earns the ribbon after clearing at least one revision-recovery
    cycle. The chip fades PROVEN_RELIABLE_DAYS after the recovery timestamp."""
    ts = (profile or {}).get("recovery_cleared_at")
    if not ts:
        return False
    try:
        cleared = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if cleared.tzinfo is None:
            cleared = cleared.replace(tzinfo=timezone.utc)
        return (now() - cleared).days <= PROVEN_RELIABLE_DAYS
    except Exception:
        return False

