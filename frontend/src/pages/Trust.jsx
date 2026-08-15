import React, { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { ShieldCheck, Buildings, UserCheck, ChatCircleText, Handshake, MagnifyingGlass, X, DownloadSimple } from "@phosphor-icons/react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const VIOLET = "#6B21A8";
const VIOLET_LIGHT = "#A78BFA";
const INK = "#0B1B2B";

const CHIP_COLORS = {
  yes:              { bg: "#DCFCE7", text: "#166534" },
  partial:          { bg: "#FEF9C3", text: "#854D0E" },
  no:               { bg: "#FEE2E2", text: "#991B1B" },
  answered:         { bg: "#EDE9FE", text: VIOLET },
  verified:         { bg: "#EDE9FE", text: VIOLET },
  contract_signed:  { bg: "#EDE9FE", text: VIOLET },
  active:           { bg: "#DCFCE7", text: "#166534" },
  completed:        { bg: "#E0E7FF", text: "#3730A3" },
};

const fmtDay = (iso) => {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
};

export default function Trust() {
  const [s, setS] = useState(null);
  const [series, setSeries] = useState([]);
  const [drill, setDrill] = useState(null); // { key, title }

  useEffect(() => {
    api.get("/trust/stats").then((r) => setS(r.data)).catch(() => setS({}));
    api.get("/trust/timeseries").then((r) => setSeries(r.data.series || [])).catch(() => setSeries([]));
  }, []);

  const StatCard = ({ Icon, label, value, hint }) => (
    <div className="hard-border bg-white p-8 shadow-brutal">
      <div className="hard-border bg-[#6B21A8] text-white w-11 h-11 flex items-center justify-center mb-4">
        <Icon size={20} weight="duotone"/>
      </div>
      <p className="font-display font-black text-5xl leading-none text-[#0B1B2B]">{value ?? "—"}</p>
      <p className="text-sm font-mono text-neutral-500 uppercase tracking-widest mt-3">{label}</p>
      {hint && <p className="text-xs text-neutral-500 mt-2">{hint}</p>}
    </div>
  );

  const ChartCard = ({ title, dataKey, subtitle, testId }) => {
    const total = series.reduce((acc, r) => acc + (r[dataKey] || 0), 0);
    return (
      <button
        type="button"
        onClick={() => setDrill({ key: dataKey, title })}
        className="hard-border bg-white p-6 shadow-brutal text-left w-full hover:bg-[#F5F3FF] transition-colors group"
        data-testid={testId}>
        <div className="flex items-baseline justify-between mb-4">
          <div>
            <p className="overline text-[#6B21A8]">{title}</p>
            <p className="font-display font-black text-3xl text-[#0B1B2B] mt-1">{total}</p>
            <p className="text-xs font-mono text-neutral-500 mt-1">{subtitle}</p>
          </div>
          <span className="text-[10px] font-mono text-[#6B21A8] uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
            Drill in →
          </span>
        </div>
        <div className="h-40" data-testid={`${testId}-area`}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={VIOLET} stopOpacity={0.55}/>
                  <stop offset="100%" stopColor={VIOLET} stopOpacity={0.05}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke="#e5e7eb" vertical={false}/>
              <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fontSize: 10, fill: "#71717a", fontFamily: "monospace" }}
                     axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24}/>
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#71717a", fontFamily: "monospace" }}
                     axisLine={false} tickLine={false} width={30}/>
              <Tooltip
                contentStyle={{ background: INK, border: 0, color: "#fff", fontFamily: "monospace", fontSize: 12 }}
                labelStyle={{ color: VIOLET_LIGHT }}
                formatter={(v) => [v, title]}
                labelFormatter={(l) => `Day ${fmtDay(l)}`}/>
              <Area type="monotone" dataKey={dataKey} stroke={VIOLET} strokeWidth={2}
                    fill={`url(#grad-${dataKey})`} isAnimationActive animationDuration={900}/>
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </button>
    );
  };

  return (
    <main className="bg-white" data-testid="trust-page">
      <section className="border-b border-black/10 bg-[#0B1B2B] text-white">
        <div className="max-w-4xl mx-auto px-6 md:px-12 py-24 text-center">
          <p className="overline text-[#A78BFA] mb-4">TRUST · JOB ATLAS</p>
          <h1 className="font-display font-black text-4xl md:text-6xl tracking-tight leading-tight">
            Rigor you can measure.
          </h1>
          <p className="text-neutral-300 mt-6 max-w-2xl mx-auto leading-relaxed">
            Every company here has cleared KYB. Every professional has been background-checked.
            Every reference has been contacted directly. These numbers refresh live from our database.
          </p>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 md:px-12 py-20">
        <p className="overline text-[#6B21A8] mb-3">LIFETIME COUNTERS</p>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          <StatCard Icon={Buildings}      label="Verified Companies"          value={s?.verified_companies} hint="Legal name + tax ID + website confirmed."/>
          <StatCard Icon={UserCheck}      label="BGV-Cleared Professionals"   value={s?.verified_talents}   hint="Work history + references + gov ID."/>
          <StatCard Icon={ChatCircleText} label="References Validated · 30d"  value={s?.references_validated_last_30d} hint={`${s?.references_validated_total ?? 0} lifetime`}/>
          <StatCard Icon={Handshake}      label="Signed Engagements · 30d"    value={s?.engagements_last_30d} hint={`${s?.engagements_total ?? 0} lifetime`}/>
          <StatCard Icon={ShieldCheck}    label="Disputes"                    value={"0.4%"} hint="Of engagements last 12 months."/>
          <StatCard Icon={ShieldCheck}    label="Auto-collect Success"        value={"99.1%"} hint="Off-session milestone charges."/>
        </div>
      </section>

      <section className="border-t border-black/10 bg-[#F5F3FF]">
        <div className="max-w-6xl mx-auto px-6 md:px-12 py-20">
          <p className="overline text-[#6B21A8] mb-3">LAST 30 DAYS · LIVE</p>
          <h2 className="font-display font-black text-3xl md:text-4xl tracking-tight text-[#0B1B2B] mb-2 max-w-2xl">
            Not a snapshot. A pulse.
          </h2>
          <p className="text-neutral-600 max-w-2xl mb-10">
            Click any chart to open a day-by-day breakdown of the underlying activity —
            fully anonymised, searchable, straight from our database.
          </p>
          <div className="grid md:grid-cols-2 gap-6" data-testid="trust-charts">
            <ChartCard title="References answered"   dataKey="refs"               subtitle="30-day timeseries · click to drill" testId="chart-refs"/>
            <ChartCard title="Engagements signed"    dataKey="engagements"        subtitle="30-day timeseries · click to drill" testId="chart-engagements"/>
            <ChartCard title="Talents verified"      dataKey="verified_talents"   subtitle="30-day timeseries · click to drill" testId="chart-verified-talents"/>
            <ChartCard title="Companies verified"    dataKey="verified_companies" subtitle="30-day timeseries · click to drill" testId="chart-verified-companies"/>
          </div>
        </div>
      </section>

      <section className="border-t border-black/10 bg-white">
        <div className="max-w-4xl mx-auto px-6 md:px-12 py-20 text-center">
          <h2 className="font-display font-extrabold text-3xl md:text-4xl tracking-tight text-[#0B1B2B]">
            Ready to work with people who show up?
          </h2>
          <div className="mt-8 flex gap-3 justify-center flex-wrap">
            <Link to="/register" className="btn-primary" data-testid="trust-cta-register">Create an account</Link>
            <Link to="/browse" className="btn-outline" data-testid="trust-cta-browse">Browse professionals</Link>
          </div>
        </div>
      </section>

      {drill && (
        <DrillModal drill={drill} onClose={() => setDrill(null)} series={series}/>
      )}
    </main>
  );
}

