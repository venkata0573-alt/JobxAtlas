#!/usr/bin/env python3
"""Emit docs/COVERAGE_GAPS.md from pytest-cov output + the AST route inventory.

Reads (all repo-relative):
  docs/scripts/.artifacts/coverage.json         — pytest-cov JSON export
  docs/scripts/.artifacts/routes.json           — AST route inventory
  docs/scripts/.artifacts/features_endpoints.json — FEATURES.md table rows

Writes:
  docs/COVERAGE_GAPS.md

Two sections:
  §1 — every module under 60% line coverage
  §2 — every route with zero test hits, cross-referenced to FEATURES.md
        section number (or "undocumented")

Zero-hit heuristic: for each route with (file, decorator_line), check if
any line in [decorator_line + 1, decorator_line + 80] was executed. If
none were, the handler body never ran.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COVERAGE = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "coverage.json"
DEFAULT_ROUTES = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "routes.json"
DEFAULT_FEATURES = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "features_endpoints.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "COVERAGE_GAPS.md"

LOW_COVERAGE_THRESHOLD = 60.0  # percent
BODY_SCAN_LINES = 80  # how many lines after the decorator to consider "handler body"

# coverage.json keys look like "/app/backend/server.py" or "backend/server.py";
# route inventory paths look like "server.py" or "routes/admin.py".
# Normalize both to a form comparable to the route entries.
_COV_PATH_PREFIXES = ("/app/backend/", "backend/", "/app/")


def _normalize_cov_path(p: str) -> str:
    for pref in _COV_PATH_PREFIXES:
        if p.startswith(pref):
            return p[len(pref):]
    return p


# Parameter placeholder normalization — matches diff.py.
_PARAM = re.compile(r"\{[^}]+\}")


def _norm_path(p: str) -> str:
    return _PARAM.sub("{}", p)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_No entries._\n"
    out = "| " + " | ".join(headers) + " |\n"
    out += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in rows:
        clean = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        out += "| " + " | ".join(clean) + " |\n"
    return out


def build(
    coverage_json: Path,
    routes_json: Path,
    features_json: Path,
) -> str:
    cov = json.loads(coverage_json.read_text())
    routes_payload = json.loads(routes_json.read_text())
    routes = routes_payload["routes"] if isinstance(routes_payload, dict) else routes_payload
    features = json.loads(features_json.read_text())

    files = cov.get("files", {})
    totals = cov.get("totals", {})

    # ---- §1 modules under threshold ----
    low_cov_rows: list[list[str]] = []
    covered_files: dict[str, dict[str, Any]] = {}
    for cov_path, data in sorted(files.items()):
        norm = _normalize_cov_path(cov_path)
        # Skip test files + docs + tooling — we care about the app itself.
        if norm.startswith("tests/") or norm.startswith("docs/"):
            continue
        summary = data.get("summary", {})
        pct = float(summary.get("percent_covered", 0.0))
        covered_lines = int(summary.get("covered_lines", 0))
        num_statements = int(summary.get("num_statements", 0))
        missing_lines = int(summary.get("missing_lines", 0))
        covered_files[norm] = {
            "pct": pct,
            "executed": set(data.get("executed_lines", [])),
            "covered": covered_lines,
            "total": num_statements,
            "missing": missing_lines,
        }
        if pct < LOW_COVERAGE_THRESHOLD:
            low_cov_rows.append([
                norm,
                f"{pct:.1f}%",
                f"{covered_lines}/{num_statements}",
                str(missing_lines),
            ])
    low_cov_rows.sort(key=lambda r: float(r[1].rstrip("%")))

    # ---- §2 routes with zero hits ----
    # Build a features lookup for cross-reference.
    feat_by_key: dict[tuple[str, str], str] = {}
    for f in features:
        key = (f["method"], _norm_path(f["path"]))
        # Keep the first section that mentions each endpoint.
        feat_by_key.setdefault(key, f["section"])

    zero_hit_rows: list[list[str]] = []
    hit_rows: list[list[str]] = []
    for r in sorted(routes, key=lambda x: (x["file"], x["line"])):
        file_data = covered_files.get(r["file"])
        if file_data is None:
            # Coverage didn't see this file at all — treat every route in it as zero-hit.
            hit = False
        else:
            body_range = range(r["line"] + 1, r["line"] + 1 + BODY_SCAN_LINES)
            hit = any(ln in file_data["executed"] for ln in body_range)
        row_key = (r["method"], _norm_path(r["path"]))
        section = feat_by_key.get(row_key, "**undocumented**")
        row = [
            r["method"],
            f"`{r['path']}`",
            f"{r['file']}:{r['line']}",
            r["handler"],
            section if section != "**undocumented**" else section,
        ]
        (zero_hit_rows if not hit else hit_rows).append(row)

    # ---- assemble ----
    total_pct = float(totals.get("percent_covered", 0.0))
    total_covered = int(totals.get("covered_lines", 0))
    total_stmts = int(totals.get("num_statements", 0))
    total_routes = len(routes)
    zero_hit = len(zero_hit_rows)
    hit = len(hit_rows)

    doc = f"""# COVERAGE_GAPS.md — baseline test coverage report

