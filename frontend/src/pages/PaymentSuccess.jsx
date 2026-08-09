import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CheckCircle } from "@phosphor-icons/react";

export default function PaymentSuccess() {
  const [params] = useSearchParams();
  const sid = params.get("session_id");
  const [status, setStatus] = useState({ payment_status: "pending", hours: 0 });
  const { refresh } = useAuth();

  useEffect(() => {
    if (!sid) return;
    let cancelled = false; let tries = 0;
    const poll = async () => {
      try {
        const r = await api.get(`/payments/status/${sid}`);
        if (cancelled) return;
        setStatus(r.data);
        if (r.data.payment_status === "paid") { await refresh(); return; }
        if (++tries < 12) setTimeout(poll, 2000);
      } catch { if (++tries < 12) setTimeout(poll, 2000); }
    };
    poll();
    return () => { cancelled = true; };
  }, [sid, refresh]);

  const paid = status.payment_status === "paid";
  return (
    <main className="max-w-2xl mx-auto px-6 py-24 text-center">
      <div className="hard-border bg-white p-12 shadow-brutal">
        <div className="mx-auto w-16 h-16 hard-border flex items-center justify-center mb-6" style={{background: paid ? "#002FA7" : "#F9F9F9", color: paid ? "#fff" : "#0A0A0A"}}>
          <CheckCircle size={30} weight="fill"/>
        </div>
        <h1 className="font-display font-extrabold text-3xl tracking-tight mb-2">
          {paid ? "Payment received." : "Verifying payment…"}
        </h1>
        <p className="text-neutral-600 mb-6">
          {paid ? `${status.hours} hours credited to your balance.` : "Hang tight — this usually takes a couple of seconds."}
        </p>
        <Link to="/employer" className="btn-primary">Back to dashboard →</Link>
      </div>
    </main>
  );
}
