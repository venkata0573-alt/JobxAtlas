import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { List, X } from "@phosphor-icons/react";

export default function Header() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);

  const dashHref = user && user.role === "employer" ? "/employer" : "/talent";
  const linkCls = "hover:text-[#C79A3B] transition-colors whitespace-nowrap";

  const guestLinks = (
    <>
      <Link to="/browse" className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navBrowse}>Browse Talent</Link>
      <Link to="/pricing" className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navPricing}>Pricing</Link>
    </>
  );

  const userLinks = user && user !== false ? (
    <>
      <Link to="/browse" className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navBrowse}>Browse</Link>
      <Link to={dashHref} className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navDashboard}>Dashboard</Link>
      <Link to="/eoi" className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navEoi}>EOI</Link>
      <Link to="/calendar" className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navCalendar}>Calendar</Link>
      <Link to="/integrations" className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navIntegrations}>Work tools</Link>
      <Link to="/accounts" className={linkCls} onClick={() => setOpen(false)}>Accounts</Link>
      <Link to="/pricing" className={linkCls} onClick={() => setOpen(false)} data-testid={TID.navPricing}>Pricing</Link>
    </>
  ) : null;

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#FAF9F6]/90 border-b border-black/10">
      <div className="max-w-7xl mx-auto px-6 md:px-10 py-4 flex items-center justify-between gap-6">
        <Link to="/" className="flex items-center gap-3" data-testid={TID.navLogo}>
          <img src="/icon.svg" alt="TalentHub" className="w-11 h-11"/>
          <div className="leading-tight">
            <span className="font-display font-black text-xl tracking-tight block">TalentHub</span>
            <span className="text-[9px] font-mono text-[#6B6B6B] tracking-[0.25em] uppercase">by Geminista</span>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-6 text-sm flex-1 justify-center">
          {user ? userLinks : guestLinks}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          {user && user !== false ? (
            <>
              <span className="text-xs text-[#6B6B6B] font-mono">{user.name}</span>
              <button className="btn-outline text-sm" onClick={async () => { await logout(); nav("/"); }}
                      data-testid={TID.navLogout}>Log out</button>
            </>
          ) : user === false ? (
            <>
              {loc.pathname !== "/login" && (
                <Link to="/login" className="btn-outline text-sm" data-testid={TID.navLogin}>Log in</Link>
              )}
              {loc.pathname !== "/register" && (
                <Link to="/register" className="btn-primary text-sm" data-testid={TID.navRegister}>Sign up</Link>
              )}
            </>
          ) : null}
        </div>

        <button className="md:hidden hard-border p-2" onClick={() => setOpen(!open)}>
          {open ? <X size={18}/> : <List size={18}/>}
        </button>
      </div>

      {open && (
        <div className="md:hidden bg-[#FAF9F6] border-t border-black/10 px-6 py-5 space-y-4 text-sm">
          {user ? userLinks : guestLinks}
          {user && user !== false ? (
            <button className="btn-outline text-sm w-full" onClick={async () => { setOpen(false); await logout(); nav("/"); }}>
              Log out
            </button>
          ) : user === false ? (
            <div className="flex gap-2">
              <Link to="/login" className="btn-outline text-sm flex-1 text-center">Log in</Link>
              <Link to="/register" className="btn-primary text-sm flex-1 text-center">Sign up</Link>
            </div>
          ) : null}
        </div>
      )}
    </header>
  );
}
