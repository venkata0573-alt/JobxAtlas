"""Project delivery workspace + milestone billing.

A converted project lead becomes a `project` doc holding:
- 5 PMI phase gates (Initiate → Plan → Execute → Monitor & Control → Close)
- Weekly variance snapshots (planned vs actual)
- A risk register
- A RACI matrix (auto-seeded from the assigned team)
- Fixed-price milestones (25% kickoff + 25% x 3 major milestones by default)

Access rules:
- Any admin scope can read/list projects.
- The linked employer (project.employer_id) can read + progress phases + add variance/risks.
- superadmin can convert a lead → project. `finance` can mark milestones invoiced/paid.
"""
from typing import Any, Dict, List, Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from deps import api, db, now, new_id, get_current_user, has_admin_scope


# ---------- Constants ----------
DEFAULT_PHASES = [
    {"id": "initiate",  "name": "Initiate",           "gate": "Charter signed",
     "deliverables": ["Business case", "Stakeholder register", "Charter"]},
    {"id": "plan",      "name": "Plan",               "gate": "Baseline approved",
     "deliverables": ["Scope statement", "WBS", "Schedule", "Cost baseline", "Risk register v1"]},
    {"id": "execute",   "name": "Execute",            "gate": "Weekly delivery cadence",
     "deliverables": ["Deployables", "Stand-ups", "Change requests"]},
    {"id": "monitor",   "name": "Monitor & Control",  "gate": "Variance under 10%",
     "deliverables": ["Variance reports", "Risk reviews", "Quality checks"]},
    {"id": "close",     "name": "Close",              "gate": "Sign-off + lessons",
     "deliverables": ["Handover", "Retrospective", "Final invoice"]},
]

DEFAULT_MILESTONE_STRUCTURE = [
    {"name": "Kickoff",           "percent": 25, "sequence": 1},
    {"name": "Phase 1 Delivery",  "percent": 25, "sequence": 2},
    {"name": "Phase 2 Delivery",  "percent": 25, "sequence": 3},
    {"name": "Final Sign-off",    "percent": 25, "sequence": 4},
]


# ---------- Helpers ----------
def _can_view_project(user: dict, project: dict) -> bool:
    if not user or not project:
        return False
    if user.get("role") == "admin":
        return True
    if user.get("role") == "employer" and project.get("employer_id") == user.get("id"):
        return True
    return False


def _can_edit_project(user: dict, project: dict) -> bool:
    """Anyone who can view + one of: admin (any scope), or the linked employer."""
    return _can_view_project(user, project)


async def _load_project_or_404(project_id: str, user: dict) -> dict:
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    if not _can_view_project(user, p):
        raise HTTPException(403, "You cannot view this project")
    return p


def _seed_raci(assigned_team: List[dict]) -> List[dict]:
    """First-pass RACI table for the standard 5 deliverables. Talent[0] is
    Accountable, the rest are Responsible, external stakeholder Consulted, admin Informed."""
    activities = [
        "Charter approval", "Scope + WBS", "Sprint delivery",
        "Weekly variance review", "Final sign-off",
    ]
    rows = []
    for act in activities:
        row = {"activity": act, "assignments": {}}
        for i, seat in enumerate(assigned_team or []):
            if not seat.get("talent_name"):
                continue
            key = seat["talent_name"]
            row["assignments"][key] = "A" if i == 0 else "R"
        row["assignments"]["Employer Sponsor"] = "C"
        row["assignments"]["Job Atlas PM"] = "I"
        rows.append(row)
    return rows


# ---------- Models ----------
class ConvertLeadIn(BaseModel):
    employer_id: Optional[str] = None  # If provided, links to an existing employer user
    currency: str = "usd"


class PhaseUpdateIn(BaseModel):
    status: str  # not_started | in_progress | complete
    signed_off_by: Optional[str] = ""


class VarianceIn(BaseModel):
    week_start: str                       # ISO date
    planned_hours: float
    actual_hours: float
    planned_cost: float
    actual_cost: float
    notes: Optional[str] = ""


class RiskIn(BaseModel):
    title: str
    description: Optional[str] = ""
    likelihood: str = "M"    # L | M | H
    impact: str = "M"        # L | M | H
    mitigation: Optional[str] = ""
    owner: Optional[str] = ""
    status: str = "open"     # open | mitigated | closed


class RaciIn(BaseModel):
    rows: List[Dict[str, Any]]


class MilestoneIn(BaseModel):
    name: str
    description: Optional[str] = ""
    amount: Optional[float] = None
    percent: Optional[float] = None
    due_date: Optional[str] = ""
    sequence: Optional[int] = None


# ---------- Convert a lead → project ----------
@api.post("/admin/project-leads/{lead_id}/convert")
async def convert_lead_to_project(lead_id: str, payload: ConvertLeadIn,
                                   user: dict = Depends(get_current_user)):
    if not has_admin_scope(user, "superadmin"):
        raise HTTPException(403, "Requires superadmin scope")
    lead = await db.project_leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead.get("converted_project_id"):
        raise HTTPException(400, "Lead already converted")

    template_id = lead.get("template_id")
    total_budget = float(lead.get("estimated_total_cost") or 0)
    monthly_budget = float(lead.get("estimated_monthly_cost") or 0)
    duration = int(lead.get("duration_months") or 6)
    assigned_team = lead.get("assigned_team") or []

    # Resolve employer_id: prefer explicit payload, else match on contact_email
    employer_id = payload.employer_id
    if not employer_id and lead.get("contact_email"):
        u = await db.users.find_one({"email": lead["contact_email"], "role": "employer"}, {"id": 1, "_id": 0})
        if u:
            employer_id = u["id"]

    project_id = new_id()
    phases = []
    for i, ph in enumerate(DEFAULT_PHASES):
        phases.append({
            **ph, "seq": i + 1,
            "status": "in_progress" if i == 0 else "not_started",
            "started_at": now().isoformat() if i == 0 else None,
            "completed_at": None, "signed_off_by": None,
        })

    project = {
        "id": project_id, "lead_id": lead_id,
        "template_id": template_id, "template_title": lead.get("template_title"),
        "industry": lead.get("industry"),
        "company_name": lead.get("company_name"),
        "contact_name": lead.get("contact_name"),
        "contact_email": lead.get("contact_email"),
        "employer_id": employer_id,
        "duration_months": duration,
        "monthly_budget": monthly_budget,
        "total_budget": total_budget,
        # Margin snapshot (transparent to admins; not shown to employer)
        "total_talent_cost": float(lead.get("total_talent_cost") or 0),
        "total_margin": float(lead.get("total_margin") or 0),
        "blended_margin_pct": float(lead.get("blended_margin_pct") or 0),
        "currency": payload.currency,
        "assigned_team": assigned_team,
        "phases": phases,
        "raci": _seed_raci(assigned_team),
        "status": "active",
        "created_at": now().isoformat(),
        "created_by": user["id"],
        "updated_at": now().isoformat(),
    }
    await db.projects.insert_one(project)

    # Auto-generate default milestones (25% x 4) tied to phases 1/2/3/close
    if total_budget > 0:
        for spec in DEFAULT_MILESTONE_STRUCTURE:
            amt = round(total_budget * spec["percent"] / 100.0, 2)
            await db.project_milestones.insert_one({
                "id": new_id(), "project_id": project_id,
                "name": spec["name"], "description": "",
                "percent": spec["percent"], "amount": amt,
                "due_date": "", "sequence": spec["sequence"],
                "status": "pending", "invoice_id": None,
                "created_at": now().isoformat(),
            })

    await db.project_leads.update_one(
        {"id": lead_id},
        {"$set": {"status": "converted", "converted_project_id": project_id,
                  "converted_at": now().isoformat()}},
    )
    project.pop("_id", None)
    return {"ok": True, "project": project}


