"""Phase 1b tests — FEATURES.md §8 shortlist + broadcast (split out of
§8's marketplace/discovery because shortlist is a distinct feature with
its own auth model and lifecycle).

Coverage:
- POST /api/shortlist — add a talent
- GET /api/shortlist — list employer's shortlist
- DELETE /api/shortlist/{talent_id} — remove
- POST /api/shortlist/broadcast — send "ready to hire" note
- GET /api/shortlist/broadcasts — employer-side broadcast history (also
  in F-04 as a no-UI candidate; test proves it works if wired up)
- GET /api/talent/me/broadcasts — talent-side broadcast inbox
- POST /api/talent/me/broadcasts/{id}/read — mark read

Not covered here: the SSE stream at /api/talent/me/broadcasts/stream —
that endpoint reads the cookie inline + does its own jwt.decode without
touching get_current_user, and the conftest's sse_token_for_talent_clean
fixture is the harness template for it. Left for a dedicated SSE test.
"""
from __future__ import annotations

import pytest

from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# Helper: employer_card is the seeded employer with hours_balance=1000.
# talent_clean is the seeded verified talent.

def _shortlist_payload(talent_id: str, name: str = "Talent Clean") -> dict:
    return {
        "talent_id": talent_id, "talent_name": name,
        "headline": "Full-stack engineer", "location": "Remote",
        "hourly_rate": 60, "skills": ["React", "Python"],
    }


# ============================================================================
# 1. POST /api/shortlist — add
# ============================================================================

class TestShortlistAdd:
    async def test_anon_401(self, anon_client):
        r = await anon_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        assert r.status_code == 401

    async def test_talent_403(self, talent_clean_client):
        r = await talent_clean_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_FLAGGED_ID),
        )
        assert r.status_code == 403, r.text

    async def test_employer_adds_and_upserts(
        self, employer_card_client, db,
    ):
        r = await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["count"] == 1

        # Adding the same talent again upserts, not double-inserts.
        r2 = await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        assert r2.status_code == 200
        assert r2.json()["count"] == 1, (
            "Re-adding the same talent must upsert, not create a second row."
        )
        rows = await db.shortlists.count_documents({
            "employer_id": seed_mod.EMPLOYER_CARD_ID,
            "talent_id": seed_mod.TALENT_CLEAN_ID,
        })
        assert rows == 1


# ============================================================================
# 2. GET /api/shortlist — list
# ============================================================================

class TestShortlistList:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/shortlist")
        assert r.status_code == 401

    async def test_talent_403(self, talent_clean_client):
        r = await talent_clean_client.get("/api/shortlist")
        assert r.status_code == 403

    async def test_employer_gets_scoped_list(
        self, employer_card_client, employer_nocard_client, db,
    ):
        """Adding for employer_card must not leak to employer_nocard's list."""
        r = await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        assert r.status_code == 200

        my = await employer_card_client.get("/api/shortlist")
        assert my.status_code == 200
        assert my.json()["count"] == 1

        other = await employer_nocard_client.get("/api/shortlist")
        assert other.status_code == 200
        assert other.json()["count"] == 0, (
            "Shortlist must be scoped per-employer — no cross-tenant leak."
        )


# ============================================================================
# 3. DELETE /api/shortlist/{talent_id} — remove
# ============================================================================

class TestShortlistRemove:
    async def test_anon_401(self, anon_client):
        r = await anon_client.delete(
            f"/api/shortlist/{seed_mod.TALENT_CLEAN_ID}"
        )
        assert r.status_code == 401

    async def test_talent_403(self, talent_clean_client):
        r = await talent_clean_client.delete(
            f"/api/shortlist/{seed_mod.TALENT_CLEAN_ID}"
        )
        assert r.status_code == 403

    async def test_employer_removes(self, employer_card_client):
        await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        r = await employer_card_client.delete(
            f"/api/shortlist/{seed_mod.TALENT_CLEAN_ID}"
        )
        assert r.status_code == 200
        assert r.json()["count"] == 0


# ============================================================================
# 4. POST /api/shortlist/broadcast — send "ready to hire"
# ============================================================================

