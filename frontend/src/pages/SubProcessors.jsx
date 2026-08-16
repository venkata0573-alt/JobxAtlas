import React from "react";
import { Link } from "react-router-dom";
import { CloudArrowUp, ShieldCheck } from "@phosphor-icons/react";
import { COMPANY } from "@/legal/content";

// Curated register of sub-processors. Update whenever a new vendor is engaged
// and republish. Categories map to the Privacy Policy section 5.
const REGISTER = [
  {
    category: "Payments",
    items: [
      { name: "Stripe, Inc.",              purpose: "Card & bank payments, refunds, Connect payouts", data: "Card metadata, payer name/email, transaction IDs",       location: "USA (with EU sub-processors)", safeguards: "PCI-DSS Level 1, EU SCCs",                    link: "https://stripe.com/privacy" },
      { name: "UPI / Indian banks",        purpose: "Domestic INR transfers",                          data: "Beneficiary reference, amount, timestamp",                location: "India",                        safeguards: "RBI-regulated",                                 link: "https://www.rbi.org.in" },
    ],
  },
  {
    category: "Cloud & infrastructure",
    items: [
      { name: "Enterprise cloud host",     purpose: "Compute, storage, database hosting",              data: "All personal data at rest (encrypted)",                    location: "India + failover EU",          safeguards: "ISO 27001, SOC 2 Type II, EU SCCs where relevant", link: "" },
      { name: "Cloudflare, Inc.",          purpose: "CDN, DDoS protection, Turnstile CAPTCHA",         data: "IP address, request headers, challenge tokens",           location: "USA (edge global)",            safeguards: "EU SCCs, ISO 27001",                            link: "https://www.cloudflare.com/privacypolicy/" },
    ],
  },
  {
    category: "Email delivery",
    items: [
      { name: "Resend (Beacon Labs, Inc.)", purpose: "Transactional emails (verify, notifications)",   data: "Recipient email, subject, body content",                  location: "USA",                          safeguards: "EU SCCs",                                       link: "https://resend.com/legal/privacy-policy" },
    ],
  },
  {
    category: "AI / LLM providers",
    items: [
      { name: "Anthropic PBC",             purpose: "Resume parsing, rate suggestions",                data: "Redacted resume text (no PII if avoidable)",              location: "USA",                          safeguards: "Zero-retention API mode, EU SCCs, model-training opt-out", link: "https://www.anthropic.com/legal/privacy" },
      { name: "OpenAI, LLC",               purpose: "Optional resume parsing fallback",                data: "Redacted resume text",                                    location: "USA",                          safeguards: "Zero-retention API mode, EU SCCs",              link: "https://openai.com/policies/privacy-policy" },
      { name: "Google LLC (Gemini API)",   purpose: "Rate suggestions",                                data: "Skill list, experience years, city",                      location: "USA / EU multi-region",        safeguards: "EU SCCs, no training on API data",              link: "https://cloud.google.com/terms/data-processing-addendum" },
      { name: "Emergent LLM Gateway",      purpose: "Routing to the above LLM providers",              data: "Routed prompts + metadata",                               location: "Global",                       safeguards: "Pass-through only, provider terms apply",       link: "" },
    ],
  },
  {
    category: "Object storage",
    items: [
      { name: "Emergent Object Storage",   purpose: "Portfolios, resumes, deliverable files",          data: "Uploaded files + metadata",                               location: "Global (multi-region)",        safeguards: "Encryption at rest, per-tenant isolation",     link: "" },
    ],
  },
  {
    category: "Background verification (BGV)",
    items: [
      { name: "Reference-check emails",    purpose: "Direct reference validation",                     data: "Reference name, email, Y/N response",                     location: "Global (via Resend)",          safeguards: "One-time signed tokens, per-check retention",  link: "" },
      { name: "KYB providers",             purpose: "Employer legal-entity verification",              data: "Tax ID, incorporation docs, UBOs",                        location: "India-regulated + intl.",      safeguards: "Vendor list on request from DPO",              link: "" },
    ],
  },
  {
    category: "Fraud & security",
    items: [
      { name: "Cloudflare Turnstile",      purpose: "Bot detection at registration",                    data: "Challenge token, IP",                                     location: "USA (edge global)",            safeguards: "EU SCCs, session-scoped only",                 link: "https://www.cloudflare.com/products/turnstile/" },
    ],
  },
  {
    category: "Third-party integrations (user-initiated)",
    items: [
      { name: "HubSpot",                    purpose: "CRM push of shortlisted talent",                  data: "OAuth token, contact names",                             location: "USA / EU",                     safeguards: "User authorises scope; encrypted-at-rest token", link: "https://legal.hubspot.com/privacy-policy" },
      { name: "Salesforce",                 purpose: "CRM lead push",                                    data: "OAuth token, lead payload",                              location: "USA / EU",                     safeguards: "User-authorised; encrypted-at-rest",             link: "https://www.salesforce.com/company/legal/privacy/" },
      { name: "Slack",                      purpose: "Broadcast + status webhooks",                     data: "Bot token, channel IDs",                                  location: "USA",                          safeguards: "User-authorised; encrypted-at-rest",             link: "https://slack.com/trust/privacy/privacy-policy" },
      { name: "Microsoft SharePoint",       purpose: "Task-file sync",                                   data: "Graph API token, document metadata",                     location: "USA / EU",                     safeguards: "User-authorised; encrypted-at-rest",             link: "https://privacy.microsoft.com/privacystatement" },
      { name: "Google Calendar",            purpose: "Availability + meeting sync",                     data: "OAuth token, event metadata",                            location: "USA / EU",                     safeguards: "User-authorised; encrypted-at-rest",             link: "https://policies.google.com/privacy" },
    ],
  },
];

