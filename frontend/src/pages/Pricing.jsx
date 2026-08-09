import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Check } from "@phosphor-icons/react";

export default function Pricing() {
  const [p, setP] = useState(null);
  useEffect(() => { api.get("/pricing").then((r) => setP(r.data)); }, []);
  if (!p) return <div className="p-16 font-mono text-center">Loading…</div>;
  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">PRICING</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">Cheaper than Upwork. Fairer than Fiverr.</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">
        Free while you evaluate. When you&apos;re ready, our platform fee is <strong>{p.platform_fee_pct}%</strong> —
        vs Upwork {p.compare.upwork}% · Fiverr {p.compare.fiverr}% · Freelancer {p.compare.freelancer}%.
      </p>

      <div className="grid md:grid-cols-3 gap-6">
        {p.plans.map((pl, i) => (
          <div key={pl.id} className={`hard-border p-8 shadow-brutal ${i === 1 ? "bg-[#0A0A0A] text-white md:-translate-y-3" : "bg-white"}`}>
            <p className="overline mb-3">{pl.name}</p>
            <div className="flex items-baseline gap-2 mb-6">
              <p className="font-display font-extrabold text-5xl tracking-tight">${pl.price}</p>
              <p className="text-xs opacity-70">{pl.period}</p>
            </div>
            <ul className="space-y-3 mb-8">
              {pl.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm">
                  <Check size={16} weight="bold" className="mt-0.5"/>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <Link to="/register" className={i === 1 ? "btn-accent w-full block text-center" : "btn-primary w-full block text-center"}>
              {pl.price === 0 ? "Start free →" : "Choose " + pl.name}
            </Link>
          </div>
        ))}
      </div>

      <p className="text-xs text-neutral-500 mt-10 font-mono">
        Platform fee applied at checkout when purchasing hour packages. All payments cleared through Stripe.
      </p>
    </main>
  );
}
