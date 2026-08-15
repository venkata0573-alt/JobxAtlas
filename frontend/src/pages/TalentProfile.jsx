import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";
import { Sparkle } from "@phosphor-icons/react";

export default function TalentProfile() {
  const { user, refresh } = useAuth();
  const [p, setP] = useState({
    headline: "", bio: "", skills: [], industries: [], years_experience: 0,
    hourly_rate: 0, location: "", portfolio_url: "", avatar_url: "", company: "",
  });
  const [skillsInput, setSkillsInput] = useState("");
  const [industryList, setIndustryList] = useState([]);
  const [suggest, setSuggest] = useState(null);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  const uploadAvatar = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    if (f.size > 3 * 1024 * 1024) return toast.error("Avatar must be under 3 MB");
    const form = new FormData(); form.append("file", f); form.append("kind", "avatar");
    setUploadingAvatar(true);
    try {
      const r = await api.post("/files/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      setP((prev) => ({ ...prev, avatar_url: r.data.url }));
      await refresh();
      toast.success("Avatar updated");
    } catch (err) { toast.error(formatErr(err)); }
    finally { setUploadingAvatar(false); }
  };

  useEffect(() => {
    if (user && user.profile) {
      setP({ ...p, ...user.profile, industries: user.profile.industries || [] });
      setSkillsInput((user.profile.skills || []).join(", "));
    }
    // eslint-disable-next-line
  }, [user]);

  useEffect(() => {
    api.get("/marketplace/industries").then((r) => setIndustryList(r.data.industries || [])).catch(() => {});
  }, []);

  const toggleIndustry = (label) => {
    setP((prev) => {
      const current = new Set(prev.industries || []);
      if (current.has(label)) current.delete(label); else current.add(label);
      return { ...prev, industries: Array.from(current) };
    });
  };

  const doSuggest = async () => {
    const skills = skillsInput.split(",").map((s) => s.trim()).filter(Boolean);
    if (!skills.length) return toast.error("Add at least one skill first");
    setSuggesting(true);
    try {
      const r = await api.post("/profile/suggest-rate", {
        skills, years_experience: Number(p.years_experience || 0), location: p.location || "Global",
      });
      setSuggest(r.data);
      toast.success(`AI suggests $${r.data.mid}/hr`);
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSuggesting(false); }
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const skills = skillsInput.split(",").map((s) => s.trim()).filter(Boolean);
      await api.put("/profile", { ...p, skills, industries: p.industries || [], years_experience: Number(p.years_experience || 0), hourly_rate: Number(p.hourly_rate || 0) });
      await refresh();
      toast.success("Profile saved");
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSaving(false); }
  };

  const isEmployer = user?.role === "employer";

  return (
    <main className="max-w-4xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#6B21A8] mb-3">{isEmployer ? "COMPANY PROFILE" : "TALENT PROFILE"}</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-10">
        Showcase what you do best.
      </h1>

      <form onSubmit={save} className="hard-border bg-white p-8 md:p-12 shadow-brutal space-y-6">
        {/* Avatar uploader */}
        <div className="flex items-center gap-5">
          <div className="w-20 h-20 hard-border bg-neutral-100 flex items-center justify-center overflow-hidden">
            {p.avatar_url ? (
              <img src={`${process.env.REACT_APP_BACKEND_URL}${p.avatar_url}`}
                   alt="avatar" className="w-full h-full object-cover"/>
            ) : (
              <span className="font-display font-black text-2xl text-neutral-400">
                {(user?.name || "?").charAt(0).toUpperCase()}
              </span>
            )}
          </div>
          <div className="flex-1">
            <p className="overline mb-1">Profile photo</p>
            <label className="btn-outline text-sm inline-block cursor-pointer">
              {uploadingAvatar ? "Uploading…" : (p.avatar_url ? "Change photo" : "Upload photo")}
              <input type="file" onChange={uploadAvatar} className="hidden"
                     accept="image/png,image/jpeg,image/webp,image/gif"/>
            </label>
            <p className="text-xs text-neutral-500 mt-2 font-mono">PNG / JPG / WebP up to 3 MB</p>
          </div>
        </div>

        <div>
          <label className="overline block mb-2">Headline</label>
          <input data-testid={TID.profileHeadline} value={p.headline || ""} onChange={(e) => setP({ ...p, headline: e.target.value })}
                 placeholder="Senior Product Designer · Design Systems"
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
        </div>
        <div>
          <label className="overline block mb-2">Bio</label>
          <textarea data-testid={TID.profileBio} value={p.bio || ""} onChange={(e) => setP({ ...p, bio: e.target.value })}
                    rows={4} placeholder="What you do, for whom, and how"
                    className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
        </div>
        {!isEmployer && (
          <>
            <div>
              <label className="overline block mb-2">Skills (comma-separated)</label>
              <input data-testid={TID.profileSkills} value={skillsInput} onChange={(e) => setSkillsInput(e.target.value)}
                     placeholder="React, TypeScript, Node.js, Figma"
                     className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
            </div>

            <div data-testid="talent-industry-picker">
              <label className="overline block mb-2">Industries you serve (pick all that apply)</label>
              {industryList.length === 0 ? (
                <p className="text-xs text-neutral-500 font-mono">Loading industries…</p>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {industryList.map((i) => {
                    const active = (p.industries || []).includes(i.label);
                    return (
                      <button
                        key={i.label}
                        type="button"
                        onClick={() => toggleIndustry(i.label)}
                        data-testid={`talent-industry-${i.label.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}
                        className={`hard-border px-3 py-2 text-left text-xs transition-colors ${
                          active ? "bg-[#0B1B2B] text-white border-[#0B1B2B]" : "bg-white hover:bg-[#F5F3FF]"
                        }`}>
                        <span className="font-display font-bold leading-tight block">{i.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
              <p className="text-xs text-neutral-500 mt-2">
                Employers searching by industry on <code className="font-mono">/browse?industry=…</code> will see your profile in matching results.
              </p>
            </div>
            <div className="grid md:grid-cols-2 gap-6">
              <div>
                <label className="overline block mb-2">Years of experience</label>
                <input data-testid={TID.profileYears} type="number" min="0" value={p.years_experience || 0}
                       onChange={(e) => setP({ ...p, years_experience: e.target.value })}
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
              </div>
              <div>
                <label className="overline block mb-2">Location</label>
                <input data-testid={TID.profileLocation} value={p.location || ""} onChange={(e) => setP({ ...p, location: e.target.value })}
                       placeholder="London, UK"
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
              </div>
            </div>

            {/* AI Rate Suggest */}
            <div className="hard-border bg-[#F5F3FF] p-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <p className="overline text-[#6B21A8] mb-1">AI-powered rate suggestion</p>
                  <p className="text-sm text-neutral-600">Claude analyses your skills and experience against market rates.</p>
                </div>
                <button type="button" onClick={doSuggest} disabled={suggesting}
                        data-testid={TID.profileSuggestRate} className="btn-outline text-sm flex items-center gap-2 whitespace-nowrap">
                  <Sparkle size={14} weight="fill"/> {suggesting ? "Analysing…" : "Suggest rate"}
                </button>
              </div>
              {suggest && (
                <div className="grid grid-cols-3 gap-2 mt-3">
                  {["low", "mid", "high"].map((k) => (
                    <button type="button" key={k} onClick={() => setP({ ...p, hourly_rate: suggest[k] })}
                            className="hard-border p-3 bg-white text-left hover:bg-[#6B21A8] hover:text-white">
                      <div className="overline">{k}</div>
                      <div className="font-display font-extrabold text-2xl">${suggest[k]}</div>
                    </button>
                  ))}
                  <p className="col-span-3 text-xs text-neutral-600 mt-2 leading-relaxed">{suggest.rationale}</p>
                </div>
              )}
            </div>

            <div>
              <label className="overline block mb-2">Your hourly rate (USD)</label>
              <input data-testid={TID.profileHourlyRate} type="number" min="0" step="1" value={p.hourly_rate || 0}
                     onChange={(e) => setP({ ...p, hourly_rate: e.target.value })}
                     className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
            </div>
            <div>
              <label className="overline block mb-2">Portfolio URL</label>
              <input data-testid={TID.profilePortfolio} value={p.portfolio_url || ""}
                     onChange={(e) => setP({ ...p, portfolio_url: e.target.value })}
                     placeholder="https://…"
                     className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
            </div>
          </>
        )}
        {isEmployer && (
          <div>
            <label className="overline block mb-2">Company</label>
            <input value={p.company || ""} onChange={(e) => setP({ ...p, company: e.target.value })}
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#6B21A8]"/>
            <label className="overline block mt-4 mb-2">Company logo</label>
            <div className="flex items-center gap-4">
              {p.company_logo_url && (
                <img src={`${process.env.REACT_APP_BACKEND_URL}${p.company_logo_url}`}
                     alt="logo" className="w-16 h-16 object-contain hard-border bg-neutral-50 p-1"/>
              )}
              <label className="btn-outline text-sm inline-block cursor-pointer">
                {p.company_logo_url ? "Change logo" : "Upload logo"}
                <input type="file" className="hidden" accept="image/*"
                       onChange={async (e) => {
                         const f = e.target.files?.[0]; if (!f) return;
                         const form = new FormData(); form.append("file", f); form.append("kind", "company_logo");
                         try {
                           const r = await api.post("/files/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
                           setP({ ...p, company_logo_url: r.data.url });
                           await refresh(); toast.success("Logo updated");
                         } catch (err) { toast.error(formatErr(err)); }
                       }}/>
              </label>
            </div>
          </div>
        )}

        {!isEmployer && (
          <div>
            <label className="overline block mb-2">Portfolio gallery (up to 6)</label>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-3">
              {(p.portfolio_images || []).map((url, x) => (
                <img key={x} src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt=""
                     className="w-full aspect-square object-cover hard-border"/>
              ))}
              {(p.portfolio_images || []).length < 6 && (
                <label className="w-full aspect-square hard-border bg-neutral-50 flex items-center justify-center text-2xl text-neutral-400 cursor-pointer hover:bg-[#0B1B2B] hover:text-white">
                  +
                  <input type="file" className="hidden" accept="image/*"
                         onChange={async (e) => {
                           const f = e.target.files?.[0]; if (!f) return;
                           const form = new FormData(); form.append("file", f); form.append("kind", "portfolio");
                           try {
                             const r = await api.post("/files/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
                             setP({ ...p, portfolio_images: [...(p.portfolio_images || []), r.data.url].slice(-6) });
                             await refresh(); toast.success("Added to gallery");
                           } catch (err) { toast.error(formatErr(err)); }
                         }}/>
                </label>
              )}
            </div>
            <p className="text-xs text-neutral-500 font-mono">Newest replaces oldest above 6. Displayed on your Browse card.</p>
          </div>
        )}
        <button type="submit" disabled={saving} data-testid={TID.profileSave}
                className="btn-primary w-full md:w-auto">
          {saving ? "Saving…" : "Save profile"}
        </button>
      </form>
    </main>
  );
}
