import React, { useEffect, useState } from "react";
import { CaretLeft, CaretRight, SpeakerHigh, SpeakerX, Check } from "@phosphor-icons/react";

/**
 * Step-by-step "How it works" — user paced (Prev / Next), with an optional
 * narration button. No autoplay. Real product screenshots + a visual "hotspot"
 * that points to the UI element being described in that step.
 */

const DECKS = {
  employer: {
    label: "For employers",
    subtitle: "Ship faster with structured, hourly experts.",
    color: "#6B21A8",
    steps: [
      { img: "/demo/landing.jpg",
        head: "Land on Job Atlas",
        do:   "Click Start free — no credit card, no lock-in.",
        why:  "The whole platform is free to explore. You only pay when you actually purchase hours.",
        hotspot: { top: "78%", left: "12%", w: "170px", h: "56px" },
        narration: "Start on the Talent Hub home page. Everything is free to explore — no credit card required." },
      { img: "/demo/browse.jpg",
        head: "Shortlist vetted talent",
        do:   "Filter by skill, timezone or rate. Save the ones you like.",
        why:  "Contact details are hidden until a contract is signed, so nobody can go around the platform.",
        hotspot: { top: "31%", left: "10%", w: "80%", h: "12%" },
        narration: "Filter our vetted talent pool by skill, timezone and rate. Add the profiles you like to a shortlist." },
      { img: "/demo/pricing.jpg",
        head: "Buy a bundle of hours",
        do:   "Pick 10, 50, 100 or 500 hour packages. Pay by card, or bank / UPI.",
        why:  "One purchase gives you a hour balance to spread across as many talent as you need.",
        hotspot: { top: "44%", left: "35%", w: "30%", h: "45%" },
        narration: "Choose an hour package that fits. Pay by Stripe, or scan a UPI QR to transfer from your bank." },
      { img: "/demo/register.jpg",
        head: "Mix, match and sign",
        do:   "Assign hours to each talent, add scope, then sign the contract with a typed signature.",
        why:  "Both sides sign, with a 12-month exclusivity clause and clear on-site health & safety terms.",
        hotspot: { top: "20%", left: "35%", w: "30%", h: "60%" },
        narration: "Assign hours across your shortlist, agree on scope, and sign a structured contract. On site engagements automatically capture location and transport terms." },
      { img: "/demo/legal.jpg",
        head: "Track work in your tools",
        do:   "Connect Jira, Asana, Confluence, SAP — or upload an Excel plan.",
        why:  "Deliverables and hours-used flow into a single work log per engagement. Reviews are moderated.",
        hotspot: { top: "50%", left: "35%", w: "60%", h: "45%" },
        narration: "Every deliverable flows into your existing tools — Jira, Asana, Confluence, SAP. Reviews are moderated. Payouts run automatically." },
    ],
  },
  talent: {
    label: "For individuals",
    subtitle: "Get discovered. Get paid. Own your calendar.",
    color: "#6B21A8",
    steps: [
      { img: "/demo/register.jpg",
        head: "Create your profile in a minute",
        do:   "Pick the Talent option and add your basics.",
        why:  "You can start browsing gigs immediately — you don't need to complete your portfolio to see what's on offer.",
        hotspot: { top: "30%", left: "36%", w: "10%", h: "12%" },
        narration: "Choose the Talent option, add your basics, and you are on the marketplace within a minute." },
      { img: "/demo/browse.jpg",
        head: "Get AI-suggested hourly rates",
        do:   "Enter your skills and years of experience.",
        why:  "Claude Sonnet 5 suggests a fair, market-aligned rate range instantly — you can accept, adjust, or override it.",
        hotspot: { top: "40%", left: "20%", w: "20%", h: "8%" },
        narration: "Add your skills and years of experience. Our AI suggests a market fair hourly rate range in seconds." },
      { img: "/demo/pricing.jpg",
        head: "Keep more of what you earn",
        do:   "Just 8% commission — dropping to 4% at higher volumes.",
        why:  "Half of what Upwork or Fiverr take. You keep the rest.",
        hotspot: { top: "82%", left: "10%", w: "80%", h: "12%" },
        narration: "Commission starts at eight percent and drops to four percent as you clock more approved hours. Less than half of what Upwork and Fiverr charge." },
      { img: "/demo/landing.jpg",
        head: "Sign the contract, then work",
        do:   "Both parties sign with a typed signature.",
        why:  "You know exactly what's expected, when, and how you'll get paid. No scope creep, no chase-emails.",
        hotspot: { top: "78%", left: "12%", w: "170px", h: "56px" },
        narration: "Both sides sign a structured contract. You know exactly what is expected, when it is due, and how you will be paid." },
      { img: "/demo/legal.jpg",
        head: "Get paid on time, in your currency",
        do:   "Automated weekly payouts to Stripe, Payoneer, Wise or your bank.",
        why:  "No invoicing, no chasing. Just a clean statement each cycle.",
        hotspot: { top: "55%", left: "35%", w: "60%", h: "40%" },
        narration: "The platform runs automated weekly payouts to Stripe, Payoneer, Wise or your bank. No invoicing, no chasing." },
    ],
  },
};

