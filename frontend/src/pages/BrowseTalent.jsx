import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";
import { MagnifyingGlass, Star } from "@phosphor-icons/react";

export default function BrowseTalent() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [skill, setSkill] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/talent", { params: { q, skill } });
      setItems(r.data);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-10">
        <div>
          <p className="overline text-[#002FA7] mb-3">BROWSE TALENT</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Vetted professionals.</h1>
        </div>
        <p className="hidden md:block text-sm text-neutral-500 max-w-xs">Contact details are unlocked after you purchase hours and both parties sign the contract.</p>
      </div>

      <div className="hard-border bg-white p-6 shadow-brutal grid md:grid-cols-[1fr_1fr_auto] gap-3 mb-10">
        <div className="flex items-center gap-2 hard-border px-3">
          <MagnifyingGlass size={16} />
          <input data-testid={TID.browseSearch} placeholder="Search by name or headline"
                 value={q} onChange={(e) => setQ(e.target.value)}
                 className="w-full py-3 focus:outline-none"/>
        </div>
        <input data-testid={TID.browseSkill} placeholder="Skill (e.g. Python, Figma)"
               value={skill} onChange={(e) => setSkill(e.target.value)}
               className="hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
        <button onClick={load} className="btn-primary">Filter</button>
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
              <div key={t.id} className={`hard-border bg-white p-7 shadow-brutal-hover ${i % 3 === 1 ? "md:translate-y-6" : ""}`}
                   data-testid={TID.browseTalentCard(t.id)}>
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <p className="overline text-[#002FA7]">{t.profile?.location || "Global"}</p>
                    <h3 className="font-display font-extrabold text-2xl tracking-tight mt-1">{t.name}</h3>
                    <p className="text-neutral-600 text-sm mt-1">{t.profile?.headline || "Independent professional"}</p>
                  </div>
                  <div className="text-right">
                    <p className="overline text-neutral-400">Rate</p>
                    <p className="font-display font-extrabold text-2xl">${t.profile?.hourly_rate || 0}<span className="text-sm text-neutral-500">/hr</span></p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mb-5">
                  {(t.profile?.skills || []).slice(0, 5).map((s) => (
                    <span key={s} className="text-xs font-mono hard-border px-2 py-1 bg-[#F9F9F9]">{s}</span>
                  ))}
                </div>
                <div className="flex items-center justify-between border-t border-black/10 pt-4">
                  <span className="text-sm flex items-center gap-1"><Star weight="fill" size={14}/> {t.profile?.years_experience || 0} yrs</span>
                  <Link to={`/employer`} className="btn-outline text-sm" data-testid={TID.hireBtn(t.id)}>View →</Link>
                </div>
              </div>
            ))}
          </div>
        )}
    </main>
  );
}