# ---------- List / detail ----------
@api.get("/admin/project-leads")
async def admin_list_leads(user: dict = Depends(get_current_user)):
    if not (has_admin_scope(user, "support") or has_admin_scope(user, "superadmin")):
        raise HTTPException(403, "Requires support or superadmin scope")
    items = await db.project_leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": items, "count": len(items)}


@api.get("/projects/mine")
async def list_my_projects(user: dict = Depends(get_current_user)):
    """Employer sees their linked projects; admins with any scope see all."""
    if user.get("role") == "admin":
        items = await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    elif user.get("role") == "employer":
        items = await db.projects.find({"employer_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    else:
        items = []
    return {"items": items, "count": len(items)}


@api.get("/projects/workspace/{project_id}")
async def get_project_workspace(project_id: str, user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    variances = await db.project_variances.find(
        {"project_id": project_id}, {"_id": 0}
    ).sort("week_start", 1).to_list(200)
    risks = await db.project_risks.find(
        {"project_id": project_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    milestones = await db.project_milestones.find(
        {"project_id": project_id}, {"_id": 0}
    ).sort("sequence", 1).to_list(50)
    invoices = await db.project_invoices.find(
        {"project_id": project_id}, {"_id": 0}
    ).sort("issued_at", -1).to_list(50)

    # Rollups for the dashboard header
    total_planned_hours = sum(v.get("planned_hours", 0) for v in variances)
    total_actual_hours  = sum(v.get("actual_hours", 0) for v in variances)
    hours_var_pct = 0
    if total_planned_hours > 0:
        hours_var_pct = round(((total_actual_hours - total_planned_hours) / total_planned_hours) * 100, 1)
    total_planned_cost = sum(v.get("planned_cost", 0) for v in variances)
    total_actual_cost  = sum(v.get("actual_cost", 0) for v in variances)
    cost_var_pct = 0
    if total_planned_cost > 0:
        cost_var_pct = round(((total_actual_cost - total_planned_cost) / total_planned_cost) * 100, 1)
    billed = sum(m.get("amount", 0) for m in milestones if m.get("status") in ("invoiced", "paid"))
    paid = sum(m.get("amount", 0) for m in milestones if m.get("status") == "paid")
    total_budget = float(project.get("total_budget") or 0)
    remaining = round(total_budget - billed, 2)

    return {
        "project": project,
        "variances": variances,
        "risks": risks,
        "milestones": milestones,
        "invoices": invoices,
        "rollups": {
            "hours_variance_pct": hours_var_pct,
            "cost_variance_pct": cost_var_pct,
            "billed": round(billed, 2),
            "paid": round(paid, 2),
            "remaining": remaining,
            "total_budget": total_budget,
        },
    }


# ---------- Phase updates ----------
@api.patch("/projects/workspace/{project_id}/phases/{phase_id}")
async def update_phase(project_id: str, phase_id: str, payload: PhaseUpdateIn,
                        user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    if not _can_edit_project(user, project):
        raise HTTPException(403, "You cannot edit this project")
    if payload.status not in ("not_started", "in_progress", "complete"):
        raise HTTPException(400, "Invalid phase status")
    phases = project.get("phases") or []
    updated = False
    for ph in phases:
        if ph.get("id") == phase_id:
            ph["status"] = payload.status
            if payload.status == "in_progress" and not ph.get("started_at"):
                ph["started_at"] = now().isoformat()
            if payload.status == "complete":
                ph["completed_at"] = now().isoformat()
                ph["signed_off_by"] = payload.signed_off_by or user.get("name") or user.get("email")
            updated = True
            break
    if not updated:
        raise HTTPException(404, "Phase not found on this project")
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"phases": phases, "updated_at": now().isoformat()}},
    )
    return {"ok": True, "phases": phases}


VARIANCE_ALERT_THRESHOLD_PCT = 10


def _variance_email_html(*, company: str, week: str, hours_var: float,
                          cost_var: float, notes: str, workspace_url: str) -> str:
    tone = "#B03A2E" if abs(hours_var) >= 10 or abs(cost_var) >= 10 else "#C79A3B"
    hours_line = f"Hours are <b style='color:{tone}'>{'+' if hours_var > 0 else ''}{hours_var}%</b> versus plan."
    cost_line  = f"Cost is <b style='color:{tone}'>{'+' if cost_var > 0 else ''}{cost_var}%</b> versus plan."
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#FAF9F6;font-family:Georgia,serif;color:#0B1B2B;">
<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #ddd;padding:32px;">
  <p style="letter-spacing:.2em;font-size:11px;color:{tone};margin:0 0 8px">VARIANCE ALERT · JOB ATLAS</p>
  <h1 style="font-size:22px;margin:0 0 12px">{company} — week of {week}</h1>
  <p style="font-size:14px;line-height:1.5;margin:0 0 12px">{hours_line}</p>
  <p style="font-size:14px;line-height:1.5;margin:0 0 12px">{cost_line}</p>
  {f'<p style="font-size:13px;color:#555;background:#FAF9F6;padding:10px;border-left:3px solid {tone}">{notes}</p>' if notes else ''}
  <p style="margin:24px 0 0"><a href="{workspace_url}" style="background:#0B1B2B;color:#fff;padding:10px 16px;text-decoration:none;display:inline-block">Open workspace →</a></p>
  <p style="font-size:11px;color:#999;margin-top:24px">You received this because a project variance week exceeded ±10%. Log in and open the workspace for the full picture.</p>
</div></body></html>"""


async def _maybe_fire_variance_alert(project: dict, variance: dict) -> Optional[dict]:
    """If the just-logged variance week breached the threshold on hours OR cost,
    write an alert doc + fire an email to the linked employer. Returns the
    alert doc when fired, else None."""
    import os
    hours_var = float(variance.get("hours_variance_pct") or 0)
    cost_var  = float(variance.get("cost_variance_pct") or 0)
    if abs(hours_var) < VARIANCE_ALERT_THRESHOLD_PCT and abs(cost_var) < VARIANCE_ALERT_THRESHOLD_PCT:
        return None
    alert = {
        "id": new_id(),
        "kind": "variance_breach",
        "project_id": project["id"],
        "project_company": project.get("company_name"),
        "employer_id": project.get("employer_id"),
        "week_start": variance.get("week_start"),
        "hours_variance_pct": hours_var,
        "cost_variance_pct": cost_var,
        "notes": (variance.get("notes") or "")[:500],
        "severity": "high" if max(abs(hours_var), abs(cost_var)) >= 20 else "medium",
        "read": False,
        "email_sent": False,
        "created_at": now().isoformat(),
    }
    await db.project_alerts.insert_one(alert)
    # Fire email (best-effort — never blocks the API response)
    try:
        from mailer import send_email
        base = os.environ.get("APP_BASE_URL") or ""
        workspace_url = f"{base}/projects/{project['id']}/workspace"
        # Prefer the linked employer's email; fall back to the lead's contact_email
        to_email = None
        if project.get("employer_id"):
            emp = await db.users.find_one({"id": project["employer_id"]}, {"email": 1, "_id": 0})
            if emp:
                to_email = emp.get("email")
        if not to_email:
            to_email = project.get("contact_email")
        if to_email:
            html = _variance_email_html(
                company=project.get("company_name") or "Your project",
                week=variance.get("week_start") or "",
                hours_var=hours_var, cost_var=cost_var,
                notes=variance.get("notes") or "",
                workspace_url=workspace_url,
            )
            subject = f"Variance alert — {project.get('company_name')} week of {variance.get('week_start')}"
            r = await send_email(to=to_email, subject=subject, html=html)
            if r.get("sent"):
                await db.project_alerts.update_one(
                    {"id": alert["id"]}, {"$set": {"email_sent": True, "email_to": to_email}}
                )
                alert["email_sent"] = True
                alert["email_to"] = to_email
        # Mirror to Slack/Teams if a webhook is configured
        emoji = ":rotating_light:" if alert["severity"] == "high" else ":warning:"
        await _slack_notify(
            f"{emoji} *Variance breach* {project.get('company_name')} · week {variance.get('week_start')} · "
            f"Hours {'+' if hours_var > 0 else ''}{hours_var}% · Cost {'+' if cost_var > 0 else ''}{cost_var}%"
        )
    except Exception:
        from deps import logger
        logger.exception("variance email failed")
    alert.pop("_id", None)
    return alert


# ---------- Variance snapshots ----------
@api.post("/projects/workspace/{project_id}/variances")
async def add_variance(project_id: str, payload: VarianceIn,
                        user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    if not _can_edit_project(user, project):
        raise HTTPException(403, "You cannot edit this project")
    ph = float(payload.planned_hours)
    ah = float(payload.actual_hours)
    pc = float(payload.planned_cost)
    ac = float(payload.actual_cost)
    hours_var_pct = round(((ah - ph) / ph) * 100, 1) if ph > 0 else 0
    cost_var_pct = round(((ac - pc) / pc) * 100, 1) if pc > 0 else 0
    doc = {
        "id": new_id(), "project_id": project_id,
        "week_start": payload.week_start,
        "planned_hours": ph, "actual_hours": ah,
        "planned_cost": pc, "actual_cost": ac,
        "hours_variance_pct": hours_var_pct,
        "cost_variance_pct": cost_var_pct,
        "notes": (payload.notes or "")[:1000],
        "author_id": user["id"], "author_name": user.get("name"),
        "created_at": now().isoformat(),
    }
    await db.project_variances.insert_one(doc)
    doc.pop("_id", None)
    # Fire an alert if we breached the ±10% threshold
    alert = await _maybe_fire_variance_alert(project, doc)
    return {"variance": doc, "alert": alert}


# ---------- Alerts ----------
@api.get("/projects/workspace/{project_id}/alerts")
async def list_project_alerts(project_id: str, user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)  # authz
    items = await db.project_alerts.find(
        {"project_id": project_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"items": items, "count": len(items)}


@api.get("/alerts/mine")
async def list_my_alerts(user: dict = Depends(get_current_user)):
    """The linked employer (or admin) sees every variance-breach alert for
    their projects — cross-project inbox."""
    if user.get("role") == "admin":
        q = {}
    elif user.get("role") == "employer":
        q = {"employer_id": user["id"]}
    else:
        return {"items": [], "count": 0, "unread": 0}
    items = await db.project_alerts.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    unread = sum(1 for a in items if not a.get("read"))
    return {"items": items, "count": len(items), "unread": unread}


@api.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str, user: dict = Depends(get_current_user)):
    a = await db.project_alerts.find_one({"id": alert_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Alert not found")
    # Only linked employer or an admin can read/dismiss
    if user.get("role") != "admin" and a.get("employer_id") != user.get("id"):
        raise HTTPException(403, "Not your alert")
    await db.project_alerts.update_one({"id": alert_id}, {"$set": {"read": True,
                                                                    "read_at": now().isoformat()}})
    return {"ok": True}


# ---------- Risk register ----------
@api.post("/projects/workspace/{project_id}/risks")
async def add_risk(project_id: str, payload: RiskIn, user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    if not _can_edit_project(user, project):
        raise HTTPException(403, "You cannot edit this project")
    if payload.likelihood not in ("L", "M", "H") or payload.impact not in ("L", "M", "H"):
        raise HTTPException(400, "likelihood/impact must be L, M or H")
    score_map = {"L": 1, "M": 2, "H": 3}
    doc = {
        "id": new_id(), "project_id": project_id,
        "title": payload.title[:120],
        "description": (payload.description or "")[:1000],
        "likelihood": payload.likelihood, "impact": payload.impact,
        "score": score_map[payload.likelihood] * score_map[payload.impact],
        "mitigation": (payload.mitigation or "")[:500],
        "owner": (payload.owner or "")[:80],
        "status": payload.status if payload.status in ("open", "mitigated", "closed") else "open",
        "author_id": user["id"], "author_name": user.get("name"),
        "created_at": now().isoformat(),
    }
    await db.project_risks.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/projects/workspace/{project_id}/risks/{risk_id}")
async def update_risk(project_id: str, risk_id: str, payload: RiskIn,
                       user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    if not _can_edit_project(user, project):
        raise HTTPException(403, "You cannot edit this project")
    score_map = {"L": 1, "M": 2, "H": 3}
    updates = {
        "title": payload.title[:120],
        "description": (payload.description or "")[:1000],
        "likelihood": payload.likelihood, "impact": payload.impact,
        "score": score_map.get(payload.likelihood, 2) * score_map.get(payload.impact, 2),
        "mitigation": (payload.mitigation or "")[:500],
        "owner": (payload.owner or "")[:80],
        "status": payload.status,
        "updated_at": now().isoformat(),
    }
    r = await db.project_risks.update_one(
        {"id": risk_id, "project_id": project_id}, {"$set": updates}
    )
    if not r.matched_count:
        raise HTTPException(404, "Risk not found")
    return {"ok": True}


# ---------- RACI matrix ----------
@api.put("/projects/workspace/{project_id}/raci")
async def set_raci(project_id: str, payload: RaciIn, user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    if not _can_edit_project(user, project):
        raise HTTPException(403, "You cannot edit this project")
    # Sanitize: allow only single-char R|A|C|I values
    clean_rows = []
    for row in payload.rows:
        activity = str(row.get("activity", ""))[:120]
        assignments = row.get("assignments") or {}
        clean = {}
        for k, v in assignments.items():
            v = str(v).upper()[:1]
            if v in ("R", "A", "C", "I"):
                clean[str(k)[:80]] = v
        clean_rows.append({"activity": activity, "assignments": clean})
    await db.projects.update_one(
        {"id": project_id}, {"$set": {"raci": clean_rows, "updated_at": now().isoformat()}}
    )
    return {"ok": True, "raci": clean_rows}


# ---------- Milestones ----------
@api.post("/projects/workspace/{project_id}/milestones")
async def add_milestone(project_id: str, payload: MilestoneIn,
                         user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    if not _can_edit_project(user, project):
        raise HTTPException(403, "You cannot edit this project")
    total_budget = float(project.get("total_budget") or 0)
    amount = payload.amount
    percent = payload.percent
    if amount is None and percent is not None and total_budget > 0:
        amount = round(total_budget * float(percent) / 100.0, 2)
    if amount is None:
        raise HTTPException(400, "Provide amount or percent (with a non-zero total_budget)")
    # Next sequence
    seq = payload.sequence
    if not seq:
        last = await db.project_milestones.find_one(
            {"project_id": project_id}, sort=[("sequence", -1)],
        )
        seq = (last.get("sequence") if last else 0) + 1
    doc = {
        "id": new_id(), "project_id": project_id,
        "name": payload.name[:80],
        "description": (payload.description or "")[:500],
        "percent": float(percent) if percent is not None else round((amount / total_budget) * 100, 2) if total_budget > 0 else 0,
        "amount": float(amount),
        "due_date": payload.due_date or "",
        "sequence": int(seq),
        "status": "pending",
        "invoice_id": None,
        "created_at": now().isoformat(),
    }
    await db.project_milestones.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.post("/projects/workspace/{project_id}/milestones/{milestone_id}/invoice")
async def invoice_milestone(project_id: str, milestone_id: str,
                             user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    # Invoicing requires finance or superadmin
    if not (has_admin_scope(user, "finance") or has_admin_scope(user, "superadmin")):
        raise HTTPException(403, "Requires finance or superadmin scope")
    m = await db.project_milestones.find_one({"id": milestone_id, "project_id": project_id})
    if not m:
        raise HTTPException(404, "Milestone not found")
    if m.get("status") != "pending":
        raise HTTPException(400, f"Milestone is already {m.get('status')}")
    invoice = {
        "id": new_id(), "project_id": project_id, "milestone_id": milestone_id,
        "amount": float(m.get("amount") or 0), "currency": project.get("currency") or "usd",
        "ref": f"INV-{new_id()[:8].upper()}",
        "status": "issued",
        "issued_by": user["id"], "issued_at": now().isoformat(),
        "paid_at": None,
    }
    await db.project_invoices.insert_one(invoice)
    await db.project_milestones.update_one(
        {"id": milestone_id},
        {"$set": {"status": "invoiced", "invoice_id": invoice["id"],
                  "invoiced_at": now().isoformat()}},
    )
    invoice.pop("_id", None)
    return invoice


@api.post("/projects/workspace/{project_id}/milestones/{milestone_id}/paid")
async def mark_milestone_paid(project_id: str, milestone_id: str,
                                user: dict = Depends(get_current_user)):
    project = await _load_project_or_404(project_id, user)
    if not (has_admin_scope(user, "finance") or has_admin_scope(user, "superadmin")):
        raise HTTPException(403, "Requires finance or superadmin scope")
    m = await db.project_milestones.find_one({"id": milestone_id, "project_id": project_id})
    if not m:
        raise HTTPException(404, "Milestone not found")
    if m.get("status") == "paid":
        return {"ok": True, "already": True}
    now_iso = now().isoformat()
    await db.project_milestones.update_one(
        {"id": milestone_id},
        {"$set": {"status": "paid", "paid_at": now_iso}},
    )
    if m.get("invoice_id"):
        await db.project_invoices.update_one(
            {"id": m["invoice_id"]},
            {"$set": {"status": "paid", "paid_at": now_iso}},
        )
    return {"ok": True}


# ---------- Invoice PDF ----------
def _render_invoice_pdf(*, project: dict, milestone: dict, invoice: dict) -> bytes:
    """Render a branded milestone invoice as a PDF, returning the raw bytes."""
    from io import BytesIO
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER

    ink = colors.HexColor("#0B1B2B")
    gold = colors.HexColor("#C79A3B")
    grey = colors.HexColor("#666666")
    faint = colors.HexColor("#DDDDDD")

    # Header band
    c.setFillColor(ink)
    c.rect(0, height - 1.4 * inch, width, 1.4 * inch, fill=1, stroke=0)
    c.setFillColor(gold)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(0.7 * inch, height - 0.7 * inch, "JOB ATLAS")
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 10)
    c.drawString(0.7 * inch, height - 0.95 * inch, "Denkoit Softech Pvt. Ltd. · GSTIN 36AAGCD3748K1ZC")
    c.drawString(0.7 * inch, height - 1.13 * inch, "support@jobatlas.io")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 0.7 * inch, height - 0.7 * inch, "MILESTONE INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 0.7 * inch, height - 0.95 * inch, f"Ref  {invoice.get('ref')}")
    c.drawRightString(width - 0.7 * inch, height - 1.13 * inch, f"Issued {(invoice.get('issued_at') or '')[:10]}")

    # Bill to
    y = height - 2.0 * inch
    c.setFillColor(grey); c.setFont("Helvetica", 9)
    c.drawString(0.7 * inch, y, "BILL TO")
    c.setFillColor(ink); c.setFont("Helvetica-Bold", 13)
    c.drawString(0.7 * inch, y - 0.22 * inch, project.get("company_name") or "—")
    c.setFont("Helvetica", 10); c.setFillColor(grey)
    c.drawString(0.7 * inch, y - 0.42 * inch, project.get("contact_name") or "")
    c.drawString(0.7 * inch, y - 0.58 * inch, project.get("contact_email") or "")

    # Project block (right)
    c.setFillColor(grey); c.setFont("Helvetica", 9)
    c.drawRightString(width - 0.7 * inch, y, "PROJECT")
    c.setFillColor(ink); c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 0.7 * inch, y - 0.22 * inch, project.get("template_title") or "Project delivery")
    c.setFont("Helvetica", 10); c.setFillColor(grey)
    c.drawRightString(width - 0.7 * inch, y - 0.42 * inch, f"Duration {project.get('duration_months', 0)} months")
    c.drawRightString(width - 0.7 * inch, y - 0.58 * inch, f"Industry {project.get('industry') or '—'}")

    # Line items table
    ty = y - 1.2 * inch
    c.setFillColor(ink); c.setFont("Helvetica-Bold", 10)
    c.drawString(0.7 * inch, ty, "DESCRIPTION")
    c.drawRightString(width - 3.0 * inch, ty, "% OF TOTAL")
    c.drawRightString(width - 0.7 * inch, ty, "AMOUNT")
    c.setStrokeColor(faint); c.setLineWidth(0.5)
    c.line(0.7 * inch, ty - 0.08 * inch, width - 0.7 * inch, ty - 0.08 * inch)

    ty -= 0.35 * inch
    c.setFont("Helvetica-Bold", 12); c.setFillColor(ink)
    c.drawString(0.7 * inch, ty, milestone.get("name") or "Milestone")
    c.setFont("Helvetica", 10); c.setFillColor(grey)
    c.drawString(0.7 * inch, ty - 0.18 * inch,
                 f"Milestone {milestone.get('sequence')} of the fixed-price plan · {project.get('company_name')}")
    percent = milestone.get("percent") or 0
    amount = float(milestone.get("amount") or 0)
    currency = (invoice.get("currency") or "usd").upper()
    c.setFillColor(ink); c.setFont("Helvetica", 11)
    c.drawRightString(width - 3.0 * inch, ty, f"{percent}%")
    c.drawRightString(width - 0.7 * inch, ty, f"{currency} {amount:,.2f}")

    # Totals block
    tot_y = ty - 1.0 * inch
    c.setStrokeColor(faint); c.line(0.7 * inch, tot_y + 0.3 * inch, width - 0.7 * inch, tot_y + 0.3 * inch)
    c.setFillColor(grey); c.setFont("Helvetica", 10)
    c.drawRightString(width - 3.0 * inch, tot_y, "Subtotal")
    c.setFillColor(ink); c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 0.7 * inch, tot_y, f"{currency} {amount:,.2f}")
    tot_y -= 0.25 * inch
    c.setFillColor(grey); c.setFont("Helvetica", 10)
    c.drawRightString(width - 3.0 * inch, tot_y, "Tax")
    c.setFillColor(ink); c.setFont("Helvetica", 11)
    c.drawRightString(width - 0.7 * inch, tot_y, "included")
    tot_y -= 0.4 * inch
    c.setFillColor(gold); c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 3.0 * inch, tot_y, "TOTAL DUE")
    c.drawRightString(width - 0.7 * inch, tot_y, f"{currency} {amount:,.2f}")

    status_label = (invoice.get("status") or "issued").upper()
    if status_label == "PAID":
        c.saveState()
        c.setFillColor(colors.HexColor("#10B981"))
        c.rect(0.7 * inch, tot_y - 0.6 * inch, 1.2 * inch, 0.35 * inch, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 12)
        c.drawString(0.85 * inch, tot_y - 0.5 * inch, "PAID")
        c.restoreState()

    # Payment terms footer
    c.setFillColor(grey); c.setFont("Helvetica", 9)
    footer_y = 0.9 * inch
    c.drawString(0.7 * inch, footer_y + 0.4 * inch, "Net-14 payment terms. Pay online via the Job Atlas workspace or wire to:")
    c.drawString(0.7 * inch, footer_y + 0.22 * inch, "ICICI Bank · A/c 112405000771 · IFSC ICIC0001124 · SWIFT ICICINBBCTS")
    c.drawString(0.7 * inch, footer_y, "Quote the ref exactly on your transfer so we can allocate the payment quickly.")

    c.showPage()
    c.save()
    return buf.getvalue()


@api.get("/projects/workspace/{project_id}/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(project_id: str, invoice_id: str,
                                user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    project = await _load_project_or_404(project_id, user)
    invoice = await db.project_invoices.find_one(
        {"id": invoice_id, "project_id": project_id}, {"_id": 0},
    )
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    milestone = await db.project_milestones.find_one(
        {"id": invoice.get("milestone_id"), "project_id": project_id}, {"_id": 0},
    )
    if not milestone:
        raise HTTPException(404, "Milestone not found")
    pdf = _render_invoice_pdf(project=project, milestone=milestone, invoice=invoice)
    filename = f"JobAtlas-{invoice.get('ref', invoice_id)}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ---------- Stripe checkout for a milestone ----------
class MilestoneCheckoutIn(BaseModel):
    origin_url: str


@api.post("/projects/workspace/{project_id}/milestones/{milestone_id}/checkout")
async def create_milestone_checkout(project_id: str, milestone_id: str,
                                     payload: MilestoneCheckoutIn,
                                     user: dict = Depends(get_current_user)):
    """Create a Stripe checkout session for a single milestone. Only the linked
    employer OR an admin can pay. On success, the webhook + return_url both
    mark the milestone + invoice paid."""
    import os, stripe
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_key:
        raise HTTPException(500, "Stripe is not configured")
    stripe.api_key = stripe_key
    project = await _load_project_or_404(project_id, user)
    if not (user.get("role") == "admin" or project.get("employer_id") == user.get("id")):
        raise HTTPException(403, "Only the linked employer or an admin can pay this milestone")
    m = await db.project_milestones.find_one({"id": milestone_id, "project_id": project_id})
    if not m:
        raise HTTPException(404, "Milestone not found")
    if m.get("status") == "paid":
        raise HTTPException(400, "Milestone already paid")

    # Ensure an invoice exists so the PDF ref lines up with the receipt.
    invoice = await db.project_invoices.find_one({"milestone_id": milestone_id})
    if not invoice:
        invoice = {
            "id": new_id(), "project_id": project_id, "milestone_id": milestone_id,
            "amount": float(m.get("amount") or 0),
            "currency": project.get("currency") or "usd",
            "ref": f"INV-{new_id()[:8].upper()}",
            "status": "issued",
            "issued_by": user["id"], "issued_at": now().isoformat(),
            "paid_at": None,
        }
        await db.project_invoices.insert_one(invoice)
        await db.project_milestones.update_one(
            {"id": milestone_id},
            {"$set": {"status": "invoiced", "invoice_id": invoice["id"],
                      "invoiced_at": now().isoformat()}},
        )

    origin = (payload.origin_url or "").rstrip("/")
    amount_cents = int(round(float(m.get("amount") or 0) * 100))
    currency = (project.get("currency") or "usd").lower()
    company = project.get("company_name") or "Project"
    try:
        session = stripe.checkout.Session.create(
            line_items=[{
                "price_data": {
                    "currency": currency,
                    "product_data": {"name": f"{company} · {m.get('name')} ({invoice['ref']})"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{origin}/projects/{project_id}/workspace?paid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/projects/{project_id}/workspace?cancel=1",
            metadata={
                "kind": "milestone",
                "project_id": project_id,
                "milestone_id": milestone_id,
                "invoice_id": invoice["id"],
                "user_id": user["id"],
            },
        )
    except Exception as e:
        raise HTTPException(400, f"Stripe error: {str(e)[:200]}")

    await db.payment_transactions.insert_one({
        "id": new_id(),
        "session_id": session.id,
        "user_id": user["id"],
        "kind": "milestone",
        "project_id": project_id,
        "milestone_id": milestone_id,
        "invoice_id": invoice["id"],
        "amount": amount_cents,
        "currency": currency,
        "status": "initiated",
        "payment_status": "pending",
        "created_at": now().isoformat(),
        "updated_at": now().isoformat(),
    })
    return {"checkout_url": session.url, "session_id": session.id, "invoice_ref": invoice["ref"]}


@api.get("/projects/milestone-payment/status/{session_id}")
async def milestone_payment_status(session_id: str, user: dict = Depends(get_current_user)):
    """Called by the frontend after the Stripe redirect. Retrieves the session
    and — if paid — marks the milestone + invoice as paid (idempotent)."""
    import stripe
    rec = await db.payment_transactions.find_one({"session_id": session_id, "kind": "milestone"},
                                                  {"_id": 0})
    if not rec:
        raise HTTPException(404, "Payment session not found")
    if rec.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                now_iso = now().isoformat()
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"status": "completed", "payment_status": "paid", "updated_at": now_iso}},
                )
                await db.project_milestones.update_one(
                    {"id": rec["milestone_id"]},
                    {"$set": {"status": "paid", "paid_at": now_iso}},
                )
                await db.project_invoices.update_one(
                    {"id": rec["invoice_id"]},
                    {"$set": {"status": "paid", "paid_at": now_iso}},
                )
                rec["payment_status"] = "paid"
        except Exception:
            from deps import logger
            logger.exception("stripe retrieve failed for %s", session_id)
    return {"session_id": session_id, "payment_status": rec.get("payment_status"),
            "milestone_id": rec.get("milestone_id"), "invoice_id": rec.get("invoice_id")}




# ---------- Employer Invoice Inbox ----------
@api.get("/invoices/mine")
async def list_my_invoices(user: dict = Depends(get_current_user)):
    """Return every invoice across the caller's linked projects. Admins see all."""
    if user.get("role") == "admin":
        projects = await db.projects.find({}, {"_id": 0, "id": 1, "company_name": 1,
                                                "template_title": 1, "employer_id": 1,
                                                "currency": 1}).to_list(500)
    elif user.get("role") == "employer":
        projects = await db.projects.find(
            {"employer_id": user["id"]},
            {"_id": 0, "id": 1, "company_name": 1, "template_title": 1,
             "employer_id": 1, "currency": 1},
        ).to_list(200)
    else:
        return {"items": [], "count": 0, "total_open": 0.0, "total_paid": 0.0}
    ids = [p["id"] for p in projects]
    invoices = await db.project_invoices.find({"project_id": {"$in": ids}},
                                              {"_id": 0}).sort("issued_at", -1).to_list(1000)
    milestones = await db.project_milestones.find({"project_id": {"$in": ids}},
                                                   {"_id": 0}).to_list(2000)
    m_by_id = {m["id"]: m for m in milestones}
    p_by_id = {p["id"]: p for p in projects}
    items = []
    total_open = 0.0
    total_paid = 0.0
    from datetime import datetime as _dt, timezone as _tz
    now_utc = _dt.now(_tz.utc)
    for inv in invoices:
        m = m_by_id.get(inv.get("milestone_id")) or {}
        p = p_by_id.get(inv.get("project_id")) or {}
        due_str = (m.get("due_date") or "")[:10]
        is_overdue = False
        if inv.get("status") != "paid" and due_str:
            try:
                due_dt = _dt.strptime(due_str, "%Y-%m-%d").replace(tzinfo=_tz.utc)
                is_overdue = due_dt < now_utc
            except Exception:
                pass
        item = {
            **inv,
            "milestone_name": m.get("name"),
            "milestone_due": due_str,
            "project_company": p.get("company_name"),
            "project_template": p.get("template_title"),
            "is_overdue": is_overdue,
        }
        items.append(item)
        amt = float(inv.get("amount") or 0)
        if inv.get("status") == "paid":
            total_paid += amt
        else:
            total_open += amt
    return {"items": items, "count": len(items),
            "total_open": round(total_open, 2),
            "total_paid": round(total_paid, 2)}


# ---------- Auto-collect Late Milestones ----------
# Employers can attach a Stripe payment_method_id via /billing/setup (below).
# The daily scheduler job hits invoices past due, emails a reminder every 3
# days, and attempts an off-session PaymentIntent if a payment method is on
# file. Every attempt is logged to db.payment_reminders for audit.

class BillingSetupIn(BaseModel):
    payment_method_id: str


class SetupCheckoutIn(BaseModel):
    origin_url: str


@api.post("/billing/setup-checkout")
async def create_setup_checkout(payload: SetupCheckoutIn,
                                 user: dict = Depends(get_current_user)):
    """Create a Stripe hosted checkout session in `setup` mode so employers can
    save a card themselves. On return, /billing/setup-checkout/status finalises
    the attach + sets it as the default PaymentMethod."""
    import os, stripe
    if user.get("role") != "employer":
        raise HTTPException(403, "Employers only")
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_key:
        raise HTTPException(500, "Stripe is not configured")
    stripe.api_key = stripe_key
    # Ensure a Stripe customer exists
    cust_id = user.get("stripe_customer_id")
    if not cust_id:
        try:
            cust = stripe.Customer.create(email=user.get("email"), name=user.get("name"),
                                           metadata={"user_id": user["id"]})
            cust_id = cust.id
            await db.users.update_one({"id": user["id"]},
                                       {"$set": {"stripe_customer_id": cust_id}})
        except Exception as e:
            raise HTTPException(400, f"Stripe customer create failed: {str(e)[:200]}")
    origin = (payload.origin_url or "").rstrip("/")
    try:
        session = stripe.checkout.Session.create(
            mode="setup",
            customer=cust_id,
            payment_method_types=["card"],
            success_url=f"{origin}/invoices?setup={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/invoices?setup_cancel=1",
            metadata={"kind": "card_setup", "user_id": user["id"]},
        )
    except Exception as e:
        raise HTTPException(400, f"Stripe error: {str(e)[:200]}")
    return {"checkout_url": session.url, "session_id": session.id}


@api.get("/billing/setup-checkout/status/{session_id}")
async def setup_checkout_status(session_id: str, user: dict = Depends(get_current_user)):
    """Called by the frontend after the Stripe setup redirect. Reads the
    SetupIntent, attaches the resulting PaymentMethod and makes it default."""
    import os, stripe
    if user.get("role") != "employer":
        raise HTTPException(403, "Employers only")
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
    if not stripe.api_key:
        raise HTTPException(500, "Stripe is not configured")
    try:
        s = stripe.checkout.Session.retrieve(session_id)
        if (s.metadata or {}).get("user_id") != user["id"]:
            raise HTTPException(403, "Not your setup session")
        setup_intent_id = s.setup_intent
        if not setup_intent_id:
            return {"ok": False, "reason": "no_setup_intent"}
        si = stripe.SetupIntent.retrieve(setup_intent_id)
        pm_id = si.payment_method
        if not pm_id or si.status != "succeeded":
            return {"ok": False, "reason": f"setup_status:{si.status}"}
        cust_id = s.customer
        stripe.Customer.modify(
            cust_id,
            invoice_settings={"default_payment_method": pm_id},
        )
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"stripe_payment_method_id": pm_id,
                      "stripe_customer_id": cust_id,
                      "billing_attached_at": now().isoformat()}},
        )
        return {"ok": True, "payment_method_id": pm_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Stripe error: {str(e)[:200]}")


@api.post("/billing/setup")
async def attach_payment_method(payload: BillingSetupIn, user: dict = Depends(get_current_user)):
    """Employer attaches (or replaces) their default Stripe PaymentMethod that
    the auto-collect job will use for off-session milestone charges."""
    import os, stripe
    if user.get("role") != "employer":
        raise HTTPException(403, "Employers only")
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_key:
        raise HTTPException(500, "Stripe is not configured")
    stripe.api_key = stripe_key
    # Ensure a Stripe customer exists for this user
    cust_id = user.get("stripe_customer_id")
    if not cust_id:
        try:
            cust = stripe.Customer.create(email=user.get("email"), name=user.get("name"),
                                           metadata={"user_id": user["id"]})
            cust_id = cust.id
            await db.users.update_one({"id": user["id"]},
                                       {"$set": {"stripe_customer_id": cust_id}})
        except Exception as e:
            raise HTTPException(400, f"Stripe customer create failed: {str(e)[:200]}")
    try:
        stripe.PaymentMethod.attach(payload.payment_method_id, customer=cust_id)
        stripe.Customer.modify(
            cust_id,
            invoice_settings={"default_payment_method": payload.payment_method_id},
        )
    except Exception as e:
        raise HTTPException(400, f"Attach failed: {str(e)[:200]}")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"stripe_payment_method_id": payload.payment_method_id,
                  "billing_attached_at": now().isoformat()}},
    )
    return {"ok": True, "customer_id": cust_id, "payment_method_id": payload.payment_method_id}


