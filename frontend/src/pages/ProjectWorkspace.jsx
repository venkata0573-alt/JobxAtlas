import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  Kanban, ChartLineUp, Warning, GridFour, Receipt,
  CheckCircle, Circle, Play, ArrowLeft, Plus, FileText,
} from "@phosphor-icons/react";

const TABS = [
  { id: "phases",     label: "Phases",      Icon: Kanban },
  { id: "variance",   label: "Variance",    Icon: ChartLineUp },
  { id: "risks",      label: "Risks",       Icon: Warning },
  { id: "raci",       label: "RACI",        Icon: GridFour },
  { id: "milestones", label: "Milestones",  Icon: Receipt },
];

export default function ProjectWorkspace() {
  const { id } = useParams();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("phases");

  const load = async () => {
    try {
      const [w, a] = await Promise.all([
        api.get(`/projects/workspace/${id}`),
        api.get(`/projects/workspace/${id}/alerts`).catch(() => ({ data: { items: [] } })),
      ]);
      setData({ ...w.data, alerts: a.data?.items || [] });
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  // Stripe redirect handling: ?paid=<session_id>
  useEffect(() => {
    const sid = params.get("paid");
    if (!sid) return;
    (async () => {
      try {
        const r = await api.get(`/projects/milestone-payment/status/${sid}`);
        if (r.data?.payment_status === "paid") {
          toast.success("Payment received — milestone marked paid.");
          load();
        } else {
          toast.error("Payment not confirmed yet. Refresh in a minute.");
        }
      } catch (e) { toast.error(formatErr(e)); }
      finally {
        // Clear the param from the URL
        params.delete("paid");
        setParams(params, { replace: true });
      }
    })();
    // eslint-disable-next-line
  }, []);

  const canFinance = user?.role === "admin";  // finance/superadmin scopes checked server-side

  if (!data) {
    return <main className="max-w-7xl mx-auto p-16 text-center"><p className="font-mono text-neutral-500">Loading workspace…</p></main>;
  }

  const p = data.project;
  const r = data.rollups;
  const unreadAlerts = (data.alerts || []).filter((a) => !a.read);
  const isAdmin = user?.role === "admin";

  const dismissAlert = async (aid) => {
    try {
      await api.post(`/alerts/${aid}/read`);
      setData((d) => ({ ...d, alerts: (d.alerts || []).map((a) => a.id === aid ? { ...a, read: true } : a) }));
    } catch (e) { /* silent */ }
  };

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-12" data-testid="project-workspace">
      <Link to={isAdmin ? "/admin" : "/employer"} className="inline-flex items-center gap-1 text-xs font-mono text-neutral-500 hover:text-black mb-4">
        <ArrowLeft size={12}/> Back
      </Link>

      {unreadAlerts.length > 0 && (
        <div className="hard-border bg-[#FEF0F0] border-red-300 p-4 shadow-brutal mb-6" data-testid="variance-alerts-banner">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <p className="font-display font-extrabold text-lg tracking-tight text-red-800">
              ⚠︎ {unreadAlerts.length} variance breach{unreadAlerts.length === 1 ? "" : "es"} need your attention
            </p>
          </div>
          <div className="space-y-2 mt-3">
            {unreadAlerts.slice(0, 3).map((a) => (
              <div key={a.id} className="flex items-center justify-between gap-3 flex-wrap text-sm">
                <span className="font-mono">
                  {a.week_start} · Hours <b>{a.hours_variance_pct > 0 ? "+" : ""}{a.hours_variance_pct}%</b> · Cost <b>{a.cost_variance_pct > 0 ? "+" : ""}{a.cost_variance_pct}%</b>
                  {a.email_sent && <span className="ml-2 text-xs text-emerald-700">✓ sponsor emailed</span>}
                </span>
                <button onClick={() => dismissAlert(a.id)} className="hard-border px-2 py-1 text-xs bg-white" data-testid={`dismiss-alert-${a.id}`}>Dismiss</button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-start justify-between gap-4 flex-wrap mb-8">
        <div>
          <p className="overline text-[#C79A3B]">{p.industry?.toUpperCase()} · {p.duration_months} MONTHS</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mt-1">{p.company_name}</h1>
          <p className="text-sm text-neutral-500 mt-1 font-mono">{p.template_title}</p>
        </div>
        <span className={`hard-border px-4 py-2 text-xs font-mono uppercase tracking-widest ${p.status === "active" ? "bg-[#0B1B2B] text-[#C79A3B]" : "bg-neutral-200"}`}>
          {p.status}
        </span>
      </div>

      {/* Rollup grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        <div className="hard-border bg-white p-4 shadow-brutal" data-testid="rollup-budget">
          <p className="overline text-neutral-500 mb-1">Budget</p>
          <p className="font-display font-black text-2xl">${(r.total_budget / 1000).toFixed(0)}k</p>
          {isAdmin && p.total_talent_cost > 0 && (
            <p className="text-[10px] text-neutral-500 font-mono mt-1" data-testid="admin-team-cost">
              Team cost ${(p.total_talent_cost / 1000).toFixed(0)}k
            </p>
          )}
        </div>
        <div className="hard-border bg-white p-4 shadow-brutal" data-testid="rollup-billed">
          <p className="overline text-neutral-500 mb-1">Billed</p>
          <p className="font-display font-black text-2xl">${(r.billed / 1000).toFixed(0)}k</p>
        </div>
        <div className="hard-border bg-white p-4 shadow-brutal" data-testid="rollup-paid">
          <p className="overline text-neutral-500 mb-1">Paid</p>
          <p className="font-display font-black text-2xl">${(r.paid / 1000).toFixed(0)}k</p>
        </div>
        <div className={`hard-border p-4 shadow-brutal ${Math.abs(r.hours_variance_pct) > 10 ? "bg-[#FEF0F0] border-red-300" : "bg-white"}`} data-testid="rollup-hours-var">
          <p className="overline text-neutral-500 mb-1">Hours variance</p>
          <p className={`font-display font-black text-2xl ${r.hours_variance_pct > 0 ? "text-red-700" : "text-emerald-700"}`}>
            {r.hours_variance_pct > 0 ? "+" : ""}{r.hours_variance_pct}%
          </p>
        </div>
        {isAdmin && p.blended_margin_pct !== undefined ? (
          <div className="hard-border bg-[#0B1B2B] text-white p-4 shadow-brutal" data-testid="rollup-margin">
            <p className="overline text-[#C79A3B] mb-1">Job Atlas margin</p>
            <p className="font-display font-black text-2xl text-[#F0C260]">{p.blended_margin_pct}%</p>
            <p className="text-[10px] text-neutral-400 font-mono mt-1">${(p.total_margin / 1000).toFixed(0)}k gross</p>
          </div>
        ) : (
          <div className={`hard-border p-4 shadow-brutal ${Math.abs(r.cost_variance_pct) > 10 ? "bg-[#FEF0F0] border-red-300" : "bg-white"}`} data-testid="rollup-cost-var">
            <p className="overline text-neutral-500 mb-1">Cost variance</p>
            <p className={`font-display font-black text-2xl ${r.cost_variance_pct > 0 ? "text-red-700" : "text-emerald-700"}`}>
              {r.cost_variance_pct > 0 ? "+" : ""}{r.cost_variance_pct}%
            </p>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="hard-border inline-flex bg-white mb-6 overflow-x-auto max-w-full" data-testid="workspace-tabs">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} onClick={() => setTab(id)}
                  className={`px-5 py-3 border-r border-black last:border-r-0 flex items-center gap-2 font-display font-extrabold text-sm tracking-tight whitespace-nowrap ${tab === id ? "bg-[#0A0A0A] text-white" : "bg-white text-black"}`}
                  data-testid={`workspace-tab-${id}`}>
            <Icon size={16} weight="duotone"/> {label}
          </button>
        ))}
      </div>

      {tab === "phases"     && <PhasesTab project={p} onChange={load}/>}
      {tab === "variance"   && <VarianceTab project={p} variances={data.variances} onChange={load}/>}
      {tab === "risks"      && <RisksTab project={p} risks={data.risks} onChange={load}/>}
      {tab === "raci"       && <RaciTab project={p} onChange={load}/>}
      {tab === "milestones" && <MilestonesTab project={p} milestones={data.milestones} invoices={data.invoices} canFinance={canFinance} canPay={isAdmin || p.employer_id === user?.id} onChange={load}/>}
    </main>
  );
}

// ---------- Phases ----------
function PhasesTab({ project, onChange }) {
  const advance = async (phaseId, next) => {
    try {
      await api.patch(`/projects/workspace/${project.id}/phases/${phaseId}`, { status: next });
      toast.success(`Phase set to ${next.replace("_", " ")}`);
      onChange();
    } catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-5 gap-3" data-testid="phases-tab">
      {(project.phases || []).map((ph, idx) => {
        const isComplete = ph.status === "complete";
        const isActive = ph.status === "in_progress";
        return (
          <div key={ph.id}
               className={`hard-border p-5 shadow-brutal ${isComplete ? "bg-[#EDF7EE]" : isActive ? "bg-[#FDF6E3]" : "bg-white"}`}
               data-testid={`phase-card-${ph.id}`}>
            <div className="flex items-center gap-2 mb-2">
              {isComplete ? <CheckCircle size={18} weight="fill" color="#10B981"/> :
               isActive ? <Play size={18} weight="fill" color="#C79A3B"/> :
                          <Circle size={18} color="#999"/>}
              <p className="font-mono text-[10px] text-neutral-500 tracking-widest">PHASE {idx + 1}</p>
            </div>
            <h3 className="font-display font-extrabold text-lg tracking-tight">{ph.name}</h3>
            <p className="text-xs text-neutral-500 mt-2 font-mono uppercase">Gate</p>
            <p className="text-xs">{ph.gate}</p>
            <p className="text-xs text-neutral-500 mt-3 font-mono uppercase">Deliverables</p>
            <ul className="text-xs space-y-0.5 mt-1">
              {(ph.deliverables || []).map((d, i) => <li key={i}>· {d}</li>)}
            </ul>
            {ph.signed_off_by && (
              <p className="text-[10px] text-emerald-700 mt-3 font-mono">✓ signed by {ph.signed_off_by}</p>
            )}
            <div className="flex gap-1 mt-3">
              {!isActive && !isComplete && (
                <button onClick={() => advance(ph.id, "in_progress")}
                        className="btn-outline text-[10px] flex-1"
                        data-testid={`start-phase-${ph.id}`}>Start</button>
              )}
              {isActive && (
                <button onClick={() => advance(ph.id, "complete")}
                        className="btn-primary text-[10px] flex-1"
                        data-testid={`complete-phase-${ph.id}`}>Complete</button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------- Variance ----------
function VarianceTab({ project, variances, onChange }) {
  const [form, setForm] = useState({
    week_start: new Date().toISOString().slice(0, 10),
    planned_hours: 40, actual_hours: 40, planned_cost: 5000, actual_cost: 5000, notes: "",
  });

  const submit = async (e) => {
    e.preventDefault();
    try {
      const r = await api.post(`/projects/workspace/${project.id}/variances`, {
        ...form,
        planned_hours: Number(form.planned_hours),
        actual_hours: Number(form.actual_hours),
        planned_cost: Number(form.planned_cost),
        actual_cost: Number(form.actual_cost),
      });
      if (r.data?.alert) {
        toast.error(`⚠︎ Variance alert fired — sponsor notified`, { duration: 6000 });
      } else {
        toast.success("Variance logged");
      }
      onChange();
    } catch (err) { toast.error(formatErr(err)); }
  };

  return (
    <div className="space-y-6" data-testid="variance-tab">
      <form onSubmit={submit} className="hard-border bg-[#FAF9F6] p-5 space-y-3 shadow-brutal">
        <div className="flex items-center gap-2">
          <ChartLineUp size={18} weight="duotone" color="#C79A3B"/>
          <p className="font-display font-extrabold text-lg">Log this week&apos;s variance</p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <label className="text-xs">Week of
            <input type="date" required value={form.week_start} onChange={(e) => setForm({...form, week_start: e.target.value})}
                   className="hard-border px-2 py-2 text-sm w-full bg-white mt-1" data-testid="var-week"/>
          </label>
          <label className="text-xs">Planned hrs
            <input type="number" step="0.5" required value={form.planned_hours} onChange={(e) => setForm({...form, planned_hours: e.target.value})}
                   className="hard-border px-2 py-2 text-sm w-full bg-white mt-1" data-testid="var-plan-hrs"/>
          </label>
          <label className="text-xs">Actual hrs
            <input type="number" step="0.5" required value={form.actual_hours} onChange={(e) => setForm({...form, actual_hours: e.target.value})}
                   className="hard-border px-2 py-2 text-sm w-full bg-white mt-1" data-testid="var-act-hrs"/>
          </label>
          <label className="text-xs">Planned cost
            <input type="number" step="1" required value={form.planned_cost} onChange={(e) => setForm({...form, planned_cost: e.target.value})}
                   className="hard-border px-2 py-2 text-sm w-full bg-white mt-1" data-testid="var-plan-cost"/>
          </label>
          <label className="text-xs">Actual cost
            <input type="number" step="1" required value={form.actual_cost} onChange={(e) => setForm({...form, actual_cost: e.target.value})}
                   className="hard-border px-2 py-2 text-sm w-full bg-white mt-1" data-testid="var-act-cost"/>
          </label>
        </div>
        <textarea rows={2} placeholder="Notes (optional)…" value={form.notes} onChange={(e) => setForm({...form, notes: e.target.value})}
                  className="hard-border px-3 py-2 text-sm bg-white w-full" data-testid="var-notes"/>
        <button type="submit" className="btn-primary text-sm" data-testid="var-submit">Log variance →</button>
      </form>

      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>{[
              {k:"week",label:"Week"},{k:"plan-h",label:"Plan hrs"},{k:"act-h",label:"Act hrs"},
              {k:"hvar",label:"Δ% hrs"},{k:"plan-c",label:"Plan $"},{k:"act-c",label:"Act $"},
              {k:"cvar",label:"Δ% cost"},{k:"notes",label:"Notes"},
            ].map((c) => <th key={c.k} className="text-left px-4 py-3 overline">{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {variances.length === 0 ? (
              <tr><td colSpan="8" className="p-8 text-center text-neutral-500">No variance logs yet.</td></tr>
            ) : variances.map((v) => (
              <tr key={v.id} className="border-t border-black/10">
                <td className="px-4 py-3 font-mono text-xs">{v.week_start}</td>
                <td className="px-4 py-3 font-mono">{v.planned_hours}</td>
                <td className="px-4 py-3 font-mono">{v.actual_hours}</td>
                <td className={`px-4 py-3 font-mono font-bold ${v.hours_variance_pct > 10 ? "text-red-700" : v.hours_variance_pct < -10 ? "text-emerald-700" : ""}`}>
                  {v.hours_variance_pct > 0 ? "+" : ""}{v.hours_variance_pct}%
                </td>
                <td className="px-4 py-3 font-mono">${v.planned_cost}</td>
                <td className="px-4 py-3 font-mono">${v.actual_cost}</td>
                <td className={`px-4 py-3 font-mono font-bold ${v.cost_variance_pct > 10 ? "text-red-700" : v.cost_variance_pct < -10 ? "text-emerald-700" : ""}`}>
                  {v.cost_variance_pct > 0 ? "+" : ""}{v.cost_variance_pct}%
                </td>
                <td className="px-4 py-3 text-xs text-neutral-600">{v.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- Risks ----------
function RisksTab({ project, risks, onChange }) {
  const [form, setForm] = useState({
    title: "", description: "", likelihood: "M", impact: "M", mitigation: "", owner: "", status: "open",
  });

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/projects/workspace/${project.id}/risks`, form);
      setForm({ title: "", description: "", likelihood: "M", impact: "M", mitigation: "", owner: "", status: "open" });
      toast.success("Risk added");
      onChange();
    } catch (err) { toast.error(formatErr(err)); }
  };

  const updateStatus = async (r, next) => {
    try {
      await api.patch(`/projects/workspace/${project.id}/risks/${r.id}`, { ...r, status: next });
      toast.success(`Risk marked ${next}`);
      onChange();
    } catch (e) { toast.error(formatErr(e)); }
  };

  const cellColor = (score) => score >= 6 ? "bg-red-100 text-red-800" : score >= 3 ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800";

  return (
    <div className="space-y-6" data-testid="risks-tab">
      <form onSubmit={submit} className="hard-border bg-[#FAF9F6] p-5 space-y-3 shadow-brutal">
        <p className="font-display font-extrabold text-lg inline-flex items-center gap-2">
          <Warning size={18} weight="duotone" color="#C79A3B"/> Add a risk
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input required placeholder="Risk title" value={form.title} onChange={(e) => setForm({...form, title: e.target.value})}
                 className="hard-border px-3 py-2 text-sm bg-white md:col-span-2" data-testid="risk-title"/>
          <input placeholder="Owner" value={form.owner} onChange={(e) => setForm({...form, owner: e.target.value})}
                 className="hard-border px-3 py-2 text-sm bg-white" data-testid="risk-owner"/>
        </div>
        <textarea rows={2} placeholder="Description" value={form.description} onChange={(e) => setForm({...form, description: e.target.value})}
                  className="hard-border px-3 py-2 text-sm bg-white w-full" data-testid="risk-desc"/>
        <div className="grid grid-cols-3 gap-3">
          <label className="text-xs">Likelihood
            <select value={form.likelihood} onChange={(e) => setForm({...form, likelihood: e.target.value})}
                    className="hard-border px-2 py-2 text-sm w-full bg-white mt-1" data-testid="risk-lik">
              {["L","M","H"].map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </label>
          <label className="text-xs">Impact
            <select value={form.impact} onChange={(e) => setForm({...form, impact: e.target.value})}
                    className="hard-border px-2 py-2 text-sm w-full bg-white mt-1" data-testid="risk-imp">
              {["L","M","H"].map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </label>
          <label className="text-xs">Mitigation
            <input placeholder="Mitigation plan" value={form.mitigation} onChange={(e) => setForm({...form, mitigation: e.target.value})}
                   className="hard-border px-3 py-2 text-sm w-full bg-white mt-1" data-testid="risk-mit"/>
          </label>
        </div>
        <button type="submit" className="btn-primary text-sm inline-flex items-center gap-1" data-testid="risk-submit"><Plus size={12}/> Add risk</button>
      </form>

      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>{["Risk","Owner","L","I","Score","Status","Actions"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
          </thead>
          <tbody>
            {risks.length === 0 ? (
              <tr><td colSpan="7" className="p-8 text-center text-neutral-500">No risks logged.</td></tr>
            ) : risks.map((r) => (
              <tr key={r.id} className="border-t border-black/10 align-top" data-testid={`risk-row-${r.id}`}>
                <td className="px-4 py-3">
                  <p className="font-display font-bold">{r.title}</p>
                  <p className="text-xs text-neutral-500">{r.description}</p>
                  {r.mitigation && <p className="text-xs text-neutral-700 mt-1"><span className="font-mono uppercase text-[10px] mr-1">MIT:</span>{r.mitigation}</p>}
                </td>
                <td className="px-4 py-3 font-mono text-xs">{r.owner || "—"}</td>
                <td className="px-4 py-3 font-mono">{r.likelihood}</td>
                <td className="px-4 py-3 font-mono">{r.impact}</td>
                <td className={`px-4 py-3 font-mono font-bold`}>
                  <span className={`px-2 py-1 ${cellColor(r.score)}`}>{r.score}</span>
                </td>
                <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{r.status}</span></td>
                <td className="px-4 py-3">
                  {r.status !== "closed" && (
                    <div className="flex gap-1">
                      {r.status === "open" && (
                        <button onClick={() => updateStatus(r, "mitigated")} className="hard-border p-1 text-xs" data-testid={`risk-mitigate-${r.id}`}>Mitigate</button>
                      )}
                      <button onClick={() => updateStatus(r, "closed")} className="hard-border p-1 text-xs" data-testid={`risk-close-${r.id}`}>Close</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- RACI ----------
function RaciTab({ project, onChange }) {
  const [rows, setRows] = useState(project.raci || []);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setRows(project.raci || []); }, [project.id]);

  // Collect all assignee names from the current RACI + assigned_team so we render columns dynamically
  const assignees = useMemo(() => {
    const set = new Set();
    (project.assigned_team || []).forEach((s) => s.talent_name && set.add(s.talent_name));
    (project.raci || []).forEach((r) => Object.keys(r.assignments || {}).forEach((k) => set.add(k)));
    return Array.from(set);
  }, [project.id]);

  const cycle = (rowIdx, name) => {
    const order = ["", "R", "A", "C", "I"];
    setRows(rows.map((r, i) => {
      if (i !== rowIdx) return r;
      const cur = (r.assignments || {})[name] || "";
      const next = order[(order.indexOf(cur) + 1) % order.length];
      const clone = { ...(r.assignments || {}) };
      if (next) clone[name] = next; else delete clone[name];
      return { ...r, assignments: clone };
    }));
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/projects/workspace/${project.id}/raci`, { rows });
      toast.success("RACI saved");
      onChange();
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSaving(false); }
  };

  const cellColor = (v) => v === "R" ? "bg-[#0B1B2B] text-white" : v === "A" ? "bg-[#C79A3B] text-white" : v === "C" ? "bg-blue-100 text-blue-800" : v === "I" ? "bg-neutral-100 text-neutral-600" : "";

  return (
    <div className="space-y-4" data-testid="raci-tab">
      <p className="text-xs text-neutral-500 font-mono">Click a cell to cycle R → A → C → I → blank.</p>
      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>
              <th className="text-left px-4 py-3 overline">Activity</th>
              {assignees.map((a) => (
                <th key={a} className="text-left px-4 py-3 overline whitespace-nowrap">{a}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={assignees.length + 1} className="p-8 text-center text-neutral-500">No RACI seeded.</td></tr>
            ) : rows.map((r, idx) => (
              <tr key={idx} className="border-t border-black/10" data-testid={`raci-row-${idx}`}>
                <td className="px-4 py-3 font-display font-bold text-sm">{r.activity}</td>
                {assignees.map((name) => {
                  const v = (r.assignments || {})[name] || "";
                  return (
                    <td key={name} className="px-2 py-2">
                      <button onClick={() => cycle(idx, name)}
                              className={`hard-border w-10 h-10 font-display font-black text-sm ${cellColor(v)}`}
                              data-testid={`raci-cell-${idx}-${name}`}>
                        {v || "·"}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button onClick={save} disabled={saving} className="btn-primary text-sm" data-testid="raci-save">
        {saving ? "Saving…" : "Save RACI"}
      </button>
    </div>
  );
}

// ---------- Milestones ----------
function MilestonesTab({ project, milestones, invoices, canFinance, canPay, onChange }) {
  const [form, setForm] = useState({ name: "", percent: 10, due_date: "" });

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/projects/workspace/${project.id}/milestones`, {
        name: form.name, percent: Number(form.percent), due_date: form.due_date,
      });
      setForm({ name: "", percent: 10, due_date: "" });
      toast.success("Milestone added");
      onChange();
    } catch (err) { toast.error(formatErr(err)); }
  };

  const invoice = async (mid) => {
    try { await api.post(`/projects/workspace/${project.id}/milestones/${mid}/invoice`);
      toast.success("Invoice issued"); onChange();
    } catch (e) { toast.error(formatErr(e)); }
  };
  const paid = async (mid) => {
    try { await api.post(`/projects/workspace/${project.id}/milestones/${mid}/paid`);
      toast.success("Marked paid"); onChange();
    } catch (e) { toast.error(formatErr(e)); }
  };
  const payViaStripe = async (mid) => {
    try {
      const r = await api.post(`/projects/workspace/${project.id}/milestones/${mid}/checkout`, {
        origin_url: window.location.origin,
      });
      window.location.href = r.data.checkout_url;
    } catch (e) { toast.error(formatErr(e)); }
  };
  const downloadPdf = (invId) => {
    const base = process.env.REACT_APP_BACKEND_URL;
    window.open(`${base}/api/projects/workspace/${project.id}/invoices/${invId}/pdf`, "_blank");
  };

  return (
    <div className="space-y-6" data-testid="milestones-tab">
      <div className="hard-border bg-[#FDF6E3] p-5 shadow-brutal">
        <div className="flex items-center gap-2 mb-2">
          <Receipt size={18} weight="duotone" color="#C79A3B"/>
          <p className="font-display font-extrabold text-lg">Fixed-price milestone plan · 25% × 4</p>
        </div>
        <p className="text-xs text-neutral-700">Default plan: 25% at kickoff, 25% at each of two major deliverables, 25% at final sign-off. Add extra milestones below if scope demands more billing checkpoints.</p>
      </div>

      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>{["#","Milestone","%","Amount","Due","Status","Actions"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
          </thead>
          <tbody>
            {milestones.length === 0 ? (
              <tr><td colSpan="7" className="p-8 text-center text-neutral-500">No milestones.</td></tr>
            ) : milestones.map((m) => (
              <tr key={m.id} className="border-t border-black/10" data-testid={`milestone-row-${m.id}`}>
                <td className="px-4 py-3 font-mono">{m.sequence}</td>
                <td className="px-4 py-3 font-display font-bold">{m.name}</td>
                <td className="px-4 py-3 font-mono">{m.percent}%</td>
                <td className="px-4 py-3 font-mono font-bold">${(m.amount || 0).toLocaleString()}</td>
                <td className="px-4 py-3 font-mono text-xs">{m.due_date || "—"}</td>
                <td className="px-4 py-3">
                  <span className={`hard-border px-2 py-1 text-xs ${m.status === "paid" ? "bg-emerald-100" : m.status === "invoiced" ? "bg-amber-100" : ""}`}>
                    {m.status}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {canFinance && m.status === "pending" && (
                    <button onClick={() => invoice(m.id)} className="btn-outline text-xs inline-flex items-center gap-1 mr-1" data-testid={`invoice-${m.id}`}>
                      <FileText size={12}/> Issue invoice
                    </button>
                  )}
                  {canFinance && m.status === "invoiced" && (
                    <button onClick={() => paid(m.id)} className="btn-outline text-xs mr-1" data-testid={`paid-${m.id}`}>Mark paid</button>
                  )}
                  {canPay && m.status !== "paid" && (
                    <button onClick={() => payViaStripe(m.id)} className="btn-primary text-xs inline-flex items-center gap-1" data-testid={`pay-stripe-${m.id}`}>
                      💳 Pay ${((m.amount || 0) / 1000).toFixed(0)}k
                    </button>
                  )}
                  {m.invoice_id && (
                    <button onClick={() => downloadPdf(m.invoice_id)} className="hard-border p-1 text-xs bg-white hover:bg-[#FAF9F6] ml-1 inline-flex items-center gap-1" data-testid={`pdf-${m.invoice_id}`}>
                      <FileText size={12}/> PDF
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form onSubmit={submit} className="hard-border bg-[#FAF9F6] p-5 space-y-3">
        <p className="font-display font-extrabold text-lg">Add a custom milestone</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input required placeholder="Name" value={form.name} onChange={(e) => setForm({...form, name: e.target.value})}
                 className="hard-border px-3 py-2 text-sm bg-white" data-testid="milestone-name"/>
          <input required type="number" placeholder="% of total budget" min={1} max={100} value={form.percent} onChange={(e) => setForm({...form, percent: e.target.value})}
                 className="hard-border px-3 py-2 text-sm bg-white" data-testid="milestone-percent"/>
          <input type="date" value={form.due_date} onChange={(e) => setForm({...form, due_date: e.target.value})}
                 className="hard-border px-3 py-2 text-sm bg-white" data-testid="milestone-due"/>
        </div>
        <button type="submit" className="btn-primary text-sm" data-testid="milestone-submit">Add milestone</button>
      </form>

      {invoices.length > 0 && (
        <div>
          <p className="overline text-neutral-500 mb-2">INVOICE HISTORY</p>
          <div className="hard-border bg-white shadow-brutal">
            <table className="w-full text-sm">
              <thead className="bg-[#0A0A0A] text-white">
                <tr>{["Ref","Milestone","Amount","Status","Issued","Paid","PDF"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
              </thead>
              <tbody>
                {invoices.map((inv) => {
                  const m = milestones.find((x) => x.id === inv.milestone_id);
                  return (
                    <tr key={inv.id} className="border-t border-black/10">
                      <td className="px-4 py-3 font-mono">{inv.ref}</td>
                      <td className="px-4 py-3">{m?.name || "—"}</td>
                      <td className="px-4 py-3 font-mono font-bold">${inv.amount.toLocaleString()}</td>
                      <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{inv.status}</span></td>
                      <td className="px-4 py-3 font-mono text-xs">{new Date(inv.issued_at).toLocaleDateString()}</td>
                      <td className="px-4 py-3 font-mono text-xs">{inv.paid_at ? new Date(inv.paid_at).toLocaleDateString() : "—"}</td>
                      <td className="px-4 py-3">
                        <button onClick={() => downloadPdf(inv.id)} className="hard-border p-1 text-xs bg-white hover:bg-[#FAF9F6] inline-flex items-center gap-1" data-testid={`pdf-history-${inv.id}`}>
                          <FileText size={12}/> Download
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
