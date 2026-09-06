"""F-11 config-boundary tests.

Enforces:
- Every required field in backend/config.py raises when unset.
- Missing required fields aggregate into ONE RuntimeError message
  (whack-a-mole boot is a documented anti-goal in the F-11 task).
- No module outside backend/config.py reads os.environ / os.getenv
  (AST scan of every .py under backend/, excluding this test dir).
- .env.test values flow through: the H-8 non-default seed
  (REVISION_REVIEW_THRESHOLD=4) is visible via settings.

Runs in the same test image as the rest of the suite, so pydantic-settings
is available and .env.test-derived environment vars are already in
os.environ. The construction tests import config in a fresh module each
time via importlib.reload so the module-level `settings = _build_settings()`
call re-runs against the mutated environment.
"""
from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path
from typing import Iterable

import pytest

# Import the module directly — the singleton `settings` is built at import
# time and cached; the parametrised missing-field tests use reload() to
# force a fresh build against a mutated env.
import config as config_module


BACKEND_DIR = Path("/app/backend")

# Every required field in each nested group + top-level Settings.
# (env_var_name, group_class_name).
REQUIRED_FIELDS: list[tuple[str, str]] = [
    ("MONGO_URL", "MongoSettings"),
    ("DB_NAME", "MongoSettings"),
    ("STRIPE_SECRET_KEY", "StripeSettings"),
    ("STRIPE_WEBHOOK_SECRET", "StripeSettings"),
    ("INTEGRATION_PROXY_URL", "StorageSettings"),
    ("STORAGE_TOKEN", "StorageSettings"),
    ("JWT_SECRET", "AuthSettings"),
    ("REFUND_AUDIT_SIGN_SECRET", "CryptoSettings"),
    ("DRILL_SIGN_SECRET", "CryptoSettings"),
    ("CORS_ORIGINS", "UrlSettings"),
    ("ENV", "Settings"),  # Top-level, the user's step-7 ask.
]


# ---------- helpers ----------------------------------------------------------

def _reload_config() -> None:
    """Force config._build_settings() to run again against the current env."""
    importlib.reload(config_module)


@pytest.fixture
def hide_dotenv():
    """Temporarily rename /app/backend/.env aside so tests can force
    missing-var scenarios. Monkey-patching the module's _MODEL_CONFIG
    doesn't work because the nested BaseSettings classes captured the
    original config at class-definition time, and reload() would redefine
    them under the same file path. Filesystem rename is the surgical way
    to make pydantic-settings' env_file load a no-op.

    Serial (make test-backend runs with -n 0) so no race with parallel
    tests. finally-rename guarantees the file is restored even if the
    test raises."""
    src = BACKEND_DIR / ".env"
    dst = src.with_suffix(".env.hidden-for-test")
    hidden = False
    if src.exists():
        src.rename(dst)
        hidden = True
    try:
        yield
    finally:
        if hidden:
            dst.rename(src)


# ---------- 1. Every required field fails when missing ----------------------

@pytest.mark.parametrize("env_var,group_cls", REQUIRED_FIELDS)
def test_missing_required_field_raises(
    env_var: str, group_cls: str,
    monkeypatch: pytest.MonkeyPatch, hide_dotenv,
):
    """Each required field, individually deleted, must fail at import
    with a message naming it under its group."""
    monkeypatch.delenv(env_var, raising=False)
    with pytest.raises(RuntimeError) as exc:
        _reload_config()
    msg = str(exc.value)
    assert env_var in msg, (
        f"missing {env_var} must appear in the aggregated error message; "
        f"got:\n{msg}"
    )


# ---------- 2. All missing → one aggregated message -------------------------

def test_all_required_missing_aggregate_into_one_error(
    monkeypatch: pytest.MonkeyPatch, hide_dotenv,
):
    """Deleting every required field must produce ONE RuntimeError
    listing all of them, grouped by service."""
    for env_var, _ in REQUIRED_FIELDS:
        monkeypatch.delenv(env_var, raising=False)
    with pytest.raises(RuntimeError) as exc:
        _reload_config()
    msg = str(exc.value)
    for env_var, _ in REQUIRED_FIELDS:
        assert env_var in msg, (
            f"aggregate error must name {env_var}; missing from:\n{msg}"
        )
    # Grouping headers must appear too (spot-check three).
    for group_label in ("Mongo:", "Stripe:", "Storage:", "Environment / global:"):
        assert group_label in msg, (
            f"aggregate error must group by service label {group_label!r}; "
            f"missing from:\n{msg}"
        )


# ---------- 3. ENV has NO default (step-7 explicit ask) ---------------------

def test_env_has_no_default(monkeypatch: pytest.MonkeyPatch, hide_dotenv):
    """ENV gates production-conditional Turnstile (S-08). A silent default
    to 'development' in a prod deployment would neuter that check, which
    is the highest-consequence config bug this module can prevent. So
    ENV must be required, not defaulted."""
    monkeypatch.delenv("ENV", raising=False)
    with pytest.raises(RuntimeError) as exc:
        _reload_config()
    msg = str(exc.value)
    assert "ENV" in msg, (
        f"missing ENV must be reported; got:\n{msg}"
    )
    assert "development" not in msg.lower() or "default" not in msg.lower(), (
        "Error message must not suggest ENV silently defaults to 'development'"
    )


