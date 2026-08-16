import React, { useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Warning } from "@phosphor-icons/react";
import { TERMS, PRIVACY, REFUND, AUP, COOKIES, COMPANY } from "@/legal/content";

const DOCS = {
  terms:          { title: "Terms of Service",     body: TERMS,   summary: "Master Services Agreement covering marketplace nature, exclusivity, fees, IP, disputes and governing law." },
  privacy:        { title: "Privacy Policy",       body: PRIVACY, summary: "GDPR / UK GDPR / DPDP-Act compliant. Explains what we collect, why, sub-processors, retention, and your rights." },
  refund:         { title: "Refund Policy",        body: REFUND,  summary: "How refunds work for hour packages, projects, subscriptions, arbitration fees and chargebacks." },
  acceptable_use: { title: "Acceptable Use",       body: AUP,     summary: "Prohibited conduct, IP take-down, marketplace integrity, enforcement ladder and appeals." },
  cookies:        { title: "Cookie Notice",        body: COOKIES, summary: "Short list of the cookies we set — no third-party ad trackers." },
};

export default function Legal() {
  const [active, setActive] = useState("terms");
  const doc = DOCS[active];

  return (
    <main className="max-w-6xl mx-auto px-6 md:px-12 py-16" data-testid="legal-page">
      <p className="overline text-[#6B21A8] mb-3">LEGAL &amp; COMPLIANCE</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">Everything, in writing.</h1>
      <p className="text-sm text-neutral-500 font-mono mb-6">
        {COMPANY.product} · {COMPANY.parent_brand} · {COMPANY.legal_name} · {COMPANY.registered_office} · CIN {COMPANY.cin} · GSTIN {COMPANY.gstin} · {COMPANY.version}
      </p>

      {/* Counsel-review banner */}
      <div className="hard-border bg-[#FEF9C3] border-yellow-500 p-4 mb-8 flex items-start gap-3" data-testid="legal-review-banner">
        <div className="hard-border bg-[#0B1B2B] text-[#A78BFA] w-9 h-9 flex items-center justify-center shrink-0">
          <Warning size={18} weight="duotone"/>
        </div>
        <div className="text-sm">
          <p className="font-display font-extrabold text-[#854D0E]">Template — pending counsel review.</p>
          <p className="text-[13px] text-neutral-700 mt-1 leading-relaxed">
            These documents are drafted to be broadly protective of Job Atlas and {COMPANY.parent_brand} across India, the EU/UK and the United States.
            They must be reviewed and localised by qualified counsel in each operating jurisdiction before publication or reliance in any dispute.
            Nothing on this page constitutes legal advice.
          </p>
        </div>
      </div>

      <div className="grid md:grid-cols-[240px_1fr] gap-6">
        <nav className="hard-border bg-white p-4 shadow-brutal h-fit" data-testid="legal-nav">
          <p className="overline mb-3">Documents</p>
          <ul className="space-y-1">
            {Object.entries(DOCS).map(([id, d]) => (
              <li key={id}>
                <button onClick={() => setActive(id)}
                        data-testid={`legal-tab-${id}`}
                        className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 ${active === id ? "bg-[#0B1B2B] text-white" : "hover:bg-[#F5F3FF]"}`}>
                  <FileText size={14} weight="duotone"/> {d.title}
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-6 pt-4 border-t border-black/10 text-xs font-mono text-neutral-500 space-y-1">
            <p>Support: {COMPANY.support_email}</p>
            <p>Grievance: {COMPANY.grievance_email}</p>
            <p>DPO: {COMPANY.dpo_email}</p>
            <p className="mt-2"><Link to="/grievance" className="underline">Raise a grievance →</Link></p>
          </div>
        </nav>

        <article className="hard-border bg-white p-8 md:p-10 shadow-brutal" data-testid={`legal-doc-${active}`}>
          <h2 className="font-display font-extrabold text-3xl tracking-tight mb-2">{doc.title}</h2>
          <p className="text-sm text-neutral-500 mb-6">{doc.summary}</p>
          <pre className="whitespace-pre-wrap font-body leading-relaxed text-sm text-neutral-800" style={{ fontFamily: "'IBM Plex Sans', 'Inter', sans-serif" }}>
{doc.body.trim()}
          </pre>
        </article>
      </div>
    </main>
  );
}
