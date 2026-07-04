"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { btnClass, fieldClass, labelClass } from "@/components/AuthShell";
import { claimAccount } from "./actions";

export function ClaimForm({ token, email }: { token: string; email: string }) {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const formData = new FormData();
    formData.set("token", token);
    formData.set("fullName", fullName);
    formData.set("password", password);
    const result = await claimAccount(formData);
    setLoading(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push("/onboarding");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label className={labelClass}>Email</label>
        <input type="email" value={email} disabled className={`${fieldClass} bg-slate-50 text-slate-500`} />
      </div>
      <div>
        <label htmlFor="fullName" className={labelClass}>Full name</label>
        <input id="fullName" type="text" required autoComplete="name"
          className={fieldClass} value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </div>
      <div>
        <label htmlFor="password" className={labelClass}>Set a password</label>
        <input id="password" type="password" required autoComplete="new-password"
          className={fieldClass} value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button type="submit" className={btnClass} disabled={loading}>
        {loading ? "Setting up your account…" : "Finish setting up my account"}
      </button>
    </form>
  );
}
