#!/usr/bin/env python3
"""Render docs/ENDPOINT_INVENTORY.md from routes.json + diff.json + public_routes.yml.

The renderer holds no policy data. `security/public_routes.yml` is the single
source of truth for which unauthorized routes are intentional public surface
and which are surprises that need triage. If the YAML says nothing about a
route, the renderer reports it as "unclassified".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml  # PyYAML — already in backend/requirements.txt

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTES = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "routes.json"
DEFAULT_DIFF = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "diff.json"
DEFAULT_PUBLIC_YAML = REPO_ROOT / "security" / "public_routes.yml"
DEFAULT_OUT = REPO_ROOT / "docs" / "ENDPOINT_INVENTORY.md"


# ------- helpers ------------------------------------------------------------

def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = "| " + " | ".join(headers) + " |\n"
    out += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in rows:
        clean = [str(c).replace("|", "\\|") for c in row]
        out += "| " + " | ".join(clean) + " |\n"
    return out


def fmt_dep(r: dict) -> str:
    if not r["has_get_current_user"] \
            and not r["scope_checks"] and not r["role_checks"] \
            and not r["admin_perm_checks"]:
        return "— (public)"
    return "get_current_user"


def fmt_body_check(r: dict) -> str:
    parts: list[str] = []
    parts.extend(r["scope_checks"])
    parts.extend(f"body: {c}" for c in r["role_checks"])
    if r["admin_perm_checks"]:
        parts.append("body: admin_permissions inspected")
    return "; ".join(parts) if parts else ""


def fmt_flag(r: dict) -> str:
    flags = []
    if r["unauthorized"]:
        flags.append("**NO-AUTH**")
    role_only_admin = (
        not r["scope_checks"]
        and any("'admin'" in c or '"admin"' in c for c in r["role_checks"])
    )
    if role_only_admin and r["path"].startswith("/api/admin/"):
        flags.append("**S-09** (role==admin only, no scope)")
    return " ".join(flags)


def load_public_yaml(path: Path) -> dict:
    """Return grouped mappings plus a flat backlog-id -> route index.

    Shape:
      {
        "intentional_public": {(M, P): {"reason": ..., "backlog_id": ...}},
        "surprising_unauth":  {(M, P): {"reason": ..., "backlog_id": ...}},
        "by_backlog_id":      {"S-23": (M, P), ...},
      }
    """
    data = yaml.safe_load(path.read_text()) or {}
    out: dict = {
        "intentional_public": {},
        "surprising_unauth": {},
        "by_backlog_id": {},
    }
    for group in ("intentional_public", "surprising_unauth"):
        for entry in data.get(group, []) or []:
            key = (entry["method"].upper(), entry["path"])
            out[group][key] = {
                "reason": entry.get("reason", ""),
                "backlog_id": entry.get("backlog_id"),
            }
            if entry.get("backlog_id"):
                out["by_backlog_id"][entry["backlog_id"]] = key
    return out


# ------- renderer -----------------------------------------------------------

def render(routes: list[dict], diff: dict, public_yaml: dict) -> str:
    routes = sorted(routes, key=lambda r: (r["file"], r["line"]))
    intentional = public_yaml["intentional_public"]
    surprising = public_yaml["surprising_unauth"]

    # -- top-of-doc counts
    counts = {
        "routes": len(routes),
        "with_gcu": sum(1 for r in routes if r["has_get_current_user"]),
        "unauth": sum(1 for r in routes if r["unauthorized"]),
        "with_scope": sum(1 for r in routes if r["scope_checks"]),
        "only_in_code": len(diff["only_in_code"]),
        "only_in_features": len(diff["only_in_features"]),
        "auth_mismatches": len({(m["method"], m["path"]) for m in diff["auth_mismatches"]}),
        "auth_unknowns": len({(m["method"], m["path"]) for m in diff["auth_unknowns"]}),
    }
    s09_rows = []
    for r in routes:
        if not r["path"].startswith("/api/admin/"):
            continue
        if r["scope_checks"]:
            continue
        if any("'admin'" in c or '"admin"' in c for c in r["role_checks"]):
            s09_rows.append([r["method"], f"`{r['path']}`",
                             f"{r['file']}:{r['line']}",
                             "; ".join(r["role_checks"])])
    counts["s09"] = len(s09_rows)

    # -- full route table
    full_rows = [
        [r["method"], f"`{r['path']}`", f"{r['file']}:{r['line']}",
         fmt_dep(r), fmt_body_check(r), fmt_flag(r)]
        for r in routes
    ]
    full_table = md_table(
        ["Method", "Path", "file:line", "Dep", "Body scope/role check", "Flag"],
        full_rows,
    )

    # -- unauth bucketing
    unauth_intentional: list[list[str]] = []
    unauth_surprising: list[list[str]] = []
    unauth_unclassified: list[list[str]] = []
    for r in routes:
        if not r["unauthorized"]:
            continue
        key = (r["method"], r["path"])
        row = [r["method"], f"`{r['path']}`", f"{r['file']}:{r['line']}", r["handler"]]
        if key in intentional:
            unauth_intentional.append(row + [intentional[key]["reason"]])
        elif key in surprising:
            unauth_surprising.append(row + [surprising[key]["reason"]])
        else:
            unauth_unclassified.append(row)

    # -- only-in-code / only-in-features
    oic_rows = [
        [r["method"], f"`{r['path']}`", f"{r['file']}:{r['line']}", r["handler"], r["auth"]]
        for r in diff["only_in_code"]
    ]
    oif_rows = [
        [r["method"], f"`{r['path']}`", f"§{r['section']}", r["location_claim"], r["auth_claim"]]
        for r in diff["only_in_features"]
    ]

    # -- mismatches / unknowns
    def _dedupe(rows: list[dict]) -> list[list[str]]:
        seen: set[tuple[str, str]] = set()
        out = []
        for m in rows:
            k = (m["method"], m["path"])
            if k in seen:
                continue
            seen.add(k)
            out.append([
                m["method"], f"`{m['path']}`",
                f"{m['code_file']}:{m['code_line']}",
                m["code_auth"], m["features_claim"],
            ])
        return out

    mismatch_rows = _dedupe(diff["auth_mismatches"])
    unknown_rows = _dedupe(diff["auth_unknowns"])

    # -- cross-reference table (§5)
    xref: list[list[str]] = []
    for bid, (method, path) in sorted(public_yaml["by_backlog_id"].items()):
        entry = intentional.get((method, path)) or surprising.get((method, path)) or {}
        # locate the file:line if this backlog id maps to a real route
        route_loc = ""
        for r in routes:
            if r["method"] == method and r["path"] == path:
                route_loc = f"{r['file']}:{r['line']}"
                break
        # find the inventory subsection: it lives in §2a or §2b
        section = "§2a" if (method, path) in intentional else "§2b"
        xref.append([bid, method, f"`{path}`", route_loc, section, entry.get("reason", "")])
    cross_ref_table = md_table(
        ["Backlog ID", "Method", "Path", "file:line", "Inventory §", "Summary"],
        xref,
    ) if xref else "_No YAML entries carry a `backlog_id` yet._\n"

    # -- assemble
    unclass_section = ""
    if unauth_unclassified:
        unclass_section = (
            f"\n### 2c. Unclassified — no entry in `security/public_routes.yml` "
            f"({len(unauth_unclassified)} routes)\n\n"
            "Add each of these to `intentional_public` or `surprising_unauth` in the YAML. "
            "`backend/tests/test_public_surface.py` fails while any unclassified row remains.\n\n"
            + md_table(["Method", "Path", "file:line", "Handler"], unauth_unclassified)
        )

    return f"""# ENDPOINT_INVENTORY.md — AST-derived route inventory

