import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { BACKEND_URL } from "@/config";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { WarningOctagon, CheckCircle, Star, ArrowUp, ArrowsCounterClockwise, Gavel, X } from "@phosphor-icons/react";
import EngagementChat from "@/components/EngagementChat";

const Rating = ({ v, onChange, disabled }) => (
  <div className="flex gap-1">
    {[1, 2, 3, 4, 5].map((n) => (
      <button key={n} type="button" disabled={disabled}
              onClick={() => onChange && onChange(n)}
              data-testid={TID.reviewRating(n)}
              className={`p-1 ${disabled ? "cursor-default" : "cursor-pointer"}`}>
        <Star size={22} weight={v >= n ? "fill" : "regular"} color={v >= n ? "#6B21A8" : "#0A0A0A"}/>
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
  const [dFiles, setDFiles] = useState([]);      // uploaded file ids
  const [dUploading, setDUploading] = useState(false);

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
        file_ids: dFiles.map(f => f.file_id),
      });
      toast.success("Deliverable submitted");
      setDTitle(""); setDDesc(""); setDLink(""); setDHours(1); setDFiles([]);
      const dr = await api.get(`/deliverables/${eng.id}`); setDels(dr.data);
    } catch (err) { toast.error(formatErr(err)); }
  };

  const attachToDeliverable = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    const form = new FormData(); form.append("file", f); form.append("kind", "deliverable");
    setDUploading(true);
    try {
      const r = await api.post("/files/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      setDFiles((x) => [...x, { file_id: r.data.file_id, name: r.data.name }]);
      toast.success("Attached");
    } catch (err) { toast.error(formatErr(err)); }
    finally { setDUploading(false); e.target.value = ""; }
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
      <p className="overline text-[#6B21A8] mt-6 mb-3">ENGAGEMENT CONTRACT</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-2">
        {eng.employer_name} × {eng.talent_name}
      </h1>
      <div className="flex flex-wrap gap-2 mb-8">
        <span className="hard-border px-2 py-1 text-xs font-mono uppercase">{eng.mode || "remote"}</span>
        <span className="hard-border px-2 py-1 text-xs font-mono">{eng.hours_allocated}h</span>
        <span className="hard-border px-2 py-1 text-xs font-mono uppercase">{eng.status.replace(/_/g, " ")}</span>
      </div>

      {/* Contract paper */}
      <article className="mx-auto max-w-3xl bg-[#F5F3FF] hard-border p-8 md:p-12 shadow-brutal">
        <p className="overline mb-6 text-neutral-600">Master Services Agreement · v1.1</p>
        <p className="mb-4 leading-relaxed">
          This engagement is between <strong>{eng.employer_name}</strong> (&quot;Employer&quot;) and <strong>{eng.talent_name}</strong> (&quot;Talent&quot;),
          both operating through Job Atlas (&quot;Platform&quot;).
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
              <WarningOctagon size={22} weight="fill" color="#6B21A8" className="mt-0.5"/>
              <div>
                <p className="overline text-[#6B21A8]">On-site Terms · Health, Safety, Transport</p>
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
            <WarningOctagon size={22} weight="fill" color="#6B21A8" className="mt-0.5"/>
            <div>
              <p className="overline text-[#6B21A8]">12-Month Exclusivity Clause</p>
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
                  {isOnsite && eng[key].onsite_ack && <p className="text-xs text-[#6B21A8] mt-1">✓ On-site terms acknowledged</p>}
                </>
              ) : (
                <p className="text-neutral-400 italic">Awaiting signature…</p>
              )}
            </div>
          ))}
        </div>

        {eng.status === "contract_signed" && (
          <div className="mt-8 hard-border bg-[#6B21A8] text-white p-4 flex items-center gap-3">
            <CheckCircle size={22} weight="fill"/>
            <p className="font-display font-extrabold tracking-tight">Contract fully executed. Work may begin.</p>
          </div>
        )}
      </article>

      {/* Sign form */}
      {!iSigned && (
        <form onSubmit={sign} className="mt-8 hard-border bg-white p-8 shadow-brutal">
          <p className="overline text-[#6B21A8] mb-3">Your signature</p>
          <input data-testid={TID.contractSignature} value={sig} onChange={(e) => setSig(e.target.value)}
                 placeholder="Type your full legal name"
                 className="w-full hard-border px-3 py-4 focus:outline-none focus:border-[#6B21A8] font-signature text-3xl"/>
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
            <form onSubmit={submitDeliverable} className="grid md:grid-cols-2 gap-4 mb-8 hard-border bg-[#F5F3FF] p-5">
              <div>
                <label className="overline block mb-1">Title</label>
                <input value={dTitle} onChange={(e) => setDTitle(e.target.value)}
                       data-testid={TID.deliverableTitle} required
                       className="w-full hard-border px-3 py-2 bg-white focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <div>
                <label className="overline block mb-1">Link (optional)</label>
                <input value={dLink} onChange={(e) => setDLink(e.target.value)} type="url"
                       data-testid={TID.deliverableLink} placeholder="https://…"
                       className="w-full hard-border px-3 py-2 bg-white font-mono focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <div className="md:col-span-2">
                <label className="overline block mb-1">Description</label>
                <textarea value={dDesc} onChange={(e) => setDDesc(e.target.value)} rows={3}
                          data-testid={TID.deliverableDesc}
                          className="w-full hard-border px-3 py-2 bg-white focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <div>
                <label className="overline block mb-1">Hours claimed</label>
                <input type="number" min="0" step="0.5" value={dHours} onChange={(e) => setDHours(e.target.value)}
                       data-testid={TID.deliverableHours}
                       className="w-full hard-border px-3 py-2 bg-white font-mono focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <div className="flex items-end">
                <button type="submit" className="btn-primary w-full" data-testid={TID.deliverableSubmit}>
                  <ArrowUp weight="bold" size={14} className="inline mr-1"/> Submit deliverable
                </button>
              </div>
              <div className="md:col-span-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <label className="btn-outline text-xs inline-flex items-center gap-2 cursor-pointer">
                    📎 {dUploading ? "Uploading…" : "Attach file"}
                    <input type="file" className="hidden" accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.csv" onChange={attachToDeliverable}/>
                  </label>
                  {dFiles.map((f, x) => (
                    <span key={x} className="hard-border px-2 py-1 text-xs font-mono bg-white">📎 {f.name}</span>
                  ))}
                </div>
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
                      {d.file_ids && d.file_ids.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {d.file_ids.map((fid) => (
                            <a key={fid} href={`${BACKEND_URL}/api/files/${fid}`} target="_blank" rel="noreferrer"
                               className="hard-border bg-white px-2 py-1 text-xs font-mono inline-flex items-center gap-1 hover:bg-[#0B1B2B] hover:text-white">
                              📎 attachment
                            </a>
                          ))}
                        </div>
                      )}
                      <p className="text-xs text-neutral-500 mt-2 font-mono">{d.hours_claimed}h · {new Date(d.submitted_at).toLocaleString()}</p>
                    </div>
                    <div className="text-right flex flex-col items-end gap-2">
                      <span className="hard-border px-2 py-1 text-xs uppercase">{d.status.replace(/_/g, " ")}</span>
                      {isEmployer && (d.status === "submitted" || d.status === "revision_resubmitted") && (
                        <div className="flex gap-2 flex-wrap justify-end">
                          <button onClick={() => actDeliverable(d.id, "approve")} className="btn-primary text-xs px-3 py-2"
                                  data-testid={TID.deliverableApprove(d.id)}>Approve</button>
                          <RevisionRequestButton deliverableId={d.id} onDone={load}/>
                          <button onClick={() => actDeliverable(d.id, "reject")} className="btn-outline text-xs px-3 py-2"
                                  data-testid={TID.deliverableReject(d.id)}>Reject</button>
                        </div>
                      )}
                    </div>
                  </div>
                  <RevisionThread deliverable={d} user={user} onChange={load}/>
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
                      className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
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


// ---------- Revision workflow components ----------
function RevisionRequestButton({ deliverableId, onDone }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [priority, setPriority] = useState("minor");
  const [attachment, setAttachment] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (text.trim().length < 20) return toast.error("Please give at least a 20-character justification.");
    setSaving(true);
    try {
      const r = await api.post(`/deliverables/${deliverableId}/request-revision`, {
        justification: text.trim(), priority, attachment_url: attachment.trim(),
      });
      toast.success(`Revision #${r.data.revision_count} requested`);
      setOpen(false); setText(""); setPriority("minor"); setAttachment("");
      onDone && onDone();
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSaving(false); }
  };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}
              data-testid={`request-revision-${deliverableId}`}
              className="hard-border bg-white text-[#6B21A8] hover:bg-[#F5F3FF] text-xs px-3 py-2 inline-flex items-center gap-1">
        <ArrowsCounterClockwise size={12} weight="bold"/> Request revision
      </button>
      {open && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
             onClick={() => !saving && setOpen(false)} data-testid="revision-modal">
          <form onSubmit={submit} onClick={(e) => e.stopPropagation()}
                className="hard-border bg-white max-w-lg w-full p-6 shadow-brutal-lg relative">
            <button type="button" onClick={() => setOpen(false)} className="absolute top-4 right-4 text-neutral-400 hover:text-neutral-700">
              <X size={18}/>
            </button>
            <p className="overline text-[#6B21A8]">REQUEST REVISION</p>
            <h3 className="font-display font-black text-2xl tracking-tight mt-1">What needs to change?</h3>
            <p className="text-xs text-neutral-500 mt-1">
              Your justification is recorded and shared with the talent and Job Atlas admins.
              Excessive revisions may be reviewed against you.
            </p>

            <label className="overline block mt-5 mb-1">Justification (min 20 chars)</label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4}
                      minLength={20} maxLength={2000} required
                      data-testid="revision-justification"
                      placeholder="Be specific: which section needs work, and how does it fall short of the brief?"
                      className="w-full hard-border px-3 py-2 text-sm focus:outline-none focus:border-[#6B21A8]"/>
            <p className="text-[10px] font-mono text-neutral-500 mt-1 text-right">{text.length}/2000</p>

            <label className="overline block mt-4 mb-2">Priority</label>
            <div className="grid grid-cols-3 gap-2">
              {["minor", "major", "blocking"].map((p) => (
                <button key={p} type="button" onClick={() => setPriority(p)}
                        data-testid={`revision-priority-${p}`}
                        className={`hard-border px-3 py-2 text-xs capitalize ${priority === p ? "bg-[#0B1B2B] text-white" : "bg-white"}`}>
                  {p}
                </button>
              ))}
            </div>

            <label className="overline block mt-4 mb-1">Reference URL (optional)</label>
            <input value={attachment} onChange={(e) => setAttachment(e.target.value)} type="url"
                   data-testid="revision-attachment" placeholder="https://…"
                   className="w-full hard-border px-3 py-2 text-sm font-mono focus:outline-none focus:border-[#6B21A8]"/>

            <div className="flex gap-3 mt-6">
              <button type="submit" disabled={saving} className="btn-primary text-sm" data-testid="revision-submit">
                {saving ? "Sending…" : "Send revision request"}
              </button>
              <button type="button" onClick={() => setOpen(false)} className="btn-outline text-sm">Cancel</button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}

