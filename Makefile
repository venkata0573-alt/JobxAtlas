# Makefile — Phase 1a harness targets. Run from repo root.
#
# Acceptance (per plan approval):
#   make up-test && make seed && make test-backend   # green from cold checkout

COMPOSE     := docker compose -f docker-compose.test.yml
COMPOSE_DEV := docker compose -f docker-compose.dev.yml

.PHONY: up-test down-test seed test-backend test-frontend e2e security-scan verify coverage-gaps help \
        up-dev down-dev down-dev-hard seed-dev dev-logs

help:
	@echo "Phase 1a harness targets:"
	@echo "  make up-test         Boot the test stack (mongo/backend/frontend/stripe-mock), wait for health."
	@echo "  make down-test       Tear it down and drop the tmpfs volume."
	@echo "  make seed            Populate synthetic data (idempotent)."
	@echo "  make test-backend    Run backend/tests/ inside the backend container."
	@echo "  make test-frontend   Placeholder — frontend unit tests not yet added."
	@echo "  make e2e             Placeholder — Playwright suite not yet added."
	@echo "  make security-scan   Placeholder — gitleaks/bandit/pip-audit/semgrep (Phase 1d)."
	@echo "  make coverage-gaps   Run tests with coverage and regenerate docs/COVERAGE_GAPS.md."
	@echo "  make verify          test-backend + test-frontend + e2e + security-scan."
	@echo ""
	@echo "Hand-driven local dev stack (see docs/LOCAL_SETUP.md):"
	@echo "  make up-dev          Boot the dev stack (real Stripe/Resend, local mongo + storage-mock)."
	@echo "  make down-dev        Stop containers.  Mongo volume PRESERVED."
	@echo "  make down-dev-hard   Stop + drop the mongo volume (nukes hand-entered data)."
	@echo "  make seed-dev        Populate the same personas as the test stack — see docs/LOCAL_SETUP.md."
	@echo "  make dev-logs        Tail all dev-stack container logs."

up-test:
	$(COMPOSE) up -d --build --wait

down-test:
	$(COMPOSE) down -v

seed:
	$(COMPOSE) exec -T backend python /app/backend/tests/seed.py

# Runs inside the backend container so sitecustomize.py is active, mongo is
# reachable at `mongo:27017`, and stripe-mock is reachable at `stripe-mock:12111`.
# TEST_BACKEND_URL=https://localhost:8443 hits the same container's uvicorn
# over TLS (self-signed cert; httpx uses verify=False).
#
# `-rs` prints the reason for every skipped test — otherwise a skip goes
# silent and someone drifts into a fake-green suite. If the CSRF ratchet or
# any invariant test starts silently skipping, we want to see it in the log.
#
# Phase 1a scope: harness smoke + Phase 0 AST invariants + scanner unit tests.
# The legacy `test_iteration*.py` and `backend_test.py` suites in
# backend/tests/ were written for a pre-harness setup; Phase 1b converts
# FEATURES.md into new tests section-by-section and supersedes them.
test-backend:
	# -n 0 (pytest.ini-documented serial mode) — the DB-mutating integration
	# suites (test_00_smoke, test_11_engagements) share ONE Mongo through the
	# backend. clean_db's drop-and-reseed on one worker invalidates any live
	# JWT on the other worker for the ~5ms window before the reseed lands,
	# yielding non-deterministic 401 "User not found" flakes. Serial cost is
	# a handful of seconds at Phase 1b size and buys full determinism.
	#
	# Coverage is a BASELINE, not a gate. --cov-fail-under=0 keeps the build
	# green regardless.
	#
	# The --cov-report=json output written here is the PYTEST-PROCESS view
	# only. Backend/uvicorn is a separate process — its coverage lives in
	# /tmp/coverage/.coverage.HOST.PID.N (via sitecustomize.py +
	# COVERAGE_PROCESS_START). `make coverage-gaps` flushes backend, combines
	# both data sets, and regenerates the JSON before running the gap report.
	# Running `make test-backend` alone WITHOUT the coverage-gaps step yields
	# a misleading ~1% because it only sees pytest imports, not app execution.
	rm -f docs/scripts/.artifacts/coverage.json
	$(COMPOSE) exec -T backend sh -c "mkdir -p /tmp/coverage && rm -f /tmp/coverage/.coverage.*"
	$(COMPOSE) exec -T -e TEST_BACKEND_URL=https://localhost:8443 backend \
		python -m pytest -rs -n 0 \
			--cov=/app/backend \
			--cov-config=/app/backend/.coveragerc \
			--cov-report=term-missing \
			--cov-fail-under=0 \
			tests/test_00_smoke.py \
			tests/test_03_auth.py \
			tests/test_06_marketplace.py \
			tests/test_07_shortlist.py \
			tests/test_08_eoi.py \
			tests/test_10_hours_purchase.py \
			tests/test_11_engagements.py \
			tests/test_12_13_revisions.py \
			tests/test_14_grievances_refunds.py \
			tests/test_17_milestone_payments.py \
			tests/test_stripe_fixtures.py \
			tests/test_public_surface.py \
			tests/test_csrf_surface.py \
			tests/test_config.py \
			../docs/scripts/tests/ \
			-v

