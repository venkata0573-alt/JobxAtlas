import React, { useEffect, useRef, useState } from "react";
import { Play, Pause, ArrowsClockwise } from "@phosphor-icons/react";

const DEMOS = {
  employer: {
    label: "For Employers",
    title: "From payment to signed contract in 90 seconds",
    poster: "https://images.unsplash.com/photo-1758518729685-f88df7890776?crop=entropy&cs=srgb&fm=jpg&w=1280",
    video: "https://videos.pexels.com/video-files/3196284/3196284-uhd_2560_1440_25fps.mp4",
    scenes: [
      { t: 0,  head: "1 · Browse vetted talent",       body: "Filter by skill, timezone and hourly rate. Contact stays hidden until a contract is signed — no side-doors." },
      { t: 12, head: "2 · Buy a package of hours",     body: "Choose 10 / 50 / 100 / 500-hour bundles. Pay via Stripe globally or bank / UPI transfer to our India account." },
      { t: 24, head: "3 · Mix & match your team",      body: "Drag hours across multiple talent. Add scope, dates, work-mode (remote / on-site / hybrid) and transport terms." },
      { t: 36, head: "4 · Sign the contract",          body: "Typed e-signature by both parties. Health & safety, 12-month exclusivity and illegal-conduct clauses baked in." },
      { t: 48, head: "5 · Track deliverables & hours", body: "Talent submits work, you approve. Hours-used auto-increments. Reviews are moderated by TalentHub before appearing." },
    ],
  },
  talent: {
    label: "For Individuals",
    title: "Get discovered, get paid, keep your calendar",
    poster: "https://images.pexels.com/photos/16029823/pexels-photo-16029823.jpeg?auto=compress&cs=tinysrgb&w=1280",
    video: "https://videos.pexels.com/video-files/5453622/5453622-uhd_2560_1440_25fps.mp4",
    scenes: [
      { t: 0,  head: "1 · Build your profile",         body: "Add skills, portfolio, years of experience. Claude Sonnet 5 suggests a market-fair hourly rate range in seconds." },
      { t: 12, head: "2 · Set weekly availability",    body: "Pick your slots in your timezone. Employers see them re-projected into theirs — no scheduling ping-pong." },
      { t: 24, head: "3 · Raise an EOI",               body: "Send an Expression of Interest to any employer, or leave it open. Multi-employer welcome — bandwidth permitting." },
      { t: 36, head: "4 · Sign & work",                body: "Contract signed both ways. On-site engagements disclose location, dates, transport and safety terms upfront." },
      { t: 48, head: "5 · Submit deliverables",        body: "Log work, get approvals, watch reviews come in. Payouts through Stripe, Payoneer, Wise or Indian bank." },
    ],
  },
};