@api.get("/billing/status")
async def billing_status(user: dict = Depends(get_current_user)):
    """Frontend uses this to decide whether to show the 'Enable auto-collect'
    banner. Returns the attached PaymentMethod (last4 masked)."""
    if user.get("role") != "employer":
        raise HTTPException(403, "Employers only")
    pm_id = user.get("stripe_payment_method_id")
    if not pm_id:
        return {"attached": False}
    # Try to fetch card metadata (best-effort; UI can survive without)
    last4 = None; brand = None
    try:
        import os, stripe
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        if stripe.api_key:
            pm = stripe.PaymentMethod.retrieve(pm_id)
            card = pm.get("card") or {}
            last4 = card.get("last4"); brand = card.get("brand")
    except Exception:
        pass
    return {"attached": True, "payment_method_id": pm_id, "last4": last4, "brand": brand,
            "since": user.get("billing_attached_at")}


REMINDER_INTERVAL_DAYS = 3


async def _slack_notify(text: str) -> None:
    """Fire-and-forget Slack/Teams incoming webhook. Uses SLACK_WEBHOOK_URL env var
    (works with Microsoft Teams incoming webhooks too — they accept the same
    {'text': ...} shape)."""
    import os, json, urllib.request
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        # urllib is blocking; run in a thread so we never stall the API loop.
        import asyncio
        await asyncio.to_thread(urllib.request.urlopen, req, None, 4)
    except Exception:
        from deps import logger
        logger.exception("slack webhook failed")


