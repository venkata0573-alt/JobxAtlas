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
    return doc


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
