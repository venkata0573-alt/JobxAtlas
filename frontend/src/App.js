import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import "@/App.css";

import { AuthProvider } from "@/context/AuthContext";
import Header from "@/components/Header";
import ProtectedRoute from "@/components/ProtectedRoute";

import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import BrowseTalent from "@/pages/BrowseTalent";
import TalentProfile from "@/pages/TalentProfile";
import TalentDashboard from "@/pages/TalentDashboard";
import EmployerDashboard from "@/pages/EmployerDashboard";
import PurchaseHours from "@/pages/PurchaseHours";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PaymentCancel from "@/pages/PaymentCancel";
import EngagementDetail from "@/pages/EngagementDetail";
import Integrations from "@/pages/Integrations";

function App() {
  return (
    <div className="App min-h-screen">
      <BrowserRouter>
        <AuthProvider>
          <Header />
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/browse" element={<BrowseTalent />} />
            <Route path="/talent" element={<ProtectedRoute role="talent"><TalentDashboard /></ProtectedRoute>} />
            <Route path="/talent/profile" element={<ProtectedRoute role="talent"><TalentProfile /></ProtectedRoute>} />
            <Route path="/employer" element={<ProtectedRoute role="employer"><EmployerDashboard /></ProtectedRoute>} />
            <Route path="/employer/purchase" element={<ProtectedRoute role="employer"><PurchaseHours /></ProtectedRoute>} />
            <Route path="/payment/success" element={<ProtectedRoute><PaymentSuccess /></ProtectedRoute>} />
            <Route path="/payment/cancel" element={<ProtectedRoute><PaymentCancel /></ProtectedRoute>} />
            <Route path="/engagement/:id" element={<ProtectedRoute><EngagementDetail /></ProtectedRoute>} />
            <Route path="/integrations" element={<ProtectedRoute><Integrations /></ProtectedRoute>} />
          </Routes>
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
