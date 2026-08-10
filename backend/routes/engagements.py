"""Engagements routes — DEFERRED PHYSICAL EXTRACTION (see server.py).

Endpoints that BELONG here (currently live in server.py):
  Engagements
    POST /engagements                                 (~line 519)
    GET  /engagements                                 (~line 549)
    GET  /engagements/{eid}                           (~line 556)
    POST /engagements/sign                            (~line 564)
  Deliverables
    POST /deliverables                                (~line 584)
    GET  /deliverables/{engagement_id}                (~line 605)
    POST /deliverables/{deliverable_id}/approve       (~line 670)
    POST /deliverables/{deliverable_id}/reject        (~line 675)
  Reviews (public/talent-facing)
    POST /reviews                                     (~line 681)
    GET  /reviews/user/{user_id}                      (~line 705)
  Messages
    GET  /messages/{engagement_id}                    (~line 945)
    POST /messages                                    (~line 954)
    POST /messages/upload                             (~line 1927)
  Availability + calendar
    PUT  /availability                                (~line 2073)
    GET  /availability/{user_id}                      (~line 2079)
    GET  /calendar/events                             (~line 2089)
  EOI (Expression of Interest)
    POST /eoi                                         (~line 2108)
    GET  /eoi                                         (~line 2132)
    POST /eoi/{eoi_id}/accept                         (~line 2144)
    POST /eoi/{eoi_id}/withdraw                       (~line 2178)

Notable coupling to be careful of during extraction:
  - Engagement + deliverable approval fires an auto-payout (see _act_deliverable)
  - Contract signing (POST /engagements/sign) writes both party signatures
  - Message upload uses the shared /files upload flow

Extraction status: PLANNED. Engagements is the most-coupled router — extract
last, and consider co-locating deliverables+payouts+contracts in one module to
keep the payout-on-accept flow local.
"""
# Intentionally empty: endpoints still register onto `api` from server.py.