export default function DemoTabs() {
  const [tab, setTab] = useState("employer");
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);
  const vidRef = useRef(null);
  const d = DEMOS[tab];

  useEffect(() => {
    setT(0);
    if (vidRef.current) { try { vidRef.current.currentTime = 0; vidRef.current.play(); } catch {} }
  }, [tab]);

  useEffect(() => {
    if (!playing) return;
    const iv = setInterval(() => setT((x) => (x + 1) % 60), 1000);
    return () => clearInterval(iv);
  }, [playing]);

  const currentScene = [...d.scenes].reverse().find((s) => t >= s.t) || d.scenes[0];

  const togglePlay = () => {
    setPlaying((p) => {
      const next = !p;
      if (vidRef.current) { next ? vidRef.current.play() : vidRef.current.pause(); }
      return next;
    });
  };
  const restart = () => {
    setT(0);
    if (vidRef.current) { vidRef.current.currentTime = 0; vidRef.current.play(); }
    setPlaying(true);
  };

  return (
    <section className="bg-white border-t border-black/10">
      <div className="max-w-7xl mx-auto px-6 md:px-12 py-24">
        <div className="flex items-baseline justify-between flex-wrap gap-6 mb-10">
          <div>
            <p className="overline text-[#002FA7] mb-3">SEE IT IN ACTION</p>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight max-w-2xl">
              90 seconds. Two perspectives. One platform.
            </h2>
          </div>
          <div className="hard-border inline-flex bg-white">
            {Object.entries(DEMOS).map(([id, v]) => (
              <button key={id} onClick={() => setTab(id)} data-testid={`demo-tab-${id}`}
                      className={`px-5 py-3 font-display font-extrabold text-sm tracking-tight border-r border-black last:border-r-0 ${tab === id ? "bg-[#0A0A0A] text-white" : "bg-white text-black"}`}>
                {v.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid lg:grid-cols-[1.5fr_1fr] gap-6">
          {/* Video with animated caption overlay */}
          <div className="hard-border shadow-brutal bg-black relative aspect-video overflow-hidden">
            <video
              key={tab}
              ref={vidRef}
              className="w-full h-full object-cover"
              poster={d.poster}
              autoPlay muted loop playsInline preload="metadata"
              data-testid={`demo-video-${tab}`}
            >
              <source src={d.video} type="video/mp4" />
            </video>

            {/* Dark gradient bottom */}
            <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-black via-black/70 to-transparent pointer-events-none"/>

            {/* Top-left badge */}
            <div className="absolute top-3 left-3 hard-border bg-white px-2 py-1 text-[10px] font-mono uppercase">
              <span className="inline-flex items-center gap-1"><Play size={10} weight="fill"/> Demo · {d.label}</span>
            </div>

            {/* Animated caption */}
            <div key={`${tab}-${currentScene.t}`} className="absolute inset-x-0 bottom-0 p-6 md:p-8 text-white">
              <p className="overline text-[#FF0A0A] mb-2 animate-in">{currentScene.head}</p>
              <p className="font-display font-extrabold text-2xl md:text-3xl tracking-tight leading-tight max-w-2xl">{currentScene.body}</p>
            </div>

            {/* Controls */}
            <div className="absolute top-3 right-3 flex gap-2">
              <button onClick={togglePlay} className="hard-border bg-white p-2 hover:bg-[#002FA7] hover:text-white">
                {playing ? <Pause size={14} weight="fill"/> : <Play size={14} weight="fill"/>}
              </button>
              <button onClick={restart} className="hard-border bg-white p-2 hover:bg-[#002FA7] hover:text-white">
                <ArrowsClockwise size={14}/>
              </button>
            </div>

            {/* Timeline dots */}
            <div className="absolute bottom-3 right-3 flex gap-1">
              {d.scenes.map((s) => (
                <button key={s.t} onClick={() => setT(s.t)} title={s.head}
                        className={`w-2 h-2 hard-border ${currentScene.t === s.t ? "bg-[#FF0A0A]" : "bg-white"}`}/>
              ))}
            </div>
          </div>

          {/* Chapter list */}
          <aside className="hard-border bg-[#FDFCF0] p-8 shadow-brutal flex flex-col">
            <p className="overline text-[#002FA7] mb-3">Walk-through</p>
            <h3 className="font-display font-extrabold text-2xl md:text-3xl tracking-tight mb-6">{d.title}</h3>
            <ol className="space-y-3 flex-1">
              {d.scenes.map((s, i) => {
                const active = currentScene.t === s.t;
                return (
                  <li key={i}>
                    <button onClick={() => setT(s.t)}
                            className={`w-full flex gap-3 text-left p-3 hard-border transition-colors ${active ? "bg-[#0A0A0A] text-white" : "bg-white hover:bg-neutral-50"}`}>
                      <span className={`w-7 h-7 flex items-center justify-center font-display font-extrabold flex-shrink-0 hard-border ${active ? "bg-[#FF0A0A] text-white border-[#FF0A0A]" : "bg-[#002FA7] text-white border-[#002FA7]"}`}>
                        {i + 1}
                      </span>
                      <span className="min-w-0">
                        <p className="font-display font-extrabold text-sm tracking-tight">{s.head.replace(/^\d+\s·\s/, "")}</p>
                        <p className={`text-xs mt-1 leading-relaxed ${active ? "text-neutral-300" : "text-neutral-600"}`}>{s.body}</p>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
            <p className="text-xs text-neutral-500 mt-4 font-mono">Auto-advance · click any step to jump</p>
          </aside>
        </div>
      </div>
    </section>
  );
}
