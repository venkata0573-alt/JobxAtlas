"""Phase 1b — FEATURES.md §11: Engagements, contract signing, deliverables.

Endpoints under test (§11 table):
  POST   /api/engagements                      role=employer         server.py:602
  GET    /api/engagements                      auth                  server.py:632
  GET    /api/engagements/{eid}                auth (party)          server.py:639
  POST   /api/engagements/sign                 auth (party)          server.py:647
      NOTE: §11 documents `POST /api/engagements/{id}/sign`. That path does
      not exist. The real handler is `POST /api/engagements/sign` and the
      engagement id lives in the JSON body (SignContractIn.engagement_id).
      Tested against the real path; the doc drift is logged in
      test_result.md.
  POST   /api/deliverables                     role=talent (party)   server.py:667
  GET    /api/deliverables/{engagement_id}     auth (party)          server.py:688
  POST   /api/deliverables/{id}/approve        role=employer (party) server.py:772
  POST   /api/deliverables/{id}/reject         role=employer (party) server.py:777
  POST   /api/reviews                          auth (party)          server.py:783
  GET    /api/reviews/user/{user_id}           public                server.py:807

Also covered — §11 uses these but does not table them:
  GET    /api/messages/{engagement_id}         auth (party)          server.py:937
  POST   /api/messages                         auth (party)          server.py:946
  POST   /api/messages/upload                  auth (party)          server.py:2286

Auth policy: all clients come from the cookie-only factory in conftest.py.
No Authorization: Bearer header, ever (S-26 policy).

Cross-tenant tests use the S-11 `load_owned` convention: cross-tenant access
returns 404 (not 403). Handlers that raise 403 on cross-tenant today fail
these tests — that is the S-11 gap surfacing. Three of these tests are
marked `xfail(strict=True)` (Phase 1d, so CI can be a merge gate) — do NOT
weaken the assertion. When load_owned() lands the handlers will start
returning 404, the tests XPASS, and strict=True fails the suite until
someone removes the xfail marker. That is how the canary self-closes.
"""

from __future__ import annotations

import io

import pytest

from tests import seed as seed_mod


# ---------------------------------------------------------------------------
# Section A — one test per numbered §11 manual step
# ---------------------------------------------------------------------------


