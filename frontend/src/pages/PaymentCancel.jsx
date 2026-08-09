import React from "react";
import { Link } from "react-router-dom";

export default function PaymentCancel() {
  return (
    <main className="max-w-2xl mx-auto px-6 py-24 text-center">
      <div className="hard-border bg-white p-12 shadow-brutal">
        <h1 className="font-display font-extrabold text-3xl tracking-tight mb-2">Payment cancelled</h1>
        <p className="text-neutral-600 mb-6">No charge was made. You can try again anytime.</p>
        <Link to="/employer/purchase" className="btn-primary">Try again →</Link>
      </div>
    </main>
  );
}
