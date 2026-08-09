import React, { useState } from "react";
import { Play } from "@phosphor-icons/react";

const DEMOS = {
  employer: {
    label: "For Employers",
    title: "Buy hours. Assemble a team in 60 seconds.",
    steps: [
      "Post a scope or shortlist talent from our vetted marketplace",
      "Purchase an hour package via Stripe (starts at 10h)",
      "Mix & match those hours across multiple people",
      "Both sides sign a contract with a 12-month exclusivity clause",
      "Track work through Jira, Asana, Confluence, SAP or an uploaded plan",
    ],
    poster: "https://images.unsplash.com/photo-1758518729685-f88df7890776?crop=entropy&cs=srgb&fm=jpg&w=1280",
    video: "https://videos.pexels.com/video-files/3196284/3196284-uhd_2560_1440_25fps.mp4",
  },
  talent: {
    label: "For Individuals",
    title: "Set your rate. Choose your clients. Own your calendar.",
    steps: [
      "Add your skills — let AI suggest a market-fair hourly rate",
      "Raise an Expression of Interest for any employer, in any timezone",
      "Sign the contract with a single typed signature",
      "Manage availability across multiple engagements from one calendar",
      "Get paid through the platform — no direct-hire loopholes",
    ],
    poster: "https://images.pexels.com/photos/16029823/pexels-photo-16029823.jpeg?auto=compress&cs=tinysrgb&w=1280",
    video: "https://videos.pexels.com/video-files/5453622/5453622-uhd_2560_1440_25fps.mp4",
  },
};

export default function DemoTabs() {
  const [tab, setTab] = useState("employer");
  const d = DEMOS[tab];

  return (
    <section className="bg-white border-t border-black/10">
      <div className="max-w-7xl mx-auto px-6 md:px-12 py-24">
        <div className="flex items-baseline justify-between flex-wrap gap-6 mb-10">
          <div>
            <p className="overline text-[#002FA7] mb-3">SEE IT IN ACTION</p>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight max-w-2xl">
              90 seconds. Two perspectives. One platform.
            </h2>
          </div>
          <div className="hard-border inline-flex bg-white">
            {Object.entries(DEMOS).map(([id, v]) => (
              <button key={id} onClick={() => setTab(id)} data-testid={`demo-tab-${id}`}
                      className={`px-5 py-3 font-display font-extrabold text-sm tracking-tight border-r border-black last:border-r-0 ${tab === id ? "bg-[#0A0A0A] text-white" : "bg-white text-black"}`}>
                {v.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid lg:grid-cols-[1.4fr_1fr] gap-6">
          <div className="hard-border shadow-brutal bg-black relative aspect-video overflow-hidden">
            <video
              key={tab}
              className="w-full h-full object-cover"
              poster={d.poster}
              controls
              preload="metadata"
              data-testid={`demo-video-${tab}`}
            >
              <source src={d.video} type="video/mp4" />
              Your browser does not support the video tag.
            </video>
            <div className="absolute top-3 left-3 hard-border bg-white px-2 py-1 text-[10px] font-mono uppercase">
              <span className="inline-flex items-center gap-1"><Play size={10} weight="fill"/> Demo · {d.label}</span>
            </div>
          </div>

          <aside className="hard-border bg-[#FDFCF0] p-8 shadow-brutal flex flex-col">
            <p className="overline text-[#002FA7] mb-3">Walk-through</p>
            <h3 className="font-display font-extrabold text-2xl md:text-3xl tracking-tight mb-6">{d.title}</h3>
            <ol className="space-y-4">
              {d.steps.map((s, i) => (
                <li key={i} className="flex gap-3">
                  <span className="hard-border bg-[#002FA7] text-white w-7 h-7 flex items-center justify-center font-display font-extrabold flex-shrink-0">
                    {i + 1}
                  </span>
                  <span className="text-sm leading-relaxed">{s}</span>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      </div>
    </section>
  );
}
