"""F-01: emergentintegrations must be an optional import.

The package isn't on PyPI; a fresh `pip install -r backend/requirements.txt`
used to fail because `ai_service.py` imported `emergentintegrations.llm.chat`
at module top with no guard. The test image papered over this with a shim
copied into site-packages, so tests never caught it — the failure mode was
only visible to someone running the backend outside the test image.

This test locks in the fix by simulating the shim absent:
  1. Delete `ai_service` and any cached `emergentintegrations` modules from
     `sys.modules`.
  2. Insert a meta-path finder that raises `ImportError` for any attempt to
     import `emergentintegrations` or a submodule.
  3. Re-import `ai_service`. It MUST succeed.
  4. Call `suggest_hourly_rate` and confirm the rule-based fallback returns
     a rate-shaped dict — the LLM path must degrade gracefully, not raise.

`monkeypatch` handles restoration of `sys.meta_path` and `sys.modules` on
teardown, so subsequent tests see the original `ai_service` module (which,
inside the current test image, still has the shim available — that's fine,
this test doesn't care what the ambient state is).
"""
from __future__ import annotations

import importlib
import sys

import pytest


class _EmergentintegrationsBlocker:
    """`sys.meta_path` finder that refuses to load `emergentintegrations`.

    Placed at the head of the meta-path so it fires before the shim (or, in
    a future fresh-install world, before the real package if it ever
    appears on PyPI). Returning `None` from `find_spec` for other names
    tells Python to keep searching the rest of the meta path.
    """

    def find_spec(self, name: str, path=None, target=None):
        if name == "emergentintegrations" or name.startswith("emergentintegrations."):
            raise ImportError("F-01 test: emergentintegrations blocked")
        return None


@pytest.fixture
def ai_service_without_emergentintegrations(monkeypatch):
    """Re-import `ai_service` with `emergentintegrations` unavailable.

    Yields the freshly-imported module. `monkeypatch` restores the real
    module on teardown.
    """
    # Force a fresh import of ai_service on the next `import_module` call.
    monkeypatch.delitem(sys.modules, "ai_service", raising=False)
    for name in list(sys.modules):
        if name == "emergentintegrations" or name.startswith("emergentintegrations."):
            monkeypatch.delitem(sys.modules, name, raising=False)

    # Block future imports of emergentintegrations for the duration of this test.
    monkeypatch.setattr(sys, "meta_path", [_EmergentintegrationsBlocker(), *sys.meta_path])

    return importlib.import_module("ai_service")


def test_ai_service_imports_when_emergentintegrations_absent(
    ai_service_without_emergentintegrations,
):
    """The whole point of F-01: module import must not raise."""
    ai_service = ai_service_without_emergentintegrations
    assert ai_service._HAS_LLM is False, (
        "expected _HAS_LLM=False when emergentintegrations is blocked; "
        f"got {ai_service._HAS_LLM!r}. The try/except at module top isn't "
        "gating the import — F-01 fix regressed."
    )
    assert ai_service.LlmChat is None
    assert ai_service.UserMessage is None


async def test_suggest_hourly_rate_falls_back_when_llm_missing(
    ai_service_without_emergentintegrations,
):
    """With no LLM available, the rate-suggest path must return a shaped dict."""
    ai_service = ai_service_without_emergentintegrations
    result = await ai_service.suggest_hourly_rate(
        skills=["Python", "FastAPI"],
        years_experience=5,
        location="US",
    )
    assert isinstance(result, dict), f"expected dict, got {type(result).__name__}"
    for key in ("low", "mid", "high", "currency", "rationale"):
        assert key in result, f"missing key {key!r} in {result!r}"
    assert result["low"] > 0, f"low must be positive, got {result['low']!r}"
    assert result["mid"] >= result["low"], (
        f"mid ({result['mid']}) must be >= low ({result['low']})"
    )
    assert result["high"] >= result["mid"], (
        f"high ({result['high']}) must be >= mid ({result['mid']})"
    )
    assert result["currency"] == "USD"
