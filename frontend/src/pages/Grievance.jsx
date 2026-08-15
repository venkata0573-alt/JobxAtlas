import React, { useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { EnvelopeSimple, WarningOctagon, CheckCircle } from "@phosphor-icons/react";

export default function Grievance() {
  const { user } = useAuth();
  const [f, setF] = useState({
    subject: "", engagement_id: "", against_party_id: "", incident_date: "",
    description: "", contact_email: user?.email || "",
  });
  const [ref, setRef] = useState(null);
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (!f.subject.trim() || !f.description.trim() || !f.contact_email.trim()) {
      return toast.error("Subject, description and contact email are required");
    }
    setLoading(true);
    try {
      const r = await api.post("/grievances", f);
      setRef(r.data);
      toast.success("Grievance recorded");
    } catch (err) { toast.error(formatErr(err)); }
    finally { setLoading(false); }
  };

  if (ref) {
    return (
      <main className="max-w-2xl mx-auto px-6 py-24">
        <div className="hard-border bg-white p-10 shadow-brutal text-center">
          <div className="mx-auto hard-border bg-[#6B21A8] text-white w-14 h-14 flex items-center justify-center mb-4">
            <CheckCircle size={26} weight="fill"/>
          </div>
          <h1 className="font-display font-extrabold text-3xl tracking-tight mb-2">Grievance submitted</h1>
          <p className="text-neutral-600 mb-4">
            Reference: <span className="font-mono font-bold">{ref.reference}</span>
          </p>
          <p className="text-sm text-neutral-500 mb-6">
            A copy has been routed to <span className="font-mono">{ref.email_to}</span>. Our moderation team will contact you
            at <span className="font-mono">{f.contact_email}</span> within 3 business days.
          </p>
          <button onClick={() => { setRef(null); setF({ ...f, subject: "", description: "" }); }} className="btn-outline text-sm">
            Submit another
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#6B21A8] mb-3">GRIEVANCE FORM</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">
        Speak up. In writing.
      </h1>
      <p className="text-neutral-600 mb-6 max-w-2xl">
        Please provide as much detail as possible. All grievances are reviewed by the platform&apos;s moderation team;
        we will not share your submission with the other party without your consent.
      </p>

      <div className="hard-border bg-[#F5F3FF] p-5 mb-8 flex items-start gap-3">
        <WarningOctagon size={22} weight="fill" color="#6B21A8"/>
        <p className="text-sm">
          For emergencies, contact local authorities first. This form is for platform-related grievances only.
        </p>
      </div>

      <form onSubmit={submit} className="hard-border bg-white p-8 shadow-brutal space-y-5">
        <div>
          <label className="overline block mb-2">Subject</label>
          <input value={f.subject} onChange={set("subject")} data-testid={TID.grievanceSubject} required
                 placeholder="One-line summary"
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="overline block mb-2">Engagement ID (optional)</label>
            <input value={f.engagement_id} onChange={set("engagement_id")}
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono text-sm"/>
          </div>
          <div>
            <label className="overline block mb-2">Against party ID (optional)</label>
            <input value={f.against_party_id} onChange={set("against_party_id")}
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono text-sm"/>
          </div>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="overline block mb-2">Incident date</label>
            <input value={f.incident_date} onChange={set("incident_date")} type="date"
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono"/>
          </div>
          <div>
            <label className="overline block mb-2">Your contact email</label>
            <input value={f.contact_email} onChange={set("contact_email")} type="email" required
                   data-testid={TID.grievanceEmail}
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
          </div>
        </div>
        <div>
          <label className="overline block mb-2">Description</label>
          <textarea value={f.description} onChange={set("description")} rows={7} required
                    data-testid={TID.grievanceDescription}
                    placeholder="What happened, when, and how it has affected you or your engagement?"
                    className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
        </div>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <p className="text-xs text-neutral-500 flex items-center gap-2 font-mono">
            <EnvelopeSimple size={14}/> Will be routed to grievance@talenthub.io
          </p>
          <button type="submit" disabled={loading} className="btn-primary" data-testid={TID.grievanceSubmit}>
            {loading ? "Submitting…" : "Submit grievance →"}
          </button>
        </div>
      </form>
    </main>
  );
}
