import React from "react";
import { Link } from "react-router-dom";
import Marquee from "@/components/Marquee";
import DemoTabs from "@/components/DemoTabs";
import { TID } from "@/constants/testIds";
import {
  ShieldCheck, Handshake, Sparkle, PuzzlePiece,
  Clock, Globe, Certificate, ChartLineUp, Star, Quotes,
} from "@phosphor-icons/react";

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

const TRUST_LOGOS = ["Jira", "Asana", "Confluence", "Monday", "Wrike", "ServiceNow", "SAP", "MS Dynamics"];

const TESTIMONIALS = [
  { name: "Amelia R.",  role: "COO, SaaS Scale-up",  quote: "We assembled a five-person product squad in an afternoon. Signed contracts, hours logged inside Jira, done." },
  { name: "Devon P.",   role: "Independent Engineer", quote: "AI suggested my rate, and it stuck. I now work across three companies without a single email chain about invoices." },
  { name: "Sana M.",    role: "Head of Design",      quote: "Every deliverable comes with a moderated review. The exclusivity clause finally made freelance feel like a real profession." },
];

const FAQ = [
  { q: "How is Job Atlas different from Upwork or Fiverr?",
    a: "We're structured. Employers buy hours in bulk and allocate them. Both sides sign a contract. Talent is bound by a 12-month exclusivity clause so no side-door hiring. Our platform fee is 8% (vs 20%)." },
  { q: "Can I hire multiple people from one hour-package?",
    a: "Yes — that's the whole point. Purchase once, mix & match hours across as many talent as you like." },
  { q: "How does the AI hourly rate suggestion work?",
    a: "Claude Sonnet 5 analyses your skills, experience and market data to suggest a fair hourly rate range in seconds. You can accept, adjust, or override." },
  { q: "Which project tools do you integrate with?",
    a: "Jira, Asana, Confluence, Monday, Wrike, ServiceNow, SAP, MS Dynamics, Trello, ClickUp, Notion — plus Excel and MS Project XML uploads." },
  { q: "Do you have a mobile app?",
    a: "Yes. Job Atlas is available as a Progressive Web App on Android and iOS today, and as native app-store shells via Capacitor." },
  { q: "How are payments handled?",
    a: "Employers pay by card via Stripe or by bank transfer / UPI. Talent are paid out via Stripe, Payoneer, Wise or direct bank credit." },
];