class TestShortlistBroadcast:
    async def test_anon_401(self, anon_client):
        r = await anon_client.post(
            "/api/shortlist/broadcast", json={"message": "Hi"},
        )
        assert r.status_code == 401

    async def test_talent_403(self, talent_clean_client):
        r = await talent_clean_client.post(
            "/api/shortlist/broadcast", json={"message": "Hi"},
        )
        assert r.status_code == 403

    async def test_empty_shortlist_returns_400(self, employer_nocard_client):
        """employer_nocard has an empty shortlist by default."""
        r = await employer_nocard_client.post(
            "/api/shortlist/broadcast",
            json={"message": "Ready to hire — 20h/wk"},
        )
        assert r.status_code == 400, r.text
        assert "empty" in r.text.lower()

    async def test_employer_broadcasts_and_delivers_to_talent(
        self, employer_card_client, db,
    ):
        """Add talent_clean to shortlist, then broadcast. talent_clean
        must have a broadcasts row (delivered) even though email fails
        silent (no RESEND_API_KEY in test env)."""
        await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        r = await employer_card_client.post(
            "/api/shortlist/broadcast",
            json={"message": "Ready to hire — 20h/wk, starting Monday."},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("delivered", 0) >= 1
        # Curated talents in the shortlist are skipped; talent_clean isn't
        # curated, so the count should include her.
        # emailed=0 is expected — no RESEND_API_KEY in .env.test.
        assert body.get("emailed", 0) == 0

        # broadcast row persisted for the talent (feeds /talent/me/broadcasts).
        rows = await db.broadcasts.count_documents({
            "talent_id": seed_mod.TALENT_CLEAN_ID,
            "employer_id": seed_mod.EMPLOYER_CARD_ID,
        })
        assert rows >= 1


# ============================================================================
# 5. GET /api/shortlist/broadcasts — employer broadcast history
# ============================================================================

class TestBroadcastHistory:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/shortlist/broadcasts")
        assert r.status_code == 401

    async def test_talent_403(self, talent_clean_client):
        r = await talent_clean_client.get("/api/shortlist/broadcasts")
        assert r.status_code == 403

    async def test_employer_gets_own_history(self, employer_card_client):
        """After sending one broadcast, history should contain a run."""
        await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        await employer_card_client.post(
            "/api/shortlist/broadcast",
            json={"message": "Ready to hire."},
        )
        r = await employer_card_client.get("/api/shortlist/broadcasts")
        assert r.status_code == 200, r.text
        # Endpoint currently returns {runs: [...]} per server.py:2204.
        body = r.json()
        assert "runs" in body


# ============================================================================
# 6. GET /api/talent/me/broadcasts — talent inbox
# ============================================================================

class TestTalentBroadcastInbox:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/talent/me/broadcasts")
        assert r.status_code == 401

    async def test_employer_gets_empty(self, employer_card_client):
        """Endpoint short-circuits to empty for non-talent roles (server.py:2122)."""
        r = await employer_card_client.get("/api/talent/me/broadcasts")
        assert r.status_code == 200
        body = r.json()
        assert body == {"items": [], "count": 0, "unread": 0}

    async def test_talent_sees_broadcast_after_send(
        self, employer_card_client, talent_clean_client,
    ):
        """End-to-end: employer_card broadcasts → talent_clean sees it
        in her inbox."""
        await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        await employer_card_client.post(
            "/api/shortlist/broadcast",
            json={"message": "Ready to hire — testing inbox delivery."},
        )
        r = await talent_clean_client.get("/api/talent/me/broadcasts")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1
        assert body["unread"] >= 1


# ============================================================================
# 7. POST /api/talent/me/broadcasts/{id}/read — mark read
# ============================================================================

class TestMarkBroadcastRead:
    async def test_anon_401(self, anon_client):
        r = await anon_client.post(
            "/api/talent/me/broadcasts/some-id/read"
        )
        assert r.status_code == 401

    async def test_talent_marks_own_broadcast_read(
        self, employer_card_client, talent_clean_client,
    ):
        """Setup: broadcast lands in inbox. Mark it read. Unread count drops."""
        await employer_card_client.post(
            "/api/shortlist",
            json=_shortlist_payload(seed_mod.TALENT_CLEAN_ID),
        )
        await employer_card_client.post(
            "/api/shortlist/broadcast", json={"message": "read-mark test"},
        )
        r_list = await talent_clean_client.get("/api/talent/me/broadcasts")
        b_id = r_list.json()["items"][0]["id"]
        r_mark = await talent_clean_client.post(
            f"/api/talent/me/broadcasts/{b_id}/read"
        )
        assert r_mark.status_code == 200
        r_after = await talent_clean_client.get("/api/talent/me/broadcasts")
        assert r_after.json()["unread"] == 0
