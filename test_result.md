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
          - S-25 confirmed as scanner-misfire empirically. Talent payer
            and employer party both reach fee-status; only unrelated +
            anon are denied. PROJECT_STATUS.md §3 marked S-25 as
            "still unverified" — active-test citation now available;
            can be marked CLOSED in SECURITY_BACKLOG.md.
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