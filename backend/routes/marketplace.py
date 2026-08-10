"""Marketplace routes — DEFERRED PHYSICAL EXTRACTION (see server.py).

Endpoints that BELONG here (currently live in server.py):
  Public / SEO
    GET  /seo/skills                    (~line 908)
    GET  /seo/hire/{skill_slug}         (~line 913)
    GET  /seo/city-skills               (~line 1341)
    GET  /seo/hire-city/{slug}          (~line 1350)
    GET  /sitemap.xml                   (~line 1374)
  Marketplace stats
    GET  /marketplace/industries        (~line 1401)
    GET  /marketplace/stats             (~line 1419)
  Shortlist
    POST /shortlist                     (~line 1571)
    GET  /shortlist                     (~line 1597)
    DELETE /shortlist/{talent_id}       (~line 1605)
    POST /shortlist/broadcast           (~line 1626)
  Talent notifications
    GET  /talent/me/rate-nudge          (~line 1542)
    POST /talent/me/rate-nudge/dismiss  (~line 1550)
    GET  /talent/me/broadcasts          (~line 1742)
    POST /talent/me/broadcasts/{id}/read (~line 1751)

Supporting private helpers to move alongside:
  SEO_SKILLS, SEO_CITIES, EMPLOYER_INDUSTRIES  (already in deps.py)
  _CURATED_TALENT, _CITY_PRETTY
  _curated_to_public, _curated_for
  _build_sitemap_xml, STATIC_SITEMAP_PATHS
  _scan_and_record_rate_nudges, RATE_DRIFT_THRESHOLD_PCT
  _broadcast_email_html, DEFAULT_BROADCAST_TEMPLATE

Extraction status: PLANNED. The auth router (routes/auth.py) is the reference
implementation for how to physically move these blocks. Follow the same pattern
(import `api` from deps, keep helpers local, delete original block from
server.py and add `import routes.marketplace` where the block used to be).
"""
# Intentionally empty: endpoints still register onto `api` from server.py.
