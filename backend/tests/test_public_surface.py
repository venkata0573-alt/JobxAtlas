"""Invariant test: every unauthorized backend route must be listed in
`security/public_routes.yml`, either under `intentional_public` (documented
as public) or under `surprising_unauth` (known triage item).

If a new route is added without authorization and without an entry here,
this test fails, forcing the reviewer to make a deliberate policy choice.

The test does not import the FastAPI app — it re-runs the AST scanner in
`docs/scripts/route_scan.py`, so it works whether the app imports cleanly
in the test environment or not."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "docs" / "scripts"
BACKEND_DIR = REPO_ROOT / "backend"
YAML_PATH = REPO_ROOT / "security" / "public_routes.yml"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from route_scan import scan_backend  # noqa: E402


@pytest.fixture(scope="module")
def scan():
    if not YAML_PATH.is_file():
        pytest.fail(f"missing {YAML_PATH.relative_to(REPO_ROOT)} — see docs/ENDPOINT_INVENTORY.md")
    return scan_backend(BACKEND_DIR)


@pytest.fixture(scope="module")
def allowlist() -> dict[str, set[tuple[str, str]]]:
    data = yaml.safe_load(YAML_PATH.read_text()) or {}
    out: dict[str, set[tuple[str, str]]] = {}
    for group in ("intentional_public", "surprising_unauth"):
        entries = data.get(group) or []
        out[group] = {(e["method"].upper(), e["path"]) for e in entries}
    return out


def test_every_unauthorized_route_is_listed(scan, allowlist) -> None:
    """The core invariant."""
    all_allowed = allowlist["intentional_public"] | allowlist["surprising_unauth"]
    unauth = [(r["method"], r["path"], r["file"], r["line"])
              for r in scan.routes if r["unauthorized"]]
    missing = [
        (method, path, file, line)
        for method, path, file, line in unauth
        if (method, path) not in all_allowed
    ]
    if missing:
        lines = ["\nUnauthorized routes missing from security/public_routes.yml:"]
        for method, path, file, line in sorted(missing):
            lines.append(f"  - {method:6} {path:60} ({file}:{line})")
        lines.append("\nAdd each to `intentional_public` (with a reason) or "
                     "`surprising_unauth` (with the FEATURES.md section that "
                     "documents the intended auth).")
        pytest.fail("\n".join(lines))


def test_allowlist_has_no_stale_entries(scan, allowlist) -> None:
    """Every YAML entry must correspond to a real unauthorized route.
    Prevents the file from silently drifting into a graveyard of ex-endpoints."""
    all_allowed = allowlist["intentional_public"] | allowlist["surprising_unauth"]
    real_unauth = {(r["method"], r["path"]) for r in scan.routes if r["unauthorized"]}
    stale = sorted(all_allowed - real_unauth)
    if stale:
        pytest.fail(
            "security/public_routes.yml lists routes that are no longer unauthorized "
            "(or no longer exist). Remove:\n  " + "\n  ".join(
                f"{m} {p}" for m, p in stale
            )
        )


def test_yaml_entries_are_well_formed() -> None:
    data = yaml.safe_load(YAML_PATH.read_text()) or {}
    valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    errors: list[str] = []
    for group in ("intentional_public", "surprising_unauth"):
        for i, entry in enumerate(data.get(group) or []):
            for key in ("method", "path", "reason"):
                if key not in entry:
                    errors.append(f"{group}[{i}] missing {key!r}")
            if entry.get("method") and entry["method"] not in valid_methods:
                errors.append(f"{group}[{i}] bad method {entry['method']!r}")
            if entry.get("path") and not entry["path"].startswith("/"):
                errors.append(f"{group}[{i}] path must start with '/': {entry['path']!r}")
    if errors:
        pytest.fail("\n".join(errors))


def test_scanner_reports_no_parse_errors_or_skips(scan) -> None:
    """If the scanner starts skipping decorators, our inventory silently loses
    routes. Fail loudly so it gets addressed."""
    assert scan.parse_errors == [], (
        f"scanner failed to parse: {scan.parse_errors}"
    )
    assert scan.skipped_decorators == [], (
        "scanner skipped route decorators — inventory is incomplete:\n  "
        + "\n  ".join(
            f"{s['file']}:{s['line']}  {s['method']} {s['raw_path']} — {s['reason']}"
            for s in scan.skipped_decorators
        )
    )
