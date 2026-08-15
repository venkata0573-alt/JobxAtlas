import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { X, Lock, CheckCircle, BookmarkSimple } from "@phosphor-icons/react";

export default function SkillLanding() {
  const { slug } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [email, setEmail] = useState("");
  const [signedUp, setSignedUp] = useState(false);
  const [selected, setSelected] = useState(null);  // curated talent open in modal
  const [shortlisting, setShortlisting] = useState(false);
  const [shortlisted, setShortlisted] = useState(new Set());

  const isCombo = slug && slug.includes("-") && ["london","new-york","san-francisco","berlin","singapore","dubai","sydney","toronto","remote"]
    .some(c => slug.endsWith("-" + c));

  useEffect(() => {
    const endpoint = isCombo ? `/seo/hire-city/${slug}` : `/seo/hire/${slug}`;
    api.get(endpoint).then(r => setData(r.data)).catch(() => setData({ notFound: true }));
    // Load existing shortlist (employer only) so we can render toggled state
    if (user && user.role === "employer") {
      api.get("/shortlist").then(r => {
        setShortlisted(new Set((r.data.items || []).map(i => i.talent_id)));
      }).catch(() => {});
    }
  }, [slug, isCombo, user]);

  const toggleShortlist = async (t) => {
    if (!user) {
      toast.info("Sign in as an employer to save talent to your shortlist");
      return;
    }
    if (user.role !== "employer") {
      toast.error("Only employer accounts can shortlist talent");
      return;
    }
    setShortlisting(true);
    try {
      if (shortlisted.has(t.id)) {
        await api.delete(`/shortlist/${t.id}`);
        const next = new Set(shortlisted); next.delete(t.id); setShortlisted(next);
        toast.success(`${t.name} removed from shortlist`);
      } else {
        await api.post("/shortlist", {
          talent_id: t.id,
          talent_name: t.name,
          headline: t.profile?.headline || "",
          location: t.profile?.location || "",
          hourly_rate: t.profile?.hourly_rate || 0,
          skills: t.profile?.skills || [],
          context: slug,
          is_curated: !!t.curated,
        });
        const next = new Set(shortlisted); next.add(t.id); setShortlisted(next);
        toast.success(`${t.name} added to your shortlist`);
      }
    } catch (e) { toast.error(formatErr(e)); }
    finally { setShortlisting(false); }
  };

  const signup = async (e, kind) => {
    e.preventDefault();
    if (!email.trim()) return toast.error("Please enter your email");
    try {
      await api.post("/newsletter/signup", { email, kind, context: slug });
      setSignedUp(true); setEmail("");
      toast.success("You're on the list — we'll be in touch.");
    } catch (err) { toast.error(formatErr(err)); }
  };

  if (!data) return <div className="p-16 font-mono text-center">Loading…</div>;
  if (data.notFound) return <main className="p-16 text-center"><p className="font-mono">No such page.</p></main>;

  const heading = data.title;

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#6B21A8] mb-3">
        HIRE {data.keyword.toUpperCase()}{data.city_pretty ? ` · ${data.city_pretty.toUpperCase()}` : ""}
      </p>
      <h1 className="font-display font-black text-4xl md:text-5xl tracking-tight mb-4">{heading}</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">{data.description}</p>

      <div className="hard-border bg-white p-6 mb-10 shadow-brutal">
        <p className="text-sm">
          <strong>Why Job Atlas for {data.keyword}{data.city_pretty ? ` in ${data.city_pretty}` : ""}?</strong>{" "}
          Purchase hours in bulk, sign structured contracts, sync with Jira &amp; Asana, and pay a platform fee half of Upwork&apos;s.
          Every professional listed here is vetted and available under a 12-month platform-only engagement.
        </p>
      </div>

      {data.talent.length === 0 ? (
        <section className="hard-border bg-white p-10 text-center mb-10">
          <p className="font-display font-black text-2xl mb-2">Coming soon to {data.city_pretty || "this category"}</p>
          <p className="text-neutral-500 mb-6">Be first on the list. We&apos;ll notify you the moment vetted {data.keyword} join Job Atlas in your area.</p>
          {!signedUp ? (
            <form onSubmit={(e) => signup(e, "notify")} className="max-w-md mx-auto flex gap-2">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                     placeholder="you@company.com" required
                     className="flex-1 hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
              <button type="submit" className="btn-primary">Notify me</button>
            </form>
          ) : <p className="text-sm text-[#6B21A8] font-mono">You&apos;re on the list — we&apos;ll be in touch.</p>}
          <p className="text-xs text-neutral-500 mt-6">
            Or browse the <Link to="/browse" className="underline">full talent marketplace →</Link>
          </p>
        </section>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
          {data.talent.map(t => (
            <button
              key={t.id}
              onClick={() => setSelected(t)}
              className="text-left hard-border bg-white p-7 shadow-brutal-hover cursor-pointer group"
              data-testid={`curated-talent-card-${t.id}`}>
              <div className="flex items-center justify-between">
                <p className="overline text-[#6B21A8]">{t.profile?.location || data.city_pretty || "Global"}</p>
                {t.curated && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-mono text-[#6B21A8] uppercase tracking-widest">
                    <CheckCircle size={12} weight="fill"/> Vetted
                  </span>
                )}
              </div>
              <h3 className="font-display font-black text-2xl tracking-tight mt-1 group-hover:text-[#6B21A8] transition-colors">{t.name}</h3>
              <p className="text-neutral-600 text-sm mt-1">{t.profile?.headline || "Independent professional"}</p>
              <div className="flex flex-wrap gap-2 mt-3">
                {(t.profile?.skills || []).slice(0, 4).map(s => (
                  <span key={s} className="text-xs font-mono hard-border px-2 py-1 bg-neutral-50">{s}</span>
                ))}
              </div>
              <div className="flex justify-between items-baseline mt-5 pt-4 border-t border-black/10">
                <span className="text-sm font-mono">{t.profile?.years_experience || 0} yrs</span>
                <p className="font-display font-black text-xl">${t.profile?.hourly_rate || 0}<span className="text-xs text-neutral-500">/hr</span></p>
              </div>
              <p className="text-[11px] font-mono text-neutral-400 mt-3 inline-flex items-center gap-1">
                <Lock size={11} weight="fill"/> Tap to preview · contact unlocks after hours are purchased
              </p>
            </button>
          ))}
        </div>
      )}

      {/* Curated Talent Preview Modal */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => setSelected(null)}
          data-testid="curated-talent-modal">
          <div
            className="hard-border bg-white max-w-lg w-full p-8 shadow-brutal-lg relative"
            onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setSelected(null)}
              className="absolute top-4 right-4 text-neutral-400 hover:text-neutral-700"
              aria-label="Close"
              data-testid="close-curated-modal">
              <X size={20}/>
            </button>

            <div className="flex items-center justify-between mb-2">
              <p className="overline text-[#6B21A8]">{selected.profile?.location || "Global"}</p>
              {selected.curated && (
                <span className="inline-flex items-center gap-1 text-[10px] font-mono text-[#6B21A8] uppercase tracking-widest">
                  <CheckCircle size={12} weight="fill"/> Vetted talent
                </span>
              )}
            </div>
            <h3 className="font-display font-black text-3xl tracking-tight text-[#0B1B2B]">{selected.name}</h3>
            <p className="text-neutral-600 mt-1">{selected.profile?.headline || "Independent professional"}</p>

            <div className="grid grid-cols-3 gap-3 my-6 text-center">
              <div className="hard-border bg-[#F5F3FF] p-3">
                <p className="font-display font-black text-xl">${selected.profile?.hourly_rate || 0}</p>
                <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest mt-1">Per hour</p>
              </div>
              <div className="hard-border bg-[#F5F3FF] p-3">
                <p className="font-display font-black text-xl">{selected.profile?.years_experience || 0}</p>
                <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest mt-1">Yrs exp</p>
              </div>
              <div className="hard-border bg-[#F5F3FF] p-3">
                <p className="font-display font-black text-xl">{selected.profile?.available_hours_per_week || 20}</p>
                <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest mt-1">Hrs / wk</p>
              </div>
            </div>

            <p className="overline text-neutral-500 mb-2">Skills</p>
            <div className="flex flex-wrap gap-2 mb-6">
              {(selected.profile?.skills || []).map(s => (
                <span key={s} className="text-xs font-mono hard-border px-2 py-1 bg-white">{s}</span>
              ))}
            </div>

            <div className="hard-border bg-[#F5F3FF] p-4 mb-6">
              <p className="text-sm font-display font-extrabold text-[#0B1B2B] inline-flex items-center gap-2">
                <Lock size={16} weight="fill" color="#6B21A8"/> Contact details unlock after purchase
              </p>
              <p className="text-xs text-neutral-600 mt-2 leading-relaxed">
                To message <strong>{selected.name.split(" ")[0]}</strong> or any vetted talent on Job Atlas,
                purchase a bundle of hours. A 12-month exclusivity contract is auto-generated and both parties sign before contact
                information is revealed.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                to="/pricing"
                className="btn-primary text-sm flex-1 text-center"
                data-testid="buy-hours-to-unlock-btn">
                Buy hours to unlock →
              </Link>
              <button
                onClick={() => toggleShortlist(selected)}
                disabled={shortlisting}
                className={`text-sm flex-1 inline-flex items-center justify-center gap-2 hard-border px-4 py-3 font-semibold transition-colors
                  ${shortlisted.has(selected.id) ? "bg-[#0B1B2B] text-white border-[#0B1B2B]" : "bg-white text-[#0B1B2B] hover:bg-[#F5F3FF]"}`}
                data-testid="shortlist-btn">
                <BookmarkSimple size={16} weight={shortlisted.has(selected.id) ? "fill" : "regular"}/>
                {shortlisted.has(selected.id) ? "Shortlisted ✓" : "Shortlist for future hire"}
              </button>
              <button
                onClick={() => setSelected(null)}
                className="btn-outline text-sm sm:flex-none"
                data-testid="continue-browsing-btn">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Talent-side CTA */}
      <section className="hard-border bg-[#0B1B2B] text-white p-10 shadow-brutal grid md:grid-cols-[1.4fr_1fr] gap-8 items-center">
        <div>
          <p className="overline text-[#6B21A8] mb-3">ARE YOU A {data.keyword.toUpperCase()}?</p>
          <h2 className="font-display font-black text-3xl md:text-4xl tracking-tight mb-3">Get listed on Job Atlas.</h2>
          <p className="text-neutral-300 max-w-lg">
            Structured contracts, transparent commission, weekly payouts to your bank. Join a marketplace that treats independent
            {" "}{data.keyword}{data.city_pretty ? ` in ${data.city_pretty}` : ""} like the senior professionals they are.
          </p>
        </div>
        {!signedUp ? (
          <form onSubmit={(e) => signup(e, "get_listed")} className="hard-border bg-white p-5">
            <label className="overline block mb-2 text-[#0B1B2B]">Your email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="you@example.com" required
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] text-[#0B1B2B] mb-3"/>
            <button type="submit" className="btn-accent w-full">Get listed →</button>
            <p className="text-[10px] text-neutral-500 mt-2 font-mono">One email. No spam. Invitation to complete your profile.</p>
          </form>
        ) : (
          <div className="hard-border bg-[#6B21A8] p-6 text-[#0B1B2B]">
            <p className="font-display font-black text-xl">You&apos;re on the list ✓</p>
            <p className="text-sm mt-2">We&apos;ll email you an onboarding link within 24 hours.</p>
          </div>
        )}
      </section>
    </main>
  );
}