function RevisionThread({ deliverable, user, onChange }) {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [resubmitOpen, setResubmitOpen] = useState(false);
  const [rLink, setRLink] = useState("");
  const [rHours, setRHours] = useState(1);
  const [rNotes, setRNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [disputeOpen, setDisputeOpen] = useState(false);
  const [dReason, setDReason] = useState("");
  const [fee, setFee] = useState(null);   // { ref, status, ruling, fee:{...} }
  const [payingFee, setPayingFee] = useState(false);

  const load = async () => {
    try {
      const r = await api.get(`/deliverables/${deliverable.id}/revisions`);
      setData(r.data);
    } catch { /* silent — non-parties get 403 */ }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [deliverable.id, deliverable.status, deliverable.revision_count]);

  // Once the deliverable is dispute_resolved (or a dispute exists), look up the
  // fee owner + payment status directly via the stamped grievance_id.
  useEffect(() => {
    (async () => {
      const gid = deliverable.dispute_grievance_id;
      if (!gid) { setFee(null); return; }
      try {
        const s = await api.get(`/grievances/${gid}/fee-status`);
        setFee({ ...s.data, grievance_id: gid });
      } catch { /* ignore */ }
    })();
    // eslint-disable-next-line
  }, [deliverable.dispute_grievance_id, deliverable.status, deliverable.dispute_ruling]);

  if (!data || data.items.length === 0) return null;

  const isTalent = user?.id === deliverable.talent_id;
  const showResubmit = isTalent && deliverable.status === "revision_requested";
  const showDispute = isTalent && data.dispute_available && deliverable.status !== "dispute_resolved";

  const payFee = async () => {
    if (!fee?.grievance_id) return;
    setPayingFee(true);
    try {
      const r = await api.post(`/grievances/${fee.grievance_id}/pay-fee`, { origin_url: window.location.origin });
      if (r.data.already_paid) { toast.success("Fee already paid."); await load(); return; }
      window.location.href = r.data.checkout_url;
    } catch (e) { toast.error(formatErr(e)); }
    finally { setPayingFee(false); }
  };

  const submitResubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(`/deliverables/${deliverable.id}/resubmit`, {
        link: rLink.trim(), hours_claimed: Number(rHours), notes: rNotes.trim(),
      });
      toast.success("Resubmitted for review");
      setResubmitOpen(false); setRLink(""); setRHours(1); setRNotes("");
      onChange && onChange();
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSaving(false); }
  };

  const submitDispute = async (e) => {
    e.preventDefault();
    if (dReason.trim().length < 20) return toast.error("Give at least a 20-char reason.");
    if (!window.confirm(
      `Raise a formal dispute?\n\nA $${data.dispute_fee_usd} arbitration fee applies to the losing party once Job Atlas rules.`
    )) return;
    setSaving(true);
    try {
      const r = await api.post(`/deliverables/${deliverable.id}/dispute`, { reason: dReason.trim() });
      toast.success(`Dispute filed · ref ${r.data.ref}`);
      setDisputeOpen(false); setDReason("");
      onChange && onChange();
    } catch (err) { toast.error(formatErr(err)); }
    finally { setSaving(false); }
  };

  const chip = data.revision_count >= data.penalty_threshold
    ? { bg: "#FEE2E2", text: "#991B1B", label: `🔴 ${data.revision_count} revisions` }
    : data.revision_count >= data.review_threshold
      ? { bg: "#FEF9C3", text: "#854D0E", label: `🟡 ${data.revision_count} revisions` }
      : { bg: "#EDE9FE", text: "#6B21A8", label: `${data.revision_count} revision${data.revision_count === 1 ? "" : "s"}` };

  return (
    <div className="mt-4 hard-border bg-[#F5F3FF] p-3" data-testid={`revision-thread-${deliverable.id}`}>
      {fee && fee.status === "resolved" && (
        <FeeCard fee={fee} user={user} onPay={payFee} paying={payingFee}/>
      )}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <button type="button" onClick={() => setExpanded(!expanded)}
                data-testid={`revision-toggle-${deliverable.id}`}
                className="text-xs font-mono uppercase tracking-widest text-[#6B21A8] inline-flex items-center gap-1">
          {expanded ? "Hide" : "Show"} revision history
          <span className="px-2 py-0.5 text-[10px]" style={{ background: chip.bg, color: chip.text }}>{chip.label}</span>
        </button>
        <div className="flex gap-2 flex-wrap">
          {showResubmit && (
            <button type="button" onClick={() => setResubmitOpen(true)}
                    data-testid={`resubmit-${deliverable.id}`}
                    className="btn-primary text-xs">Respond &amp; resubmit</button>
          )}
          {showDispute && (
            <button type="button" onClick={() => setDisputeOpen(true)}
                    data-testid={`dispute-${deliverable.id}`}
                    className="hard-border bg-white text-[#991B1B] hover:bg-red-50 text-xs px-3 py-2 inline-flex items-center gap-1">
              <Gavel size={12} weight="bold"/> Raise dispute
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <ul className="mt-3 space-y-2" data-testid={`revision-list-${deliverable.id}`}>
          {data.items.map((r) => (
            <li key={r.id} className="hard-border bg-white p-3">
              <div className="flex items-center justify-between gap-2 mb-1 flex-wrap">
                <p className="font-display font-extrabold text-sm">Revision #{r.revision_number}
                  <span className="ml-2 text-[10px] font-mono uppercase tracking-widest text-neutral-500">{r.priority}</span>
                </p>
                <p className="text-[10px] font-mono text-neutral-500">
                  {new Date(r.created_at).toLocaleString()}
                  {r.resubmitted_at && ` · resubmitted ${new Date(r.resubmitted_at).toLocaleString()}`}
                </p>
              </div>
              <p className="text-xs text-neutral-700 whitespace-pre-wrap">{r.justification}</p>
              {r.attachment_url && (
                <a href={r.attachment_url} target="_blank" rel="noreferrer"
                   className="text-[11px] font-mono underline underline-offset-4 mt-1 inline-block">Reference URL ↗</a>
              )}
              {r.status === "resubmitted" && r.resubmit_notes && (
                <div className="mt-2 pt-2 border-t border-black/10">
                  <p className="text-[10px] font-mono uppercase tracking-widest text-[#6B21A8]">Talent response</p>
                  <p className="text-xs text-neutral-700 whitespace-pre-wrap mt-1">{r.resubmit_notes}</p>
                  {r.resubmit_link && (
                    <a href={r.resubmit_link} target="_blank" rel="noreferrer"
                       className="text-[11px] font-mono underline underline-offset-4 mt-1 inline-block">{r.resubmit_link}</a>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {resubmitOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
             onClick={() => !saving && setResubmitOpen(false)} data-testid="resubmit-modal">
          <form onClick={(e) => e.stopPropagation()} onSubmit={submitResubmit}
                className="hard-border bg-white max-w-lg w-full p-6 shadow-brutal-lg relative">
            <button type="button" onClick={() => setResubmitOpen(false)}
                    className="absolute top-4 right-4 text-neutral-400 hover:text-neutral-700"><X size={18}/></button>
            <p className="overline text-[#6B21A8]">RESUBMIT</p>
            <h3 className="font-display font-black text-2xl tracking-tight mt-1">Respond to revision</h3>
            <label className="overline block mt-4 mb-1">Updated link</label>
            <input value={rLink} onChange={(e) => setRLink(e.target.value)} type="url" required
                   data-testid="resubmit-link" className="w-full hard-border px-3 py-2 text-sm font-mono focus:outline-none focus:border-[#6B21A8]"/>
            <label className="overline block mt-3 mb-1">Extra hours claimed</label>
            <input value={rHours} onChange={(e) => setRHours(e.target.value)} type="number" min="0" step="0.5" required
                   data-testid="resubmit-hours" className="w-full hard-border px-3 py-2 text-sm font-mono focus:outline-none focus:border-[#6B21A8]"/>
            <label className="overline block mt-3 mb-1">Notes for the employer</label>
            <textarea value={rNotes} onChange={(e) => setRNotes(e.target.value)} rows={3}
                      data-testid="resubmit-notes"
                      className="w-full hard-border px-3 py-2 text-sm focus:outline-none focus:border-[#6B21A8]"/>
            <button type="submit" disabled={saving} className="btn-primary text-sm mt-4" data-testid="resubmit-submit">
              {saving ? "Sending…" : "Resubmit for review"}
            </button>
          </form>
        </div>
      )}

      {disputeOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
             onClick={() => !saving && setDisputeOpen(false)} data-testid="dispute-modal">
          <form onClick={(e) => e.stopPropagation()} onSubmit={submitDispute}
                className="hard-border bg-white max-w-lg w-full p-6 shadow-brutal-lg relative">
            <button type="button" onClick={() => setDisputeOpen(false)}
                    className="absolute top-4 right-4 text-neutral-400 hover:text-neutral-700"><X size={18}/></button>
            <p className="overline text-[#991B1B]">RAISE DISPUTE</p>
            <h3 className="font-display font-black text-2xl tracking-tight mt-1">Escalate to Job Atlas admins</h3>
            <p className="text-xs text-neutral-500 mt-2">
              Your revision thread will be attached automatically. A <b>${data.dispute_fee_usd}</b> arbitration fee
              applies to the losing party once we rule.
            </p>
            <label className="overline block mt-4 mb-1">Why is this unfair? (min 20 chars)</label>
            <textarea value={dReason} onChange={(e) => setDReason(e.target.value)} rows={4}
                      required minLength={20} data-testid="dispute-reason"
                      className="w-full hard-border px-3 py-2 text-sm focus:outline-none focus:border-[#991B1B]"/>
            <button type="submit" disabled={saving}
                    className="hard-border bg-[#991B1B] text-white px-4 py-2 text-sm mt-4"
                    data-testid="dispute-submit">
              {saving ? "Filing…" : "File dispute"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}


function FeeCard({ fee, user, onPay, paying }) {
  const f = fee.fee || {};
  const owedByMe = f.owed_by === user?.id;
  const paid = f.payment_status === "paid";
  const winnerLabel = fee.ruling === "talent" ? "Talent" : "Employer";
  return (
    <div
      className={`mb-3 hard-border p-4 ${paid ? "bg-emerald-50 border-emerald-500" : owedByMe ? "bg-red-50 border-red-500" : "bg-white"}`}
      data-testid={`fee-card-${fee.grievance_id}`}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <p className="overline text-[#6B21A8]">Dispute {fee.ref} · Ruled for {winnerLabel}</p>
          <p className="font-display font-extrabold text-sm mt-1">
            Arbitration fee <span className="font-black">${f.amount_usd}</span>
            {paid ? (
              <span className="ml-2 text-emerald-700">· Paid ✓</span>
            ) : (
              <span className="ml-2 text-neutral-500">· {f.payment_status || "unpaid"}</span>
            )}
          </p>
          <p className="text-xs text-neutral-600 mt-1">
            {paid ? "Fee settled — case closed." : owedByMe ? "You owe this fee. Settle by card to close the case." : "Awaiting the other party to settle."}
          </p>
        </div>
        {!paid && owedByMe && (
          <button onClick={onPay} disabled={paying} className="btn-primary text-sm" data-testid={`fee-pay-${fee.grievance_id}`}>
            {paying ? "Redirecting…" : `Pay $${f.amount_usd}`}
          </button>
        )}
      </div>
    </div>
  );
}

