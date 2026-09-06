// Phase 1c Playwright config. Runs against the existing docker-compose.test.yml
// stack (frontend on :13000, backend HTTPS on :18443). Executed from the HOST —
// installing Playwright inside the frontend container fails because the SPA is
// baked with REACT_APP_BACKEND_URL=https://localhost:18443, unreachable from
// inside the container.
//
// Prereqs:
//   `make up-test` (stack must be healthy)
//   `cd frontend && yarn install`   (@playwright/test is a devDep)
//   `cd frontend && npx playwright install chromium`
// Run:
//   `cd frontend && npx playwright test`
//   `make e2e` (via the Makefile target added in this commit)

const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  fullyParallel: false,   // Shared backend DB — serial. Same rationale as
                          // pytest.ini's `-n 0` (see PROJECT_STATUS.md §5 H-9).
  workers: 1,
  timeout: 45_000,        // API round-trips + Mongo tmpfs; generous.
  expect: { timeout: 10_000 },
  retries: 0,             // Leave failures failing per Phase 1b convention.
  reporter: [['list']],
  outputDir: 'e2e-artifacts',

  use: {
    baseURL: 'http://localhost:13000',
    ignoreHTTPSErrors: true,      // Backend self-signed cert (Dockerfile.test).
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
