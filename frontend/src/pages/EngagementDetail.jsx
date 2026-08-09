import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { WarningOctagon, CheckCircle } from "@phosphor-icons/react";

export default function EngagementDetail() {
  const { id } = useParams();
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [eng, setEng] = useState(null);
  const [sig, setSig] = useState("");
  const [agree, setAgree] = useState(false);
  const [signing, setSigning] = useState(false);

  const load = async () => {
    try { const r = await api.get(`/engagements/${id}`); setEng(r.data); }
    catch (e) { toast.error(formatErr(e)); nav("/"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  if (!eng) return <div className="p-16 font-mono text-center">Loading…</div>;

  const mySide = user?.id === eng.employer_id ? "employer_signature" : "talent_signature";
  const otherSide = mySide === "employer_signature" ? "talent_signature" : "employer_signature";
  const iSigned = !!eng[mySide];
  const otherSigned = !!eng[otherSide];

  const sign = async (e) => {
    e.preventDefault();
    if (!agree) return toast.error("You must agree to the terms");
    if (sig.trim().length < 2) return toast.error("Please type your full name");
    setSigning(true);
    try {
      const r = await api.post("/engagements/sign", { engagement_id: eng.id, signature: sig.trim() });
      setEng(r.data);
      await refresh();
      toast.success(r.data.status === "contract_signed" ? "Contract fully signed!" : "Signature recorded — awaiting the other party.");
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSigning(false); }
  };

  const exclusive = new Date(eng.exclusive_until).toLocaleDateString();

  return (
    <main className="max-w-4xl mx-auto px-6 md:px-12 py-16">
      <Link to={user.role === "employer" ? "/employer" : "/talent"} className="text-sm underline underline-offset-4">← Back</Link>
      <p className="overline text-[#002FA7] mt-6 mb-3">ENGAGEMENT CONTRACT</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-8">
        {eng.employer_name} × {eng.talent_name}
      </h1>

      {/* Contract paper */}
      <article className="mx-auto max-w-3xl bg-[#FDFCF0] hard-border p-8 md:p-12 shadow-brutal">
        <p className="overline mb-6 text-neutral-600">Master Services Agreement · v1.0</p>
        <p className="mb-4 leading-relaxed">
          This engagement is between <strong>{eng.employer_name}</strong> (&quot;Employer&quot;) and <strong>{eng.talent_name}</strong> (&quot;Talent&quot;),
          both operating through TalentHub (&quot;Platform&quot;).
        </p>
        <p className="mb-4 leading-relaxed"><strong>Scope of Work:</strong> {eng.scope}</p>
        <p className="mb-4 leading-relaxed"><strong>Hours Allocated:</strong> {eng.hours_allocated} hours, deducted from the Employer&apos;s pre-paid platform balance.</p>
        <p className="mb-4 leading-relaxed"><strong>Payment:</strong> All fees are settled via the Platform. Direct payments between parties are forbidden.</p>
        <div className="my-6 hard-border bg-white p-5">
          <div className="flex gap-3 items-start">
            <WarningOctagon size={22} weight="fill" color="#FF0A0A" className="mt-0.5"/>
            <div>
              <p className="overline text-[#FF0A0A]">12-Month Exclusivity Clause</p>
              <p className="text-sm leading-relaxed mt-1">
                For a period of 12 months from the effective date of this contract (until <strong>{exclusive}</strong>),
                the Employer shall not directly engage, hire, or contract the Talent outside the Platform. Reciprocally,
                the Talent shall not accept work directly from the Employer outside the Platform during the same period.
                Breach entitles the Platform to a liquidated fee equal to six (6) months of the projected fees.
              </p>
            </div>
          </div>
        </div>
        <p className="mb-4 leading-relaxed"><strong>Confidentiality:</strong> Standard mutual NDA applies to all shared materials.</p>
        <p className="mb-8 leading-relaxed"><strong>Termination:</strong> Either party may terminate for cause with 7 days notice. Unused hours revert to the Employer&apos;s balance.</p>

        {/* Signatures */}
        <div className="grid md:grid-cols-2 gap-6 mt-10">
          {[["Employer signature", "employer_signature", eng.employer_name],
            ["Talent signature", "talent_signature", eng.talent_name]].map(([label, key, who]) => (
            <div key={key} className="hard-border p-5 bg-white">
              <p className="overline mb-2">{label}</p>
              {eng[key] ? (
                <>
                  <p className="font-signature text-4xl">{eng[key].name}</p>
                  <p className="text-xs text-neutral-500 mt-2 font-mono">Signed by {who} · {new Date(eng[key].signed_at).toLocaleString()}</p>
                </>
              ) : (
                <p className="text-neutral-400 italic">Awaiting signature…</p>
              )}
            </div>
          ))}
        </div>

        {eng.status === "contract_signed" && (
          <div className="mt-8 hard-border bg-[#002FA7] text-white p-4 flex items-center gap-3">
            <CheckCircle size={22} weight="fill"/>
            <p className="font-display font-extrabold tracking-tight">Contract fully executed. Work may begin.</p>
          </div>
        )}
      </article>

      {/* Sign form */}
      {!iSigned && (
        <form onSubmit={sign} className="mt-8 hard-border bg-white p-8 shadow-brutal">
          <p className="overline text-[#002FA7] mb-3">Your signature</p>
          <input data-testid={TID.contractSignature} value={sig} onChange={(e) => setSig(e.target.value)}
                 placeholder="Type your full legal name"
                 className="w-full hard-border px-3 py-4 focus:outline-none focus:border-[#002FA7] font-signature text-3xl"/>
          <label className="flex items-start gap-2 mt-4 text-sm cursor-pointer">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)}
                   data-testid={TID.contractAgree} className="mt-1"/>
            <span>I agree to the terms above, including the 12-month exclusivity clause. My typed name constitutes a legally binding electronic signature.</span>
          </label>
          <button type="submit" disabled={signing} data-testid={TID.contractSubmit} className="btn-primary mt-5">
            {signing ? "Signing…" : "Agree & sign →"}
          </button>
        </form>
      )}
      {iSigned && !otherSigned && (
        <p className="mt-6 text-sm text-neutral-500">You&apos;ve signed. Waiting for the other party to countersign.</p>
      )}
    </main>
  );
}
