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
  const [overview, setOverview] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hours, setHours] = useState(5);
  const [scope, setScope] = useState("");
  const [mode, setMode] = useState("remote");
  const [location, setLocation] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [transport, setTransport] = useState("employer");

  useEffect(() => {
    (async () => {
      try {
        const [a, b, m, o] = await Promise.all([
          api.get("/engagements"), api.get("/talent"),
          api.get("/dashboard/metrics"), api.get("/employer/overview"),
        ]);
        setEngs(a.data); setTalent(b.data); setMetrics(m.data); setOverview(o.data);
      } catch (e) { toast.error(formatErr(e)); }
    })();
  }, []);

  const createEngagement = async (e) => {
    e.preventDefault();
    if (!selected) return toast.error("Pick a talent first");
    if (mode !== "remote" && !location.trim()) return toast.error("Please add a location for on-site / hybrid work");
    try {
      const r = await api.post("/engagements", {
        talent_id: selected.id, hours: Number(hours), scope,
        mode, location, start_date: startDate, end_date: endDate, transport,
      });
      toast.success("Engagement created — sign the contract");
      setEngs([r.data, ...engs]);
      setSelected(null); setScope(""); setHours(5); setMode("remote"); setLocation("");
      setStartDate(""); setEndDate(""); setTransport("employer");
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

      {/* Resources & Finances */}
      {overview && (
        <div className="grid lg:grid-cols-[1.4fr_1fr] gap-6 mb-10">
          <section className="hard-border bg-white p-8 shadow-brutal">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display font-extrabold text-2xl tracking-tight">Your resources</h2>
              <span className="text-xs font-mono text-neutral-500">{overview.resources.length} people</span>
            </div>
            {overview.resources.length === 0 ? (
              <p className="text-neutral-500 text-sm">Nobody engaged yet. Use the panel below to build your first team.</p>
            ) : (
              <div className="divide-y divide-black/10">
                {overview.resources.map(r => (
                  <div key={r.talent_id} className="py-3 flex items-center justify-between gap-4">
                    <div>
                      <p className="font-display font-extrabold text-lg tracking-tight">{r.talent_name}</p>
                      <p className="text-xs text-neutral-500 font-mono">{r.engagements} engagements · {r.active} active</p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm">{r.hours_used}h / {r.hours_allocated}h</p>
                      <p className="text-xs text-neutral-500">used / allocated</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="hard-border bg-[#FDFCF0] p-8 shadow-brutal">
            <h2 className="font-display font-extrabold text-2xl tracking-tight mb-6">Your finances</h2>
            <dl className="space-y-3 font-mono text-sm">
              <Fin label="Total spent"                       v={`$${overview.finances.total_spent_usd.toLocaleString()}`}/>
              <Fin label="Hours purchased"                   v={`${overview.finances.hours_purchased}h`}/>
              <Fin label="Hours allocated to engagements"    v={`${overview.finances.hours_allocated}h`}/>
              <Fin label="Hours actually used"               v={`${overview.finances.hours_used}h`}/>
              <Fin label="Hours available"                   v={`${overview.finances.hours_balance}h`} bold/>
              <div className="h-px bg-black/10 my-2"/>
              <Fin label="Gross paid to talent (approved)"   v={`$${overview.finances.total_gross_paid_to_talent_usd.toLocaleString()}`}/>
              <Fin label="Active engagements"                v={overview.finances.active_engagements}/>
            </dl>
            <p className="text-xs text-neutral-500 mt-6">Talent are auto-paid the moment you approve a deliverable. Rate × approved-hours minus platform commission.</p>
          </section>
        </div>
      )}

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

            <div>
              <p className="overline mb-2">4 · Work mode</p>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "remote",  label: "Remote",  testid: TID.engModeRemote },
                  { id: "onsite",  label: "On-site", testid: TID.engModeOnsite },
                  { id: "hybrid",  label: "Hybrid",  testid: TID.engModeHybrid },
                ].map((m) => (
                  <button type="button" key={m.id} onClick={() => setMode(m.id)}
                          data-testid={m.testid}
                          className={`hard-border py-3 font-display font-extrabold text-sm ${mode === m.id ? "bg-[#0A0A0A] text-white" : "bg-white"}`}>
                    {m.label}
                  </button>
                ))}
              </div>
            </div>

            {mode !== "remote" && (
              <div className="hard-border bg-[#FDFCF0] p-5 space-y-4">
                <p className="overline text-[#FF0A0A]">On-site details (required)</p>
                <div>
                  <label className="text-xs text-neutral-600 block mb-1">Location / address</label>
                  <input value={location} onChange={(e) => setLocation(e.target.value)}
                         data-testid={TID.engLocation}
                         placeholder="Full address inc. city, country"
                         className="w-full hard-border px-3 py-3 bg-white focus:outline-none focus:border-[#002FA7]"/>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-neutral-600 block mb-1">Start date</label>
                    <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                           data-testid={TID.engStart}
                           className="w-full hard-border px-3 py-3 bg-white font-mono"/>
                  </div>
                  <div>
                    <label className="text-xs text-neutral-600 block mb-1">End date</label>
                    <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                           data-testid={TID.engEnd}
                           className="w-full hard-border px-3 py-3 bg-white font-mono"/>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-neutral-600 block mb-1">Transport arrangement</label>
                  <select value={transport} onChange={(e) => setTransport(e.target.value)}
                          data-testid={TID.engTransport}
                          className="w-full hard-border px-3 py-3 bg-white">
                    <option value="employer">Employer covers all transport</option>
                    <option value="mutual">Mutually agreed / split</option>
                    <option value="talent">Talent covers own transport</option>
                  </select>
                </div>
                <p className="text-xs text-neutral-600 leading-relaxed">
                  These fields appear in the contract. Both parties must acknowledge health &amp; safety and transport terms before signing.
                </p>
              </div>
            )}

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
              <p className="text-xs leading-relaxed">Direct hiring outside Job Atlas is prohibited for 12 months per engagement. All work must remain routed through the platform.</p>
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

function Fin({ label, v, bold }) {
  return (
    <div className={`flex justify-between ${bold ? "font-bold text-base" : ""}`}>
      <dt className="text-neutral-600">{label}</dt><dd>{v}</dd>
    </div>
  );
}