Built by AST-parsing `backend/`. Regenerate with `docs/scripts/render_inventory.py`.
Every file/line reference is exact.

- **{counts['routes']}** routes registered on the shared APIRouter (`api = APIRouter(prefix="/api")` from `backend/deps.py:37`).
- **{counts['with_gcu']}** carry `Depends(get_current_user)` (via default, `Annotated[..., Depends(...)]`, or decorator-level `dependencies=`).
- **{counts['unauth']}** have no authentication or authorization check of any kind (see §2).
- **{counts['with_scope']}** call `_require_scope` / `has_admin_scope` in the body.
- **{counts['s09']}** admin routes gate on `role == "admin"` alone with no scope (S-09 pattern; see `SECURITY_BACKLOG.md`).
- **{counts['only_in_code']}** routes are in code but not documented in `FEATURES.md` tables.
- **{counts['only_in_features']}** endpoint in FEATURES.md tables has no corresponding route in code.
- **{counts['auth_mismatches']}** routes have an auth claim in FEATURES.md that diverges from what the handler actually enforces.
- **{counts['auth_unknowns']}** routes have a FEATURES.md auth claim the diff tool couldn't machine-verify (see §4d).

Methodology notes:
- The scanner detects `Depends(get_current_user)` in all three FastAPI shapes: positional/keyword defaults, `Annotated[dict, Depends(get_current_user)]`, and route-decorator `dependencies=[Depends(...)]`.
- "Body scope/role check" is what the handler actually enforces at request time. Only comparisons whose left-hand receiver is literally the `user` variable are treated as authorization — loop-variable classifications like `u.get("role")` are excluded.
- "NO-AUTH" flag = no `Depends(get_current_user)`, no `_require_scope`/`has_admin_scope`, no `user["role"]`/`user.get("role")` comparison, no `admin_permissions` inspection. Unrelated `Depends(...)` (e.g. rate-limiter) do NOT suppress this flag. Some public routes are still gated by out-of-band checks (Stripe signature on the webhook, emailed token on `/reference-check/{{token}}`).
- Diff verdicts are tri-state: **match** (docs & code agree), **mismatch** (real divergence), **unknown** (FEATURES.md claim is a free-form phrase the tool cannot parse).

