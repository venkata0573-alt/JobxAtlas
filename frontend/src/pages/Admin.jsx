import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { CheckCircle, X, Star, Bank, ChatCircleText } from "@phosphor-icons/react";

const TABS = [
  { id: "bank",       label: "Bank Transfers", Icon: Bank },
  { id: "reviews",    label: "Reviews",        Icon: Star },
  { id: "grievances", label: "Grievances",     Icon: ChatCircleText },
];

export default function Admin() {
  const { user } = useAuth();
  const [tab, setTab] = useState("bank");
  const [data, setData] = useState({ bank: [], reviews: [], grievances: [] });

  const load = async () => {
    try {
      const [b, r, g] = await Promise.all([
        api.get("/admin/bank-transfers").catch(() => ({ data: [] })),
        api.get("/admin/reviews").catch(() => ({ data: [] })),
        api.get("/admin/grievances").catch(() => ({ data: [] })),
      ]);
      setData({ bank: b.data, reviews: r.data, grievances: g.data });
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { if (user?.role === "admin") load(); }, [user]);

  if (user?.role !== "admin") {
    return <main className="max-w-3xl mx-auto p-16 text-center"><p className="font-mono">Admins only.</p></main>;
  }

  const act = async (url, msg) => {
    try { await api.post(url); toast.success(msg); load(); }
    catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">ADMIN CONSOLE</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-8">Moderation & finance.</h1>

      <div className="hard-border inline-flex bg-white mb-8">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} onClick={() => setTab(id)}
                  className={`px-5 py-3 border-r border-black last:border-r-0 flex items-center gap-2 font-display font-extrabold text-sm tracking-tight ${tab === id ? "bg-[#0A0A0A] text-white" : "bg-white text-black"}`}>
            <Icon size={16} weight="duotone"/> {label} <span className="text-xs opacity-70">({data[id].length})</span>
          </button>
        ))}
      </div>

      {tab === "bank" && (
        <div className="hard-border bg-white shadow-brutal overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#0A0A0A] text-white">
              <tr>{["Reference","Employer","Amount","UTR","Status","Actions"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
            </thead>
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
                    <button onClick={() => act(`/admin/bank-transfers/${p.id}/approve`, "Approved")}
                            className="hard-border p-2 hover:bg-[#002FA7] hover:text-white"><CheckCircle size={16}/></button>
                    <button onClick={() => act(`/admin/bank-transfers/${p.id}/reject`, "Rejected")}
                            className="hard-border p-2 hover:bg-[#FF0A0A] hover:text-white"><X size={16}/></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "reviews" && (
        <div className="grid md:grid-cols-2 gap-4">
          {data.reviews.length === 0 ? (
            <p className="text-neutral-500 col-span-2">No reviews pending moderation.</p>
          ) : data.reviews.map((r) => (
            <div key={r.id} className="hard-border bg-white p-5 shadow-brutal">
              <div className="flex items-center justify-between mb-2">
                <p className="font-display font-extrabold">{r.reviewer_name} <span className="text-xs text-neutral-500 font-normal">({r.reviewer_role})</span></p>
                <div className="flex gap-0.5">
                  {[1,2,3,4,5].map((n) => <Star key={n} size={14} weight={r.rating >= n ? "fill" : "regular"} color="#FF0A0A"/>)}
                </div>
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
            <thead className="bg-[#0A0A0A] text-white">
              <tr>{["Ref","Subject","From","Engagement","Status","Actions"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.grievances.length === 0 ? (
                <tr><td colSpan="6" className="p-8 text-center text-neutral-500">No grievances filed.</td></tr>
              ) : data.grievances.map((g) => (
                <tr key={g.id} className="border-t border-black/10 align-top">
                  <td className="px-4 py-3 font-mono text-xs">{g.id.slice(0,8)}</td>
                  <td className="px-4 py-3">
                    <p className="font-medium">{g.subject}</p>
                    <p className="text-xs text-neutral-500 line-clamp-2">{g.description}</p>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{g.contact_email}</td>
                  <td className="px-4 py-3 font-mono text-xs">{g.engagement_id?.slice(0,8) || "—"}</td>
                  <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{g.status}</span></td>
                  <td className="px-4 py-3">
                    {g.status !== "resolved" && (
                      <button onClick={() => act(`/admin/grievances/${g.id}/resolve`, "Resolved")}
                              className="hard-border p-2 hover:bg-[#002FA7] hover:text-white"><CheckCircle size={16}/></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
