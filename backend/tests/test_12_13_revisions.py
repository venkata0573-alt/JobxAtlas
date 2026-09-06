"""Phase 1b tests — FEATURES.md §12 (revisions + penalty ladder) and
§13 (disputes + arbitration).

H-8 posture. `.env.test` sets `REVISION_REVIEW_THRESHOLD=4` (non-default
vs the code default 3). Every threshold assertion in this file references
`REVIEW_THRESHOLD_H8 = 4` explicitly and asserts behaviour at that value —
never "either 3 or 4 is fine." A test that would pass under either
threshold does not prove the config path is live, and violates the H-8
close-out condition in PROJECT_STATUS.md §5.

Bounded scope. Only §12 + §13 endpoints. §14 (dispute-fee Stripe checkout,
refund, refund-audit PDF, refund-analytics) is out — it needs
locally-signed Stripe payloads (H-7 in PROJECT_STATUS.md §5) and lands in
a later session.

Cookie-only. Every client here comes from `conftest.client_factory`,
which authenticates via the login cookie and never touches
`Authorization: Bearer` (S-26). Do not add a Bearer opt-in.

Expected failures. Nothing in this file is a ratchet-fail placeholder.
If an assertion here goes red, it is a genuine drift signal — either
the config path stopped working, the ladder constants changed, or the
handler regressed. Investigate; do not just adjust the number.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests import seed as seed_mod


# ---------- Constants tied to .env.test / code defaults --------------------

# H-8: .env.test sets REVISION_REVIEW_THRESHOLD=4. This is THE anchor value
# for every "does amber fire?" assertion below. If you find yourself
# tempted to change it to 3, first check whether .env.test still sets the
# non-default seed — if it does, the config path regressed, not this test.
REVIEW_THRESHOLD_H8 = 4

# The remaining ladder values match code defaults in
# backend/config.py:BusinessRules. .env.test does NOT override these,
# because H-8 only needs ONE non-default to prove the path is live.
PENALTY_THRESHOLD           = 5
DISPUTE_FEE_USD             = 49.0
VISIBILITY_PENALTY          = 20
RATE_NUDGE_PENALTY_PCT      = 10.0
RECOVERY_UNDER_REVIEW       = 3
RECOVERY_EXCESSIVE          = 5
EMPLOYER_FLAG_TALENTS       = 3
EMPLOYER_FLAG_WINDOW_DAYS   = 60


pytestmark = pytest.mark.asyncio


# ---------- test helpers ---------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


async def _open_revision(employer_client, deliverable_id: str) -> dict:
    """POST one request-revision. Returns parsed JSON. Raises on non-2xx."""
    r = await employer_client.post(
        f"/api/deliverables/{deliverable_id}/request-revision",
        json={"justification": "Please tighten the header section copy.",
              "priority": "minor"},
    )
    assert r.status_code == 200, f"request-revision failed: {r.status_code} {r.text[:200]}"
    return r.json()


async def _resubmit(talent_client, deliverable_id: str) -> dict:
    """POST one resubmit. Flips deliverable back to a state where the
    employer can open another revision. Returns parsed JSON."""
    r = await talent_client.post(
        f"/api/deliverables/{deliverable_id}/resubmit",
        json={"link": "https://example.test/next-version",
              "hours_claimed": 1, "notes": ""},
    )
    assert r.status_code == 200, f"resubmit failed: {r.status_code} {r.text[:200]}"
    return r.json()


async def _advance_revisions(employer_client, talent_client, deliverable_id: str,
                              target_count: int) -> dict:
    """Escalate to exactly `target_count` request-revision cycles.

    Between each revision the talent must resubmit — otherwise the handler
    400s ("Revision can only be requested on submitted or resubmitted
    work"). After the final request-revision the deliverable is left in
    `revision_requested` state and its `revision_count == target_count`.

    Returns the final request-revision JSON so callers can assert on
    `penalty_triggered` / `dispute_available` without re-fetching."""
    if target_count < 1:
        raise ValueError("target_count must be >= 1")
    final = None
    for i in range(target_count):
        final = await _open_revision(employer_client, deliverable_id)
        # Resubmit between rounds so the next request-revision has valid state.
        if i < target_count - 1:
            await _resubmit(talent_client, deliverable_id)
    return final


# ===========================================================================
# §12 — request-revision threshold behaviour
# ===========================================================================

class TestRequestRevisionThresholds:
    """The penalty ladder itself. These are the tests H-8 exists to make
    trustworthy — .env.test's non-default REVISION_REVIEW_THRESHOLD=4
    means a config-read regression would flip amber to fire at 3 and be
    caught here."""

    async def test_first_revision_does_not_fire_amber(
        self, employer_card_client, talent_clean_client, db,
    ):
        """count=1 → no flag anywhere; revision_count on deliverable is 1."""
        j = await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=1,
        )
        assert j["revision_count"] == 1
        assert j["penalty_triggered"] is False
        assert j["dispute_available"] is False
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof = talent.get("profile", {})
        assert prof.get("under_review") is not True
        assert prof.get("excessive_revisions") is not True

    async def test_third_revision_STILL_no_amber_at_H8_threshold(
        self, employer_card_client, talent_clean_client, db,
    ):
        """H-8 fingerprint. Under the CODE default (REVIEW_FLAG_THRESHOLD=3)
        amber would fire at count=3; under the .env.test seed (=4) it must
        NOT. If this test flips green while returning `under_review=True`
        at count=3, the config path stopped reading REVISION_REVIEW_THRESHOLD
        and the whole F-11 sweep regressed silently."""
        j = await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=3,
        )
        assert j["revision_count"] == 3
        assert j["penalty_triggered"] is False, (
            "H-8 REGRESSION: amber fired at count=3. .env.test sets "
            "REVISION_REVIEW_THRESHOLD=4, so amber must NOT fire here. "
            "If this assertion started failing without a code change to "
            "config.BusinessRules.revision_review_threshold, F-11's env "
            "read path silently broke."
        )
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        assert (talent.get("profile") or {}).get("under_review") is not True

    async def test_fourth_revision_fires_amber_at_H8_threshold(
        self, employer_card_client, talent_clean_client, db,
    ):
        """H-8 anchor. count = REVIEW_THRESHOLD_H8 = 4 → amber fires and
        `penalty_triggered=True` in the endpoint response. Would fail
        under either code-default 3 OR any other override — only passes
        at exactly the value .env.test sets."""
        j = await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=REVIEW_THRESHOLD_H8,
        )
        assert j["revision_count"] == REVIEW_THRESHOLD_H8
        assert j["penalty_triggered"] is True
        assert j["dispute_available"] is False, (
            "Dispute must not open at amber-only; only at excessive (count >= 5)."
        )
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof = talent.get("profile") or {}
        assert prof.get("under_review") is True
        assert prof.get("excessive_revisions") is not True, (
            "excessive_revisions must not fire until PENALTY_THRESHOLD (5)."
        )
        # No visibility deduction at amber-only.
        assert int(prof.get("visibility_score") or 100) == 100

    async def test_fifth_revision_fires_red_and_deducts_visibility_once(
        self, employer_card_client, talent_clean_client, db,
    ):
        """count=5 (PENALTY_THRESHOLD) → excessive_revisions=True, visibility
        drops to 80 (100 - 20), rate_bias to -10%. Second escalation past
        the threshold (count=6) must NOT double-deduct — the handler's
        `_apply_talent_penalty` is idempotent per deliverable+level pair."""
        j5 = await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        assert j5["revision_count"] == PENALTY_THRESHOLD
        assert j5["dispute_available"] is True
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof = talent.get("profile") or {}
        assert prof.get("excessive_revisions") is True
        assert int(prof.get("visibility_score")) == 100 - VISIBILITY_PENALTY
        assert float(prof.get("rate_bias_pct")) == -RATE_NUDGE_PENALTY_PCT

        # Push past the threshold once more; the idempotency guard should
        # keep visibility at 80, not drop it to 60.
        await _resubmit(talent_clean_client, seed_mod.DELIVERABLE_SUBMITTED_ID)
        j6 = await _open_revision(employer_card_client, seed_mod.DELIVERABLE_SUBMITTED_ID)
        assert j6["revision_count"] == PENALTY_THRESHOLD + 1
        talent2 = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof2 = talent2.get("profile") or {}
        assert int(prof2.get("visibility_score")) == 100 - VISIBILITY_PENALTY, (
            f"Idempotency violated: visibility={prof2.get('visibility_score')} "
            f"after 6 revisions; expected {100 - VISIBILITY_PENALTY} (deduct-once)."
        )


class TestRequestRevisionNegatives:
    """Three-per-endpoint negatives for request-revision."""

    async def test_talent_cannot_request_revision(self, talent_clean_client):
        r = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/request-revision",
            json={"justification": "would love to change my own deliverable pls",
                  "priority": "minor"},
        )
        assert r.status_code == 403, r.text

    async def test_wrong_employer_cannot_request_revision(self, employer_nocard_client):
        """employer_nocard is not the party on the seeded engagement."""
        r = await employer_nocard_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/request-revision",
            json={"justification": "twenty character justification here",
                  "priority": "minor"},
        )
        assert r.status_code == 403, r.text

    async def test_short_justification_rejected(self, employer_card_client):
        """min_length=20 on the Pydantic model — should 422."""
        r = await employer_card_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/request-revision",
            json={"justification": "too short", "priority": "minor"},
        )
        assert r.status_code == 422, r.text

    async def test_wrong_status_rejected(
        self, employer_card_client, talent_clean_client, db,
    ):
        """revision-request against an APPROVED deliverable → 400.
        (The seeded deliverable is `submitted`; mutate to approved.)"""
        await db.deliverables.update_one(
            {"id": seed_mod.DELIVERABLE_SUBMITTED_ID},
            {"$set": {"status": "approved"}},
        )
        r = await employer_card_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/request-revision",
            json={"justification": "twenty character justification here",
                  "priority": "minor"},
        )
        assert r.status_code == 400, r.text


# ===========================================================================
# §12 — resubmit
# ===========================================================================

class TestResubmit:
    async def test_resubmit_flips_state(
        self, employer_card_client, talent_clean_client, db,
    ):
        await _open_revision(employer_card_client, seed_mod.DELIVERABLE_SUBMITTED_ID)
        r = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/resubmit",
            json={"link": "https://example.test/v2", "hours_claimed": 2,
                  "notes": "Addressed header note."},
        )
        assert r.status_code == 200, r.text
        d = await db.deliverables.find_one({"id": seed_mod.DELIVERABLE_SUBMITTED_ID})
        assert d["status"] == "revision_resubmitted"
        assert d["link"] == "https://example.test/v2"

    async def test_employer_cannot_resubmit(
        self, employer_card_client, talent_clean_client,
    ):
        await _open_revision(employer_card_client, seed_mod.DELIVERABLE_SUBMITTED_ID)
        r = await employer_card_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/resubmit",
            json={"link": "https://example.test/x", "hours_claimed": 1},
        )
        assert r.status_code == 403, r.text

    async def test_resubmit_without_open_revision_rejected(self, talent_clean_client):
        """Seeded deliverable is `submitted`, not `revision_requested`."""
        r = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/resubmit",
            json={"link": "https://example.test/x", "hours_claimed": 1},
        )
        assert r.status_code == 400, r.text


# ===========================================================================
# §12 — list + summary (surfaces the H-8 threshold to the UI)
# ===========================================================================

class TestListRevisionsAndSummary:
    async def test_list_returns_H8_threshold(self, employer_card_client):
        """The list endpoint returns `review_threshold` so the UI can
        show "N revisions until amber". H-8 anchor: must be 4, not 3."""
        r = await employer_card_client.get(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/revisions"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["review_threshold"] == REVIEW_THRESHOLD_H8, (
            f"H-8 REGRESSION: /revisions endpoint returned review_threshold="
            f"{body['review_threshold']}, expected {REVIEW_THRESHOLD_H8} from "
            f".env.test. Config path likely broken."
        )
        assert body["penalty_threshold"] == PENALTY_THRESHOLD
        assert body["dispute_fee_usd"] == DISPUTE_FEE_USD

    async def test_summary_dispute_flag_flips_at_5(
        self, employer_card_client, talent_clean_client,
    ):
        """dispute_available False at count=4, True at count=5."""
        # Advance to 4 (amber) — dispute_available must stay False.
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=REVIEW_THRESHOLD_H8,
        )
        r4 = await employer_card_client.get(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/revision-summary"
        )
        assert r4.status_code == 200
        s4 = r4.json()
        assert s4["revision_count"] == REVIEW_THRESHOLD_H8
        # revision-summary doesn't have a dispute_available field — but /revisions does.
        r_list = await employer_card_client.get(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/revisions"
        )
        assert r_list.json()["dispute_available"] is False

        # Push through 5 → excessive + dispute_available flips True.
        await _resubmit(talent_clean_client, seed_mod.DELIVERABLE_SUBMITTED_ID)
        j5 = await _open_revision(employer_card_client, seed_mod.DELIVERABLE_SUBMITTED_ID)
        assert j5["revision_count"] == PENALTY_THRESHOLD
        r_list2 = await employer_card_client.get(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/revisions"
        )
        assert r_list2.json()["dispute_available"] is True

    async def test_list_anon_401(self, anon_client):
        r = await anon_client.get(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/revisions"
        )
        assert r.status_code == 401, r.text

    async def test_list_cross_tenant_403(self, talent_flagged_client):
        """talent_flagged is not a party on the seeded engagement."""
        r = await talent_flagged_client.get(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/revisions"
        )
        assert r.status_code == 403, r.text


# ===========================================================================
# §12 — recovery status / ladder-reversal
# ===========================================================================

class TestRecovery:
    async def test_recovery_status_no_penalty(self, talent_clean_client):
        r = await talent_clean_client.get("/api/talent/me/recovery-status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {
            "has_penalty": False, "clean_streak": 0,
            "target": None, "needed": 0, "progress_pct": 0,
        }

    async def test_recovery_status_under_review_needs_3(
        self, talent_clean_client, db,
    ):
        """Amber (under_review) recovery target = RECOVERY_UNDER_REVIEW = 3.
        Note: this is separate from REVIEW_THRESHOLD_H8 = 4 (the amber
        TRIGGER) — the RECOVERY value is not H-8-seeded and matches the
        code default."""
        await db.users.update_one(
            {"id": seed_mod.TALENT_CLEAN_ID},
            {"$set": {"profile.under_review": True,
                      "profile.excessive_revisions": False,
                      "profile.clean_streak": 2}},
        )
        r = await talent_clean_client.get("/api/talent/me/recovery-status")
        assert r.status_code == 200
        body = r.json()
        assert body["has_penalty"] is True
        assert body["target"] == "under_review"
        assert body["needed"] == RECOVERY_UNDER_REVIEW
        assert body["clean_streak"] == 2
        assert body["remaining"] == 1

    async def test_recovery_status_excessive_needs_5(self, talent_flagged_client):
        """talent_flagged is pre-seeded with excessive_revisions=True.
        Recovery target = RECOVERY_EXCESSIVE = 5."""
        r = await talent_flagged_client.get("/api/talent/me/recovery-status")
        assert r.status_code == 200
        body = r.json()
        assert body["has_penalty"] is True
        assert body["target"] == "excessive_revisions"
        assert body["needed"] == RECOVERY_EXCESSIVE

    async def test_employer_cannot_read_recovery_status(self, employer_card_client):
        r = await employer_card_client.get("/api/talent/me/recovery-status")
        assert r.status_code == 403, r.text

    async def test_end_to_end_amber_lift_after_3_clean_approvals(
        self, employer_card_client, talent_clean_client, db,
    ):
        """Set talent_clean under_review + streak=2, then approve the seed
        deliverable (revision_count==0). Approval fires
        _record_clean_approval → streak becomes 3 → RECOVERY_UNDER_REVIEW
        met → under_review lifts, streak resets to 0. This is the ONE
        end-to-end recovery test — enough to prove the write path exists;
        the numerical threshold is covered by the read-path tests above."""
        await db.users.update_one(
            {"id": seed_mod.TALENT_CLEAN_ID},
            {"$set": {"profile.under_review": True,
                      "profile.excessive_revisions": False,
                      "profile.clean_streak": 2,
                      "profile.revision_flags": []}},
        )
        r = await employer_card_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/approve",
            json={"feedback": "Looks good, shipping."},
        )
        assert r.status_code == 200, r.text
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof = talent.get("profile") or {}
        assert prof.get("under_review") is False, (
            f"Amber did not lift after streak reached {RECOVERY_UNDER_REVIEW}. "
            f"Profile: under_review={prof.get('under_review')}, "
            f"clean_streak={prof.get('clean_streak')}"
        )
        # After a lift the handler resets streak to 0 (see
        # _record_clean_approval in routes/revisions.py).
        assert prof.get("clean_streak") == 0


# ===========================================================================
# §12 — employer abuse flag (§ EMPLOYER_FLAG_TALENTS × EMPLOYER_FLAG_WINDOW_DAYS)
# ===========================================================================

class TestEmployerAbuseFlag:
    async def test_flag_fires_at_5_revisions_across_3_talents_in_60d(
        self, employer_card_client, talent_clean_client, db,
    ):
        """Insert 2 pre-existing high-revision histories directly (talents A
        and B), then push the seed deliverable through 5 revisions —
        that's the third distinct talent hitting PENALTY_THRESHOLD in the
        window, triggering the employer flag scan."""
        # Two synthetic prior escalations attributed to employer_card, each
        # against a distinct fictional talent, both inside the 60d window.
        for tid in ("prior-talent-A", "prior-talent-B"):
            await db.revision_requests.insert_one({
                "id": f"rr-seed-{tid}", "deliverable_id": f"del-{tid}",
                "engagement_id": f"eng-{tid}",
                "employer_id": seed_mod.EMPLOYER_CARD_ID, "talent_id": tid,
                "revision_number": PENALTY_THRESHOLD,
                "justification": "seed", "priority": "minor", "status": "open",
                "created_at": _iso_days_ago(10),
            })

        # Now push the real seeded deliverable to PENALTY_THRESHOLD — this
        # is talent_clean, the third distinct talent inside the window.
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        employer = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        prof = employer.get("profile") or {}
        assert prof.get("abusive_pattern_flag") is True, (
            f"Employer abuse flag did not fire at "
            f"{EMPLOYER_FLAG_TALENTS} distinct talents × "
            f"{PENALTY_THRESHOLD} revisions within {EMPLOYER_FLAG_WINDOW_DAYS} days. "
            f"Employer profile: {prof}"
        )
        # Should list all three talents.
        assert len(prof.get("abusive_pattern_talents") or []) >= EMPLOYER_FLAG_TALENTS

    async def test_flag_does_not_fire_at_2_talents_in_window(
        self, employer_card_client, talent_clean_client, db,
    ):
        """Only 1 prior + the seed's talent = 2 distinct talents. Below
        the EMPLOYER_FLAG_TALENTS=3 threshold, so no flag."""
        await db.revision_requests.insert_one({
            "id": "rr-seed-solo", "deliverable_id": "del-solo",
            "engagement_id": "eng-solo",
            "employer_id": seed_mod.EMPLOYER_CARD_ID, "talent_id": "prior-solo",
            "revision_number": PENALTY_THRESHOLD,
            "justification": "seed", "priority": "minor", "status": "open",
            "created_at": _iso_days_ago(10),
        })
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        employer = await db.users.find_one({"id": seed_mod.EMPLOYER_CARD_ID})
        assert (employer.get("profile") or {}).get("abusive_pattern_flag") is not True


# ===========================================================================
# §12 — F-07 confirmation: revision counter is monotonic
# ===========================================================================

class TestF07CounterMonotonic:
    async def test_counter_never_decrements_after_talent_favourable_ruling(
        self, employer_card_client, talent_clean_client, admin_all_client, db,
    ):
        """F-07 in SECURITY_BACKLOG.md: revision counter never decrements;
        recovery only clears flags. Prove it: run to 5 revisions, open a
        dispute, admin rules for talent (which reverses PENALTY FLAGS on
        the profile), then confirm deliverable.revision_count STAYS 5."""
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        # Talent raises the dispute.
        r_disp = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/dispute",
            json={"reason": "The revisions were arbitrary; requesting review."},
        )
        assert r_disp.status_code == 200, r_disp.text
        gid = r_disp.json()["grievance"]["id"]

        # Admin rules for talent.
        r_rule = await admin_all_client.post(
            f"/api/admin/revisions/{gid}/rule",
            json={"ruling": "talent",
                  "notes": "Employer changed spec mid-cycle; unfair to penalise talent."},
        )
        assert r_rule.status_code == 200, r_rule.text

        # F-07 assertion: revision_count is intact.
        d = await db.deliverables.find_one({"id": seed_mod.DELIVERABLE_SUBMITTED_ID})
        assert d["revision_count"] == PENALTY_THRESHOLD, (
            f"F-07 VIOLATION: revision_count decremented to {d['revision_count']} "
            f"after talent-favourable ruling. FEATURES.md §12 says the counter is "
            f"monotonic; only the penalty FLAGS on the talent's profile clear on ruling."
        )
        # Talent-side flags should clear (this is the ruling's actual effect).
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof = talent.get("profile") or {}
        assert prof.get("excessive_revisions") is False
        assert int(prof.get("visibility_score")) == 100
        assert float(prof.get("rate_bias_pct")) == 0


# ===========================================================================
# §13 — raise-dispute
# ===========================================================================

class TestRaiseDispute:
    async def test_dispute_blocked_below_penalty_threshold(
        self, employer_card_client, talent_clean_client,
    ):
        """Advance to 4 (H-8 amber) but not 5 → dispute POST is 400."""
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=REVIEW_THRESHOLD_H8,
        )
        r = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/dispute",
            json={"reason": "twenty characters minimum reason string here"},
        )
        assert r.status_code == 400, r.text
        assert str(PENALTY_THRESHOLD) in r.text

    async def test_dispute_opens_at_5_with_49_fee(
        self, employer_card_client, talent_clean_client, db,
    ):
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        r = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/dispute",
            json={"reason": "twenty characters minimum reason string here"},
        )
        assert r.status_code == 200, r.text
        g = r.json()["grievance"]
        assert g["kind"] == "revision_dispute"
        assert g["dispute_fee"]["amount_usd"] == DISPUTE_FEE_USD
        assert g["dispute_fee"]["status"] == "pending"
        # Full revision thread copied into the grievance.
        assert len(g.get("revision_thread") or []) == PENALTY_THRESHOLD
        # Deliverable is stamped with the grievance id for UI lookup.
        d = await db.deliverables.find_one({"id": seed_mod.DELIVERABLE_SUBMITTED_ID})
        assert d.get("dispute_grievance_id") == g["id"]

    async def test_duplicate_dispute_rejected(
        self, employer_card_client, talent_clean_client,
    ):
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        r1 = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/dispute",
            json={"reason": "twenty characters minimum reason string here"},
        )
        assert r1.status_code == 200
        r2 = await talent_clean_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/dispute",
            json={"reason": "twenty characters minimum reason string here"},
        )
        assert r2.status_code == 400, r2.text

    async def test_employer_cannot_raise_dispute(
        self, employer_card_client, talent_clean_client,
    ):
        await _advance_revisions(
            employer_card_client, talent_clean_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        r = await employer_card_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/dispute",
            json={"reason": "twenty characters minimum reason string here"},
        )
        assert r.status_code == 403, r.text


# ===========================================================================
# §13 — admin ruling
# ===========================================================================

class TestAdminRule:
    async def _open_dispute(self, employer_client, talent_client, db) -> str:
        """Escalate to 5 + open dispute. Returns grievance id."""
        await _advance_revisions(
            employer_client, talent_client,
            seed_mod.DELIVERABLE_SUBMITTED_ID, target_count=PENALTY_THRESHOLD,
        )
        r = await talent_client.post(
            f"/api/deliverables/{seed_mod.DELIVERABLE_SUBMITTED_ID}/dispute",
            json={"reason": "twenty characters minimum reason string here"},
        )
        assert r.status_code == 200, r.text
        return r.json()["grievance"]["id"]

    async def test_rule_for_talent_reverses_penalty_and_bills_employer(
        self, employer_card_client, talent_clean_client, admin_all_client, db,
    ):
        gid = await self._open_dispute(employer_card_client, talent_clean_client, db)
        r = await admin_all_client.post(
            f"/api/admin/revisions/{gid}/rule",
            json={"ruling": "talent",
                  "notes": "Employer scope-crept the deliverable mid-cycle."},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ruling"] == "talent"
        assert body["fee_status"] == "owed_by_employer"
        assert body["fee_usd"] == DISPUTE_FEE_USD

        # Talent penalty flags reversed.
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof = talent.get("profile") or {}
        assert prof.get("excessive_revisions") is False
        assert int(prof.get("visibility_score")) == 100
        assert float(prof.get("rate_bias_pct")) == 0
        # Grievance is closed.
        g = await db.grievances.find_one({"id": gid})
        assert g["status"] == "resolved"
        assert g["ruling"] == "talent"
        assert g["dispute_fee"]["status"] == "owed_by_employer"

    async def test_rule_for_employer_keeps_penalty_and_bills_talent(
        self, employer_card_client, talent_clean_client, admin_all_client, db,
    ):
        gid = await self._open_dispute(employer_card_client, talent_clean_client, db)
        r = await admin_all_client.post(
            f"/api/admin/revisions/{gid}/rule",
            json={"ruling": "employer",
                  "notes": "Revisions were legitimate — talent did not meet spec."},
        )
        assert r.status_code == 200, r.text
        assert r.json()["fee_status"] == "owed_by_talent"

        # Talent penalty flags STAY (only lift on talent-favourable ruling).
        talent = await db.users.find_one({"id": seed_mod.TALENT_CLEAN_ID})
        prof = talent.get("profile") or {}
        assert prof.get("excessive_revisions") is True
        assert int(prof.get("visibility_score")) == 100 - VISIBILITY_PENALTY

    async def test_admin_noscope_cannot_rule(
        self, employer_card_client, talent_clean_client, admin_noscope_client, db,
    ):
        """S-09 pattern: admin without moderation scope must not pass."""
        gid = await self._open_dispute(employer_card_client, talent_clean_client, db)
        r = await admin_noscope_client.post(
            f"/api/admin/revisions/{gid}/rule",
            json={"ruling": "talent", "notes": "trying without scope"},
        )
        assert r.status_code == 403, r.text

    async def test_bad_ruling_value_rejected(
        self, employer_card_client, talent_clean_client, admin_all_client, db,
    ):
        gid = await self._open_dispute(employer_card_client, talent_clean_client, db)
        r = await admin_all_client.post(
            f"/api/admin/revisions/{gid}/rule",
            json={"ruling": "referee", "notes": "not talent or employer"},
        )
        assert r.status_code == 400, r.text

    async def test_double_ruling_rejected(
        self, employer_card_client, talent_clean_client, admin_all_client, db,
    ):
        gid = await self._open_dispute(employer_card_client, talent_clean_client, db)
        r1 = await admin_all_client.post(
            f"/api/admin/revisions/{gid}/rule",
            json={"ruling": "talent", "notes": "first ruling"},
        )
        assert r1.status_code == 200
        r2 = await admin_all_client.post(
            f"/api/admin/revisions/{gid}/rule",
            json={"ruling": "employer", "notes": "second ruling attempt"},
        )
        assert r2.status_code == 400, r2.text


# ===========================================================================
# §13 — /api/grievances/{gid}/fee-status (S-25 verification)
# ===========================================================================

class TestFeeStatusS25:
    """S-25 in SECURITY_BACKLOG.md was flagged as scanner-misfire: the
    endpoint gates on `user["id"] in (talent_id, employer_id) OR
    has_admin_scope("moderation")`, so both parties (including the payer)
    and any moderation admin can read it. These tests prove that
    empirically — if S-25 turns out to be a real bug, one of these will
    fail and force us to re-open it in the backlog."""

    async def test_payer_talent_can_read_fee_status(self, talent_flagged_client):
        """The seeded grievance has dispute_fee.owed_by_id=TALENT_FLAGGED
        (via the initial payment_status='unpaid'). The payer must be able
        to poll their own fee status — that is the S-25 concern."""
        r = await talent_flagged_client.get(
            f"/api/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/fee-status"
        )
        assert r.status_code == 200, (
            f"S-25 CONFIRMED as real bug: talent (payer) cannot poll fee status. "
            f"Got {r.status_code}: {r.text[:200]}. Re-open S-25 in SECURITY_BACKLOG.md "
            f"and fix by relaxing the guard at revisions.py:679."
        )
        body = r.json()
        assert body["fee"]["amount_usd"] == DISPUTE_FEE_USD
        assert body["fee"]["payment_status"] == "unpaid"

    async def test_employer_party_can_read_fee_status(self, employer_card_client):
        """Same endpoint, other party — proves the OR branch works both ways."""
        r = await employer_card_client.get(
            f"/api/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/fee-status"
        )
        assert r.status_code == 200, r.text

    async def test_moderation_admin_can_read_fee_status(self, admin_all_client):
        r = await admin_all_client.get(
            f"/api/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/fee-status"
        )
        assert r.status_code == 200, r.text

    async def test_anon_gets_401(self, anon_client):
        r = await anon_client.get(
            f"/api/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/fee-status"
        )
        assert r.status_code == 401, r.text

    async def test_unrelated_party_gets_403(self, talent_clean_client):
        """talent_clean is not the talent OR employer on GRIEVANCE_OPEN
        (which belongs to talent_flagged ↔ employer_card)."""
        r = await talent_clean_client.get(
            f"/api/grievances/{seed_mod.GRIEVANCE_OPEN_ID}/fee-status"
        )
        assert r.status_code == 403, r.text

    async def test_unknown_grievance_gets_404(self, admin_all_client):
        r = await admin_all_client.get(
            "/api/grievances/does-not-exist/fee-status"
        )
        assert r.status_code == 404, r.text
