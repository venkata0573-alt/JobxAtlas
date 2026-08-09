import React, { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";

export default function Register() {
  const [f, setF] = useState({ name: "", email: "", password: "", role: "talent", company_industry: "" });
  const [loading, setLoading] = useState(false);
  const [industries, setIndustries] = useState([]);
  const nav = useNavigate();
  const { setUser } = useAuth();

  useEffect(() => {
    api.get("/marketplace/industries")
      .then((r) => setIndustries(r.data.industries || []))
      .catch(() => {});
  }, []);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (f.role === "employer" && !f.company_industry) {
      toast.error("Please select the industry that best describes your company");
      return;
    }
    setLoading(true);
    try {
      const r = await api.post("/auth/register", f);
      setUser(r.data);
      toast.success("Welcome to Job Atlas");
      nav(f.role === "employer" ? "/employer" : "/talent/profile");
    } catch (err) {
      toast.error(formatErr(err));
    } finally { setLoading(false); }
  };

  return (
    <main className="max-w-md mx-auto px-6 py-16">
      <p className="overline text-[#002FA7] mb-3">CREATE ACCOUNT</p>
      <h1 className="font-display font-extrabold text-4xl tracking-tight mb-10">Join the marketplace.</h1>
      <form onSubmit={submit} className="hard-border bg-white p-8 shadow-brutal space-y-5">
        <div className="grid grid-cols-2 gap-3">
          <button type="button" onClick={() => setF({ ...f, role: "talent" })}
                  data-testid={TID.registerRoleTalent}
                  className={`hard-border p-4 text-left ${f.role === "talent" ? "bg-[#0A0A0A] text-white" : "bg-white"}`}>
            <div className="overline mb-1">I&apos;m a</div>
            <div className="font-display font-extrabold text-xl">Talent</div>
          </button>
          <button type="button" onClick={() => setF({ ...f, role: "employer" })}
                  data-testid={TID.registerRoleEmployer}
                  className={`hard-border p-4 text-left ${f.role === "employer" ? "bg-[#0A0A0A] text-white" : "bg-white"}`}>
            <div className="overline mb-1">I&apos;m an</div>
            <div className="font-display font-extrabold text-xl">Employer</div>
          </button>
        </div>
        <div>
          <label className="overline block mb-2">Name</label>
          <input data-testid={TID.registerName} required value={f.name} onChange={set("name")}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
        </div>
        <div>
          <label className="overline block mb-2">Email</label>
          <input data-testid={TID.registerEmail} type="email" required value={f.email} onChange={set("email")}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
        </div>
        <div>
          <label className="overline block mb-2">Password</label>
          <input data-testid={TID.registerPassword} type="password" required minLength={6}
                 value={f.password} onChange={set("password")}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
        </div>

        {/* Employer-only: industry self-selection (feeds the Landing trust bar) */}
        {f.role === "employer" && (
          <div data-testid="industry-picker">
            <label className="overline block mb-3">Which best describes your company?</label>
            {industries.length === 0 ? (
              <p className="text-xs text-neutral-500 font-mono">Loading industries…</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {industries.map((i) => {
                  const selected = f.company_industry === i.label;
                  return (
                    <button
                      key={i.label}
                      type="button"
                      onClick={() => setF({ ...f, company_industry: i.label })}
                      data-testid={`industry-${i.label.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}
                      className={`hard-border px-3 py-3 text-left transition-colors ${
                        selected ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "bg-white hover:bg-[#FAF9F6]"
                      }`}>
                      <span className="block text-sm font-display font-bold leading-tight">{i.label}</span>
                      {i.count > 0 && (
                        <span className={`block mt-1 text-[10px] font-mono tracking-widest ${selected ? "text-[#F0C260]" : "text-[#C79A3B]"}`}>
                          {i.count} ON PLATFORM
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
            <input type="hidden" name="company_industry" value={f.company_industry} data-testid="register-industry"/>
            <p className="text-xs text-neutral-500 mt-3">
              Anonymised in aggregate on our public trust bar. Your company name is never shown.
            </p>
          </div>
        )}

        <button type="submit" disabled={loading}
                data-testid={TID.registerSubmit} className="btn-primary w-full">
          {loading ? "Creating account…" : "Create account →"}
        </button>
        <p className="text-sm text-neutral-500">
          Have an account? <Link to="/login" className="underline">Sign in</Link>
        </p>
      </form>
    </main>
  );
}