export default function DemoTabs() {
  const [tab, setTab] = useState("employer");
  const [i, setI] = useState(0);
  const [narrate, setNarrate] = useState(false);

  const deck = DECKS[tab];
  const step = deck.steps[i];
  const total = deck.steps.length;

  const speak = (text) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95;
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find((v) => /en-(US|GB)/i.test(v.lang) && /Google|Neural|Samantha|Daniel/i.test(v.name))
                    || voices.find((v) => /en-/i.test(v.lang));
    if (preferred) u.voice = preferred;
    window.speechSynthesis.speak(u);
  };

  useEffect(() => {
    if (narrate) speak(step.narration);
    else window.speechSynthesis?.cancel();
    // eslint-disable-next-line
  }, [i, tab, narrate]);
  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  const changeTab = (id) => { setTab(id); setI(0); };
  const prev = () => setI((v) => Math.max(0, v - 1));
  const next = () => setI((v) => Math.min(total - 1, v + 1));

  return (
    <section id="how-it-works" className="bg-white border-t border-black/10">
      <div className="max-w-7xl mx-auto px-6 md:px-12 py-24">
        <div className="flex items-baseline justify-between flex-wrap gap-6 mb-4">
          <div>
            <p className="overline text-[#6B21A8] mb-3">HOW IT WORKS · STEP BY STEP</p>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight max-w-2xl">
              Five clicks. That&apos;s it.
            </h2>
            <p className="text-neutral-600 mt-3 max-w-2xl">{deck.subtitle}</p>
          </div>
          <div className="hard-border inline-flex bg-white">
            {Object.entries(DECKS).map(([id, v]) => (
              <button key={id} onClick={() => changeTab(id)} data-testid={`demo-tab-${id}`}
                      className={`px-5 py-3 font-display font-extrabold text-sm tracking-tight border-r border-black last:border-r-0 ${tab === id ? "bg-[#0A0A0A] text-white" : "bg-white text-black"}`}>
                {v.label}
              </button>
            ))}
          </div>
        </div>

        {/* Step numbers bar */}
        <ol className="grid grid-cols-5 hard-border bg-white mb-6">
          {deck.steps.map((s, x) => {
            const done = x < i;
            const active = x === i;
            return (
              <li key={x}>
                <button onClick={() => setI(x)}
                        className={`w-full border-r border-black last:border-r-0 p-4 text-left transition-colors ${active ? "bg-[#0A0A0A] text-white" : done ? "bg-[#F9F9F9]" : "bg-white hover:bg-neutral-50"}`}>
                  <div className="flex items-center gap-2">
                    <span className={`hard-border w-6 h-6 flex items-center justify-center text-xs font-display font-extrabold ${done ? "bg-[#6B21A8] text-white border-[#6B21A8]" : active ? "bg-[#6B21A8] text-white border-[#6B21A8]" : ""}`}>
                      {done ? <Check size={12} weight="bold"/> : x + 1}
                    </span>
                    <span className="text-[10px] uppercase tracking-widest font-mono opacity-70">Step {x + 1}</span>
                  </div>
                  <p className="mt-2 font-display font-extrabold text-sm tracking-tight leading-tight">{s.head}</p>
                </button>
              </li>
            );
          })}
        </ol>

        <div className="grid lg:grid-cols-[1.5fr_1fr] gap-6">
          {/* Screenshot with annotation */}
          <figure className="hard-border shadow-brutal bg-white relative aspect-video overflow-hidden">
            {deck.steps.map((s, x) => (
              <img key={x} src={s.img} alt={s.head}
                   className="absolute inset-0 w-full h-full object-cover transition-opacity duration-500"
                   style={{ opacity: i === x ? 1 : 0 }}/>
            ))}
            {/* Hotspot highlight for current step */}
            {step.hotspot && (
              <>
                <div className="absolute pointer-events-none" style={{
                  top: step.hotspot.top, left: step.hotspot.left,
                  width: step.hotspot.w, height: step.hotspot.h,
                  outline: `3px solid ${deck.color}`, boxShadow: `0 0 0 9999px rgba(0,0,0,0.35)`,
                  transition: "all 0.4s cubic-bezier(0.4,0,0.2,1)",
                }}/>
                <div className="absolute pointer-events-none animate-pulse" style={{
                  top: `calc(${step.hotspot.top} - 14px)`,
                  left: `calc(${step.hotspot.left} - 14px)`,
                  width: 28, height: 28, borderRadius: 999,
                  background: deck.color, opacity: 0.35,
                }}/>
              </>
            )}
            <figcaption className="absolute top-3 left-3 hard-border bg-white px-2 py-1 text-[10px] font-mono uppercase">
              Step {i + 1} of {total} · {deck.label}
            </figcaption>
          </figure>

          {/* Text card */}
          <div className="hard-border bg-[#F5F3FF] p-8 shadow-brutal flex flex-col">
            <p className="overline mb-3" style={{ color: deck.color }}>Step {i + 1}</p>
            <h3 className="font-display font-extrabold text-3xl tracking-tight mb-4">{step.head}</h3>
            <div className="hard-border bg-white p-4 mb-4">
              <p className="overline mb-2 text-[#6B21A8]">What you do</p>
              <p className="text-sm leading-relaxed">{step.do}</p>
            </div>
            <div className="hard-border bg-white p-4 mb-6">
              <p className="overline mb-2" style={{ color: "#6B21A8" }}>Why it matters</p>
              <p className="text-sm leading-relaxed">{step.why}</p>
            </div>

            <div className="mt-auto flex items-center justify-between gap-3">
              <div className="flex gap-2">
                <button onClick={prev} disabled={i === 0}
                        className="hard-border p-3 hover:bg-[#0A0A0A] hover:text-white disabled:opacity-30 disabled:hover:bg-white disabled:hover:text-black">
                  <CaretLeft size={16} weight="bold"/>
                </button>
                <button onClick={next} disabled={i === total - 1}
                        className="hard-border p-3 hover:bg-[#0A0A0A] hover:text-white disabled:opacity-30 disabled:hover:bg-white disabled:hover:text-black">
                  <CaretRight size={16} weight="bold"/>
                </button>
              </div>
              <button onClick={() => setNarrate((n) => !n)}
                      className="hard-border px-3 py-2 text-xs font-display font-extrabold inline-flex items-center gap-2 hover:bg-[#6B21A8] hover:text-white">
                {narrate ? <SpeakerHigh size={14} weight="fill"/> : <SpeakerX size={14} weight="fill"/>}
                {narrate ? "Narration on" : "Narrate this step"}
              </button>
              <p className="text-xs font-mono text-neutral-500">{i + 1} / {total}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
