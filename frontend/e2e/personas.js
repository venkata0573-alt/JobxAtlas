// Personas that mirror backend/tests/seed.py — keep the two in sync when
// adding new fixtures. Every id, email, and password below MUST match what
// the pytest fixture seeds, otherwise Playwright and pytest can't share a
// backend without stomping each other's state.
//
// Password is a single shared value from FIXTURE_PASSWORD in seed.py.
// If seed.py is ever rotated (say, for a security exercise), update this
// file in the same commit or every e2e login instantly breaks.

const FIXTURE_PASSWORD = 'Passw0rd!';

const PERSONAS = {
  ADMIN_ALL: {
    id: 'seed-admin-all',
    email: 'admin-all@atlas-test.example.com',
    role: 'admin',
    name: 'Admin All-Scopes',
  },
  TALENT_CLEAN: {
    id: 'seed-talent-clean',
    email: 'talent-clean@atlas-test.example.com',
    role: 'talent',
    name: 'Talent Clean',
  },
  TALENT_FLAGGED: {
    id: 'seed-talent-flagged',
    email: 'talent-flagged@atlas-test.example.com',
    role: 'talent',
    name: 'Talent Flagged',
  },
  EMPLOYER_CARD: {
    id: 'seed-employer-card',
    email: 'employer-card@atlas-test.example.com',
    role: 'employer',
    name: 'Employer Card-On-File',
  },
  EMPLOYER_NOCARD: {
    id: 'seed-employer-nocard',
    email: 'employer-nocard@atlas-test.example.com',
    role: 'employer',
    name: 'Employer No-Card',
  },
};

const SEEDED_IDS = {
  ENGAGEMENT_SIGNED: 'seed-engagement-signed',
  DELIVERABLE_SUBMITTED: 'seed-deliverable-submitted',
  PROJECT_OPEN: 'seed-project-open',
  MILESTONE_1: 'seed-milestone-1',
  INVOICE_OPEN: 'seed-invoice-open',
  GRIEVANCE_OPEN: 'seed-grievance-open',
};

// Backend URL for API calls made from Playwright test code (not the
// browser). Same value the SPA's axios baseURL uses (per .env.test).
const BACKEND_URL = 'https://localhost:18443';

module.exports = { PERSONAS, FIXTURE_PASSWORD, SEEDED_IDS, BACKEND_URL };
