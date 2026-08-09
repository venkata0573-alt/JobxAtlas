import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { FileText } from "@phosphor-icons/react";

const DOCS = {
  terms: {
    title: "Terms of Service",
    body: `These Terms govern your access to and use of TalentHub (the "Platform"), a product of Geminsta operated by
Denkoit Softech Pvt. Ltd., a company registered in Hyderabad, Telangana, India (GSTIN 36AAGCD3748K1ZC).

1. Eligibility. You must be 18+ and legally able to enter into contracts in your jurisdiction.
2. Marketplace role. The Platform introduces employers and independent professionals ("Talent"). We are not the
   employer of the Talent nor the agent of any employer. All engagements are contracts between the parties.
3. Hour packages & payments. Employers purchase hour packages via card or Indian bank transfer. Hours are
   allocated by the employer to specific engagements, tracked and deducted per approved deliverable.
4. 12-Month Exclusivity. Talent introduced to an Employer via the Platform may not be hired or engaged
   directly outside the Platform for 12 months from first engagement, and vice versa. Breach entitles the
   Platform to a liquidated fee equal to six (6) months of projected fees.
5. On-site engagements. Where an engagement is on-site or hybrid, both parties must acknowledge the health,
   safety, transport and legal-conduct clauses recorded in the contract before signing.
6. Illegal conduct. Any illegal act at the work location is the sole responsibility of the acting party. The
   Platform disclaims all liability, does not condone and does not support such conduct.
7. Fees. Employer platform fee is 8% of hours purchased on paid plans. Talent commission on hourly rates is
   volume-tiered (8% → 4%). A multi-employer monthly fee of $9 / ₹749 applies when a Talent has active
   engagements with more than one Employer in the same calendar month.
8. Termination. Either party may terminate an engagement for cause on 7 days notice. Unused hours revert.
9. Governing law. These Terms are governed by the laws of India. Courts of Hyderabad shall have exclusive
   jurisdiction.`
  },
  privacy: {
    title: "Privacy Policy",
    body: `Denkoit Softech Pvt. Ltd. ("we") collects and processes personal data to operate TalentHub. We are the
data controller for the purposes of applicable data-protection laws including India's Digital Personal Data
Protection Act.

Data we collect: name, email, payment metadata, profile & portfolio info you upload, connected accounts &
tokens (encrypted at rest), calendar availability, engagement & deliverable records.

Purpose: providing the service, fraud prevention, statutory reporting (including GST invoicing), grievance
handling, and product improvement.

Retention: engagement records are retained for 7 years for statutory & tax compliance. You may request
deletion of personal data not required for such compliance by writing to grievance@talenthub.io.

International transfers: we may use sub-processors outside India (Stripe, cloud hosting) with appropriate
contractual safeguards.

Cookies: session cookies for authentication (httpOnly). No third-party ad tracking.

Your rights: access, rectification, portability, and erasure — write to grievance@talenthub.io with a copy of
your ID for verification.`
  },
  refund: {
    title: "Refund Policy",
    body: `1. Unused hours are refundable at the employer's request within 12 months of purchase, minus the platform
   fee and any transaction fees. Bank-transfer refunds are processed within 7 working days.
2. Hours already allocated to signed engagements are not refundable but may be reassigned to another
   talent on the platform if the original engagement is terminated for cause.
3. Subscription plan fees (Starter, Growth) are non-refundable but can be cancelled anytime and take effect
   at the end of the current billing cycle.
4. Multi-employer monthly fees for talent are charged in arrears and are non-refundable once billed.
5. All refund requests must be submitted in writing to grievance@talenthub.io with the transaction reference.`
  },
  acceptable_use: {
    title: "Acceptable Use",
    body: `You may not use TalentHub to:
· Circumvent the platform to transact directly with an introduced party (breach of exclusivity).
· Post misleading skills, credentials or portfolio.
· Upload malware, illegal content, or content that violates intellectual property rights.
· Harass, threaten or discriminate against other users.
· Engage in illegal activity — the platform will suspend accounts and cooperate with lawful investigations.`
  },
  exclusivity: {
    title: "12-Month Exclusivity Terms",
    body: `The exclusivity clause is a foundational protection for the Platform's marketplace. For 12 months from the
effective date of any signed engagement:
· Employer shall not directly engage, hire or contract the Talent outside the Platform.
· Talent shall not accept work directly from the Employer outside the Platform.
· All communication and payment must remain on-platform.
· Introductions to third parties from either side are subject to the same 12-month period.

Breach entitles the Platform to invoice a liquidated fee equal to six (6) months of the projected engagement
fees, plus recovery of reasonable enforcement costs.`
  },
};

export default function Legal() {
  const [legal, setLegal] = useState(null);
  const [active, setActive] = useState("terms");
  useEffect(() => { api.get("/legal").then((r) => setLegal(r.data)); }, []);

  return (
    <main className="max-w-6xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">LEGAL &amp; COMPLIANCE</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">Everything, in writing.</h1>
      {legal && (
        <p className="text-sm text-neutral-500 font-mono mb-8">
          {legal.company.product} · {legal.company.brand} · {legal.company.legal_name} · {legal.company.registered_office} · GSTIN {legal.company.gstin}
        </p>
      )}

      <div className="grid md:grid-cols-[220px_1fr] gap-6">
        <nav className="hard-border bg-white p-4 shadow-brutal h-fit">
          <p className="overline mb-3">Documents</p>
          <ul className="space-y-1">
            {Object.entries(DOCS).map(([id, d]) => (
              <li key={id}>
                <button onClick={() => setActive(id)}
                        className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 ${active === id ? "bg-[#0A0A0A] text-white" : "hover:bg-neutral-100"}`}>
                  <FileText size={14} weight="duotone"/> {d.title}
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-6 pt-4 border-t border-black/10 text-xs font-mono text-neutral-500">
            <p>Support: hello@talenthub.io</p>
            <p>Grievance: grievance@talenthub.io</p>
            <p className="mt-2"><Link to="/grievance" className="underline">Raise a grievance →</Link></p>
          </div>
        </nav>
        <article className="hard-border bg-white p-8 md:p-10 shadow-brutal">
          <h2 className="font-display font-extrabold text-3xl tracking-tight mb-6">{DOCS[active].title}</h2>
          <pre className="whitespace-pre-wrap font-body leading-relaxed text-sm text-neutral-800" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
{DOCS[active].body}
          </pre>
        </article>
      </div>
    </main>
  );
}
