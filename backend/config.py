"""backend/config.py — the sole environment boundary for backend/.

This is the only module in backend/ that reads the process environment.
Every other module must `from config import settings` and read typed
attributes; a direct `os.environ` / `os.getenv` call outside this file is
a bug.

Enforcement: tests/test_config.py::test_no_module_reads_env AST-scans
backend/ and fails if any other module touches os.environ / os.getenv.

Missing required env vars fail at import-time with ONE RuntimeError that
names every missing var at once (not one at a time). See
docs/CONFIG_INVENTORY.md for the full catalogue and backend/.env.example
for descriptions.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

from typing_extensions import Annotated

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


# --- .env resolution --------------------------------------------------------
# In dev + tests we honour backend/.env; in production the process
# environment is already populated by the orchestrator and .env doesn't
# exist. pydantic-settings silently skips a missing env_file, so this
# works either way.
_ENV_PATH = Path(__file__).parent / ".env"

_MODEL_CONFIG = SettingsConfigDict(
    env_file=str(_ENV_PATH),
    env_file_encoding="utf-8",
    extra="ignore",
)

EnvName = Literal["development", "test", "production"]


# ---------- Nested settings, one class per service --------------------------
# Each nested class reads only its own env vars (via explicit alias). No
# nested delimiter — env var names stay the exact strings ops already use.

class MongoSettings(BaseSettings):
    model_config = _MODEL_CONFIG
    url: str = Field(alias="MONGO_URL")
    db_name: str = Field(alias="DB_NAME")


class StripeSettings(BaseSettings):
    """S-05: 11 read sites across server.py, projects.py, revisions.py
    all collapse to `settings.stripe.secret_key`. No silent fallback."""
    model_config = _MODEL_CONFIG
    secret_key: str = Field(alias="STRIPE_SECRET_KEY")
    webhook_secret: str = Field(alias="STRIPE_WEBHOOK_SECRET")


class MailSettings(BaseSettings):
    """Silent-fail is intentional per CLAUDE.md landmine list — mailer.py
    logs [mailer:noop] and returns sent=False when the key is unset."""
    model_config = _MODEL_CONFIG
    resend_api_key: Optional[str] = Field(default=None, alias="RESEND_API_KEY")
    sender_email: str = Field(default="onboarding@resend.dev", alias="SENDER_EMAIL")


class SlackSettings(BaseSettings):
    """Silent-fail intentional — _slack_notify early-returns when unset."""
    model_config = _MODEL_CONFIG
    webhook_url: Optional[str] = Field(default=None, alias="SLACK_WEBHOOK_URL")


class StorageSettings(BaseSettings):
    """S-15: token is its own env var, no longer borrows EMERGENT_LLM_KEY.
    S-27: proxy_url is required at boot, no silent fallback to
    integrations.emergentagent.com."""
    model_config = _MODEL_CONFIG
    proxy_url: str = Field(alias="INTEGRATION_PROXY_URL")
    token: str = Field(alias="STORAGE_TOKEN")


class LLMSettings(BaseSettings):
    """Fully optional. ai_service.suggest_hourly_rate falls back to
    rule-based rates when unset — intentional silent-fail."""
    model_config = _MODEL_CONFIG
    emergent_llm_key: Optional[str] = Field(default=None, alias="EMERGENT_LLM_KEY")


class AuthSettings(BaseSettings):
    """How we authenticate: JWT, admin seeder, captcha.
    Signing/encryption keys live in CryptoSettings — they rotate on a
    different cadence and have a different blast radius."""
    model_config = _MODEL_CONFIG
    jwt_secret: str = Field(alias="JWT_SECRET")
    admin_email: str = Field(default="admin@talenthub.io", alias="ADMIN_EMAIL")
    # S-20: no default. server.py's admin seeder must check presence and
    # skip with a WARN log if None — never seed a hardcoded password.
    admin_password: Optional[str] = Field(default=None, alias="ADMIN_PASSWORD")
    # S-08: optional here; enforced-required by Settings.model_validator
    # when env=production. auth.py:_verify_turnstile must log loudly
    # (WARN) when this is None and the fail-open path is taken.
    turnstile_secret_key: Optional[str] = Field(default=None, alias="TURNSTILE_SECRET_KEY")


class CryptoSettings(BaseSettings):
    """Keys for signing/encryption. Distinct from AuthSettings because
    they rotate on a different cadence and have a different blast radius.
    S-04: no silent fallback to the hardcoded 'jobatlas-*-v1' salts."""
    model_config = _MODEL_CONFIG
    refund_audit_secret: str = Field(alias="REFUND_AUDIT_SIGN_SECRET")
    drill_secret: str = Field(alias="DRILL_SIGN_SECRET")


class UrlSettings(BaseSettings):
    """Public URLs used to build outbound links (email, PDFs, redirects)
    plus the CORS allowlist. S-02 (partial): CORS_ORIGINS is required at
    boot and cannot contain '*'."""
    model_config = _MODEL_CONFIG
    app_base: str = Field(default="", alias="APP_BASE_URL")
    public_base: str = Field(default="", alias="PUBLIC_BASE_URL")
    public_site: str = Field(default="", alias="PUBLIC_SITE_URL")
    # NoDecode disables pydantic-settings' default JSON parsing for
    # complex types — CORS_ORIGINS is a comma-separated string in the
    # env, and the field_validator below splits it.
    cors_origins: Annotated[List[str], NoDecode] = Field(alias="CORS_ORIGINS")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            items = [x.strip() for x in v.split(",") if x.strip()]
            if not items:
                raise ValueError("CORS_ORIGINS must be a non-empty comma-separated list")
            if "*" in items:
                raise ValueError(
                    "CORS_ORIGINS must not contain '*' — "
                    "allow_credentials=True forbids wildcard origins (S-02)"
                )
            return items
        return v


class BusinessRules(BaseSettings):
    """Revision ladder + refund thresholds + F-10 rate-drift threshold.
    Defaults match FEATURES.md §12 verbatim; every value is env-tunable."""
    model_config = _MODEL_CONFIG
    revision_review_threshold: int = Field(default=3, alias="REVISION_REVIEW_THRESHOLD")
    revision_penalty_threshold: int = Field(default=5, alias="REVISION_PENALTY_THRESHOLD")
    revision_dispute_fee_usd: float = Field(default=49.0, alias="REVISION_DISPUTE_FEE_USD")
    revision_visibility_penalty: int = Field(default=20, alias="REVISION_VISIBILITY_PENALTY")
    revision_rate_nudge_penalty: float = Field(default=10.0, alias="REVISION_RATE_NUDGE_PENALTY")
    employer_flag_unique_talents: int = Field(default=3, alias="EMPLOYER_FLAG_UNIQUE_TALENTS")
    employer_flag_window_days: int = Field(default=60, alias="EMPLOYER_FLAG_WINDOW_DAYS")
    revision_recovery_under_review: int = Field(default=3, alias="REVISION_RECOVERY_UNDER_REVIEW")
    revision_recovery_excessive: int = Field(default=5, alias="REVISION_RECOVERY_EXCESSIVE")
    proven_reliable_days: int = Field(default=90, alias="PROVEN_RELIABLE_DAYS")
    refund_alert_threshold_pct: int = Field(default=20, alias="REFUND_ALERT_THRESHOLD_PCT")
    # F-10: was hardcoded at deps.py:153; now env-tunable.
    rate_drift_threshold_pct: int = Field(default=15, alias="RATE_DRIFT_THRESHOLD_PCT")


# ---------- Top-level Settings ----------------------------------------------

class Settings(BaseSettings):
    """The single point of truth. Every module imports `settings` from
    this file. See docs/CONFIG_INVENTORY.md for the full var catalogue."""
    model_config = _MODEL_CONFIG
    env: EnvName = Field(default="development", alias="ENV")
    mongo: MongoSettings
    stripe: StripeSettings
    mail: MailSettings
    slack: SlackSettings
    storage: StorageSettings
    llm: LLMSettings
    auth: AuthSettings
    crypto: CryptoSettings
    urls: UrlSettings
    business_rules: BusinessRules

    @model_validator(mode="after")
    def _enforce_production_required(self) -> "Settings":
        if self.env == "production":
            missing: List[str] = []
            if not self.auth.turnstile_secret_key:
                missing.append("TURNSTILE_SECRET_KEY")
            if missing:
                raise ValueError(
                    "Missing production-only required env vars: " + ", ".join(missing)
                )
        return self


# ---------- Aggregated-error factory ----------------------------------------

_NESTED: List[tuple[str, type[BaseSettings], str]] = [
    ("mongo", MongoSettings, "Mongo"),
    ("stripe", StripeSettings, "Stripe"),
    ("mail", MailSettings, "Mail (Resend)"),
    ("slack", SlackSettings, "Slack"),
    ("storage", StorageSettings, "Storage"),
    ("llm", LLMSettings, "LLM"),
    ("auth", AuthSettings, "Auth / JWT"),
    ("crypto", CryptoSettings, "Crypto / Signing"),
    ("urls", UrlSettings, "URLs / CORS"),
    ("business_rules", BusinessRules, "Business rules"),
]


def _env_var_name(cls: type[BaseSettings], field_name: str) -> str:
    field = cls.model_fields.get(field_name)
    if field is None:
        return field_name.upper()
    return field.alias or field_name.upper()


def _build_settings() -> Settings:
    """Construct Settings, aggregating every missing-var error across
    all nested groups into ONE RuntimeError message. Non-missing
    validation errors (e.g. CORS_ORIGINS='*') are included in the same
    message so a single boot attempt surfaces every problem at once."""
    kwargs: dict = {}
    missing_by_group: dict[str, List[str]] = {}
    other_errors: List[str] = []

    for key, cls, label in _NESTED:
        try:
            kwargs[key] = cls()
        except ValidationError as e:
            group_missing: List[str] = []
            for err in e.errors():
                if err["type"] == "missing":
                    field_name = str(err["loc"][0])
                    group_missing.append(_env_var_name(cls, field_name))
                else:
                    loc = ".".join(str(x) for x in err["loc"])
                    other_errors.append(f"  {label}.{loc}: {err['msg']}")
            if group_missing:
                missing_by_group[label] = group_missing

    if missing_by_group or other_errors:
        lines = [
            "Config error — required environment variables missing or invalid:",
            "",
        ]
        for _, _, label in _NESTED:
            if label in missing_by_group:
                lines.append(f"  {label}:")
                for var in missing_by_group[label]:
                    lines.append(f"    - {var}")
        if other_errors:
            lines.append("")
            lines.append("Also invalid:")
            lines.extend(other_errors)
        lines.append("")
        lines.append(f"Set them in {_ENV_PATH} (see backend/.env.example for descriptions).")
        raise RuntimeError("\n".join(lines))

    try:
        return Settings(**kwargs)
    except ValidationError as e:
        # Prod-only conditional missing (e.g. TURNSTILE_SECRET_KEY when
        # ENV=production). All other errors were caught above.
        msgs = "\n".join(f"  - {err['msg']}" for err in e.errors())
        raise RuntimeError(
            f"Config error — production-mode validation failed:\n{msgs}\n\n"
            f"Set them in {_ENV_PATH} (see backend/.env.example for descriptions)."
        ) from e


# ---------- Module-level singleton ------------------------------------------

settings: Settings = _build_settings()
