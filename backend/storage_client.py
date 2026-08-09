"""Emergent Object Storage client for TalentHub attachments."""
import os
import requests
from typing import Tuple

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
APP_NAME = "talenthub"

_storage_key: str = ""


def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    if not EMERGENT_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY missing")
    r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
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