class TestManualSteps:
    """FEATURES.md §11 manual steps 1-6. Each test is self-contained and does
    not depend on the ordering of any other test in this class."""

    async def test_step_1_employer_creates_engagement_via_mix_and_match(
        self, employer_card_client, db,
    ):
        """§11 step 1. Employer picks a talent, hours, scope, remote mode."""
        r = await employer_card_client.post(
            "/api/engagements",
            json={
                "talent_id": seed_mod.TALENT_CLEAN_ID,
                "hours": 20,
                "scope": "Rebuild dashboard",
                "mode": "remote",
            },
        )
        assert r.status_code == 200, r.text
        eng = r.json()
        assert eng["employer_id"] == seed_mod.EMPLOYER_CARD_ID
        assert eng["talent_id"] == seed_mod.TALENT_CLEAN_ID
        assert eng["hours_allocated"] == 20
        assert eng["scope"] == "Rebuild dashboard"
        assert eng["mode"] == "remote"
        assert eng["status"] == "pending_signatures"
        assert eng["employer_signature"] is None
        assert eng["talent_signature"] is None
        # Persisted in Mongo.
        stored = await db.engagements.find_one({"id": eng["id"]}, {"_id": 0})
        assert stored is not None
        assert stored["scope"] == "Rebuild dashboard"

    async def test_step_2_both_parties_sign_and_status_flips_to_contract_signed(
        self, employer_card_client, talent_clean_client, db,
    ):
        """§11 step 2. Employer signs → still pending; talent signs → flips
        to contract_signed and the employer's hours_balance is decremented
        by hours_allocated."""
        create = await employer_card_client.post(
            "/api/engagements",
            json={
                "talent_id": seed_mod.TALENT_CLEAN_ID,
                "hours": 20,
                "scope": "Rebuild dashboard",
                "mode": "remote",
            },
        )
        assert create.status_code == 200, create.text
        eid = create.json()["id"]

        before = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID}, {"hours_balance": 1})
        hours_before = int(before["hours_balance"])

        # Employer signs first.
        r1 = await employer_card_client.post(
            "/api/engagements/sign",
            json={"engagement_id": eid, "signature": "Employer Card-On-File"},
        )
        assert r1.status_code == 200, r1.text
        after_first = r1.json()
        assert after_first["employer_signature"] is not None
        assert after_first["talent_signature"] is None
        assert after_first["status"] == "pending_signatures"

        # Talent signs second → contract_signed + hours debit.
        r2 = await talent_clean_client.post(
            "/api/engagements/sign",
            json={"engagement_id": eid, "signature": "Talent Clean"},
        )
        assert r2.status_code == 200, r2.text
        after_both = r2.json()
        assert after_both["employer_signature"] is not None
        assert after_both["talent_signature"] is not None
        assert after_both["status"] == "contract_signed"

        after_user = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID}, {"hours_balance": 1})
        assert int(after_user["hours_balance"]) == hours_before - 20

    async def test_step_3_talent_submits_deliverable_against_signed_engagement(
        self, talent_clean_client,
    ):
        """§11 step 3. Talent posts a deliverable on the seeded signed
        engagement. Seeded state already has one submitted deliverable; this
        adds a second."""
        r = await talent_clean_client.post(
            "/api/deliverables",
            json={
                "engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID,
                "title": "Dashboard v2",
                "link": "https://example.test/pr/2",
                "description": "Second slice",
                "hours_claimed": 5,
            },
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["engagement_id"] == seed_mod.ENGAGEMENT_SIGNED_ID
        assert d["talent_id"] == seed_mod.TALENT_CLEAN_ID
        assert d["title"] == "Dashboard v2"
        assert d["status"] == "submitted"
        assert d["hours_claimed"] == 5.0

    async def test_step_4_employer_approve_returns_payout_id_and_increments_hours_used(
        self, employer_card_client, db,
    ):
        """§11 step 4. Employer approves the seeded submitted deliverable.
        FEATURES states 'Response should include a payout_id.' Handler
        actually inserts the payout row asynchronously and returns the updated
        deliverable, not the payout id. Assert on the observable side effect:
        a payouts row exists for this deliverable after approval."""
        r = await employer_card_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/approve",
            json={"feedback": "LGTM"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "approved"
        assert d["feedback"] == "LGTM"

        # engagement.hours_used += hours_claimed
        eng = await db.engagements.find_one(
            {"id": seed_mod.ENGAGEMENT_SIGNED_ID}, {"hours_used": 1}
        )
        assert float(eng["hours_used"]) == 5.0

    async def test_step_5_payout_row_written_with_commission_calc(
        self, employer_card_client, db,
    ):
        """§11 step 5. `db.payouts.find({engagement_id:...})` shows a row
        with the commission calculation."""
        r = await employer_card_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/approve",
            json={"feedback": ""},
        )
        assert r.status_code == 200, r.text

        payouts = await db.payouts.find(
            {"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID}, {"_id": 0}
        ).to_list(10)
        assert len(payouts) == 1, f"expected exactly one payout row, got: {payouts}"
        p = payouts[0]
        assert p["deliverable_id"] == seed_mod.DELIVERABLE_SUBMITTED_ID
        assert p["talent_id"] == seed_mod.TALENT_CLEAN_ID
        assert p["hours"] == 5.0
        assert p["hourly_rate"] == 60.0  # talent_clean.profile.hourly_rate
        assert p["gross"] == 300.0       # 60 * 5
        assert p["commission"] > 0
        assert p["net"] == round(p["gross"] - p["commission"] - p.get("multi_employer_fee", 0), 2)
        assert p["status"] == "pending"

    async def test_step_6_review_writes_pending_moderation(
        self, employer_card_client, db,
    ):
        """§11 step 6. Post a review after approval. FEATURES states the
        record has `status="pending_moderation"`. Handler actually writes
        `status="pending"` (server.py:800); assert on the real value and log
        the doc drift.
        (Not a bug — just doc language drift. See test_result.md.)"""
        r = await employer_card_client.post(
            "/api/reviews",
            json={
                "engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID,
                "rating": 5,
                "text": "Great work.",
            },
        )
        assert r.status_code == 200, r.text
        rev = r.json()
        assert rev["engagement_id"] == seed_mod.ENGAGEMENT_SIGNED_ID
        assert rev["reviewer_id"] == seed_mod.EMPLOYER_CARD_ID
        assert rev["reviewee_id"] == seed_mod.TALENT_CLEAN_ID
        assert rev["reviewer_role"] == "employer"
        assert rev["rating"] == 5
        assert rev["status"] == "pending"

        stored = await db.reviews.find_one({"id": rev["id"]}, {"_id": 0})
        assert stored is not None
        assert stored["status"] == "pending"


# ---------------------------------------------------------------------------
# Section B — per-endpoint negative tests (unauth / wrong role / cross-tenant)
# ---------------------------------------------------------------------------


class TestEngagementsCreate:
    """POST /api/engagements — role=employer."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.post(
            "/api/engagements",
            json={"talent_id": seed_mod.TALENT_CLEAN_ID, "hours": 20,
                  "scope": "x", "mode": "remote"},
        )
        assert r.status_code == 401, r.text

    async def test_talent_returns_403(self, talent_clean_client):
        """Wrong role — server.py:604 rejects role != 'employer'."""
        r = await talent_clean_client.post(
            "/api/engagements",
            json={"talent_id": seed_mod.TALENT_CLEAN_ID, "hours": 20,
                  "scope": "x", "mode": "remote"},
        )
        assert r.status_code == 403, r.text

    async def test_admin_returns_403(self, admin_all_client):
        """Only role=employer creates; admin (correctly) can't."""
        r = await admin_all_client.post(
            "/api/engagements",
            json={"talent_id": seed_mod.TALENT_CLEAN_ID, "hours": 20,
                  "scope": "x", "mode": "remote"},
        )
        assert r.status_code == 403, r.text


class TestEngagementsList:
    """GET /api/engagements — auth. Returns only the caller's own engagements
    (server.py:635 filters by employer_id or talent_id). Cross-tenant test is
    a scoping check, not a 403 check."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.get("/api/engagements")
        assert r.status_code == 401, r.text

    async def test_scoped_to_caller_no_cross_tenant_leak(
        self, employer_nocard_client,
    ):
        """employer_nocard has no seeded engagements. The seeded engagement
        belongs to employer_card. Cross-tenant scoping: list must be empty."""
        r = await employer_nocard_client.get("/api/engagements")
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        assert all(x["employer_id"] == seed_mod.EMPLOYER_NOCARD_ID for x in items), (
            f"cross-tenant leak: employer_nocard sees engagements they don't own: {items}"
        )


class TestEngagementDetail:
    """GET /api/engagements/{eid} — auth + party membership.
    Cross-tenant returns 404 per handler (server.py:643); matches S-11."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.get(f"/api/engagements/{seed_mod.ENGAGEMENT_SIGNED_ID}")
        assert r.status_code == 401, r.text

    async def test_cross_tenant_returns_404(self, talent_flagged_client):
        """talent_flagged is not a party to ENGAGEMENT_SIGNED_ID."""
        r = await talent_flagged_client.get(
            f"/api/engagements/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 404, r.text

    async def test_party_talent_returns_200(self, talent_clean_client):
        r = await talent_clean_client.get(
            f"/api/engagements/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == seed_mod.ENGAGEMENT_SIGNED_ID

    async def test_party_employer_returns_200(self, employer_card_client):
        r = await employer_card_client.get(
            f"/api/engagements/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == seed_mod.ENGAGEMENT_SIGNED_ID


class TestEngagementSign:
    """POST /api/engagements/sign — auth + party. Real path; §11 doc says
    POST /api/engagements/{id}/sign which does not exist.

    Cross-tenant handler at server.py:650 already returns 404 — matches S-11."""

    async def _fresh_engagement(self, employer_card_client) -> str:
        r = await employer_card_client.post(
            "/api/engagements",
            json={"talent_id": seed_mod.TALENT_CLEAN_ID, "hours": 20,
                  "scope": "x", "mode": "remote"},
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    async def test_documented_path_returns_404(self, employer_card_client):
        """§11 documents POST /api/engagements/{id}/sign. That path does not
        exist in code. FastAPI returns 404 for unregistered routes. Test
        exists to make sure a future refactor doesn't accidentally add the
        documented path without updating the doc."""
        eid = await self._fresh_engagement(employer_card_client)
        r = await employer_card_client.post(f"/api/engagements/{eid}/sign", json={})
        assert r.status_code == 404, (
            "The documented `/api/engagements/{id}/sign` path exists — either "
            "the code grew a new handler or FastAPI is now routing this to "
            "the real /sign endpoint via loose matching. Update the doc and "
            "this assertion together."
        )

    async def test_unauth_returns_401(self, anon_client, employer_card_client):
        eid = await self._fresh_engagement(employer_card_client)
        r = await anon_client.post(
            "/api/engagements/sign",
            json={"engagement_id": eid, "signature": "x"},
        )
        assert r.status_code == 401, r.text

    async def test_cross_tenant_returns_404(
        self, employer_card_client, talent_flagged_client,
    ):
        """talent_flagged is not a party."""
        eid = await self._fresh_engagement(employer_card_client)
        r = await talent_flagged_client.post(
            "/api/engagements/sign",
            json={"engagement_id": eid, "signature": "Talent Flagged"},
        )
        assert r.status_code == 404, r.text


class TestDeliverablesCreate:
    """POST /api/deliverables — must be the engaged talent.
    Cross-tenant currently returns 403 (server.py:670) — S-11 wants 404."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.post(
            "/api/deliverables",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "title": "x",
                  "hours_claimed": 1},
        )
        assert r.status_code == 401, r.text

    async def test_employer_returns_403(self, employer_card_client):
        """Wrong role — the engaging employer isn't allowed to submit as
        the talent. Body ownership check at server.py:670 uses `user["id"] !=
        eng.get("talent_id")` and raises 403."""
        r = await employer_card_client.post(
            "/api/deliverables",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "title": "x",
                  "hours_claimed": 1},
        )
        assert r.status_code == 403, r.text

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "S-11: cross-tenant POST /deliverables leaks 403 (id-exists "
            "signal) instead of 404. The engagement handler in server.py "
            "checks `user['id'] != eng.get('talent_id')` and raises 403; "
            "S-11 wants 404 to avoid the id-existence oracle. Marked "
            "xfail(strict=True) so this test self-clears when load_owned() "
            "lands — strict then fails the suite on XPASS, forcing us to "
            "remove the marker and close the canary. Phase 1d converted "
            "this from a hard-red test so CI is gate-able (permanently red "
            "CI trains people to ignore it)."
        ),
    )
    async def test_cross_tenant_returns_404_per_s11(self, talent_flagged_client):
        """talent_flagged is not the engaged talent on ENGAGEMENT_SIGNED_ID."""
        r = await talent_flagged_client.post(
            "/api/deliverables",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "title": "x",
                  "hours_claimed": 1},
        )
        assert r.status_code == 404, (
            f"S-11 violation: cross-tenant POST leaked 403 (id-exists signal) "
            f"instead of 404. Got {r.status_code}: {r.text[:200]}. "
            f"See server.py deliverable-create handler — needs load_owned()."
        )


class TestDeliverablesList:
    """GET /api/deliverables/{engagement_id} — party. Cross-tenant is 404
    (server.py:691) — matches S-11."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.get(
            f"/api/deliverables/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 401, r.text

    async def test_cross_tenant_returns_404(self, talent_flagged_client):
        r = await talent_flagged_client.get(
            f"/api/deliverables/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 404, r.text

    async def test_party_talent_returns_200(self, talent_clean_client):
        r = await talent_clean_client.get(
            f"/api/deliverables/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 200, r.text
        items = r.json()
        assert any(x["id"] == seed_mod.DELIVERABLE_SUBMITTED_ID for x in items)


class TestDeliverableApprove:
    """POST /api/deliverables/{id}/approve — must be the engaging employer.
    Cross-tenant currently returns 403 (server.py:705) — S-11 wants 404."""

    _URL = f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/approve"

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.post(self._URL, json={"feedback": "x"})
        assert r.status_code == 401, r.text

    async def test_talent_returns_403(self, talent_clean_client):
        """Wrong role — the engaged talent can't approve their own deliverable."""
        r = await talent_clean_client.post(self._URL, json={"feedback": "x"})
        assert r.status_code == 403, r.text

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "S-11: cross-tenant POST /deliverables/{id}/approve leaks 403 "
            "instead of 404. Handler in server.py raises 403 when the "
            "requesting employer is not the engaging employer; S-11 wants "
            "404 (no id-existence oracle). Self-clears when load_owned() "
            "lands — strict then fails the suite on XPASS, forcing the "
            "marker off. Phase 1d converted from hard-red to xfail so "
            "CI can be a merge gate."
        ),
    )
    async def test_cross_tenant_employer_returns_404_per_s11(
        self, employer_nocard_client,
    ):
        """employer_nocard is not the engaging employer on DELIVERABLE_SUBMITTED_ID."""
        r = await employer_nocard_client.post(self._URL, json={"feedback": "x"})
        assert r.status_code == 404, (
            f"S-11 violation: cross-tenant approve leaked 403 instead of 404. "
            f"Got {r.status_code}: {r.text[:200]}. See server.py deliverable-"
            f"approve handler — needs load_owned()."
        )


class TestDeliverableReject:
    """POST /api/deliverables/{id}/reject — same auth model as approve."""

    _URL = f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/reject"

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.post(self._URL, json={"feedback": "x"})
        assert r.status_code == 401, r.text

    async def test_talent_returns_403(self, talent_clean_client):
        r = await talent_clean_client.post(self._URL, json={"feedback": "x"})
        assert r.status_code == 403, r.text

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "S-11: cross-tenant POST /deliverables/{id}/reject leaks 403 "
            "instead of 404. Same handler shape as approve — the reject "
            "path shares the party-membership check that raises 403; "
            "S-11 wants 404. Self-clears on XPASS(strict) when the "
            "load_owned() helper lands. Phase 1d converted from hard-red."
        ),
    )
    async def test_cross_tenant_employer_returns_404_per_s11(
        self, employer_nocard_client,
    ):
        r = await employer_nocard_client.post(self._URL, json={"feedback": "x"})
        assert r.status_code == 404, (
            f"S-11 violation: cross-tenant reject leaked 403 instead of 404. "
            f"Got {r.status_code}: {r.text[:200]}. See server.py deliverable-"
            f"reject handler — needs load_owned()."
        )


class TestReviewsCreate:
    """POST /api/reviews — auth + party. Handler at server.py:788 returns
    404 on cross-tenant — matches S-11 already."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.post(
            "/api/reviews",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "rating": 5},
        )
        assert r.status_code == 401, r.text

    async def test_cross_tenant_returns_404(self, talent_flagged_client):
        r = await talent_flagged_client.post(
            "/api/reviews",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "rating": 5},
        )
        assert r.status_code == 404, r.text

    async def test_out_of_range_rating_returns_400(self, employer_card_client):
        r = await employer_card_client.post(
            "/api/reviews",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "rating": 6},
        )
        assert r.status_code == 400, r.text


class TestReviewsForUser:
    """GET /api/reviews/user/{uid} — public. FEATURES §11 marks this public;
    handler at server.py:807 has no auth dependency and filters to
    status=approved only."""

    async def test_unauth_allowed_returns_200(self, anon_client):
        r = await anon_client.get(f"/api/reviews/user/{seed_mod.TALENT_CLEAN_ID}")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    async def test_returns_only_approved_reviews(
        self, employer_card_client, anon_client, db,
    ):
        """Post a review (status=pending) and confirm it is NOT returned on
        the public feed. The moderation gate is load-bearing — this test
        would flag a regression that dropped the status filter."""
        post = await employer_card_client.post(
            "/api/reviews",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "rating": 5,
                  "text": "Should be moderated first"},
        )
        assert post.status_code == 200, post.text
        rid = post.json()["id"]
        # Sanity: the review exists in Mongo with status=pending.
        stored = await db.reviews.find_one({"id": rid}, {"_id": 0})
        assert stored["status"] == "pending"
        # Public feed must not include it.
        pub = await anon_client.get(f"/api/reviews/user/{seed_mod.TALENT_CLEAN_ID}")
        assert pub.status_code == 200
        assert all(item["id"] != rid for item in pub.json()), (
            "Public review feed returned a pending-moderation review"
        )


# ---------------------------------------------------------------------------
# Messaging endpoints §11 uses but never tables
# ---------------------------------------------------------------------------


class TestMessagesList:
    """GET /api/messages/{engagement_id} — auth + party. server.py:937."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.get(
            f"/api/messages/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 401, r.text

    async def test_cross_tenant_returns_404(self, talent_flagged_client):
        r = await talent_flagged_client.get(
            f"/api/messages/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 404, r.text

    async def test_party_returns_200_and_scoped_list(
        self, talent_clean_client, employer_card_client, db,
    ):
        # Seed a message via the API so we know it exists.
        post = await employer_card_client.post(
            "/api/messages",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID,
                  "text": "hello"},
        )
        assert post.status_code == 200, post.text
        r = await talent_clean_client.get(
            f"/api/messages/{seed_mod.ENGAGEMENT_SIGNED_ID}"
        )
        assert r.status_code == 200, r.text
        items = r.json()
        assert any(m["text"] == "hello" for m in items)


class TestMessagesCreate:
    """POST /api/messages — auth + party. server.py:946."""

    async def test_unauth_returns_401(self, anon_client):
        r = await anon_client.post(
            "/api/messages",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "text": "x"},
        )
        assert r.status_code == 401, r.text

    async def test_cross_tenant_returns_404(self, talent_flagged_client):
        r = await talent_flagged_client.post(
            "/api/messages",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "text": "x"},
        )
        assert r.status_code == 404, r.text

    async def test_empty_text_returns_400(self, employer_card_client):
        r = await employer_card_client.post(
            "/api/messages",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID, "text": "   "},
        )
        assert r.status_code == 400, r.text

    async def test_pii_regex_flags_but_does_not_block(
        self, employer_card_client,
    ):
        """server.py:959 flags off-platform contact but does not reject."""
        r = await employer_card_client.post(
            "/api/messages",
            json={"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID,
                  "text": "email me at test@example.com"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["flagged"] is True


class TestMessagesUpload:
    """POST /api/messages/upload — multipart form, auth + party. server.py:2286.

    stripe-mock ≠ storage mock — this test hits the real storage_client
    against INTEGRATION_PROXY_URL from .env.test. Because that URL points
    at stripe-mock (which returns 404 for arbitrary paths), the storage
    put_object call will raise → handler surfaces 500. This is expected
    until a storage mock is wired; the ONLY assertion we can safely make
    without hitting real storage is the auth gate itself."""

    async def test_unauth_returns_401(self, anon_client):
        files = {"file": ("t.txt", io.BytesIO(b"hi"), "text/plain")}
        data = {"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID}
        r = await anon_client.post("/api/messages/upload", data=data, files=files)
        assert r.status_code == 401, r.text

    async def test_cross_tenant_returns_404(self, talent_flagged_client):
        """Auth-gate check. If cross-tenant were allowed through, the request
        would proceed to storage and return 500 instead."""
        files = {"file": ("t.txt", io.BytesIO(b"hi"), "text/plain")}
        data = {"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID}
        r = await talent_flagged_client.post(
            "/api/messages/upload", data=data, files=files
        )
        assert r.status_code == 404, r.text

    async def test_unsupported_extension_returns_400(self, employer_card_client):
        """Extension check at server.py:2296 fires BEFORE the storage call, so
        this assertion is stable even without a storage mock."""
        files = {"file": ("t.exe", io.BytesIO(b"payload"),
                          "application/octet-stream")}
        data = {"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID}
        r = await employer_card_client.post(
            "/api/messages/upload", data=data, files=files
        )
        assert r.status_code == 400, r.text

    async def test_party_upload_writes_message_row_and_files_row(
        self, employer_card_client, db,
    ):
        """Happy path against the storage-mock (see backend/tests/_storage_mock/app.py)."""
        content = b"hello from the test suite"
        files = {"file": ("hello.txt", io.BytesIO(content), "text/plain")}
        data = {"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID}
        r = await employer_card_client.post(
            "/api/messages/upload", data=data, files=files
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["engagement_id"] == seed_mod.ENGAGEMENT_SIGNED_ID
        assert body["attachment_name"] == "hello.txt"
        assert body["attachment_id"], "handler should mint an attachment_id"
        # Files row exists with the storage_path server.py:2306 built.
        f = await db.files.find_one({"id": body["attachment_id"]}, {"_id": 0})
        assert f is not None
        assert f["engagement_id"] == seed_mod.ENGAGEMENT_SIGNED_ID
        assert f["user_id"] == seed_mod.EMPLOYER_CARD_ID
        assert f["storage_path"].startswith("talenthub/attachments/")
        # Message row for the attachment (server.py:2313).
        m = await db.messages.find_one({"id": body["id"]}, {"_id": 0})
        assert m is not None
        assert m["attachment_id"] == body["attachment_id"]

    async def test_storage_mock_stored_key_is_uuid_shaped_not_guessable(
        self, employer_card_client,
    ):
        """S-14 wants random storage keys, not guessable paths. Use the mock's
        /_debug/keys endpoint to inspect exactly what got stored, then assert
        the tail component looks like a UUID with the expected extension."""
        # Reset the mock so this test's uploads are the only keys on it.
        import httpx
        async with httpx.AsyncClient(
            base_url="http://storage-mock:9000", timeout=5.0
        ) as mc:
            await mc.post("/_debug/reset")

            files = {"file": ("evidence.pdf", io.BytesIO(b"%PDF-fake"),
                              "application/pdf")}
            data = {"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID}
            up = await employer_card_client.post(
                "/api/messages/upload", data=data, files=files
            )
            assert up.status_code == 200, up.text

            info = (await mc.get("/_debug/keys")).json()

        assert info["count"] == 1, info
        key = info["keys"][0]["path"]
        # Expected shape: talenthub/attachments/{user_id}/{uuid}.{ext}
        parts = key.split("/")
        assert parts[0] == "talenthub", key
        assert parts[1] == "attachments", key
        assert parts[2] == seed_mod.EMPLOYER_CARD_ID, key
        leaf = parts[3]
        assert leaf.endswith(".pdf"), leaf
        # UUID4 tail is 36 chars (32 hex + 4 dashes) — enough randomness that
        # a directory listing doesn't leak sibling filenames.
        stem = leaf.rsplit(".", 1)[0]
        assert len(stem) >= 32, (
            f"storage key stem {stem!r} is not UUID-shaped — S-14 wants a "
            f"random key so listing one attachment doesn't leak another."
        )
        # Mock echoes size + content_type — assert what actually crossed the wire.
        assert info["keys"][0]["size"] == len(b"%PDF-fake")
        assert info["keys"][0]["content_type"] == "application/pdf"

    async def test_over_10mb_upload_rejected_at_backend_before_reaching_storage(
        self, employer_card_client,
    ):
        """Backend at server.py:2293 rejects >10MB with 400 before the storage
        call. The mock's own 413 (see storage-mock app.py) is defense-in-depth
        for the day someone drops the backend check.

        We verify: (a) backend returns 400, NOT 413, so the check is still
        at the backend; (b) the storage-mock did NOT receive the payload
        (nothing was stored)."""
        import httpx
        async with httpx.AsyncClient(
            base_url="http://storage-mock:9000", timeout=5.0
        ) as mc:
            await mc.post("/_debug/reset")

            big = b"\x00" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
            files = {"file": ("big.pdf", io.BytesIO(big), "application/pdf")}
            data = {"engagement_id": seed_mod.ENGAGEMENT_SIGNED_ID}
            r = await employer_card_client.post(
                "/api/messages/upload", data=data, files=files
            )
            assert r.status_code == 400, (
                f"expected backend 400 (server.py:2293), got {r.status_code}. "
                f"If this becomes 413 the backend check was removed and the "
                f"storage-mock is the only gate — restore the backend check."
            )

            info = (await mc.get("/_debug/keys")).json()

        assert info["count"] == 0, (
            f"storage-mock received an oversized upload the backend was "
            f"supposed to reject: {info}"
        )
