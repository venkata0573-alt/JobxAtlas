import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Bank, CheckCircle, X } from "@phosphor-icons/react";

export default function Admin() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const load = async () => {
    try { const r = await api.get("/admin/bank-transfers"); setItems(r.data); }
    catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { if (user?.role === "admin") load(); }, [user]);

  if (user?.role !== "admin") {
    return <main className="max-w-3xl mx-auto p-16 text-center"><p className="font-mono">Admins only.</p></main>;
  }

  const approve = async (id) => {
    try { await api.post(`/admin/bank-transfers/${id}/approve`); toast.success("Approved"); load(); }
    catch (e) { toast.error(formatErr(e)); }
  };
  const reject = async (id) => {
    try { await api.post(`/admin/bank-transfers/${id}/reject`); toast.success("Rejected"); load(); }
    catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">ADMIN · BANK TRANSFERS</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-8">Approve incoming payments.</h1>
      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>{["Reference","Employer","Amount","UTR","Status","Actions"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan="6" className="p-8 text-center text-neutral-500">No pending transfers.</td></tr>
            ) : items.map((p) => (
              <tr key={p.id} className="border-t border-black/10">
                <td className="px-4 py-3 font-mono">{p.reference}</td>
                <td className="px-4 py-3">{p.user_id.slice(0,8)}…</td>
                <td className="px-4 py-3 font-mono">₹{(p.amount/100).toLocaleString()} · {p.hours}h</td>
                <td className="px-4 py-3 font-mono text-xs">{p.utr || "—"}</td>
                <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{p.status}</span></td>
                <td className="px-4 py-3 flex gap-2">
                  <button onClick={() => approve(p.id)} className="hard-border p-2 hover:bg-[#002FA7] hover:text-white"><CheckCircle size={16}/></button>
                  <button onClick={() => reject(p.id)} className="hard-border p-2 hover:bg-[#FF0A0A] hover:text-white"><X size={16}/></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
