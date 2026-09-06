"""Phase 1b tests — FEATURES.md §9 EOI (Expression of Interest).

Endpoints covered:
- POST /api/eoi — talent raises an EOI (targeted or open)
- GET /api/eoi — role-scoped listing
- POST /api/eoi/{id}/accept — employer accepts, auto-creates engagement
- POST /api/eoi/{id}/withdraw — talent withdraws (owner check)

Note on the /withdraw endpoint: the task checklist said this was already
covered by test_11_engagements.py, but grep -n "eoi" backend/tests/test_
11_engagements.py returned zero matches. Covering it here — it's the
natural home for EOI tests, and leaving it uncovered would defeat the
"cross-tenant → 404" ownership assertion for the EOI domain.

Manual steps (FEATURES.md §9) covered:
- Step 1: Alex (talent_clean) posts an EOI targeting employer_card
- Step 2: employer_card sees the EOI in list, accepts → engagement created
- Step 3: The new engagement is visible via GET /api/engagements
"""
from __future__ import annotations

import pytest

from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# ============================================================================
# Manual steps §9
# ============================================================================

class TestManualSteps:
    async def test_step_1_talent_posts_eoi_to_employer(
        self, talent_clean_client, db,
    ):
        r = await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "proposed_hours_per_week": 20,
                  "start_date": "2026-10-01",
                  "message": "Interested in the broadcast."},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "open"
        assert body["talent_id"] == seed_mod.TALENT_CLEAN_ID
        assert body["employer_id"] == seed_mod.EMPLOYER_CARD_ID
        assert body["employer_name"] == "Employer Card-On-File", (
            "EOI must denormalise employer_name for the employer's inbox UI"
        )

    async def test_step_2_employer_sees_incoming_eoi(
        self, talent_clean_client, employer_card_client,
    ):
        # Post the EOI first
        await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "proposed_hours_per_week": 20,
                  "message": "Interested in the broadcast."},
        )
        r = await employer_card_client.get("/api/eoi")
        assert r.status_code == 200, r.text
        items = r.json()
        assert len(items) >= 1
        assert any(x["talent_id"] == seed_mod.TALENT_CLEAN_ID for x in items)

    async def test_step_3_employer_accepts_and_engagement_is_created(
        self, talent_clean_client, employer_card_client, db,
    ):
        # Setup: post EOI
        eoi_r = await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "proposed_hours_per_week": 20,
                  "message": "Interested."},
        )
        eoi_id = eoi_r.json()["id"]

        # Accept
        r = await employer_card_client.post(
            f"/api/eoi/{eoi_id}/accept",
            json={"scope": "Sprint 1 delivery"},
        )
        assert r.status_code == 200, r.text
        eng = r.json()
        assert eng["employer_id"] == seed_mod.EMPLOYER_CARD_ID
        assert eng["talent_id"] == seed_mod.TALENT_CLEAN_ID
        assert eng["status"] == "pending_signatures"
        assert eng["from_eoi_id"] == eoi_id

        # EOI is stamped accepted with the engagement id
        e = await db.eois.find_one({"id": eoi_id})
        assert e["status"] == "accepted"
        assert e["engagement_id"] == eng["id"]

        # Engagement exists in the engagements collection
        e_doc = await db.engagements.find_one({"id": eng["id"]})
        assert e_doc is not None


# ============================================================================
# POST /api/eoi — negatives
# ============================================================================

