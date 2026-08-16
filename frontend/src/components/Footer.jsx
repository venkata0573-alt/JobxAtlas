import React from "react";
import { Link } from "react-router-dom";
import { COMPANY } from "@/legal/content";

/**
 * Global footer strip carrying the Grievance Officer details (required by
 * Rule 3(2)(a) of the Indian IT Rules 2021) plus canonical policy links.
 * Small, understated — rendered on every route.
 */
export default function Footer() {
  return (
    <footer className="border-t border-black/10 bg-[#0B1B2B] text-neutral-300 mt-16" data-testid="site-footer">
      <div className="max-w-7xl mx-auto px-6 md:px-12 py-10 grid gap-8 md:grid-cols-4">
        <div>
          <p className="overline text-[#A78BFA] mb-3">JOB ATLAS · GEMINISTA</p>
          <p className="text-xs font-mono text-neutral-400 leading-relaxed">
            {COMPANY.legal_name}<br/>
            {COMPANY.registered_office}<br/>
            CIN {COMPANY.cin}<br/>
            GSTIN {COMPANY.gstin}
          </p>
        </div>
        <div>
          <p className="overline text-[#A78BFA] mb-3">POLICIES</p>
          <ul className="text-xs space-y-2">
            <li><Link to="/legal" className="hover:text-white" data-testid="footer-terms">Terms of Service</Link></li>
            <li><Link to="/legal" className="hover:text-white" data-testid="footer-privacy">Privacy Policy</Link></li>
            <li><Link to="/legal" className="hover:text-white" data-testid="footer-refund">Refund Policy</Link></li>
            <li><Link to="/legal" className="hover:text-white" data-testid="footer-aup">Acceptable Use</Link></li>
            <li><Link to="/subprocessors" className="hover:text-white" data-testid="footer-subprocessors">Sub-processors</Link></li>
            <li><Link to="/trust" className="hover:text-white">Trust &amp; Safety</Link></li>
          </ul>
        </div>
        <div>
          <p className="overline text-[#A78BFA] mb-3">SUPPORT</p>
          <ul className="text-xs space-y-2 font-mono">
            <li>Support: <a href={`mailto:${COMPANY.support_email}`} className="hover:text-white">{COMPANY.support_email}</a></li>
            <li>DPO: <a href={`mailto:${COMPANY.dpo_email}`} className="hover:text-white">{COMPANY.dpo_email}</a></li>
            <li><Link to="/grievance" className="hover:text-white underline">Raise a grievance →</Link></li>
          </ul>
        </div>
        <div data-testid="footer-grievance-officer">
          <p className="overline text-[#A78BFA] mb-3">GRIEVANCE OFFICER · IT RULES 2021</p>
          <p className="text-xs font-mono text-neutral-400 leading-relaxed">
            <span className="text-white">{COMPANY.grievance_officer_name}</span><br/>
            <a href={`mailto:${COMPANY.grievance_email}`} className="hover:text-white">{COMPANY.grievance_email}</a><br/>
            <a href={`tel:${COMPANY.grievance_officer_phone.replace(/\s+/g, "")}`} className="hover:text-white">{COMPANY.grievance_officer_phone}</a><br/>
            <span className="text-neutral-500">24-hour acknowledgement · 15-day resolution</span>
          </p>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-4 flex items-center justify-between flex-wrap gap-2">
          <p className="text-[10px] font-mono text-neutral-500">© {new Date().getFullYear()} {COMPANY.legal_name}. All rights reserved.</p>
          <p className="text-[10px] font-mono text-neutral-500">{COMPANY.version}</p>
        </div>
      </div>
    </footer>
  );
}
