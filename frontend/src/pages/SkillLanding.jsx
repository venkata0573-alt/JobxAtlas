import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { toast } from "sonner";

export default function SkillLanding() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [email, setEmail] = useState("");
  const [signedUp, setSignedUp] = useState(false);

  const isCombo = slug && slug.includes("-") && ["london","new-york","san-francisco","berlin","singapore","dubai","sydney","toronto","remote"]
    .some(c => slug.endsWith("-" + c));

  useEffect(() => {
    const endpoint = isCombo ? `/seo/hire-city/${slug}` : `/seo/hire/${slug}`;
    api.get(endpoint).then(r => setData(r.data)).catch(() => setData({ notFound: true }));
  }, [slug, isCombo]);

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
      <p className="overline text-[#C79A3B] mb-3">
        HIRE {data.keyword.toUpperCase()}{data.city_pretty ? ` · ${data.city_pretty.toUpperCase()}` : ""}
      </p>
      <h1 className="font-display font-black text-4xl md:text-5xl tracking-tight mb-4">{heading}</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">{data.description}</p>

      <div className="hard-border bg-white p-6 mb-10 shadow-brutal">
        <p className="text-sm">
          <strong>Why TalentHub for {data.keyword}{data.city_pretty ? ` in ${data.city_pretty}` : ""}?</strong>{" "}
          Purchase hours in bulk, sign structured contracts, sync with Jira &amp; Asana, and pay a platform fee half of Upwork&apos;s.
          Every professional listed here is vetted and available under a 12-month platform-only engagement.
        </p>
      </div>

      {data.talent.length === 0 ? (
        <section className="hard-border bg-white p-10 text-center mb-10">
          <p className="font-display font-black text-2xl mb-2">Coming soon to {data.city_pretty || "this category"}</p>
          <p className="text-neutral-500 mb-6">Be first on the list. We&apos;ll notify you the moment vetted {data.keyword} join TalentHub in your area.</p>
          {!signedUp ? (
            <form onSubmit={(e) => signup(e, "notify")} className="max-w-md mx-auto flex gap-2">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                     placeholder="you@company.com" required
                     className="flex-1 hard-border px-3 py-3 focus:outline-none focus:border-[#C79A3B]"/>
              <button type="submit" className="btn-primary">Notify me</button>
            </form>
          ) : <p className="text-sm text-[#C79A3B] font-mono">You&apos;re on the list — we&apos;ll be in touch.</p>}
          <p className="text-xs text-neutral-500 mt-6">
            Or browse the <Link to="/browse" className="underline">full talent marketplace →</Link>
          </p>
        </section>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
          {data.talent.map(t => (
            <div key={t.id} className="hard-border bg-white p-7 shadow-brutal-hover">
              <p className="overline text-[#C79A3B]">{t.profile?.location || data.city_pretty || "Global"}</p>
              <h3 className="font-display font-black text-2xl tracking-tight mt-1">{t.name}</h3>
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
            </div>
          ))}
        </div>
      )}

      {/* Talent-side CTA */}
      <section className="hard-border bg-[#0B1B2B] text-white p-10 shadow-brutal grid md:grid-cols-[1.4fr_1fr] gap-8 items-center">
        <div>
          <p className="overline text-[#C79A3B] mb-3">ARE YOU A {data.keyword.toUpperCase()}?</p>
          <h2 className="font-display font-black text-3xl md:text-4xl tracking-tight mb-3">Get listed on TalentHub.</h2>
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
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#C79A3B] text-[#0B1B2B] mb-3"/>
            <button type="submit" className="btn-accent w-full">Get listed →</button>
            <p className="text-[10px] text-neutral-500 mt-2 font-mono">One email. No spam. Invitation to complete your profile.</p>
          </form>
        ) : (
          <div className="hard-border bg-[#C79A3B] p-6 text-[#0B1B2B]">
            <p className="font-display font-black text-xl">You&apos;re on the list ✓</p>
            <p className="text-sm mt-2">We&apos;ll email you an onboarding link within 24 hours.</p>
          </div>
        )}
      </section>
    </main>
  );
}