async def _attempt_off_session_charge(*, invoice: dict, milestone: dict,
                                       project: dict, employer: dict) -> dict:
    """Try to auto-collect an overdue invoice using the employer's stored
    PaymentMethod. Returns a small report dict for logging."""
    import os, stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
    if not stripe.api_key:
        return {"charged": False, "reason": "stripe_not_configured"}
    pm_id = employer.get("stripe_payment_method_id")
    cust_id = employer.get("stripe_customer_id")
    if not pm_id or not cust_id:
        return {"charged": False, "reason": "no_payment_method"}
    amount = float(invoice.get("amount") or 0)
    if amount <= 0:
        return {"charged": False, "reason": "zero_amount"}
    currency = (invoice.get("currency") or project.get("currency") or "usd").lower()
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(round(amount * 100)),
            currency=currency,
            customer=cust_id,
            payment_method=pm_id,
            off_session=True,
            confirm=True,
            description=f"Auto-collect {invoice.get('ref')} · {milestone.get('name')} · {project.get('company_name')}",
            metadata={
                "kind": "milestone_auto_collect",
                "project_id": project.get("id"),
                "milestone_id": milestone.get("id"),
                "invoice_id": invoice.get("id"),
            },
        )
        if intent.status == "succeeded":
            now_iso = now().isoformat()
            await db.project_milestones.update_one(
                {"id": milestone["id"]},
                {"$set": {"status": "paid", "paid_at": now_iso}},
            )
            await db.project_invoices.update_one(
                {"id": invoice["id"]},
                {"$set": {"status": "paid", "paid_at": now_iso,
                          "auto_collected": True, "payment_intent_id": intent.id}},
            )
            return {"charged": True, "payment_intent_id": intent.id}
        return {"charged": False, "reason": f"intent_status:{intent.status}",
                "payment_intent_id": intent.id}
    except Exception as e:
        # Stripe raises stripe.error.CardError with intent info on SCA required
        return {"charged": False, "reason": f"stripe_error:{str(e)[:180]}"}


