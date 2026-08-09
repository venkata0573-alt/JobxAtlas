import React, { useEffect, useRef, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { PuzzlePiece, ArrowsClockwise, Trash, FileArrowUp } from "@phosphor-icons/react";

export default function Integrations() {
  const { user, refresh } = useAuth();
  const [providers, setProviders] = useState([]);
  const [selected, setSelected] = useState(null);
  const [token, setToken] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [items, setItems] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const loadWork = async () => {
    try { const r = await api.get("/work/items"); setItems(r.data); } catch (e) { toast.error(formatErr(e)); }
  };

  useEffect(() => {
    api.get("/integrations/providers").then((r) => setProviders(r.data));
    loadWork();
  }, []);

  const connect = async (e) => {
    e.preventDefault();
    if (!selected || !token.trim()) return toast.error("Choose a provider and paste your token");
    try {
      await api.post("/integrations/connect", { provider: selected.id, api_token: token.trim(), workspace });
      toast.success(`${selected.name} connected — syncing tasks…`);
      setSelected(null); setToken(""); setWorkspace("");
      await refresh(); await loadWork();
    } catch (err) { toast.error(formatErr(err)); }
  };

  const doSync = async (id) => {
    try { const r = await api.post(`/integrations/sync/${id}`); toast.success(`Synced ${r.data.synced} items`); await loadWork(); }
    catch (e) { toast.error(formatErr(e)); }
  };
  const disconnect = async (id) => {
    try { await api.delete(`/integrations/${id}`); await refresh(); toast.success("Disconnected"); }
    catch (e) { toast.error(formatErr(e)); }
  };

  const upload = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) return toast.error("Choose a file first");
    const form = new FormData(); form.append("file", f);
    setUploading(true);
    try {
      const r = await api.post("/work/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Imported ${r.data.inserted} items`);
      fileRef.current.value = "";
      await loadWork();
    } catch (e) { toast.error(formatErr(e)); }
    finally { setUploading(false); }
  };

  const connections = user?.integrations || [];

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">INTEGRATIONS</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">One inbox for every task.</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">Connect the tools your teams already use, or upload project plans directly.
        We map everything into a single work log per engagement.</p>

      {/* Existing connections */}
      {connections.length > 0 && (
        <section className="mb-12">
          <p className="overline mb-4">Active connections</p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {connections.map((c) => (
              <div key={c.id} className="hard-border bg-white p-5 flex items-center justify-between">
                <div>
                  <p className="font-display font-extrabold text-lg tracking-tight">{c.provider}</p>
                  <p className="text-xs font-mono text-neutral-500">Token {c.token_masked}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => doSync(c.id)} data-testid={TID.integrationSync(c.id)}
                          className="hard-border p-2 hover:bg-[#0A0A0A] hover:text-white"><ArrowsClockwise size={16}/></button>
                  <button onClick={() => disconnect(c.id)} data-testid={TID.integrationDisconnect(c.id)}
                          className="hard-border p-2 hover:bg-[#FF0A0A] hover:text-white"><Trash size={16}/></button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid lg:grid-cols-[1.3fr_1fr] gap-6 mb-12">
        {/* Provider picker */}
        <section className="hard-border bg-white p-8 shadow-brutal">
          <div className="flex items-center gap-3 mb-4">
            <PuzzlePiece size={22} weight="duotone" color="#002FA7"/>
            <h2 className="font-display font-extrabold text-2xl tracking-tight">Connect a provider</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
            {providers.map((p) => (
              <button key={p.id} type="button" onClick={() => setSelected(p)}
                      data-testid={TID.integrationProviderCard(p.id)}
                      className={`hard-border p-4 text-left ${selected?.id === p.id ? "bg-[#0A0A0A] text-white" : "bg-white"}`}>
                <p className="font-display font-extrabold">{p.name}</p>
                <p className="text-xs opacity-70 mt-1">{p.token_label}</p>
              </button>
            ))}
          </div>
          {selected && (
            <form onSubmit={connect} className="space-y-4 border-t border-black/10 pt-6">
              <p className="overline">{selected.name} · Credentials</p>
              <div>
                <label className="text-xs text-neutral-500 mb-1 block">{selected.token_label}</label>
                <input data-testid={TID.integrationToken} value={token} onChange={(e) => setToken(e.target.value)}
                       type="password" required
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7] font-mono"/>
              </div>
              <div>
                <label className="text-xs text-neutral-500 mb-1 block">{selected.workspace_label}</label>
                <input data-testid={TID.integrationWorkspace} value={workspace} onChange={(e) => setWorkspace(e.target.value)}
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
              </div>
              <button type="submit" className="btn-primary" data-testid={TID.integrationConnect}>Connect →</button>
              <p className="text-xs text-neutral-500">If we can&apos;t reach the API, we&apos;ll seed placeholder tasks so you can preview the flow.</p>
            </form>
          )}
        </section>

        {/* File upload */}
        <section className="hard-border bg-[#FDFCF0] p-8 shadow-brutal">
          <div className="flex items-center gap-3 mb-4">
            <FileArrowUp size={22} weight="duotone" color="#002FA7"/>
            <h2 className="font-display font-extrabold text-2xl tracking-tight">Upload a plan</h2>
          </div>
          <p className="text-sm text-neutral-600 mb-4">Excel (.xlsx/.xls) with a &quot;Task&quot; column, or MS Project XML export.</p>
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.xml"
                 data-testid={TID.workUpload}
                 className="w-full hard-border px-3 py-3 bg-white mb-4 font-mono text-sm"/>
          <button onClick={upload} disabled={uploading} className="btn-primary w-full" data-testid={TID.workUploadBtn}>
            {uploading ? "Uploading…" : "Import tasks"}
          </button>
          <p className="text-xs text-neutral-500 mt-3 font-mono">.mpp binary → export as XML in MS Project first</p>
        </section>
      </div>

      {/* Work log */}
      <section className="hard-border bg-white shadow-brutal">
        <div className="p-6 border-b border-black/10 flex items-center justify-between">
          <h2 className="font-display font-extrabold text-2xl tracking-tight">Unified work log</h2>
          <p className="text-sm text-neutral-500 font-mono">{items.length} items</p>
        </div>
        {items.length === 0 ? (
          <p className="p-8 text-neutral-500">Nothing here yet. Connect a provider or upload a file above.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#0A0A0A] text-white">
                <tr>
                  {["Task", "Source", "Status", "Assignee", "Due", "Hours"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 overline">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((w) => (
                  <tr key={w.id} className="border-t border-black/10" data-testid={TID.workItemRow(w.id)}>
                    <td className="px-4 py-3 font-medium">{w.title}</td>
                    <td className="px-4 py-3 font-mono text-xs">{w.source}</td>
                    <td className="px-4 py-3"><span className="hard-border px-2 py-1 text-xs">{w.status}</span></td>
                    <td className="px-4 py-3">{w.assignee || "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs">{w.due_date || "—"}</td>
                    <td className="px-4 py-3 font-mono">{w.hours_logged || 0}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
