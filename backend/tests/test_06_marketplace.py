"""Phase 1b tests — FEATURES.md §8 marketplace / browse-discovery
surface (industries + stats + talent browse + employer directory + SEO
landing endpoints). Shortlist (also §8) is in test_07_shortlist.py so
each domain has a single test file.

The file number in the name is a sort key, not a FEATURES.md section
number — the harness convention.
"""
from __future__ import annotations

import pytest

from tests import seed as seed_mod


pytestmark = pytest.mark.asyncio


# ============================================================================
# 1. Public marketplace metadata — /marketplace/industries + /marketplace/stats
# ============================================================================

class TestMarketplaceIndustries:
    async def test_public_returns_industry_list(self, anon_client):
        r = await anon_client.get("/api/marketplace/industries")
        assert r.status_code == 200, r.text
        body = r.json()
        # Handler returns {industries: [{label, count}], total_labelled_employers}.
        assert isinstance(body, dict) and "industries" in body, (
            f"marketplace/industries returns a wrapper dict; got: {body}"
        )
        items = body["industries"]
        assert isinstance(items, list) and items
        first = items[0]
        assert "label" in first, (
            f"industry entries need a `label`; got: {first}"
        )


class TestMarketplaceStats:
    async def test_public_returns_stats_dict(self, anon_client):
        r = await anon_client.get("/api/marketplace/stats")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict), (
            "marketplace/stats fuels the Landing trust bar — must be a JSON object"
        )


# ============================================================================
# 2. GET /api/talent — public browse (search / filter)
# ============================================================================

class TestTalentBrowse:
    async def test_public_returns_seeded_talents(self, anon_client):
        """Landing browse is deliberately public — no auth required."""
        r = await anon_client.get("/api/talent")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        # Both seeded talents (clean + flagged) should appear.
        ids = {t.get("id") for t in body}
        assert seed_mod.TALENT_CLEAN_ID in ids
        # Flagged talent is `visibility_score=80` — visible but demoted;
        # asserting presence covers the "no silent hiding" contract.
        assert seed_mod.TALENT_FLAGGED_ID in ids

    async def test_verified_only_filter_excludes_unverified(
        self, anon_client, db,
    ):
        """Force talent-clean unverified and confirm the filter drops it."""
        await db.users.update_one(
            {"id": seed_mod.TALENT_CLEAN_ID},
            {"$set": {"verification_status": "none"}},
        )
        r = await anon_client.get("/api/talent?verified_only=true")
        assert r.status_code == 200
        ids = {t.get("id") for t in r.json()}
        assert seed_mod.TALENT_CLEAN_ID not in ids

    async def test_skill_filter_scopes_results(self, anon_client, db):
        """Query by skill regex; talent-clean has React so should match."""
        r = await anon_client.get("/api/talent?skill=React")
        assert r.status_code == 200
        assert any(t.get("id") == seed_mod.TALENT_CLEAN_ID for t in r.json())

    async def test_q_search_matches_name(self, anon_client):
        r = await anon_client.get("/api/talent?q=Talent+Clean")
        assert r.status_code == 200
        assert any(t.get("id") == seed_mod.TALENT_CLEAN_ID for t in r.json())


# ============================================================================
# 3. GET /api/talent/{id} — single talent, auth-required, email-gated
# ============================================================================