# ---------- 4. Non-missing validation errors also aggregate -----------------

def test_cors_wildcard_rejected(monkeypatch: pytest.MonkeyPatch, hide_dotenv):
    """S-02 (partial): explicit '*' in CORS_ORIGINS is rejected by the
    field validator, and the error must surface in the aggregated boot
    message rather than at first request time."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError) as exc:
        _reload_config()
    msg = str(exc.value)
    assert "CORS_ORIGINS" in msg
    assert "'*'" in msg or "wildcard" in msg.lower()
    assert "S-02" in msg


# ---------- 5. Production-conditional Turnstile ------------------------------

def test_production_requires_turnstile(monkeypatch: pytest.MonkeyPatch, hide_dotenv):
    """S-08 (partial): TURNSTILE_SECRET_KEY is optional in dev/test but
    required when ENV=production."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        _reload_config()
    msg = str(exc.value)
    assert "TURNSTILE_SECRET_KEY" in msg
    assert "production" in msg.lower()


# ---------- 6. AST scan — nothing outside config.py touches os.environ ------

_EXCLUDE_DIR_NAMES = {
    "tests",           # tests are allowed to touch env directly
    ".venv", "venv",   # installed third-party packages
    "__pycache__",     # bytecode caches
    ".pytest_cache",
    "node_modules",
}


def _walk_backend_py() -> Iterable[Path]:
    for p in BACKEND_DIR.rglob("*.py"):
        # config.py is the sole allowed env reader.
        if p == BACKEND_DIR / "config.py":
            continue
        if any(part in _EXCLUDE_DIR_NAMES for part in p.parts):
            continue
        yield p


def _reads_os_env(tree: ast.AST) -> list[str]:
    """Return a list of 'line: description' strings for any os.environ /
    os.getenv reads found in the AST. Empty list means clean."""
    hits: list[str] = []
    for node in ast.walk(tree):
        # os.getenv(...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "getenv"
        ):
            hits.append(f"line {node.lineno}: os.getenv(...)")
        # os.environ (Subscript, Attribute access — .get, .pop, indexing)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "environ"
        ):
            hits.append(f"line {node.lineno}: os.environ")
    return hits


def test_no_module_outside_config_reads_os_environ():
    """AST-scan every backend/*.py (excluding config.py and tests/).
    Any os.environ / os.getenv access is a violation of the F-11 goal:
    config is the sole environment boundary. If you need a new env var,
    add a field to config.Settings and import from there."""
    violations: dict[str, list[str]] = {}
    for path in _walk_backend_py():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue  # not our concern; other suites catch syntax
        hits = _reads_os_env(tree)
        if hits:
            violations[str(path.relative_to(BACKEND_DIR))] = hits
    assert not violations, (
        "F-11 boundary violated — the following modules read os.environ / "
        "os.getenv directly instead of importing from config:\n"
        + "\n".join(
            f"  {p}\n" + "\n".join(f"    {h}" for h in hits)
            for p, hits in sorted(violations.items())
        )
    )


# ---------- 7. .env.test flows through — H-8 non-default assertion ----------

def test_env_test_h8_non_default_is_live():
    """H-8 CLOSED: .env.test sets REVISION_REVIEW_THRESHOLD=4 (non-default
    vs code default 3) so a regression that stops reading the env would
    be caught here — every other value would still pass because .env.test
    happens to match the defaults exactly.

    This test asserts the config path is live end-to-end: env var →
    pydantic-settings → BusinessRules → settings.business_rules.

    If this fires and the ladder tests that will come with Phase 1b §12
    also assert the value is 4 (not 3), you have full ladder-coverage."""
    assert config_module.settings.business_rules.revision_review_threshold == 4, (
        f"Expected REVISION_REVIEW_THRESHOLD=4 to reach settings; got "
        f"{config_module.settings.business_rules.revision_review_threshold}. "
        f"See PROJECT_STATUS.md §5 H-8 for context."
    )


# ---------- 8. Sanity: .env.test values match settings ---------------------

def test_env_test_values_match_settings():
    """Spot-check that a handful of .env.test values flow through the
    nested-group hierarchy correctly (guards against alias/field-name
    typos in config.py that would silently pick up the default)."""
    s = config_module.settings
    assert s.env == "test"
    assert s.mongo.url == os.environ["MONGO_URL"]
    assert s.mongo.db_name == os.environ["DB_NAME"]
    assert s.stripe.secret_key == os.environ["STRIPE_SECRET_KEY"]
    assert s.storage.token == os.environ["STORAGE_TOKEN"]
    assert s.crypto.refund_audit_secret == os.environ["REFUND_AUDIT_SIGN_SECRET"]
    # CORS split into a list
    assert isinstance(s.urls.cors_origins, list) and len(s.urls.cors_origins) >= 1
