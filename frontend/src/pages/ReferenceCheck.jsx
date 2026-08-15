import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { CheckCircle, WarningCircle, ShieldCheck } from "@phosphor-icons/react";

export default function ReferenceCheck() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState("loading");   // loading | prompt | submitting | done | error
  const [data, setData] = useState(null);
  const [answer, setAnswer] = useState("");        // yes | no | partial
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) { setState("error"); setMsg("Missing token."); return; }
    api.get(`/reference-check/${encodeURIComponent(token)}`)
      .then((r) => {
        setData(r.data);
        setState(r.data.already_answered ? "done" : "prompt");
      })
      .catch((e) => { setState("error"); setMsg(formatErr(e)); });
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (!answer) return;
    setState("submitting");
    try {
      await api.post(`/reference-check/${encodeURIComponent(token)}`,
                      { response: answer, note });
      setState("done");
    } catch (err) {
      setMsg(formatErr(err));
      setState("prompt");
    }
  };

  return (
    <main className="max-w-lg mx-auto p-8 md:p-16" data-testid="reference-check-page">
      <div className="hard-border bg-white p-8 shadow-brutal">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck size={22} weight="fill" color="#C79A3B"/>
          <p className="overline text-[#C79A3B]">JOB ATLAS · REFERENCE CHECK</p>
        </div>
        {state === "loading" && <p className="font-mono text-neutral-500">Loading…</p>}
        {state === "error" && (
          <>
            <WarningCircle size={40} weight="fill" color="#B03A2E" className="mb-3"/>
            <p className="font-display font-extrabold text-2xl" data-testid="ref-check-error">{msg}</p>
          </>
        )}
        {state === "done" && (
          <>
            <CheckCircle size={40} weight="fill" color="#10B981" className="mb-3"/>
            <h1 className="font-display font-extrabold text-2xl tracking-tight mb-2">Thank you.</h1>
            <p className="text-neutral-600 text-sm">Your answer has been recorded. Job Atlas won&apos;t contact you further about this reference.</p>
          </>
        )}
        {state === "prompt" && data && (
          <form onSubmit={submit}>
            <h1 className="font-display font-extrabold text-2xl tracking-tight mb-2">
              Did you work with <span className="text-[#C79A3B]">{data.talent_name}</span>?
            </h1>
            <p className="text-sm text-neutral-600 mb-6">
              You&apos;re listed as their <b>{data.ref_relationship}</b>{data.ref_company ? ` at ${data.ref_company}` : ""}. One click — no login needed.
            </p>
            <div className="space-y-2 mb-4">
              {[
                { id: "yes",     label: "Yes — I worked with them as described.",     tone: "bg-[#EDF7EE] border-emerald-400" },
                { id: "partial", label: "Partly — some details are off, see notes.",  tone: "bg-[#FDF6E3] border-[#C79A3B]" },
                { id: "no",      label: "No — I don't recognise this person.",         tone: "bg-[#FEF0F0] border-red-300" },
              ].map((opt) => (
                <label key={opt.id} className={`hard-border block cursor-pointer p-3 ${answer === opt.id ? opt.tone : "bg-white"}`} data-testid={`ref-answer-${opt.id}`}>
                  <input type="radio" name="answer" value={opt.id} checked={answer === opt.id}
                         onChange={(e) => setAnswer(e.target.value)} className="mr-2"/>
                  <span className="text-sm">{opt.label}</span>
                </label>
              ))}
            </div>
            {answer && answer !== "yes" && (
              <textarea rows={3} placeholder="Anything to add? (optional)" value={note}
                        onChange={(e) => setNote(e.target.value)}
                        className="hard-border px-3 py-2 text-sm w-full mb-4"
                        data-testid="ref-note"/>
            )}
            <button type="submit" disabled={!answer}
                    className="btn-primary w-full text-sm"
                    data-testid="ref-submit">
              Submit answer
            </button>
            {msg && <p className="text-xs text-red-700 mt-2">{msg}</p>}
          </form>
        )}
      </div>
    </main>
  );
}
