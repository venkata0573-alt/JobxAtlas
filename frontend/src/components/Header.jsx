import React from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { TID } from "@/constants/testIds";
import { Lightning } from "@phosphor-icons/react";

export default function Header() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();

  const dashHref = user && user.role === "employer" ? "/employer" : "/talent";

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/70 border-b border-black/10">
      <div className="max-w-7xl mx-auto px-6 md:px-12 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2" data-testid={TID.navLogo}>
          <div className="hard-border bg-[#002FA7] text-white w-8 h-8 flex items-center justify-center">
            <Lightning weight="fill" size={18} />
          </div>
          <span className="font-display font-extrabold text-xl tracking-tight">TALENTHUB</span>
        </Link>
        <nav className="flex items-center gap-3 md:gap-5 text-sm">
          <Link to="/browse" className="hidden md:inline-block hover:underline underline-offset-4"
                data-testid={TID.navBrowse}>Browse Talent</Link>
          {user && user !== false ? (
            <>
              <Link to={dashHref} className="hidden md:inline-block hover:underline underline-offset-4"
                    data-testid={TID.navDashboard}>Dashboard</Link>
              <Link to="/integrations" className="hidden md:inline-block hover:underline underline-offset-4"
                    data-testid={TID.navIntegrations}>Integrations</Link>
              <span className="hidden md:inline-block text-xs text-neutral-500">{user.name}</span>
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
        </nav>
      </div>
    </header>
  );
}
