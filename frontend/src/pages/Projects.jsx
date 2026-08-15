import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { ArrowRight, X, Users, Clock, Certificate, ArrowsClockwise, LockSimple, LockSimpleOpen, Sparkle } from "@phosphor-icons/react";

export default function Projects() {
  const { user } = useAuth();
  const [templates, setTemplates] = useState([]);
  const [phases, setPhases] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [seats, setSeats] = useState([]);        // [{role, seat_index, rate_range, suggested_talent, locked, current}]
  const [reshuffling, setReshuffling] = useState(false);
  const [industryFilter, setIndustryFilter] = useState("");
  const [form, setForm] = useState({ company_name: "", contact_name: "", contact_email: "", duration_months: 6, notes: "" });
  const [submitting, setSubmitting] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [customForm, setCustomForm] = useState({
    company_name: "", contact_name: "", contact_email: "",
    custom_title: "", custom_industry: "", custom_summary: "",
    duration_months: 6, notes: "",
    seats: [{ role: "", rate: 100 }],
  });

  useEffect(() => {
    api.get("/projects/templates").then((r) => { setTemplates(r.data.templates); setPhases(r.data.phases); })
       .catch((e) => toast.error(formatErr(e)));
  }, []);

  const openTemplate = async (id) => {
    setSelected(id); setDetail(null); setSeats([]);
    try {
      const [dRes, tRes] = await Promise.all([
        api.get(`/projects/templates/${id}`),
        api.get(`/projects/templates/${id}/team-suggestions`),
      ]);
      setDetail(dRes.data);
      setForm((f) => ({ ...f, duration_months: dRes.data.duration_months }));
      setSeats((tRes.data.seats || []).map((s) => ({ ...s, current: s.suggested_talent, locked: false })));
    } catch (e) { toast.error(formatErr(e)); }
  };

  const reshuffle = async () => {
    if (!selected) return;
    setReshuffling(true);
    try {
      const r = await api.get(`/projects/templates/${selected}/team-suggestions`);
      const fresh = r.data.seats || [];
      // Keep locked seats; replace unlocked ones with fresh suggestions (avoid re-picking locked names)
      const lockedIds = new Set(seats.filter((s) => s.locked && s.current).map((s) => s.current.id));
      setSeats(seats.map((s, i) => {
        if (s.locked) return s;
        // Take the fresh suggestion at same index if not already locked elsewhere
        const alt = fresh[i]?.suggested_talent;
        if (alt && !lockedIds.has(alt.id)) return { ...s, current: alt };
        // Fallback: find any fresh talent not yet locked
        const spare = fresh.find((f) => f.suggested_talent && !lockedIds.has(f.suggested_talent.id));
        return { ...s, current: spare?.suggested_talent || s.current };
      }));
    } catch (e) { toast.error(formatErr(e)); }
    finally { setReshuffling(false); }
  };

  const toggleLock = (idx) => {
    setSeats(seats.map((s, i) => i === idx ? { ...s, locked: !s.locked } : s));
  };

  // Compute cost from actual assigned seats (uses talent.rate when set, else the mid of the range).
  // Employer-facing price uses sell_rate (backend-supplied) — Job Atlas margin already baked in.
  // We also expose the raw talent cost so admins/employers see the transparent breakdown.
  const costs = useMemo(() => {
    if (!detail || !seats.length) return {
      monthly: detail?.monthly_client_price || detail?.estimated_monthly_cost || 0,
      total: detail?.total_client_price || detail?.estimated_total_cost || 0,
      talent_monthly: detail?.monthly_talent_cost || 0,
      talent_total: detail?.total_talent_cost || 0,
      margin_pct: detail?.blended_margin_pct || 0,
    };
    const monthlyHrs = 160;
    let monthlyClient = 0;
    let monthlyTalent = 0;
    for (const s of seats) {
      const talentRate = s.current?.rate || ((s.rate_range?.[0] + s.rate_range?.[1]) / 2);
      const sellRate = s.current?.sell_rate || (talentRate * 1.15);  // fallback if backend didn't set
      monthlyClient += sellRate * monthlyHrs;
      monthlyTalent += talentRate * monthlyHrs;
    }
    const months = detail?.duration_months || 1;
    const margin = monthlyClient - monthlyTalent;
    const marginPct = monthlyTalent > 0 ? (margin / monthlyTalent) * 100 : 0;
    return {
      monthly: Math.round(monthlyClient),
      total: Math.round(monthlyClient * months),
      talent_monthly: Math.round(monthlyTalent),
      talent_total: Math.round(monthlyTalent * months),
      margin_pct: Math.round(marginPct * 10) / 10,
    };
  }, [seats, detail]);

  const submitLead = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const assigned_team = seats.map((s) => ({
        role: s.role,
        seat_index: s.seat_index,
        talent_id: s.current?.id || null,
        talent_name: s.current?.name || null,
        rate: s.current?.rate || null,
        locked: !!s.locked,
      }));
      const r = await api.post("/projects/lead", {
        template_id: selected, ...form,
        assigned_team,
      });
      toast.success(r.data.message);
      setSelected(null); setSeats([]);
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
            {/* Custom project tile */}
            <button onClick={() => setShowCustom(true)}
                    className="text-left hard-border bg-[#0B1B2B] text-white p-6 shadow-brutal-hover group"
                    data-testid="project-template-custom">
              <p className="overline text-[#C79A3B]">BUILD YOUR OWN</p>
              <h3 className="font-display font-black text-xl tracking-tight mt-1 group-hover:text-[#F0C260] transition-colors">Custom project</h3>
              <p className="text-sm text-neutral-300 mt-2 leading-relaxed">
                Blueprint doesn&apos;t fit? Assemble your own team seat-by-seat, name your industry, set your duration. Same PMI phases, same 25%-milestone billing, same margin.
              </p>
              <div className="flex items-center justify-between mt-5 pt-4 border-t border-white/20 text-xs font-mono text-[#C79A3B]">
                <span>Any industry</span>
                <span>Any team →</span>
              </div>
            </button>
          </div>
        </div>
      </section>

      {/* Template detail modal */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setSelected(null)}
             data-testid="template-detail-modal">
          <div className="hard-border bg-white max-w-3xl w-full max-h-[92vh] overflow-y-auto p-8 shadow-brutal-lg relative" onClick={(e) => e.stopPropagation()}>
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
                    <p className="font-display font-black text-xl">{seats.length || detail.monthly_headcount}</p>
                    <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest mt-1">Seats</p>
                  </div>
                  <div className="hard-border bg-[#0B1B2B] text-white p-3 text-center" data-testid="live-monthly-cost">
                    {user ? (
                      <>
                        <p className="font-display font-black text-xl">${(costs.monthly / 1000).toFixed(1)}k</p>
                        <p className="text-[10px] font-mono text-[#F0C260] uppercase tracking-widest mt-1">You pay / mo</p>
                      </>
                    ) : (
                      <>
                        <p className="font-display font-black text-lg">Custom quote</p>
                        <p className="text-[10px] font-mono text-[#F0C260] uppercase tracking-widest mt-1">Sign in to reveal</p>
                      </>
                    )}
                  </div>
                </div>

                {user ? (
                  <div className="hard-border bg-[#F5EEF9] px-3 py-2 mb-4 text-xs font-mono flex items-center justify-between gap-2 flex-wrap" data-testid="price-transparency">
                    <span>Team cost <span className="font-bold">${(costs.talent_monthly / 1000).toFixed(1)}k/mo</span></span>
                    <span>·</span>
                    <span>Job Atlas margin <span className="font-bold">{costs.margin_pct}%</span></span>
                    <span>·</span>
                    <span>Total {detail.duration_months}mo: <span className="font-bold">${(costs.total / 1000).toFixed(0)}k</span></span>
                  </div>
                ) : (
                  <div className="hard-border bg-[#F5EEF9] px-3 py-3 mb-4 text-xs flex items-center justify-between gap-2 flex-wrap" data-testid="pricing-signin-nudge">
                    <span className="font-mono">
                      <b>{seats.length} seats · {detail.duration_months} months</b> — full quote unlocks after sign-in. No card, no obligation.
                    </span>
                    <Link to="/register" className="btn-primary text-xs">Sign in to see quote →</Link>
                  </div>
                )}

                <div className="flex items-center justify-between mb-3">
                  <p className="overline text-neutral-500">Assemble the team · auto-matched from our vetted bench</p>
                  <button onClick={reshuffle} disabled={reshuffling}
                          className="hard-border text-xs px-3 py-2 bg-white hover:bg-[#FAF9F6] inline-flex items-center gap-1"
                          data-testid="reshuffle-team-btn">
                    <ArrowsClockwise size={12} weight="bold" className={reshuffling ? "animate-spin" : ""}/>
                    Reshuffle unlocked
                  </button>
                </div>

                <div className="space-y-2 mb-6" data-testid="assemble-team-list">
                  {seats.map((s, idx) => {
                    const t = s.current;
                    return (
                      <div key={idx}
                           className={`hard-border p-3 flex items-center gap-3 ${s.locked ? "bg-[#FDF6E3] border-[#C79A3B]" : "bg-white"}`}
                           data-testid={`seat-${idx}`}>
                        <div className="hard-border bg-[#0B1B2B] text-[#C79A3B] w-9 h-9 flex items-center justify-center shrink-0 text-xs font-mono">
                          #{idx + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-display font-extrabold text-sm truncate">{s.role}</p>
                          {t ? (
                            <p className="text-xs text-neutral-600 truncate">
                              <span className="font-mono">{t.name}</span> · {t.headline} · <span className="font-mono">${t.sell_rate || t.rate}/hr</span> · {t.years}y
                            </p>
                          ) : (
                            <p className="text-xs text-neutral-400">No match in bench — Job Atlas team will source</p>
                          )}
                        </div>
                        <button onClick={() => toggleLock(idx)}
                                className={`hard-border p-2 shrink-0 ${s.locked ? "bg-[#C79A3B] text-white" : "bg-white text-[#0B1B2B]"}`}
                                title={s.locked ? "Locked · click to unlock" : "Lock this seat"}
                                data-testid={`toggle-lock-${idx}`}>
                          {s.locked ? <LockSimple size={14} weight="fill"/> : <LockSimpleOpen size={14}/>}
                        </button>
                      </div>
                    );
                  })}
                </div>

                <form onSubmit={submitLead} className="hard-border bg-[#FAF9F6] p-5 space-y-3" data-testid="project-lead-form">
                  <p className="font-display font-extrabold text-lg inline-flex items-center gap-2">
                    <Sparkle size={16} weight="fill" color="#C79A3B"/> Request scoping — no commitment
                  </p>
                  <p className="text-xs text-neutral-600 -mt-1">
                    We&apos;ll send your assembled team ({seats.filter((s) => s.locked).length} locked, {seats.length - seats.filter((s) => s.locked).length} flexible)
                    and estimate <span className="font-mono font-bold">${(costs.total / 1000).toFixed(0)}k</span> over {detail.duration_months} months.
                  </p>
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
                    {submitting ? "Sending…" : `Request scoping — $${(costs.monthly / 1000).toFixed(1)}k/mo →`}
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      )}
      {/* Custom project modal */}
      {showCustom && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
             onClick={() => setShowCustom(false)} data-testid="custom-project-modal">
          <form onClick={(e) => e.stopPropagation()}
                onSubmit={async (e) => {
                  e.preventDefault();
                  const seats = customForm.seats
                    .filter((s) => s.role && Number(s.rate) > 0)
                    .map((s, i) => ({ role: s.role, seat_index: i + 1, rate: Number(s.rate) }));
                  if (!seats.length) { toast.error("Add at least one seat with role + rate"); return; }
                  try {
                    const r = await api.post("/projects/lead", {
                      template_id: "custom",
                      company_name: customForm.company_name,
                      contact_name: customForm.contact_name,
                      contact_email: customForm.contact_email,
                      duration_months: Number(customForm.duration_months),
                      notes: customForm.notes,
                      assigned_team: seats,
                      custom_title: customForm.custom_title,
                      custom_industry: customForm.custom_industry,
                      custom_summary: customForm.custom_summary,
                    });
                    toast.success(r.data.message);
                    setShowCustom(false);
                  } catch (err) { toast.error(formatErr(err)); }
                }}
                className="hard-border bg-white max-w-3xl w-full max-h-[92vh] overflow-y-auto p-8 shadow-brutal-lg relative space-y-4">
            <button type="button" onClick={() => setShowCustom(false)}
                    className="absolute top-6 right-6 text-neutral-400 hover:text-neutral-700" data-testid="close-custom-modal">
              <X size={20}/>
            </button>
            <p className="overline text-[#C79A3B]">CUSTOM PROJECT</p>
            <h3 className="font-display font-black text-3xl tracking-tight">Build your own blueprint</h3>
            <div className="grid md:grid-cols-2 gap-3">
              <input required placeholder="Project title" value={customForm.custom_title} onChange={(e) => setCustomForm({...customForm, custom_title: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="cp-title"/>
              <input required placeholder="Industry (any)" value={customForm.custom_industry} onChange={(e) => setCustomForm({...customForm, custom_industry: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="cp-industry"/>
            </div>
            <textarea rows={2} placeholder="One-line summary" value={customForm.custom_summary} onChange={(e) => setCustomForm({...customForm, custom_summary: e.target.value})} className="hard-border px-3 py-2 text-sm w-full" data-testid="cp-summary"/>
            <div>
              <p className="overline mb-2">Your team</p>
              <div className="space-y-2">
                {customForm.seats.map((s, i) => (
                  <div key={i} className="grid grid-cols-[1fr_120px_40px] gap-2" data-testid={`cp-seat-${i}`}>
                    <input required placeholder="Role (e.g. Senior BE Engineer)" value={s.role}
                           onChange={(e) => { const c=[...customForm.seats]; c[i].role=e.target.value; setCustomForm({...customForm, seats: c});}}
                           className="hard-border px-3 py-2 text-sm"/>
                    <input required type="number" placeholder="Rate/hr $" value={s.rate}
                           onChange={(e) => { const c=[...customForm.seats]; c[i].rate=e.target.value; setCustomForm({...customForm, seats: c});}}
                           className="hard-border px-3 py-2 text-sm"/>
                    <button type="button" onClick={() => { if (customForm.seats.length > 1) setCustomForm({...customForm, seats: customForm.seats.filter((_, idx) => idx !== i)}); }}
                            className="hard-border bg-white text-neutral-500 hover:text-red-700"
                            data-testid={`cp-remove-${i}`}>
                      <X size={12}/>
                    </button>
                  </div>
                ))}
              </div>
              <button type="button" onClick={() => setCustomForm({...customForm, seats: [...customForm.seats, { role: "", rate: 100 }]})}
                      className="btn-outline text-xs mt-3" data-testid="cp-add-seat">+ Add seat</button>
            </div>
            <div className="grid md:grid-cols-2 gap-3">
              <input required placeholder="Company name" value={customForm.company_name} onChange={(e) => setCustomForm({...customForm, company_name: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="cp-company"/>
              <input required placeholder="Your name" value={customForm.contact_name} onChange={(e) => setCustomForm({...customForm, contact_name: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="cp-name"/>
              <input required type="email" placeholder="Work email" value={customForm.contact_email} onChange={(e) => setCustomForm({...customForm, contact_email: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="cp-email"/>
              <select value={customForm.duration_months} onChange={(e) => setCustomForm({...customForm, duration_months: Number(e.target.value)})} className="hard-border px-3 py-2 text-sm" data-testid="cp-duration">
                {[2, 3, 6, 9, 12, 18, 24].map((n) => <option key={n} value={n}>{n} months</option>)}
              </select>
            </div>
            <button type="submit" className="btn-primary w-full text-sm" data-testid="cp-submit">Request scoping →</button>
          </form>
        </div>
      )}
    </main>
  );
}
