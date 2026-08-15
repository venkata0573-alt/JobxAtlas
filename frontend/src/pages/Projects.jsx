import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Briefcase, ArrowRight, X, Users, Clock, Certificate } from "@phosphor-icons/react";

export default function Projects() {
  const [templates, setTemplates] = useState([]);
  const [phases, setPhases] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [industryFilter, setIndustryFilter] = useState("");
  const [form, setForm] = useState({ company_name: "", contact_name: "", contact_email: "", duration_months: 6, notes: "" });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get("/projects/templates").then((r) => { setTemplates(r.data.templates); setPhases(r.data.phases); })
       .catch((e) => toast.error(formatErr(e)));
  }, []);

  const openTemplate = async (id) => {
    setSelected(id); setDetail(null);
    try {
      const r = await api.get(`/projects/templates/${id}`);
      setDetail(r.data);
      setForm((f) => ({ ...f, duration_months: r.data.duration_months }));
    } catch (e) { toast.error(formatErr(e)); }
  };

  const submitLead = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await api.post("/projects/lead", { template_id: selected, ...form });
      toast.success(r.data.message);
      setSelected(null);
      setForm({ company_name: "", contact_name: "", contact_email: "", duration_months: 6, notes: "" });
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSubmitting(false); }
  };

  const industries = Array.from(new Set(templates.map((t) => t.industry)));
  const filtered = industryFilter ? templates.filter((t) => t.industry === industryFilter) : templates;

  return (
    <main className="bg-white">
      {/* Hero */}
      <section className="border-b border-black/10 bg-[#0B1B2B] text-white">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-24">
          <p className="overline text-[#C79A3B] mb-4">PROJECT DELIVERY · PMI-STRUCTURED</p>
          <h1 className="font-display font-black text-4xl md:text-6xl tracking-tight leading-[1.05]">
            Two ways to work with Job Atlas.<br/>
            <span className="text-[#F0C260]">Pick your model. Ship on time.</span>
          </h1>
          <div className="grid md:grid-cols-2 gap-6 mt-12 max-w-4xl">
            <div className="hard-border border-white/20 bg-white/[0.03] p-6">
              <p className="overline text-neutral-400 mb-2">MODEL 1</p>
              <h3 className="font-display font-extrabold text-2xl tracking-tight">Hire by the hour</h3>
              <p className="text-sm text-neutral-300 mt-2 leading-relaxed">Single vetted expert. Book hours in bulk, integrate into your existing team. Best for sprint capacity, specialist skills, and short bursts of work.</p>
              <Link to="/browse" className="mt-6 inline-flex items-center gap-2 text-[#C79A3B] hover:text-[#F0C260] text-sm font-mono">Browse talent <ArrowRight size={14}/></Link>
            </div>
            <div className="hard-border border-[#C79A3B]/60 bg-[#C79A3B]/10 p-6">
              <p className="overline text-[#C79A3B] mb-2">MODEL 2 — THIS PAGE</p>
              <h3 className="font-display font-extrabold text-2xl tracking-tight">Deliver a project</h3>
              <p className="text-sm text-neutral-200 mt-2 leading-relaxed">Multi-month engagement with a pre-loaded team blueprint by industry. PMI process groups, milestone gates, weekly variance reports. Best for scoped outcomes over 3–12 months.</p>
              <a href="#templates" className="mt-6 inline-flex items-center gap-2 text-[#F0C260] hover:text-white text-sm font-mono">See templates <ArrowRight size={14}/></a>
            </div>
          </div>
        </div>
      </section>

      {/* PMI phases */}
      <section className="bg-[#FAF9F6] border-b border-black/10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-16">
          <p className="overline text-[#C79A3B] mb-3">HOW WE DELIVER · PMI PROCESS GROUPS</p>
          <h2 className="font-display font-extrabold text-3xl md:text-4xl tracking-tight max-w-2xl mb-10">
            Every project moves through five gated phases.
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {phases.map((p, idx) => (
              <div key={p.id} className="hard-border bg-white p-5 shadow-brutal" data-testid={`phase-${p.id}`}>
                <p className="font-mono text-xs text-[#C79A3B] tracking-widest">PHASE {idx + 1}</p>
                <h3 className="font-display font-extrabold text-xl tracking-tight mt-1">{p.name}</h3>
                <p className="text-xs text-neutral-500 mt-3 font-mono uppercase tracking-widest">Gate</p>
                <p className="text-sm text-[#0B1B2B] mt-1">{p.gate}</p>
                <p className="text-xs text-neutral-500 mt-4 font-mono uppercase tracking-widest">Deliverables</p>
                <ul className="text-xs text-neutral-700 mt-1 space-y-1">
                  {p.deliverables.map((d, i) => <li key={i}>· {d}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Templates gallery */}
      <section id="templates" className="border-b border-black/10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-20">
          <p className="overline text-[#C79A3B] mb-3">TEMPLATES · PRE-LOADED TEAMS BY INDUSTRY</p>
          <h2 className="font-display font-extrabold text-3xl md:text-4xl tracking-tight max-w-2xl mb-6">
            Pick a proven blueprint, swap seats, and ship.
          </h2>
          <div className="flex gap-2 flex-wrap mb-8">
            <button onClick={() => setIndustryFilter("")}
                    className={`hard-border px-3 py-2 text-xs ${!industryFilter ? "bg-[#0B1B2B] text-white" : "bg-white"}`}
                    data-testid="filter-all">All</button>
            {industries.map((i) => (
              <button key={i} onClick={() => setIndustryFilter(i)}
                      className={`hard-border px-3 py-2 text-xs ${industryFilter === i ? "bg-[#0B1B2B] text-white" : "bg-white"}`}
                      data-testid={`filter-${i.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}>{i}</button>
            ))}
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map((t) => (
              <button key={t.id} onClick={() => openTemplate(t.id)}
                      className="text-left hard-border bg-white p-6 shadow-brutal-hover group"
                      data-testid={`project-template-${t.id}`}>
                <p className="overline text-[#C79A3B]">{t.industry}</p>
                <h3 className="font-display font-black text-xl tracking-tight mt-1 group-hover:text-[#6B21A8] transition-colors">{t.title}</h3>
                <p className="text-sm text-neutral-600 mt-2 leading-relaxed line-clamp-3">{t.summary}</p>
                <div className="flex items-center justify-between mt-5 pt-4 border-t border-black/10 text-xs font-mono text-neutral-500">
                  <span className="inline-flex items-center gap-1"><Clock size={12} weight="fill" color="#C79A3B"/> {t.duration_months} months</span>
                  <span className="inline-flex items-center gap-1"><Users size={12} weight="fill" color="#C79A3B"/> {t.team.reduce((n, s) => n + s.count, 0)} seats</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Template detail modal */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setSelected(null)}
             data-testid="template-detail-modal">
          <div className="hard-border bg-white max-w-2xl w-full max-h-[90vh] overflow-y-auto p-8 shadow-brutal-lg" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => setSelected(null)} className="absolute top-6 right-6 text-neutral-400 hover:text-neutral-700" data-testid="close-template-modal"><X size={20}/></button>
            {!detail ? (
              <p className="text-neutral-500 font-mono text-sm">Loading blueprint…</p>
            ) : (
              <>
                <p className="overline text-[#C79A3B]">{detail.industry}</p>
                <h3 className="font-display font-black text-3xl tracking-tight mt-1">{detail.title}</h3>
                <p className="text-neutral-600 mt-2 leading-relaxed">{detail.summary}</p>

                <div className="grid grid-cols-3 gap-3 my-6">
                  <div className="hard-border bg-[#FAF9F6] p-3 text-center">
                    <p className="font-display font-black text-xl">{detail.duration_months}</p>
                    <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest mt-1">Months</p>
                  </div>
                  <div className="hard-border bg-[#FAF9F6] p-3 text-center">
                    <p className="font-display font-black text-xl">{detail.monthly_headcount}</p>
                    <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest mt-1">Seats</p>
                  </div>
                  <div className="hard-border bg-[#FAF9F6] p-3 text-center">
                    <p className="font-display font-black text-xl">${(detail.estimated_monthly_cost / 1000).toFixed(0)}k</p>
                    <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest mt-1">Est / month</p>
                  </div>
                </div>

                <p className="overline text-neutral-500 mb-2">Team blueprint</p>
                <div className="space-y-2 mb-6">
                  {detail.team.map((s, i) => (
                    <div key={i} className="hard-border bg-white p-3 flex items-center justify-between text-sm">
                      <span className="font-display font-bold">{s.count}× {s.role}</span>
                      <span className="font-mono text-xs text-neutral-500">${s.rate_range[0]}–${s.rate_range[1]}/hr</span>
                    </div>
                  ))}
                </div>

                <form onSubmit={submitLead} className="hard-border bg-[#FAF9F6] p-5 space-y-3" data-testid="project-lead-form">
                  <p className="font-display font-extrabold text-lg">Request scoping — no commitment</p>
                  <div className="grid grid-cols-2 gap-3">
                    <input required placeholder="Company name" value={form.company_name} onChange={(e) => setForm({...form, company_name: e.target.value})} className="hard-border px-3 py-2 bg-white text-sm" data-testid="lead-company"/>
                    <input required placeholder="Your name" value={form.contact_name} onChange={(e) => setForm({...form, contact_name: e.target.value})} className="hard-border px-3 py-2 bg-white text-sm" data-testid="lead-name"/>
                  </div>
                  <input required type="email" placeholder="Work email" value={form.contact_email} onChange={(e) => setForm({...form, contact_email: e.target.value})} className="hard-border px-3 py-2 bg-white text-sm w-full" data-testid="lead-email"/>
                  <div className="flex items-center gap-3">
                    <label className="text-xs font-mono">Duration:</label>
                    <select value={form.duration_months} onChange={(e) => setForm({...form, duration_months: Number(e.target.value)})} className="hard-border px-2 py-1 bg-white text-sm" data-testid="lead-duration">
                      {[3, 6, 9, 12].map((n) => <option key={n} value={n}>{n} months</option>)}
                    </select>
                  </div>
                  <textarea rows={3} placeholder="Anything specific we should know? (optional)" value={form.notes} onChange={(e) => setForm({...form, notes: e.target.value})} className="hard-border px-3 py-2 bg-white text-sm w-full" data-testid="lead-notes"/>
                  <button type="submit" disabled={submitting} className="btn-primary w-full inline-flex items-center justify-center gap-2" data-testid="submit-project-lead">
                    <Certificate size={14} weight="fill"/>
                    {submitting ? "Sending…" : "Request scoping →"}
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
