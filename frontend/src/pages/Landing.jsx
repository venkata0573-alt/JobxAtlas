import React from "react";
import { Link } from "react-router-dom";
import Marquee from "@/components/Marquee";
import DemoTabs from "@/components/DemoTabs";
import { TID } from "@/constants/testIds";
import { ShieldCheck, Handshake, Sparkle, PuzzlePiece, FileArrowUp, Clock } from "@phosphor-icons/react";

const HERO = "https://images.pexels.com/photos/18502918/pexels-photo-18502918.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";

const Feature = ({ Icon, title, desc }) => (
  <div className="hard-border bg-white p-8">
    <div className="hard-border bg-[#002FA7] text-white w-12 h-12 flex items-center justify-center mb-6">
      <Icon size={22} weight="duotone" />
    </div>
    <h3 className="font-display font-extrabold text-2xl tracking-tight mb-2">{title}</h3>
    <p className="text-neutral-600 leading-relaxed">{desc}</p>
  </div>
);

export default function Landing() {
  return (
    <main className="bg-white">
      {/* HERO */}
      <section className="relative hard-border-b bg-[#0A0A0A] text-white">
        <div className="absolute inset-0 opacity-40" style={{ backgroundImage: `url(${HERO})`, backgroundSize: "cover", backgroundPosition: "center" }} />
        <div className="absolute inset-0 bg-black/40" />
        <div className="relative max-w-7xl mx-auto px-6 md:px-12 py-24 md:py-36">
          <p className="overline text-[#FF0A0A] mb-6">TalentHub · Vetted Marketplace</p>
          <h1 className="font-display font-extrabold text-5xl sm:text-6xl lg:text-7xl tracking-tight leading-[0.95] max-w-4xl">
            Hire hours.<br/>
            Not headaches.<br/>
            <span className="text-[#FF0A0A]">Mix & match.</span>
          </h1>
          <p className="mt-8 max-w-2xl text-lg text-neutral-300 leading-relaxed">
            A structured marketplace where independent professionals showcase their skills and employers buy hours in bulk.
            Every engagement is contracted, tracked, and protected by a 12-month exclusivity clause.
          </p>
          <div className="mt-12 flex flex-wrap gap-4">
            <Link to="/register" className="btn-primary shadow-brutal shadow-brutal-hover" data-testid={TID.landingGetStarted}>
              Get started free →
            </Link>
            <Link to="/browse" className="btn-outline shadow-brutal shadow-brutal-hover" data-testid={TID.landingBrowseTalent}
                  style={{background:"#fff", color:"#0A0A0A"}}>
              Browse Talent
            </Link>
          </div>
        </div>
      </section>

      <Marquee />

      {/* STATS bento */}
      <section className="max-w-7xl mx-auto px-6 md:px-12 py-24 grid grid-cols-2 md:grid-cols-4 gap-0 border-l border-t border-black/10">
        {[
          {k:"12", label:"Months of exclusivity"},
          {k:"AI", label:"Rate suggestions"},
          {k:"∞", label:"Mix & match hours"},
          {k:"2✕", label:"Signed contracts"},
        ].map((s, i) => (
          <div key={i} className="p-10 border-r border-b border-black/10">
            <div className="font-display font-extrabold text-5xl md:text-6xl tracking-tight">{s.k}</div>
            <p className="mt-2 overline text-neutral-500">{s.label}</p>
          </div>
        ))}
      </section>

      {/* HOW IT WORKS */}
      <section className="bg-[#F9F9F9] border-t border-black/10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-24">
          <p className="overline text-[#002FA7] mb-3">HOW IT WORKS</p>
          <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight max-w-2xl mb-16">
            One platform, three unbreakable rules.
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            <Feature Icon={Sparkle}      title="1. AI-priced skills"   desc="Talent adds skills & years of experience. Claude Sonnet suggests a market-aligned hourly rate range."/>
            <Feature Icon={Clock}        title="2. Buy hours in bulk"  desc="Employers purchase hour packages via Stripe and allocate them freely across shortlisted talent."/>
            <Feature Icon={Handshake}    title="3. Sign & work"        desc="Both parties sign a typed-signature contract. Then the meter starts running — inside the platform only."/>
          </div>
        </div>
      </section>

      <DemoTabs />

      {/* Exclusivity + Work tracking */}
      <section className="max-w-7xl mx-auto px-6 md:px-12 py-24 grid md:grid-cols-2 gap-6">
        <div className="hard-border bg-[#FDFCF0] p-10 md:p-14 shadow-brutal">
          <div className="hard-border bg-[#FF0A0A] text-white w-12 h-12 flex items-center justify-center mb-6">
            <ShieldCheck size={22} weight="duotone" />
          </div>
          <p className="overline text-[#FF0A0A] mb-3">12-Month Exclusivity</p>
          <h3 className="font-display font-extrabold text-3xl tracking-tight mb-4">
            No side-doors. Ever.
          </h3>
          <p className="text-neutral-700 leading-relaxed">
            Employers cannot directly hire talent introduced via TalentHub, and talent cannot work directly for
            introduced employers — for 12 months. Contact details stay hidden until hours are purchased and a
            contract is signed by both parties.
          </p>
        </div>
        <div className="hard-border bg-white p-10 md:p-14 shadow-brutal">
          <div className="hard-border bg-[#002FA7] text-white w-12 h-12 flex items-center justify-center mb-6">
            <PuzzlePiece size={22} weight="duotone" />
          </div>
          <p className="overline text-[#002FA7] mb-3">Work tracked automatically</p>
          <h3 className="font-display font-extrabold text-3xl tracking-tight mb-4">
            Plug in Monday, Wrike, Jira, SAP…
          </h3>
          <p className="text-neutral-700 leading-relaxed">
            Connect your project tools or upload Excel / MS Project XML plans. TalentHub pulls tasks, statuses and
            hours logged so every engagement has a single source of truth.
          </p>
          <div className="mt-6 flex flex-wrap gap-2 text-xs font-mono">
            {["Monday", "Wrike", "MS Dynamics", "ServiceNow", "SAP", "Asana", "Jira", "Trello", "ClickUp", "Notion", ".xlsx", ".xml"].map((t) => (
              <span key={t} className="hard-border px-2 py-1 bg-[#F9F9F9]">{t}</span>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-black/10 bg-[#0A0A0A] text-white">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-20 flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          <div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Ready when you are.</h2>
            <p className="mt-3 text-neutral-400 max-w-lg">Create your account in under a minute. Talent or Employer, you decide.</p>
          </div>
          <Link to="/register" className="btn-primary shadow-brutal">Sign up →</Link>
        </div>
      </section>

      <footer className="bg-black text-neutral-500 text-sm border-t border-neutral-900">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-10 grid md:grid-cols-4 gap-6 font-mono">
          <div>
            <p className="text-white font-display font-extrabold tracking-tight text-lg mb-2">TALENTHUB</p>
            <p>A product of <span className="text-white">Geminsta</span></p>
            <p>Operated by Denkoit Softech Pvt. Ltd.</p>
            <p>Hyderabad, Telangana, India</p>
            <p className="mt-2">GSTIN: 36AAGCD3748K1ZC</p>
          </div>
          <div>
            <p className="text-neutral-300 mb-2">Payments</p>
            <p>Stripe (Cards · Global)</p>
            <p>Direct bank transfer / UPI (India)</p>
            <p>GST invoice available</p>
          </div>
          <div>
            <p className="text-neutral-300 mb-2">Company</p>
            <p><Link to="/legal" className="hover:text-white">Terms &amp; Privacy</Link></p>
            <p><Link to="/legal" className="hover:text-white">Refund policy</Link></p>
            <p><Link to="/legal" className="hover:text-white">Acceptable use</Link></p>
            <p><Link to="/grievance" className="hover:text-white">Raise a grievance</Link></p>
          </div>
          <div>
            <p className="text-neutral-300 mb-2">Contact</p>
            <p>hello@talenthub.io</p>
            <p>grievance@talenthub.io</p>
            <p className="mt-3">© 2026 Denkoit Softech Pvt. Ltd.</p>
          </div>
        </div>
      </footer>
    </main>
  );
}
