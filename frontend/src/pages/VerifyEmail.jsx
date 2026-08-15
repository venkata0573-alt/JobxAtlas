import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const [state, setState] = useState("verifying");   // verifying | ok | fail
  const [msg, setMsg] = useState("");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;             // guard against React StrictMode double-invoke
    ran.current = true;
    const token = params.get("token");
    if (!token) { setState("fail"); setMsg("Missing verification token."); return; }
    api.get(`/auth/verify-email?token=${encodeURIComponent(token)}`)
      .then((r) => { setState("ok"); setMsg(r.data.email); })
      .catch((e) => { setState("fail"); setMsg(formatErr(e)); });
  }, [params]);

  return (
    <main className="max-w-lg mx-auto p-8 md:p-16 text-center" data-testid="verify-email-page">
      <div className="hard-border bg-white p-10 shadow-brutal">
        {state === "verifying" && (
          <p className="font-mono text-neutral-500">Verifying your email…</p>
        )}
        {state === "ok" && (
          <>
            <CheckCircle size={48} weight="fill" color="#10B981" className="mx-auto mb-4"/>
            <h1 className="font-display font-extrabold text-3xl tracking-tight mb-3">Email verified</h1>
            <p className="text-neutral-600 mb-6">{msg} is now confirmed on Job Atlas.</p>
            <Link to="/login" className="btn-primary" data-testid="verify-email-continue">Continue</Link>
          </>
        )}
        {state === "fail" && (
          <>
            <WarningCircle size={48} weight="fill" color="#B03A2E" className="mx-auto mb-4"/>
            <h1 className="font-display font-extrabold text-3xl tracking-tight mb-3">Link expired</h1>
            <p className="text-neutral-600 mb-6" data-testid="verify-email-error">{msg}</p>
            <Link to="/login" className="btn-outline">Log in to resend</Link>
          </>
        )}
      </div>
    </main>
  );
}