coverage-gaps: test-backend
	# Flush backend (SIGTERM triggers coverage.save() via the atexit hook
	# coverage.process_startup() registered) then start it back up.
	$(COMPOSE) restart backend
	$(COMPOSE) exec -T backend sh -c "\
	  coverage combine /tmp/coverage/.coverage.* 2>/dev/null || true; \
	  coverage json --rcfile=/app/backend/.coveragerc \
	    -o /app/docs/scripts/.artifacts/coverage.json"
	python3 docs/scripts/coverage_gaps.py

test-frontend:
	@echo "test-frontend: no frontend unit tests yet — Phase 1c will add them."

e2e:
	# Phase 1c: Playwright end-to-end suite lives under frontend/e2e/.
	# Runs from the HOST (Playwright browsers need direct network access
	# to the published ports; installing them inside the frontend container
	# would break because REACT_APP_BACKEND_URL is baked as
	# https://localhost:18443 — unreachable from inside the container).
	#
	# Reset backend state first so Playwright starts from the same seed
	# pytest's clean_db creates for backend tests. Otherwise state
	# accumulates across runs (H-9 in PROJECT_STATUS.md §5, extended to
	# the frontend layer).
	# Clear mutable collections first — Playwright has no equivalent to
	# pytest's conftest.clean_db autouse, so without this, subsequent
	# runs see accumulated state and toggle-style buttons (Shortlist
	# add/remove) fire the wrong verb. See backend/tests/e2e_reset.py
	# for the list.
	$(COMPOSE) exec -T backend python /app/backend/tests/e2e_reset.py
	$(COMPOSE) exec -T backend python /app/backend/tests/seed.py
	cd frontend && npx playwright test

# Phase 1d proper wires these tools into CI. Today this target reports what's
# missing rather than silently passing.
security-scan:
	@echo "security-scan: not yet wired. Phase 1d will pin gitleaks + bandit + pip-audit + semgrep."
	@echo "See VALIDATION_PROCESS.md §1d for the target shape."

verify: test-backend test-frontend e2e security-scan

# ---------------------------------------------------------------------------
# Hand-driven dev stack (docs/LOCAL_SETUP.md).  Never merged with `verify`:
# the test stack has to stay hermetic — no dev credentials, no real Stripe.
# ---------------------------------------------------------------------------

# Refuse to boot if .env.dev is missing.  Cheapest way to tell someone
# "copy the example first" without a mysterious pydantic RuntimeError deep
# in the backend container's boot sequence.
up-dev:
	@test -f .env.dev || { \
	  echo ""; \
	  echo "  .env.dev not found.  Bootstrap it once:"; \
	  echo "    cp .env.dev.example .env.dev  &&  $$EDITOR .env.dev"; \
	  echo "  Then re-run.  Full walkthrough: docs/LOCAL_SETUP.md"; \
	  echo ""; \
	  exit 1; \
	}
	$(COMPOSE_DEV) up -d --build --wait
	@echo ""
	@echo "  Open https://localhost:3000  (accept the backend cert warning once at https://localhost:8443)"
	@echo "  For Stripe webhooks, keep this running in a separate terminal:"
	@echo "    stripe listen --forward-to https://localhost:8443/api/stripe/webhook --skip-verify"
	@echo "  Personas: make seed-dev  (login table: docs/LOCAL_SETUP.md §Personas)"
	@echo ""

down-dev:
	$(COMPOSE_DEV) down

# Same as down-dev + drop the mongo volume.  Loses every account and
# transaction you clicked through.  Named `-hard` so nobody types it in
# muscle memory.
down-dev-hard:
	$(COMPOSE_DEV) down -v

seed-dev:
	$(COMPOSE_DEV) exec -T backend python /app/backend/tests/seed.py

dev-logs:
	$(COMPOSE_DEV) logs -f --tail=100
