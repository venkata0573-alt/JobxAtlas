import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import DashboardMetrics from "@/components/DashboardMetrics";

export default function TalentDashboard() {
  const { user } = useAuth();
  const [engs, setEngs] = useState([]);
  const [metrics, setMetrics] = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const [a, m] = await Promise.all([api.get("/engagements"), api.get("/dashboard/metrics")]);
        setEngs(a.data); setMetrics(m.data);
      } catch (e) { toast.error(formatErr(e)); }
    })();
  }, []);

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <div className="flex items-baseline justify-between mb-10 flex-wrap gap-4">
        <div>
          <p className="overline text-[#002FA7] mb-3">TALENT DASHBOARD</p>
          <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Hey {user?.name?.split(" ")[0]}.</h1>
          <p className="text-neutral-600 mt-2">Everything you&apos;re working on — in one grid.</p>
        </div>
        <Link to="/talent/profile" className="btn-outline text-sm">Edit profile →</Link>
      <Link to="/talent/earnings" className="btn-outline text-sm ml-2">View earnings →</Link>
      </div>

      <DashboardMetrics metrics={metrics} role="talent"/>

      <section className="hard-border bg-white p-8 shadow-brutal mt-8">
        <h2 className="font-display font-extrabold text-2xl tracking-tight mb-6">Engagements</h2>
        {engs.length === 0 ? (
          <p className="text-neutral-500">No engagements yet. Employers who purchase hours will invite you here.</p>
        ) : (
          <div className="divide-y divide-black/10">
            {engs.map((e) => (
              <div key={e.id} className="py-4 flex items-center justify-between gap-4" data-testid={TID.engagementRow(e.id)}>
                <div>
                  <p className="font-display font-extrabold text-lg tracking-tight">{e.employer_name}</p>
                  <p className="text-sm text-neutral-500">{e.scope}</p>
                </div>
                <div className="text-right">
                  <p className="font-mono text-sm">{e.hours_allocated}h · {e.status.replace(/_/g, " ")}</p>
                  <Link to={`/engagement/${e.id}`} className="text-xs underline underline-offset-4" data-testid={TID.contractOpen(e.id)}>Open →</Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