class TestTalentDetail:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get(f"/api/talent/{seed_mod.TALENT_CLEAN_ID}")
        assert r.status_code == 401

    async def test_unknown_talent_404(self, employer_card_client):
        r = await employer_card_client.get("/api/talent/does-not-exist")
        assert r.status_code == 404

    async def test_email_hidden_unless_active_engagement(
        self, employer_nocard_client,
    ):
        """employer_nocard has NO engagement with talent_clean → email hidden
        (server.py:410 gates on engagement in {contract_signed, active})."""
        r = await employer_nocard_client.get(
            f"/api/talent/{seed_mod.TALENT_CLEAN_ID}"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "email" not in body, (
            f"Cross-tenant employer must not see talent email; got: {body}"
        )

    async def test_email_visible_to_engaged_employer(
        self, employer_card_client,
    ):
        """employer_card ↔ talent_clean HAS a signed engagement (seed) →
        email should be visible."""
        r = await employer_card_client.get(
            f"/api/talent/{seed_mod.TALENT_CLEAN_ID}"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("email") == seed_mod.PERSONA_EMAILS[seed_mod.TALENT_CLEAN_ID], (
            f"engaged employer must see talent email; got: {body}"
        )


# ============================================================================
# 4. GET /api/employers — talent/admin only
# ============================================================================

class TestEmployersList:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get("/api/employers")
        assert r.status_code == 401

    async def test_employer_gets_403(self, employer_card_client):
        """Employers can't browse other employers (server.py:326)."""
        r = await employer_card_client.get("/api/employers")
        assert r.status_code == 403, r.text

    async def test_talent_can_browse_employers(self, talent_clean_client):
        r = await talent_clean_client.get("/api/employers")
        assert r.status_code == 200

    async def test_admin_can_browse_employers(self, admin_all_client):
        r = await admin_all_client.get("/api/employers")
        assert r.status_code == 200


# ============================================================================
# 5. GET /api/employers/{id} — profile lookup
# ============================================================================

class TestEmployerDetail:
    async def test_anon_401(self, anon_client):
        r = await anon_client.get(f"/api/employers/{seed_mod.EMPLOYER_CARD_ID}")
        assert r.status_code == 401

    async def test_employer_403(self, employer_card_client):
        r = await employer_card_client.get(
            f"/api/employers/{seed_mod.EMPLOYER_CARD_ID}"
        )
        assert r.status_code == 403

    async def test_talent_gets_public_profile(self, talent_clean_client):
        r = await talent_clean_client.get(
            f"/api/employers/{seed_mod.EMPLOYER_CARD_ID}"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # PII must be stripped (server.py:379 excludes email + integrations).
        assert "email" not in body
        assert body.get("company_name") == "CardCo"

    async def test_unknown_employer_404(self, talent_clean_client):
        r = await talent_clean_client.get("/api/employers/does-not-exist")
        assert r.status_code == 404


# ============================================================================
# 6. SEO indexes — /seo/skills + /seo/city-skills + /sitemap.xml
# ============================================================================

class TestSeoEndpoints:
    async def test_seo_skills_public_returns_list(self, anon_client):
        r = await anon_client.get("/api/seo/skills")
        assert r.status_code == 200, r.text
        body = r.json()
        # The SEO landing pages iterate this to render `/hire/*` routes.
        assert isinstance(body, (list, dict)), (
            f"seo/skills should return a list/dict; got: {body}"
        )

    async def test_seo_city_skills_public(self, anon_client):
        r = await anon_client.get("/api/seo/city-skills")
        assert r.status_code == 200

    async def test_sitemap_returns_xml(self, anon_client):
        r = await anon_client.get("/api/sitemap.xml")
        assert r.status_code == 200
        assert "xml" in r.headers.get("content-type", "").lower(), (
            f"sitemap must be served as XML; got content-type: "
            f"{r.headers.get('content-type')}"
        )
        assert "<urlset" in r.text or "<sitemap" in r.text


# ============================================================================
# 7. Skill-slug SEO landing pages — /seo/hire/{slug} + /seo/hire-city/{slug}
# ============================================================================

class TestSeoHireLandingPages:
    async def test_hire_slug_returns_talent_pool(self, anon_client):
        """Public endpoint. FEATURES.md §8 says it mixes real DB talents
        with curated pool."""
        r = await anon_client.get("/api/seo/hire/react-developers")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict), (
            f"landing endpoint returns a shape (talents + meta); got: {type(body)}"
        )

    async def test_hire_city_slug_returns_pool(self, anon_client):
        r = await anon_client.get("/api/seo/hire-city/react-developers-london")
        assert r.status_code == 200
