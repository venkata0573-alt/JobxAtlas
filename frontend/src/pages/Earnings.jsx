import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { toast } from "sonner";
import { CurrencyDollar, ChartLineUp, ClockCounterClockwise, Bank, DownloadSimple } from "@phosphor-icons/react";

export default function Earnings() {
  const [e, setE] = useState(null);
  const [past, setPast] = useState([]);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/earnings/mine"), api.get("/payouts/mine")]);
      setE(a.data); setPast(b.data);
    } catch (err) { toast.error(formatErr(err)); }
  };
  useEffect(() => { load(); }, []);

  const downloadStatement = () => {
    if (!e) return;
    const rows = [
      `Statement period: ${String(e.period_start).slice(0,10)} → ${String(e.period_end).slice(0,10)}`,
      `Talent: ${e.talent_name}`,
      ``,
      `Hourly rate:            $${e.hourly_rate}`,
      `Hours worked (approved): ${e.hours}`,
      `Employers this period:  ${e.employers_count}`,
      `Commission tier:        ${e.commission_pct}%`,
      ``,
      `Gross:                  $${e.gross.toFixed(2)}`,
      `− Platform commission:  $${e.commission.toFixed(2)}`,
      `− Multi-employer fee:   $${e.multi_employer_fee.toFixed(2)}`,
      `= NET PAYABLE:          $${e.net.toFixed(2)} ${e.currency.toUpperCase()}`,
      ``,
      `Job Atlas · a product of Geminista · Denkoit Softech Pvt. Ltd.`,
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `talenthub-statement-${String(e.period_end).slice(0,10)}.txt`; a.click();
    URL.revokeObjectURL(url);
  };

  if (!e) return <div className="p-16 font-mono text-center">Loading…</div>;

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-8 flex-wrap gap-4">
        <div>
          <p className="overline text-[#002FA7] mb-3">EARNINGS</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Rolling 30-day statement.</h1>
          <p className="text-neutral-600 mt-2">{String(e.period_start).slice(0,10)} → {String(e.period_end).slice(0,10)}</p>
        </div>
        <button onClick={downloadStatement} className="btn-outline text-sm inline-flex items-center gap-2">
          <DownloadSimple size={14}/> Download statement
        </button>
      </div>

      {/* Top strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 border-l border-t border-black/10 mb-8">
        {[
          { k: `${e.hours}h`,          label: "Approved hours", Icon: ClockCounterClockwise },
          { k: `$${e.gross.toFixed(2)}`, label: "Gross earnings", Icon: CurrencyDollar },
          { k: `${e.commission_pct}%`,  label: "Commission tier", Icon: ChartLineUp },
          { k: `$${e.net.toFixed(2)}`,  label: "Net payable",     Icon: Bank },
        ].map(({ k, label, Icon }, i) => (
          <div key={i} className="p-8 border-r border-b border-black/10 bg-white">
            <Icon size={20} weight="duotone" color="#002FA7"/>
            <div className="font-display font-extrabold text-4xl tracking-tight mt-3">{k}</div>
            <p className="overline text-neutral-500 mt-2">{label}</p>
          </div>
        ))}
      </div>

      {/* Breakdown */}
      <section className="grid md:grid-cols-[1.4fr_1fr] gap-6 mb-10">
        <div className="hard-border bg-white p-8 shadow-brutal">
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-6">This period&apos;s math</h2>
          <div className="divide-y divide-black/10 font-mono text-sm">
            <Row label="Hourly rate"                  v={`$${e.hourly_rate}`}/>
            <Row label={`Approved hours × rate`}      v={`$${e.gross.toFixed(2)}`}/>
            <Row label={`− Platform commission (${e.commission_pct}%)`} v={`− $${e.commission.toFixed(2)}`}/>
            <Row label={`− Multi-employer fee`}       v={`− $${e.multi_employer_fee.toFixed(2)}`} muted={!e.multi_employer_fee}/>
            <Row label="Net payable"                  v={`$${e.net.toFixed(2)}`} bold/>
          </div>
        </div>
        <aside className="hard-border bg-[#FDFCF0] p-8 shadow-brutal">
          <p className="overline text-[#002FA7] mb-3">Volume tiers</p>
          <p className="text-sm text-neutral-600 mb-4">Commission drops as you clock more approved hours in a rolling month:</p>
          <ul className="space-y-2 font-mono text-sm">
            <li>≤ 40h    · 8%</li>
            <li>40–120h  · 6%</li>
            <li>120–250h · 5%</li>
            <li>250h+    · <strong>4%</strong></li>
          </ul>
          <p className="text-xs text-neutral-500 mt-6">Multi-employer fee of $9 kicks in if you have active engagements with more than one employer this month.</p>
        </aside>
      </section>

      {/* Past payouts */}
      <section className="hard-border bg-white shadow-brutal overflow-x-auto">
        <div className="p-6 border-b border-black/10 flex items-center justify-between">
          <h2 className="font-display font-extrabold text-2xl tracking-tight">Past payouts</h2>
          <p className="text-sm font-mono text-neutral-500">{past.length} runs</p>
        </div>
        {past.length === 0 ? (
          <p className="p-8 text-neutral-500 text-sm">No payouts recorded yet. The platform generates payout runs at the end of each cycle.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-[#0A0A0A] text-white">
              <tr>{["Period","Hours","Gross","Commission","Multi-fee","Net","Status"].map((h) => <th key={h} className="text-left px-4 py-3 overline">{h}</th>)}</tr>
            </thead>
            <tbody>
              {past.map((p) => (
                <tr key={p.id} className="border-t border-black/10">
                  <td className="px-4 py-3 font-mono text-xs">{String(p.period_start).slice(0,10)} → {String(p.period_end).slice(0,10)}</td>
                  <td className="px-4 py-3 font-mono">{p.hours}h</td>
                  <td className="px-4 py-3 font-mono">${p.gross.toFixed(2)}</td>
                  <td className="px-4 py-3 font-mono">−${p.commission.toFixed(2)} ({p.commission_pct}%)</td>
                  <td className="px-4 py-3 font-mono">−${p.multi_employer_fee.toFixed(2)}</td>
                  <td className="px-4 py-3 font-mono font-bold">${p.net.toFixed(2)}</td>
                  <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{p.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

function Row({ label, v, bold, muted }) {
  return (
    <div className={`flex justify-between py-3 ${bold ? "font-bold text-lg" : ""} ${muted ? "opacity-50" : ""}`}>
      <span>{label}</span><span>{v}</span>
    </div>
  );
}
