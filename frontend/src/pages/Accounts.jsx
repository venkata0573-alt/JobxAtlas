import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  LinkedinLogo, GithubLogo, GitlabLogo, DribbbleLogo, BehanceLogo,
  GoogleLogo, MicrosoftOutlookLogo, SlackLogo, MicrosoftTeamsLogo,
  Buildings, CurrencyDollar, Bank, Trash, Globe,
} from "@phosphor-icons/react";

const ICONS = {
  linkedin: LinkedinLogo, github: GithubLogo, gitlab: GitlabLogo,
  dribbble: DribbbleLogo, behance: BehanceLogo, google: GoogleLogo,
  microsoft: MicrosoftOutlookLogo, slack: SlackLogo, teams: MicrosoftTeamsLogo,
  company: Buildings, stripe_pay: CurrencyDollar, payoneer: CurrencyDollar,
  wise: CurrencyDollar, plaid: Bank,
};

export default function Accounts() {
  const { user } = useAuth();
  const [providers, setProviders] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [handle, setHandle] = useState("");
  const [token, setToken] = useState("");

  const load = async () => {
    try {
      const [p, a] = await Promise.all([api.get("/accounts/providers"), api.get("/accounts")]);
      setProviders(p.data); setAccounts(a.data);
    } catch (e) { toast.error(formatErr(e)); }
  };
  useEffect(() => { load(); }, []);

  const connect = async (e) => {
    e.preventDefault();
    if (!selected) return toast.error("Choose a provider");
    if (!handle.trim()) return toast.error("Please enter your handle / identifier");
    try {
      await api.post("/accounts/connect", { provider: selected.id, handle: handle.trim(), api_token: token || "" });
      toast.success(`${selected.name} connected`);
      setSelected(null); setHandle(""); setToken("");
      load();
    } catch (err) { toast.error(formatErr(err)); }
  };

  const disconnect = async (id) => {
    try { await api.delete(`/accounts/${id}`); toast.success("Disconnected"); load(); }
    catch (e) { toast.error(formatErr(e)); }
  };

  const isEmployer = user?.role === "employer";

  return (
    <main className="max-w-7xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#6B21A8] mb-3">CONNECTED ACCOUNTS</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">
        {isEmployer ? "Bring your business online." : "Show the world you're the real deal."}
      </h1>
      <p className="text-neutral-600 max-w-2xl mb-10">
        Link your {isEmployer ? "company, work-tools and payout" : "professional profiles, portfolio and payout"} accounts.
        We keep credentials encrypted and never post on your behalf without approval.
      </p>

      {/* Existing connections */}
      {accounts.length > 0 && (
        <section className="mb-10">
          <p className="overline mb-4">Active</p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {accounts.map((a) => {
              const Icon = ICONS[a.provider] || Globe;
              return (
                <div key={a.id} className="hard-border bg-white p-5 flex items-center gap-4">
                  <Icon size={26} weight="duotone" color="#6B21A8"/>
                  <div className="min-w-0 flex-1">
                    <p className="font-display font-extrabold text-lg tracking-tight">{a.provider_name}</p>
                    <p className="text-xs font-mono text-neutral-500 truncate">{a.handle}</p>
                  </div>
                  <button onClick={() => disconnect(a.id)} className="hard-border p-2 hover:bg-[#6B21A8] hover:text-white">
                    <Trash size={16}/>
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Available providers */}
      <div className="grid lg:grid-cols-[1.3fr_1fr] gap-6">
        <section className="hard-border bg-white p-8 shadow-brutal">
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-4">Available for {user?.role || "you"}</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {providers.map((p) => {
              const Icon = ICONS[p.id] || Globe;
              const active = selected?.id === p.id;
              return (
                <button key={p.id} type="button" onClick={() => setSelected(p)}
                        className={`hard-border p-4 text-left ${active ? "bg-[#0A0A0A] text-white" : "bg-white"}`}>
                  <Icon size={22} weight="duotone" color={active ? "#fff" : "#6B21A8"}/>
                  <p className="font-display font-extrabold mt-2">{p.name}</p>
                  <p className="text-xs opacity-70">{p.handle_label}</p>
                </button>
              );
            })}
          </div>
        </section>

        <section className="hard-border bg-[#F5F3FF] p-8 shadow-brutal">
          <h2 className="font-display font-extrabold text-2xl tracking-tight mb-4">
            {selected ? `Connect ${selected.name}` : "Pick a provider →"}
          </h2>
          {!selected ? (
            <p className="text-sm text-neutral-600">Select any provider on the left. You&apos;ll only need to paste a handle
              (like a profile URL or username). API tokens are optional and only required for automated syncs.</p>
          ) : (
            <form onSubmit={connect} className="space-y-4">
              <div>
                <label className="overline block mb-2">{selected.handle_label}</label>
                <input value={handle} onChange={(e) => setHandle(e.target.value)} required
                       className="w-full hard-border px-3 py-3 bg-white focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <div>
                <label className="overline block mb-2">API token (optional)</label>
                <input value={token} onChange={(e) => setToken(e.target.value)} type="password"
                       className="w-full hard-border px-3 py-3 bg-white focus:outline-none focus:border-[#6B21A8] font-mono"/>
              </div>
              <button type="submit" className="btn-primary w-full">Connect {selected.name} →</button>
            </form>
          )}
        </section>
      </div>
    </main>
  );
}
