"""Unit tests for docs/scripts/route_scan.py.

Each test builds a synthetic fixture module on disk in a tmp dir shaped like
`backend/`, runs `scan_backend()` against it, and asserts on the extracted
route metadata. This isolates the scanner from the real backend so regressions
in the fixture do not need to be re-baselined.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from route_scan import scan_backend  # noqa: E402


def _write_module(root: Path, name: str, body: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _by_path(result, method: str, path: str) -> dict:
    for r in result.routes:
        if r["method"] == method and r["path"] == path:
            return r
    raise AssertionError(
        f"route {method} {path} not scanned; got: "
        + ", ".join(f"{r['method']} {r['path']}" for r in result.routes)
    )


# ---- 2a: Annotated[..., Depends(get_current_user)] --------------------------

def test_annotated_depends_get_current_user_is_detected(tmp_path: Path) -> None:
    _write_module(tmp_path, "routes.py", '''
from typing import Annotated
from fastapi import Depends
from deps import api, get_current_user

@api.get("/annotated")
async def annotated_handler(user: Annotated[dict, Depends(get_current_user)]):
    return user

@api.get("/annotated-namespaced")
async def annotated_ns(user: "typing.Annotated[dict, Depends(get_current_user)]"):
    # string-annotation edge case; scanner won't parse the string.
    return user
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/annotated")
    assert r["has_get_current_user"] is True, (
        "Annotated[..., Depends(get_current_user)] must be detected"
    )
    assert r["unauthorized"] is False
    assert "get_current_user" in r["auth_deps"]


# ---- 2b: dependencies=[Depends(...)] on the route decorator -----------------

def test_decorator_dependencies_kwarg_is_detected(tmp_path: Path) -> None:
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends
from deps import api, get_current_user

@api.get("/dep-in-decorator", dependencies=[Depends(get_current_user)])
async def dep_in_decorator():
    return {"ok": True}

@api.get("/dep-in-decorator-mixed",
         dependencies=[Depends(some_rate_limiter), Depends(get_current_user)])
async def dep_mixed():
    return {"ok": True}
''')
    result = scan_backend(tmp_path)
    for path in ("/api/dep-in-decorator", "/api/dep-in-decorator-mixed"):
        r = _by_path(result, "GET", path)
        assert r["has_get_current_user"] is True, (
            f"dependencies=[Depends(get_current_user)] must be detected for {path}"
        )
        assert r["unauthorized"] is False


# ---- 2c: defaults / kw_defaults alignment ------------------------------------

def test_kwonly_only_get_current_user_is_still_detected(tmp_path: Path) -> None:
    """Regression: previously the scanner concatenated args.defaults and
    kw_defaults and took the tail of the combined list, which mis-aligned when
    positional args also had defaults."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends
from deps import api, get_current_user

@api.get("/kwonly")
async def kwonly(*, limit: int = 20, user: dict = Depends(get_current_user)):
    return {"limit": limit}

@api.get("/pos-with-default")
async def pos_with_default(offset: int = 0,
                            user: dict = Depends(get_current_user)):
    return {"offset": offset}

@api.get("/pos-mixed-kwonly")
async def pos_mixed_kwonly(offset: int = 0, *, limit: int = 20,
                            user: dict = Depends(get_current_user)):
    return {"ok": True}
''')
    result = scan_backend(tmp_path)
    for path in ("/api/kwonly", "/api/pos-with-default", "/api/pos-mixed-kwonly"):
        r = _by_path(result, "GET", path)
        assert r["has_get_current_user"] is True, (
            f"alignment bug: get_current_user default missed on {path}"
        )


def test_required_kwonly_before_depends_does_not_shift_alignment(tmp_path: Path) -> None:
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends
from deps import api, get_current_user

@api.get("/required-kwonly")
async def required_kwonly(*, must_have: int,
                          user: dict = Depends(get_current_user)):
    return {"ok": True}
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/required-kwonly")
    assert r["has_get_current_user"] is True, (
        "kw_defaults contains None for required kwonly; alignment must survive"
    )


# ---- 2d: skipped decorators + parse errors are reported ---------------------

def test_dynamic_path_is_reported_as_skipped(tmp_path: Path) -> None:
    _write_module(tmp_path, "routes.py", '''
from deps import api
PREFIX = "/dynamic"

@api.get(PREFIX + "/thing")
async def dynamic_path():
    return {"ok": True}
''')
    result = scan_backend(tmp_path)
    assert not any(r["path"].endswith("/dynamic/thing") for r in result.routes)
    assert len(result.skipped_decorators) == 1
    s = result.skipped_decorators[0]
    assert s["reason"] == "path is not a string literal"
    assert s["method"] == "GET"


def test_unknown_router_name_is_reported_as_skipped(tmp_path: Path) -> None:
    _write_module(tmp_path, "routes.py", '''
from fastapi import APIRouter
mystery = APIRouter()

@mystery.get("/mystery")
async def mystery_handler():
    return {}
''')
    result = scan_backend(tmp_path)
    assert not any(r["path"] == "/mystery" for r in result.routes)
    assert len(result.skipped_decorators) == 1
    assert "unknown router name 'mystery'" in result.skipped_decorators[0]["reason"]


def test_syntax_error_is_reported_as_parse_error(tmp_path: Path) -> None:
    _write_module(tmp_path, "broken.py", "def broken(:\n    pass\n")
    _write_module(tmp_path, "good.py", '''
from deps import api

@api.get("/good")
async def good():
    return {}
''')
    result = scan_backend(tmp_path)
    assert any(r["path"] == "/api/good" for r in result.routes)
    assert len(result.parse_errors) == 1
    assert result.parse_errors[0]["file"] == "broken.py"


# ---- 2e: unauthorized is not suppressed by unrelated Depends() --------------

def test_unrelated_depends_does_not_suppress_unauthorized(tmp_path: Path) -> None:
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends
from deps import api

def rate_limiter(): pass
def request_id(): pass

@api.get("/only-rate-limiter")
async def only_rate_limiter(rl: str = Depends(rate_limiter)):
    return {}

@api.get("/decorator-only-rate-limiter", dependencies=[Depends(request_id)])
async def decorator_dep_only():
    return {}
''')
    result = scan_backend(tmp_path)
    for path in ("/api/only-rate-limiter", "/api/decorator-only-rate-limiter"):
        r = _by_path(result, "GET", path)
        assert r["has_get_current_user"] is False
        assert r["unauthorized"] is True, (
            f"{path}: rate-limiter Depends must not mask NO-AUTH flag"
        )


# ---- Sanity: baseline route with role check is not unauthorized -------------

def test_role_check_in_body_is_recognized(tmp_path: Path) -> None:
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.post("/talent-only")
async def talent_only(user: dict = Depends(get_current_user)):
    if user.get("role") != "talent":
        raise HTTPException(403, "talent only")
    return {"ok": True}
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "POST", "/api/talent-only")
    assert r["has_get_current_user"] is True
    assert r["unauthorized"] is False
    assert any("'talent'" in c for c in r["role_checks"])


def test_loop_variable_role_compare_is_not_treated_as_authz(tmp_path: Path) -> None:
    """Regression: earlier scanner counted `u.get("role") == "talent"` inside
    a Mongo iteration as an authorization check. Only `user.*` counts."""
    _write_module(tmp_path, "routes.py", '''
from deps import api

@api.get("/aggregate")
async def aggregate():
    users = [{"role": "talent"}, {"role": "employer"}]
    for u in users:
        if u.get("role") == "talent":
            continue
    return {}
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/aggregate")
    assert r["role_checks"] == []
    assert r["unauthorized"] is True
