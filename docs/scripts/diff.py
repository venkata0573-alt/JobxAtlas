#!/usr/bin/env python3
"""Diff the AST-derived route inventory against FEATURES.md's declared endpoints.

`auth_matches(...)` returns one of {"match", "mismatch", "unknown"}.
Unknowns are cases where the FEATURES.md auth claim doesn't fit any of the
recognized shapes and no honest verdict is possible. They get their own
section in the output so a reviewer can decide manually rather than being
folded into either bucket.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTES = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "routes.json"
DEFAULT_FEATURES = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "features_endpoints.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "diff.json"

PARAM = re.compile(r"\{[^}]+\}")


def norm(p: str) -> str:
    """Normalize path parameters — {anything} -> {} — for cross-doc matching."""
    return PARAM.sub("{}", p)


Verdict = Literal["match", "mismatch", "unknown"]


def _scope_names(code_r: dict) -> set[str]:
    out: set[str] = set()
    for s in code_r["scope_checks"]:
        # Scope check strings look like: `_require_scope(user, 'finance')`
        m = re.search(r"['\"]([^'\"]+)['\"]", s)
        if m:
            out.add(m.group(1))
    return out


def _role_names(code_r: dict) -> set[str]:
    """Roles that the body explicitly compares to."""
    out: set[str] = set()
    for rc in code_r["role_checks"]:
        for m in re.finditer(r"['\"]([a-z_]+)['\"]", rc):
            out.add(m.group(1))
    return out


def auth_matches(code_r: dict, features_claim: str) -> Verdict:
    """Compare what the code enforces to what FEATURES.md claims.

    Returns one of:
      "match"    — code and docs agree
      "mismatch" — real divergence, needs a decision
      "unknown"  — docs claim is a free-form phrase we can't parse
    """
    feat = features_claim.strip().lower()

    has_gcu = code_r["has_get_current_user"]
    scopes = _scope_names(code_r)
    roles = _role_names(code_r)
    ownerships = code_r.get("ownership_checks") or []
    code_public = (
        not has_gcu and not scopes and not roles
        and not code_r["admin_perm_checks"] and not ownerships
    )

    # Case 1: docs say public
    if re.fullmatch(r"public(\s*\([^)]+\))?", feat):
        return "match" if code_public else "mismatch"

    # Case 2: docs say "auth" (bare) — any authenticated user.
    if re.fullmatch(r"auth", feat):
        return "match" if has_gcu else "mismatch"

    # Case 2b: docs say "auth (...)" — authenticated + free-form scope phrase.
    # This is genuinely ambiguous ("auth (party)", "auth (talent flow)",
    # "auth (payer/other party/admin)"), so we report unknown unless the code
    # is truly public (then it's a mismatch).
    if re.match(r"^auth\s*\(", feat):
        if code_public:
            return "mismatch"
        return "unknown"

    # Case 3: docs say role=X
    m = re.search(r"role\s*=\s*([a-z_]+)", feat)
    if m:
        want = m.group(1)
        if not has_gcu:
            return "mismatch"
        # Body must express that role (either `role == X` or `role != Y`
        # where the exclusion effectively enforces `role in {X, ...}`).
        return "match" if want in roles else "mismatch"

    # Case 4: docs say scope=X (possibly "scope=X OR scope=Y")
    scope_tokens = re.findall(r"scope\s*=\s*([a-z_]+)", feat)
    if scope_tokens:
        if not has_gcu:
            return "mismatch"
        return "match" if scopes & set(scope_tokens) else "mismatch"

    # Case 5: "role==admin only" wording
    if "role==admin" in feat.replace(" ", "") or "role == admin" in feat:
        if not has_gcu:
            return "mismatch"
        return "match" if ("admin" in roles and not scopes) else "mismatch"

    return "unknown"


def build_diff(routes: list[dict], features: list[dict]) -> dict:
    code_index: dict[tuple[str, str], list[dict]] = {}
    for r in routes:
        code_index.setdefault((r["method"], norm(r["path"])), []).append(r)

    feat_index: dict[tuple[str, str], list[dict]] = {}
    for f in features:
        feat_index.setdefault((f["method"], norm(f["path"])), []).append(f)

    code_keys = set(code_index)
    feat_keys = set(feat_index)

    only_in_code = sorted(code_keys - feat_keys)
    only_in_features = sorted(feat_keys - code_keys)
    in_both = sorted(code_keys & feat_keys)

    def classify_code_auth(r: dict) -> str:
        parts: list[str] = []
        parts.extend(r["scope_checks"])
        parts.extend(r["role_checks"])
        if r["admin_perm_checks"]:
            parts.append("admin_permissions check")
        parts.extend(f"ownership: {c}" for c in r.get("ownership_checks") or [])
        if not parts and r["has_get_current_user"]:
            return "auth (no role/scope in body)"
        if not parts:
            return "PUBLIC (no auth)"
        return "; ".join(parts)

    out = {
        "totals": {
            "code_routes": len(routes),
            "features_endpoints": len(feat_index),
            "in_both": len(in_both),
            "only_in_code": len(only_in_code),
            "only_in_features": len(only_in_features),
        },
        "only_in_code": [],
        "only_in_features": [],
        "auth_mismatches": [],
        "auth_unknowns": [],
    }

    for k in only_in_code:
        for r in code_index[k]:
            out["only_in_code"].append({
                "method": r["method"], "path": r["path"],
                "file": r["file"], "line": r["line"],
                "handler": r["handler"], "auth": classify_code_auth(r),
            })

    for k in only_in_features:
        for f in feat_index[k]:
            out["only_in_features"].append({
                "method": f["method"], "path": f["path"],
                "section": f["section"], "location_claim": f["location_claim"],
                "auth_claim": f["auth_claim"],
            })

    for k in in_both:
        code_r = code_index[k][0]
        for f in feat_index[k]:
            verdict = auth_matches(code_r, f["auth_claim"])
            row = {
                "method": k[0], "path": k[1],
                "code_file": code_r["file"], "code_line": code_r["line"],
                "code_auth": classify_code_auth(code_r),
                "features_claim": f["auth_claim"],
                "features_section": f["section"],
                "features_line": f["features_line"],
                "verdict": verdict,
            }
            if verdict == "mismatch":
                out["auth_mismatches"].append(row)
            elif verdict == "unknown":
                out["auth_unknowns"].append(row)

    return out


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diff route inventory vs FEATURES.md.")
    ap.add_argument("--routes", default=str(DEFAULT_ROUTES))
    ap.add_argument("--features", default=str(DEFAULT_FEATURES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    routes_payload = json.loads(Path(args.routes).read_text())
    routes = routes_payload["routes"] if isinstance(routes_payload, dict) else routes_payload
    features = json.loads(Path(args.features).read_text())

    result = build_diff(routes, features)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(
        f"wrote {out} — "
        f"{result['totals']['only_in_code']} only-in-code, "
        f"{result['totals']['only_in_features']} only-in-features, "
        f"{len(result['auth_mismatches'])} mismatches, "
        f"{len(result['auth_unknowns'])} unknowns"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
