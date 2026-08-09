import React, { useEffect, useRef, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { PaperPlaneTilt, WarningOctagon, Paperclip, FileText } from "@phosphor-icons/react";

export default function EngagementChat({ engagementId }) {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [blobs, setBlobs] = useState({});           // { file_id: objectURL }
  const scrollRef = useRef(null);
  const fileRef = useRef(null);

  const load = async () => {
    try { const r = await api.get(`/messages/${engagementId}`); setItems(r.data); }
    catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => {
    load(); const iv = setInterval(load, 8000); return () => clearInterval(iv);
    // eslint-disable-next-line
  }, [engagementId]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: 9e9, behavior: "smooth" }); }, [items]);

  // Preload image attachments as blob URLs (img cannot pass auth headers)
  useEffect(() => {
    items.forEach((m) => {
      if (m.attachment_id && (m.attachment_type || "").startsWith("image/") && !blobs[m.attachment_id]) {
        api.get(`/files/${m.attachment_id}`, { responseType: "blob" }).then((r) => {
          const url = URL.createObjectURL(r.data);
          setBlobs((b) => ({ ...b, [m.attachment_id]: url }));
        }).catch(() => {});
      }
    });
    // eslint-disable-next-line
  }, [items]);

  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    try {
      await api.post("/messages", { engagement_id: engagementId, text: text.trim() });
      setText(""); load();
    } catch (err) { toast.error(formatErr(err)); }
  };

  const upload = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    if (f.size > 10 * 1024 * 1024) return toast.error("File exceeds 10 MB");
    const form = new FormData();
    form.append("file", f); form.append("engagement_id", engagementId);
    setUploading(true);
    try {
      await api.post("/messages/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err) { toast.error(formatErr(err)); }
    finally { setUploading(false); }
  };

  const downloadAttachment = async (fileId, name) => {
    try {
      const r = await api.get(`/files/${fileId}`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a"); a.href = url; a.download = name || "download"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { toast.error(formatErr(e)); }
  };

  return (
    <section className="hard-border bg-white shadow-brutal mt-10">
      <div className="p-5 border-b border-black/10 flex items-center justify-between">
        <h2 className="font-display font-black text-xl tracking-tight">In-platform chat</h2>
        <p className="text-xs font-mono text-neutral-500">Moderated · attachments up to 10 MB</p>
      </div>
      <div ref={scrollRef} className="max-h-[28rem] overflow-y-auto p-5 space-y-3">
        {items.length === 0 ? (
          <p className="text-sm text-neutral-500 text-center py-8">Say hi. Align on scope before the meter starts.</p>
        ) : items.map(m => {
          const mine = m.sender_id === user?.id;
          const isImg = (m.attachment_type || "").startsWith("image/");
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[75%] hard-border p-3 ${mine ? "bg-[#0B1B2B] text-white" : "bg-white"}`}>
                {!mine && <p className="text-xs font-mono opacity-70 mb-1">{m.sender_name}</p>}
                {m.attachment_id ? (
                  isImg && blobs[m.attachment_id] ? (
                    <img src={blobs[m.attachment_id]} alt={m.attachment_name}
                         className="max-w-full max-h-64 hard-border cursor-pointer"
                         onClick={() => downloadAttachment(m.attachment_id, m.attachment_name)}/>
                  ) : (
                    <button onClick={() => downloadAttachment(m.attachment_id, m.attachment_name)}
                            className={`hard-border p-3 flex items-center gap-2 text-sm ${mine ? "bg-white/10" : "bg-neutral-50"}`}>
                      <FileText size={18} weight="duotone"/> {m.attachment_name}
                    </button>
                  )
                ) : (
                  <p className="text-sm whitespace-pre-wrap">{m.text}</p>
                )}
                <p className={`text-[10px] font-mono mt-1 ${mine ? "text-white/70" : "text-neutral-500"}`}>{new Date(m.created_at).toLocaleString()}</p>
                {m.flagged && (
                  <p className={`text-[10px] mt-1 inline-flex items-center gap-1 ${mine ? "text-[#C79A3B]" : "text-red-600"}`}>
                    <WarningOctagon size={10} weight="fill"/> flagged for moderator review
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <form onSubmit={send} className="p-4 border-t border-black/10 flex gap-2">
        <label className="hard-border px-3 flex items-center cursor-pointer hover:bg-[#0B1B2B] hover:text-white">
          <Paperclip size={16} weight="duotone"/>
          <input ref={fileRef} type="file" onChange={upload} className="hidden"
                 accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.csv"/>
        </label>
        <input value={text} onChange={(e) => setText(e.target.value)}
               placeholder={uploading ? "Uploading…" : "Type a message… (phone / email will be flagged)"}
               disabled={uploading}
               className="flex-1 hard-border px-3 py-3 focus:outline-none focus:border-[#C79A3B]"/>
        <button type="submit" className="btn-primary inline-flex items-center gap-2" disabled={uploading}>
          <PaperPlaneTilt size={14} weight="fill"/> Send
        </button>
      </form>
    </section>
  );
}
