"""Object Storage client for Job Atlas attachments."""
import requests
from typing import Tuple

# F-11: config is the sole env boundary.
from config import settings

# S-27 CLOSED: fallback to integrations.emergentagent.com removed.
#              INTEGRATION_PROXY_URL is required at boot.
# S-15 CLOSED: STORAGE_TOKEN replaces the borrowed EMERGENT_LLM_KEY —
#              storage no longer shares an auth secret with the LLM.
# STORAGE_BASE preserved (thin proxy for settings.storage.proxy_url)
# so tests that assert on it — notably the S-27 guardrail in
# tests/test_00_smoke.py::test_storage_client_base_matches_env — keep
# a stable attribute to check.
STORAGE_BASE = settings.storage.proxy_url.rstrip("/")
STORAGE_URL = STORAGE_BASE + "/objstore/api/v1/storage"
STORAGE_TOKEN = settings.storage.token
APP_NAME = "talenthub"

_storage_key: str = ""


def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    # S-15: the `if not EMERGENT_KEY: raise RuntimeError(...)` guard is
    # gone. Uploads must never depend on LLM config again; STORAGE_TOKEN
    # is required at boot, so we can rely on it here.
    r = requests.post(
        f"{STORAGE_URL}/init",
        json={"storage_token": STORAGE_TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    _storage_key = r.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    try:
        r = requests.put(f"{STORAGE_URL}/objects/{path}",
                         headers={"X-Storage-Key": key, "Content-Type": content_type},
                         data=data, timeout=120)
        if r.status_code == 404:
            key = init_storage(force=True)
            r = requests.put(f"{STORAGE_URL}/objects/{path}",
                             headers={"X-Storage-Key": key, "Content-Type": content_type},
                             data=data, timeout=120)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise RuntimeError(f"Upload failed: {e}") from e


def get_object(path: str) -> Tuple[bytes, str]:
    key = init_storage()
    r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if r.status_code == 404:
        key = init_storage(force=True)
        r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")
