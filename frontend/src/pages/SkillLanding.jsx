import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";

export default function SkillLanding() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  useEffect(() => { api.get(`/seo/hire/${slug}`).then(r => setData(r.data)).catch(() => setData({ notFound: true })); }, [slug]);

  if (!data) return <div className="p-16 font-mono text-center">Loading…</div>;
  if (data.notFound) return <main className="p-16 text-center"><p className="font-mono">No such skill category.</p></main>;

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">HIRE · {data.keyword.toUpperCase()}</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">{data.title}</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">{data.description}</p>

      <div className="hard-border bg-[#FDFCF0] p-6 mb-10 shadow-brutal">
        <p className="text-sm">
          <strong>Why TalentHub for {data.keyword}?</strong> {" "}
          Purchase hours in bulk, sign structured contracts, sync with Jira &amp; Asana, and pay a platform fee half of Upwork&apos;s.
          Every {data.keyword.split(" ")[0]} on this list is vetted and available under a 12-month platform-only engagement.
        </p>
      </div>

      {data.talent.length === 0 ? (
        <div className="hard-border bg-white p-16 text-center">
          <p className="font-display font-extrabold text-2xl mb-2">No talent yet in this category</p>
          <p className="text-neutral-500">Browse the full marketplace instead — <Link to="/browse" className="underline">All talent →</Link></p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {data.talent.map(t => (
            <div key={t.id} className="hard-border bg-white p-7 shadow-brutal-hover">
              <p className="overline text-[#002FA7]">{t.profile?.location || "Global"}</p>
              <h3 className="font-display font-extrabold text-2xl tracking-tight mt-1">{t.name}</h3>
              <p className="text-neutral-600 text-sm mt-1">{t.profile?.headline || "Independent professional"}</p>
              <div className="flex flex-wrap gap-2 mt-3">
                {(t.profile?.skills || []).slice(0, 4).map(s => (
                  <span key={s} className="text-xs font-mono hard-border px-2 py-1 bg-[#F9F9F9]">{s}</span>
                ))}
              </div>
              <div className="flex justify-between items-baseline mt-5 pt-4 border-t border-black/10">
                <span className="text-sm font-mono">{t.profile?.years_experience || 0} yrs</span>
                <p className="font-display font-extrabold text-xl">${t.profile?.hourly_rate || 0}<span className="text-xs text-neutral-500">/hr</span></p>
              </div>
            </div>
          ))}
        </div>
      )}

      <section className="mt-16 text-center">
        <Link to="/register" className="btn-primary shadow-brutal">Start free →</Link>
      </section>
    </main>
  );
}
