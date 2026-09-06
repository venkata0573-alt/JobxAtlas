/**
 * frontend/src/config.js — the sole environment boundary for the SPA.
 *
 * Every other module imports typed constants from here. A direct
 * `process.env.REACT_APP_*` read outside this file is a bug.
 *
 * F-08 CLOSED: REACT_APP_BACKEND_URL is required at boot. If unset the
 * module (a) renders a visible red banner into #root so the failure is
 * obvious in production, and (b) throws so the React app never mounts.
 * Without both, an unset value silently produced `undefined/api/...`
 * requests and a blank page.
 */

const BACKEND_URL_RAW = process.env.REACT_APP_BACKEND_URL;

if (!BACKEND_URL_RAW) {
  // Best-effort visible failure. Only render if document is available
  // (guards against SSR / test environments where `document` is undefined).
  if (typeof document !== "undefined") {
    const root = document.getElementById("root") || document.body;
    if (root) {
      root.innerHTML =
        '<div style="' +
        [
          "font-family:system-ui,sans-serif",
          "background:#8B0000",
          "color:#fff",
          "padding:24px",
          "margin:16px",
          "border-radius:6px",
          "line-height:1.5",
          "font-size:14px",
        ].join(";") +
        '">' +
        "<h2 style=\"margin:0 0 8px;font-size:18px\">Configuration error (F-08)</h2>" +
        "<p style=\"margin:0 0 8px\"><code>REACT_APP_BACKEND_URL</code> is not set. " +
        "The SPA cannot talk to the backend and every API call would resolve to " +
        "<code>undefined/api/&hellip;</code>.</p>" +
        "<p style=\"margin:0;opacity:.85;font-size:12px\">" +
        "Set it in your build environment (see backend/.env.example) and rebuild the frontend.</p>" +
        "</div>";
    }
  }
  throw new Error(
    "REACT_APP_BACKEND_URL is required (F-08). See frontend/src/config.js for details."
  );
}

export const BACKEND_URL = BACKEND_URL_RAW;

// Cloudflare's public always-passes test key. Preserves local-dev
// ergonomics for anyone running the SPA without a real Turnstile
// account. Real Turnstile enforcement lands with S-08's production
// hardening.
export const TURNSTILE_SITE_KEY =
  process.env.REACT_APP_TURNSTILE_SITE_KEY || "1x00000000000000000000AA";
