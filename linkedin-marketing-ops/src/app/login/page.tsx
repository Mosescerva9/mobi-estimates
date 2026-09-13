"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const params = useSearchParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  // Detect a misconfigured hosted deployment (no OPS_PASSWORD) so we show a
  // plain-language configuration message instead of a login form that can
  // never succeed.
  useEffect(() => {
    let active = true;
    fetch("/api/auth/status")
      .then((res) => res.json())
      .then((data) => {
        if (active && data?.configError) setConfigError(data.configError);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Login failed");
        setBusy(false);
        return;
      }
      const requestedNext = params.get("next");
      const safeNext =
        requestedNext?.startsWith("/") && !requestedNext.startsWith("//")
          ? requestedNext
          : "/";
      // A full navigation guarantees the new HttpOnly session cookie is applied
      // before the protected dashboard is requested.
      window.location.assign(safeNext);
    } catch {
      setError("Login failed");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-12">
      <div className="panel rise p-6">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-blueprint">
          Mobi Estimating
        </p>
        <h1 className="mt-2 font-display text-2xl font-semibold text-steel-900">
          LinkedIn Ops login
        </h1>
        {configError ? (
          <div className="mt-4 border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-900">
            <p className="font-semibold">Access not configured</p>
            <p className="mt-1">{configError}</p>
          </div>
        ) : checking ? (
          <p className="mt-4 text-sm text-steel-700">Loading…</p>
        ) : (
          <>
        <p className="mt-2 text-sm text-steel-700">
          Enter the ops password to review and approve drafts.
        </p>
        <form className="mt-5 space-y-3" onSubmit={onSubmit}>
          <label className="block text-sm">
            Password
            <input
              type="password"
              className="field mt-1"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && (
            <p className="border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary w-full" disabled={busy}>
            {busy ? "Checking…" : "Enter dashboard"}
          </button>
        </form>
          </>
        )}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex min-h-screen max-w-md items-center justify-center px-4">
          <p className="text-steel-700">Loading…</p>
        </main>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
