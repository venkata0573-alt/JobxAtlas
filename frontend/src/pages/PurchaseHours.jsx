import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";
import { Clock, Bank, CreditCard, Copy, CheckCircle } from "@phosphor-icons/react";

export default function PurchaseHours() {
  const [data, setData] = useState({ packages: {}, bank: {}, usd_to_inr: 83 });
  const [tab, setTab] = useState("card");
  const [bank, setBank] = useState(null);
  const [utr, setUtr] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => { api.get("/packages").then((r) => setData(r.data)); }, []);

  const buyCard = async (id) => {
    try {
      const r = await api.post("/payments/checkout", { package_id: id, origin_url: window.location.origin });
      window.location.href = r.data.checkout_url;
    } catch (e) { toast.error(formatErr(e)); }
  };

  const initBank = async (id) => {
    try {
      const r = await api.post("/payments/bank/initiate", { package_id: id });
      setBank(r.data); setSubmitted(false); setUtr("");
      toast.success("Bank transfer initiated");
    } catch (e) { toast.error(formatErr(e)); }
  };

  const submitUtr = async () => {
    if (!utr.trim()) return toast.error("Enter your UTR / bank reference");
    try {
      await api.post("/payments/bank/submit", { payment_id: bank.payment_id, utr: utr.trim() });
      setSubmitted(true);
      toast.success("Reference submitted. We'll verify & credit your hours within 1 business day.");
    } catch (e) { toast.error(formatErr(e)); }
  };

  const copy = (v) => { navigator.clipboard.writeText(v); toast.success("Copied"); };

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">HOUR PACKAGES</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Fuel your team.</h1>
      <p className="text-neutral-600 max-w-2xl mb-8">
        Card via Stripe (fastest), or a direct bank transfer to our India account (great for Indian companies, GST invoice available).
      </p>

      {/* Tabs */}
      <div className="hard-border inline-flex bg-white mb-8">
        {[
          { id: "card", label: "Pay by card", Icon: CreditCard },
          { id: "bank", label: "Bank transfer (India)", Icon: Bank },
        ].map(({ id, label, Icon }) => (
          <button key={id} onClick={() => setTab(id)}
                  className={`px-5 py-3 border-r border-black last:border-r-0 flex items-center gap-2 font-display font-extrabold text-sm tracking-tight ${tab === id ? "bg-[#0A0A0A] text-white" : "bg-white text-black"}`}
                  data-testid={`pay-tab-${id}`}>
            <Icon size={16} weight="duotone"/> {label}
          </button>
        ))}
      </div>

      {/* Package grid */}
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
        {Object.entries(data.packages || {}).map(([id, p], i) => (
          <div key={id} className={`hard-border bg-white p-8 shadow-brutal ${i===1 ? "md:-translate-y-3" : ""}`}
               data-testid={TID.pkgCard(id)}>
            <div className="hard-border bg-[#002FA7] text-white w-12 h-12 flex items-center justify-center mb-6">
              <Clock size={20} weight="fill"/>
            </div>
            <p className="overline text-neutral-500">{p.name}</p>
            <p className="font-display font-extrabold text-5xl tracking-tight mt-2">{p.hours}<span className="text-lg text-neutral-500">h</span></p>
            {tab === "card" ? (
              <>
                <p className="text-3xl font-display font-extrabold mt-3">${p.amount.toLocaleString()}</p>
                <p className="text-xs text-neutral-500 font-mono">${(p.amount/p.hours).toFixed(2)}/hr</p>
                <button onClick={() => buyCard(id)} className="btn-primary w-full mt-6" data-testid={TID.pkgBuy(id)}>
                  Buy {p.name} →
                </button>
              </>
            ) : (
              <>
                <p className="text-3xl font-display font-extrabold mt-3">₹{p.amount_inr.toLocaleString()}</p>
                <p className="text-xs text-neutral-500 font-mono">≈ ${p.amount.toLocaleString()} · ₹{Math.round(p.amount_inr/p.hours)}/hr</p>
                <button onClick={() => initBank(id)} className="btn-outline w-full mt-6" data-testid={`bank-init-${id}`}>
                  Get bank details →
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      {tab === "card" && (
        <p className="text-xs text-neutral-500 font-mono">Secure card checkout by Stripe · Test card 4242 4242 4242 4242 · any future expiry · any CVC</p>
      )}

      {/* Bank details panel */}
      {tab === "bank" && bank && (
        <section className="hard-border bg-[#FDFCF0] p-8 md:p-12 shadow-brutal mt-4">
          <div className="flex items-center gap-3 mb-4">
            <Bank size={22} weight="duotone" color="#002FA7"/>
            <h2 className="font-display font-extrabold text-2xl tracking-tight">Send ₹{bank.amount_inr.toLocaleString()} to our India account</h2>
          </div>
          <p className="text-sm text-neutral-600 mb-6">Reference: <span className="font-mono font-bold">{bank.reference}</span> (must be quoted exactly).</p>

          <div className="grid md:grid-cols-2 gap-4 mb-8">
            {[
              ["Beneficiary", bank.bank.beneficiary],
              ["Bank", bank.bank.bank],
              ["Branch", bank.bank.branch],
              ["Account No.", bank.bank.account_number],
              ["IFSC", bank.bank.ifsc],
              ["SWIFT (Intl)", bank.bank.swift],
              ["UPI ID", bank.bank.upi],
              ["GSTIN", bank.bank.gstin],
              ["Payment reference", bank.reference],
              ["Amount", `₹${bank.amount_inr.toLocaleString()}`],
            ].map(([k, v]) => (
              <div key={k} className="hard-border bg-white p-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="overline">{k}</p>
                  <p className="font-mono text-sm break-all mt-1">{v}</p>
                </div>
                <button type="button" onClick={() => copy(String(v))} className="hard-border p-2 hover:bg-[#002FA7] hover:text-white flex-shrink-0">
                  <Copy size={14}/>
                </button>
              </div>
            ))}
          </div>

          {!submitted ? (
            <div className="hard-border bg-white p-6">
              <p className="overline mb-3">After you&apos;ve made the transfer</p>
              <p className="text-sm text-neutral-600 mb-3">Paste the UTR / UPI reference from your bank confirmation. We&apos;ll verify and credit your hours within 1 business day.</p>
              <div className="flex flex-col md:flex-row gap-3">
                <input value={utr} onChange={(e) => setUtr(e.target.value)} placeholder="e.g. HDFC1234567890 or UPI ref"
                       className="flex-1 hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7] font-mono"
                       data-testid="bank-utr-input"/>
                <button onClick={submitUtr} className="btn-primary" data-testid="bank-submit-utr">Submit reference →</button>
              </div>
            </div>
          ) : (
            <div className="hard-border bg-[#002FA7] text-white p-6 flex items-center gap-3">
              <CheckCircle size={22} weight="fill"/>
              <p className="font-display font-extrabold tracking-tight">Reference received. We&apos;ll credit your hours once the transfer clears.</p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
