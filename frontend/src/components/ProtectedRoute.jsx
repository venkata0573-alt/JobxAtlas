import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export default function ProtectedRoute({ children, role }) {
  const { user } = useAuth();
  if (user === null) return <div className="p-16 text-center font-mono">Loading…</div>;
  if (user === false) return <Navigate to="/login" replace />;
  if (role && user.role !== role && user.role !== "admin") return <Navigate to="/" replace />;
  return children;
}
