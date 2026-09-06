"""Test image ONLY. Never ship this file in a prod image.

Python's `site` module imports `sitecustomize` automatically at interpreter
startup, before anything else in the process (including uvicorn's app import).
That gives us a place to point the Stripe SDK at `stripe-mock` for the entire
backend process — pytest, Playwright, curl, everyone — with zero application
code change.

Delivered via `backend/Dockerfile.test` copying this file into
`/usr/local/lib/python3.11/site-packages/sitecustomize.py`. Site-packages is
on sys.path unconditionally and lives outside the `.:/app` bind-mount, so
compose can't accidentally shadow this file with an empty copy from the repo.

Contract:
  - If STRIPE_API_BASE is set, override `stripe.api_base` to point at it.
  - If COVERAGE_PROCESS_START is set, start coverage.py in this process
    (uvicorn, pytest, one-shot scripts — all get traced).
  - If neither is set, do nothing — image is still safe to boot for
    pytest-only runs that don't touch Stripe or need coverage.

Failure mode this exists to prevent: one bad env var → app talks to
api.stripe.com in CI with a test secret and returns 401s that look like app
bugs. `test_00_smoke.py::test_stripe_api_base_is_the_mock` will fail loudly
if this file is ever missing from the image."""

import os

# ---- Test-only Stripe injection --------------------------------------------
_api_base = os.environ.get("STRIPE_API_BASE")
if _api_base:
    try:
        import stripe
    except ImportError:
        pass
    else:
        stripe.api_base = _api_base


# ---- Test-only sub-process coverage collection -----------------------------
# Backend/uvicorn is a different process from pytest, so pytest-cov's in-
# process tracer sees NONE of the code the app actually executes on an HTTPS
# request. This block wires coverage.py's standard subprocess-coverage
# pattern: when COVERAGE_PROCESS_START is set (test image only), any Python
# process — including uvicorn — auto-starts a coverage tracer bound to the
# config the env var points at. Data files land under `data_file` from the
# .coveragerc (see backend/.coveragerc) and get combined via
# `make coverage-gaps`.
if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage
    except ImportError:
        pass
    else:
        coverage.process_startup()
