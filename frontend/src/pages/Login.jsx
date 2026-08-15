import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";

export default function Login() {
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();
  const { setUser } = useAuth();

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const r = await api.post("/auth/login", { email, password: pwd });
      setUser(r.data);
      toast.success(`Welcome back, ${r.data.name}`);
      nav(r.data.role === "employer" ? "/employer" : r.data.role === "talent" ? "/talent" : "/");
    } catch (err) {
      toast.error(formatErr(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-md mx-auto px-6 py-16">
      <p className="overline text-[#6B21A8] mb-3">SIGN IN</p>
      <h1 className="font-display font-extrabold text-4xl tracking-tight mb-10">Welcome back.</h1>
      <form onSubmit={submit} className="hard-border bg-white p-8 shadow-brutal space-y-5">
        <div>
          <label className="overline block mb-2">Email</label>
          <input data-testid={TID.loginEmail} type="email" required value={email}
                 onChange={(e) => setEmail(e.target.value)}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
        </div>
        <div>
          <label className="overline block mb-2">Password</label>
          <input data-testid={TID.loginPassword} type="password" required value={pwd}
                 onChange={(e) => setPwd(e.target.value)}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
        </div>
        <button type="submit" disabled={loading}
                data-testid={TID.loginSubmit} className="btn-primary w-full">
          {loading ? "Signing in…" : "Sign in →"}
        </button>
        <p className="text-sm text-neutral-500">
          No account? <Link to="/register" className="underline">Create one</Link>
        </p>
      </form>
    </main>
  );
}
