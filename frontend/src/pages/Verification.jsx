import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { ShieldCheck, Plus, X, CheckCircle, WarningCircle, Envelope } from "@phosphor-icons/react";

export default function Verification() {
  const { user } = useAuth();
  const [state, setState] = useState(null);
  const [resending, setResending] = useState(false);

  const load = async () => {
    try { const r = await api.get("/verification/me"); setState(r.data); }
    catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); }, []);

  const resend = async () => {
    setResending(true);
    try { await api.post("/auth/resend-verification"); toast.success("Verification email re-sent"); }
    catch (e) { toast.error(formatErr(e)); }
    finally { setResending(false); }
  };

  if (!state) return <main className="max-w-3xl mx-auto p-16 text-center"><p className="font-mono text-neutral-500">Loading…</p></main>;

  const status = state.verification_status || "none";
  const isVerified = status === "verified";
  const isPending = status === "pending";
  const isRejected = status === "rejected";

  return (
    <main className="max-w-3xl mx-auto p-8 md:p-16" data-testid="verification-page">
      <p className="overline text-[#C79A3B] mb-2">TRUST & SAFETY</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Verify your profile</h1>
      <p className="text-sm text-neutral-600 mb-8">
        Verified {user?.role === "employer" ? "companies" : "talents"} appear ahead in search + get a {user?.role === "employer" ? "golden star" : "blue tick"} on every card. Verified accounts convert at 3× the unverified rate.
      </p>

      {/* Email verification banner */}
      <div className={`hard-border p-5 mb-6 shadow-brutal ${state.email_verified ? "bg-[#EDF7EE]" : "bg-[#FEF0F0] border-red-300"}`} data-testid="email-verification-banner">
        <div className="flex items-center gap-3">
          {state.email_verified
            ? <CheckCircle size={22} weight="fill" color="#10B981"/>
            : <Envelope size={22} weight="fill" color="#B03A2E"/>}
          <div className="flex-1">
            <p className="font-display font-extrabold text-lg">
              {state.email_verified ? "Email verified" : "Email not yet verified"}
            </p>
            {!state.email_verified && (
              <p className="text-xs text-neutral-600 mt-1">Check your inbox for the confirmation link, or resend it below.</p>
            )}
          </div>
          {!state.email_verified && (
            <button onClick={resend} disabled={resending}
                    className="btn-outline text-xs" data-testid="resend-verification-btn">
              {resending ? "Sending…" : "Resend link"}
            </button>
          )}
        </div>
      </div>

      {/* Profile verification status */}
      <div className={`hard-border p-5 mb-6 shadow-brutal ${isVerified ? "bg-[#EDF7EE]" : isPending ? "bg-[#FDF6E3]" : isRejected ? "bg-[#FEF0F0]" : "bg-white"}`} data-testid="profile-verification-status">
        <div className="flex items-center gap-3 mb-1">
          <ShieldCheck size={22} weight="fill" color={isVerified ? "#10B981" : isPending ? "#C79A3B" : "#666"}/>
          <p className="font-display font-extrabold text-lg">
            {isVerified && (user?.role === "employer" ? "Verified company ✦" : "Verified talent ✓")}
            {isPending && "Verification pending review"}
            {isRejected && "Verification rejected"}
            {status === "none" && "Not yet submitted"}
          </p>
        </div>
        {isRejected && state.verification_notes && (
          <p className="text-sm text-red-800 mt-2">Reason: {state.verification_notes}</p>
        )}
        {isPending && (
          <p className="text-xs text-neutral-500 mt-2">Our ops team usually clears verifications within 24 business hours.</p>
        )}
      </div>

      {/* Submit form (only if not verified + not pending) */}
      {!isVerified && !isPending && (
        user?.role === "employer" ? <CompanyForm profile={state.profile} onDone={load}/>
                                  : <BgvForm profile={state.profile} onDone={load}/>
      )}
    </main>
  );
}

