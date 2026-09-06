#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: >
  Phase 1b — convert FEATURES.md §11 (Engagements + contract signing + deliverables)
  into automated tests using the cookie-only harness. One test per numbered manual
  step; per-endpoint negative tests (unauth 401, wrong role 403, cross-tenant 404
  per S-11 load_owned convention). Also cover the messaging endpoints §11 uses but
  never tables. Test the real /api/engagements/sign path, not the doc's incorrect
  /api/engagements/{id}/sign.

backend:
  - task: "§11 POST /api/deliverables — S-11 ownership check"
    implemented: true
    working: false
    file: "backend/server.py:670"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: false
        -agent: "testing"
        -comment: >
          FAIL: TestDeliverablesCreate::test_cross_tenant_returns_404_per_s11 in
          tests/test_11_engagements.py:400. Cross-tenant POST (talent_flagged
          submitting against ENGAGEMENT_SIGNED_ID which belongs to talent_clean)
          returns 403 "Only the engaged talent can submit deliverables". Per
          SECURITY_BACKLOG.md S-11, should return 404 to avoid the id-exists
          side channel. Handler at server.py:670 checks user["id"] !=
          eng.get("talent_id") and raises 403. Fix: replace with a load_owned()
          helper that raises 404 on both "not found" and "not yours". Failure
          is intentional — leaving it red per Phase 1b protocol.

  - task: "§11 POST /api/deliverables/{id}/approve — S-11 ownership check"
    implemented: true
    working: false
    file: "backend/server.py:705"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: false
        -agent: "testing"
        -comment: >
          FAIL: TestDeliverableApprove::test_cross_tenant_employer_returns_404_per_s11
          in tests/test_11_engagements.py:454. Cross-tenant approve
          (employer_nocard on DELIVERABLE_SUBMITTED_ID which belongs to
          employer_card) returns 403 "Only the engaging employer can review
          deliverables" from _act_deliverable at server.py:705. S-11 wants 404.
          Same load_owned() fix as the deliverables-create case above; single
          helper closes both. Intentional red.

  - task: "§11 POST /api/deliverables/{id}/reject — S-11 ownership check"
    implemented: true
    working: false
    file: "backend/server.py:705"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: false
        -agent: "testing"
        -comment: >
          FAIL: TestDeliverableReject::test_cross_tenant_employer_returns_404_per_s11
          in tests/test_11_engagements.py:477. Same _act_deliverable ownership
          path as approve (server.py:705); returns 403 instead of 404. Bundled
          with S-11 approve fix. Intentional red.

  - task: "§11 POST /api/engagements/{id}/sign — documented path does not exist"
    implemented: false
    working: "NA"
    file: "FEATURES.md:352"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "testing"
        -comment: >
          FEATURES.md §11 (line 352) documents POST /api/engagements/{id}/sign.
          That handler does not exist in backend/server.py. The real endpoint
          is POST /api/engagements/sign with engagement_id in the JSON body
          (SignContractIn schema at server.py:127; handler at server.py:647).
          Tests target the real path. A guard test
          (TestEngagementSign::test_documented_path_returns_404) asserts the
          documented path returns 404 so a future refactor cannot silently
          make the doc "correct" without a real code change. Fix: update
          FEATURES.md §11 table row to the real path. No code change.

  - task: "§11 POST /api/reviews — status field spelling drift"
    implemented: true
    working: true
    file: "backend/server.py:800"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "testing"
        -comment: >
          FEATURES.md §11 step 6 (line 372) says reviews land with
          status="pending_moderation". Handler at server.py:800 writes
          status="pending". Functionally equivalent (both mean "not yet
          approved") but the doc's exact string mismatch would trip a
          test written literally from the doc. Test asserts the real
          value; noted here so someone fixes the doc, not the code.

  - task: "§11 lifecycle manual steps 1-6"
    implemented: true
    working: true
    file: "backend/tests/test_11_engagements.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "testing"
        -comment: >
          All six TestManualSteps tests pass against the cookie-only harness:
          engagement create, both-parties sign (status flips to contract_signed
          and employer hours_balance decrements by hours_allocated), talent
          submits deliverable, employer approves (hours_used increments), payout
          row is written with correct commission (60 rate * 5 hrs = 300 gross;
          commission tier applied), and review lands with status=pending.

  - task: "§11 auth-only messaging endpoints (undocumented in §11 table)"
    implemented: true
    working: true
    file: "backend/server.py:937,946,2286"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "testing"
        -comment: >
          GET /api/messages/{engagement_id}, POST /api/messages, and
          POST /api/messages/upload all enforce cookie auth + party membership
          via 404-on-cross-tenant (matches S-11 convention already). Only
          negative caveat: /messages/upload actually calls storage_client
          which points at INTEGRATION_PROXY_URL (currently stripe-mock in
          .env.test) — the happy-path upload test is skipped until a real
          storage mock lands. Auth-gate tests still cover the endpoint.

  - task: "§14 grievances + dispute-fee lifecycle + refund audit — 29 tests (S-04 evidence)"
    implemented: true
    working: true
    file: "backend/tests/test_14_grievances_refunds.py + test_17_milestone_payments.py (+1 concurrent test)"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >
          PASS: 312 passed / 3 S-11 ratchets / 1 CSRF skip / 4 xfailed.
          Baseline before: 283/3/1/3. Delta: +29 pass, +1 xfail (S-04
          canary), zero pre-existing regressions.
          test_14_grievances_refunds.py (29 tests, 28 pass + 1 xfail):
          - TestPayFee (6): anon 401, unknown 404, dispute-not-resolved
            400, wrong-payer 403, payer creates $49 checkout session +
            persists dispute_fee_transactions row, already-paid short-
            circuits.
          - TestDisputeFeeWebhook (2): signed checkout.session.completed
            with kind=dispute_fee flips dispute_fee.payment_status +
            dispute_fee_transactions to paid; bad signature 400s + no
            state change. Uses stripe_fixtures.py.
          - TestRefundFee (7): anon/noscope/unknown/not-paid/already-
            refunded/short-reason negatives + admin refund happy path
            (refund_id returned via stripe-mock, dispute_fee + tx
            both flipped refunded, admin id stamped, $49 amount).
          - TestRefundAnalytics (4): anon/noscope 401/403 + empty-state
            30-zero-buckets + paid-and-refunded populate series with
            correct refund_rate_pct + alert threshold=20 from
            config.BusinessRules.
          - TestRefundAuditPdf (5): anon/noscope + days=0/days=400
            bounds + happy path (PDF bytes with %PDF- magic, 64-char
            sha256 signature in X-Audit-Signature header, receipt row
            in refund_audit_receipts).
          - TestRefundAuditVerify (5): anon/noscope + unknown-sig
            receipt_found=false + round-trip known-sig receipt_found=
            true + S-04 tamper canary (xfail strict=True).
          test_17_milestone_payments.py (+1):
          - test_concurrent_milestone_replay_is_still_idempotent: 5×
            asyncio.gather on same session_id. PASSES because the
            milestone branch's follow-on writes are $set (idempotent),
            NOT $inc. Documents the TOCTOU shape shares hours' pattern
            but has no money-loss vector today; recorded under S-03
            (c) as invariant that would break if a future revision
            adds $inc.
          S-04 EVIDENCE (asked by user, filed as xfail canary):
          test_verify_detects_tampering_via_recompute in test_14. Fires
          the PDF over an empty set (0 rows hashed), then inserts a
          refunded dispute_fee_transactions row into the same 30-day
          window (tamper), re-hits /verify/{sig}. Expected post-S-04-
          fix: response includes recompute_matches=False. Current
          behaviour: verify at revisions.py:978-987 is a plain
          find_one({signature}) — no recompute — response is just
          {"receipt_found": true, "receipt": {...}}. Assertion of
          recompute_matches=False fails → xfail catches → XFAILED.
          When S-04 (b) lands (verify re-runs the query + recomputes +
          hmac.compare_digest), the assertion passes → strict fails on
          xpass → forces removal.
          S-03 UPDATE (backlog): SECURITY_BACKLOG.md S-03 row extended
          with (c) — the TOCTOU pattern at server.py:590-595 gates
          hours_balance $inc on the snapshot read rather than on the
          update result. Fix scope: `res = update_one({session_id, $ne
          paid}, {$set: paid}); if res.modified_count == 1: $inc`. Also
          noted milestone branch shares the shape but writes idempotent
          $set (no money-loss vector today, only paid_at drift), and
          that this fires on ordinary Stripe retries + F-05
          PaymentSuccess.jsx polling — no attacker required.
          MILESTONE TOCTOU CHECK (asked by user): same shape as hours
          (find_one → Python if-check → follow-on writes inside if-
          block). NO money-loss because writes are idempotent $set
          (status="paid", paid_at). Only observable difference is
          paid_at gets restamped by whichever handler finishes last.
          Concurrent test PASSES today — invariant documented.

  - task: "§10 hours purchase + §17 milestone payments — 30 money-path tests"
    implemented: true
    working: true
    file: "backend/tests/{test_10_hours_purchase, test_17_milestone_payments}.py + updated test_stripe_fixtures.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >
          PASS: 283 passed / 3 S-11 ratchets / 1 CSRF skip / 3 xfailed.
          Baseline before: 256 passed / 3 ratchets / 1 skip / 0 xfail.
          Delta: +27 pass, +3 xfail (all expected). Zero pre-existing
          regressions.
          Files added:
          - test_10_hours_purchase.py (17 tests, 15 pass + 2 xfail):
            /payments/checkout + /bank/{initiate,submit} + /mine +
            /status/{id} + webhook hours-credit + S-03(b) idempotency
            (sequential + concurrent) + F-05 dual-credit + forged +
            unknown session + charge.refunded xfail.
          - test_17_milestone_payments.py (13 tests, all pass):
            /projects/workspace/{p}/milestones/{m}/checkout + status
            + webhook milestone-flip + idempotency + forged + unknown.
          - test_stripe_fixtures.py updated: grep canary replaced
            with behavioral S-03 xfail(strict=True) that patches
            mark_dispute_fee_paid to raise and asserts 5xx propagates.
            Currently XFAILED (swallow present); flips xpassed when
            S-03 lands, forcing removal.
          Findings from writing these tests:
          - Sequential-replay idempotency PASSES today for both hours
            (test_sequential_replay_credits_once) and milestone
            (test_sequential_replay_leaves_state_stable). The
            session_id + `payment_status: {"$ne": "paid"}` guard is
            effective for serial re-delivery. The user's a-priori
            "expect double credit" prediction for sequential replay
            is not the current behavior. S-03(b) evidence is the
            CONCURRENT case, not sequential.
          - Concurrent replay (5× asyncio.gather on same session_id +
            same event.id) XFAILED — race hit, hours credited more
            than once. Root cause is at server.py:590-595: the if-check
            reads `rec.get("payment_status")` from the find_one
            snapshot; multiple concurrent handlers all see 'pending'
            in the same read window, all enter the block, all $inc
            hours_balance (the update_one uses $ne guard atomically
            but the subsequent $inc is unconditional on that update's
            success). F-05 race real for concurrent case. Fix scope
            per S-03(b): add stripe_events collection with unique
            event.id index so the second delivery is dropped BEFORE
            the find_one runs. Marked xfail(strict=False) since race
            is timing-dependent on tmpfs Mongo — may xpass on slow
            hosts, which strict=False accepts.
          - F-05 dual-credit test (webhook + polling) PASSED. Webhook
            fires first → payment_status=paid → polling endpoint calls
            stripe.Session.retrieve → _credit_hours_if_paid sees
            payment_status=paid → short-circuits. Guard holds for the
            documented sequential case.
          - charge.refunded webhook: no handler branch exists.
            server.py:563-596 only branches on
            checkout.session.completed; charge.refunded falls through
            to line 596 → 200 no-op. hours_balance stays credited
            after Stripe reverses the charge. Marked xfail(strict=True)
            with the expected-post-fix assertion; will flip xpassed
            when a charge.refunded branch is added.
          - S-03 dispute_fee behavioral xfail (replaced the grep
            canary) XFAILED as designed. Uses sf.make_webhook_request
            to call stripe_webhook directly (bypasses HTTP → uvicorn
            is a separate process so monkeypatch is visible), patches
            routes.revisions.mark_dispute_fee_paid to raise, asserts
            5xx propagates. Currently the swallow returns 200 → no
            exception → xfail catches. When S-03 lands, exception
            propagates → test passes → strict=True fails on xpass →
            forces removal.
          Not covered (intentional bounded scope):
          - Nightly auto-collect off-session charge path (F-05 branch
            in projects.py:_attempt_off_session_charge) — needs a
            scheduler-run harness. Phase 1c will add.
          - Setup-checkout / card-attach flows (/api/billing/setup*) —
            separate §17b domain; skipped this pass.
          - Bank-transfer admin-approval flow — separate §21 admin-
            panel scope, will land with the admin-panel coverage pass.

  - task: "Stripe webhook signing fixtures + S-03 evidence"
    implemented: true
    working: true
    file: "backend/tests/stripe_fixtures.py + backend/tests/test_stripe_fixtures.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >
          PASS: 10/10 green under make test-backend (serial -n 0).
          Baseline before: 246 passed / 3 S-11 ratchets / 1 CSRF skip.
          Baseline after: 256 passed / 3 ratchets / 1 skip. Zero
          regressions.
          Delivered: stripe_fixtures.py with sign_payload() +
          checkout_session_completed / payment_intent_succeeded /
          charge_refunded factories + with_bad_signature /
          with_stale_timestamp / with_malformed_header helpers.
          Secret is read from settings.stripe.webhook_secret (same
          config path the app uses) so fixture + handler agree
          byte-exact.
          Fixture tests (10 total):
          - 4× signed-payload-reaches-handler (hours_purchase,
            milestone E2E with DB update, PI succeeded, charge
            refunded)
          - 1× bad v1 signature → 400
          - 1× stale timestamp (400s past tolerance) → 400
          - 1× missing Stripe-Signature header → 400
          - 1× malformed header value → 400
          - 2× S-03 evidence: dispute_fee webhook returns 200 for
            unknown session + AST snapshot of server.py:568-573 that
            fails if the try/except → return {"ok": True} pattern
            changes shape (canary for S-03 closure).
          Reports H-7 in PROJECT_STATUS.md §5: "Money-path tests need
          locally-signed payloads with a test STRIPE_WEBHOOK_SECRET"
          — fixtures now exist; §10 / §14 / §17 tests can proceed in
          later sessions.
          S-03 EVIDENCE REPORT (asked by user):
          - Signature verification path (server.py:559-562): WORKS
            correctly. `stripe.Webhook.construct_event` throws on bad
            HMAC, stale timestamp, missing header, malformed header —
            handler catches and raises HTTPException(400, "Invalid
            signature"). All four adversarial fixture tests confirm
            400 in production; a bad signature does NOT get 200.
          - Business-logic swallow (server.py:568-573, dispute_fee
            branch only): SHAPE UNCHANGED — still wraps
            mark_dispute_fee_paid in try/except that logs and then
            unconditionally returns {"ok": True}. Confirmed by
            test_S03_shape_documented_dispute_branch_swallows which
            grep-checks the source. If mark_dispute_fee_paid throws
            (Mongo down, revisions.py refactor, dependency import
            error), Stripe still sees 200 and never retries → the DB
            + Stripe diverge silently. The unknown-session variant
            (dispute_fee kind + non-existent session) 200s cleanly
            because mark_dispute_fee_paid short-circuits on missing
            tx, not because the swallow fires; the swallow is a
            defense-in-depth trap waiting for a real exception.
          - Milestone branch (server.py:575-588) and hours-purchase
            fallback (server.py:590-595) do NOT have try/except
            wrappers — an exception there propagates as 500 (Stripe
            retries correctly). S-03 scope is dispute_fee branch only.
          - Verdict: S-03 correctly filed at P0. Signature side is
            solid; the money-loss risk is the swallow. Fix per
            SECURITY_BACKLOG.md: (a) replace the swallow with a raise
            so 500 propagates and Stripe retries, (b) add a stripe_
            events collection keyed on event.id for idempotency so
            retries don't double-process.

  - task: "§3 auth + §8 marketplace/shortlist + §9 EOI — 98 Phase 1b tests"
    implemented: true
    working: true
    file: "backend/tests/{test_03_auth, test_06_marketplace, test_07_shortlist, test_08_eoi}.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >
          PASS: 98/98 green under make test-backend (serial -n 0).
          Baseline before: 148 passed / 3 S-11 ratchets / 1 CSRF skip.
          Baseline after: 246 passed / 3 ratchets / 1 skip. Zero
          pre-existing regressions.
          Coverage per file (32 + 23 + 21 + 22 = 98):
          - test_03_auth.py (32): 6 manual-step tests, 4 register
            negatives (via direct-import to bypass Turnstile outbound
            call — see file docstring), 2 Turnstile fail-open assertions
            (S-08 partial: WARN fires with [S-08] tag + env + remote_ip
            when TURNSTILE_SECRET_KEY is unset), 3 verify-email token
            paths, 3 resend-verification (auth-required + already-verified
            short-circuit + fresh-token-persistence), 3 login negatives,
            1 logout cookie-clear, 2 /auth/me tests (401 anon +
            password_hash never returned), 2 PUT /profile tests, 2
            /profile/suggest-rate tests (asserts rule-based fallback
            shape regardless of LLM), 2 /verification/me, 2 SSE token
            endpoint.
          - test_06_marketplace.py (23): 1 industries, 1 stats, 4 talent
            browse (verified_only filter, skill filter, q search, all
            seeded), 4 talent detail (email visibility gated on
            engagement), 4 employers list (talent+admin allowed,
            employer 403), 4 employer detail (PII scrubbed), 3 SEO
            index endpoints (skills, city-skills, sitemap XML), 2 SEO
            landing pages (/hire/{slug}, /hire-city/{slug}).
          - test_07_shortlist.py (21): 3 add (upsert dedup verified),
            3 list (per-employer scoping), 3 remove, 4 broadcast
            (empty-shortlist 400, delivery count, emails=0 without
            RESEND_API_KEY), 3 broadcast history, 3 talent inbox, 2
            mark-read. SSE stream (/api/talent/me/broadcasts/stream)
            NOT covered — needs a dedicated fixture; the conftest's
            sse_token_for_talent_clean template is ready.
          - test_08_eoi.py (22): 3 manual steps (talent posts →
            employer sees → employer accepts → engagement created), 6
            EOI create (auth, role, unknown employer 404, wrong-role
            target 404, open EOI allowed), 3 list (talent scoped +
            employer sees own+open), 6 accept (auth, role, insufficient
            hours 400, double-accept 400, hours defaults from proposed),
            4 withdraw (owner + cross-tenant 404 not 403 per S-11 shape).
          Findings surfaced during writing:
          - Password reset endpoint does NOT exist in the backend. The
            user's task asked to "cover password reset token handling";
            only a `forgotPasswordLink` testId placeholder exists in
            frontend/src/constants/testIds/auth.js. Nothing to test.
            Possible F-XX candidate: either build the endpoint or
            remove the placeholder.
          - User's checklist said test_11_engagements.py covers "EOI
            withdraw" — but `grep -n eoi backend/tests/test_11_
            engagements.py` returns zero matches. Covered here instead
            (TestEoiWithdraw); no duplication with test_11.
          - /api/marketplace/industries returns {industries: [...],
            total_labelled_employers: N} — the wrapper shape is not
            documented in FEATURES.md §8. Test asserts against the
            wrapper. Add to F-12's §8 doc-fix list.

  - task: "§12 §13 revision ladder + disputes + S-25 fee-status"
    implemented: true
    working: true
    file: "backend/tests/test_12_13_revisions.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >
          PASS: 38/38 green under make test-backend (serial -n 0).
          Coverage: 4 threshold-ladder tests (amber-at-3-STAYS-off proves the
          H-8 config path, amber-at-4 fires, red-at-5 fires + visibility -20
          once, idempotent double-deduction guard); 4 request-revision
          negatives (wrong role, wrong party, short justification, bad
          status); 3 resubmit (happy + 2 negatives); 4 list/summary
          (H-8 review_threshold==4 surfaces to UI, dispute_available flips
          at 5, anon 401, cross-tenant 403); 5 recovery (no-penalty flat
          response, amber needs 3, excessive needs 5, employer 403,
          end-to-end amber lift after 3 clean approvals); 2 employer
          abuse flag (fires at 5×3×60d, does NOT fire at 2 talents); 1 F-07
          monotonic counter (revision_count stays 5 after talent-favourable
          ruling); 4 dispute (blocked at 4, opens at 5 with $49, duplicate
          400, employer 403); 5 admin rule (talent → fee owed_by_employer +
          penalty reversed, employer → fee owed_by_talent + penalty kept,
          admin_noscope 403, bad ruling 400, double rule 400); 6 S-25 fee-
          status (talent payer 200, employer party 200, moderation admin
          200, anon 401, unrelated talent 403, unknown grievance 404).
          Findings — nothing failing:
          - H-8 assertion path is live and green; every threshold check
            binds to REVIEW_THRESHOLD_H8=4, not 3.
          - S-25 CLOSED as scanner false positive. Handler at
            revisions.py:679 (was :672; F-11 shifted the line, content
            unchanged since first commit f409130 2026-08-15) has always
            enforced `user["id"] in (talent_id, employer_id) OR
            has_admin_scope("moderation")`. Zero application-code
            change required or made. Blind spot in
            docs/scripts/route_scan.py:220-298 documented as S-28 with
            list of ~11 other handlers currently mis-classified as
            "auth (no role/scope in body)" that actually enforce
            party-ownership via `user["id"]` patterns the scanner
            doesn't recognise.
          - F-07 confirmed intended behaviour: revision_count is
            monotonic; only profile penalty flags reverse on ruling.
          - H-9 (parallel worker state trampling) fires hard on this
            file if run without -n 0 — 7 tests failed under default -n
            auto due to shared-Mongo drop-and-reseed races. Makefile
            already enforces serial; documenting for anyone running
            pytest directly on this file.
          Bounded scope: §14 (dispute-fee Stripe checkout, refund,
          audit PDF, refund-analytics) NOT covered — needs signed Stripe
          payloads (H-7). Lands in a later session.

  - task: "F-11 centralise env reads — backend/config.py + frontend/src/config.js"
    implemented: true
    working: true
    file: "backend/config.py + frontend/src/config.js + backend/tests/test_config.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >
          PASS: F-11 landed 2026-09-06 across three commits — 4a85b96 (backend
          sweep, 49 sites in 9 files), 6448200 (initial doc updates), 22329d1
          (frontend sweep, 13 sites in 10 files). backend/config.py is now the
          sole os.environ/os.getenv reader in backend/; enforced by
          test_config.py::test_no_module_outside_config_reads_os_environ (AST
          scan). frontend/src/config.js is the sole process.env.REACT_APP_*
          reader; renders visible red banner + throws if REACT_APP_BACKEND_URL
          unset (F-08 close). Aggregated missing-var factory: one RuntimeError
          lists every missing var grouped by service. ENV is required at boot
          (no default) — silently defaulting to "development" would neuter
          S-08 production Turnstile enforcement. Added 18 tests in
          test_config.py (parametrised per-required-field, aggregation,
          ENV-no-default, CORS wildcard rejection, prod-Turnstile conditional,
          AST scan, H-8 non-default proof, .env.test-values-match-settings
          sanity). Baseline: was 80 passed / 3 S-11 ratchets / 1 CSRF skip;
          post-F-11: 98 passed / 3 S-11 ratchets / 1 CSRF skip. Zero
          pre-existing test regressions. Closed: S-05, S-15, S-27, F-08, F-09,
          F-10, H-8. Partial: S-02 (default removed, per-env validation open),
          S-04 (fallback chain collapsed, HMAC + verify recompute open), S-08
          (prod required + WARN logs, rate limiting open), S-20 (password
          default removed + seeder skips, force-rotate + prod superadmin-check
          open). All PARTIAL rows in SECURITY_BACKLOG.md have explicit
          "still open" notes so the backlog doesn't rot into fiction.

metadata:
  created_by: "testing"
  version: "1.0"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "S-11 load_owned() helper — covers 3 backend tests marked working: false above"
    - "FEATURES.md §11 table row for POST /api/engagements/sign — doc-only fix"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "testing"
    -message: >
      Phase 1b §11 landed at 77 passed / 3 failed / 2 skipped. The 3 failures
      are intentional — they surface S-11 (SECURITY_BACKLOG.md) at server.py:670
      and server.py:705. All three collapse into a single load_owned(collection,
      id, user) helper per S-11's proposed fix. Skips: (1) one skip is the
      /messages/upload happy path — needs a storage mock (harness debt); (2)
      the CSRF ratchet skip is unchanged (waiting on S-01).
      Two docs need PRs: (a) FEATURES.md §11 fix the /engagements/{id}/sign
      path, (b) FEATURES.md §11 fix the review status string
      "pending_moderation" → "pending". Both zero-risk doc-only fixes; not in
      this PR's scope (which is tests-only).
#====================================================================================================