import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { WarningOctagon, CheckCircle, Star, ArrowUp } from "@phosphor-icons/react";
import EngagementChat from "@/components/EngagementChat";

const Rating = ({ v, onChange, disabled }) => (
  <div className="flex gap-1">
    {[1, 2, 3, 4, 5].map((n) => (
      <button key={n} type="button" disabled={disabled}
              onClick={() => onChange && onChange(n)}
              data-testid={TID.reviewRating(n)}
              className={`p-1 ${disabled ? "cursor-default" : "cursor-pointer"}`}>
        <Star size={22} weight={v >= n ? "fill" : "regular"} color={v >= n ? "#FF0A0A" : "#0A0A0A"}/>
      </button>
    ))}
  </div>
);

export default function EngagementDetail() {
  const { id } = useParams();
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [eng, setEng] = useState(null);
  const [sig, setSig] = useState("");
  const [agree, setAgree] = useState(false);
  const [ackOnsite, setAckOnsite] = useState(false);
  const [signing, setSigning] = useState(false);

  const [dels, setDels] = useState([]);
  const [dTitle, setDTitle] = useState("");
  const [dDesc, setDDesc] = useState("");
  const [dLink, setDLink] = useState("");
  const [dHours, setDHours] = useState(1);

  const [rating, setRating] = useState(0);
  const [rText, setRText] = useState("");

  const load = async () => {
    try {
      const r = await api.get(`/engagements/${id}`); setEng(r.data);
      const dr = await api.get(`/deliverables/${id}`); setDels(dr.data);
    } catch (e) { toast.error(formatErr(e)); nav("/"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  if (!eng) return <div className="p-16 font-mono text-center">Loading…</div>;

  const mySide = user?.id === eng.employer_id ? "employer_signature" : "talent_signature";
  const otherSide = mySide === "employer_signature" ? "talent_signature" : "employer_signature";
  const iSigned = !!eng[mySide];
  const otherSigned = !!eng[otherSide];
  const isOnsite = eng.mode && eng.mode !== "remote";
  const canWork = eng.status === "contract_signed";
  const isTalent = user?.id === eng.talent_id;
  const isEmployer = user?.id === eng.employer_id;

  const sign = async (e) => {
    e.preventDefault();
    if (!agree) return toast.error("You must agree to the terms");
    if (isOnsite && !ackOnsite) return toast.error("You must acknowledge the on-site health, safety and transport terms");
    if (sig.trim().length < 2) return toast.error("Please type your full name");
    setSigning(true);
    try {
      const r = await api.post("/engagements/sign", {
        engagement_id: eng.id, signature: sig.trim(),
        onsite_ack: isOnsite ? ackOnsite : false,
      });
      setEng(r.data);
      await refresh();
      toast.success(r.data.status === "contract_signed" ? "Contract fully signed!" : "Signature recorded — awaiting the other party.");
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSigning(false); }
  };

  const submitDeliverable = async (e) => {
    e.preventDefault();
    if (!dTitle.trim()) return toast.error("Add a title");
    try {
      await api.post("/deliverables", {
        engagement_id: eng.id, title: dTitle, description: dDesc,
        link: dLink, hours_claimed: Number(dHours || 0),
      });
      toast.success("Deliverable submitted");
      setDTitle(""); setDDesc(""); setDLink(""); setDHours(1);
      const dr = await api.get(`/deliverables/${eng.id}`); setDels(dr.data);
    } catch (err) { toast.error(formatErr(err)); }
  };

  const actDeliverable = async (did, kind) => {
    try {
      await api.post(`/deliverables/${did}/${kind}`, {});
      toast.success(kind === "approve" ? "Approved" : "Rejected");
      const dr = await api.get(`/deliverables/${eng.id}`); setDels(dr.data);
    } catch (e) { toast.error(formatErr(e)); }
  };

  const submitReview = async (e) => {
    e.preventDefault();
    if (!rating) return toast.error("Please pick a rating");
    try {
      await api.post("/reviews", { engagement_id: eng.id, rating, text: rText });
      toast.success("Review submitted — pending platform moderation");
      setRating(0); setRText("");
    } catch (err) { toast.error(formatErr(err)); }
  };

  const exclusive = new Date(eng.exclusive_until).toLocaleDateString();

  return (
    <main className="max-w-4xl mx-auto px-6 md:px-12 py-16">
      <Link to={user.role === "employer" ? "/employer" : "/talent"} className="text-sm underline underline-offset-4">← Back</Link>
      <p className="overline text-[#002FA7] mt-6 mb-3">ENGAGEMENT CONTRACT</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-2">
        {eng.employer_name} × {eng.talent_name}
      </h1>
      <div className="flex flex-wrap gap-2 mb-8">
        <span className="hard-border px-2 py-1 text-xs font-mono uppercase">{eng.mode || "remote"}</span>
        <span className="hard-border px-2 py-1 text-xs font-mono">{eng.hours_allocated}h</span>
        <span className="hard-border px-2 py-1 text-xs font-mono uppercase">{eng.status.replace(/_/g, " ")}</span>
      </div>

      {/* Contract paper */}
      <article className="mx-auto max-w-3xl bg-[#FDFCF0] hard-border p-8 md:p-12 shadow-brutal">
        <p className="overline mb-6 text-neutral-600">Master Services Agreement · v1.1</p>
        <p className="mb-4 leading-relaxed">
          This engagement is between <strong>{eng.employer_name}</strong> (&quot;Employer&quot;) and <strong>{eng.talent_name}</strong> (&quot;Talent&quot;),
          both operating through TalentHub (&quot;Platform&quot;).
        </p>
        <p className="mb-4 leading-relaxed"><strong>Scope of Work:</strong> {eng.scope}</p>
        <p className="mb-4 leading-relaxed"><strong>Hours Allocated:</strong> {eng.hours_allocated} hours from the Employer&apos;s pre-paid platform balance.</p>
        <p className="mb-4 leading-relaxed"><strong>Work Mode:</strong> {eng.mode || "remote"}
          {isOnsite && eng.location && <> · <strong>Location:</strong> {eng.location}</>}
          {isOnsite && (eng.start_date || eng.end_date) && <> · <strong>Dates:</strong> {eng.start_date || "TBD"} → {eng.end_date || "TBD"}</>}
          {isOnsite && eng.transport && <> · <strong>Transport:</strong> {eng.transport}</>}
        </p>

        {isOnsite && (
          <div className="my-6 hard-border bg-white p-5">
            <div className="flex gap-3 items-start">
              <WarningOctagon size={22} weight="fill" color="#FF0A0A" className="mt-0.5"/>
              <div>
                <p className="overline text-[#FF0A0A]">On-site Terms · Health, Safety, Transport</p>
                <ul className="text-sm leading-relaxed mt-2 list-disc pl-5 space-y-1">
                  <li>Both parties shall comply with all applicable local health &amp; safety laws at the site of work
                      ({eng.location || "as disclosed above"}) and take reasonable responsibility for the well-being of themselves and the other party.</li>
                  <li>The Employer shall provide a safe working environment. The Talent shall follow all
                      reasonable site-specific safety protocols and PPE requirements.</li>
                  <li><strong>Transport:</strong> {eng.transport === "employer" ? "Employer covers all reasonable transport costs." :
                                                    eng.transport === "talent"   ? "Talent covers own transport." :
                                                                                    "Mutually agreed between the parties in writing prior to travel."}</li>
                  <li>Any illegal activity undertaken by either party at the work location — as defined by the
                      laws applicable to that region — is the sole responsibility of the party undertaking it.
                      The Platform assumes no liability, does not condone, and does not support such conduct.</li>
                  <li>The disclosed <strong>duration, location and dates</strong> above are binding. Any material change
                      must be re-agreed via the Platform.</li>
                </ul>
              </div>
            </div>
          </div>
        )}

        <p className="mb-4 leading-relaxed"><strong>Payment:</strong> All fees are settled via the Platform. Direct payments between parties are forbidden.</p>
        <div className="my-6 hard-border bg-white p-5">
          <div className="flex gap-3 items-start">
            <WarningOctagon size={22} weight="fill" color="#FF0A0A" className="mt-0.5"/>
            <div>
              <p className="overline text-[#FF0A0A]">12-Month Exclusivity Clause</p>
              <p className="text-sm leading-relaxed mt-1">
                For 12 months from the effective date (until <strong>{exclusive}</strong>) the Employer shall not
                directly engage, hire or contract the Talent outside the Platform. Reciprocally the Talent shall
                not accept work directly from the Employer outside the Platform during the same period. Breach
                entitles the Platform to a liquidated fee equal to six (6) months of the projected fees.
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
                  {isOnsite && eng[key].onsite_ack && <p className="text-xs text-[#002FA7] mt-1">✓ On-site terms acknowledged</p>}
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
          {isOnsite && (
            <label className="flex items-start gap-2 mt-3 text-sm cursor-pointer">
              <input type="checkbox" checked={ackOnsite} onChange={(e) => setAckOnsite(e.target.checked)}
                     data-testid={TID.contractOnsiteAck} className="mt-1"/>
              <span>I acknowledge the on-site health &amp; safety, transport arrangement, and that any illegal conduct is solely my responsibility — the Platform bears no liability.</span>
            </label>
          )}
          <button type="submit" disabled={signing} data-testid={TID.contractSubmit} className="btn-primary mt-5">
            {signing ? "Signing…" : "Agree & sign →"}
          </button>
        </form>
      )}
      {iSigned && !otherSigned && (
        <p className="mt-6 text-sm text-neutral-500">You&apos;ve signed. Waiting for the other party to countersign.</p>
      )}

      {/* Deliverables tracker */}
      {canWork && (
        <section className="mt-10 hard-border bg-white p-8 shadow-brutal">
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-2">Deliverables tracker</h2>
          <p className="text-sm text-neutral-600 mb-6">
            Talent submits completed work; Employer confirms. Hours claimed by an approved deliverable are logged against the engagement.
          </p>

          {isTalent && (
            <form onSubmit={submitDeliverable} className="grid md:grid-cols-2 gap-4 mb-8 hard-border bg-[#FDFCF0] p-5">
              <div>
                <label className="overline block mb-1">Title</label>
                <input value={dTitle} onChange={(e) => setDTitle(e.target.value)}
                       data-testid={TID.deliverableTitle} required
                       className="w-full hard-border px-3 py-2 bg-white focus:outline-none focus:border-[#002FA7]"/>
              </div>
              <div>
                <label className="overline block mb-1">Link (optional)</label>
                <input value={dLink} onChange={(e) => setDLink(e.target.value)} type="url"
                       data-testid={TID.deliverableLink} placeholder="https://…"
                       className="w-full hard-border px-3 py-2 bg-white font-mono focus:outline-none focus:border-[#002FA7]"/>
              </div>
              <div className="md:col-span-2">
                <label className="overline block mb-1">Description</label>
                <textarea value={dDesc} onChange={(e) => setDDesc(e.target.value)} rows={3}
                          data-testid={TID.deliverableDesc}
                          className="w-full hard-border px-3 py-2 bg-white focus:outline-none focus:border-[#002FA7]"/>
              </div>
              <div>
                <label className="overline block mb-1">Hours claimed</label>
                <input type="number" min="0" step="0.5" value={dHours} onChange={(e) => setDHours(e.target.value)}
                       data-testid={TID.deliverableHours}
                       className="w-full hard-border px-3 py-2 bg-white font-mono focus:outline-none focus:border-[#002FA7]"/>
              </div>
              <div className="flex items-end">
                <button type="submit" className="btn-primary w-full" data-testid={TID.deliverableSubmit}>
                  <ArrowUp weight="bold" size={14} className="inline mr-1"/> Submit deliverable
                </button>
              </div>
            </form>
          )}

          {dels.length === 0 ? (
            <p className="text-sm text-neutral-500">No deliverables submitted yet.</p>
          ) : (
            <div className="divide-y divide-black/10">
              {dels.map((d) => (
                <div key={d.id} className="py-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="font-display font-extrabold text-lg tracking-tight">{d.title}</p>
                      {d.description && <p className="text-sm text-neutral-600 mt-1">{d.description}</p>}
                      {d.link && <a href={d.link} target="_blank" rel="noreferrer" className="text-xs underline underline-offset-4 font-mono">{d.link}</a>}
                      <p className="text-xs text-neutral-500 mt-2 font-mono">{d.hours_claimed}h · {new Date(d.submitted_at).toLocaleString()}</p>
                    </div>
                    <div className="text-right flex flex-col items-end gap-2">
                      <span className="hard-border px-2 py-1 text-xs uppercase">{d.status}</span>
                      {isEmployer && d.status === "submitted" && (
                        <div className="flex gap-2">
                          <button onClick={() => actDeliverable(d.id, "approve")} className="btn-primary text-xs px-3 py-2"
                                  data-testid={TID.deliverableApprove(d.id)}>Approve</button>
                          <button onClick={() => actDeliverable(d.id, "reject")} className="btn-outline text-xs px-3 py-2"
                                  data-testid={TID.deliverableReject(d.id)}>Reject</button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Reviews */}
      {canWork && (
        <section className="mt-10 hard-border bg-white p-8 shadow-brutal">
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-2">Leave a review</h2>
          <p className="text-sm text-neutral-600 mb-4">Both parties may rate each other once. Reviews are moderated by the Platform before appearing publicly.</p>
          <form onSubmit={submitReview} className="space-y-4">
            <Rating v={rating} onChange={setRating}/>
            <textarea value={rText} onChange={(e) => setRText(e.target.value)} rows={3}
                      data-testid={TID.reviewText}
                      placeholder="What went well? Anything the other party could improve?"
                      className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
            <button type="submit" className="btn-primary" data-testid={TID.reviewSubmit}>Submit for moderation →</button>
          </form>
        </section>
      )}

      <div className="mt-10 text-sm text-center">
        Have a concern? <Link to="/grievance" className="underline underline-offset-4">Raise a formal grievance →</Link>
      </div>

      {canWork && <EngagementChat engagementId={eng.id}/>}
    </main>
  );
}