Generated from `docs/scripts/.artifacts/coverage.json` (pytest-cov) plus the
AST route inventory. **Baseline only** — `make test-backend` uses
`--cov-fail-under=0`; nothing blocks on the numbers below.

- **Overall backend line coverage:** {total_pct:.1f}% ({total_covered}/{total_stmts} statements).
- **Routes with zero test hits:** {zero_hit} of {total_routes} (~{zero_hit * 100 // max(total_routes, 1)}%).
- **Modules under {LOW_COVERAGE_THRESHOLD:.0f}%:** {len(low_cov_rows)} files.

Read alongside `PROJECT_STATUS.md §6` — the "what's next" order should target
zero-hit money and admin routes first.

---

## 1. Modules under {LOW_COVERAGE_THRESHOLD:.0f}% line coverage

Sorted ascending by coverage. Test files and tooling excluded. `missing` is
the count of statements never executed; grep the file for the specific lines
via pytest-cov's `term-missing` report (visible in the test-backend stdout).

{_md_table(["File", "Coverage", "Covered/Total", "Missing"], low_cov_rows)}

---

## 2. Routes with zero test hits ({zero_hit} of {total_routes})

Every route below has no executed line in its handler body across the full
test run. The FEATURES.md § tells you where the manual test steps live, if
they exist — a route flagged **undocumented** has neither an automated test
nor a manual walkthrough, which is where security surface hides.

Suggested Phase 1b ordering: money paths (§10 purchase, §14 dispute fee,
§17 invoices) → admin scopes (§21) → auth/verification (§3, §15) →
everything else. Cross-reference this list against `SECURITY_BACKLOG.md`
before picking the next section — a zero-hit money route is a P0-candidate
gap, not a paperwork one.

{_md_table(["Method", "Path", "file:line", "Handler", "FEATURES §"], zero_hit_rows)}

---

## 3. Routes WITH at least one hit ({hit} of {total_routes})

For symmetry with §2. A hit is not a claim of adequate coverage — one
happy-path test still leaves the negative and cross-tenant paths open. Use
this list to know what NOT to prioritize when writing new tests.

<details>
<summary>Expand</summary>

{_md_table(["Method", "Path", "file:line", "Handler", "FEATURES §"], hit_rows)}

</details>

---

## Reproduce

```
make test-backend           # writes .artifacts/coverage.json
make coverage-gaps          # runs test-backend, then regenerates this file
```

Zero-hit heuristic: for each route with a decorator at file line L, checks
whether any line in [L+1, L+{BODY_SCAN_LINES}] was executed. A handler
shorter than {BODY_SCAN_LINES} lines whose only executed line is the `def`
itself would be false-flagged as no-hit; verify individually if the label
looks wrong.
"""
    return doc


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate docs/COVERAGE_GAPS.md.")
    ap.add_argument("--coverage", default=str(DEFAULT_COVERAGE))
    ap.add_argument("--routes", default=str(DEFAULT_ROUTES))
    ap.add_argument("--features", default=str(DEFAULT_FEATURES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    if not Path(args.coverage).is_file():
        raise SystemExit(
            f"coverage.json not found at {args.coverage}. Run `make test-backend` first."
        )

    doc = build(Path(args.coverage), Path(args.routes), Path(args.features))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(f"wrote {out} ({len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
