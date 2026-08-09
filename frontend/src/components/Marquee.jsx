import React from "react";

export default function Marquee({ text = "12-MONTH EXCLUSIVITY GUARANTEED · PREMIUM VETTED TALENT · MIX & MATCH HOURS · CONTRACTS SIGNED BOTH WAYS ·" }) {
  return (
    <div className="bg-[#0A0A0A] text-white py-3 overflow-hidden border-y border-black">
      <div className="marquee-track">
        {Array.from({ length: 8 }).map((_, i) => (
          <span key={i} className="ticker-item">{text}</span>
        ))}
        {Array.from({ length: 8 }).map((_, i) => (
          <span key={`b${i}`} className="ticker-item">{text}</span>
        ))}
      </div>
    </div>
  );
}
