"""Admin routes — DEFERRED PHYSICAL EXTRACTION (see server.py).

Endpoints that BELONG here (currently live in server.py):
  Bank-transfer approvals
    GET  /admin/bank-transfers                        (~line 449)
    POST /admin/bank-transfers/{payment_id}/approve   (~line 460)
    POST /admin/bank-transfers/{payment_id}/reject    (~line 477)
  Review moderation
    GET  /admin/reviews                               (~line 762)
    POST /admin/reviews/{rid}/approve                 (~line 770)
    POST /admin/reviews/{rid}/reject                  (~line 780)
  Grievance moderation
    GET  /admin/grievances                            (~line 814)
    POST /admin/grievances/{gid}/resolve              (~line 822)
  Payout runs
    POST /admin/payouts/run                           (~line 877)
    GET  /admin/payouts/runs                          (~line 912)
    GET  /admin/payouts/{run_id}                      (~line 919)
    POST /admin/payouts/{payout_id}/mark-paid         (~line 930)
  Rate-nudge + scheduler
    POST /admin/rate-nudges/scan                      (~line 1516)
    GET  /admin/scheduler                             (~line 1523)

Extraction status: PLANNED. See routes/auth.py for the reference extraction
pattern.
"""
# Intentionally empty: endpoints still register onto `api` from server.py.