def _reminder_email_html(*, employer_name: str, invoice_ref: str, amount: float,
                          currency: str, due_date: str, milestone_name: str,
                          workspace_url: str, days_overdue: int) -> str:
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#FAF9F6;font-family:Georgia,serif;color:#0B1B2B;">
<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #ddd;padding:32px;">
  <p style="letter-spacing:.2em;font-size:11px;color:#B03A2E;margin:0 0 8px">INVOICE OVERDUE · JOB ATLAS</p>
  <h1 style="font-size:22px;margin:0 0 12px">{invoice_ref} — {currency.upper()} {amount:,.2f}</h1>
  <p style="font-size:14px;line-height:1.5;margin:0 0 12px">
    Hi {employer_name or 'there'}, invoice <b>{invoice_ref}</b> for milestone
    <b>{milestone_name}</b> was due on <b>{due_date}</b> — {days_overdue} day{'s' if days_overdue != 1 else ''} ago.
  </p>
  <p style="font-size:14px;line-height:1.5;margin:0 0 12px">
    Pay in one click from your workspace, or reply to this email if there's anything to discuss.
  </p>
  <p style="margin:24px 0 0"><a href="{workspace_url}" style="background:#0B1B2B;color:#fff;padding:10px 16px;text-decoration:none;display:inline-block">Pay in workspace →</a></p>
  <p style="font-size:11px;color:#999;margin-top:24px">If a card is saved on your Job Atlas billing settings, we'll attempt to auto-collect after 7 days overdue.</p>