export default function Landing() {
  return (
    <main className="bg-white">
      {/* HERO */}
      <section className="relative border-b border-black bg-[#0A0A0A] text-white">
        <div className="absolute inset-0 opacity-40" style={{ backgroundImage: `url(${HERO})`, backgroundSize: "cover", backgroundPosition: "center" }} />
        <div className="absolute inset-0 bg-black/40" />
        <div className="relative max-w-7xl mx-auto px-6 md:px-12 py-24 md:py-40">
          <p className="overline text-[#FF0A0A] mb-6">The premium marketplace for hourly experts</p>
          <h1 className="font-display font-extrabold text-5xl sm:text-6xl lg:text-7xl tracking-tight leading-[0.95] max-w-4xl">
            Hire experts by the hour.<br/>
            Ship projects by the week.<br/>
            <span className="text-[#FF0A0A]">Grow without the guesswork.</span>
          </h1>
          <p className="mt-8 max-w-2xl text-lg text-neutral-300 leading-relaxed">
            Job Atlas connects world-class freelance developers, designers and consultants with the companies
            that need them — hours purchased once, allocated across a shortlist, every engagement contracted
            and tracked inside your existing tools.
          </p>
          <div className="mt-12 flex flex-wrap gap-4">
            <Link to="/register" className="btn-primary shadow-brutal shadow-brutal-hover" data-testid={TID.landingGetStarted}>
              Start free →
            </Link>
            <Link to="/browse" className="btn-outline shadow-brutal shadow-brutal-hover" data-testid={TID.landingBrowseTalent}
                  style={{background:"#fff", color:"#0A0A0A"}}>
              Browse talent
            </Link>
            <Link to="/pricing" className="text-white/80 hover:text-white underline underline-offset-4 self-center text-sm">
              See pricing →
            </Link>
          </div>
          <div className="mt-14 flex flex-wrap gap-x-8 gap-y-3 text-sm text-neutral-400 font-mono">
            <span className="inline-flex items-center gap-2"><Star weight="fill" color="#FF0A0A" size={14}/> Vetted global talent pool</span>
            <span className="inline-flex items-center gap-2"><ShieldCheck weight="fill" color="#FF0A0A" size={14}/> Signed dual-party contracts</span>
            <span className="inline-flex items-center gap-2"><Certificate weight="fill" color="#FF0A0A" size={14}/> 8% platform fee — half of the market</span>
          </div>
        </div>
      </section>

      <Marquee />

      {/* Trust bar — integrations */}
      <section className="border-b border-black/10 bg-white py-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <p className="overline text-neutral-500 mb-6 text-center">Works with your stack</p>
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
            {TRUST_LOGOS.map((t) => (
              <span key={t} className="font-display font-extrabold text-neutral-400 hover:text-black transition-colors tracking-tight text-2xl">{t}</span>
            ))}
          </div>
        </div>
      </section>

      {/* STATS bento */}
      <section className="max-w-7xl mx-auto px-6 md:px-12 py-24 grid grid-cols-2 md:grid-cols-4 gap-0 border-l border-t border-black/10">
        {[
          {k:"12", label:"Months of exclusivity"},
          {k:"AI", label:"Rate suggestions"},
          {k:"8%", label:"Platform fee"},
          {k:"11+", label:"Native integrations"},
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
            One platform. Three unbreakable rules.
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            <Feature Icon={Sparkle}      title="1. AI-priced skills"   desc="Talent adds skills & years of experience. Claude Sonnet 5 suggests a market-aligned hourly rate range in seconds."/>
            <Feature Icon={Clock}        title="2. Buy hours in bulk"  desc="Employers purchase hour packages and allocate them freely across a shortlist. Cheaper than hiring one full-time."/>
            <Feature Icon={Handshake}    title="3. Sign & work"        desc="Both parties sign a typed-signature contract. Then the meter starts — inside the platform only, tracked in your tools."/>
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
            Employers cannot directly hire talent introduced via Job Atlas, and talent cannot work directly for
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
            Plug in Jira, Asana, Confluence, SAP…
          </h3>
          <p className="text-neutral-700 leading-relaxed">
            Connect your project tools or upload Excel / MS Project XML plans. Job Atlas pulls tasks, statuses
            and hours logged so every engagement has a single source of truth.
          </p>
          <div className="mt-6 flex flex-wrap gap-2 text-xs font-mono">
            {["Jira", "Asana", "Confluence", "Monday", "Wrike", "MS Dynamics", "ServiceNow", "SAP", ".xlsx", ".xml"].map((t) => (
              <span key={t} className="hard-border px-2 py-1 bg-[#F9F9F9]">{t}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="bg-[#F9F9F9] border-t border-black/10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-24">
          <p className="overline text-[#002FA7] mb-3">LOVED BY BOTH SIDES</p>
          <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight max-w-2xl mb-16">
            The marketplace freelancers and CFOs finally agree on.
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {TESTIMONIALS.map((t, i) => (
              <blockquote key={i} className={`hard-border bg-white p-8 shadow-brutal ${i === 1 ? "md:-translate-y-3" : ""}`}>
                <Quotes size={28} weight="fill" color="#002FA7"/>
                <p className="mt-4 leading-relaxed">{t.quote}</p>
                <footer className="mt-6 border-t border-black/10 pt-4">
                  <p className="font-display font-extrabold tracking-tight">{t.name}</p>
                  <p className="overline text-neutral-500">{t.role}</p>
                </footer>
              </blockquote>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="max-w-4xl mx-auto px-6 md:px-12 py-24" itemScope itemType="https://schema.org/FAQPage">
        <p className="overline text-[#002FA7] mb-3">FREQUENTLY ASKED</p>
        <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-12">Straight answers.</h2>
        <div className="divide-y divide-black/10 hard-border bg-white shadow-brutal">
          {FAQ.map((f, i) => (
            <details key={i} className="p-6 group" itemScope itemType="https://schema.org/Question" itemProp="mainEntity">
              <summary className="cursor-pointer list-none flex justify-between items-center font-display font-extrabold text-lg tracking-tight" itemProp="name">
                <span>{f.q}</span>
                <span className="text-2xl group-open:rotate-45 transition-transform">+</span>
              </summary>
              <div itemScope itemType="https://schema.org/Answer" itemProp="acceptedAnswer">
                <p className="mt-3 text-neutral-600 leading-relaxed" itemProp="text">{f.a}</p>
              </div>
            </details>
          ))}
        </div>
      </section>

      <section className="border-t border-black/10 bg-[#FAF9F6]">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-14">
          <p className="overline text-[#C79A3B] mb-6 text-center">SIGNED &amp; ENDORSED BY DENKOIT SOFTECH LEADERSHIP</p>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { name: "Sowmya D.",     role: "Chief Executive Officer" },
              { name: "Rajesh K.",     role: "Chief Technology Officer" },
              { name: "Vikram M.",     role: "Head of Client Success" },
            ].map(s => (
              <div key={s.name} className="hard-border bg-white p-6 text-center">
                <p className="font-signature text-4xl text-[#0B1B2B] leading-tight">{s.name}</p>
                <div className="w-16 h-px bg-[#C79A3B] mx-auto my-3"/>
                <p className="text-xs font-mono text-neutral-500 uppercase tracking-widest">{s.role}</p>
              </div>
            ))}
          </div>
          <p className="text-center text-xs font-mono text-neutral-500 mt-8">
            Job Atlas is operated with the same standards of governance that define Job Atlas&apos;s enterprise practice.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-black/10 bg-[#0B1B2B] text-white">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-24 flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          <div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Ready when you are.</h2>
            <p className="mt-3 text-neutral-400 max-w-lg">Create your account in under a minute. Talent or employer, you decide.
              First engagements are always free — no credit card required.</p>
          </div>
          <div className="flex gap-3">
            <Link to="/register" className="btn-primary shadow-brutal">Start free →</Link>
            <Link to="/pricing" className="btn-outline shadow-brutal" style={{background:"#fff", color:"#0A0A0A"}}>See pricing</Link>
          </div>
        </div>
      </section>

      <footer className="bg-black text-neutral-500 text-sm border-t border-neutral-900">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-12 grid md:grid-cols-4 gap-8 font-mono">
          <div>
            <p className="text-white font-display font-extrabold tracking-tight text-lg mb-2">JOB ATLAS</p>
            <p>Operated by <span className="text-white">Denkoit Softech Pvt. Ltd.</span></p>
            <p className="mt-2">Structured hiring for a global workforce.</p>
          </div>
          <div>
            <p className="text-neutral-300 mb-2">Product</p>
            <p><Link to="/browse" className="hover:text-white">Browse talent</Link></p>
            <p><Link to="/pricing" className="hover:text-white">Pricing</Link></p>
            <p><Link to="/register" className="hover:text-white">Sign up</Link></p>
            <p><Link to="/login" className="hover:text-white">Sign in</Link></p>
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
            <p className="mt-4 text-neutral-600">Operated by Denkoit Softech Pvt. Ltd.</p>
            <p className="text-neutral-600">GSTIN 36AAGCD3748K1ZC</p>
            <p className="mt-3">© 2026 Job Atlas</p>
          </div>
        </div>
      </footer>
    </main>
  );
}
