import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";

export default function Register() {
  const [f, setF] = useState({ name: "", email: "", password: "", role: "talent" });
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();
  const { setUser } = useAuth();

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
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
