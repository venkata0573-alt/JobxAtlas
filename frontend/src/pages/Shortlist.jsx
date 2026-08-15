import React, { useEffect, useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { toast } from "sonner";
import { BookmarkSimple, Trash, ShoppingCart, MapPin, Star, PaperPlaneTilt, X, UploadSimple } from "@phosphor-icons/react";

export default function Shortlist() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [removing, setRemoving] = useState(null);
  const [hoursPerTalent, setHoursPerTalent] = useState(20);
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [broadcastMsg, setBroadcastMsg] = useState("");
  const [broadcastSending, setBroadcastSending] = useState(false);
  const [crmConns, setCrmConns] = useState([]);
  const [pushing, setPushing] = useState(null); // talent_id being pushed
  const nav = useNavigate();

  useEffect(() => { load(); loadCrm(); }, []);
  const load = async () => {
    try {
      const r = await api.get("/shortlist");
      setItems(r.data.items || []);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setLoading(false); }
  };
  const loadCrm = async () => {
    try { const r = await api.get("/integrations/crm"); setCrmConns(r.data.items || []); }
    catch { /* ignore */ }
  };

  const pushToCrm = async (t) => {
    if (crmConns.length === 0) {
      toast.error("Connect a CRM first — /integrations");
      return;
    }
    // If multiple providers connected, ask; otherwise auto-use the only one.
    const provider = crmConns.length === 1
      ? crmConns[0].provider
      : window.prompt(`Push to which CRM? Options: ${crmConns.map((c) => c.provider).join(", ")}`, crmConns[0].provider);
    if (!provider) return;
    setPushing(t.talent_id);
    try {
      await api.post("/integrations/crm/push-lead", {
        provider,
        talent_id: t.talent_id,
        talent_name: t.talent_name,
        hourly_rate: t.hourly_rate,
        headline: t.headline || "",
        location: t.location || "",
      });
      toast.success(`Pushed ${t.talent_name} to ${provider}`);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setPushing(null); }
  };

  const remove = async (talentId) => {
    setRemoving(talentId);
    try {
      await api.delete(`/shortlist/${talentId}`);
      setItems((prev) => prev.filter((x) => x.talent_id !== talentId));
      toast.success("Removed from shortlist");
    } catch (e) { toast.error(formatErr(e)); }
    finally { setRemoving(null); }
  };

  const stats = useMemo(() => {
    if (!items.length) return null;
    const rates = items.map((x) => Number(x.hourly_rate || 0)).filter((n) => n > 0);
    const avg = rates.length ? Math.round(rates.reduce((a, b) => a + b, 0) / rates.length) : 0;
    const min = rates.length ? Math.min(...rates) : 0;
    const max = rates.length ? Math.max(...rates) : 0;
    const bundleTotal = avg * hoursPerTalent * items.length;
    return { count: items.length, avg, min, max, bundleTotal };
  }, [items, hoursPerTalent]);

  const gotoPurchase = () => {
    // Pre-fill the calculator via URL params — PurchaseHours reads these.
    const params = new URLSearchParams({
      context: "shortlist",
      talents: String(items.length),
      hours_per_talent: String(hoursPerTalent),
      est_budget: String(stats?.bundleTotal || 0),
    });
    nav(`/employer/purchase?${params.toString()}`);
  };

  const sendBroadcast = async () => {
    setBroadcastSending(true);
    try {
      const r = await api.post("/shortlist/broadcast", { message: broadcastMsg });
      const { delivered, emailed, skipped_curated } = r.data;
      toast.success(
        `Broadcast sent to ${delivered} talent${delivered === 1 ? "" : "s"}` +
        (emailed ? ` · ${emailed} email${emailed === 1 ? "" : "s"} delivered` : "") +
        (skipped_curated ? ` · ${skipped_curated} curated skipped (no real inbox)` : "")
      );
      setBroadcastOpen(false);
      setBroadcastMsg("");
    } catch (e) { toast.error(formatErr(e)); }
    finally { setBroadcastSending(false); }
  };

  const realCount = items.filter((x) => !x.is_curated).length;

  if (loading) {
    return <main className="max-w-7xl mx-auto px-6 py-16"><p className="font-mono text-neutral-500">Loading shortlist…</p></main>;
  }

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-start justify-between gap-4 mb-10 flex-wrap">
        <div>
          <p className="overline text-[#6B21A8] mb-3">MY SHORTLIST</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Talents you&apos;ve saved.</h1>
          <p className="text-neutral-600 mt-2 max-w-xl">
            Contact information stays locked until you purchase a bundle of hours. Reach out to any shortlisted
            talent the moment your first bundle is on file.
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <Link to="/employer" className="btn-outline text-sm">← Dashboard</Link>
          <Link to="/browse" className="btn-outline text-sm">Find more talent →</Link>
        </div>
      </div>

      {items.length === 0 ? (
        <section className="hard-border bg-[#F5F3FF] p-16 text-center shadow-brutal" data-testid="shortlist-empty">
          <BookmarkSimple size={40} weight="duotone" className="mx-auto mb-4 text-[#6B21A8]"/>
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-2">Your shortlist is empty.</h2>
          <p className="text-neutral-600 max-w-md mx-auto mb-6">
            Browse curated city × skill pages and tap any talent card to open a preview. Use <strong>Shortlist for future hire</strong> to save profiles here.
          </p>
          <Link to="/browse" className="btn-primary inline-block">Browse talent →</Link>
        </section>
      ) : (
        <>
          {/* Summary + CTA */}
          <section className="hard-border bg-gradient-to-br from-[#0B1B2B] via-[#122740] to-[#0B1B2B] text-white p-8 md:p-10 shadow-brutal mb-8" data-testid="shortlist-summary">
            <div className="grid md:grid-cols-[1.4fr_1fr] gap-8 items-center">
              <div>
                <p className="overline text-[#6B21A8] mb-3">READY TO PURCHASE HOURS</p>
                <h2 className="font-display font-extrabold text-3xl tracking-tight mb-3">
                  {stats.count} talent{stats.count > 1 ? "s" : ""} · avg <span className="text-[#A78BFA]">${stats.avg}/hr</span>
                </h2>
                <p className="text-sm text-neutral-300 leading-relaxed max-w-md">
                  Buy a bundle of hours to unlock direct messaging with everyone on this shortlist.
                  A 12-month exclusivity contract auto-generates when the first hour is logged.
                </p>
                <div className="mt-6 flex items-center gap-3 flex-wrap">
                  <label className="text-xs font-mono text-neutral-400 tracking-widest uppercase">Hours per talent</label>
                  <div className="hard-border border-white/30 inline-flex overflow-hidden">
                    {[10, 20, 40, 80].map((h) => (
                      <button
                        key={h}
                        onClick={() => setHoursPerTalent(h)}
                        className={`px-3 py-2 text-sm font-mono ${hoursPerTalent === h ? "bg-[#6B21A8] text-[#0B1B2B]" : "bg-transparent text-white hover:bg-white/10"}`}
                        data-testid={`hours-per-talent-${h}`}>
                        {h}h
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="hard-border border-white/20 bg-white/[0.04] p-6">
                <p className="text-xs font-mono text-neutral-400 tracking-widest uppercase mb-2">Estimated bundle</p>
                <p className="font-display font-black text-4xl md:text-5xl text-white leading-tight">
                  ${stats.bundleTotal.toLocaleString()}
                </p>
                <p className="text-xs text-neutral-400 mt-2 font-mono">
                  {stats.count} × {hoursPerTalent}h × avg ${stats.avg}/hr
                </p>
                <button
                  onClick={gotoPurchase}
                  className="mt-6 w-full inline-flex items-center justify-center gap-2 bg-[#6B21A8] hover:bg-[#A78BFA] text-[#0B1B2B] font-display font-extrabold text-sm tracking-tight px-4 py-3 hard-border border-[#6B21A8]"
                  data-testid="purchase-for-shortlist-btn">
                  <ShoppingCart size={16} weight="fill"/> Purchase hours for this shortlist →
                </button>
                <button
                  onClick={() => setBroadcastOpen(true)}
                  disabled={realCount === 0}
                  className="mt-2 w-full inline-flex items-center justify-center gap-2 bg-transparent hover:bg-white/10 text-white font-display font-extrabold text-sm tracking-tight px-4 py-3 hard-border border-white/40 disabled:opacity-40"
                  data-testid="broadcast-btn"
                  title={realCount === 0 ? "No real-user talents to broadcast to (curated demo profiles are skipped)" : ""}>
                  <PaperPlaneTilt size={16} weight="fill"/> Broadcast &quot;I&apos;m ready to hire&quot;
                </button>
              </div>
            </div>
          </section>

          {/* Talent cards */}
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((t) => (
              <div key={t.talent_id} className="hard-border bg-white p-6 shadow-brutal" data-testid={`shortlist-item-${t.talent_id}`}>
                <div className="flex items-start justify-between mb-2 gap-2">
                  <p className="overline text-[#6B21A8] inline-flex items-center gap-1 truncate">
                    <MapPin size={11} weight="fill"/> {t.location || "Global"}
                  </p>
                  {t.is_curated && (
                    <span className="text-[10px] font-mono text-[#6B21A8] uppercase tracking-widest inline-flex items-center gap-1 shrink-0">
                      <Star size={11} weight="fill"/> Vetted
                    </span>
                  )}
                </div>
                <h3 className="font-display font-black text-xl tracking-tight text-[#0B1B2B]">{t.talent_name}</h3>
                <p className="text-sm text-neutral-600 mt-1 line-clamp-2">{t.headline || "Independent professional"}</p>
                {t.skills?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {t.skills.slice(0, 4).map((s) => (
                      <span key={s} className="text-[11px] font-mono hard-border px-2 py-0.5 bg-neutral-50">{s}</span>
                    ))}
                  </div>
                )}
                <div className="flex justify-between items-baseline mt-5 pt-4 border-t border-black/10">
                  <p className="font-display font-black text-xl">${t.hourly_rate}<span className="text-xs text-neutral-500">/hr</span></p>
                  <div className="flex items-center gap-2">
                    {crmConns.length > 0 && !t.is_curated && (
                      <button
                        onClick={() => pushToCrm(t)}
                        disabled={pushing === t.talent_id}
                        className="text-xs text-[#6B21A8] hover:text-[#0B1B2B] inline-flex items-center gap-1"
                        data-testid={`crm-push-${t.talent_id}`}
                        title={`Push to ${crmConns.map((c) => c.provider).join(", ")}`}>
                        <UploadSimple size={12} weight="bold"/> {pushing === t.talent_id ? "Pushing…" : "Push to CRM"}
                      </button>
                    )}
                    <button
                      onClick={() => remove(t.talent_id)}
                      disabled={removing === t.talent_id}
                      className="text-xs text-neutral-500 hover:text-red-700 inline-flex items-center gap-1"
                      data-testid={`remove-${t.talent_id}`}>
                      <Trash size={12}/> Remove
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Broadcast composer modal */}
      {broadcastOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => !broadcastSending && setBroadcastOpen(false)}
          data-testid="broadcast-modal">
          <div className="hard-border bg-white max-w-lg w-full p-8 shadow-brutal-lg relative" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setBroadcastOpen(false)}
              disabled={broadcastSending}
              className="absolute top-4 right-4 text-neutral-400 hover:text-neutral-700"
              data-testid="close-broadcast-modal">
              <X size={20}/>
            </button>
            <p className="overline text-[#6B21A8] mb-2">BROADCAST TO SHORTLIST</p>
            <h2 className="font-display font-extrabold text-2xl tracking-tight text-[#0B1B2B]">Send one note to {realCount} talent{realCount === 1 ? "" : "s"}.</h2>
            <p className="text-sm text-neutral-600 mt-2 leading-relaxed">
              Everyone on your shortlist will receive the same in-app note. When the Resend API key is
              configured, they&apos;ll also get an email pointing them back to Job Atlas.
            </p>

            <label className="overline block mt-6 mb-2">Your message (optional — a default is used if left blank)</label>
            <textarea
              value={broadcastMsg}
              onChange={(e) => setBroadcastMsg(e.target.value)}
              placeholder="Hi — I'm ready to bring you on for a paid engagement through Job Atlas. Reply here to talk scope, timelines and start date."
              rows={5}
              maxLength={800}
              data-testid="broadcast-message"
              className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#0B1B2B] text-sm"
            />
            <p className="text-[10px] font-mono text-neutral-400 mt-1 text-right">{broadcastMsg.length}/800</p>

            <div className="flex gap-3 mt-6">
              <button
                onClick={sendBroadcast}
                disabled={broadcastSending}
                className="btn-primary text-sm flex-1 inline-flex items-center justify-center gap-2"
                data-testid="send-broadcast-btn">
                <PaperPlaneTilt size={14} weight="fill"/>
                {broadcastSending ? "Sending…" : `Send to ${realCount} talent${realCount === 1 ? "" : "s"}`}
              </button>
              <button
                onClick={() => setBroadcastOpen(false)}
                disabled={broadcastSending}
                className="btn-outline text-sm">
                Cancel
              </button>
            </div>
            {items.some((x) => x.is_curated) && (
              <p className="text-[11px] font-mono text-neutral-500 mt-4 leading-relaxed">
                Note: curated demo profiles on your shortlist ({items.length - realCount}) are skipped —
                they don&apos;t have real inboxes yet.
              </p>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
