"use client";

import { useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { AuthShell, btnClass, fieldClass, labelClass } from "@/components/AuthShell";

export default function SignupPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Use at least 8 characters for your password.");
      return;
    }
    setLoading(true);
    const supabase = createClient();
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo:
          typeof window !== "undefined" ? `${window.location.origin}/login` : undefined,
      },
    });
    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }
    setDone(true);
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Set up access to submit projects and receive estimates."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-brand">Sign in</Link>
        </>
      }
    >
      {done ? (
        <p className="text-[15px] text-slate-600">
          Check your email to verify your address, then sign in. If email
          verification is disabled on the project, you can sign in now.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="name" className={labelClass}>Full name</label>
            <input id="name" type="text" required autoComplete="name"
              className={fieldClass} value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div>
            <label htmlFor="email" className={labelClass}>Work email</label>
            <input id="email" type="email" required autoComplete="email"
              className={fieldClass} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label htmlFor="password" className={labelClass}>Password</label>
            <input id="password" type="password" required autoComplete="new-password"
              className={fieldClass} value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button type="submit" className={btnClass} disabled={loading}>
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
