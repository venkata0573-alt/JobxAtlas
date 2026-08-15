import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { toast } from "sonner";
import { FileText, Warning, ArrowRight, CreditCard } from "@phosphor-icons/react";

export default function Invoices() {
  const [data, setData] = useState({ items: [], total_open: 0, total_paid: 0 });
  const [billing, setBilling] = useState({ attached: false });
  const [filter, setFilter] = useState("all");  // all | open | overdue | paid
  const [params, setParams] = useSearchParams();

  const load = async () => {
    try {
      const [inv, b] = await Promise.all([
        api.get("/invoices/mine"),
        api.get("/billing/status").catch(() => ({ data: { attached: false } })),
      ]);
      setData(inv.data);
      setBilling(b.data);
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); }, []);

  // Stripe SetupCheckout return handler
  useEffect(() => {
    const sid = params.get("setup");
    if (!sid) return;
    (async () => {
      try {
        const r = await api.get(`/billing/setup-checkout/status/${sid}`);
        if (r.data?.ok) { toast.success("Card saved — auto-collect is on."); load(); }
        else { toast.error("Card setup did not complete. Please try again."); }
      } catch (e) { toast.error(formatErr(e)); }
      finally { params.delete("setup"); setParams(params, { replace: true }); }
    })();
    // eslint-disable-next-line
  }, []);

  const downloadPdf = (projectId, invId) => {
    const base = process.env.REACT_APP_BACKEND_URL;
    window.open(`${base}/api/projects/workspace/${projectId}/invoices/${invId}/pdf`, "_blank");
  };

  const filtered = useMemo(() => {
    const items = data.items || [];
    if (filter === "open")    return items.filter((i) => i.status !== "paid" && !i.is_overdue);
    if (filter === "overdue") return items.filter((i) => i.is_overdue);
    if (filter === "paid")    return items.filter((i) => i.status === "paid");
    return items;
  }, [data.items, filter]);

  const overdueCount = (data.items || []).filter((i) => i.is_overdue).length;

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16" data-testid="invoices-page">
      <div className="flex items-baseline justify-between mb-6 flex-wrap gap-4">
        <div>
          <p className="overline text-[#C79A3B] mb-2">FINANCE</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Invoices</h1>
          <p className="text-sm text-neutral-600 mt-2">Every milestone invoice across your projects. Download PDFs, pay in one click.</p>
        </div>
        <div className="text-right">
          {billing.attached ? (
            <p className="text-xs font-mono text-emerald-700" data-testid="billing-attached">
              ✓ Auto-collect on file · {billing.brand?.toUpperCase()} ••{billing.last4}
            </p>
          ) : (
            <div>
              <p className="text-xs font-mono text-neutral-500">No card on file</p>
              <p className="text-[10px] text-neutral-400">Save a card once, we&apos;ll auto-collect overdue invoices.</p>
            </div>
          )}
        </div>
      </div>

      {/* Totals */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <div className="hard-border bg-white p-4 shadow-brutal" data-testid="totals-count">
          <p className="overline text-neutral-500 mb-1">Invoices</p>
          <p className="font-display font-black text-2xl">{data.count || 0}</p>
        </div>
        <div className="hard-border bg-white p-4 shadow-brutal" data-testid="totals-open">
          <p className="overline text-neutral-500 mb-1">Open</p>
          <p className="font-display font-black text-2xl">${(data.total_open / 1000).toFixed(1)}k</p>
        </div>
        <div className={`hard-border p-4 shadow-brutal ${overdueCount > 0 ? "bg-[#FEF0F0] border-red-300" : "bg-white"}`} data-testid="totals-overdue">
          <p className="overline text-neutral-500 mb-1">Overdue</p>
          <p className={`font-display font-black text-2xl ${overdueCount > 0 ? "text-red-700" : ""}`}>{overdueCount}</p>
        </div>
        <div className="hard-border bg-white p-4 shadow-brutal" data-testid="totals-paid">
          <p className="overline text-neutral-500 mb-1">Paid</p>
          <p className="font-display font-black text-2xl">${(data.total_paid / 1000).toFixed(1)}k</p>
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {[
          { id: "all", label: "All" },
          { id: "open", label: "Open" },
          { id: "overdue", label: `Overdue (${overdueCount})` },
          { id: "paid", label: "Paid" },
        ].map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)}
                  className={`hard-border px-3 py-2 text-xs ${filter === f.id ? "bg-[#0B1B2B] text-white" : "bg-white"}`}
                  data-testid={`filter-${f.id}`}>{f.label}</button>
        ))}
      </div>

      {/* Table */}
      <div className="hard-border bg-white shadow-brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#0A0A0A] text-white">
            <tr>{["Ref","Project · Milestone","Amount","Due","Status","Actions"].map((h) => (
              <th key={h} className="text-left px-4 py-3 overline">{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan="6" className="p-8 text-center text-neutral-500">No invoices in this view.</td></tr>
            ) : filtered.map((inv) => (
              <tr key={inv.id} className={`border-t border-black/10 align-top ${inv.is_overdue ? "bg-[#FEF0F0]" : ""}`} data-testid={`invoice-row-${inv.id}`}>
                <td className="px-4 py-3 font-mono">{inv.ref}</td>
                <td className="px-4 py-3">
                  <p className="font-display font-bold">{inv.project_company}</p>
                  <p className="text-xs text-neutral-500">{inv.milestone_name} · {inv.project_template}</p>
                </td>
                <td className="px-4 py-3 font-mono font-bold">{(inv.currency || "usd").toUpperCase()} {(inv.amount || 0).toLocaleString()}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {inv.milestone_due || "—"}
                  {inv.is_overdue && (
                    <span className="ml-2 hard-border bg-red-700 text-white px-1 py-0.5 text-[9px] inline-flex items-center gap-1">
                      <Warning size={10} weight="fill"/> OVERDUE
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className={`hard-border px-2 py-1 text-xs ${inv.status === "paid" ? "bg-emerald-100" : "bg-amber-100"}`}>
                    {inv.status}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-1 flex-wrap">
                    <button onClick={() => downloadPdf(inv.project_id, inv.id)}
                            className="hard-border px-2 py-1 text-xs bg-white hover:bg-[#FAF9F6] inline-flex items-center gap-1"
                            data-testid={`pdf-${inv.id}`}>
                      <FileText size={12}/> PDF
                    </button>
                    <Link to={`/projects/${inv.project_id}/workspace`}
                          className="hard-border px-2 py-1 text-xs bg-white hover:bg-[#FAF9F6] inline-flex items-center gap-1"
                          data-testid={`open-workspace-${inv.id}`}>
                      Workspace <ArrowRight size={10}/>
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!billing.attached && (
        <div className="hard-border bg-[#FDF6E3] p-5 shadow-brutal mt-8" data-testid="attach-card-cta">
          <div className="flex items-center gap-3 mb-2">
            <CreditCard size={20} weight="duotone" color="#C79A3B"/>
            <p className="font-display font-extrabold text-lg">Enable auto-collect</p>
          </div>
          <p className="text-sm text-neutral-700 mb-3">
            Save a card once and Job Atlas will auto-collect any invoice past its due date after 7 days. You&apos;ll still receive email reminders every 3 days before the auto-charge.
          </p>
          <button
            onClick={async () => {
              try {
                const r = await api.post("/billing/setup-checkout", { origin_url: window.location.origin });
                window.location.href = r.data.checkout_url;
              } catch (e) { toast.error(formatErr(e)); }
            }}
            className="btn-primary text-sm inline-flex items-center gap-2"
            data-testid="save-card-btn">
            <CreditCard size={14} weight="fill"/> Save a card via Stripe
          </button>
        </div>
      )}
    </main>
  );
}
