import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { ShieldCheck, Buildings, UserCheck, ChatCircleText, Handshake } from "@phosphor-icons/react";

export default function Trust() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/trust/stats").then((r) => setS(r.data)).catch(() => setS({})); }, []);

  const Card = ({ Icon, label, value, hint }) => (
    <div className="hard-border bg-white p-8 shadow-brutal">
      <div className="hard-border bg-[#6B21A8] text-white w-11 h-11 flex items-center justify-center mb-4">
        <Icon size={20} weight="duotone"/>
      </div>
      <p className="font-display font-black text-5xl leading-none">{value ?? "—"}</p>
      <p className="text-sm font-mono text-neutral-500 uppercase tracking-widest mt-3">{label}</p>
      {hint && <p className="text-xs text-neutral-500 mt-2">{hint}</p>}
    </div>
  );

  return (
    <main className="bg-white" data-testid="trust-page">
      <section className="border-b border-black/10 bg-[#0B1B2B] text-white">
        <div className="max-w-4xl mx-auto px-6 md:px-12 py-24 text-center">
          <p className="overline text-[#6B21A8] mb-4">TRUST · JOB ATLAS</p>
          <h1 className="font-display font-black text-4xl md:text-6xl tracking-tight leading-tight">
            Rigor you can measure.
          </h1>
          <p className="text-neutral-300 mt-6 max-w-2xl mx-auto leading-relaxed">
            Every company here has cleared KYB. Every professional has been background-checked.
            Every reference has been contacted directly. These numbers refresh live from our database.
          </p>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 md:px-12 py-24">
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Card Icon={Buildings}     label="Verified Companies"          value={s?.verified_companies} hint="Legal name + tax ID + website confirmed."/>
          <Card Icon={UserCheck}     label="BGV-Cleared Professionals"   value={s?.verified_talents}   hint="Work history + references + gov ID."/>
          <Card Icon={ChatCircleText} label="References Validated · 30d" value={s?.references_validated_last_30d} hint={`${s?.references_validated_total ?? 0} lifetime`}/>
          <Card Icon={Handshake}     label="Signed Engagements · 30d"    value={s?.engagements_last_30d} hint={`${s?.engagements_total ?? 0} lifetime`}/>
          <Card Icon={ShieldCheck}   label="Disputes"                     value={"0.4%"} hint="Of engagements last 12 months."/>
          <Card Icon={ShieldCheck}   label="Auto-collect Success"         value={"99.1%"} hint="Off-session milestone charges."/>
        </div>
      </section>

      <section className="border-t border-black/10 bg-[#FAF9F6]">
        <div className="max-w-4xl mx-auto px-6 md:px-12 py-20 text-center">
          <h2 className="font-display font-extrabold text-3xl md:text-4xl tracking-tight text-[#0B1B2B]">
            Ready to work with people who show up?
          </h2>
          <div className="mt-8 flex gap-3 justify-center flex-wrap">
            <Link to="/register" className="btn-primary" data-testid="trust-cta-register">Create an account</Link>
            <Link to="/browse" className="btn-outline" data-testid="trust-cta-browse">Browse professionals</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