</div></body></html>"""


async def scan_overdue_invoices() -> Dict[str, Any]:
    """Run daily by APScheduler. For each unpaid invoice past the milestone
    due_date: (1) email a reminder every REMINDER_INTERVAL_DAYS days; (2) if a
    payment method is on file and the invoice is >=7 days overdue, attempt
    an off-session Stripe charge. Also mirrors to Slack when configured."""
    import os
    from datetime import datetime as _dt, timezone as _tz
    result = {"scanned": 0, "reminders_sent": 0, "auto_collected": 0, "failed": 0}
    now_utc = _dt.now(_tz.utc)
    invoices = await db.project_invoices.find(
        {"status": {"$in": ["issued", "invoiced"]}}, {"_id": 0},
    ).to_list(500)
    for inv in invoices:
        m = await db.project_milestones.find_one({"id": inv.get("milestone_id")}, {"_id": 0})
        if not m:
            continue
        due_str = (m.get("due_date") or "")[:10]
        if not due_str:
            continue
        try:
            due_dt = _dt.strptime(due_str, "%Y-%m-%d").replace(tzinfo=_tz.utc)
        except Exception:
            continue
        if due_dt >= now_utc:
            continue
        result["scanned"] += 1
        days_overdue = (now_utc - due_dt).days
        project = await db.projects.find_one({"id": inv.get("project_id")}, {"_id": 0})
        if not project:
            continue
        employer = None
        to_email = project.get("contact_email")
        if project.get("employer_id"):
            employer = await db.users.find_one({"id": project["employer_id"]}, {"_id": 0})
            if employer and employer.get("email"):
                to_email = employer.get("email")

        # Reminder cadence — every REMINDER_INTERVAL_DAYS days
        last_reminder = await db.payment_reminders.find_one(
            {"invoice_id": inv["id"], "kind": "email"}, sort=[("created_at", -1)],
        )
        should_send_email = True
        if last_reminder:
            try:
                last_dt = _dt.fromisoformat(str(last_reminder.get("created_at")).replace("Z", "+00:00"))
                if (now_utc - last_dt).days < REMINDER_INTERVAL_DAYS:
                    should_send_email = False
            except Exception:
                pass

        base = os.environ.get("APP_BASE_URL") or ""
        workspace_url = f"{base}/projects/{project['id']}/workspace"

        if should_send_email and to_email:
            try:
                from mailer import send_email
                html = _reminder_email_html(
                    employer_name=(employer or {}).get("name") or project.get("contact_name") or "",
                    invoice_ref=inv.get("ref") or inv["id"][:8],
                    amount=float(inv.get("amount") or 0),
                    currency=inv.get("currency") or "usd",
                    due_date=due_str, milestone_name=m.get("name") or "Milestone",
                    workspace_url=workspace_url, days_overdue=days_overdue,
                )
                subject = f"Overdue: {inv.get('ref')} · {project.get('company_name')}"
                r = await send_email(to=to_email, subject=subject, html=html)
                await db.payment_reminders.insert_one({
                    "id": new_id(), "kind": "email",
                    "invoice_id": inv["id"], "project_id": project["id"],
                    "milestone_id": m["id"],
                    "sent_to": to_email, "sent": r.get("sent", False),
                    "reason": r.get("reason"), "days_overdue": days_overdue,
                    "created_at": now().isoformat(),
                })
                if r.get("sent"):
                    result["reminders_sent"] += 1
                await _slack_notify(
                    f":warning: *Overdue invoice* {inv.get('ref')} · {project.get('company_name')} · "
                    f"{days_overdue}d late · {(inv.get('currency') or 'usd').upper()} "
                    f"{float(inv.get('amount') or 0):,.0f}"
                )
            except Exception:
                from deps import logger
                logger.exception("reminder email failed")
                result["failed"] += 1

        # Attempt auto-collect on invoices ≥7 days overdue (once per invoice)
        if days_overdue >= 7 and employer and employer.get("stripe_payment_method_id"):
            already = await db.payment_reminders.find_one(
                {"invoice_id": inv["id"], "kind": "auto_charge", "outcome": "charged"},
            )
            if not already:
                report = await _attempt_off_session_charge(
                    invoice=inv, milestone=m, project=project, employer=employer,
                )
                await db.payment_reminders.insert_one({
                    "id": new_id(), "kind": "auto_charge",
                    "invoice_id": inv["id"], "project_id": project["id"],
                    "milestone_id": m["id"],
                    "outcome": "charged" if report.get("charged") else "failed",
                    "reason": report.get("reason"),
                    "payment_intent_id": report.get("payment_intent_id"),
                    "days_overdue": days_overdue,
                    "created_at": now().isoformat(),
                })
                if report.get("charged"):
                    result["auto_collected"] += 1
                    await _slack_notify(
                        f":white_check_mark: *Auto-collected* {inv.get('ref')} · "
                        f"{project.get('company_name')} · "
                        f"{(inv.get('currency') or 'usd').upper()} {float(inv.get('amount') or 0):,.0f}"
                    )
                else:
                    result["failed"] += 1
    return result


@api.post("/admin/invoices/scan-overdue")
async def admin_scan_overdue(user: dict = Depends(get_current_user)):
    """Manual trigger for the daily overdue-invoice scan (finance / superadmin)."""
    if not (has_admin_scope(user, "finance") or has_admin_scope(user, "superadmin")):
        raise HTTPException(403, "Requires finance or superadmin scope")
    result = await scan_overdue_invoices()
    await db.job_runs.insert_one({
        "id": new_id(), "job": "scan_overdue_invoices",
        "at": now().isoformat(), "result": result, "manual": True,
    })
    return result


# ---------- Save a live project as a permanent template ----------
import re


class SaveAsTemplateIn(BaseModel):
    title: str
    industry: str
    summary: Optional[str] = ""


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "custom"


@api.post("/admin/projects/{project_id}/save-as-template")
async def save_project_as_template(project_id: str, payload: SaveAsTemplateIn,
                                    user: dict = Depends(get_current_user)):
    """Superadmin promotes a successful project's team into the permanent
    blueprint library. Preserves the seat structure + rate ranges as a
    ±20% band around the actual rate paid."""
    if not (has_admin_scope(user, "superadmin") or has_admin_scope(user, "customization")):
        raise HTTPException(403, "Requires superadmin or customization scope")
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found")
    seats = project.get("assigned_team") or []
    if not seats:
        raise HTTPException(400, "Project has no team to snapshot")
    # Group by role → count + averaged rate → ±20% band
    role_agg: Dict[str, Dict[str, Any]] = {}
    for s in seats:
        role = s.get("role") or "Contributor"
        r = float(s.get("rate") or 0)
        if role not in role_agg:
            role_agg[role] = {"count": 0, "sum_rate": 0.0, "n_rated": 0}
        role_agg[role]["count"] += 1
        if r > 0:
            role_agg[role]["sum_rate"] += r
            role_agg[role]["n_rated"] += 1
    team = []
    for role, agg in role_agg.items():
        avg = (agg["sum_rate"] / agg["n_rated"]) if agg["n_rated"] else 100.0
        low = max(30, int(round(avg * 0.85)))
        high = int(round(avg * 1.15))
        team.append({"role": role, "count": agg["count"],
                      "rate_range": [low, high]})
    base_slug = _slugify(payload.title)
    slug = f"custom-{base_slug}"
    # Uniqueness — collide with a suffix if needed
    while await db.custom_project_templates.find_one({"id": slug}, {"id": 1}):
        slug = f"{slug}-{secrets.token_hex(2)}"
    doc = {
        "id": slug,
        "industry": payload.industry,
        "title": payload.title[:120],
        "summary": (payload.summary or project.get("template_title") or "")[:500],
        "duration_months": int(project.get("duration_months") or 6),
        "team": team,
        "source_project_id": project_id,
        "source_company": project.get("company_name"),
        "created_by": user["id"],
        "created_at": now().isoformat(),
    }
    await db.custom_project_templates.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "template": doc}


import secrets  # placed at bottom so the module-level import order stays tidy


# ---------- Reference-check summary alongside verifications ----------
@api.get("/admin/verifications-with-refs")
async def admin_verifications_with_refs(status: Optional[str] = "pending",
                                         user: dict = Depends(get_current_user)):
    """Same as /admin/verifications but joins each talent row with a
    reference-check summary so ops can approve BGV in one screen."""
    if not (has_admin_scope(user, "moderation") or has_admin_scope(user, "support")):
        raise HTTPException(403, "Requires moderation or support scope")
    q = {}
    if status in ("pending", "verified", "rejected", "none"):
        q["verification_status"] = status
    users = await db.users.find(q, {"_id": 0, "password_hash": 0,
                                     "email_verification_token": 0}).sort("verification_submitted_at", 1).to_list(200)
    out = []
    for u in users:
        refs = []
        if u.get("role") == "talent":
            refs = await db.reference_checks.find(
                {"talent_id": u["id"]}, {"_id": 0, "token": 0},
            ).sort("sent_at", -1).to_list(10)
        summary = {
            "total": len(refs),
            "yes":     sum(1 for r in refs if r.get("response") == "yes"),
            "partial": sum(1 for r in refs if r.get("response") == "partial"),
            "no":      sum(1 for r in refs if r.get("response") == "no"),
            "pending": sum(1 for r in refs if r.get("response") is None),
        }
        out.append({**u, "reference_checks": refs, "reference_summary": summary})
    return {"items": out, "count": len(out)}

