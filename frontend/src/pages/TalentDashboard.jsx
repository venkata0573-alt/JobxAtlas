import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { Sparkle, ArrowsClockwise, WarningCircle, X, Envelope } from "@phosphor-icons/react";
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

  const profile = user?.profile || {};
  const currentRate = Number(profile.hourly_rate || 0);
  const skills = profile.skills || [];
  const years = Number(profile.years_experience || 0);

  useEffect(() => {
    (async () => {
      try {
        const [a, m, n, b] = await Promise.all([
          api.get("/engagements"),
          api.get("/dashboard/metrics"),
          api.get("/talent/me/rate-nudge").catch(() => ({ data: { nudge: null } })),
          api.get("/talent/me/broadcasts").catch(() => ({ data: { items: [] } })),
        ]);
        setEngs(a.data); setMetrics(m.data); setNudge(n.data?.nudge || null);
        setBroadcasts(b.data?.items || []);
      } catch (e) { toast.error(formatErr(e)); }
    })();
  }, []);

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

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-10 flex-wrap gap-4">
        <div>
          <p className="overline text-[#002FA7] mb-3">TALENT DASHBOARD</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Hey {user?.name?.split(" ")[0]}.</h1>
          <p className="text-neutral-600 mt-2">Everything you&apos;re working on — in one grid.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/talent/profile" className="btn-outline text-sm">Edit profile →</Link>
          <Link to="/talent/earnings" className="btn-outline text-sm">View earnings →</Link>
        </div>
      </div>

      <DashboardMetrics metrics={metrics} role="talent"/>

      {/* Rate Nudge banner — appears when the last monthly scan found >±15% drift */}
      {nudge && !nudgeDismissed && (
        <section
          className={`mt-8 hard-border p-6 md:p-7 shadow-brutal flex flex-col md:flex-row md:items-center gap-4
            ${nudge.direction === "raise" ? "bg-[#FDF6E3] border-[#C79A3B]" : "bg-[#FEF0F0] border-red-300"}`}
          data-testid="rate-nudge-banner">
          <div className="hard-border bg-[#0B1B2B] text-[#C79A3B] w-12 h-12 flex items-center justify-center shrink-0">
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
      <section className="hard-border bg-[#FAF9F6] p-8 shadow-brutal mt-8" data-testid="rate-sanity-card">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="hard-border bg-[#0B1B2B] text-white w-12 h-12 flex items-center justify-center shrink-0">
              <Sparkle size={22} weight="duotone"/>
            </div>
            <div>
              <p className="overline text-[#C79A3B] mb-1">RATE SANITY CHECK</p>
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
              <p className="overline text-[#C79A3B] mb-1">HIRE-INTENT INBOX</p>
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
                className={`hard-border p-5 cursor-pointer transition-colors ${b.read ? "bg-[#FAF9F6]" : "bg-white hover:bg-[#FDF6E3] border-[#C79A3B]"}`}
                data-testid={`broadcast-${b.id}`}>
                <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                  <p className="font-display font-extrabold text-lg tracking-tight inline-flex items-center gap-2">
                    <Envelope size={16} weight={b.read ? "regular" : "fill"} color={b.read ? "#666" : "#C79A3B"}/>
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
