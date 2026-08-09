import React, { useEffect, useMemo, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { Plus, X, Clock, GlobeHemisphereEast } from "@phosphor-icons/react";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const TZS = [
  "UTC", "America/Los_Angeles", "America/New_York", "Europe/London",
  "Europe/Berlin", "Europe/Paris", "Asia/Dubai", "Asia/Kolkata",
  "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney",
];

function toMinutes(t) { const [h, m] = (t || "0:0").split(":").map(Number); return h * 60 + (m || 0); }
function fmt(mins) { const h = Math.floor(mins / 60) % 24; const m = mins % 60; return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`; }

// Convert HH:MM in fromTz to HH:MM in toTz using today's date
function convertHM(hm, fromTz, toTz) {
  try {
    const [H, M] = hm.split(":").map(Number);
    const now = new Date();
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: fromTz, year: "numeric", month: "2-digit", day: "2-digit" })
      .formatToParts(now).reduce((a, p) => { a[p.type] = p.value; return a; }, {});
    // Build a Date representing that wall-clock time in fromTz — approximate via UTC arithmetic
    const utcRef = new Date(`${parts.year}-${parts.month}-${parts.day}T00:00:00Z`);
    // Get the offset of fromTz vs UTC in minutes on that day
    const offFrom = utcOffsetMin(utcRef, fromTz);
    const utcMinutes = H * 60 + M - offFrom;
    const offTo = utcOffsetMin(utcRef, toTz);
    const total = (utcMinutes + offTo + 24 * 60) % (24 * 60);
    return fmt(total);
  } catch { return hm; }
}
function utcOffsetMin(d, tz) {
  const dtf = new Intl.DateTimeFormat("en-US", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false, year: "numeric", month: "2-digit", day: "2-digit" });
  const parts = dtf.formatToParts(d).reduce((a, p) => { a[p.type] = p.value; return a; }, {});
  const asUTC = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
  return Math.round((asUTC - d.getTime()) / 60000);
}

export default function Calendar() {
  const { user } = useAuth();
  const [avail, setAvail] = useState({ timezone: "UTC", slots: [] });
  const [viewTz, setViewTz] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [events, setEvents] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const [a, e] = await Promise.all([
          api.get(`/availability/${user.id}`),
          api.get("/calendar/events"),
        ]);
        setAvail(a.data.availability || { timezone: "UTC", slots: [] });
        setEvents(e.data);
      } catch (err) { toast.error(formatErr(err)); }
    })();
  }, [user]);

  const addSlot = () => setAvail({ ...avail, slots: [...avail.slots, { day: 1, start: "09:00", end: "17:00" }] });
  const rmSlot = (i) => setAvail({ ...avail, slots: avail.slots.filter((_, x) => x !== i) });
  const setSlot = (i, k, v) => {
    const s = avail.slots.map((sl, x) => x === i ? { ...sl, [k]: k === "day" ? Number(v) : v } : sl);
    setAvail({ ...avail, slots: s });
  };
  const save = async () => {
    setSaving(true);
    try { await api.put("/availability", avail); toast.success("Availability saved"); }
    catch (e) { toast.error(formatErr(e)); }
    finally { setSaving(false); }
  };

  // Convert slots into viewTz for the weekly grid
  const grid = useMemo(() => {
    const cells = Array.from({ length: 7 }, () => []);
    for (const s of avail.slots) {
      const start = convertHM(s.start, avail.timezone, viewTz);
      const end = convertHM(s.end, avail.timezone, viewTz);
      cells[s.day].push({ start, end });
    }
    return cells;
  }, [avail, viewTz]);

  const totalHrs = avail.slots.reduce((sum, s) => sum + Math.max(0, (toMinutes(s.end) - toMinutes(s.start)) / 60), 0);

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-6 flex-wrap gap-3">
        <div>
          <p className="overline text-[#002FA7] mb-3">CALENDAR & AVAILABILITY</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Your week, on your terms.</h1>
        </div>
        <div className="flex items-center gap-3">
          <GlobeHemisphereEast size={18} weight="duotone" color="#002FA7"/>
          <span className="overline">View timezone</span>
          <select value={viewTz} onChange={(e) => setViewTz(e.target.value)}
                  className="hard-border px-3 py-2 font-mono text-sm bg-white">
            {[viewTz, ...TZS.filter(t => t !== viewTz)].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {/* Availability editor */}
      <section className="hard-border bg-white p-8 shadow-brutal mb-8">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h2 className="font-display font-extrabold text-2xl tracking-tight">Weekly availability</h2>
            <p className="text-sm text-neutral-500">Set slots in your own timezone; the grid re-projects into any viewer&apos;s zone.</p>
          </div>
          <div className="flex items-center gap-3">
            <label className="overline">Your timezone</label>
            <select value={avail.timezone} onChange={(e) => setAvail({ ...avail, timezone: e.target.value })}
                    data-testid={TID.availTimezone}
                    className="hard-border px-3 py-2 font-mono text-sm bg-white">
              {TZS.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div className="space-y-3">
          {avail.slots.map((s, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-3 items-end">
              <div>
                <label className="overline block mb-1">Day</label>
                <select value={s.day} onChange={(e) => setSlot(i, "day", e.target.value)}
                        data-testid={TID.availSlotDay(i)}
                        className="w-full hard-border px-3 py-2 bg-white">
                  {DAYS.map((d, x) => <option key={d} value={x}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="overline block mb-1">Start</label>
                <input type="time" value={s.start} onChange={(e) => setSlot(i, "start", e.target.value)}
                       data-testid={TID.availSlotStart(i)}
                       className="w-full hard-border px-3 py-2 font-mono"/>
              </div>
              <div>
                <label className="overline block mb-1">End</label>
                <input type="time" value={s.end} onChange={(e) => setSlot(i, "end", e.target.value)}
                       data-testid={TID.availSlotEnd(i)}
                       className="w-full hard-border px-3 py-2 font-mono"/>
              </div>
              <button onClick={() => rmSlot(i)} className="hard-border p-2 hover:bg-[#FF0A0A] hover:text-white">
                <X size={16}/>
              </button>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-6">
          <button onClick={addSlot} className="btn-outline text-sm inline-flex items-center gap-2" data-testid={TID.availSlotAdd}>
            <Plus size={14}/> Add slot
          </button>
          <p className="text-sm font-mono text-neutral-500">{totalHrs}h / week capacity</p>
          <button onClick={save} disabled={saving} className="btn-primary" data-testid={TID.availSave}>
            {saving ? "Saving…" : "Save availability"}
          </button>
        </div>
      </section>

      {/* Weekly grid (view timezone) */}
      <section className="hard-border bg-white shadow-brutal overflow-x-auto mb-8">
        <div className="p-6 border-b border-black/10 flex items-center gap-3">
          <Clock size={18} weight="duotone" color="#002FA7"/>
          <h2 className="font-display font-extrabold text-2xl tracking-tight">Weekly view</h2>
          <span className="text-xs text-neutral-500 font-mono ml-auto">Showing in {viewTz}</span>
        </div>
        <div className="grid grid-cols-7 min-w-[720px]">
          {DAYS.map((d, i) => (
            <div key={d} className="border-r border-black/10 last:border-r-0 min-h-[220px]">
              <div className="bg-[#0A0A0A] text-white p-3">
                <p className="overline">{d}</p>
              </div>
              <div className="p-3 space-y-2">
                {grid[i].length === 0 ? (
                  <p className="text-xs text-neutral-400 italic">—</p>
                ) : grid[i].map((sl, x) => (
                  <div key={x} className="hard-border bg-[#002FA7] text-white p-2 font-mono text-xs">
                    {sl.start} — {sl.end}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Events */}
      <section className="hard-border bg-white p-8 shadow-brutal">
        <h2 className="font-display font-extrabold text-2xl tracking-tight mb-4">Upcoming events</h2>
        {events.length === 0 ? (
          <p className="text-neutral-500 text-sm">Nothing scheduled yet.</p>
        ) : (
          <ul className="divide-y divide-black/10">
            {events.slice(0, 10).map((e) => (
              <li key={`${e.type}-${e.id}`} className="py-3 flex justify-between gap-3">
                <div>
                  <p className="font-medium">{e.title}</p>
                  <p className="text-xs text-neutral-500 font-mono uppercase">{e.type} · {e.status || e.source || ""}</p>
                </div>
                <p className="font-mono text-sm">{String(e.date || "").slice(0, 10)}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