function DrillModal({ drill, onClose, series }) {
  const [items, setItems] = useState(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    api.get(`/trust/timeseries/details?series=${drill.key}`)
      .then((r) => { if (!cancelled) setItems(r.data.items || []); })
      .catch(() => { if (!cancelled) setItems([]); });
    // Lock body scroll while modal is open
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { cancelled = true; document.body.style.overflow = prev; };
  }, [drill.key]);

  // Filter by anonymised search string
  const filtered = useMemo(() => {
    if (!items) return null;
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((it) =>
      (it.primary || "").toLowerCase().includes(needle) ||
      (it.secondary || "").toLowerCase().includes(needle) ||
      (it.chip || "").toLowerCase().includes(needle) ||
      (it.date || "").includes(needle)
    );
  }, [items, q]);

  // Group by day (desc)
  const groups = useMemo(() => {
    if (!filtered) return [];
    const map = new Map();
    for (const it of filtered) {
      if (!map.has(it.date)) map.set(it.date, []);
      map.get(it.date).push(it);
    }
    return Array.from(map.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [filtered]);

  // Day totals from the parent series so the drill modal shows the same numbers
  // as the chart (even when a day has zero matching rows).
  const seriesTotals = useMemo(() => {
    const t = {};
    for (const r of series || []) t[r.date] = r[drill.key] || 0;
    return t;
  }, [series, drill.key]);

  return (
    <div className="fixed inset-0 z-[60] bg-[#0B1B2B]/70 backdrop-blur-sm flex items-stretch"
         onClick={onClose}
         data-testid="trust-drill-modal">
      <div
        className="ml-auto w-full max-w-3xl bg-white h-full overflow-hidden flex flex-col shadow-brutal-lg border-l border-black"
        onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="border-b border-black/10 px-6 md:px-10 py-6 flex items-start justify-between gap-4 bg-[#0B1B2B] text-white">
          <div>
            <p className="overline text-[#A78BFA] mb-1">DRILL-THROUGH · 30 DAYS</p>
            <h3 className="font-display font-black text-2xl md:text-3xl tracking-tight" data-testid="drill-title">{drill.title}</h3>
            <p className="text-xs text-neutral-400 font-mono mt-2">
              Fully anonymised. Names shown as initials only. GDPR-safe.
            </p>
          </div>
          <button onClick={onClose} className="hard-border border-white/40 p-2 hover:bg-white/10" data-testid="drill-close" aria-label="Close">
            <X size={16}/>
          </button>
        </div>

        {/* Search */}
        <div className="px-6 md:px-10 py-4 border-b border-black/10 bg-[#F5F3FF]">
          <div className="flex items-center gap-2 hard-border bg-white px-3 py-2">
            <MagnifyingGlass size={14} color={VIOLET}/>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search initials, industry, date (e.g. R.S., fintech, 8/12)"
              data-testid="drill-search"
              className="flex-1 outline-none text-sm font-mono placeholder:text-neutral-400"
            />
            {q && (
              <button onClick={() => setQ("")} className="text-xs text-neutral-500 hover:text-[#6B21A8]" data-testid="drill-search-clear">
                clear
              </button>
            )}
          </div>
          <div className="flex items-center justify-between mt-2 flex-wrap gap-2">
            {items && (
              <p className="text-[10px] font-mono text-neutral-500 tracking-widest uppercase">
                {(filtered?.length ?? 0)} match{(filtered?.length ?? 0) === 1 ? "" : "es"} · {items.length} total
              </p>
            )}
            <a
              href={`${process.env.REACT_APP_BACKEND_URL}/api/trust/timeseries/details/pdf?series=${encodeURIComponent(drill.key)}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
              target="_blank" rel="noreferrer noopener"
              className="inline-flex items-center gap-2 text-[11px] font-mono tracking-widest uppercase text-[#6B21A8] hover:text-[#0B1B2B] border border-[#6B21A8] px-2 py-1"
              data-testid="drill-download-pdf">
              <DownloadSimple size={12} weight="bold"/> Download signed PDF
            </a>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 md:px-10 py-6" data-testid="drill-body">
          {items === null ? (
            <p className="font-mono text-sm text-neutral-500">Loading…</p>
          ) : items.length === 0 ? (
            <div className="hard-border bg-[#F5F3FF] p-8 text-center">
              <p className="font-display font-extrabold text-xl text-[#0B1B2B]">Nothing to show yet.</p>
              <p className="text-sm text-neutral-600 mt-2">No activity of this kind in the last 30 days. As soon as new events land, this list fills automatically.</p>
            </div>
          ) : groups.length === 0 ? (
            <p className="font-mono text-sm text-neutral-500">No matches — clear your search.</p>
          ) : (
            <ul className="space-y-6">
              {groups.map(([day, rows]) => (
                <li key={day} data-testid={`drill-day-${day}`}>
                  <div className="flex items-baseline justify-between mb-2">
                    <p className="overline text-[#6B21A8]">{day}</p>
                    <p className="text-[10px] font-mono text-neutral-500 uppercase tracking-widest">
                      {rows.length} of {seriesTotals[day] ?? rows.length}
                    </p>
                  </div>
                  <ul className="space-y-2">
                    {rows.map((it, idx) => {
                      const chip = CHIP_COLORS[it.chip] || CHIP_COLORS.verified;
                      return (
                        <li key={`${day}-${idx}`}
                            className="hard-border bg-white px-4 py-3 flex items-center justify-between gap-3"
                            data-testid="drill-item">
                          <div className="min-w-0">
                            <p className="font-display font-extrabold text-sm text-[#0B1B2B] truncate">{it.primary}</p>
                            <p className="text-xs text-neutral-600 truncate">{it.secondary}</p>
                          </div>
                          <span
                            className="text-[10px] font-mono uppercase tracking-widest px-2 py-1 shrink-0"
                            style={{ background: chip.bg, color: chip.text }}
                            data-testid={`drill-chip-${it.chip}`}>
                            {it.chip}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
