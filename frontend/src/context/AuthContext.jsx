import React, { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null=loading, false=guest, obj=user
  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(false));
  }, []);
  const value = {
    user,
    setUser,
    logout: async () => { await api.post("/auth/logout"); setUser(false); },
    refresh: async () => { const r = await api.get("/auth/me"); setUser(r.data); return r.data; },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);