---

## 1. Full route inventory

{full_table}

---

## 2. Routes with no authorization check

### 2a. Intentional public surface ({len(unauth_intentional)} routes)

Listed in `security/public_routes.yml`:`intentional_public`. Adding a new public
route without listing it here trips `backend/tests/test_public_surface.py`.

{md_table(["Method", "Path", "file:line", "Handler", "Reason"], unauth_intentional)}

### 2b. Surprising — should probably require auth ({len(unauth_surprising)} routes)

Listed in `security/public_routes.yml`:`surprising_unauth`. Each row is a triage item.

{md_table(["Method", "Path", "file:line", "Handler", "Why it's a surprise"], unauth_surprising)}
{unclass_section}

---

## 3. Admin routes that gate on `role == "admin"` alone (no scope) — S-09

CLAUDE.md invariant #6: *"Any new admin endpoint uses `_require_scope(user, "<scope>")`. `role == "admin"` alone is a bug."*
SECURITY_BACKLOG.md S-09 flags `POST /admin/rate-nudges/scan` and `GET /admin/scheduler` at `admin.py:186-211` explicitly. The AST scan confirms:

{md_table(["Method", "Path", "file:line", "Body check"], s09_rows)}

`GET /api/admin/me` is arguably fine as-is (identity/scopes lookup), but a proposed
"every `/admin/*` route has a scope dependency" pytest will need it on the allow-list.

---

## 4. Drift vs `FEATURES.md`

### 4a. In code, missing from FEATURES.md tables ({len(oic_rows)})

Routes that exist in the backend but do not appear in any FEATURES.md pipe table.
Some are mentioned in narrative prose but never in a machine-checkable table.

{md_table(["Method", "Path", "file:line", "Handler", "Actual authz"], oic_rows)}

### 4b. In FEATURES.md tables, missing from code ({len(oif_rows)})

{md_table(["Method", "Path", "FEATURES section", "Location claim", "Auth claim"], oif_rows)}

### 4c. Auth-claim mismatches ({len(mismatch_rows)})

Docs and code disagree on the authz shape:

{md_table(["Method", "Path", "file:line", "Code enforces", "FEATURES claims"], mismatch_rows)}

### 4d. Auth-claim unknowns ({len(unknown_rows)})

FEATURES.md uses a free-form phrase (e.g. "auth (party)", "auth (payer/other party/admin)")
that the diff tool can't machine-verify against code. Not necessarily wrong — needs a human eye.

{md_table(["Method", "Path", "file:line", "Code enforces", "FEATURES claims"], unknown_rows)}

---

## 5. Cross-references to `SECURITY_BACKLOG.md`

Every YAML entry in `security/public_routes.yml` may carry a `backlog_id`. The
renderer builds this table from those pointers so a reviewer can walk from a
scan finding to the ranked backlog and back.

{cross_ref_table}

---

## 6. Reproduce

```
python3 docs/scripts/route_scan.py
python3 docs/scripts/features_scan.py
python3 docs/scripts/diff.py
python3 docs/scripts/render_inventory.py
```

All four accept `--backend`, `--features`, `--routes`, `--diff`, `--public-yaml`, `--out` as appropriate; defaults are repo-relative. Artifacts land under `docs/scripts/.artifacts/`.
""".replace("{cross_ref_table}", cross_ref_table)


# ------- CLI ----------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render ENDPOINT_INVENTORY.md.")
    ap.add_argument("--routes", default=str(DEFAULT_ROUTES))
    ap.add_argument("--diff", default=str(DEFAULT_DIFF))
    ap.add_argument("--public-yaml", default=str(DEFAULT_PUBLIC_YAML))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    routes_payload = json.loads(Path(args.routes).read_text())
    routes = routes_payload["routes"] if isinstance(routes_payload, dict) else routes_payload
    diff = json.loads(Path(args.diff).read_text())
    public_yaml = load_public_yaml(Path(args.public_yaml))

    doc = render(routes, diff, public_yaml)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(f"wrote {out} ({len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
