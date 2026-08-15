import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { Handshake, PaperPlaneTilt } from "@phosphor-icons/react";

export default function EOI() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [employers, setEmployers] = useState([]);
  const [msg, setMsg] = useState("");
  const [hours, setHours] = useState(10);
  const [employerId, setEmployerId] = useState("");
  const [startDate, setStartDate] = useState("");
  const nav = useNavigate();

  const load = async () => {
    try {
      const r = await api.get("/eoi");
      setItems(r.data);
      if (user?.role === "talent") {
        // fetch employer list for targeted EOI: we hit /talent endpoint but need employers — quick user lookup via /users? — just query as talent
        // For now, we ask users to leave employer blank (open EOI) or paste an employer id received elsewhere.
      }
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/eoi", {
        employer_id: employerId || null, message: msg,
        proposed_hours_per_week: Number(hours), start_date: startDate,
      });
      toast.success("EOI submitted");
      setMsg(""); setHours(10); setEmployerId(""); setStartDate("");
      load();
    } catch (e) { toast.error(formatErr(e)); }
  };

  const accept = async (id) => {
    try {
      const r = await api.post(`/eoi/${id}/accept`, {});
      toast.success("EOI accepted — sign the contract");
      nav(`/engagement/${r.data.id}`);
    } catch (e) { toast.error(formatErr(e)); }
  };
  const withdraw = async (id) => {
    try { await api.post(`/eoi/${id}/withdraw`); toast.success("Withdrawn"); load(); }
    catch (e) { toast.error(formatErr(e)); }
  };

  const isTalent = user?.role === "talent";
  const isEmployer = user?.role === "employer";

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#6B21A8] mb-3">EXPRESSIONS OF INTEREST</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">
        {isTalent ? "Choose your next engagement." : "Talent wants to work with you."}
      </h1>
      <p className="text-neutral-600 max-w-2xl mb-10">
        {isTalent
          ? "Raise an EOI for any employer or leave it open to any. Work across multiple engagements & timezones — as long as your calendar allows."
          : "Review EOIs raised by talent. Accept to create a signed engagement automatically."}
      </p>

      <div className="grid lg:grid-cols-[1fr_1.4fr] gap-6">
        {isTalent && (
          <form onSubmit={submit} className="hard-border bg-white p-8 shadow-brutal h-fit">
            <div className="flex items-center gap-2 mb-4">
              <PaperPlaneTilt size={22} weight="duotone" color="#6B21A8"/>
              <h2 className="font-display font-extrabold text-2xl tracking-tight">Raise an EOI</h2>
            </div>
            <div className="mb-4">
              <label className="overline block mb-2">Employer ID (leave blank for open)</label>
              <input value={employerId} onChange={(e) => setEmployerId(e.target.value)}
                     data-testid={TID.eoiEmployer} placeholder="Optional — open to any"
                     className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono text-sm"/>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="overline block mb-2">Hours / week</label>
                <input data-testid={TID.eoiHours} type="number" min="1" value={hours}
                       onChange={(e) => setHours(e.target.value)}
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <div>
                <label className="overline block mb-2">Start date</label>
                <input value={startDate} onChange={(e) => setStartDate(e.target.value)}
                       placeholder="YYYY-MM-DD"
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono"/>
              </div>
            </div>
            <div className="mb-4">
              <label className="overline block mb-2">Message</label>
              <textarea data-testid={TID.eoiMessage} value={msg} onChange={(e) => setMsg(e.target.value)}
                        rows={5} required placeholder="What you bring to the table, timezone, availability…"
                        className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
            </div>
            <button type="submit" className="btn-primary w-full" data-testid={TID.eoiSubmit}>Submit EOI →</button>
          </form>
        )}

        <section className={`hard-border bg-white p-8 shadow-brutal ${!isTalent ? "lg:col-span-2" : ""}`}>
          <div className="flex items-center gap-2 mb-4">
            <Handshake size={22} weight="duotone" color="#6B21A8"/>
            <h2 className="font-display font-extrabold text-2xl tracking-tight">
              {isTalent ? "Your EOIs" : "Incoming EOIs"}
            </h2>
          </div>
          {items.length === 0 ? (
            <p className="text-neutral-500">Nothing here yet.</p>
          ) : (
            <div className="divide-y divide-black/10">
              {items.map((e) => (
                <div key={e.id} className="py-4 flex flex-col md:flex-row md:items-center gap-3 md:justify-between"
                     data-testid={TID.eoiRow(e.id)}>
                  <div className="min-w-0">
                    <p className="font-display font-extrabold text-lg tracking-tight">
                      {isTalent ? (e.employer_name || "Open to any employer") : e.talent_name}
                    </p>
                    <p className="text-sm text-neutral-600 truncate">{e.message}</p>
                    <p className="text-xs font-mono text-neutral-500 mt-1">
                      {e.proposed_hours_per_week}h/wk · start {e.start_date || "flexible"} · <span className="uppercase">{e.status}</span>
                    </p>
                  </div>
                  <div className="flex gap-2">
                    {isEmployer && e.status === "open" && (
                      <button onClick={() => accept(e.id)} className="btn-primary text-sm" data-testid={TID.eoiAccept(e.id)}>
                        Accept →
                      </button>
                    )}
                    {isTalent && e.status === "open" && (
                      <button onClick={() => withdraw(e.id)} className="btn-outline text-sm" data-testid={TID.eoiWithdraw(e.id)}>
                        Withdraw
                      </button>
                    )}
                    {e.engagement_id && (
                      <Link to={`/engagement/${e.engagement_id}`} className="btn-outline text-sm">Open engagement →</Link>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
