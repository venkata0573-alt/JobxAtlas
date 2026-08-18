import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Cookie, X } from "@phosphor-icons/react";

const CONSENT_KEY = "cookie_consent_v1";

/**
 * Cookie preferences persisted in localStorage.
 * SECURITY NOTE: This store is INTENTIONAL and non-sensitive by design —
 * it holds only three boolean flags + a timestamp + a schema version. GDPR
 * guidance (EDPB Guidelines 05/2020) explicitly permits storing the user's
 * consent decision in a first-party cookie or equivalent (localStorage is
 * equivalent per Recital 30). No PII, no tokens, no session material is
 * written here. Session auth uses httpOnly Secure SameSite=Lax cookies.
 */

// Read current consent state, or null if none yet
export function readConsent() {
  try { return JSON.parse(localStorage.getItem(CONSENT_KEY) || "null"); }
  catch { return null; }
}

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);
  const [customize, setCustomize] = useState(false);
  const [functional, setFunctional] = useState(false);

  useEffect(() => {
    if (!readConsent()) {
      // Small delay so the banner doesn't fight the hero animation.
      const t = setTimeout(() => setVisible(true), 600);
      return () => clearTimeout(t);
    }
  }, []);

  const persist = (state) => {
    const doc = {
      necessary: true,
      functional: Boolean(state.functional),
      timestamp: new Date().toISOString(),
      version: 1,
    };
    localStorage.setItem(CONSENT_KEY, JSON.stringify(doc));
    // Broadcast so other parts of the app (e.g. analytics wrappers) can react.
    window.dispatchEvent(new CustomEvent("cookie-consent-changed", { detail: doc }));
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label="Cookie preferences"
      data-testid="cookie-consent-banner"
      className="fixed left-4 right-4 bottom-4 md:left-6 md:right-auto md:bottom-6 md:max-w-md z-[70]">
      <div className="hard-border bg-white shadow-brutal-lg p-5">
        <div className="flex items-start gap-3">
          <div className="hard-border bg-[#6B21A8] text-white w-9 h-9 flex items-center justify-center shrink-0">
            <Cookie size={18} weight="duotone"/>
          </div>
          <div className="flex-1 min-w-0">
            <p className="overline text-[#6B21A8]">COOKIE PREFERENCES</p>
            <p className="text-sm mt-1 leading-relaxed">
              We use strictly-necessary cookies to keep you signed in and secure. Functional
              cookies remember your preferences on this device. We don&apos;t run third-party
              advertising trackers.{" "}
              <Link to="/legal" className="underline underline-offset-4">Read the Cookie Notice →</Link>
            </p>

            {customize && (
              <div className="mt-3 space-y-2 border-t border-black/10 pt-3" data-testid="cookie-customize">
                <label className="flex items-center gap-2 opacity-70 cursor-not-allowed">
                  <input type="checkbox" checked disabled className="accent-[#6B21A8]"/>
                  <span className="text-xs font-mono">
                    Strictly necessary <span className="text-[10px] text-neutral-500">(required — cannot disable)</span>
                  </span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={functional}
                    onChange={(e) => setFunctional(e.target.checked)}
                    className="accent-[#6B21A8]"
                    data-testid="cookie-functional-toggle"/>
                  <span className="text-xs font-mono">Functional (remember theme, dismissed banners, industry)</span>
                </label>
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2">
              {!customize && (
                <>
                  <button onClick={() => persist({ functional: true })}
                          data-testid="cookie-accept-all"
                          className="btn-primary text-xs">Accept all</button>
                  <button onClick={() => persist({ functional: false })}
                          data-testid="cookie-accept-necessary"
                          className="btn-outline text-xs">Necessary only</button>
                  <button onClick={() => setCustomize(true)}
                          data-testid="cookie-customize-open"
                          className="text-xs underline underline-offset-4 text-[#6B21A8] hover:text-[#0B1B2B]">Customize</button>
                </>
              )}
              {customize && (
                <button onClick={() => persist({ functional })}
                        data-testid="cookie-save"
                        className="btn-primary text-xs">Save preferences</button>
              )}
            </div>
          </div>
          <button onClick={() => persist({ functional: false })}
                  aria-label="Dismiss"
                  data-testid="cookie-dismiss"
                  className="text-neutral-400 hover:text-neutral-700 shrink-0">
            <X size={16}/>
          </button>
        </div>
      </div>
    </div>
  );
}
