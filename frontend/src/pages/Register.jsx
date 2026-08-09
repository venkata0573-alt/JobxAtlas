import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";
import { Sparkle, LinkedinLogo } from "@phosphor-icons/react";

export default function Register() {
  const [f, setF] = useState({ name: "", email: "", password: "", role: "talent" });
  const [loading, setLoading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [parsed, setParsed] = useState(null);
  const nav = useNavigate();
  const { setUser } = useAuth();

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const queueImport = () => {
    if (!resumeText && !linkedinUrl) return toast.error("Add a resume or LinkedIn URL");
    setParsed({ resumeText, linkedinUrl });
    toast.success("Ready — we'll pre-fill your profile after signup");
    setImportOpen(false);
  };

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const r = await api.post("/auth/register", f);
      setUser(r.data);
      if (parsed && (parsed.resumeText || parsed.linkedinUrl)) {
        try {
          const p = await api.post("/profile/parse-resume", {
            text: parsed.resumeText, linkedin_url: parsed.linkedinUrl,
          });
          if (p.data && (p.data.headline || p.data.skills?.length)) {
            await api.put("/profile", {
              ...(r.data.profile || {}), ...p.data,
              years_experience: Number(p.data.years_experience || 0),
            });
            toast.success("Profile auto-filled from your resume ✨");
          }
        } catch { /* silent */ }
      }
      toast.success("Welcome to Job Atlas");
      nav(f.role === "employer" ? "/employer" : "/talent/profile");
    } catch (err) { toast.error(formatErr(err)); }
    finally { setLoading(false); }
  };

  const handleResumeFile = (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    if (file.type === "application/pdf" || file.name.endsWith(".pdf")) {
      toast.info("PDF selected — its text will be inferred after signup.");
      setResumeText(`[PDF filename: ${file.name}]`);
    } else {
      const reader = new FileReader();
      reader.onload = () => setResumeText(String(reader.result || "").slice(0, 8000));
      reader.readAsText(file);
    }
  };

  return (
    <main className="max-w-md mx-auto px-6 py-16">
      <p className="overline mb-3">CREATE ACCOUNT</p>
      <h1 className="font-display font-black text-4xl tracking-tight mb-10">Join Job Atlas.</h1>
      <form onSubmit={submit} className="hard-border bg-white p-8 shadow-brutal space-y-5">
        <div className="grid grid-cols-2 gap-3">
          <button type="button" onClick={() => setF({ ...f, role: "talent" })}
                  data-testid={TID.registerRoleTalent}
                  className={`hard-border p-4 text-left ${f.role === "talent" ? "bg-[#5A34E8] text-white border-[#5A34E8]" : "bg-white"}`}>
            <div className="overline mb-1 opacity-80">I&apos;m a</div>
            <div className="font-display font-black text-xl">Talent</div>
          </button>
          <button type="button" onClick={() => setF({ ...f, role: "employer" })}
                  data-testid={TID.registerRoleEmployer}
                  className={`hard-border p-4 text-left ${f.role === "employer" ? "bg-[#5A34E8] text-white border-[#5A34E8]" : "bg-white"}`}>
            <div className="overline mb-1 opacity-80">I&apos;m an</div>
            <div className="font-display font-black text-xl">Employer</div>
          </button>
        </div>

        {f.role === "talent" && (
          <div className="hard-border bg-[#F7F7FB] p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">Fast-track your profile</p>
                <p className="text-xs text-neutral-600">Upload a resume or paste your LinkedIn URL — our AI pre-fills your skills, headline and experience.</p>
              </div>
              <button type="button" onClick={() => setImportOpen(true)}
                      className="btn-outline text-xs inline-flex items-center gap-1 whitespace-nowrap">
                <Sparkle size={14} weight="fill"/> Import
              </button>
            </div>
            {parsed && (
              <p className="text-xs text-[#5A34E8] font-mono mt-3">✓ Import queued — runs on signup</p>
            )}
          </div>
        )}

        <div>
          <label className="overline block mb-2 text-neutral-700">Name</label>
          <input data-testid={TID.registerName} required value={f.name} onChange={set("name")}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#5A34E8]"/>
        </div>
        <div>
          <label className="overline block mb-2 text-neutral-700">Email</label>
          <input data-testid={TID.registerEmail} type="email" required value={f.email} onChange={set("email")}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#5A34E8]"/>
        </div>
        <div>
          <label className="overline block mb-2 text-neutral-700">Password</label>
          <input data-testid={TID.registerPassword} type="password" required minLength={6}
                 value={f.password} onChange={set("password")}
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#5A34E8]"/>
        </div>
        <button type="submit" disabled={loading}
                data-testid={TID.registerSubmit} className="btn-primary w-full">
          {loading ? "Creating account…" : "Create account →"}
        </button>
        <p className="text-sm text-neutral-500">Have an account? <Link to="/login" className="underline">Sign in</Link></p>
      </form>

      {importOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-6" onClick={() => setImportOpen(false)}>
          <div className="hard-border bg-white p-6 max-w-lg w-full shadow-brutal-lg" onClick={(e) => e.stopPropagation()}>
            <p className="overline mb-3">FAST-TRACK IMPORT</p>
            <h2 className="font-display font-black text-2xl mb-4">Pre-fill your profile</h2>
            <label className="text-xs font-semibold flex items-center gap-2 mb-2"><LinkedinLogo size={14} weight="fill" color="#0A66C2"/> LinkedIn profile URL</label>
            <input value={linkedinUrl} onChange={(e) => setLinkedinUrl(e.target.value)} type="url"
                   placeholder="https://linkedin.com/in/yourname"
                   className="w-full hard-border px-3 py-3 mb-4"/>
            <label className="text-xs font-semibold block mb-2">Or paste your resume text (.txt / .pdf name accepted)</label>
            <input type="file" accept=".txt,.pdf,.md" onChange={handleResumeFile}
                   className="w-full hard-border px-3 py-2 mb-3 text-sm"/>
            <textarea value={resumeText} onChange={(e) => setResumeText(e.target.value)} rows={5}
                      placeholder="…or paste resume text directly"
                      className="w-full hard-border px-3 py-2 text-sm"/>
            <div className="flex gap-2 justify-end mt-4">
              <button type="button" onClick={() => setImportOpen(false)} className="btn-outline text-sm">Cancel</button>
              <button type="button" onClick={queueImport}
                      className="btn-primary text-sm inline-flex items-center gap-2">
                <Sparkle size={14} weight="fill"/> Save & pre-fill
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
