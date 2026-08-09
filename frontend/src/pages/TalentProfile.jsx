import React, { useEffect, useState } from "react";
import api, { formatErr } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { toast } from "sonner";
import { Sparkle } from "@phosphor-icons/react";

export default function TalentProfile() {
  const { user, refresh } = useAuth();
  const [p, setP] = useState({
    headline: "", bio: "", skills: [], years_experience: 0,
    hourly_rate: 0, location: "", portfolio_url: "", avatar_url: "", company: "",
  });
  const [skillsInput, setSkillsInput] = useState("");
  const [suggest, setSuggest] = useState(null);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);

  useEffect(() => {
    if (user && user.profile) {
      setP({ ...p, ...user.profile });
      setSkillsInput((user.profile.skills || []).join(", "));
    }
    // eslint-disable-next-line
  }, [user]);

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
      await api.put("/profile", { ...p, skills, years_experience: Number(p.years_experience || 0), hourly_rate: Number(p.hourly_rate || 0) });
      await refresh();
      toast.success("Profile saved");
    } catch (e) { toast.error(formatErr(e)); }
    finally { setSaving(false); }
  };

  const isEmployer = user?.role === "employer";

  return (
    <main className="max-w-4xl mx-auto px-6 md:px-12 py-16">
      <p className="overline text-[#002FA7] mb-3">{isEmployer ? "COMPANY PROFILE" : "TALENT PROFILE"}</p>
      <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-10">
        Showcase what you do best.
      </h1>

      <form onSubmit={save} className="hard-border bg-white p-8 md:p-12 shadow-brutal space-y-6">
        <div>
          <label className="overline block mb-2">Headline</label>
          <input data-testid={TID.profileHeadline} value={p.headline || ""} onChange={(e) => setP({ ...p, headline: e.target.value })}
                 placeholder="Senior Product Designer · Design Systems"
                 className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
        </div>
        <div>
          <label className="overline block mb-2">Bio</label>
          <textarea data-testid={TID.profileBio} value={p.bio || ""} onChange={(e) => setP({ ...p, bio: e.target.value })}
                    rows={4} placeholder="What you do, for whom, and how"
                    className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
        </div>
        {!isEmployer && (
          <>
            <div>
              <label className="overline block mb-2">Skills (comma-separated)</label>
              <input data-testid={TID.profileSkills} value={skillsInput} onChange={(e) => setSkillsInput(e.target.value)}
                     placeholder="React, TypeScript, Node.js, Figma"
                     className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
            </div>
            <div className="grid md:grid-cols-2 gap-6">
              <div>
                <label className="overline block mb-2">Years of experience</label>
                <input data-testid={TID.profileYears} type="number" min="0" value={p.years_experience || 0}
                       onChange={(e) => setP({ ...p, years_experience: e.target.value })}
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
              </div>
              <div>
                <label className="overline block mb-2">Location</label>
                <input data-testid={TID.profileLocation} value={p.location || ""} onChange={(e) => setP({ ...p, location: e.target.value })}
                       placeholder="London, UK"
                       className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
              </div>
            </div>

            {/* AI Rate Suggest */}
            <div className="hard-border bg-[#FDFCF0] p-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <p className="overline text-[#002FA7] mb-1">AI-powered rate suggestion</p>
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
                            className="hard-border p-3 bg-white text-left hover:bg-[#002FA7] hover:text-white">
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
                     className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
            </div>
            <div>
              <label className="overline block mb-2">Portfolio URL</label>
              <input data-testid={TID.profilePortfolio} value={p.portfolio_url || ""}
                     onChange={(e) => setP({ ...p, portfolio_url: e.target.value })}
                     placeholder="https://…"
                     className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
            </div>
          </>
        )}
        {isEmployer && (
          <div>
            <label className="overline block mb-2">Company</label>
            <input value={p.company || ""} onChange={(e) => setP({ ...p, company: e.target.value })}
                   className="w-full hard-border px-3 py-3 focus:outline-none focus:border-[#002FA7]"/>
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
