"""Stripe webhook signing fixtures for local money-path tests.

Why this exists:
    stripe-mock (docker-compose.test.yml) returns canned SDK responses
    but cannot SIGN webhooks — it has no private key that matches the
    STRIPE_WEBHOOK_SECRET the app runs with. `stripe.Webhook.construct_
    event` at `server.py:560` therefore can't be exercised against
    stripe-mock. This module rebuilds the exact wire format Stripe uses
    (v1 HMAC over `timestamp.payload`) using the SAME secret the app
    reads from env, so tests can deliver a payload the app accepts and
    the webhook handler processes end-to-end.

Signing algorithm (Stripe's official spec):
    1. Serialize the event dict as compact JSON, encode to bytes.
    2. Concatenate `f"{unix_ts}.{payload}"` (the "signed payload").
    3. HMAC-SHA256 with the secret; hex-encode.
    4. Header format: `t=<unix_ts>,v1=<hex_sig>` (Stripe also emits v0
       for legacy but v1 is required — construct_event only checks v1).

References:
    - https://docs.stripe.com/webhooks/signatures
    - `stripe.Webhook.construct_event` (stripe python SDK): validates
      the header, checks timestamp within `tolerance` (default 300s),
      and computes HMAC over the raw payload. Any mismatch → raises
      `stripe.error.SignatureVerificationError`.

Usage:
    payload, headers = checkout_session_completed(
        session_id="cs_test_milestone_1", kind="milestone",
        metadata={"milestone_id": "m1", "invoice_id": "inv1"},
    )
    r = await anon_client.post("/api/stripe/webhook",
                               content=payload, headers=headers)
    assert r.status_code == 200
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Optional


# Read the secret from the same config.py the backend reads. Guarantees
# fixture and handler agree on the key even if .env.test is rotated.
from config import settings


DEFAULT_SECRET: str = settings.stripe.webhook_secret

# Stripe's default construct_event tolerance is 300s. Set STALE > 300 to
# force rejection; the test at test_stale_timestamp_rejected uses 400s.
STRIPE_DEFAULT_TOLERANCE_SECONDS = 300


# ---------- Signing primitive ------------------------------------------------

def sign_payload(
    payload: bytes,
    *,
    secret: Optional[str] = None,
    timestamp: Optional[int] = None,
) -> str:
    """Compute the `Stripe-Signature` header value for a raw payload.

    Args:
        payload: Raw JSON bytes exactly as they'll be POSTed. Byte-exact
            matters — one whitespace difference invalidates the HMAC.
        secret: Override for testing bad-secret behaviour. Defaults to
            settings.stripe.webhook_secret (the same env value the app
            reads at boot).
        timestamp: Unix seconds for the `t=` field. Defaults to `now()`.
            Set explicitly to test stale-timestamp rejection.

    Returns:
        A `t=<unix>,v1=<hex_sig>` header value ready for
        `headers["Stripe-Signature"]`.
    """
    if secret is None:
        secret = DEFAULT_SECRET
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    v1 = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={v1}"


def build_headers(payload: bytes, **sign_kwargs) -> dict:
    """Return the full headers dict for a webhook POST — Stripe-Signature
    plus Content-Type. Convenience wrapper around sign_payload."""
    return {
        "Stripe-Signature": sign_payload(payload, **sign_kwargs),
        "Content-Type": "application/json",
    }


# ---------- Event body factories --------------------------------------------

def _serialize(event: dict) -> bytes:
    """Compact JSON identical to what Stripe emits. `separators` matters —
    HMAC is byte-exact so `{"a": 1}` and `{"a":1}` produce different
    signatures. Stripe uses no-whitespace JSON."""
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _envelope(*, event_id: str, event_type: str, obj: dict) -> dict:
    """Wrap an object in Stripe's standard event envelope. Fields match
    what construct_event + the handler at server.py:563 read."""
    return {
        "id": event_id,
        "object": "event",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "type": event_type,
        "livemode": False,
        "data": {"object": obj},
        "request": {"id": None, "idempotency_key": None},
    }


def checkout_session_completed(
    *,
    session_id: str = "cs_test_fixture_default",
    kind: str = "hours_purchase",
    metadata: Optional[dict] = None,
    payment_intent: Optional[str] = "pi_test_fixture_default",
    amount_total: int = 4900,
    currency: str = "usd",
) -> tuple[bytes, dict]:
    """Build a signed `checkout.session.completed` event.

    The handler at server.py:564 branches on `metadata.kind`:
      - "dispute_fee" → mark_dispute_fee_paid (revisions.py)
      - "milestone"   → project milestones + invoices
      - anything else (or missing) → hours-purchase (default branch)

    The default kind here is "hours_purchase" — matches the fallback
    handler branch. Override `kind` + `metadata` to exercise the
    dispute_fee / milestone paths.

    Returns:
        `(payload_bytes, headers_dict)` — POST directly with
        `client.post(url, content=payload, headers=headers)`.
    """
    meta = dict(metadata or {})
    if kind and "kind" not in meta:
        meta["kind"] = kind
    obj = {
        "id": session_id,
        "object": "checkout.session",
        "amount_total": amount_total,
        "currency": currency,
        "payment_intent": payment_intent,
        "payment_status": "paid",
        "status": "complete",
        "mode": "payment",
        "metadata": meta,
    }
    event = _envelope(
        event_id=f"evt_test_{session_id}",
        event_type="checkout.session.completed",
        obj=obj,
    )
    payload = _serialize(event)
    return payload, build_headers(payload)


def payment_intent_succeeded(
    *,
    pi_id: str = "pi_test_fixture_default",
    amount: int = 4900,
    currency: str = "usd",
) -> tuple[bytes, dict]:
    """Signed `payment_intent.succeeded` event.

    Note: the current handler at server.py:563-596 only branches on
    `checkout.session.completed`. This event type falls through to the
    top-level `return {"ok": True}` — 200 no-op. Included in the
    factories so tests can prove the signing shape works for it too
    (and for future handlers that add PI-level logic)."""
    obj = {
        "id": pi_id, "object": "payment_intent",
        "amount": amount, "currency": currency,
        "status": "succeeded", "metadata": {},
    }
    event = _envelope(
        event_id=f"evt_test_{pi_id}",
        event_type="payment_intent.succeeded",
        obj=obj,
    )
    payload = _serialize(event)
    return payload, build_headers(payload)


def charge_refunded(
    *,
    charge_id: str = "ch_test_fixture_default",
    refund_id: str = "re_test_fixture_default",
    payment_intent: str = "pi_test_fixture_default",
    amount_refunded: int = 4900,
) -> tuple[bytes, dict]:
    """Signed `charge.refunded` event. Currently a no-op in the handler
    (falls through). Included for the same forward-compat reason as
    payment_intent_succeeded."""
    obj = {
        "id": charge_id, "object": "charge",
        "amount_refunded": amount_refunded,
        "payment_intent": payment_intent,
        "refunded": True,
        "refunds": {"data": [{"id": refund_id, "amount": amount_refunded}]},
        "metadata": {},
    }
    event = _envelope(
        event_id=f"evt_test_{charge_id}",
        event_type="charge.refunded",
        obj=obj,
    )
    payload = _serialize(event)
    return payload, build_headers(payload)


# ---------- Adversarial variants (bad sig / stale ts / malformed) -----------

def with_bad_signature(payload: bytes) -> dict:
    """Return headers with a syntactically-valid but wrong v1 signature.
    Header shape is intact so we exercise the HMAC verification path,
    not just the header-parse path."""
    fake = hashlib.sha256(b"not-the-real-secret").hexdigest()
    return {
        "Stripe-Signature": f"t={int(time.time())},v1={fake}",
        "Content-Type": "application/json",
    }


def with_stale_timestamp(
    payload: bytes,
    *,
    age_seconds: int = STRIPE_DEFAULT_TOLERANCE_SECONDS + 100,
) -> dict:
    """Sign the payload correctly but backdate the timestamp past
    construct_event's tolerance window (default 300s). The HMAC is
    valid — the rejection comes from the timestamp check."""
    ts = int(time.time()) - age_seconds
    return {
        "Stripe-Signature": sign_payload(payload, timestamp=ts),
        "Content-Type": "application/json",
    }


def with_malformed_header(payload: bytes) -> dict:
    """Return headers whose Stripe-Signature value doesn't parse at all
    (missing `v1=`, no timestamp, wrong shape). Exercises the header-
    parsing branch of construct_event."""
    return {
        "Stripe-Signature": "this-is-not-a-valid-stripe-signature-header",
        "Content-Type": "application/json",
    }


# ---------- Synthetic Request builder for direct handler calls --------------

def make_webhook_request(payload: bytes, headers: dict):
    """Build a Starlette Request that `stripe_webhook` will accept when
    called directly (bypassing HTTP + uvicorn).

    Rationale: pytest runs in the same *container* as the backend, but
    it's a separate *process* from uvicorn. Monkey-patches applied in
    pytest are invisible to the backend process, so any test that needs
    to force a fault in a downstream helper (e.g. S-03 xfail for
    `mark_dispute_fee_paid`) has to call the handler in-process. This
    helper builds the minimal ASGI scope + receive callable the handler
    needs; construct_event still fires + validates the signature end-
    to-end, so this is not a mock — it's the real code path.
    """
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/stripe/webhook",
        "raw_path": b"/api/stripe/webhook",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in headers.items()
        ],
        "query_string": b"",
        "root_path": "",
        "http_version": "1.1",
        "scheme": "https",
        "server": ("localhost", 443),
        "client": ("127.0.0.1", 12345),
    }
    sent = False

    async def _receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(scope, _receive)
