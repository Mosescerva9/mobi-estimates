"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function ManageBillingButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function open() {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/stripe/portal", { method: "POST" });
      const data = await res.json();
      if (!res.ok || !data.url) {
        if (data.redirect) {
          router.push(data.redirect as string);
          return;
        }
        throw new Error(data.error || "Could not open billing portal.");
      }
      window.location.href = data.url as string;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setLoading(false);
    }
  }

  return (
    <div>
      <button onClick={open} disabled={loading}
        className="rounded-full bg-brand px-5 py-2.5 font-semibold text-white transition hover:bg-brand-dark disabled:opacity-60">
        {loading ? "Opening…" : "Manage billing"}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
