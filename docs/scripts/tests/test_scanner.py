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


# ==========================================================================
# S-28: ownership checks (user["id"] in/not in/==/!= ...)
#
# Positive shapes MUST be recognised. Negative shapes MUST NOT — a scanner
# that only knows how to find correct patterns will silently bless the
# incorrect ones (see S-28 in SECURITY_BACKLOG.md for the rationale).
# ==========================================================================

# ---- Positive: canonical patterns that should count ----------------------

def test_ownership_membership_tuple_is_recognized(tmp_path: Path) -> None:
    """The ATLAS canonical shape at revisions.py:679 and 7+ server.py sites:
    `if user["id"] not in (a, b): raise HTTPException(403)`."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user, db

@api.get("/engagements/{eid}")
async def get_engagement(eid: str, user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": eid})
    if not eng or user["id"] not in (eng["employer_id"], eng["talent_id"]):
        raise HTTPException(404, "Not found")
    return eng
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/engagements/{eid}")
    assert r["ownership_checks"], (
        f"Canonical `user['id'] not in (a, b)` should be detected; got "
        f"ownership_checks={r['ownership_checks']}"
    )
    assert r["unauthorized"] is False


def test_ownership_equality_both_sides_recognized(tmp_path: Path) -> None:
    """Both `user["id"] == foo` and `foo != user["id"]` count. The latter
    is the shape at revisions.py:608 (`if payer_id != user["id"]:`)."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.post("/lhs-equality")
async def lhs_equality(user: dict = Depends(get_current_user)):
    d = {"owner_id": "x"}
    if user["id"] != d["owner_id"]:
        raise HTTPException(403, "not owner")
    return {}

@api.post("/rhs-equality")
async def rhs_equality(user: dict = Depends(get_current_user)):
    payer_id = "y"
    if payer_id != user["id"]:
        raise HTTPException(403, "wrong payer")
    return {}
''')
    result = scan_backend(tmp_path)
    for path in ("/api/lhs-equality", "/api/rhs-equality"):
        r = _by_path(result, "POST", path)
        assert r["ownership_checks"], (
            f"{path}: equality-form ownership check missed"
        )
        assert r["unauthorized"] is False


def test_ownership_via_user_get_id_and_dot_id(tmp_path: Path) -> None:
    """All three receiver shapes count: user["id"], user.get("id"), user.id."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.get("/via-get")
async def via_get(user: dict = Depends(get_current_user)):
    if user.get("id") != "x":
        raise HTTPException(403, "nope")
    return {}

@api.get("/via-attr")
async def via_attr(user = Depends(get_current_user)):
    if user.id != "x":
        raise HTTPException(403, "nope")
    return {}
''')
    result = scan_backend(tmp_path)
    for path in ("/api/via-get", "/api/via-attr"):
        r = _by_path(result, "GET", path)
        assert r["ownership_checks"], f"{path}: shape not recognised"


def test_ownership_recognized_in_boolop_compound_test(tmp_path: Path) -> None:
    """`if not eng or user["id"] not in (a, b): raise` — the compound
    test used across ATLAS. BoolOp recursion in _extract_ownership_compares
    must find the inner ownership Compare."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user, db

@api.get("/compound")
async def compound(user: dict = Depends(get_current_user)):
    eng = await db.engagements.find_one({"id": "e1"})
    if not eng or user["id"] not in (eng["employer_id"], eng["talent_id"]):
        raise HTTPException(403, "not party")
    return eng
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/compound")
    assert r["ownership_checks"], (
        "BoolOp compound test containing an ownership compare must be found"
    )


def test_ownership_recognized_with_404_response(tmp_path: Path) -> None:
    """S-11 wants cross-tenant to be 404, not 403 (id-exists side channel).
    A handler that raises 404 on the ownership-fail branch must still count
    as protection — the caller is blocked either way."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.post("/four-oh-four")
async def four_oh_four(user: dict = Depends(get_current_user)):
    d = {"owner_id": "x"}
    if user["id"] != d["owner_id"]:
        raise HTTPException(404, "Not found")
    return {}
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "POST", "/api/four-oh-four")
    assert r["ownership_checks"], "404 blocks the caller; ownership must count"


def test_ownership_recognized_in_whitelist_branch_pattern(tmp_path: Path) -> None:
    """The `_load_deliverable_and_authorize` shape in revisions.py:120-131:
    a sequence of `if user["id"] == X: return d` allow-lists followed by a
    final `raise HTTPException(403)`. Each allow-branch returns, so the
    ownership compare counts under the "unconditional exit" rule."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.get("/whitelist")
async def whitelist(user: dict = Depends(get_current_user)):
    d = {"employer_id": "e", "talent_id": "t"}
    if user["id"] == d.get("employer_id"):
        return {"role": "employer"}
    if user["id"] == d.get("talent_id"):
        return {"role": "talent"}
    raise HTTPException(403, "Not authorised")
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/whitelist")
    assert len(r["ownership_checks"]) >= 2, (
        f"Both whitelist branches should count as ownership; got "
        f"{r['ownership_checks']}"
    )


# ---- Inverse guards: shapes that LOOK authorized but aren't --------------
#
# Each of these MUST NOT be classified as protected. The scanner is
# supposed to under-report authorization when the pattern is uncertain,
# not silently bless a broken check.


def test_inverse_guard_loop_variable_lhs_is_not_authz(tmp_path: Path) -> None:
    """Inverse guard (a): the compare's LHS is a loop/row variable, not
    the request `user`. `row["owner_id"] == row["talent_id"]` is business
    logic classifying data, not authorizing the request."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user, db

