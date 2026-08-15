import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Check, X } from "@phosphor-icons/react";

export default function Pricing() {
  const [p, setP] = useState(null);
  useEffect(() => { api.get("/pricing").then((r) => setP(r.data)); }, []);
  if (!p) return <div className="p-16 font-mono text-center">Loading…</div>;

  const tc = p.talent_commission;
  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#6B21A8] mb-3">PRICING</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">Cheaper than Upwork. Fairer than Fiverr.</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">
        Free while you evaluate. When you&apos;re ready, our employer platform fee is <strong>{p.platform_fee_pct}%</strong> —
        vs Upwork {p.compare.upwork}% · Fiverr {p.compare.fiverr}% · Freelancer {p.compare.freelancer}%.
        Individuals pay a volume-based commission on their hourly rate — see below.
      </p>

      {/* Employer plans */}
      <p className="overline text-neutral-500 mb-4">For Employers</p>
      <div className="grid md:grid-cols-3 gap-6 mb-16">
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

      {/* Talent commission */}
      <p className="overline text-neutral-500 mb-4">For Individuals — volume-tiered commission on your hourly rate</p>
      <div className="grid md:grid-cols-4 gap-4 mb-6">
        {tc.tiers.map((t, i) => (
          <div key={i} className={`hard-border p-6 shadow-brutal ${i === tc.tiers.length - 1 ? "bg-[#6B21A8] text-white" : "bg-white"}`}>
            <p className="overline mb-2">{t.label}</p>
            <p className="font-display font-extrabold text-5xl tracking-tight">{t.commission_pct}<span className="text-2xl">%</span></p>
            <p className="text-xs mt-2 opacity-70 font-mono">deducted at payout</p>
          </div>
        ))}
      </div>
      <div className="hard-border bg-[#F5F3FF] p-6 mb-16 shadow-brutal">
        <p className="text-sm leading-relaxed">
          <strong>Multi-employer monthly fee:</strong> {" "}
          <span className="font-mono">${tc.multi_employer_fee.amount_usd} / ₹{tc.multi_employer_fee.amount_inr} / month</span>
          {" "} — applied when you have active engagements with more than one employer in the same calendar month.
          Keeps side-door hiring closed while letting you work across companies.
        </p>
        <p className="text-sm text-neutral-600 mt-3">
          Comparison of talent take-rates: <strong>Job Atlas {tc.tiers[0].commission_pct}%–{tc.tiers[tc.tiers.length-1].commission_pct}%</strong> ·
          Upwork {tc.compare_talent.upwork}% · Fiverr up to {tc.compare_talent.fiverr}% · Toptal {tc.compare_talent.toptal}%.
        </p>
      </div>

      {/* Feature comparison */}
      <p className="overline text-neutral-500 mb-4">How we stack up</p>
      <div className="hard-border bg-white shadow-brutal overflow-x-auto mb-10">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>
              {["Feature", "Job Atlas", "Upwork", "Fiverr", "Freelancer"].map((h) => (
                <th key={h} className="text-left px-4 py-3 overline">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-black/10">
            {[
              ["Employer platform fee",   `${p.platform_fee_pct}%`, `${p.compare.upwork}%`,   `${p.compare.fiverr}%`, `${p.compare.freelancer}%`],
              ["Talent commission (min)", `${tc.tiers[tc.tiers.length-1].commission_pct}%`,   `${tc.compare_talent.upwork}%`, `${tc.compare_talent.fiverr}%`, "—"],
              ["12-month exclusivity",    "✓",                       "✗",                     "✗",                    "✗"],
              ["Signed contracts (both)", "✓",                       "partial",               "✗",                    "partial"],
              ["Enterprise tool sync",    "Jira, SAP, ServiceNow, +",  "limited",              "✗",                    "✗"],
              ["INR bank transfer",       "✓ (India)",               "✗",                     "✗",                    "✗"],
              ["Deliverables & reviews",  "✓ (moderated)",           "✓",                     "✓",                    "✓"],
            ].map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className={`px-4 py-3 ${j === 1 ? "font-mono font-bold text-[#6B21A8]" : "font-mono"}`}>
                    {cell === "✓" ? <Check size={16} weight="bold" className="inline"/> :
                     cell === "✗" ? <X size={16} weight="bold" className="inline text-neutral-400"/> :
                     cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-neutral-500 mt-4 font-mono">
        {p.brand.product} · operated by {p.brand.operator} · {p.brand.city} · GSTIN {p.brand.gstin}
      </p>
    </main>
  );
}