function CompanyForm({ profile, onDone }) {
  const [f, setF] = useState({
    company_name: profile?.company_name || "",
    company_registration_number: profile?.company_registration_number || "",
    tax_id: profile?.tax_id || "",
    company_website: profile?.company_website || "",
    company_size: profile?.company_size || "",
    year_founded: profile?.year_founded || "",
    country: profile?.country || "",
  });
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/verification/company", { ...f, year_founded: Number(f.year_founded) || null });
      toast.success("Submitted for review");
      onDone();
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSaving(false); }
  };
  return (
    <form onSubmit={submit} className="hard-border bg-white p-6 shadow-brutal space-y-4" data-testid="company-verification-form">
      <p className="font-display font-extrabold text-xl">Company details</p>
      <div className="grid md:grid-cols-2 gap-3">
        <input required placeholder="Legal company name" value={f.company_name} onChange={(e) => setF({...f, company_name: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="vc-name"/>
        <input placeholder="Company registration #" value={f.company_registration_number} onChange={(e) => setF({...f, company_registration_number: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="vc-reg"/>
        <input placeholder="Tax ID / GSTIN" value={f.tax_id} onChange={(e) => setF({...f, tax_id: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="vc-tax"/>
        <input placeholder="Website" value={f.company_website} onChange={(e) => setF({...f, company_website: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="vc-web"/>
        <select value={f.company_size} onChange={(e) => setF({...f, company_size: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="vc-size">
          <option value="">Company size…</option>
          {["1-10", "11-50", "51-200", "201-1000", "1000+"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input placeholder="Year founded" value={f.year_founded} onChange={(e) => setF({...f, year_founded: e.target.value})} className="hard-border px-3 py-2 text-sm" data-testid="vc-year"/>
        <input placeholder="Country of registration" value={f.country} onChange={(e) => setF({...f, country: e.target.value})} className="hard-border px-3 py-2 text-sm md:col-span-2" data-testid="vc-country"/>
      </div>
      <p className="text-xs text-neutral-500">By submitting you confirm the information is accurate. Job Atlas will verify against public records + a follow-up call.</p>
      <button type="submit" disabled={saving} className="btn-primary text-sm" data-testid="submit-company-verification">
        {saving ? "Submitting…" : "Submit for review"}
      </button>
    </form>
  );
}

function BgvForm({ profile, onDone }) {
  const [works, setWorks] = useState(profile?.work_history?.length ? profile.work_history : [{ company: "", role: "", start: "", end: "", description: "" }]);
  const [refs, setRefs] = useState(profile?.references?.length ? profile.references : [{ name: "", email: "", relationship: "", company: "", phone: "" }, { name: "", email: "", relationship: "", company: "", phone: "" }]);
  const [linkedin, setLinkedin] = useState(profile?.linkedin_url || "");
  const [saving, setSaving] = useState(false);

  const addWork = () => setWorks([...works, { company: "", role: "", start: "", end: "", description: "" }]);
  const addRef = () => setRefs([...refs, { name: "", email: "", relationship: "", company: "", phone: "" }]);
  const removeWork = (i) => setWorks(works.filter((_, idx) => idx !== i));
  const removeRef = (i) => refs.length > 2 && setRefs(refs.filter((_, idx) => idx !== i));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/verification/bgv", { work_history: works, references: refs, linkedin_url: linkedin });
      toast.success("Submitted for background verification");
      onDone();
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSaving(false); }
  };
  return (
    <form onSubmit={submit} className="hard-border bg-white p-6 shadow-brutal space-y-6" data-testid="bgv-form">
      <div>
        <p className="font-display font-extrabold text-xl mb-2">Work history</p>
        <p className="text-xs text-neutral-500 mb-3">Add every role from the last 5 years. We verify the last two.</p>
        <div className="space-y-3">
          {works.map((w, i) => (
            <div key={i} className="hard-border bg-[#FAF9F6] p-3 space-y-2" data-testid={`work-${i}`}>
              <div className="grid md:grid-cols-2 gap-2">
                <input required placeholder="Company" value={w.company} onChange={(e) => { const c=[...works]; c[i].company=e.target.value; setWorks(c);}} className="hard-border px-3 py-2 text-sm"/>
                <input required placeholder="Role" value={w.role} onChange={(e) => { const c=[...works]; c[i].role=e.target.value; setWorks(c);}} className="hard-border px-3 py-2 text-sm"/>
                <input required type="date" placeholder="Start" value={w.start} onChange={(e) => { const c=[...works]; c[i].start=e.target.value; setWorks(c);}} className="hard-border px-3 py-2 text-sm"/>
                <input type="date" placeholder="End (blank if current)" value={w.end || ""} onChange={(e) => { const c=[...works]; c[i].end=e.target.value; setWorks(c);}} className="hard-border px-3 py-2 text-sm"/>
              </div>
              {works.length > 1 && (
                <button type="button" onClick={() => removeWork(i)} className="text-xs text-neutral-500 hover:text-red-700 inline-flex items-center gap-1"><X size={10}/> Remove</button>
              )}
            </div>
          ))}
        </div>
        <button type="button" onClick={addWork} className="btn-outline text-xs mt-3 inline-flex items-center gap-1" data-testid="add-work"><Plus size={12}/> Add role</button>
      </div>

      <div>
        <p className="font-display font-extrabold text-xl mb-2">References (min 2)</p>
        <p className="text-xs text-neutral-500 mb-3">A recent manager + a recent peer works best. We contact them directly.</p>
        <div className="space-y-3">
          {refs.map((r, i) => (
            <div key={i} className="hard-border bg-[#FAF9F6] p-3 space-y-2" data-testid={`ref-${i}`}>
              <div className="grid md:grid-cols-2 gap-2">
                <input required placeholder="Name" value={r.name} onChange={(e) => { const c=[...refs]; c[i].name=e.target.value; setRefs(c);}} className="hard-border px-3 py-2 text-sm"/>
                <input required type="email" placeholder="Email" value={r.email} onChange={(e) => { const c=[...refs]; c[i].email=e.target.value; setRefs(c);}} className="hard-border px-3 py-2 text-sm"/>
                <input required placeholder="Relationship (e.g. Manager)" value={r.relationship} onChange={(e) => { const c=[...refs]; c[i].relationship=e.target.value; setRefs(c);}} className="hard-border px-3 py-2 text-sm"/>
                <input placeholder="Company (optional)" value={r.company || ""} onChange={(e) => { const c=[...refs]; c[i].company=e.target.value; setRefs(c);}} className="hard-border px-3 py-2 text-sm"/>
              </div>
              {refs.length > 2 && (
                <button type="button" onClick={() => removeRef(i)} className="text-xs text-neutral-500 hover:text-red-700 inline-flex items-center gap-1"><X size={10}/> Remove</button>
              )}
            </div>
          ))}
        </div>
        <button type="button" onClick={addRef} className="btn-outline text-xs mt-3 inline-flex items-center gap-1" data-testid="add-ref"><Plus size={12}/> Add reference</button>
      </div>

      <div>
        <label className="overline block mb-1">LinkedIn URL (optional)</label>
        <input value={linkedin} onChange={(e) => setLinkedin(e.target.value)} placeholder="https://linkedin.com/in/…" className="hard-border px-3 py-2 text-sm w-full" data-testid="bgv-linkedin"/>
      </div>

      <button type="submit" disabled={saving} className="btn-primary text-sm" data-testid="submit-bgv">
        {saving ? "Submitting…" : "Submit for BGV"}
      </button>
    </form>
  );
}
