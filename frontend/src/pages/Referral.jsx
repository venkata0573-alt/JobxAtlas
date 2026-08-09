import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { toast } from "sonner";
import { Copy, Share } from "@phosphor-icons/react";

export default function Referral() {
  const [r, setR] = useState(null);
  const [code, setCode] = useState("");

  const load = async () => {
    try { const res = await api.get("/referrals/mine"); setR(res.data); }
    catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); }, []);

  const claim = async (e) => {
    e.preventDefault();
    try { await api.post("/referrals/claim", { code }); toast.success("Referral claimed"); setCode(""); load(); }
    catch (err) { toast.error(formatErr(err)); }
  };

  if (!r) return <div className="p-16 font-mono text-center">Loading…</div>;
  const link = `${window.location.origin}${r.share_url}`;

  return (
    <main className="max-w-4xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">REFERRALS</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">
        Bring a friend. Get 2% back.
      </h1>
      <p className="text-neutral-600 mb-10 max-w-2xl">
        {r.reward}. Credited automatically to your hours balance when your invitee makes their first purchase.
      </p>

      <section className="hard-border bg-white p-8 shadow-brutal mb-8">
        <p className="overline mb-3">Your referral code</p>
        <div className="flex items-center gap-3 mb-4">
          <p className="font-display font-extrabold text-4xl tracking-tight">{r.code}</p>
          <button onClick={() => { navigator.clipboard.writeText(r.code); toast.success("Copied"); }} className="hard-border p-2 hover:bg-[#002FA7] hover:text-white"><Copy size={16}/></button>
        </div>
        <div className="hard-border bg-[#F9F9F9] p-3 flex items-center justify-between gap-3">
          <span className="font-mono text-xs break-all">{link}</span>
          <div className="flex gap-2">
            <button onClick={() => { navigator.clipboard.writeText(link); toast.success("Link copied"); }} className="hard-border p-2 hover:bg-[#002FA7] hover:text-white"><Copy size={14}/></button>
            <button onClick={() => navigator.share?.({ title: "TalentHub", url: link })} className="hard-border p-2 hover:bg-[#002FA7] hover:text-white"><Share size={14}/></button>
          </div>
        </div>
        <p className="text-xs text-neutral-500 mt-4">Bonus hours earned so far: <strong>{r.total_bonus_hours}</strong></p>
      </section>

      <section className="hard-border bg-[#FDFCF0] p-8 shadow-brutal mb-8">
        <p className="overline mb-3">Got a code?</p>
        <form onSubmit={claim} className="flex flex-col md:flex-row gap-3">
          <input value={code} onChange={(e) => setCode(e.target.value)}
                 placeholder="TH-XXXXXX"
                 className="flex-1 hard-border px-3 py-3 bg-white font-mono focus:outline-none focus:border-[#002FA7]"/>
          <button type="submit" className="btn-primary">Apply</button>
        </form>
      </section>

      <section className="hard-border bg-white shadow-brutal overflow-x-auto">
        <div className="p-6 border-b border-black/10"><h2 className="font-display font-extrabold text-2xl tracking-tight">Your referrals</h2></div>
        {r.claims.length === 0 ? (
          <p className="p-8 text-sm text-neutral-500">No one has signed up with your code yet. Share it!</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-[#0A0A0A] text-white"><tr>{["Friend","Status","Bonus","When"].map(h => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr></thead>
            <tbody>
              {r.claims.map(c => (
                <tr key={c.id} className="border-t border-black/10">
                  <td className="px-4 py-3">{c.referred_name || c.referred_id.slice(0,8)}</td>
                  <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{c.status}</span></td>
                  <td className="px-4 py-3 font-mono">{c.bonus_hours}h</td>
                  <td className="px-4 py-3 font-mono text-xs">{String(c.claimed_at).slice(0,10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
