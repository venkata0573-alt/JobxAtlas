"""In-memory object-storage mock. Test image only. Never ship.

Matches the API shape `backend/storage_client.py` speaks to
`https://integrations.emergentagent.com/objstore/api/v1/storage/*`.

Design notes:
  - Deliberately NOT a stub. This mock is an observation point.
  - Enforces the 10 MB body cap the backend also enforces
    (server.py:2293). If the backend ever stops rejecting oversized
    payloads, the mock still 413s so oversized-upload tests fail loud
    instead of silently succeeding.
  - Echoes `size` and `content_type` in the PUT response so tests can
    assert on what was actually sent, not just that the call returned 200.
  - Exposes `GET /_debug/keys` so tests can inspect stored path structure.
    S-14 wants random object keys, not guessable paths — tests should
    walk this list and assert every key has a UUID component and starts
    with the expected `{STORAGE_APP}/attachments/{user_id}/` prefix.

This mock intentionally does NOT enforce content-type or magic-byte
allowlists — those are the backend's job (server.py:2296). A mock that
enforced them would mask a regression where the backend dropped the
check. The point is that the backend does the validation; the mock just
records what got through.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response

app = FastAPI(title="atlas-storage-mock")

_KEY = "test-storage-key-static"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB — matches server.py:2293
_STORE: dict[str, tuple[bytes, str]] = {}


@app.post("/objstore/api/v1/storage/init")
async def init_storage(body: dict) -> dict:
    """Expect a `{storage_token: ...}` payload (post-S-15). Return a
    fixed test key.

    S-15: the client used to send `{emergent_key: ...}` because storage
    borrowed EMERGENT_LLM_KEY. Post-F-11 the field is `storage_token`
    and comes from its own env var. This mock rejects the old field
    name so a regression that reintroduces the coupling fails loud
    instead of silently continuing to work against the mock.

    The real service issues per-caller keys. Tests do not care about
    key rotation semantics — they only care that storage_client can
    obtain a key and use it on subsequent PUT/GET requests."""
    if "storage_token" not in body:
        raise HTTPException(
            400,
            f"init payload must contain 'storage_token' (S-15). Got keys: {sorted(body)}",
        )
    return {"storage_key": _KEY}


@app.put("/objstore/api/v1/storage/objects/{path:path}")
async def put_object(path: str, request: Request) -> dict:
    if request.headers.get("X-Storage-Key") != _KEY:
        raise HTTPException(401, "bad storage key")
    body = await request.body()
    if len(body) > _MAX_BYTES:
        # Match the real service's shape when payload exceeds the cap.
        # Backend already enforces 10 MB before we see it (server.py:2293);
        # this 413 is defense-in-depth for any future path that bypasses
        # the backend check.
        raise HTTPException(413, f"payload too large ({len(body)} > {_MAX_BYTES})")
    ctype = request.headers.get("Content-Type", "application/octet-stream")
    _STORE[path] = (body, ctype)
    # Response includes size + content_type so tests can assert on what
    # actually arrived. `storage_client.py:38` reads result["path"] — the
    # rest of the fields are additive.
    return {"path": path, "size": len(body), "content_type": ctype}


@app.get("/objstore/api/v1/storage/objects/{path:path}")
async def get_object(path: str, request: Request):
    if request.headers.get("X-Storage-Key") != _KEY:
        raise HTTPException(401, "bad storage key")
    if path not in _STORE:
        raise HTTPException(404, "not found")
    body, ctype = _STORE[path]
    return Response(content=body, media_type=ctype)


@app.delete("/objstore/api/v1/storage/objects/{path:path}")
async def delete_object(path: str, request: Request) -> dict:
    if request.headers.get("X-Storage-Key") != _KEY:
        raise HTTPException(401, "bad storage key")
    _STORE.pop(path, None)
    return {"deleted": path}


# ---- observation surface ---------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"ok": True, "objects": len(_STORE)}


@app.get("/_debug/keys")
async def debug_keys() -> dict:
    """Every stored key + its metadata. Tests use this to assert path
    structure (S-14: random keys, not guessable) and to check that a
    specific upload actually landed. Not a real-service endpoint —
    strictly for the mock."""
    return {
        "count": len(_STORE),
        "keys": [
            {"path": p, "size": len(body), "content_type": ct}
            for p, (body, ct) in sorted(_STORE.items())
        ],
    }


@app.post("/_debug/reset")
async def debug_reset() -> dict:
    """Wipe all stored objects. clean_db in conftest.py should call this
    between tests so uploads from one test don't bleed into another's
    /_debug/keys assertions."""
    n = len(_STORE)
    _STORE.clear()
    return {"cleared": n}
