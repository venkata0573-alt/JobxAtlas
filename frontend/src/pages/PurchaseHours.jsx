import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";
import { Clock } from "@phosphor-icons/react";

export default function PurchaseHours() {
  const [pkgs, setPkgs] = useState({});
  useEffect(() => { api.get("/packages").then((r) => setPkgs(r.data)); }, []);

  const buy = async (id) => {
    try {
      const r = await api.post("/payments/checkout", { package_id: id, origin_url: window.location.origin });
      window.location.href = r.data.checkout_url;
    } catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">HOUR PACKAGES</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Fuel your team.</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">Purchase hour bundles once, then mix & match across any talent on the platform.
        Hours never expire while your account is active.</p>

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
        {Object.entries(pkgs).map(([id, p], i) => (
          <div key={id} className={`hard-border bg-white p-8 shadow-brutal ${i===1 ? "md:-translate-y-3" : ""}`}
               data-testid={TID.pkgCard(id)}>
            <div className="hard-border bg-[#002FA7] text-white w-12 h-12 flex items-center justify-center mb-6">
              <Clock size={20} weight="fill"/>
            </div>
            <p className="overline text-neutral-500">{p.name}</p>
            <p className="font-display font-extrabold text-5xl tracking-tight mt-2">{p.hours}<span className="text-lg text-neutral-500">h</span></p>
            <p className="text-3xl font-display font-extrabold mt-3">${p.amount.toLocaleString()}</p>
            <p className="text-xs text-neutral-500 font-mono">${(p.amount/p.hours).toFixed(2)}/hr</p>
            <button onClick={() => buy(id)} className="btn-primary w-full mt-6" data-testid={TID.pkgBuy(id)}>
              Buy {p.name} →
            </button>
          </div>
        ))}
      </div>

      <p className="mt-10 text-xs text-neutral-500 font-mono">Secure checkout by Stripe · Test card 4242 4242 4242 4242 · any future expiry · any CVC</p>
    </main>
  );
}