@api.get("/loop-var")
async def loop_var(user: dict = Depends(get_current_user)):
    rows = await db.deliverables.find({}).to_list(50)
    for row in rows:
        if row["owner_id"] == row["talent_id"]:
            raise HTTPException(403, "self-owned")
    return rows
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/loop-var")
    assert r["ownership_checks"] == [], (
        f"LOOP VARIABLE LHS must NOT count as ownership; got {r['ownership_checks']}. "
        f"This is the shape that would let a broken 'compare-two-fields-that-happen-"
        f"to-both-be-the-user' pattern silently look protected."
    )


def test_inverse_guard_ownership_in_skippable_branch_is_not_authz(tmp_path: Path) -> None:
    """Inverse guard (b): the ownership check is nested inside an outer
    conditional. If the outer condition is false the check is skipped
    entirely, so the request is not authorized on that path.

    ATLAS calls this pattern out explicitly — the correct shape is a
    top-level `if user[id] not in (...): raise`, not nested."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.post("/skippable")
async def skippable(user: dict = Depends(get_current_user)):
    payload = {"strict": False, "owner_id": "x"}
    if payload["strict"]:
        # SKIPPABLE: only enforced when payload.strict is True. A caller
        # can bypass ownership by setting strict=False in the body.
        if user["id"] != payload["owner_id"]:
            raise HTTPException(403, "not owner")
    return payload
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "POST", "/api/skippable")
    assert r["ownership_checks"] == [], (
        f"Nested-inside-outer-if ownership check MUST NOT count; got "
        f"{r['ownership_checks']}. This is the shape that lets a request "
        f"bypass ownership by hitting the outer-else branch."
    )


def test_inverse_guard_ownership_computed_but_never_raises(tmp_path: Path) -> None:
    """Inverse guard (c): the ownership compare is assigned to a variable
    (or embedded in a return dict) but never raises. The developer
    computed the check and forgot to enforce it."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends
from deps import api, get_current_user

@api.get("/computed-not-enforced")
async def computed_not_enforced(user: dict = Depends(get_current_user)):
    d = {"owner_id": "x"}
    owns = user["id"] == d["owner_id"]
    return {"owns": owns, "data": d}

@api.get("/computed-in-return")
async def computed_in_return(user: dict = Depends(get_current_user)):
    d = {"owner_id": "x"}
    return {"is_owner": user["id"] == d["owner_id"]}
''')
    result = scan_backend(tmp_path)
    for path in ("/api/computed-not-enforced", "/api/computed-in-return"):
        r = _by_path(result, "GET", path)
        assert r["ownership_checks"] == [], (
            f"{path}: ownership compare that never raises MUST NOT count; "
            f"got {r['ownership_checks']}. This is the classic "
            f"forgot-to-actually-enforce bug."
        )


def test_inverse_guard_membership_against_wrong_container(tmp_path: Path) -> None:
    """Inverse guard (d): `user["id"] in engagement` — membership against
    a bare Name RHS. This is almost certainly a bug (dict membership
    tests KEYS, not values; the dev probably meant `in (engagement[
    "talent_id"], engagement["employer_id"])`). Reject bare-name RHS."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.post("/wrong-container")
async def wrong_container(user: dict = Depends(get_current_user)):
    engagement = {"talent_id": "t", "employer_id": "e"}
    if user["id"] in engagement:
        # Bug: tests dict KEYS ("talent_id", "employer_id"), not values.
        # user["id"] is a UUID, so this is always False → always raises.
        raise HTTPException(403, "not party")
    return engagement

@api.post("/name-rhs")
async def name_rhs(user: dict = Depends(get_current_user)):
    parties = ["t", "e"]  # not a literal at the compare site
    if user["id"] not in parties:
        raise HTTPException(403, "not party")
    return {}
''')
    result = scan_backend(tmp_path)
    for path in ("/api/wrong-container", "/api/name-rhs"):
        r = _by_path(result, "POST", path)
        assert r["ownership_checks"] == [], (
            f"{path}: bare-Name RHS in membership check MUST NOT count; "
            f"got {r['ownership_checks']}. Only literal Tuple/List/Set "
            f"is accepted; a variable might be the wrong container "
            f"(inverse-guard #4 in _find_ownership_checks)."
        )


def test_inverse_guard_bare_expression_statement_is_not_authz(tmp_path: Path) -> None:
    """Extra defense: an ownership compare as a bare expression statement
    (or inside an assert) is not the test of an `if` and doesn't
    unconditionally block."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends
from deps import api, get_current_user

@api.get("/bare-expr")
async def bare_expr(user: dict = Depends(get_current_user)):
    d = {"owner_id": "x"}
    user["id"] == d["owner_id"]  # bare expression — no effect
    return d
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/bare-expr")
    assert r["ownership_checks"] == []


# ---- Regression: NO-AUTH flag drops when ownership_checks fires ----------

def test_ownership_check_suppresses_no_auth_flag(tmp_path: Path) -> None:
    """The whole point of S-28: a handler that has get_current_user +
    an ownership check should NOT be classified as `unauthorized`."""
    _write_module(tmp_path, "routes.py", '''
from fastapi import Depends, HTTPException
from deps import api, get_current_user

@api.get("/owned")
async def owned(user: dict = Depends(get_current_user)):
    if user["id"] != "x":
        raise HTTPException(403)
    return {}
''')
    result = scan_backend(tmp_path)
    r = _by_path(result, "GET", "/api/owned")
    assert r["unauthorized"] is False
    assert r["ownership_checks"], "owned-by-user check must fire"