class TestEoiCreate:
    async def test_anon_401(self, anon_client):
        r = await anon_client.post(
            "/api/eoi",
            json={"message": "Interested.", "employer_id": None},
        )
        assert r.status_code == 401

    async def test_employer_role_403(self, employer_card_client):
        r = await employer_card_client.post(
            "/api/eoi",
            json={"message": "Employer trying to post an EOI",
                  "employer_id": None},
        )
        assert r.status_code == 403, r.text

    async def test_admin_role_403(self, admin_all_client):
        r = await admin_all_client.post(
            "/api/eoi",
            json={"message": "Admin trying to post an EOI",
                  "employer_id": None},
        )
        assert r.status_code == 403

    async def test_unknown_employer_id_404(self, talent_clean_client):
        r = await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": "does-not-exist",
                  "message": "Message for a ghost employer."},
        )
        assert r.status_code == 404, r.text

    async def test_targeting_wrong_role_404(self, talent_clean_client):
        """The endpoint filters by role=employer; supplying another
        talent's id → 404 (server.py:2471-2473)."""
        r = await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.TALENT_FLAGGED_ID,
                  "message": "Wrong-role target."},
        )
        assert r.status_code == 404

    async def test_open_eoi_no_employer_id_is_allowed(self, talent_clean_client):
        """FEATURES.md §9 says employer_id may be None for an open EOI."""
        r = await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": None,
                  "message": "Open EOI — any employer welcome."},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["employer_id"] is None
        assert body["employer_name"] is None


# ============================================================================
# GET /api/eoi — role scoping
# ============================================================================

class TestEoiList:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/eoi")
        assert r.status_code == 401

    async def test_talent_sees_only_own(
        self, talent_clean_client, talent_flagged_client,
    ):
        """talent_clean's list must not include talent_flagged's EOIs."""
        # talent_flagged posts one
        r_other = await talent_flagged_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "message": "Flagged talent EOI"},
        )
        assert r_other.status_code == 200
        other_id = r_other.json()["id"]

        r = await talent_clean_client.get("/api/eoi")
        assert r.status_code == 200
        ids = {x["id"] for x in r.json()}
        assert other_id not in ids, (
            f"Cross-tenant leak: talent_clean saw talent_flagged's EOI "
            f"{other_id}. Handler at server.py:2491 must scope by talent_id."
        )

    async def test_employer_sees_own_targeted_and_open(
        self, talent_clean_client, employer_card_client, employer_nocard_client,
    ):
        """Employers see EOIs targeting them + any open (employer_id=None)."""
        # Post one targeted to employer_card
        await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "message": "Targeted."},
        )
        # Post one open
        await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": None, "message": "Open."},
        )

        r_card = await employer_card_client.get("/api/eoi")
        assert r_card.status_code == 200
        card_items = r_card.json()
        # Both should be visible to employer_card
        assert len(card_items) >= 2

        # employer_nocard should ONLY see the open one, not the targeted one.
        r_nocard = await employer_nocard_client.get("/api/eoi")
        assert r_nocard.status_code == 200
        nocard_items = r_nocard.json()
        # Every visible item must be either targeting nocard OR open.
        for it in nocard_items:
            assert (it.get("employer_id") == seed_mod.EMPLOYER_NOCARD_ID
                    or it.get("employer_id") is None), (
                f"employer_nocard leaked a targeted EOI: {it}"
            )


# ============================================================================
# POST /api/eoi/{id}/accept — role + hours-balance + state
# ============================================================================

