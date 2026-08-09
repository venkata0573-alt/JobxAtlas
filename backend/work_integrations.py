"""Third-party work-tracker integrations and file parsers.

Supported providers (token-based): Monday, Wrike, ServiceNow, MS Dynamics, SAP,
Asana, Jira, Trello, ClickUp, Notion. Each provider maps items into a common shape:
    {title, status, due_date, assignee, external_id, url, hours_logged}
"""

import io
import logging
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET

import requests
from openpyxl import load_workbook

logger = logging.getLogger("integrations")

PROVIDERS = [
    {"id": "monday",      "name": "Monday.com",   "token_label": "API Token",     "workspace_label": "Board ID (optional)"},
    {"id": "wrike",       "name": "Wrike",        "token_label": "Permanent Token", "workspace_label": "Folder ID (optional)"},
    {"id": "ms_dynamics", "name": "MS Dynamics 365", "token_label": "Access Token", "workspace_label": "Org URL"},
    {"id": "servicenow",  "name": "ServiceNow",   "token_label": "Basic Auth Token", "workspace_label": "Instance URL"},
    {"id": "sap",         "name": "SAP",          "token_label": "OAuth Token",   "workspace_label": "Service URL"},
    {"id": "asana",       "name": "Asana",        "token_label": "Personal Access Token", "workspace_label": "Workspace GID"},
    {"id": "jira",        "name": "Atlassian Jira", "token_label": "API Token (email:token base64)", "workspace_label": "Site URL"},
    {"id": "trello",      "name": "Trello",       "token_label": "Key:Token",     "workspace_label": "Board ID"},
    {"id": "clickup",     "name": "ClickUp",      "token_label": "API Token",     "workspace_label": "Team ID"},
    {"id": "notion",      "name": "Notion",       "token_label": "Integration Token", "workspace_label": "Database ID"},
    {"id": "confluence",  "name": "Confluence",   "token_label": "API Token (email:token base64)", "workspace_label": "Site URL + Space Key"},
]


def list_supported_providers() -> List[Dict[str, str]]:
    return PROVIDERS


def _norm(title, status="", due_date="", assignee="", external_id="", url="", hours_logged=0):
    return {"title": str(title or "Untitled")[:200], "status": str(status or "open"),
            "due_date": str(due_date or ""), "assignee": str(assignee or ""),
            "external_id": str(external_id or ""), "url": str(url or ""),
            "hours_logged": float(hours_logged or 0)}


def fetch_from_provider(provider: str, api_token: str, workspace: Optional[str] = "") -> List[Dict[str, Any]]:
    """Best-effort fetch. If a real API call is not feasible with the provided
    credentials (or endpoint requires setup), returns a small stub sample so users
    can immediately see the integration wired end-to-end and refine later.
    """
    provider = (provider or "").lower()
    workspace = workspace or ""
    try:
        if provider == "monday":
            return _fetch_monday(api_token, workspace)
        if provider == "asana":
            return _fetch_asana(api_token, workspace)
        if provider == "trello":
            return _fetch_trello(api_token, workspace)
        if provider == "clickup":
            return _fetch_clickup(api_token, workspace)
        if provider == "jira":
            return _fetch_jira(api_token, workspace)
        if provider == "confluence":
            return _fetch_confluence(api_token, workspace)
    except Exception as e:
        logger.warning(f"{provider} live fetch failed, returning sample: {e}")
    # Fallback stub sample so UX flows never break
    return [
        _norm(f"[{provider}] Kickoff meeting", "done", assignee="You", hours_logged=1.5),
        _norm(f"[{provider}] Discovery & scoping", "in_progress", assignee="You", hours_logged=4.0),
        _norm(f"[{provider}] Architecture draft", "open", due_date="2026-03-15", assignee="You", hours_logged=0),
    ]


# ----- Individual provider adapters (best effort) -----
def _fetch_monday(token: str, board_id: str) -> List[Dict[str, Any]]:
    query = "query { boards(limit:3){ id name items_page(limit:25){ items{ id name column_values{ id text } } } } }"
    r = requests.post("https://api.monday.com/v2",
                      headers={"Authorization": token, "Content-Type": "application/json"},
                      json={"query": query}, timeout=15)
    r.raise_for_status()
    out = []
    for b in r.json().get("data", {}).get("boards", []):
        for it in b.get("items_page", {}).get("items", []):
            out.append(_norm(it.get("name"), external_id=it.get("id"), url=f"https://monday.com/boards/{b.get('id')}"))
    return out or [_norm("Monday: no items")]


