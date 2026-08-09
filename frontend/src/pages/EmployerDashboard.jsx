import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import DashboardMetrics from "@/components/DashboardMetrics";
import { Coins, WarningOctagon } from "@phosphor-icons/react";

export default function EmployerDashboard() {
  const { user } = useAuth();
  const [engs, setEngs] = useState([]);
  const [talent, setTalent] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hours, setHours] = useState(5);
  const [scope, setScope] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [a, b, m] = await Promise.all([api.get("/engagements"), api.get("/talent"), api.get("/dashboard/metrics")]);
        setEngs(a.data); setTalent(b.data); setMetrics(m.data);
      } catch (e) { toast.error(formatErr(e)); }
    })();
  }, []);

  const createEngagement = async (e) => {
    e.preventDefault();
    if (!selected) return toast.error("Pick a talent first");
    try {
      const r = await api.post("/engagements", { talent_id: selected.id, hours: Number(hours), scope });
      toast.success("Engagement created — sign the contract");
      setEngs([r.data, ...engs]);
      setSelected(null); setScope(""); setHours(5);
    } catch (err) { toast.error(formatErr(err)); }
  };

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-6 flex-wrap gap-4">
        <div>
          <p className="overline text-[#002FA7] mb-3">EMPLOYER DASHBOARD</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Welcome, {user?.name?.split(" ")[0]}.</h1>
        </div>
        <Link to="/employer/purchase" className="btn-primary shadow-brutal shadow-brutal-hover">
          <span className="inline-flex items-center gap-2"><Coins weight="duotone" size={16}/> Buy more hours</span>
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 border-l border-t border-black/10 mb-10 hidden">
        <Stat k={user?.hours_balance ?? 0} label="Hours available"/>
        <Stat k={engs.length} label="Engagements"/>
        <Stat k={engs.filter(e=>e.status==="contract_signed"||e.status==="active").length} label="Active"/>
        <Stat k={talent.length} label="Talent on platform"/>
      </div>

      <div className="mb-10"><DashboardMetrics metrics={metrics} role="employer"/></div>

      <div className="grid lg:grid-cols-[1.4fr_1fr] gap-6">
        {/* Mix & Match — create engagement */}
        <section className="hard-border bg-white p-8 shadow-brutal">
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-1">Mix & match your team</h2>
          <p className="text-sm text-neutral-600 mb-6">Pick talent, allocate hours from your balance, and issue a signed contract.</p>

          <form onSubmit={createEngagement} className="space-y-5">
            <div>
              <p className="overline mb-2">1 · Select talent</p>
              {talent.length === 0 ? (
                <p className="text-sm text-neutral-500">No talent available yet.</p>
              ) : (
                <div className="grid sm:grid-cols-2 gap-2 max-h-72 overflow-auto">
                  {talent.map((t) => (
                    <button type="button" key={t.id} onClick={() => setSelected(t)}
                            className={`hard-border p-3 text-left ${selected?.id === t.id ? "bg-[#0A0A0A] text-white" : "bg-white"}`}>
                      <p className="font-display font-extrabold">{t.name}</p>
                      <p className="text-xs opacity-70">{t.profile?.headline || "—"}</p>
                      <p className="text-xs font-mono mt-1">${t.profile?.hourly_rate || 0}/hr · {t.profile?.years_experience || 0}y</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="overline mb-2">2 · Hours to allocate ({hours})</p>
              <input type="range" min="1" max={Math.max(1, user?.hours_balance ?? 0) || 100}
                     value={hours} onChange={(e) => setHours(e.target.value)} className="w-full"/>
              <p className="text-xs text-neutral-500 mt-1">Your balance: {user?.hours_balance ?? 0}h</p>
            </div>
            <div>
              <p className="overline mb-2">3 · Scope of work</p>
              <textarea value={scope} onChange={(e) => setScope(e.target.value)} required rows={3}
                        placeholder="What will they deliver?"
                        className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
            </div>
            <button type="submit" className="btn-primary">Create engagement →</button>
          </form>
        </section>

        {/* Engagements list */}
        <aside className="hard-border bg-white p-8 shadow-brutal">
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-4">Your engagements</h2>
          {engs.length === 0 ? (
            <p className="text-sm text-neutral-500">You haven&apos;t booked any talent yet.</p>
          ) : (
            <div className="divide-y divide-black/10">
              {engs.map((e) => (
                <div key={e.id} className="py-3 flex items-center justify-between gap-3" data-testid={TID.engagementRow(e.id)}>
                  <div>
                    <p className="font-display font-extrabold">{e.talent_name}</p>
                    <p className="text-xs text-neutral-500">{e.hours_allocated}h · {e.status.replace(/_/g, " ")}</p>
                  </div>
                  <Link to={`/engagement/${e.id}`} className="text-xs underline" data-testid={TID.contractOpen(e.id)}>Open →</Link>
                </div>
              ))}
            </div>
          )}
          <div className="hard-border bg-[#FDFCF0] p-4 mt-6">
            <div className="flex items-start gap-2">
              <WarningOctagon weight="fill" color="#FF0A0A" size={16} className="mt-0.5"/>
              <p className="text-xs leading-relaxed">Direct hiring outside TalentHub is prohibited for 12 months per engagement. All work must remain routed through the platform.</p>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}

function Stat({ k, label }) {
  return (
    <div className="p-8 border-r border-b border-black/10 bg-white">
      <div className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">{k}</div>
      <p className="overline text-neutral-500 mt-2">{label}</p>
    </div>
  );
}