export default function SubProcessors() {
  return (
    <main className="max-w-6xl mx-auto px-6 md:px-12 py-16" data-testid="subprocessors-page">
      <p className="overline text-[#6B21A8] mb-3">TRANSPARENCY · SUB-PROCESSOR REGISTER</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">Everyone who touches your data.</h1>
      <p className="text-sm text-neutral-500 font-mono mb-6">
        {COMPANY.product} · {COMPANY.parent_brand} · {COMPANY.legal_name} · CIN {COMPANY.cin} · Register {COMPANY.version}
      </p>
      <p className="text-neutral-600 max-w-3xl mb-10 leading-relaxed">
        This page names every third-party sub-processor that may process personal data on our behalf. We keep the list short on purpose.
        Each entry lists the vendor, the specific purpose, the categories of data involved, the hosting jurisdiction, and the safeguards in place.
        For questions or to receive notice of new sub-processors before they go live, subscribe by emailing <a className="underline" href={`mailto:${COMPANY.dpo_email}`}>{COMPANY.dpo_email}</a>.
      </p>

      <div className="hard-border bg-[#F5F3FF] p-4 mb-10 flex items-start gap-3" data-testid="subprocessor-safeguards-note">
        <div className="hard-border bg-[#0B1B2B] text-[#A78BFA] w-9 h-9 flex items-center justify-center shrink-0">
          <ShieldCheck size={18} weight="duotone"/>
        </div>
        <div className="text-sm">
          <p className="font-display font-extrabold text-[#0B1B2B]">Safeguards we apply across the board</p>
          <ul className="text-[13px] text-neutral-700 mt-1 leading-relaxed list-disc pl-5">
            <li>Data-processing agreements (DPAs) with every vendor before onboarding.</li>
            <li>EU Standard Contractual Clauses (2021/914) for transfers outside the EEA/UK.</li>
            <li>Encryption in transit (TLS 1.2+) and at rest for sensitive fields.</li>
            <li>Vendor security review + annual re-review.</li>
            <li>30-day notice to users before adding a new sub-processor to a live product.</li>
          </ul>
        </div>
      </div>

      {REGISTER.map((section) => (
        <section key={section.category} className="mb-10" data-testid={`subprocessor-section-${section.category.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}>
          <div className="flex items-center gap-3 mb-3">
            <div className="hard-border bg-[#6B21A8] text-white w-8 h-8 flex items-center justify-center">
              <CloudArrowUp size={16} weight="duotone"/>
            </div>
            <h2 className="font-display font-extrabold text-2xl tracking-tight">{section.category}</h2>
          </div>
          <div className="hard-border bg-white shadow-brutal overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#0B1B2B] text-white">
                <tr>
                  <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Vendor</th>
                  <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Purpose</th>
                  <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Data categories</th>
                  <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Location</th>
                  <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Safeguards</th>
                </tr>
              </thead>
              <tbody>
                {section.items.map((row) => (
                  <tr key={row.name} className="border-t border-black/10 align-top">
                    <td className="px-3 py-3 font-display font-extrabold text-[13px] text-[#0B1B2B]">
                      {row.name}
                      {row.link && (
                        <a href={row.link} target="_blank" rel="noreferrer" className="block text-[10px] font-mono text-[#6B21A8] underline underline-offset-4 mt-1">
                          Privacy policy ↗
                        </a>
                      )}
                    </td>
                    <td className="px-3 py-3 text-[13px] text-neutral-700">{row.purpose}</td>
                    <td className="px-3 py-3 text-[12px] text-neutral-600">{row.data}</td>
                    <td className="px-3 py-3 text-[12px] text-neutral-600">{row.location}</td>
                    <td className="px-3 py-3 text-[12px] text-neutral-600">{row.safeguards}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <section className="hard-border bg-white p-6 shadow-brutal">
        <p className="overline text-[#6B21A8] mb-2">Notice of change</p>
        <p className="text-sm text-neutral-700 leading-relaxed">
          We will publish an update to this page and email subscribed users at least 30 days before adding any new sub-processor that will process personal data on our behalf,
          except where required to onboard urgently for security or continuity reasons. In such cases the change is posted here and users notified without undue delay.
        </p>
        <p className="text-xs text-neutral-500 mt-3">
          To object to a new sub-processor, email <a className="underline" href={`mailto:${COMPANY.dpo_email}`}>{COMPANY.dpo_email}</a> within 30 days of the notice.
          The Company will consider the objection in good faith; where a resolution cannot be reached, either party may terminate the affected service.
        </p>
        <p className="mt-4 text-xs">
          <Link to="/legal" className="underline underline-offset-4">Read the full Privacy Policy →</Link>
        </p>
      </section>
    </main>
  );
}
