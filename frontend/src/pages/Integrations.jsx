import React, { useEffect, useRef, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { PuzzlePiece, ArrowsClockwise, Trash, FileArrowUp, Handshake, CheckCircle, CloudArrowUp, ClockClockwise } from "@phosphor-icons/react";

const CRM_PROVIDERS = [
  { id: "hubspot",    name: "HubSpot",      token_label: "Private-app access token",  needs_instance: false, help: "Settings → Integrations → Private Apps → Access token" },
  { id: "salesforce", name: "Salesforce",   token_label: "OAuth access token",         needs_instance: true,  help: "OAuth Playground or Connected App refresh flow" },
  { id: "slack",      name: "Slack",        token_label: "Bot user OAuth token (xoxb-)", needs_instance: false, help: "OAuth & Permissions → Bot User OAuth Token" },
  { id: "sharepoint", name: "SharePoint",   token_label: "Graph API access token",     needs_instance: false, help: "Azure AD app registration → Client credentials" },
];

export default function Integrations() {
  const { user, refresh } = useAuth();
  const [providers, setProviders] = useState([]);
  const [selected, setSelected] = useState(null);
  const [token, setToken] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [items, setItems] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);
  // ---- CRM state ----
  const [crmConns, setCrmConns] = useState([]);
  const [crmProv, setCrmProv] = useState(null);      // selected CRM provider spec
  const [crmToken, setCrmToken] = useState("");
  const [crmInstance, setCrmInstance] = useState("");
  const [crmConnecting, setCrmConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncLog, setSyncLog] = useState([]);

  const loadWork = async () => {
    try { const r = await api.get("/work/items"); setItems(r.data); } catch (e) { toast.error(formatErr(e)); }
  };
  const loadCrm = async () => {
    try { const r = await api.get("/integrations/crm"); setCrmConns(r.data.items || []); }
    catch { /* endpoint gated by role; ignore for talents */ }
  };
  const loadSyncLog = async () => {
    try { const r = await api.get("/integrations/crm/sync-log?limit=20"); setSyncLog(r.data.items || []); }
    catch { /* ignore for talent role */ }
  };

  useEffect(() => {
    api.get("/integrations/providers").then((r) => setProviders(r.data));
    loadWork();
    if (user?.role === "employer") { loadCrm(); loadSyncLog(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role]);

  const syncNow = async () => {
    setSyncing(true);
    try {
      const r = await api.post("/integrations/crm/sync-now");
      const { pushed, skipped, failed } = r.data;
      toast.success(`Sync complete · ${pushed} pushed · ${skipped} deduped · ${failed} failed`);
      await loadCrm();
      await loadSyncLog();
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSyncing(false); }
  };

  const connectCrm = async (e) => {
    e.preventDefault();
    if (!crmProv || !crmToken.trim()) { toast.error("Pick a provider and paste your token"); return; }
    if (crmProv.needs_instance && !crmInstance.trim()) { toast.error(`${crmProv.name} requires an instance URL`); return; }
    setCrmConnecting(true);
    try {
      await api.post("/integrations/crm/connect", {
        provider: crmProv.id,
        access_token: crmToken.trim(),
        instance_url: crmInstance.trim() || null,
      });
      toast.success(`${crmProv.name} connected`);
      setCrmProv(null); setCrmToken(""); setCrmInstance("");
      await loadCrm();
    } catch (err) { toast.error(formatErr(err)); }
    finally { setCrmConnecting(false); }
  };
  const disconnectCrm = async (provider) => {
    if (!window.confirm(`Disconnect ${provider}?`)) return;
    try {
      await api.delete(`/integrations/crm/${provider}`);
      toast.success(`${provider} disconnected`);
      await loadCrm();
    } catch (e) { toast.error(formatErr(e)); }
  };

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
      <p className="overline text-[#6B21A8] mb-3">INTEGRATIONS</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">One inbox for every task.</h1>
      <p className="text-neutral-600 max-w-2xl mb-10">Connect the tools your teams already use, or upload project plans directly.
        We map everything into a single work log per engagement.</p>

      {/* -------------------- CRM & Sales Tools (employer only) -------------------- */}
      {user?.role === "employer" && (
        <section className="mb-14" data-testid="crm-section">
          <div className="flex items-center gap-3 mb-4">
            <div className="hard-border bg-[#6B21A8] text-white w-10 h-10 flex items-center justify-center">
              <Handshake size={18} weight="duotone"/>
            </div>
            <div>
              <p className="overline text-[#6B21A8]">CRM &amp; SALES TOOLS</p>
              <h2 className="font-display font-extrabold text-2xl tracking-tight">Push shortlisted talent into your CRM in one click.</h2>
            </div>
          </div>
          <p className="text-sm text-neutral-600 max-w-2xl mb-6">
            Connect HubSpot, Salesforce, Slack, or SharePoint. We validate your token against the vendor&apos;s
            live API before saving. Push a shortlisted professional as a Contact (HubSpot) or Lead (Salesforce)
            without leaving Job Atlas.
          </p>

          {/* Active CRM connections */}
          {crmConns.length > 0 && (
            <>
              <div className="flex items-center justify-between mb-2 flex-wrap gap-3">
                <p className="overline text-neutral-500">Active connections</p>
                <div className="flex items-center gap-2 flex-wrap">
                  <button onClick={syncNow} disabled={syncing}
                          data-testid="crm-sync-now"
                          className="hard-border bg-white text-[#6B21A8] hover:bg-[#F5F3FF] text-xs font-mono uppercase tracking-widest px-3 py-2 inline-flex items-center gap-2 disabled:opacity-50">
                    <CloudArrowUp size={14} weight={syncing ? "regular" : "bold"} className={syncing ? "animate-pulse" : ""}/>
                    {syncing ? "Syncing…" : "Sync now"}
                  </button>
                  <p className="text-[10px] font-mono text-neutral-500 tracking-widest uppercase">
                    Auto-sync · daily 02:00 UTC
                  </p>
                </div>
              </div>
              <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6" data-testid="crm-connections">
                {crmConns.map((c) => (
                  <div key={c.provider} className="hard-border bg-white p-4 shadow-brutal flex items-center justify-between" data-testid={`crm-conn-${c.provider}`}>
                    <div className="min-w-0">
                      <p className="font-display font-extrabold text-sm tracking-tight capitalize inline-flex items-center gap-1">
                        <CheckCircle size={14} weight="fill" color="#6B21A8"/> {c.provider}
                      </p>
                      <p className="text-[10px] font-mono text-neutral-500 mt-1 truncate">Token {c.token_masked || "•••"}</p>
                      {c.last_sync_at && (
                        <p className="text-[10px] font-mono text-neutral-400 truncate" title={c.last_sync_at}>
                          Last sync {new Date(c.last_sync_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </p>
                      )}
                      {c.instance_url && (
                        <p className="text-[10px] font-mono text-neutral-500 truncate" title={c.instance_url}>{c.instance_url}</p>
                      )}
                    </div>
                    <button onClick={() => disconnectCrm(c.provider)}
                            data-testid={`crm-disconnect-${c.provider}`}
                            className="hard-border p-2 bg-white text-neutral-500 hover:bg-red-50 hover:text-red-700"
                            title="Disconnect">
                      <Trash size={14}/>
                    </button>
                  </div>
                ))}
              </div>

              {/* Sync log ribbon */}
              {syncLog.length > 0 && (
                <div className="hard-border bg-[#F5F3FF] p-4 mb-6" data-testid="crm-sync-log">
                  <p className="overline text-[#6B21A8] mb-2 inline-flex items-center gap-1">
                    <ClockClockwise size={12} weight="bold"/> Recent syncs
                  </p>
                  <ul className="grid md:grid-cols-2 gap-1 text-[11px] font-mono">
                    {syncLog.slice(0, 6).map((s, i) => (
                      <li key={s.id || i} className="flex items-center justify-between gap-2 bg-white px-2 py-1 hard-border">
                        <span className="truncate">
                          <span className={s.status === "pushed" ? "text-[#166534]" : "text-red-700"}>{s.status}</span>
                          {" · "}{s.provider}{" · "}{(s.talent_id || "").slice(0, 8)}
                        </span>
                        <span className="text-neutral-500 shrink-0">
                          {new Date(s.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {/* Connect a CRM */}
          <div className="hard-border bg-white p-6 shadow-brutal" data-testid="crm-connect-card">
            <p className="overline mb-3">Connect a provider</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
              {CRM_PROVIDERS.map((p) => {
                const already = crmConns.some((c) => c.provider === p.id);
                return (
                  <button key={p.id} type="button"
                          onClick={() => !already && setCrmProv(p)}
                          disabled={already}
                          data-testid={`crm-provider-${p.id}`}
                          className={`hard-border p-3 text-left transition-colors ${
                            crmProv?.id === p.id ? "bg-[#0B1B2B] text-white border-[#0B1B2B]"
                            : already ? "bg-[#F5F3FF] opacity-60 cursor-not-allowed"
                            : "bg-white hover:bg-[#F5F3FF]"
                          }`}>
                    <p className="font-display font-extrabold text-sm">{p.name}</p>
                    <p className={`text-[10px] mt-1 truncate ${crmProv?.id === p.id ? "text-[#A78BFA]" : "text-neutral-500"}`}>
                      {already ? "Connected ✓" : p.token_label}
                    </p>
                  </button>
                );
              })}
            </div>

            {crmProv && (
              <form onSubmit={connectCrm} className="space-y-3 border-t border-black/10 pt-4" data-testid="crm-connect-form">
                <p className="overline text-[#6B21A8]">{crmProv.name} · Credentials</p>
                <p className="text-[11px] font-mono text-neutral-500">{crmProv.help}</p>
                <div>
                  <label className="text-xs text-neutral-500 mb-1 block">{crmProv.token_label}</label>
                  <input value={crmToken} onChange={(e) => setCrmToken(e.target.value)}
                         type="password" required
                         data-testid="crm-token-input"
                         className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono text-sm"/>
                </div>
                {crmProv.needs_instance && (
                  <div>
                    <label className="text-xs text-neutral-500 mb-1 block">Instance URL (e.g. https://myco.my.salesforce.com)</label>
                    <input value={crmInstance} onChange={(e) => setCrmInstance(e.target.value)}
                           placeholder="https://…" required
                           data-testid="crm-instance-input"
                           className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono text-sm"/>
                  </div>
                )}
                <div className="flex gap-3">
                  <button type="submit" disabled={crmConnecting} className="btn-primary text-sm" data-testid="crm-connect-btn">
                    {crmConnecting ? "Validating…" : `Connect ${crmProv.name} →`}
                  </button>
                  <button type="button" onClick={() => { setCrmProv(null); setCrmToken(""); setCrmInstance(""); }}
                          className="btn-outline text-sm">Cancel</button>
                </div>
                <p className="text-[11px] text-neutral-500">Tokens are validated against the vendor&apos;s live API before we persist them. Disconnect anytime.</p>
              </form>
            )}
            {!crmProv && (
              <p className="text-xs text-neutral-500 font-mono">Pick a provider above to paste your token.</p>
            )}
          </div>
        </section>
      )}

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
                          className="hard-border p-2 hover:bg-[#6B21A8] hover:text-white"><Trash size={16}/></button>
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
            <PuzzlePiece size={22} weight="duotone" color="#6B21A8"/>
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
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8] font-mono"/>
              </div>
              <div>
                <label className="text-xs text-neutral-500 mb-1 block">{selected.workspace_label}</label>
                <input data-testid={TID.integrationWorkspace} value={workspace} onChange={(e) => setWorkspace(e.target.value)}
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <button type="submit" className="btn-primary" data-testid={TID.integrationConnect}>Connect →</button>
              <p className="text-xs text-neutral-500">If we can&apos;t reach the API, we&apos;ll seed placeholder tasks so you can preview the flow.</p>
            </form>
          )}
        </section>

        {/* File upload */}
        <section className="hard-border bg-[#F5F3FF] p-8 shadow-brutal">
          <div className="flex items-center gap-3 mb-4">
            <FileArrowUp size={22} weight="duotone" color="#6B21A8"/>
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
