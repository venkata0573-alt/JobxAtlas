#!/usr/bin/env python3
"""Extract every (METHOD, PATH, auth) row from FEATURES.md pipe tables."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEATURES = REPO_ROOT / "FEATURES.md"
DEFAULT_OUT = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "features_endpoints.json"

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# Table row like:
# | POST | `/api/auth/register` | `backend/routes/auth.py:115` | public |
ROW = re.compile(
    r"^\|\s*(?P<method>[A-Z]+)\s*"
    r"\|\s*`(?P<path>[^`]+)`\s*"
    r"\|\s*(?P<loc>[^|]+?)\s*"
    r"\|\s*(?P<auth>[^|]+?)\s*\|",
)


def normalize_path(p: str) -> str:
    p = p.split("?", 1)[0]
    if p != "/" and p.endswith("/"):
        p = p[:-1]
    return p


def extract_features(features_path: str | Path) -> list[dict]:
    features_path = Path(features_path)
    rows: list[dict] = []
    section = "0. preamble"
    for i, line in enumerate(features_path.read_text().splitlines(), start=1):
        m_sec = re.match(r"^##\s+(.+)$", line)
        if m_sec:
            section = m_sec.group(1).strip()
            continue
        m = ROW.match(line)
        if not m:
            continue
        method = m.group("method")
        if method not in METHODS:
            continue
        rows.append({
            "method": method,
            "path": normalize_path(m.group("path").strip()),
            "raw_path": m.group("path").strip(),
            "location_claim": m.group("loc").strip(),
            "auth_claim": m.group("auth").strip(),
            "features_line": i,
            "section": section,
        })
    return rows


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract endpoints from FEATURES.md tables.")
    ap.add_argument("--features", default=str(DEFAULT_FEATURES),
                    help="path to FEATURES.md (default: repo root)")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="output JSON path")
    args = ap.parse_args(argv)
    rows = extract_features(args.features)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2))
    print(f"wrote {out} — {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
