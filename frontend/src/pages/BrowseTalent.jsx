import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { BACKEND_URL } from "@/config";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";
import { MagnifyingGlass, Star, X } from "@phosphor-icons/react";
import { useAuth } from "@/context/AuthContext";

export default function BrowseTalent() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [skill, setSkill] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const industryFilter = searchParams.get("industry") || "";

  const load = async () => {
    setLoading(true);
    try {
      const params = { q, skill };
      if (industryFilter) params.industry = industryFilter;
      if (verifiedOnly) params.verified_only = true;
      const r = await api.get("/talent", { params });
      setItems(r.data);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [industryFilter, verifiedOnly]);

  const clearIndustry = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("industry");
    setSearchParams(next);
  };

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-10">
        <div>
          <p className="overline text-[#6B21A8] mb-3">BROWSE TALENT</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Vetted professionals.</h1>
        </div>
        <p className="hidden md:block text-sm text-neutral-500 max-w-xs">Contact details are unlocked after you purchase hours and both parties sign the contract.</p>
      </div>

      {/* Industry filter banner — set via /browse?industry=<label> from the Landing trust bar */}
      {industryFilter && (
        <div className="hard-border bg-[#0B1B2B] text-white p-4 mb-6 flex items-center justify-between gap-4"
             data-testid="industry-filter-banner">
          <div className="flex items-center gap-3 min-w-0">
            <span className="w-1.5 h-1.5 rounded-full bg-[#6B21A8] shrink-0"/>
            <p className="text-sm">
              <span className="overline text-[#6B21A8] mr-2">FILTERED BY INDUSTRY</span>
              <span className="font-display font-extrabold">{industryFilter}</span>
              <span className="hidden md:inline text-neutral-400 ml-3 text-xs">
                · Showing talents self-tagged with this industry <em>or</em> who&apos;ve delivered past engagements to buyers in it
              </span>
            </p>
          </div>
          <button
            onClick={clearIndustry}
            className="text-sm text-neutral-300 hover:text-white inline-flex items-center gap-1"
            data-testid="clear-industry-filter">
            <X size={14}/> Clear
          </button>
        </div>
      )}

      <div className="hard-border bg-white p-6 shadow-brutal grid md:grid-cols-[1fr_1fr_auto] gap-3 mb-10">
        <div className="flex items-center gap-2 hard-border px-3">
          <MagnifyingGlass size={16} />
          <input data-testid={TID.browseSearch} placeholder="Search by name or headline"
                 value={q} onChange={(e) => setQ(e.target.value)}
                 className="w-full py-3 focus:outline-none"/>
        </div>
        <input data-testid={TID.browseSkill} placeholder="Skill (e.g. Python, Figma)"
               value={skill} onChange={(e) => setSkill(e.target.value)}
               className="hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
        <button onClick={load} className="btn-primary">Filter</button>
      </div>

      <div className="mb-6 flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setVerifiedOnly((v) => !v)}
          className={`hard-border px-3 py-2 text-xs inline-flex items-center gap-2 ${verifiedOnly ? "bg-[#0EA5E9] text-white" : "bg-white"}`}
          data-testid="verified-only-toggle">
          <span className={`text-base leading-none ${verifiedOnly ? "text-white" : "text-[#0EA5E9]"}`}>✓</span>
          Verified only {verifiedOnly ? "· ON" : ""}
        </button>
        {verifiedOnly && (
          <p className="text-xs font-mono text-neutral-500">Showing only BGV-cleared talent.</p>
        )}
      </div>

      {loading ? <p className="font-mono">Loading…</p> :
        items.length === 0 ? (
          <div className="hard-border bg-white p-16 text-center">
            <p className="font-display font-extrabold text-2xl mb-2">No talent yet</p>
            <p className="text-neutral-500">Be the first — <Link to="/register" className="underline">create a talent profile</Link>.</p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((t, i) => (
              <div key={t.id} className={`hard-border bg-white p-7 shadow-brutal-hover relative ${i % 3 === 1 ? "md:translate-y-6" : ""}`}
                   data-testid={TID.browseTalentCard(t.id)}>
                {t.is_trusted_partner && (
                  <div className="absolute -top-3 left-4 bg-[#6B21A8] text-white px-3 py-1 hard-border text-[10px] font-mono tracking-widest z-10"
                       data-testid={`trusted-partner-${t.id}`}
                       title={`${t.completed_engagements} completed engagements · ${t.avg_rating}★ avg`}>
                    ★ TRUSTED PARTNER
                  </div>
                )}
                {t.excessive_revisions && (
                  <div className="absolute -top-3 left-4 bg-red-100 text-red-800 px-3 py-1 hard-border border-red-300 text-[10px] font-mono tracking-widest z-10"
                       data-testid={`excessive-revisions-${t.id}`}
                       title="This talent has accumulated 5+ revisions on a single deliverable.">
                    ⚠ REVISION HISTORY
                  </div>
                )}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-start gap-3 min-w-0">
                    {t.profile?.avatar_url ? (
                      <img src={`${BACKEND_URL}${t.profile.avatar_url}`}
                           alt={t.name} className="w-12 h-12 hard-border object-cover flex-shrink-0"/>
                    ) : (
                      <div className="w-12 h-12 hard-border bg-[#0B1B2B] text-[#6B21A8] font-display font-black text-lg flex items-center justify-center flex-shrink-0">
                        {(t.name || "?").charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div className="min-w-0">
                      <p className="overline text-[#6B21A8]">{t.profile?.location || "Global"}</p>
                      <h3 className="font-display font-black text-2xl tracking-tight mt-1 truncate inline-flex items-center gap-1">
                        {t.name}
                        {t.is_verified && (
                          <span title="BGV verified" data-testid={`verified-badge-${t.id}`} className="text-[#0EA5E9] text-xl leading-none">✓</span>
                        )}
                        {t.is_proven_reliable && (
                          <span title="Recovered from a rough patch — 3+ clean approvals in a row"
                                data-testid={`proven-reliable-${t.id}`}
                                className="ml-1 text-[9px] font-mono uppercase tracking-widest bg-emerald-100 text-emerald-800 px-1.5 py-0.5 border border-emerald-400">
                            ★ Proven Reliable
                          </span>
                        )}
                      </h3>
                      <p className="text-neutral-600 text-sm mt-1 line-clamp-2">{t.profile?.headline || "Independent professional"}</p>
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0" data-testid={`rate-chip-${t.id}`}>
                    <p className="overline text-neutral-400">Talent rate</p>
                    <p className="font-display font-black text-2xl">${t.profile?.hourly_rate || 0}<span className="text-sm text-neutral-500">/hr</span></p>
                    {t.sell_rate && user?.role !== "talent" ? (
                      <p className="mt-1 hard-border bg-[#0B1B2B] text-[#6B21A8] text-[10px] font-mono px-2 py-1 tracking-widest whitespace-nowrap" data-testid={`sell-rate-${t.id}`}>
                        You pay ${t.sell_rate}/hr
                      </p>
                    ) : null}
                  </div>
                </div>
                {t.profile?.portfolio_images?.length > 0 && (
                  <div className="grid grid-cols-3 gap-1 mb-3">
                    {t.profile.portfolio_images.slice(0, 3).map((f) => (
                      <img key={f} src={`${BACKEND_URL}${f}`} alt="portfolio"
                           className="w-full h-14 object-cover hard-border"/>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-2 mb-5">
                  {(t.profile?.skills || []).slice(0, 5).map((s) => (
                    <span key={s} className="text-xs font-mono hard-border px-2 py-1 bg-[#F9F9F9]">{s}</span>
                  ))}
                </div>
                <div className="flex items-center justify-between border-t border-black/10 pt-4">
                  <span className="text-sm flex items-center gap-1"><Star weight="fill" size={14}/> {t.profile?.years_experience || 0} yrs</span>
                  <Link to={`/employer`} className="btn-outline text-sm" data-testid={TID.hireBtn(t.id)}>View →</Link>
                </div>              </div>
            ))}
          </div>
        )}
    </main>
  );
}
