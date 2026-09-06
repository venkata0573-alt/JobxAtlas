"""Invariant test: every non-GET route either sits behind the CSRF middleware
or appears in `security/csrf_exempt.yml`.

Coupled to `docs/scripts/route_scan.py` — the same AST scanner that powers
`test_public_surface.py`. Does not import the FastAPI app.

Rationale for the shape of these tests:

- Today (as of writing), SECURITY_BACKLOG.md S-01 is open. The CSRF
  middleware does not exist yet, so no route "sits behind" anything, and the
  main invariant (`test_every_non_get_route_is_protected_or_exempt`) skips
  with a message pointing at S-01. That test flips to enforcing the moment
  S-01 lands.
- The three hygiene tests (`well_formed`, `have_reasons`, `not_stale`) run
  today regardless. Stale exemptions are the failure mode this file exists to
  prevent — a route deleted or renamed without pruning its exemption is
  silently a policy hole.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "docs" / "scripts"
BACKEND_DIR = REPO_ROOT / "backend"
SERVER_PY = BACKEND_DIR / "server.py"
YAML_PATH = REPO_ROOT / "security" / "csrf_exempt.yml"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from route_scan import scan_backend  # noqa: E402


# ---------------------------------------------------------------------------
# Ratchet: today's count of unprotected non-GET routes. This constant may only
# be edited DOWN. If your PR reduces the count (by adding CSRF coverage or by
# exempting a route with justification), lower this number in the same PR. If
# your PR would raise the count, add CSRF coverage or a `security/csrf_exempt.yml`
# entry with a `reason` — do not bump the ceiling.
#
# The measurement: non-GET routes that are neither covered by a registered
# CSRF middleware nor listed in the exempt YAML. Measured at 84 on the day
# `test_csrf_surface.py` was introduced; SECURITY_BACKLOG.md S-01 will drive
# it to 1 (Stripe webhook, exempt).
MAX_UNPROTECTED_NON_GET = 84


def _csrf_middleware_class() -> str | None:
    """Return the class name of a registered CSRF middleware, or None.

    Scans `server.py` for `app.add_middleware(X, ...)` calls where the class
    name contains 'csrf' (case-insensitive). This is the same shape used for
    the existing CORSMiddleware registration (`server.py:2886`).
    """
    if not SERVER_PY.is_file():
        return None
    tree = ast.parse(SERVER_PY.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "add_middleware"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        name: str | None = None
        if isinstance(first, ast.Name):
            name = first.id
        elif isinstance(first, ast.Attribute):
            name = first.attr
        if name and "csrf" in name.lower():
            return name
    return None


# ---- fixtures --------------------------------------------------------------

@pytest.fixture(scope="module")
def scan():
    if not YAML_PATH.is_file():
        pytest.fail(f"missing {YAML_PATH.relative_to(REPO_ROOT)}")
    return scan_backend(BACKEND_DIR)


@pytest.fixture(scope="module")
def raw_yaml() -> dict:
    return yaml.safe_load(YAML_PATH.read_text()) or {}


@pytest.fixture(scope="module")
def exempt_entries(raw_yaml) -> list[dict]:
    return raw_yaml.get("exempt") or []


@pytest.fixture(scope="module")
def exempt_set(exempt_entries) -> set[tuple[str, str]]:
    return {(e["method"].upper(), e["path"]) for e in exempt_entries
            if "method" in e and "path" in e}


# ---- hygiene tests (run today regardless of middleware state) --------------

def test_yaml_entries_are_well_formed(exempt_entries) -> None:
    valid_methods = {"POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    errors: list[str] = []
    for i, entry in enumerate(exempt_entries):
        for key in ("method", "path", "reason"):
            if key not in entry:
                errors.append(f"exempt[{i}] missing {key!r}")
        method = entry.get("method")
        if method and method not in valid_methods:
            # Note: GET is not permitted here — CSRF only protects mutations.
            errors.append(f"exempt[{i}] method must be non-GET; got {method!r}")
        path = entry.get("path")
        if path and not path.startswith("/"):
            errors.append(f"exempt[{i}] path must start with '/': {path!r}")
    if errors:
        pytest.fail("\n".join(errors))


def test_every_exemption_has_a_reason(exempt_entries) -> None:
    """Empty or missing reason = rubber-stamp exemption. Fail hard."""
    missing = []
    for i, entry in enumerate(exempt_entries):
        reason = entry.get("reason")
        if not (isinstance(reason, str) and reason.strip()):
            missing.append(f"exempt[{i}] ({entry.get('method')} {entry.get('path')}): no reason")
    if missing:
        pytest.fail("\n".join(missing))


def test_no_stale_exemptions(scan, exempt_set) -> None:
    """Every exempt (method, path) must resolve to a real route in the
    current backend. Rename or delete a route → prune the exemption."""
    real_non_get = {(r["method"], r["path"]) for r in scan.routes
                    if r["method"] != "GET"}
    stale = sorted(exempt_set - real_non_get)
    if stale:
        pytest.fail(
            "security/csrf_exempt.yml exempts routes that no longer exist "
            "(or have been renamed):\n  "
            + "\n  ".join(f"{m} {p}" for m, p in stale)
            + "\n\nEither restore the route or remove the exemption."
        )


# ---- coverage helper -------------------------------------------------------

def csrf_covered(route: dict) -> bool:
    """True iff the route is covered by a registered CSRF middleware.

    Today this is a binary global-or-nothing check because the codebase uses
    `app.add_middleware(...)` which applies to every route. When/if middleware
    coverage becomes route-scoped (e.g. a mount-point split), this function
    grows the per-route logic — the tests below already read through it and
    will pick up the change automatically."""
    return _csrf_middleware_class() is not None


# ---- ratchet ---------------------------------------------------------------

def test_csrf_ratchet(scan, exempt_set) -> None:
    """Monotonic-decrease ceiling on unprotected non-GET routes.

    New mutating routes must be CSRF-covered or exempted. New routes that
    are neither will push the count over `MAX_UNPROTECTED_NON_GET` and trip
    this test. Do not raise the ceiling — fix the route."""
    unprotected = [
        r for r in scan.routes
        if r["method"] != "GET"
        and not csrf_covered(r)
        and (r["method"], r["path"]) not in exempt_set
    ]
    assert len(unprotected) <= MAX_UNPROTECTED_NON_GET, (
        f"{len(unprotected)} unprotected non-GET routes, ceiling is "
        f"{MAX_UNPROTECTED_NON_GET}. New mutating routes must be CSRF-covered "
        f"or exempted. See SECURITY_BACKLOG.md S-01.\n\nNew unprotected routes:\n  "
        + "\n  ".join(
            f"{r['method']:6} {r['path']:60} ({r['file']}:{r['line']})"
            for r in sorted(unprotected, key=lambda x: (x["file"], x["line"]))[
                MAX_UNPROTECTED_NON_GET:
            ]
        )
    )


def test_csrf_ratchet_ceiling_is_tight(scan, exempt_set) -> None:
    """The ceiling must equal today's actual count, not float above it.

    If your PR *reduces* the unprotected count (great — thank you), you must
    also lower `MAX_UNPROTECTED_NON_GET` in the same PR. Otherwise the ratchet
    becomes a lagging indicator and a new unprotected route can silently
    reoccupy the slack."""
    unprotected = sum(
        1 for r in scan.routes
        if r["method"] != "GET"
        and not csrf_covered(r)
        and (r["method"], r["path"]) not in exempt_set
    )
    assert unprotected == MAX_UNPROTECTED_NON_GET, (
        f"Ratchet ceiling is stale: MAX_UNPROTECTED_NON_GET={MAX_UNPROTECTED_NON_GET}, "
        f"actual unprotected count is {unprotected}. Update the constant "
        f"in backend/tests/test_csrf_surface.py."
    )


# ---- main invariant --------------------------------------------------------

def test_every_non_get_route_is_protected_or_exempt(scan, exempt_set) -> None:
    """The core CSRF-surface invariant."""
    middleware = _csrf_middleware_class()
    if middleware is None:
        # No CSRF middleware registered yet — enforcing coverage would fail
        # for every non-GET route, which would drown the actionable signal.
        # This test starts enforcing the moment S-01 registers a middleware
        # whose class name contains "csrf".
        pytest.skip(
            "CSRF middleware not registered on `app` — see SECURITY_BACKLOG.md S-01. "
            "This test enforces coverage as soon as an `app.add_middleware(*CSRF*)` "
            "call exists in backend/server.py."
        )

    # Middleware is registered → global coverage assumption applies.
    # Everything not exempt is protected; assert every exemption is a real
    # non-GET route (redundant with test_no_stale_exemptions, kept for clarity
    # so the invariant's second half is visible in one place).
    non_get_routes = {(r["method"], r["path"]) for r in scan.routes
                      if r["method"] != "GET"}
    orphaned = sorted(exempt_set - non_get_routes)
    assert not orphaned, (
        f"CSRF exemption list contains entries that are not real non-GET routes: {orphaned}"
    )
