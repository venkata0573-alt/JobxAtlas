import json
import re
import logging
from typing import List

# F-01: emergentintegrations is not on PyPI, so a bare top-level import
# used to fail every `pip install -r backend/requirements.txt` from a
# fresh checkout. Wrap it: when the package is absent, `_HAS_LLM` stays
# False and `suggest_hourly_rate` routes to the same rule-based fallback
# that fires when EMERGENT_LLM_KEY is unset. No new silent-fail path —
# we log once at import so the degradation is visible.
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore[import-not-found]
    _HAS_LLM = True
    _MISSING_LLM_REASON = ""
except ImportError as _e:
    LlmChat = None  # type: ignore[assignment,misc]
    UserMessage = None  # type: ignore[assignment,misc]
    _HAS_LLM = False
    _MISSING_LLM_REASON = str(_e)

# F-11: config is the sole env boundary. LLM key stays optional —
# silent-fail to rule-based rates is intentional per CLAUDE.md landmine list.
from config import settings

logger = logging.getLogger("ai_service")

if not _HAS_LLM:
    logger.info(
        "[ai_service] emergentintegrations not installed (%s) — rate "
        "suggestions will use the rule-based fallback (F-01).",
        _MISSING_LLM_REASON,
    )

EMERGENT_LLM_KEY = settings.llm.emergent_llm_key or ""


async def suggest_hourly_rate(skills: List[str], years_experience: int, location: str = "Global") -> dict:
    """Ask Claude Sonnet to suggest a market-aligned hourly rate."""
    if not _HAS_LLM or not EMERGENT_LLM_KEY:
        return {"low": 25, "mid": 45, "high": 80, "currency": "USD",
                "rationale": "Default fallback (no LLM configured)."}

    system = (
        "You are a global talent-market pricing analyst. Given a candidate's skills, "
        "years of experience, and location, return a market-aligned hourly rate range in USD. "
        "Reply ONLY with strict JSON of the form: "
        '{"low": <int>, "mid": <int>, "high": <int>, "currency": "USD", "rationale": "<one sentence>"}'
    )
    user_msg = (
        f"Skills: {', '.join(skills) or 'general'}\n"
        f"Years of experience: {years_experience}\n"
        f"Location/region: {location}\n"
        "Return only JSON."
    )
    try:
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"rate-{years_experience}", system_message=system)
        chat.with_model("anthropic", "claude-sonnet-4-5-20250929").with_max_tokens(400)
        resp = await chat.send_message(UserMessage(text=user_msg))
        text = resp if isinstance(resp, str) else str(resp)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            for k in ("low", "mid", "high"):
                data[k] = int(data.get(k, 0))
            data["currency"] = data.get("currency", "USD")
            data["rationale"] = data.get("rationale", "")[:280]
            return data
    except Exception as e:
        logger.warning(f"AI rate suggestion failed: {e}")

    # Rule-based fallback
    base = 20 + years_experience * 6
    return {"low": max(15, base - 15), "mid": base, "high": base + 25,
            "currency": "USD", "rationale": "Fallback estimate based on experience."}
