import React, { useEffect, useMemo, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import {
  CheckCircle, X, Star, Bank, ChatCircleText, CurrencyDollar, Play,
  UsersThree, ShieldCheck, PaintBrush, MagnifyingGlass, Plus, Trash,
  Briefcase, ArrowRight, SealCheck,
} from "@phosphor-icons/react";
import { Link } from "react-router-dom";

const TAB_CATALOG = [
  { id: "support",       label: "Support",         Icon: UsersThree,     scope: "support" },
  { id: "leads",         label: "Project Leads",   Icon: Briefcase,      scopes: ["support", "superadmin"] },
  { id: "verifications", label: "Verifications",   Icon: SealCheck,      scopes: ["moderation", "support"] },
  { id: "revisions",     label: "Revisions",       Icon: ChatCircleText, scope: "moderation" },
  { id: "bank",          label: "Bank Transfers",  Icon: Bank,           scope: "finance" },
  { id: "payouts",       label: "Payouts",         Icon: CurrencyDollar, scope: "finance" },
  { id: "reviews",       label: "Reviews",         Icon: Star,           scope: "moderation" },
  { id: "grievances",    label: "Grievances",      Icon: ChatCircleText, scopes: ["support", "moderation"] },
  { id: "customization", label: "Customization",   Icon: PaintBrush,     scope: "customization" },
  { id: "staff",         label: "Staff & Roles",   Icon: ShieldCheck,    scope: "superadmin" },
];

export default function Admin() {
  const { user } = useAuth();
  const [me, setMe] = useState(null);   // { effective_scopes, scopes_catalog }
  const [tab, setTab] = useState(null);
  const [data, setData] = useState({ bank: [], reviews: [], grievances: [], payouts: [] });
  const [range, setRange] = useState({
    start: new Date(Date.now() - 30*86400000).toISOString().slice(0,10),
    end:   new Date().toISOString().slice(0,10),
  });

  // Load admin identity + permissions on mount
  useEffect(() => {
    if (user?.role !== "admin") return;
    api.get("/admin/me").then((r) => {
      setMe(r.data);
      // Pick the first tab this admin can access
      const scopes = new Set(r.data.effective_scopes || []);
      const first = TAB_CATALOG.find((t) => canSee(t, scopes));
      setTab(first ? first.id : null);
    }).catch((e) => toast.error(formatErr(e)));
  }, [user]);

  const canSee = (t, scopeSet) => {
    if (t.scope) return scopeSet.has(t.scope);
    if (t.scopes) return t.scopes.some((s) => scopeSet.has(s));
    return false;
  };

  const scopeSet = useMemo(() => new Set(me?.effective_scopes || []), [me]);
  const visibleTabs = useMemo(() => TAB_CATALOG.filter((t) => canSee(t, scopeSet)), [scopeSet]);

  // Load per-tab data when tab changes
  useEffect(() => {
    if (!tab || !me) return;
    (async () => {
      try {
        if (tab === "bank") {
          const r = await api.get("/admin/bank-transfers").catch(() => ({ data: [] }));
          setData((d) => ({ ...d, bank: r.data || [] }));
        } else if (tab === "reviews") {
          const r = await api.get("/admin/reviews").catch(() => ({ data: [] }));
          setData((d) => ({ ...d, reviews: r.data || [] }));
        } else if (tab === "grievances") {
          const r = await api.get("/admin/grievances").catch(() => ({ data: [] }));
          setData((d) => ({ ...d, grievances: r.data || [] }));
        } else if (tab === "payouts") {
          const r = await api.get("/admin/payouts/runs").catch(() => ({ data: [] }));
          setData((d) => ({ ...d, payouts: r.data || [] }));
        }
      } catch (e) { toast.error(formatErr(e)); }
    })();
  }, [tab, me]);

  if (user?.role !== "admin") {
    return <main className="max-w-3xl mx-auto p-16 text-center"><p className="font-mono">Admins only.</p></main>;
  }
  if (!me) {
    return <main className="max-w-3xl mx-auto p-16 text-center"><p className="font-mono text-neutral-500">Loading admin console…</p></main>;
  }

  const act = async (url, msg) => {
    try { await api.post(url); toast.success(msg);
      // refresh whatever tab is active
      if (tab === "bank") setData((d) => ({ ...d, bank: d.bank.filter((x) => !url.includes(x.id)) }));
      else if (tab === "reviews") setData((d) => ({ ...d, reviews: d.reviews.filter((x) => !url.includes(x.id)) }));
      else if (tab === "grievances") setData((d) => ({ ...d, grievances: d.grievances.map((x) => url.includes(x.id) ? { ...x, status: "resolved" } : x) }));
    } catch (e) { toast.error(formatErr(e)); }
  };

  const runPayouts = async () => {
    try {
      const r = await api.post("/admin/payouts/run", {
        period_start: `${range.start}T00:00:00`, period_end: `${range.end}T23:59:59`, currency: "usd",
      });
      toast.success(`Generated payouts for ${r.data.run.count} talent · Net $${r.data.run.total_net}`);
      const rr = await api.get("/admin/payouts/runs");
      setData((d) => ({ ...d, payouts: rr.data || [] }));
    } catch (e) { toast.error(formatErr(e)); }
  };

  const count = (id) => (data[id] || []).length;

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <p className="overline text-[#6B21A8]">ADMIN CONSOLE</p>
        <div className="flex flex-wrap gap-1" data-testid="admin-scopes">
          {(me.effective_scopes || []).map((s) => (
            <span key={s} className="hard-border bg-[#0B1B2B] text-[#6B21A8] px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest">{s}</span>
          ))}
        </div>
      </div>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-8">
        {me.name} · <span className="text-neutral-500 text-3xl md:text-4xl">{visibleTabs.length} module{visibleTabs.length === 1 ? "" : "s"}</span>
      </h1>

      {visibleTabs.length === 0 ? (
        <p className="hard-border bg-[#F5F3FF] p-6 font-mono text-sm">
          Your admin account has no scopes granted yet. Ask a superadmin to grant you access.
        </p>
      ) : (
        <>
          <div className="hard-border inline-flex bg-white mb-8 overflow-x-auto max-w-full" data-testid="admin-tabs">
            {visibleTabs.map(({ id, label, Icon }) => (
              <button key={id} onClick={() => setTab(id)}
                      className={`px-5 py-3 border-r border-black last:border-r-0 flex items-center gap-2 font-display font-extrabold text-sm tracking-tight whitespace-nowrap ${tab === id ? "bg-[#0A0A0A] text-white" : "bg-white text-black"}`}
                      data-testid={`admin-tab-${id}`}>
                <Icon size={16} weight="duotone"/> {label}
                {["bank","reviews","grievances","payouts"].includes(id) && (
                  <span className="text-xs opacity-70">({count(id)})</span>
                )}
              </button>
            ))}
          </div>

          {tab === "support"       && <SupportPanel/>}
          {tab === "leads"         && <ProjectLeadsPanel scopes={me.effective_scopes}/>}
          {tab === "verifications" && <VerificationsPanel scopes={me.effective_scopes}/>}
          {tab === "revisions"     && <RevisionsPanel scopes={me.effective_scopes}/>}
          {tab === "staff"         && <StaffPanel selfId={me.id} scopes={me.scopes_catalog}/>}
          {tab === "customization" && <CustomizationPanel/>}

          {tab === "bank" && (
            <div className="hard-border bg-white shadow-brutal overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#0A0A0A] text-white"><tr>{["Reference","Employer","Amount","UTR","Status","Actions"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr></thead>
                <tbody>
                  {data.bank.length === 0 ? (
                    <tr><td colSpan="6" className="p-8 text-center text-neutral-500">No pending transfers.</td></tr>
                  ) : data.bank.map((p) => (
                    <tr key={p.id} className="border-t border-black/10">
                      <td className="px-4 py-3 font-mono">{p.reference}</td>
                      <td className="px-4 py-3">{p.user_id.slice(0,8)}…</td>
                      <td className="px-4 py-3 font-mono">₹{(p.amount/100).toLocaleString()} · {p.hours}h</td>
                      <td className="px-4 py-3 font-mono text-xs">{p.utr || "—"}</td>
                      <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{p.status}</span></td>
                      <td className="px-4 py-3 flex gap-2">
                        <button onClick={() => act(`/admin/bank-transfers/${p.id}/approve`, "Approved")} className="hard-border p-2 hover:bg-[#6B21A8] hover:text-white"><CheckCircle size={16}/></button>
                        <button onClick={() => act(`/admin/bank-transfers/${p.id}/reject`, "Rejected")} className="hard-border p-2 hover:bg-[#6B21A8] hover:text-white"><X size={16}/></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === "reviews" && (
            <div className="grid md:grid-cols-2 gap-4">
              {data.reviews.length === 0 ? <p className="text-neutral-500 col-span-2">No reviews pending moderation.</p> : data.reviews.map((r) => (
                <div key={r.id} className="hard-border bg-white p-5 shadow-brutal">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-display font-extrabold">{r.reviewer_name} <span className="text-xs text-neutral-500 font-normal">({r.reviewer_role})</span></p>
                    <div className="flex gap-0.5">{[1,2,3,4,5].map((n) => <Star key={n} size={14} weight={r.rating >= n ? "fill" : "regular"} color="#6B21A8"/>)}</div>
                  </div>
                  <p className="text-sm text-neutral-600 mb-3">{r.text || <em className="text-neutral-400">No comment.</em>}</p>
                  <div className="flex gap-2">
                    <button onClick={() => act(`/admin/reviews/${r.id}/approve`, "Approved")} className="btn-primary text-xs px-3 py-2">Approve</button>
                    <button onClick={() => act(`/admin/reviews/${r.id}/reject`, "Rejected")} className="btn-outline text-xs px-3 py-2">Reject</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "grievances" && (
            <div className="hard-border bg-white shadow-brutal overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#0A0A0A] text-white"><tr>{["Ref","Subject","From","Engagement","Status","Actions"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr></thead>
                <tbody>
                  {data.grievances.length === 0 ? (
                    <tr><td colSpan="6" className="p-8 text-center text-neutral-500">No grievances filed.</td></tr>
                  ) : data.grievances.map((g) => (
                    <tr key={g.id} className="border-t border-black/10 align-top">
                      <td className="px-4 py-3 font-mono text-xs">{g.id.slice(0,8)}</td>
                      <td className="px-4 py-3"><p className="font-medium">{g.subject}</p><p className="text-xs text-neutral-500 line-clamp-2">{g.description}</p></td>
                      <td className="px-4 py-3 font-mono text-xs">{g.contact_email}</td>
                      <td className="px-4 py-3 font-mono text-xs">{g.engagement_id?.slice(0,8) || "—"}</td>
                      <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{g.status}</span></td>
                      <td className="px-4 py-3">
                        {g.status !== "resolved" && (
                          <button onClick={() => act(`/admin/grievances/${g.id}/resolve`, "Resolved")} className="hard-border p-2 hover:bg-[#6B21A8] hover:text-white"><CheckCircle size={16}/></button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === "payouts" && (
            <>
              <section className="hard-border bg-[#F5F3FF] p-6 shadow-brutal mb-6">
                <div className="flex items-end justify-between flex-wrap gap-3">
                  <div>
                    <p className="overline text-[#6B21A8]">Generate payout run</p>
                    <p className="text-sm text-neutral-600 mt-1">Aggregates approved deliverables into per-talent payouts (rate × hours minus commission tier + multi-employer fee).</p>
                  </div>
                  <div className="flex items-end gap-3">
                    <div>
                      <label className="overline block mb-1">Start</label>
                      <input type="date" value={range.start} onChange={(e) => setRange({...range, start: e.target.value})}
                             className="hard-border px-3 py-2 font-mono bg-white"/>
                    </div>
                    <div>
                      <label className="overline block mb-1">End</label>
                      <input type="date" value={range.end} onChange={(e) => setRange({...range, end: e.target.value})}
                             className="hard-border px-3 py-2 font-mono bg-white"/>
                    </div>
                    <button onClick={runPayouts} className="btn-primary inline-flex items-center gap-2">
                      <Play size={14} weight="fill"/> Run
                    </button>
                  </div>
                </div>
              </section>
              <div className="hard-border bg-white shadow-brutal overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[#0A0A0A] text-white"><tr>{["Run","Period","Talents","Net","Status","Created"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr></thead>
                  <tbody>
                    {data.payouts.length === 0 ? (
                      <tr><td colSpan="6" className="p-8 text-center text-neutral-500">No payout runs yet.</td></tr>
                    ) : data.payouts.map((r) => (
                      <tr key={r.id} className="border-t border-black/10">
                        <td className="px-4 py-3 font-mono text-xs">{r.id.slice(0,8)}</td>
                        <td className="px-4 py-3 font-mono text-xs">{String(r.period_start).slice(0,10)} → {String(r.period_end).slice(0,10)}</td>
                        <td className="px-4 py-3 font-mono">{r.count}</td>
                        <td className="px-4 py-3 font-mono font-bold">${r.total_net?.toFixed?.(2) ?? r.total_net}</td>
                        <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{r.status}</span></td>
                        <td className="px-4 py-3 font-mono text-xs">{new Date(r.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </main>
  );
}

// ---------- Support panel ----------
function SupportPanel() {
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [users, setUsers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState("");
  const [hoursAdj, setHoursAdj] = useState(0);
  const [reason, setReason] = useState("");

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (role) params.set("role", role);
      const r = await api.get(`/admin/users?${params.toString()}`);
      setUsers(r.data.items || []);
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const openUser = async (u) => {
    setSelected(u.id); setDetail(null);
    try {
      const r = await api.get(`/admin/users/${u.id}`);
      setDetail(r.data);
    } catch (e) { toast.error(formatErr(e)); }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    try {
      const r = await api.post(`/admin/users/${selected}/notes`, { text: note });
      setDetail((d) => ({ ...d, notes: [r.data, ...(d.notes || [])] }));
      setNote(""); toast.success("Note added");
    } catch (e) { toast.error(formatErr(e)); }
  };

  const adjustHours = async () => {
    if (!hoursAdj) return;
    try {
      await api.post(`/admin/users/${selected}/adjust`, { hours_delta: Number(hoursAdj), reason });
      toast.success(`Adjusted by ${hoursAdj}h`);
      setHoursAdj(0); setReason("");
      const r = await api.get(`/admin/users/${selected}`);
      setDetail(r.data);
    } catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <div className="grid lg:grid-cols-[1fr_1.4fr] gap-6">
      <div className="hard-border bg-white shadow-brutal p-5" data-testid="support-list">
        <div className="flex gap-2 mb-3">
          <div className="relative flex-1">
            <MagnifyingGlass size={14} className="absolute top-3 left-2 text-neutral-400"/>
            <input value={q} onChange={(e) => setQ(e.target.value)}
                   onKeyDown={(e) => e.key === "Enter" && load()}
                   placeholder="Search by name, email, company"
                   className="hard-border pl-7 pr-3 py-2 text-sm w-full"
                   data-testid="support-search"/>
          </div>
          <select value={role} onChange={(e) => setRole(e.target.value)}
                  className="hard-border px-2 py-2 text-sm bg-white"
                  data-testid="support-role">
            <option value="">All roles</option>
            <option value="talent">Talent</option>
            <option value="employer">Employer</option>
            <option value="admin">Admin</option>
          </select>
          <button onClick={load} className="btn-primary text-xs px-3 py-2" data-testid="support-search-btn">Search</button>
        </div>
        <div className="divide-y divide-black/10 max-h-[560px] overflow-y-auto">
          {users.length === 0 ? <p className="text-neutral-500 text-sm py-6 text-center">No users found.</p>
          : users.map((u) => (
            <button key={u.id} onClick={() => openUser(u)}
                    className={`w-full text-left py-3 px-2 hover:bg-[#F5F3FF] ${selected === u.id ? "bg-[#F5F3FF]" : ""}`}
                    data-testid={`support-user-${u.id}`}>
              <div className="flex justify-between gap-2">
                <p className="font-display font-bold text-sm truncate">{u.name}</p>
                <span className="text-[10px] font-mono uppercase text-[#6B21A8]">{u.role}</span>
              </div>
              <p className="text-xs text-neutral-500 truncate">{u.email}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="hard-border bg-white shadow-brutal p-5">
        {!detail ? (
          <p className="text-neutral-500 text-sm">Select a user to see their history.</p>
        ) : (
          <div className="space-y-4" data-testid="support-detail">
            <div>
              <p className="overline text-[#6B21A8]">{detail.user.role.toUpperCase()}</p>
              <p className="font-display font-extrabold text-2xl tracking-tight">{detail.user.name}</p>
              <p className="text-xs text-neutral-500 font-mono">{detail.user.email}</p>
              <p className="text-xs text-neutral-500 mt-2">
                {detail.user.hours_balance || 0}h in wallet · {detail.engagements.length} engagements · {detail.eois.length} EOIs · {detail.payments.length} payments
              </p>
            </div>

            <div className="hard-border bg-[#F5F3FF] p-3">
              <p className="overline mb-2">Adjust hours (goodwill)</p>
              <div className="flex gap-2">
                <input type="number" value={hoursAdj} onChange={(e) => setHoursAdj(e.target.value)}
                       placeholder="e.g. 5 or -2" className="hard-border px-2 py-1 text-sm w-24"
                       data-testid="support-hours-adj"/>
                <input value={reason} onChange={(e) => setReason(e.target.value)}
                       placeholder="Reason" className="hard-border px-2 py-1 text-sm flex-1"
                       data-testid="support-reason"/>
                <button onClick={adjustHours} className="btn-outline text-xs px-3" data-testid="support-adjust-btn">Apply</button>
              </div>
            </div>

            <div>
              <p className="overline mb-2">Support notes ({detail.notes.length})</p>
              <div className="flex gap-2 mb-2">
                <input value={note} onChange={(e) => setNote(e.target.value)}
                       placeholder="Log a support interaction…" className="hard-border px-3 py-2 text-sm flex-1"
                       data-testid="support-note-input"/>
                <button onClick={addNote} className="btn-primary text-xs px-3" data-testid="support-add-note">Add</button>
              </div>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {detail.notes.map((n) => (
                  <div key={n.id} className="text-xs text-neutral-700 hard-border bg-white p-2">
                    <span className="font-mono text-neutral-400 text-[10px]">{new Date(n.created_at).toLocaleString()} · {n.author_name}</span>
                    <p>{n.text}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="overline mb-2">Recent engagements</p>
              {detail.engagements.slice(0, 5).map((e) => (
                <p key={e.id} className="text-xs font-mono py-1 border-b border-black/5">
                  {e.employer_name} ↔ {e.talent_name} · {e.hours_allocated}h · {e.status}
                </p>
              ))}
              {detail.engagements.length === 0 && <p className="text-xs text-neutral-400">None yet.</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- Staff & Roles panel ----------
function StaffPanel({ selfId, scopes }) {
  const [staff, setStaff] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ email: "", name: "", password: "", admin_permissions: ["support"] });

  const load = async () => {
    try { const r = await api.get("/admin/staff"); setStaff(r.data.staff || []); }
    catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); }, []);

  const toggleScope = (s) => {
    const set = new Set(form.admin_permissions);
    if (set.has(s)) set.delete(s); else set.add(s);
    setForm({ ...form, admin_permissions: Array.from(set) });
  };

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/admin/staff", form);
      toast.success("Staff added");
      setShowAdd(false);
      setForm({ email: "", name: "", password: "", admin_permissions: ["support"] });
      load();
    } catch (err) { toast.error(formatErr(err)); }
  };

  const updateScopes = async (id, current, scope) => {
    const set = new Set(current);
    if (set.has(scope)) set.delete(scope); else set.add(scope);
    try {
      await api.patch(`/admin/staff/${id}`, { admin_permissions: Array.from(set) });
      toast.success("Updated");
      load();
    } catch (e) { toast.error(formatErr(e)); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this admin?")) return;
    try { await api.delete(`/admin/staff/${id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <div className="space-y-6" data-testid="staff-panel">
      <div className="flex items-center justify-between">
        <div>
          <p className="overline text-[#6B21A8]">STAFF & PERMISSIONS</p>
          <h2 className="font-display font-extrabold text-2xl">{staff.length} admin{staff.length === 1 ? "" : "s"}</h2>
        </div>
        <button onClick={() => setShowAdd((v) => !v)} className="btn-primary text-sm inline-flex items-center gap-1" data-testid="add-staff-toggle">
          <Plus size={14} weight="bold"/> {showAdd ? "Cancel" : "Add staff"}
        </button>
      </div>

      {showAdd && (
        <form onSubmit={create} className="hard-border bg-[#F5F3FF] p-5 space-y-3" data-testid="add-staff-form">
          <div className="grid md:grid-cols-3 gap-3">
            <input required placeholder="Name" value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} className="hard-border px-3 py-2 text-sm bg-white" data-testid="staff-name"/>
            <input required type="email" placeholder="Email" value={form.email} onChange={(e) => setForm({...form, email: e.target.value})} className="hard-border px-3 py-2 text-sm bg-white" data-testid="staff-email"/>
            <input required type="password" placeholder="Temp password" value={form.password} onChange={(e) => setForm({...form, password: e.target.value})} className="hard-border px-3 py-2 text-sm bg-white" data-testid="staff-password"/>
          </div>
          <div>
            <p className="overline mb-2">Grant scopes</p>
            <div className="flex flex-wrap gap-2">
              {scopes.map((s) => {
                const on = form.admin_permissions.includes(s.id);
                return (
                  <button type="button" key={s.id} onClick={() => toggleScope(s.id)}
                          className={`hard-border px-3 py-2 text-xs ${on ? "bg-[#0B1B2B] text-white" : "bg-white"}`}
                          data-testid={`new-scope-${s.id}`}>
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
          <button type="submit" className="btn-primary text-sm" data-testid="create-staff">Create admin</button>
        </form>
      )}

      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>
              <th className="text-left px-4 py-3 overline">Name</th>
              <th className="text-left px-4 py-3 overline">Email</th>
              <th className="text-left px-4 py-3 overline">Scopes</th>
              <th className="text-left px-4 py-3 overline">Actions</th>
            </tr>
          </thead>
          <tbody>
            {staff.map((s) => (
              <tr key={s.id} className="border-t border-black/10 align-top" data-testid={`staff-row-${s.id}`}>
                <td className="px-4 py-3 font-display font-bold">{s.name}{s.id === selfId && <span className="text-xs text-[#6B21A8] ml-2">(you)</span>}</td>
                <td className="px-4 py-3 font-mono text-xs">{s.email}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {scopes.map((sc) => {
                      const on = (s.admin_permissions || []).includes(sc.id);
                      return (
                        <button key={sc.id} onClick={() => updateScopes(s.id, s.admin_permissions || [], sc.id)}
                                className={`hard-border px-2 py-1 text-[10px] font-mono uppercase tracking-widest ${on ? "bg-[#6B21A8] text-white" : "bg-white text-neutral-500"}`}
                                data-testid={`scope-${s.id}-${sc.id}`}>
                          {sc.id}
                        </button>
                      );
                    })}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {s.id !== selfId && (
                    <button onClick={() => del(s.id)} className="hard-border p-2 hover:bg-[#6B21A8] hover:text-white" data-testid={`delete-staff-${s.id}`}>
                      <Trash size={14}/>
                    </button>
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

// ---------- Customization panel ----------
function CustomizationPanel() {
  const [doc, setDoc] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/admin/customization").then((r) => setDoc(r.data)).catch((e) => toast.error(formatErr(e)));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put("/admin/customization", {
        hero_headline: doc.hero_headline, hero_subline: doc.hero_subline,
        cta_primary_label: doc.cta_primary_label, cta_secondary_label: doc.cta_secondary_label,
        features: doc.features, support_email: doc.support_email, support_hours: doc.support_hours,
      });
      setDoc(r.data);
      toast.success("Customization saved");
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSaving(false); }
  };

  if (!doc) return <p className="text-neutral-500">Loading…</p>;

  const setField = (k, v) => setDoc({ ...doc, [k]: v });
  const setFeature = (k, v) => setDoc({ ...doc, features: { ...(doc.features || {}), [k]: v } });

  return (
    <div className="space-y-6" data-testid="customization-panel">
      <div>
        <p className="overline text-[#6B21A8]">SITE CUSTOMIZATION</p>
        <h2 className="font-display font-extrabold text-2xl">Landing content & feature flags</h2>
        <p className="text-xs text-neutral-500 mt-1">These fields drive the public marketing surface. Changes go live on save.</p>
      </div>

      <div className="hard-border bg-white p-5 space-y-4">
        <div>
          <label className="overline block mb-1">Hero headline</label>
          <input value={doc.hero_headline || ""} onChange={(e) => setField("hero_headline", e.target.value)}
                 className="hard-border px-3 py-2 text-sm w-full" data-testid="cust-hero-headline"/>
        </div>
        <div>
          <label className="overline block mb-1">Hero subline</label>
          <textarea rows={2} value={doc.hero_subline || ""} onChange={(e) => setField("hero_subline", e.target.value)}
                    className="hard-border px-3 py-2 text-sm w-full" data-testid="cust-hero-subline"/>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="overline block mb-1">Primary CTA</label>
            <input value={doc.cta_primary_label || ""} onChange={(e) => setField("cta_primary_label", e.target.value)}
                   className="hard-border px-3 py-2 text-sm w-full" data-testid="cust-cta-primary"/>
          </div>
          <div>
            <label className="overline block mb-1">Secondary CTA</label>
            <input value={doc.cta_secondary_label || ""} onChange={(e) => setField("cta_secondary_label", e.target.value)}
                   className="hard-border px-3 py-2 text-sm w-full" data-testid="cust-cta-secondary"/>
          </div>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="overline block mb-1">Support email</label>
            <input value={doc.support_email || ""} onChange={(e) => setField("support_email", e.target.value)}
                   className="hard-border px-3 py-2 text-sm w-full" data-testid="cust-support-email"/>
          </div>
          <div>
            <label className="overline block mb-1">Support hours</label>
            <input value={doc.support_hours || ""} onChange={(e) => setField("support_hours", e.target.value)}
                   className="hard-border px-3 py-2 text-sm w-full" data-testid="cust-support-hours"/>
          </div>
        </div>
        <div>
          <p className="overline mb-2">Feature flags</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(doc.features || {}).map(([k, v]) => (
              <button key={k} onClick={() => setFeature(k, !v)}
                      className={`hard-border px-3 py-2 text-xs ${v ? "bg-[#6B21A8] text-white" : "bg-white text-neutral-500"}`}
                      data-testid={`cust-flag-${k}`}>
                {v ? "ON" : "OFF"} · {k}
              </button>
            ))}
          </div>
        </div>
        <button onClick={save} disabled={saving} className="btn-primary text-sm" data-testid="cust-save">
          {saving ? "Saving…" : "Save customization"}
        </button>
      </div>
    </div>
  );
}

// ---------- Project Leads panel ----------
function ProjectLeadsPanel({ scopes }) {
  const [leads, setLeads] = useState([]);
  const canConvert = (scopes || []).includes("superadmin");

  const load = async () => {
    try { const r = await api.get("/admin/project-leads"); setLeads(r.data.items || []); }
    catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); }, []);

  const convert = async (id) => {
    try {
      const r = await api.post(`/admin/project-leads/${id}/convert`, { currency: "usd" });
      toast.success("Lead converted — workspace ready");
      // Update local list
      setLeads((prev) => prev.map((l) => l.id === id ? { ...l, status: "converted", converted_project_id: r.data.project.id } : l));
    } catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <div className="space-y-4" data-testid="project-leads-panel">
      <div>
        <p className="overline text-[#6B21A8]">PROJECT LEADS</p>
        <h2 className="font-display font-extrabold text-2xl">{leads.length} scoping request{leads.length === 1 ? "" : "s"}</h2>
        <p className="text-xs text-neutral-500 mt-1">Convert a lead into a full delivery workspace with PMI phases, variance tracking, risk register, RACI and 25% milestone billing.</p>
      </div>
      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>{["Company","Template","Duration","Est. Total","Status","Action"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
          </thead>
          <tbody>
            {leads.length === 0 ? (
              <tr><td colSpan="6" className="p-8 text-center text-neutral-500">No project leads yet.</td></tr>
            ) : leads.map((l) => (
              <tr key={l.id} className="border-t border-black/10 align-top" data-testid={`lead-row-${l.id}`}>
                <td className="px-4 py-3">
                  <p className="font-display font-bold">{l.company_name}</p>
                  <p className="text-xs text-neutral-500">{l.contact_name} · <span className="font-mono">{l.contact_email}</span></p>
                </td>
                <td className="px-4 py-3">
                  <p className="text-xs font-mono">{l.template_title}</p>
                  <p className="text-[10px] text-neutral-500 uppercase">{l.industry}</p>
                </td>
                <td className="px-4 py-3 font-mono text-xs">{l.duration_months} mo</td>
                <td className="px-4 py-3 font-mono">${((l.estimated_total_cost || 0) / 1000).toFixed(0)}k</td>
                <td className="px-4 py-3">
                  <span className={`hard-border px-2 py-1 text-xs ${l.status === "converted" ? "bg-[#0B1B2B] text-[#6B21A8]" : ""}`}>{l.status}</span>
                </td>
                <td className="px-4 py-3">
                  {l.converted_project_id ? (
                    <Link to={`/projects/${l.converted_project_id}/workspace`}
                          className="btn-outline text-xs inline-flex items-center gap-1"
                          data-testid={`open-workspace-${l.id}`}>
                      Open workspace <ArrowRight size={12}/>
                    </Link>
                  ) : canConvert ? (
                    <button onClick={() => convert(l.id)}
                            className="btn-primary text-xs inline-flex items-center gap-1"
                            data-testid={`convert-lead-${l.id}`}>
                      Convert → project
                    </button>
                  ) : (
                    <span className="text-xs text-neutral-400">Superadmin only</span>
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



// ---------- Verifications panel ----------
function VerificationsPanel({ scopes }) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("pending");
  const canDecide = (scopes || []).includes("moderation") || (scopes || []).includes("superadmin");

  const load = async () => {
    try {
      const r = await api.get(`/admin/verifications-with-refs?status=${status}`);
      setItems(r.data.items || []);
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);

  const decide = async (uid, action) => {
    const notes = action === "reject"
      ? window.prompt("Rejection reason (visible to the user):")
      : window.prompt("Approval notes (optional):") || "";
    if (action === "reject" && !notes) return;
    try {
      const r = await api.post(`/admin/verifications/${uid}/${action}`, { notes });
      if (r.data.perks_granted?.hours_credited) {
        toast.success(`Approved — 10 discovery hours credited + hero placement enabled`);
      } else {
        toast.success(action === "approve" ? "Approved" : "Rejected");
      }
      load();
    } catch (e) { toast.error(formatErr(e)); }
  };

  const chipColor = (kind) => ({
    yes:     "bg-emerald-100 text-emerald-800 border-emerald-400",
    partial: "bg-amber-100 text-amber-800 border-amber-400",
    no:      "bg-red-100 text-red-800 border-red-400",
    pending: "bg-neutral-100 text-neutral-600 border-neutral-300",
  }[kind]);

  return (
    <div className="space-y-4" data-testid="verifications-panel">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="overline text-[#6B21A8]">TRUST & SAFETY</p>
          <h2 className="font-display font-extrabold text-2xl">{items.length} · {status}</h2>
        </div>
        <div className="flex gap-1">
          {["pending", "verified", "rejected"].map((s) => (
            <button key={s} onClick={() => setStatus(s)}
                    className={`hard-border px-3 py-2 text-xs ${status === s ? "bg-[#0B1B2B] text-white" : "bg-white"}`}
                    data-testid={`ver-filter-${s}`}>
              {s}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-4">
        {items.length === 0 ? (
          <p className="text-neutral-500 text-sm hard-border bg-white p-6 shadow-brutal text-center">No {status} verifications.</p>
        ) : items.map((u) => {
          const p = u.profile || {};
          const rs = u.reference_summary || {};
          return (
            <div key={u.id} className="hard-border bg-white p-5 shadow-brutal" data-testid={`ver-row-${u.id}`}>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0 flex-1">
                  <p className="overline text-neutral-500">{(u.role || "").toUpperCase()}</p>
                  <p className="font-display font-extrabold text-lg tracking-tight">
                    {u.name}
                    {u.role === "employer" && u.verification_status === "verified" && <span className="text-[#6B21A8] ml-1" title="Verified company">✦</span>}
                    {u.role === "talent" && u.verification_status === "verified" && <span className="text-[#0EA5E9] ml-1" title="BGV verified">✓</span>}
                  </p>
                  <p className="text-xs font-mono text-neutral-500">{u.email}</p>
                  {u.role === "employer" && (
                    <p className="text-xs text-neutral-600 mt-1">{p.company_name} · {p.company_website} · {p.company_size || "—"}</p>
                  )}
                  {u.role === "talent" && (
                    <p className="text-xs text-neutral-600 mt-1">{(p.work_history || []).length} work rows · {(p.references || []).length} refs · LinkedIn: {p.linkedin_url ? "✓" : "—"}</p>
                  )}
                </div>
                {u.role === "talent" && rs.total > 0 && (
                  <div className="flex gap-1 flex-wrap" data-testid={`ref-chips-${u.id}`}>
                    {rs.yes > 0     && <span className={`hard-border px-2 py-1 text-[10px] font-mono ${chipColor("yes")}`} data-testid={`ref-yes-${u.id}`}>{rs.yes} YES</span>}
                    {rs.partial > 0 && <span className={`hard-border px-2 py-1 text-[10px] font-mono ${chipColor("partial")}`} data-testid={`ref-partial-${u.id}`}>{rs.partial} PARTIAL</span>}
                    {rs.no > 0      && <span className={`hard-border px-2 py-1 text-[10px] font-mono ${chipColor("no")}`} data-testid={`ref-no-${u.id}`}>{rs.no} NO</span>}
                    {rs.pending > 0 && <span className={`hard-border px-2 py-1 text-[10px] font-mono ${chipColor("pending")}`} data-testid={`ref-pending-${u.id}`}>{rs.pending} PENDING</span>}
                  </div>
                )}
              </div>
              {u.verification_notes && (
                <p className="text-xs text-neutral-600 mt-3 hard-border bg-[#F5F3FF] px-2 py-1"><b>Notes:</b> {u.verification_notes}</p>
              )}
              {status === "pending" && canDecide && (
                <div className="flex gap-2 mt-4">
                  <button onClick={() => decide(u.id, "approve")} className="btn-primary text-xs" data-testid={`ver-approve-${u.id}`}>Approve</button>
                  <button onClick={() => decide(u.id, "reject")}  className="btn-outline text-xs" data-testid={`ver-reject-${u.id}`}>Reject</button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}



// ---------- Revisions panel (moderation) ----------
function RevisionsPanel({ scopes }) {
  const [data, setData] = useState(null);
  const [flagged, setFlagged] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [ruling, setRuling] = useState({}); // {grievanceId: {choice, notes}}

  const canRule = (scopes || []).includes("moderation") || (scopes || []).includes("superadmin");

  const load = async () => {
    try {
      const r = await api.get("/admin/revisions");
      setData(r.data);
      const f = await api.get("/admin/employers-flagged");
      setFlagged(f.data.items || []);
      const a = await api.get("/admin/revisions/refund-analytics");
      setAnalytics(a.data);
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); }, []);

  const rule = async (gid) => {
    const state = ruling[gid] || {};
    if (!state.choice) return toast.error("Pick a ruling first");
    if ((state.notes || "").trim().length < 10) return toast.error("Add at least a 10-char justification");
    try {
      await api.post(`/admin/revisions/${gid}/rule`, { ruling: state.choice, notes: state.notes });
      toast.success(`Dispute ruled in favour of ${state.choice}`);
      setRuling((prev) => { const c = { ...prev }; delete c[gid]; return c; });
      await load();
    } catch (e) { toast.error(formatErr(e)); }
  };

  if (!data) return <p className="font-mono text-sm text-neutral-500">Loading revisions…</p>;

  return (
    <div className="space-y-8" data-testid="admin-revisions-panel">
      <div className="grid grid-cols-3 gap-3">
        <StatTile label="Open revisions" value={data.counts.open_revisions}/>
        <StatTile label="Open disputes"  value={data.disputes.filter((d) => d.status !== "resolved").length}/>
        <StatTile label="Flagged employers" value={flagged.length}/>
      </div>

      {/* Refund analytics — 30-day rolling area chart */}
      {analytics && <RefundAnalyticsCard analytics={analytics}/>}

      {/* Disputes queue */}
      <section>
        <p className="overline text-[#6B21A8] mb-3">Disputes queue</p>
        {data.disputes.length === 0 ? (
          <p className="hard-border bg-white p-5 text-sm text-neutral-500">Nothing to rule on.</p>
        ) : (
          <ul className="space-y-3">
            {data.disputes.map((g) => (
              <li key={g.id} className="hard-border bg-white p-4 shadow-brutal" data-testid={`admin-dispute-${g.id}`}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <p className="font-display font-extrabold text-sm">Ref {g.ref} · {g.revision_thread?.length || 0} revisions</p>
                    <p className="text-[10px] font-mono text-neutral-500">
                      Talent {(g.talent_id || "").slice(0,8)} vs Employer {(g.employer_id || "").slice(0,8)} · Filed {new Date(g.created_at).toLocaleString()}
                    </p>
                    <p className="text-xs text-neutral-700 mt-2 whitespace-pre-wrap">{g.reason}</p>
                  </div>
                  <span className={`hard-border px-2 py-1 text-[10px] font-mono uppercase ${g.status === "resolved" ? "bg-[#EDE9FE] text-[#6B21A8]" : "bg-yellow-100 text-yellow-900"}`}>
                    {g.status}
                  </span>
                </div>
                {g.status === "resolved" ? (
                  <>
                    <p className="text-xs mt-3 text-neutral-600">
                      Ruled for <b>{g.ruling}</b> · Fee {g.dispute_fee?.status} ·
                      {" "}<span className={g.dispute_fee?.payment_status === "paid" ? "text-emerald-700"
                        : g.dispute_fee?.payment_status === "refunded" ? "text-[#6B21A8]"
                        : "text-red-700"}>
                        {g.dispute_fee?.payment_status === "paid"
                          ? `Paid ${new Date(g.dispute_fee?.paid_at || Date.now()).toLocaleDateString()}`
                          : g.dispute_fee?.payment_status === "refunded"
                            ? `Refunded ${new Date(g.dispute_fee?.refunded_at || Date.now()).toLocaleDateString()}`
                            : (g.dispute_fee?.payment_status || "unpaid")}
                      </span>
                      {" · "}{g.ruling_notes}
                    </p>
                    {g.dispute_fee?.payment_status === "paid" && canRule && (
                      <RefundInline grievanceId={g.id} onDone={load}/>
                    )}
                    {g.dispute_fee?.payment_status === "refunded" && g.dispute_fee?.refund_reason && (
                      <p className="text-[10px] font-mono text-neutral-500 mt-1">
                        Refund reason: {g.dispute_fee.refund_reason}
                      </p>
                    )}
                  </>
                ) : canRule && (
                  <div className="mt-3 grid md:grid-cols-[auto_1fr_auto] gap-2 items-center">
                    <div className="flex gap-2">
                      {["talent", "employer"].map((c) => (
                        <button key={c} type="button"
                                data-testid={`rule-${c}-${g.id}`}
                                onClick={() => setRuling({ ...ruling, [g.id]: { ...(ruling[g.id] || {}), choice: c } })}
                                className={`hard-border px-3 py-1 text-xs capitalize ${ruling[g.id]?.choice === c ? "bg-[#0B1B2B] text-white" : "bg-white"}`}>
                          Rule for {c}
                        </button>
                      ))}
                    </div>
                    <input placeholder="Ruling notes (min 10 chars)"
                           value={ruling[g.id]?.notes || ""}
                           onChange={(e) => setRuling({ ...ruling, [g.id]: { ...(ruling[g.id] || {}), notes: e.target.value } })}
                           data-testid={`rule-notes-${g.id}`}
                           className="hard-border px-2 py-1 text-xs w-full"/>
                    <button type="button" onClick={() => rule(g.id)} className="btn-primary text-xs" data-testid={`rule-submit-${g.id}`}>
                      Apply ruling
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Open revision cycles */}
      <section>
        <p className="overline text-[#6B21A8] mb-3">Open revision cycles</p>
        {data.revisions.length === 0 ? (
          <p className="hard-border bg-white p-5 text-sm text-neutral-500">No open revision cycles.</p>
        ) : (
          <ul className="space-y-2" data-testid="admin-revisions-list">
            {data.revisions.slice(0, 25).map((r) => (
              <li key={r.id} className="hard-border bg-white p-3 flex items-center justify-between gap-2 flex-wrap">
                <div className="min-w-0">
                  <p className="font-display font-extrabold text-sm">
                    Rev #{r.revision_number} · <span className="text-[10px] font-mono uppercase text-neutral-500">{r.priority}</span>
                  </p>
                  <p className="text-[11px] font-mono text-neutral-500">Deliverable {r.deliverable_id?.slice(0, 8)} · {new Date(r.created_at).toLocaleString()}</p>
                  <p className="text-xs text-neutral-700 mt-1 line-clamp-2">{r.justification}</p>
                </div>
                <span className={`hard-border px-2 py-1 text-[10px] font-mono uppercase ${r.status === "resubmitted" ? "bg-[#EDE9FE] text-[#6B21A8]" : "bg-yellow-100 text-yellow-900"}`}>
                  {r.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Flagged employers */}
      {flagged.length > 0 && (
        <section>
          <p className="overline text-[#991B1B] mb-3">Flagged employers · abuse pattern</p>
          <ul className="grid md:grid-cols-2 gap-3">
            {flagged.map((e) => (
              <li key={e.id} className="hard-border bg-white p-3">
                <p className="font-display font-extrabold text-sm">{e.name || e.email}</p>
                <p className="text-[10px] font-mono text-neutral-500">
                  Flagged {new Date(e.profile?.abusive_pattern_flagged_at || Date.now()).toLocaleString()} ·
                  {" "}{(e.profile?.abusive_pattern_talents || []).length} talents affected
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function StatTile({ label, value }) {
  return (
    <div className="hard-border bg-white p-4 shadow-brutal">
      <p className="overline text-neutral-500">{label}</p>
      <p className="font-display font-black text-2xl text-[#0B1B2B] mt-1">{value ?? "—"}</p>
    </div>
  );
}



function RefundInline({ grievanceId, onDone }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if ((reason || "").trim().length < 10) return toast.error("Add at least a 10-char refund reason");
    if (!window.confirm("Issue a full Stripe refund to the payer's card?")) return;
    setSaving(true);
    try {
      const r = await api.post(`/admin/grievances/${grievanceId}/refund-fee`, { reason: reason.trim() });
      toast.success(`Refunded $${r.data.amount_usd}`);
      setOpen(false); setReason("");
      onDone && onDone();
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSaving(false); }
  };
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}
              data-testid={`refund-open-${grievanceId}`}
              className="mt-2 text-[11px] font-mono uppercase tracking-widest text-[#6B21A8] hover:text-[#0B1B2B] border border-[#6B21A8] px-2 py-1 inline-flex items-center gap-1">
        ↺ Refund fee
      </button>
    );
  }
  return (
    <div className="mt-2 hard-border bg-[#F5F3FF] p-2" data-testid={`refund-form-${grievanceId}`}>
      <p className="overline text-[#6B21A8] mb-1">Refund justification (visible in audit log)</p>
      <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                minLength={10} data-testid={`refund-reason-${grievanceId}`}
                className="w-full hard-border px-2 py-1 text-xs focus:outline-none focus:border-[#6B21A8]"
                placeholder="New evidence surfaced — please describe briefly"/>
      <div className="flex gap-2 mt-2">
        <button type="button" onClick={submit} disabled={saving} className="btn-primary text-xs" data-testid={`refund-submit-${grievanceId}`}>
          {saving ? "Refunding…" : "Refund via Stripe"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="btn-outline text-xs">Cancel</button>
      </div>
    </div>
  );
}



function RefundAnalyticsCard({ analytics }) {
  const { series, totals, alert } = analytics || {};
  const fmtDay = (iso) => { if (!iso) return ""; const [, m, d] = iso.split("-"); return `${Number(m)}/${Number(d)}`; };
  const isAlert = alert?.breached;
  return (
    <div className={`hard-border p-6 shadow-brutal ${isAlert ? "bg-red-50 border-red-500" : "bg-white"}`}
         data-testid="refund-analytics-card">
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-3">
        <div>
          <p className="overline text-[#6B21A8]">Refund analytics · 30-day</p>
          <div className="flex items-baseline gap-4 mt-1 flex-wrap">
            <p className="font-display font-black text-3xl text-[#0B1B2B]" data-testid="refund-rate-pct">
              {totals?.refund_rate_pct ?? 0}%
              <span className="text-sm font-mono text-neutral-500 ml-2">refund rate</span>
            </p>
            <p className="text-[11px] font-mono text-neutral-500 uppercase tracking-widest">
              {totals?.refunded_30d ?? 0} refunded of {totals?.paid_30d ?? 0} paid
              {" · "}${totals?.amount_refunded_usd ?? 0} out
            </p>
          </div>
        </div>
        {isAlert && (
          <span className="hard-border px-3 py-1 bg-red-600 text-white text-[10px] font-mono uppercase tracking-widest"
                data-testid="refund-alert-chip">
            ⚠ Above {alert.threshold_pct}% threshold
          </span>
        )}
      </div>
      <div className="h-32" data-testid="refund-analytics-chart">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="grad-paid" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6B21A8" stopOpacity={0.45}/>
                <stop offset="100%" stopColor="#6B21A8" stopOpacity={0.05}/>
              </linearGradient>
              <linearGradient id="grad-refunded" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#DC2626" stopOpacity={0.5}/>
                <stop offset="100%" stopColor="#DC2626" stopOpacity={0.05}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="#e5e7eb" vertical={false}/>
            <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fontSize: 10, fill: "#71717a", fontFamily: "monospace" }}
                   axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24}/>
            <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#71717a", fontFamily: "monospace" }}
                   axisLine={false} tickLine={false} width={30}/>
            <Tooltip
              contentStyle={{ background: "#0B1B2B", border: 0, color: "#fff", fontFamily: "monospace", fontSize: 12 }}
              labelStyle={{ color: "#A78BFA" }}
              labelFormatter={(l) => `Day ${fmtDay(l)}`}/>
            <Area type="monotone" dataKey="paid"     stroke="#6B21A8" strokeWidth={2} fill="url(#grad-paid)"     name="Paid"/>
            <Area type="monotone" dataKey="refunded" stroke="#DC2626" strokeWidth={2} fill="url(#grad-refunded)" name="Refunded"/>
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] font-mono text-neutral-500 mt-2 tracking-widest uppercase">
        Alert if refund rate crosses {alert?.threshold_pct ?? 20}% · env: REFUND_ALERT_THRESHOLD_PCT
      </p>
    </div>
  );
}

