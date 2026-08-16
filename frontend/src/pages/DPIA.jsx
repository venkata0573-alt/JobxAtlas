import React from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Warning, CheckCircle } from "@phosphor-icons/react";
import { COMPANY } from "@/legal/content";

/**
 * Public Data Protection Impact Assessment summary for the BGV workflow.
 * Follows the structure suggested by:
 *   - GDPR Article 35 & ICO's DPIA template
 *   - CNIL PIA methodology
 *   - India DPDP Act 2023 (once DPB rules the equivalent template)
 * This is the PUBLIC SUMMARY. The full internal DPIA including risk-scoring
 * spreadsheets, sub-processor audits, and log-of-changes is held by the DPO
 * and available to lawful supervisory authorities on request.
 */
export default function DPIA() {
  return (
    <main className="max-w-5xl mx-auto px-6 md:px-12 py-16" data-testid="dpia-page">
      <p className="overline text-[#6B21A8] mb-3">TRANSPARENCY · DPIA SUMMARY</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">
        Background Verification · DPIA
      </h1>
      <p className="text-sm text-neutral-500 font-mono mb-8">
        {COMPANY.product} · operated by {COMPANY.legal_name} under the brand {COMPANY.parent_brand} · CIN {COMPANY.cin} · Rev {COMPANY.version}
      </p>
      <p className="text-neutral-700 max-w-3xl leading-relaxed mb-10">
        A Data Protection Impact Assessment (DPIA) is a structured way of surfacing and mitigating the privacy
        risks of a high-impact data-processing activity <em>before</em> we roll it out to production. This page is
        the public summary of the DPIA we run on our Background Verification workflow — the highest-risk
        processing we do. The full internal document is held by the DPO and shared with lawful supervisory
        authorities on request.
      </p>

      {/* Section 1 — Scope */}
      <Section number="1" title="Scope of the processing">
        <Bullet><b>Purpose.</b> Verify a Talent's work history, references, and government-issued identity so Employers can hire with confidence.</Bullet>
        <Bullet><b>Data subjects.</b> Talent users of Job Atlas (all voluntary sign-ups aged 18+). References nominated by the Talent are also data subjects for their contact + response.</Bullet>
        <Bullet><b>Data categories.</b> Identity (name, gov ID number, photo), contact (email, phone), work history (employer names, dates), references (name, email, response), device metadata (during upload).</Bullet>
        <Bullet><b>Volume.</b> Every Talent who requests the "Blue-tick" BGV badge — currently &lt;1000/mo.</Bullet>
        <Bullet><b>Duration.</b> Verification runs typically complete in 2-7 days. Result is retained for 5 years, then archived in encrypted form.</Bullet>
      </Section>

      {/* Section 2 — Legal basis */}
      <Section number="2" title="Legal basis & necessity">
        <p className="text-sm text-neutral-700 mb-3">
          We rely on the following lawful bases:
        </p>
        <Bullet><b>Consent (GDPR Art. 6(1)(a) / DPDP Sec. 7(a)).</b> Talent explicitly opts in to BGV in-app before we begin.</Bullet>
        <Bullet><b>Contract (GDPR Art. 6(1)(b)).</b> Verified status is required to receive certain paid engagements.</Bullet>
        <Bullet><b>Legitimate interest (Art. 6(1)(f)).</b> Fraud prevention on the marketplace, balancing test recorded in the internal DPIA.</Bullet>
        <p className="text-sm text-neutral-700 mt-3">
          <b>Special-category data:</b> Government-issued ID falls within DPDP "identity documents". We collect
          the minimum necessary field only (ID number + photo), encrypt at rest, and never share with third-party
          marketing or analytics.
        </p>
      </Section>

      {/* Section 3 — Necessity & proportionality */}
      <Section number="3" title="Necessity & proportionality">
        <Bullet>Every field collected is tested against a data-minimisation checklist. Optional fields are marked "optional" in the UI.</Bullet>
        <Bullet>Reference contacts see only the fields the Talent explicitly authorised.</Bullet>
        <Bullet>Employers see the outcome badge + verification date, never the underlying documents.</Bullet>
        <Bullet>Automated approval kicks in only when 2+ references respond positively AND the ID check passes. Human admin review otherwise.</Bullet>
      </Section>

      {/* Section 4 — Risks & mitigations table */}
      <Section number="4" title="Risks identified & mitigations">
        <div className="hard-border bg-white shadow-brutal overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#0B1B2B] text-white">
              <tr>
                <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Risk</th>
                <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Impact</th>
                <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Likelihood</th>
                <th className="text-left px-3 py-2 text-[10px] font-mono uppercase tracking-widest">Mitigation</th>
              </tr>
            </thead>
            <tbody>
              <Row risk="Unauthorised access to gov ID scans"
                   impact="High" likelihood="Low"
                   mitigation="Field-level encryption (AES-256), role-based access, quarterly access review, audit log"/>
              <Row risk="Reference impersonation (fake references)"
                   impact="Medium" likelihood="Medium"
                   mitigation="One-time signed tokens per reference, email confirmation, IP + timestamp logged, admin sample-audit"/>
              <Row risk="Bias in auto-approval algorithm"
                   impact="High" likelihood="Low"
                   mitigation="No protected-class inputs, admin human-in-the-loop for any flagged case, quarterly bias audit"/>
              <Row risk="Data breach at sub-processor"
                   impact="High" likelihood="Low"
                   mitigation="DPA + SCC with every vendor, ISO 27001/SOC 2 required, annual re-review, 30-day notice-of-change"/>
              <Row risk="Excessive retention"
                   impact="Medium" likelihood="Medium"
                   mitigation="Automated purge after 5 years + on erasure request. Retention audit reported to DPO monthly"/>
              <Row risk="Cross-border transfer to non-adequate jurisdictions"
                   impact="Medium" likelihood="Medium"
                   mitigation="EU SCCs (2021/914) with supplementary measures per Schrems II, encryption in transit"/>
              <Row risk="Refusal or withdrawal of consent leaves Talent worse off"
                   impact="Medium" likelihood="Low"
                   mitigation="Withdrawal purges verification records within 30 days. Talent can continue on the platform without a Blue-tick"/>
              <Row risk="Malicious take-down abuse (DMCA/IP)"
                   impact="Low" likelihood="Medium"
                   mitigation="Counter-notice process; repeat-abuser account termination"/>
              <Row risk="Employer misuse of verified status for discriminatory hiring"
                   impact="High" likelihood="Low"
                   mitigation="Terms Section 27 prohibits; auto-flag on ≥5-revision escalations against multiple talents in 60 days"/>
            </tbody>
          </table>
        </div>
      </Section>

      {/* Section 5 — Rights */}
      <Section number="5" title="Data-subject rights honoured">
        <div className="grid md:grid-cols-2 gap-3">
          {[
            "Right of access — GET /api/talent/me returns your full record",
            "Right to rectification — edit anytime under /talent/profile",
            "Right to erasure — email privacy@geminista.io; purge within 30 days",
            "Right to restrict — pause verification anytime",
            "Right to portability — machine-readable JSON export on request",
            "Right to object — including to any profiling used in rate suggestions",
            "Right to complain — DPB India / ICO UK / lead EU DPA",
            "Right to nominate (DPDP §14) — appoint another person to exercise rights on your behalf",
          ].map((r) => (
            <div key={r} className="hard-border bg-white p-3 flex items-start gap-2">
              <CheckCircle size={14} weight="fill" color="#6B21A8" className="mt-1 shrink-0"/>
              <p className="text-xs text-neutral-700 leading-relaxed">{r}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Section 6 — Consultation */}
      <Section number="6" title="Consultation & sign-off">
        <Bullet><b>DPO review.</b> Every version of the BGV workflow is reviewed by our Data Protection Officer before ship.</Bullet>
        <Bullet><b>External counsel.</b> Indian counsel review for DPDP compliance; EU counsel review for GDPR + Schrems II.</Bullet>
        <Bullet><b>User feedback.</b> A dedicated feedback channel (<a className="underline" href={`mailto:${COMPANY.dpo_email}`}>{COMPANY.dpo_email}</a>) is monitored for BGV concerns.</Bullet>
        <Bullet><b>Review cadence.</b> DPIA is re-run every 12 months or on material change to the workflow / sub-processors / applicable law.</Bullet>
      </Section>

      {/* Section 7 — Contact */}
      <div className="hard-border bg-[#F5F3FF] p-6 shadow-brutal mt-10 flex items-start gap-3" data-testid="dpia-contact">
        <div className="hard-border bg-[#6B21A8] text-white w-10 h-10 flex items-center justify-center shrink-0">
          <ShieldCheck size={18} weight="duotone"/>
        </div>
        <div>
          <p className="overline text-[#6B21A8] mb-1">DPO CONTACT</p>
          <p className="text-sm text-neutral-700 leading-relaxed">
            Questions about this DPIA, requests to see the full internal document (for lawful supervisory
            authorities), or complaints about the BGV workflow should be sent to
            {" "}<a className="underline" href={`mailto:${COMPANY.dpo_email}`}>{COMPANY.dpo_email}</a>.
            Grievance route (Indian IT Rules 2021): {COMPANY.grievance_officer_name},{" "}
            <a className="underline" href={`mailto:${COMPANY.grievance_email}`}>{COMPANY.grievance_email}</a>,{" "}
            <a className="underline" href={`tel:${COMPANY.grievance_officer_phone.replace(/\s+/g, "")}`}>{COMPANY.grievance_officer_phone}</a>.
          </p>
          <p className="mt-3 text-xs">
            <Link to="/subprocessors" className="underline underline-offset-4">See our Sub-Processor Register →</Link>
            {" · "}
            <Link to="/legal" className="underline underline-offset-4">Full Privacy Policy →</Link>
          </p>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="hard-border bg-[#FEF9C3] border-yellow-500 p-4 mt-8 flex items-start gap-3">
        <div className="hard-border bg-[#0B1B2B] text-[#A78BFA] w-9 h-9 flex items-center justify-center shrink-0">
          <Warning size={18} weight="duotone"/>
        </div>
        <p className="text-xs text-neutral-700 leading-relaxed">
          This is the public summary. It is not a substitute for professional legal advice. Enterprise buyers may
          request the full internal DPIA (with risk-scoring matrix, sub-processor audit reports and mitigation log)
          under NDA by emailing our DPO.
        </p>
      </div>
    </main>
  );
}

function Section({ number, title, children }) {
  return (
    <section className="mb-10" data-testid={`dpia-section-${number}`}>
      <div className="flex items-baseline gap-3 mb-3">
        <span className="font-display font-black text-3xl text-[#6B21A8]">{number}</span>
        <h2 className="font-display font-extrabold text-2xl tracking-tight text-[#0B1B2B]">{title}</h2>
      </div>
      <div className="pl-12 space-y-2">{children}</div>
    </section>
  );
}

function Bullet({ children }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-[#6B21A8] font-black mt-0.5">·</span>
      <p className="text-sm text-neutral-700 leading-relaxed">{children}</p>
    </div>
  );
}

function Row({ risk, impact, likelihood, mitigation }) {
  const chip = (v) => {
    const s = v.toLowerCase();
    if (s === "high") return "bg-red-100 text-red-800";
    if (s === "medium") return "bg-yellow-100 text-yellow-800";
    return "bg-emerald-100 text-emerald-800";
  };
  return (
    <tr className="border-t border-black/10 align-top">
      <td className="px-3 py-3 font-display font-extrabold text-[13px] text-[#0B1B2B]">{risk}</td>
      <td className="px-3 py-3">
        <span className={`text-[10px] font-mono uppercase tracking-widest px-2 py-0.5 ${chip(impact)}`}>{impact}</span>
      </td>
      <td className="px-3 py-3">
        <span className={`text-[10px] font-mono uppercase tracking-widest px-2 py-0.5 ${chip(likelihood)}`}>{likelihood}</span>
      </td>
      <td className="px-3 py-3 text-[12px] text-neutral-700">{mitigation}</td>
    </tr>
  );
}
