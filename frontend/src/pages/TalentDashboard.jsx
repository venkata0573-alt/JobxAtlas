import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { Sparkle, ArrowsClockwise, WarningCircle, X, Envelope, Buildings, PaperPlaneTilt, SealCheck, TrendUp } from "@phosphor-icons/react";
import DashboardMetrics from "@/components/DashboardMetrics";

export default function TalentDashboard() {
  const { user, refresh } = useAuth();
  const [engs, setEngs] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [suggest, setSuggest] = useState(null);
  const [suggesting, setSuggesting] = useState(false);
  const [applying, setApplying] = useState(false);
  const [nudge, setNudge] = useState(null);
  const [nudgeDismissed, setNudgeDismissed] = useState(false);
  const [broadcasts, setBroadcasts] = useState([]);
  const [employers, setEmployers] = useState([]);
  const [employerQuery, setEmployerQuery] = useState("");
  const [eoiTarget, setEoiTarget] = useState(null);  // employer obj or null
  const [eoiForm, setEoiForm] = useState({ message: "", proposed_hours_per_week: 10, start_date: "" });
  const [eoiSending, setEoiSending] = useState(false);
  const [recovery, setRecovery] = useState(null);

  const profile = user?.profile || {};
  const currentRate = Number(profile.hourly_rate || 0);
  const skills = profile.skills || [];
  const years = Number(profile.years_experience || 0);

  useEffect(() => {
    (async () => {
      try {
        const [a, m, n, b, e, r] = await Promise.all([
          api.get("/engagements"),
          api.get("/dashboard/metrics"),
          api.get("/talent/me/rate-nudge").catch(() => ({ data: { nudge: null } })),
          api.get("/talent/me/broadcasts").catch(() => ({ data: { items: [] } })),
          api.get("/employers").catch(() => ({ data: { items: [] } })),
          api.get("/talent/me/recovery-status").catch(() => ({ data: null })),
        ]);
        setEngs(a.data); setMetrics(m.data); setNudge(n.data?.nudge || null);
        setBroadcasts(b.data?.items || []);
        setEmployers(e.data?.items || []);
        setRecovery(r.data);
      } catch (e) { toast.error(formatErr(e)); }
    })();
  }, []);

  // Real-time SSE stream — prepends new broadcasts the moment an employer sends one.
  useEffect(() => {
    if (!user || user.role !== "talent") return;
    let es;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/auth/sse-token");
        if (cancelled) return;
        const base = process.env.REACT_APP_BACKEND_URL;
        es = new EventSource(`${base}/api/talent/me/broadcasts/stream?token=${encodeURIComponent(data.token)}`);
        es.onmessage = (e) => {
          try {
            const ev = JSON.parse(e.data);
            if (ev.type === "broadcast") {
              setBroadcasts((prev) => {
                if (prev.some((x) => x.id === ev.id)) return prev;
                return [{
                  id: ev.id, employer_name: ev.employer_name, subject: ev.subject,
                  message: ev.message, read: false, created_at: ev.created_at,
                }, ...prev];
              });
              toast.success(`${ev.employer_name} is ready to hire you`, { duration: 8000 });
            }
          } catch (err) { /* ignore parse errors on comments */ }
        };
        es.onerror = () => { /* browser auto-reconnects */ };
      } catch (err) { /* silent — non-critical */ }
    })();
    return () => { cancelled = true; if (es) es.close(); };
  }, [user]);

  const markBroadcastRead = async (docId) => {
    try {
      await api.post(`/talent/me/broadcasts/${docId}/read`);
      setBroadcasts((prev) => prev.map((x) => x.id === docId ? { ...x, read: true } : x));
    } catch (e) { /* silent */ }
  };

  const dismissNudge = async () => {
    setNudgeDismissed(true);
    try { await api.post("/talent/me/rate-nudge/dismiss"); } catch (e) { /* silent */ }
  };

  const applyNudge = async () => {
    if (!nudge) return;
    setApplying(true);
    try {
      await api.put("/profile", { ...profile, hourly_rate: Number(nudge.suggested_mid) });
      await refresh();
      await api.post("/talent/me/rate-nudge/dismiss").catch(() => {});
      setNudge(null);
      toast.success(`Rate updated to $${nudge.suggested_mid}/hr`);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setApplying(false); }
  };

  const runRateCheck = async () => {
    if (!skills.length) return toast.error("Add at least one skill to your profile first");
    setSuggesting(true);
    setSuggest(null);
    try {
      const r = await api.post("/profile/suggest-rate", {
        skills, years_experience: years, location: profile.location || "Global",
      });
      setSuggest(r.data);
      toast.success(`AI suggests $${r.data.mid}/hr for your current skill set`);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSuggesting(false); }
  };

  const applySuggestion = async () => {
    if (!suggest) return;
    setApplying(true);
    try {
      await api.put("/profile", { ...profile, hourly_rate: Number(suggest.mid) });
      await refresh();
      toast.success(`Rate updated to $${suggest.mid}/hr`);
      setSuggest(null);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setApplying(false); }
  };

  const drift = suggest ? Math.round(suggest.mid - currentRate) : 0;
  const driftPct = currentRate > 0 ? Math.round((drift / currentRate) * 100) : 0;

  const openEoi = (emp) => {
    setEoiTarget(emp);
    setEoiForm({ message: `Hi ${emp.company_name || emp.name} — I'd love to explore working together.`, proposed_hours_per_week: 10, start_date: "" });
  };

  const sendEoi = async (e) => {
    e.preventDefault();
    if (!eoiTarget) return;
    setEoiSending(true);
    try {
      await api.post("/eoi", {
        employer_id: eoiTarget.id,
        message: eoiForm.message,
        proposed_hours_per_week: Number(eoiForm.proposed_hours_per_week),
        start_date: eoiForm.start_date || "",
      });
      toast.success(`EOI sent to ${eoiTarget.company_name || eoiTarget.name}`);
      setEoiTarget(null);
    } catch (err) { toast.error(formatErr(err)); }
    finally { setEoiSending(false); }
  };

  const filteredEmployers = (employers || []).filter((emp) => {
    if (!employerQuery) return true;
    const q = employerQuery.toLowerCase();
    return (emp.company_name || "").toLowerCase().includes(q)
        || (emp.company_industry || "").toLowerCase().includes(q)
        || (emp.name || "").toLowerCase().includes(q);
  });

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-10 flex-wrap gap-4">
        <div>
          <p className="overline text-[#6B21A8] mb-3">TALENT DASHBOARD</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight inline-flex items-baseline gap-3 flex-wrap">
            Hey {user?.name?.split(" ")[0]}.
            {profile.recovery_cleared_at && !profile.under_review && !profile.excessive_revisions && (() => {
              const cleared = new Date(profile.recovery_cleared_at);
              const daysSince = Math.floor((Date.now() - cleared.getTime()) / (86400 * 1000));
              if (daysSince > 90) return null;
              return (
                <span title="Recovered from a rough patch — 3+ clean approvals in a row"
                      data-testid="proven-reliable-self"
                      className="text-[10px] font-mono uppercase tracking-widest bg-emerald-100 text-emerald-800 px-2 py-1 border border-emerald-400 self-center">
                  ★ Proven Reliable
                </span>
              );
            })()}
          </h1>
          <p className="text-neutral-600 mt-2">Everything you&apos;re working on — in one grid.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/talent/profile" className="btn-outline text-sm">Edit profile →</Link>
          <Link to="/talent/earnings" className="btn-outline text-sm">View earnings →</Link>
        </div>
      </div>

      <DashboardMetrics metrics={metrics} role="talent"/>

      {/* Recovery banner — visible while a revision penalty is active */}
      {recovery?.has_penalty && (
        <section className="mt-8 hard-border p-6 md:p-7 shadow-brutal bg-[#FEF9C3] border-yellow-500 flex flex-col md:flex-row md:items-center gap-4"
                 data-testid="recovery-banner">
          <div className="hard-border bg-[#0B1B2B] text-[#A78BFA] w-12 h-12 flex items-center justify-center shrink-0">
            <SealCheck size={22} weight="duotone"/>
          </div>
          <div className="flex-1 min-w-0">
            <p className="overline text-[#854D0E] mb-1">RECOVERY IN PROGRESS</p>
            <p className="font-display font-extrabold text-lg md:text-xl tracking-tight leading-snug">
              {recovery.remaining} more clean approval{recovery.remaining === 1 ? "" : "s"} and your
              <span className="capitalize"> {recovery.target.replace(/_/g, " ")}</span> flag lifts automatically.
            </p>
            <p className="text-xs text-neutral-700 mt-1">
              A clean approval = a deliverable approved with zero revision requests. A rejection resets the streak.
              Visibility score today: <b>{recovery.visibility_score}</b>{" · "}Rate bias: <b>{recovery.rate_bias_pct}%</b>
            </p>
            <div className="mt-3 hard-border bg-white h-3 relative overflow-hidden" data-testid="recovery-progress">
              <div className="absolute inset-y-0 left-0 bg-[#6B21A8] transition-all"
                   style={{ width: `${recovery.progress_pct}%` }}/>
            </div>
            <p className="text-[10px] font-mono uppercase tracking-widest text-[#6B21A8] mt-2">
              {recovery.clean_streak} / {recovery.needed} clean approvals · {recovery.progress_pct}%
            </p>
          </div>
          <TrendUp size={26} className="text-[#6B21A8] shrink-0"/>
        </section>
      )}

      {/* Rate Nudge banner — appears when the last monthly scan found >±15% drift */}
      {nudge && !nudgeDismissed && (
        <section
          className={`mt-8 hard-border p-6 md:p-7 shadow-brutal flex flex-col md:flex-row md:items-center gap-4
            ${nudge.direction === "raise" ? "bg-[#F5F3FF] border-[#6B21A8]" : "bg-[#FEF0F0] border-red-300"}`}
          data-testid="rate-nudge-banner">
          <div className="hard-border bg-[#0B1B2B] text-[#6B21A8] w-12 h-12 flex items-center justify-center shrink-0">
            <WarningCircle size={22} weight="duotone"/>
          </div>
          <div className="flex-1 min-w-0">
            <p className="overline text-[#0B1B2B] mb-1">MONTHLY RATE NUDGE</p>
            <p className="font-display font-extrabold text-lg md:text-xl tracking-tight leading-snug">
              Your ${nudge.current_rate}/hr is <span className={nudge.direction === "raise" ? "text-emerald-700" : "text-red-700"}>
                {Math.abs(nudge.drift_pct)}%
              </span> {nudge.direction === "raise" ? "below" : "above"} the market mid of ${nudge.suggested_mid}/hr.
            </p>
            {nudge.rationale && <p className="text-sm text-neutral-600 mt-1">{nudge.rationale}</p>}
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={applyNudge}
              disabled={applying}
              className="btn-primary text-sm whitespace-nowrap"
              data-testid="apply-nudge-btn">
              {applying ? "Applying…" : `Apply $${nudge.suggested_mid}/hr →`}
            </button>
            <button
              onClick={dismissNudge}
              className="btn-outline text-sm inline-flex items-center gap-1"
              data-testid="dismiss-nudge-btn"
              aria-label="Dismiss">
              <X size={14}/>
            </button>
          </div>
        </section>
      )}

      {/* Rate Sanity Check */}
      <section className="hard-border bg-[#F5F3FF] p-8 shadow-brutal mt-8" data-testid="rate-sanity-card">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="hard-border bg-[#0B1B2B] text-white w-12 h-12 flex items-center justify-center shrink-0">
              <Sparkle size={22} weight="duotone"/>
            </div>
            <div>
              <p className="overline text-[#6B21A8] mb-1">RATE SANITY CHECK</p>
              <h2 className="font-display font-extrabold text-2xl tracking-tight">Is your ${currentRate}/hr still market-fresh?</h2>
              <p className="text-sm text-neutral-600 mt-1">
                Re-run the AI rate suggestion any time you add a new skill or gain a year of experience.
                Currently modelling <span className="font-mono">{skills.length}</span> skills · <span className="font-mono">{years}</span> yrs · <span className="font-mono">{profile.location || "Global"}</span>.
              </p>
            </div>
          </div>
          <button
            onClick={runRateCheck}
            disabled={suggesting}
            className="btn-primary text-sm inline-flex items-center gap-2 whitespace-nowrap"
            data-testid="run-rate-check-btn">
            <ArrowsClockwise size={16} weight="bold" className={suggesting ? "animate-spin" : ""}/>
            {suggesting ? "Checking…" : "Refresh my rate"}
          </button>
        </div>

        {suggest && (
          <div className="mt-6 pt-6 border-t border-black/10 grid md:grid-cols-[1.2fr_1fr] gap-6" data-testid="rate-suggestion-panel">
            <div>
              <p className="overline text-neutral-500 mb-2">AI suggestion (Claude Sonnet 5)</p>
              <p className="font-display font-black text-4xl text-[#0B1B2B]">
                ${suggest.low}<span className="text-2xl text-neutral-500">–</span>${suggest.high}
                <span className="text-lg text-neutral-500 font-mono">/hr</span>
              </p>
              <p className="text-sm text-neutral-600 mt-2">Mid-range: <span className="font-mono font-bold">${suggest.mid}/hr</span></p>
              {suggest.rationale && (
                <p className="text-xs text-neutral-500 mt-3 leading-relaxed">{suggest.rationale}</p>
              )}
            </div>
            <div className="hard-border bg-white p-5">
              {currentRate > 0 && drift !== 0 ? (
                <>
                  <p className="overline text-neutral-500 mb-2">Delta vs your current rate</p>
                  <p className={`font-display font-black text-3xl ${drift > 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {drift > 0 ? "+" : ""}${drift}
                    <span className="text-base font-mono text-neutral-500 ml-2">({drift > 0 ? "+" : ""}{driftPct}%)</span>
                  </p>
                  <p className="text-xs text-neutral-500 mt-3">
                    {drift > 0
                      ? "You're pricing under the market. Consider bumping to stay competitive on quality perception."
                      : "You're pricing above the market. That can be intentional — but be ready to justify with portfolio & reviews."}
                  </p>
                </>
              ) : (
                <p className="text-sm text-neutral-600">Your current rate matches the mid-range — you&apos;re on point.</p>
              )}
              <button
                onClick={applySuggestion}
                disabled={applying}
                className="btn-accent text-sm w-full mt-4"
                data-testid="apply-rate-btn">
                {applying ? "Applying…" : `Apply $${suggest.mid}/hr →`}
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Broadcasts inbox — employer "I'm ready to hire" notes */}
      {broadcasts.length > 0 && (
        <section className="hard-border bg-white p-8 shadow-brutal mt-8" data-testid="broadcasts-inbox">
          <div className="flex items-baseline justify-between mb-6 gap-4 flex-wrap">
            <div>
              <p className="overline text-[#6B21A8] mb-1">HIRE-INTENT INBOX</p>
              <h2 className="font-display font-extrabold text-2xl tracking-tight">
                {broadcasts.filter((b) => !b.read).length > 0
                  ? `${broadcasts.filter((b) => !b.read).length} employer${broadcasts.filter((b) => !b.read).length === 1 ? " is" : "s are"} ready to hire you.`
                  : "Recent hire-intent notes."}
              </h2>
            </div>
          </div>
          <div className="space-y-3">
            {broadcasts.slice(0, 5).map((b) => (
              <div
                key={b.id}
                onClick={() => !b.read && markBroadcastRead(b.id)}
                style={!b.read ? { borderColor: "#6B21A8", borderWidth: "2px" } : undefined}
                className={`hard-border p-5 cursor-pointer transition-colors ${b.read ? "bg-[#F5F3FF]" : "bg-white hover:bg-[#F5F3FF]"}`}
                data-testid={`broadcast-${b.id}`}>
                <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                  <p className="font-display font-extrabold text-lg tracking-tight inline-flex items-center gap-2">
                    <Envelope size={16} weight={b.read ? "regular" : "fill"} color={b.read ? "#666" : "#6B21A8"}/>
                    {b.employer_name}
                  </p>
                  <span className="text-[10px] font-mono text-neutral-400 uppercase tracking-widest">
                    {new Date(b.created_at).toLocaleDateString()}{!b.read && " · NEW"}
                  </span>
                </div>
                <p className="text-sm text-[#333] leading-relaxed whitespace-pre-line">{b.message}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="hard-border bg-white p-8 shadow-brutal mt-8" data-testid="companies-hiring">
        <div className="flex items-baseline justify-between mb-6 gap-4 flex-wrap">
          <div>
            <p className="overline text-[#6B21A8] mb-1">COMPANIES ON JOB ATLAS</p>
            <h2 className="font-display font-extrabold text-2xl tracking-tight inline-flex items-center gap-2">
              <Buildings size={22} weight="duotone" color="#0B1B2B"/>
              {employers.length} {employers.length === 1 ? "company is" : "companies are"} on the platform
            </h2>
            <p className="text-sm text-neutral-600 mt-1">Raise an Expression of Interest with any employer. They see it instantly on their dashboard and can accept to create an engagement.</p>
          </div>
          <input
            type="search"
            placeholder="Search companies by name or industry…"
            value={employerQuery}
            onChange={(e) => setEmployerQuery(e.target.value)}
            className="hard-border px-3 py-2 bg-white text-sm w-full md:w-72"
            data-testid="employer-search"/>
        </div>
        {filteredEmployers.length === 0 ? (
          <p className="text-neutral-500 text-sm">
            {employers.length === 0
              ? "No companies onboarded yet — check back soon."
              : `No companies match "${employerQuery}".`}
          </p>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredEmployers.slice(0, 12).map((emp) => (
              <div key={emp.id} className="hard-border bg-[#F5F3FF] p-5" data-testid={`employer-card-${emp.id}`}>
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="min-w-0">
                    <p className="font-display font-extrabold text-lg tracking-tight truncate inline-flex items-center gap-1">
                      {emp.company_name || emp.name}
                      {emp.is_verified && (
                        <span title="Verified company" data-testid={`verified-badge-${emp.id}`} className="text-[#6B21A8]">✦</span>
                      )}
                    </p>
                    <p className="text-xs font-mono text-neutral-500 truncate">{emp.company_industry || "—"}</p>
                  </div>
                  {emp.hours_balance > 0 && (
                    <span className="hard-border bg-[#6B21A8] text-white text-[10px] font-mono px-2 py-1 tracking-widest shrink-0">
                      {emp.hours_balance}h READY
                    </span>
                  )}
                </div>
                {emp.headline && <p className="text-xs text-neutral-600 line-clamp-2 mb-3">{emp.headline}</p>}
                <div className="flex items-center justify-between text-[11px] font-mono text-neutral-500 mb-3">
                  <span>{emp.location || "Remote"}</span>
                  <span>{emp.active_engagements > 0 ? `${emp.active_engagements} active` : "New"}</span>
                </div>
                <button
                  onClick={() => openEoi(emp)}
                  className="btn-primary text-xs w-full inline-flex items-center justify-center gap-1"
                  data-testid={`raise-eoi-${emp.id}`}>
                  <PaperPlaneTilt size={12} weight="fill"/> Raise EOI
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* EOI modal */}
      {eoiTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
             onClick={() => setEoiTarget(null)}
             data-testid="eoi-modal">
          <form onSubmit={sendEoi} onClick={(e) => e.stopPropagation()}
                className="hard-border bg-white max-w-lg w-full p-6 shadow-brutal-lg space-y-3 relative">
            <button type="button" onClick={() => setEoiTarget(null)}
                    className="absolute top-4 right-4 text-neutral-400 hover:text-neutral-700"
                    data-testid="close-eoi-modal">
              <X size={18}/>
            </button>
            <p className="overline text-[#6B21A8]">EXPRESSION OF INTEREST</p>
            <h3 className="font-display font-extrabold text-2xl tracking-tight">
              Reach out to {eoiTarget.company_name || eoiTarget.name}
            </h3>
            <p className="text-xs text-neutral-500 -mt-1">{eoiTarget.company_industry || "—"} · {eoiTarget.location || "Remote"}</p>
            <textarea
              required
              rows={4}
              value={eoiForm.message}
              onChange={(e) => setEoiForm({...eoiForm, message: e.target.value})}
              className="hard-border px-3 py-2 bg-[#F5F3FF] text-sm w-full"
              placeholder="Tell them what you can bring…"
              data-testid="eoi-message"/>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest text-neutral-500">Hours / week</label>
                <input type="number" min={1} max={40} required value={eoiForm.proposed_hours_per_week}
                       onChange={(e) => setEoiForm({...eoiForm, proposed_hours_per_week: e.target.value})}
                       className="hard-border px-3 py-2 bg-white text-sm w-full mt-1"
                       data-testid="eoi-hours"/>
              </div>
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest text-neutral-500">Start date</label>
                <input type="date" value={eoiForm.start_date}
                       onChange={(e) => setEoiForm({...eoiForm, start_date: e.target.value})}
                       className="hard-border px-3 py-2 bg-white text-sm w-full mt-1"
                       data-testid="eoi-start"/>
              </div>
            </div>
            <button type="submit" disabled={eoiSending}
                    className="btn-primary w-full text-sm inline-flex items-center justify-center gap-2"
                    data-testid="submit-eoi">
              <PaperPlaneTilt size={14} weight="fill"/>
              {eoiSending ? "Sending…" : "Send EOI →"}
            </button>
          </form>
        </div>
      )}

      <section className="hard-border bg-white p-8 shadow-brutal mt-8">
        <h2 className="font-display font-extrabold text-2xl tracking-tight mb-6">Engagements</h2>
        {engs.length === 0 ? (
          <p className="text-neutral-500">No engagements yet. Employers who purchase hours will invite you here.</p>
        ) : (
          <div className="divide-y divide-black/10">
            {engs.map((e) => (
              <div key={e.id} className="py-4 flex items-center justify-between gap-4" data-testid={TID.engagementRow(e.id)}>
                <div>
                  <p className="font-display font-extrabold text-lg tracking-tight">{e.employer_name}</p>
                  <p className="text-sm text-neutral-500">{e.scope}</p>
                </div>
                <div className="text-right">
                  <p className="font-mono text-sm">{e.hours_allocated}h · {e.status.replace(/_/g, " ")}</p>
                  <Link to={`/engagement/${e.id}`} className="text-xs underline underline-offset-4" data-testid={TID.contractOpen(e.id)}>Open →</Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