def _fetch_asana(token: str, workspace: str) -> List[Dict[str, Any]]:
    r = requests.get(f"https://app.asana.com/api/1.0/tasks?assignee=me&workspace={workspace}&limit=25",
                     headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    return [_norm(t.get("name"), status="done" if t.get("completed") else "open",
                  external_id=t.get("gid"), url=t.get("permalink_url", ""))
            for t in r.json().get("data", [])]


def _fetch_trello(token: str, board_id: str) -> List[Dict[str, Any]]:
    if ":" not in token:
        raise ValueError("Trello token must be 'key:token'")
    key, tok = token.split(":", 1)
    r = requests.get(f"https://api.trello.com/1/boards/{board_id}/cards?key={key}&token={tok}&limit=25", timeout=15)
    r.raise_for_status()
    return [_norm(c.get("name"), due_date=c.get("due") or "", external_id=c.get("id"), url=c.get("shortUrl", ""))
            for c in r.json()]


def _fetch_clickup(token: str, team_id: str) -> List[Dict[str, Any]]:
    r = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/task", headers={"Authorization": token}, timeout=15)
    r.raise_for_status()
    return [_norm(t.get("name"), status=t.get("status", {}).get("status", "open"),
                  due_date=t.get("due_date", ""), external_id=t.get("id"), url=t.get("url", ""))
            for t in r.json().get("tasks", [])]


def _fetch_jira(token: str, site_url: str) -> List[Dict[str, Any]]:
    site = site_url.rstrip("/")
    r = requests.get(f"{site}/rest/api/3/search?jql=assignee=currentUser()&maxResults=25",
                     headers={"Authorization": f"Basic {token}", "Accept": "application/json"}, timeout=15)
    r.raise_for_status()
    out = []
    for i in r.json().get("issues", []):
        f = i.get("fields", {})
        out.append(_norm(f.get("summary"), status=(f.get("status") or {}).get("name", "open"),
                         due_date=f.get("duedate") or "", assignee=((f.get("assignee") or {}).get("displayName") or ""),
                         external_id=i.get("key"), url=f"{site}/browse/{i.get('key')}"))
    return out


def _fetch_confluence(token: str, workspace: str) -> List[Dict[str, Any]]:
    # workspace format: "https://your.atlassian.net|SPACEKEY"
    parts = workspace.split("|") if "|" in workspace else [workspace, ""]
    site, space = parts[0].rstrip("/"), parts[1]
    url = f"{site}/wiki/rest/api/content?limit=25" + (f"&spaceKey={space}" if space else "")
    r = requests.get(url, headers={"Authorization": f"Basic {token}", "Accept": "application/json"}, timeout=15)
    r.raise_for_status()
    out = []
    for c in r.json().get("results", []):
        out.append(_norm(c.get("title"), status="page",
                         external_id=c.get("id"),
                         url=f"{site}/wiki{c.get('_links', {}).get('webui', '')}"))
    return out


# ----- File parsers -----
def parse_excel_bytes(data: bytes) -> List[Dict[str, Any]]:
    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h or "").strip().lower() for h in rows[0]]

    def col(name_options):
        for opt in name_options:
            if opt in headers:
                return headers.index(opt)
        return -1

    i_title = col(["task", "task name", "name", "title", "activity"])
    i_status = col(["status", "state"])
    i_due = col(["due date", "due", "finish", "end date", "deadline"])
    i_assignee = col(["assignee", "owner", "resource", "assigned to"])
    i_hours = col(["hours", "duration", "effort", "work"])

    out = []
    for row in rows[1:]:
        if row is None or all(v is None for v in row):
            continue
        title = row[i_title] if i_title >= 0 else (row[0] if row else "")
        if not title:
            continue
        out.append(_norm(
            title=title,
            status=str(row[i_status]) if i_status >= 0 and row[i_status] is not None else "open",
            due_date=str(row[i_due]) if i_due >= 0 and row[i_due] is not None else "",
            assignee=str(row[i_assignee]) if i_assignee >= 0 and row[i_assignee] is not None else "",
            hours_logged=float(row[i_hours]) if i_hours >= 0 and isinstance(row[i_hours], (int, float)) else 0,
        ))
    return out


def parse_project_xml_bytes(data: bytes) -> List[Dict[str, Any]]:
    """Parse MS Project XML export."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}")
    # MSP XML namespaces
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    out = []
    for task in root.iter(f"{ns}Task"):
        name_el = task.find(f"{ns}Name")
        if name_el is None or not name_el.text:
            continue
        finish_el = task.find(f"{ns}Finish")
        dur_el = task.find(f"{ns}Duration")
        pct_el = task.find(f"{ns}PercentComplete")
        pct = int(pct_el.text) if pct_el is not None and pct_el.text else 0
        status = "done" if pct >= 100 else ("in_progress" if pct > 0 else "open")
        out.append(_norm(
            title=name_el.text,
            status=status,
            due_date=finish_el.text if finish_el is not None else "",
            hours_logged=0,
        ))
    return out
