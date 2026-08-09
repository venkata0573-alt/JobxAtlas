import React, { useEffect, useRef, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { PaperPlaneTilt, WarningOctagon } from "@phosphor-icons/react";

export default function EngagementChat({ engagementId }) {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const scrollRef = useRef(null);

  const load = async () => {
    try { const r = await api.get(`/messages/${engagementId}`); setItems(r.data); }
    catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); const iv = setInterval(load, 8000); return () => clearInterval(iv); /* eslint-disable-next-line */ }, [engagementId]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: 9e9, behavior: "smooth" }); }, [items]);

  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    try {
      await api.post("/messages", { engagement_id: engagementId, text: text.trim() });
      setText(""); load();
    } catch (err) { toast.error(formatErr(err)); }
  };

  return (
    <section className="hard-border bg-white shadow-brutal mt-10">
      <div className="p-5 border-b border-black/10 flex items-center justify-between">
        <h2 className="font-display font-extrabold text-xl tracking-tight">In-platform chat</h2>
        <p className="text-xs font-mono text-neutral-500">Moderated · off-platform contact flagged</p>
      </div>
      <div ref={scrollRef} className="max-h-96 overflow-y-auto p-5 space-y-3">
        {items.length === 0 ? (
          <p className="text-sm text-neutral-500 text-center py-8">Say hi. Align on scope before the meter starts.</p>
        ) : items.map(m => {
          const mine = m.sender_id === user?.id;
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[75%] hard-border p-3 ${mine ? "bg-[#002FA7] text-white" : "bg-white"}`}>
                {!mine && <p className="text-xs font-mono opacity-70 mb-1">{m.sender_name}</p>}
                <p className="text-sm whitespace-pre-wrap">{m.text}</p>
                <p className={`text-[10px] font-mono mt-1 ${mine ? "text-white/70" : "text-neutral-500"}`}>{new Date(m.created_at).toLocaleString()}</p>
                {m.flagged && (
                  <p className={`text-[10px] mt-1 inline-flex items-center gap-1 ${mine ? "text-yellow-200" : "text-[#FF0A0A]"}`}>
                    <WarningOctagon size={10} weight="fill"/> flagged for moderator review
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <form onSubmit={send} className="p-4 border-t border-black/10 flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)}
               placeholder="Type a message… (phone / email will be flagged)"
               className="flex-1 hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
        <button type="submit" className="btn-primary inline-flex items-center gap-2">
          <PaperPlaneTilt size={14} weight="fill"/> Send
        </button>
      </form>
    </section>
  );
}
