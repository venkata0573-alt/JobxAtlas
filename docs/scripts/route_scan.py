#!/usr/bin/env python3
"""AST-parse the ATLAS backend and enumerate every FastAPI route.

Callable as `scan_backend(backend_path)` from other Python code (tests import
it) or as a CLI (writes JSON).

The scanner recognizes routes decorated `@<router>.<method>(<path>, ...)` where
`<router>` is `app` (FastAPI instance) or `api` (`APIRouter(prefix="/api")`
from `backend/deps.py`). For each route it records:

  - method, full_path (router prefix + decorator path)
  - file, line (of the decorator)
  - has_get_current_user: True if `Depends(get_current_user)` is bound to any
    parameter, either as a default value OR inside `Annotated[..., Depends(...)]`
    on the parameter's type annotation, OR inside the decorator's
    `dependencies=[Depends(...)]` kwarg.
  - auth_deps: every `Depends(<thing>)` expression seen (for context)
  - scope_checks: `_require_scope(user, "X")` / `has_admin_scope(user, "X")`
    calls in the handler body
  - role_checks: comparisons whose LHS is literally `user.get("role")`,
    `user["role"]`, or `user.role` — anything else (e.g. loop-variable `u`) is
    excluded to avoid false positives
  - admin_perm_checks: `user.get("admin_permissions", ...)` inspections
  - unauthorized: True iff none of {has_get_current_user, scope_checks,
    role_checks, admin_perm_checks} are set. Presence of unrelated
    `Depends(...)` does NOT suppress this flag (a `Depends(rate_limiter)`
    without an identity check is still unauthorized).

Also reports:
  - skipped_decorators: things that looked like route decorators but weren't
    machine-readable (dynamic path expression, unknown router name).
  - parse_errors: files whose AST parse blew up.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Repo-relative default for the backend directory.
# docs/scripts/route_scan.py -> parents[0]=scripts, [1]=docs, [2]=repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKEND = REPO_ROOT / "backend"
DEFAULT_OUT = REPO_ROOT / "docs" / "scripts" / ".artifacts" / "routes.json"

# Known router constructor prefixes.
#   server.py: `app = FastAPI(...)`             -> no prefix
#   deps.py:   `api = APIRouter(prefix="/api")` -> "/api"
# If future refactors add more, list them here.
ROUTER_PREFIX = {
    "app": "",
    "api": "/api",
    "router": "",  # not observed in this repo, but harmless
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
SKIP_DIRS = {"__pycache__", ".venv", "venv", "tests", ".pytest_cache"}


@dataclass
class ScanResult:
    routes: list[dict[str, Any]] = field(default_factory=list)
    skipped_decorators: list[dict[str, Any]] = field(default_factory=list)
    parse_errors: list[dict[str, Any]] = field(default_factory=list)


# ------- helpers -------------------------------------------------------------

def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparseable>"


def _is_depends_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Depends"
        and bool(node.args)
    )


def _depends_target_name(call: ast.Call) -> str | None:
    """Return the name of the dependency function inside `Depends(...)`."""
    if not call.args:
        return None
    inner = call.args[0]
    if isinstance(inner, ast.Name):
        return inner.id
    if isinstance(inner, ast.Attribute):
        return inner.attr
    return None


def _annotation_depends(annotation: ast.expr | None) -> list[ast.Call]:
    """Return every `Depends(...)` call found inside `Annotated[..., ...]` on
    a parameter annotation. Returns an empty list otherwise."""
    if annotation is None:
        return []
    found: list[ast.Call] = []
    if isinstance(annotation, ast.Subscript):
        base = annotation.value
        base_ok = (
            (isinstance(base, ast.Name) and base.id == "Annotated")
            or (isinstance(base, ast.Attribute) and base.attr == "Annotated")
        )
        if base_ok:
            slice_node = annotation.slice
            elts: list[ast.expr]
            if isinstance(slice_node, ast.Tuple):
                elts = list(slice_node.elts)
            else:
                elts = [slice_node]
            # Skip the first element (the underlying type); scan the metadata.
            for meta in elts[1:]:
                if _is_depends_call(meta):
                    found.append(meta)  # type: ignore[arg-type]
    return found


# ------- extraction ----------------------------------------------------------

def _route_decorator_info(dec: ast.expr) -> tuple[str, str, str, ast.Call] | None:
    """If `dec` looks like a route decorator we understand, return
    (router, method, path, dec_call). Otherwise None.

    Returning the raw router+method+dec_call even for dynamic-path decorators
    lets the caller distinguish "not a route decorator" from
    "a route decorator we skipped for a reason worth reporting"."""
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name):
        return None
    router = func.value.id
    method = func.attr.lower()
    if method not in HTTP_METHODS:
        return None
    if not dec.args:
        return None
    first = dec.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return router, method, first.value, dec
    # Path is dynamic — record as a skip.
    return router, method, "<dynamic>", dec


def _find_get_current_user_and_deps(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator_call: ast.Call,
) -> tuple[bool, list[str]]:
    """Return (has_get_current_user, all_Depends_target_names).

    Sources scanned, in order:
      1. Positional defaults aligned to the TAIL of args.args
      2. Kwonly defaults aligned 1:1 with args.kwonlyargs (skip None)
      3. Annotated[..., Depends(...)] on any arg/kwarg annotation
      4. dependencies=[Depends(...), ...] on the route decorator itself
    """
    has_gcu = False
    dep_targets: list[str] = []

    def _consume(call: ast.Call) -> None:
        nonlocal has_gcu
        name = _depends_target_name(call)
        if name is None:
            return
        dep_targets.append(name)
        if name == "get_current_user":
            has_gcu = True

    # 1. Positional defaults align with the TAIL of args.args.
    pos_args = func.args.args
    pos_defaults = func.args.defaults or []
    n = len(pos_defaults)
    if n:
        for arg, default in zip(pos_args[-n:], pos_defaults):
            if _is_depends_call(default):
                _consume(default)  # type: ignore[arg-type]

    # 2. Kwonly defaults align 1:1 with kwonlyargs. Missing defaults are None.
    for arg, default in zip(func.args.kwonlyargs, func.args.kw_defaults or []):
        if default is None:
            continue
        if _is_depends_call(default):
            _consume(default)  # type: ignore[arg-type]

    # 3. Annotated[..., Depends(...)] on any parameter annotation.
    all_args = list(pos_args) + list(func.args.kwonlyargs)
    if func.args.vararg is not None:
        all_args.append(func.args.vararg)
    if func.args.kwarg is not None:
        all_args.append(func.args.kwarg)
    for arg in all_args:
        for call in _annotation_depends(arg.annotation):
            _consume(call)

    # 4. Decorator-level dependencies=[Depends(...), ...]
    for kw in decorator_call.keywords or []:
        if kw.arg != "dependencies":
            continue
        if isinstance(kw.value, (ast.List, ast.Tuple)):
            for elt in kw.value.elts:
                if _is_depends_call(elt):
                    _consume(elt)  # type: ignore[arg-type]

    return has_gcu, dep_targets


def _collect_body_checks(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    scope_checks: list[str] = []
    role_checks: list[str] = []
    admin_perm_checks: list[str] = []
    raises_403 = False
    raises_401 = False

    for node in ast.walk(func):
        # 1. _require_scope / has_admin_scope / require_scope calls
        if isinstance(node, ast.Call):
            fn = node.func
            fn_name: str | None = None
            if isinstance(fn, ast.Name):
                fn_name = fn.id
            elif isinstance(fn, ast.Attribute):
                fn_name = fn.attr
            if fn_name in ("_require_scope", "has_admin_scope", "require_scope"):
                scope_arg = "?"
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    scope_arg = node.args[1].value
                scope_checks.append(f"{fn_name}(user, {scope_arg!r})")
            if fn_name == "HTTPException" and node.args:
                if isinstance(node.args[0], ast.Constant):
                    code = node.args[0].value
                    if code == 403:
                        raises_403 = True
                    if code == 401:
                        raises_401 = True

        # 2. Compare against user.get("role") / user["role"] / user.role.
        #    Only accept when the receiver is literally the `user` variable —
        #    otherwise we pick up business-logic classification like
        #    `u.get("role")` inside a Mongo `.to_list()` loop.
        if isinstance(node, ast.Compare):
            left = node.left
            role_ref = False
            if (isinstance(left, ast.Call)
                    and isinstance(left.func, ast.Attribute)
                    and left.func.attr == "get"
                    and left.args
                    and isinstance(left.args[0], ast.Constant)
                    and left.args[0].value == "role"
                    and isinstance(left.func.value, ast.Name)
                    and left.func.value.id == "user"):
                role_ref = True
            elif (isinstance(left, ast.Subscript)
                    and _unparse(left.slice).strip("\"'") == "role"
                    and isinstance(left.value, ast.Name)
                    and left.value.id == "user"):
                role_ref = True
            elif (isinstance(left, ast.Attribute)
                    and left.attr == "role"
                    and isinstance(left.value, ast.Name)
                    and left.value.id == "user"):
                role_ref = True
            if role_ref:
                for op, comp in zip(node.ops, node.comparators):
                    op_sym = {
                        ast.Eq: "==", ast.NotEq: "!=",
                        ast.In: "in", ast.NotIn: "not in",
                    }.get(type(op), "?")
                    role_checks.append(f"role {op_sym} {_unparse(comp)}")

        # 3. admin_permissions inspections
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "admin_permissions"):
            admin_perm_checks.append('user.get("admin_permissions", ...)')

    return {
        "scope_checks": scope_checks,
        "role_checks": role_checks,
        "admin_perm_checks": admin_perm_checks,
        "raises_403": raises_403,
        "raises_401": raises_401,
    }


def _scan_file(path: Path, backend_root: Path, result: ScanResult) -> None:
    try:
        src = path.read_text()
        tree = ast.parse(src, filename=str(path))
    except (OSError, SyntaxError) as e:
        result.parse_errors.append({
            "file": str(path.relative_to(backend_root)),
            "error": f"{type(e).__name__}: {e}",
        })
        return

    rel = str(path.relative_to(backend_root))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            info = _route_decorator_info(dec)
            if info is None:
                continue
            router, method, raw_path, dec_call = info
            if router not in ROUTER_PREFIX:
                result.skipped_decorators.append({
                    "file": rel, "line": dec.lineno,
                    "reason": f"unknown router name {router!r}",
                    "handler": node.name,
                    "method": method.upper(),
                    "raw_path": raw_path,
                })
                continue
            if raw_path == "<dynamic>":
                result.skipped_decorators.append({
                    "file": rel, "line": dec.lineno,
                    "reason": "path is not a string literal",
                    "handler": node.name,
                    "method": method.upper(),
                    "raw_path": raw_path,
                })
                continue

            full_path = ROUTER_PREFIX[router] + raw_path
            has_gcu, deps = _find_get_current_user_and_deps(node, dec_call)
            body = _collect_body_checks(node)
            unauthorized = (
                not has_gcu
                and not body["scope_checks"]
                and not body["role_checks"]
                and not body["admin_perm_checks"]
            )
            result.routes.append({
                "method": method.upper(),
                "path": full_path,
                "file": rel,
                "line": dec.lineno,
                "handler": node.name,
                "router": router,
                "has_get_current_user": has_gcu,
                "auth_deps": deps,
                "scope_checks": body["scope_checks"],
                "role_checks": body["role_checks"],
                "admin_perm_checks": body["admin_perm_checks"],
                "raises_403": body["raises_403"],
                "raises_401": body["raises_401"],
                "unauthorized": unauthorized,
            })


def scan_backend(backend_path: str | os.PathLike) -> ScanResult:
    """Walk `backend_path` and return a ScanResult."""
    backend = Path(backend_path).resolve()
    if not backend.is_dir():
        raise NotADirectoryError(f"backend path not a directory: {backend}")
    result = ScanResult()
    for root, dirs, files in os.walk(backend):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.endswith(".py"):
                continue
            _scan_file(Path(root) / f, backend, result)
    result.routes.sort(key=lambda r: (r["file"], r["line"]))
    return result


# ------- CLI ----------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AST-scan ATLAS backend for FastAPI routes.")
    ap.add_argument("--backend", default=str(DEFAULT_BACKEND),
                    help="path to backend/ (default: repo-relative)")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="output JSON path (default: docs/scripts/.artifacts/routes.json)")
    args = ap.parse_args(argv)

    result = scan_backend(args.backend)

    if result.skipped_decorators:
        print(f"WARN: skipped {len(result.skipped_decorators)} route decorator(s):",
              file=sys.stderr)
        for s in result.skipped_decorators:
            print(f"  {s['file']}:{s['line']}  {s['method']} {s['raw_path']} — {s['reason']}",
                  file=sys.stderr)
    if result.parse_errors:
        print(f"WARN: {len(result.parse_errors)} file(s) failed to parse:",
              file=sys.stderr)
        for e in result.parse_errors:
            print(f"  {e['file']}: {e['error']}", file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "routes": result.routes,
        "skipped_decorators": result.skipped_decorators,
        "parse_errors": result.parse_errors,
    }
    out.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out} — {len(result.routes)} routes, "
          f"{len(result.skipped_decorators)} skipped, "
          f"{len(result.parse_errors)} parse errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