class TestEoiAccept:
    async def _make_eoi(self, talent_client) -> str:
        r = await talent_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "proposed_hours_per_week": 20,
                  "message": "Accept-me EOI"},
        )
        assert r.status_code == 200
        return r.json()["id"]

    async def test_anon_401(self, anon_client, talent_clean_client):
        eoi_id = await self._make_eoi(talent_clean_client)
        r = await anon_client.post(f"/api/eoi/{eoi_id}/accept", json={})
        assert r.status_code == 401

    async def test_talent_role_403(self, talent_clean_client):
        eoi_id = await self._make_eoi(talent_clean_client)
        r = await talent_clean_client.post(
            f"/api/eoi/{eoi_id}/accept", json={},
        )
        assert r.status_code == 403, r.text

    async def test_unknown_eoi_404(self, employer_card_client):
        r = await employer_card_client.post(
            "/api/eoi/does-not-exist/accept", json={},
        )
        assert r.status_code == 404

    async def test_insufficient_hours_balance_400(
        self, talent_clean_client, employer_nocard_client, db,
    ):
        """employer_nocard has hours_balance=100 (seed); accept with hours>100
        must 400. Set hours_balance low to force the error."""
        await db.users.update_one(
            {"id": seed_mod.EMPLOYER_NOCARD_ID},
            {"$set": {"hours_balance": 5}},
        )
        # Post open EOI so nocard can accept it
        r_eoi = await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": None, "proposed_hours_per_week": 20,
                  "message": "Open EOI for nocard"},
        )
        eoi_id = r_eoi.json()["id"]
        r = await employer_nocard_client.post(
            f"/api/eoi/{eoi_id}/accept",
            json={"hours": 20},
        )
        assert r.status_code == 400, r.text
        assert "hours" in r.text.lower()

    async def test_already_accepted_eoi_returns_400(
        self, talent_clean_client, employer_card_client,
    ):
        eoi_id = await self._make_eoi(talent_clean_client)
        r1 = await employer_card_client.post(
            f"/api/eoi/{eoi_id}/accept", json={},
        )
        assert r1.status_code == 200
        r2 = await employer_card_client.post(
            f"/api/eoi/{eoi_id}/accept", json={},
        )
        assert r2.status_code == 400, r2.text

    async def test_engagement_hours_default_from_proposed(
        self, talent_clean_client, employer_card_client, db,
    ):
        """When accept payload omits `hours`, engagement uses the EOI's
        proposed_hours_per_week (server.py:2510)."""
        r_eoi = await talent_clean_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "proposed_hours_per_week": 15,
                  "message": "hours-default test"},
        )
        eoi_id = r_eoi.json()["id"]
        r = await employer_card_client.post(
            f"/api/eoi/{eoi_id}/accept", json={},
        )
        assert r.status_code == 200, r.text
        assert r.json()["hours_allocated"] == 15


# ============================================================================
# POST /api/eoi/{id}/withdraw — owner check (S-11 shape: 404 on wrong-tenant)
# ============================================================================

class TestEoiWithdraw:
    async def _make_eoi(self, talent_client) -> str:
        r = await talent_client.post(
            "/api/eoi",
            json={"employer_id": seed_mod.EMPLOYER_CARD_ID,
                  "message": "Withdraw-me EOI"},
        )
        assert r.status_code == 200
        return r.json()["id"]

    async def test_anon_401(self, anon_client, talent_clean_client):
        eoi_id = await self._make_eoi(talent_clean_client)
        r = await anon_client.post(f"/api/eoi/{eoi_id}/withdraw")
        assert r.status_code == 401

    async def test_owner_talent_withdraws_ok(
        self, talent_clean_client, db,
    ):
        eoi_id = await self._make_eoi(talent_clean_client)
        r = await talent_clean_client.post(f"/api/eoi/{eoi_id}/withdraw")
        assert r.status_code == 200
        e = await db.eois.find_one({"id": eoi_id})
        assert e["status"] == "withdrawn"

    async def test_cross_tenant_talent_gets_404_not_403(
        self, talent_clean_client, talent_flagged_client,
    ):
        """S-11 shape: cross-tenant returns 404, not 403 (no id-exists
        side channel). server.py:2537 already implements this."""
        eoi_id = await self._make_eoi(talent_clean_client)
        r = await talent_flagged_client.post(f"/api/eoi/{eoi_id}/withdraw")
        assert r.status_code == 404, r.text

    async def test_employer_gets_404_on_talent_owned_eoi(
        self, talent_clean_client, employer_card_client,
    ):
        """Employers aren't the talent owner of EOIs; the handler treats
        them as non-owner → 404."""
        eoi_id = await self._make_eoi(talent_clean_client)
        r = await employer_card_client.post(f"/api/eoi/{eoi_id}/withdraw")
        assert r.status_code == 404
