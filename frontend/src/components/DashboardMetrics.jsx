import React from "react";
import { Link } from "react-router-dom";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis } from "recharts";
import { PuzzlePiece, Clock, ChartBar, ListChecks, WarningOctagon } from "@phosphor-icons/react";

const COLORS = ["#6B21A8", "#0A0A0A", "#6B21A8", "#7C7C7C", "#B0B0B0"];

const Stat = ({ k, label, sub }) => (
  <div className="p-8 border-r border-b border-black/10 bg-white">
    <div className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">{k}</div>
    <p className="overline text-neutral-500 mt-2">{label}</p>
    {sub ? <p className="text-xs text-neutral-500 mt-1 font-mono">{sub}</p> : null}
  </div>
);

const toArr = (obj) => Object.entries(obj || {}).map(([name, value]) => ({ name, value }));

export default function DashboardMetrics({ metrics, role }) {
  if (!metrics) return null;
  const status = toArr(metrics.work_items_by_status);
  const sources = toArr(metrics.work_items_by_source);

  const roleStats = role === "employer"
    ? [
        { k: metrics.hours_balance, label: "Hours available", sub: "Ready to allocate" },
        { k: metrics.hours_purchased, label: "Hours purchased" },
        { k: `$${metrics.total_spent_usd}`, label: "Total spent" },
        { k: metrics.engagements_active, label: "Active engagements" },
      ]
    : [
        { k: metrics.hours_contracted, label: "Hours contracted" },
        { k: metrics.engagements_active, label: "Active engagements" },
        { k: metrics.engagements_total, label: "Total engagements" },
        { k: `${metrics.hours_logged}h`, label: "Hours logged" },
      ];

  return (
    <div className="space-y-6">
      {/* Role-specific top strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 border-l border-t border-black/10">
        {roleStats.map((s, i) => <Stat key={i} {...s} />)}
      </div>

      {/* Shared middle bento */}
      <div className="grid lg:grid-cols-3 gap-6">
        <div className="hard-border bg-white p-6 shadow-brutal lg:col-span-1">
          <div className="flex items-center gap-2 mb-4">
            <ChartBar size={18} weight="duotone" color="#6B21A8"/>
            <p className="overline">Task status</p>
          </div>
          {status.length === 0 ? (
            <p className="text-sm text-neutral-500 py-8">Connect an integration to see task metrics.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={status} innerRadius={50} outerRadius={85} dataKey="value" stroke="#0A0A0A" strokeWidth={1.5}>
                  {status.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]}/>)}
                </Pie>
                <Tooltip contentStyle={{ border: "1px solid #0A0A0A", borderRadius: 0 }}/>
              </PieChart>
            </ResponsiveContainer>
          )}
          <div className="flex flex-wrap gap-3 mt-2 text-xs font-mono">
            {status.map((s, i) => (
              <span key={s.name} className="inline-flex items-center gap-1">
                <span className="inline-block w-2 h-2" style={{ background: COLORS[i % COLORS.length] }}/> {s.name}: {s.value}
              </span>
            ))}
          </div>
        </div>

        <div className="hard-border bg-white p-6 shadow-brutal lg:col-span-1">
          <div className="flex items-center gap-2 mb-4">
            <PuzzlePiece size={18} weight="duotone" color="#6B21A8"/>
            <p className="overline">Work by source</p>
          </div>
          {sources.length === 0 ? (
            <p className="text-sm text-neutral-500 py-8">Nothing synced yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={sources} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#0A0A0A"/>
                <YAxis tick={{ fontSize: 10 }} stroke="#0A0A0A" allowDecimals={false}/>
                <Tooltip cursor={{ fill: "rgba(0,47,167,0.08)" }} contentStyle={{ border: "1px solid #0A0A0A", borderRadius: 0 }}/>
                <Bar dataKey="value" fill="#6B21A8" stroke="#0A0A0A" strokeWidth={1}/>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="hard-border bg-[#F5F3FF] p-6 shadow-brutal lg:col-span-1">
          <div className="flex items-center gap-2 mb-4">
            <ListChecks size={18} weight="duotone" color="#6B21A8"/>
            <p className="overline">Upcoming</p>
          </div>
          {metrics.upcoming.length === 0 ? (
            <p className="text-sm text-neutral-500">No dated tasks. Add due dates to see them here.</p>
          ) : (
            <ul className="divide-y divide-black/10">
              {metrics.upcoming.map((u, i) => (
                <li key={i} className="py-3 flex justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{u.title}</p>
                    <p className="text-xs text-neutral-500 font-mono">{u.source} · {u.status}</p>
                  </div>
                  <span className="font-mono text-xs whitespace-nowrap">{String(u.due_date).slice(0, 10)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Shared footer strip */}
      <div className="grid md:grid-cols-3 gap-6">
        <Link to="/integrations" className="hard-border bg-white p-6 shadow-brutal-hover flex items-center gap-4">
          <PuzzlePiece size={26} weight="duotone" color="#6B21A8"/>
          <div>
            <p className="font-display font-extrabold text-lg tracking-tight">{metrics.integrations_connected} connected</p>
            <p className="text-xs text-neutral-500">Jira · Asana · Confluence · Monday · SAP…</p>
          </div>
        </Link>
        <div className="hard-border bg-white p-6 shadow-brutal flex items-center gap-4">
          <ListChecks size={26} weight="duotone" color="#6B21A8"/>
          <div>
            <p className="font-display font-extrabold text-lg tracking-tight">{metrics.work_items_total} tasks tracked</p>
            <p className="text-xs text-neutral-500">Across all connected sources & uploads</p>
          </div>
        </div>
        <div className="hard-border bg-[#F5F3FF] p-6 flex items-center gap-4">
          <WarningOctagon size={26} weight="fill" color="#6B21A8"/>
          <div>
            <p className="font-display font-extrabold text-lg tracking-tight">12-month exclusivity</p>
            <p className="text-xs text-neutral-700">All engagements protected via platform contract.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
