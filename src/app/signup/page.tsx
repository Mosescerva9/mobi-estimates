"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { AuthShell, btnClass, fieldClass, labelClass } from "@/components/AuthShell";
import { isApprovedOfferId } from "@/lib/pricing";

function SignupForm() {
  const router = useRouter();
  const params = useSearchParams();
  // Preserve the plan the visitor selected on the pricing page (validated again
  // server-side at /start). Anything unrecognized is ignored.
  const planParam = params.get("plan");
  const plan = isApprovedOfferId(planParam) ? planParam : null;
  // Where to send the user once they have an account.
  const next = plan ? `/start?plan=${plan}` : "/onboarding";
  const signInHref = `/login?redirect=${encodeURIComponent(next)}`;

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
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo:
          typeof window !== "undefined"
            ? `${window.location.origin}${signInHref}`
            : undefined,
      },
    });
    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }
    // If email confirmation is disabled, a session exists immediately — continue
    // straight to the selected-plan flow. Otherwise prompt to verify email.
    if (data.session) {
      router.push(next);
      router.refresh();
      return;
    }
    setDone(true);
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle={
        plan
          ? "Create your account to continue to secure checkout for your selected plan."
          : "Set up access to submit projects and receive estimates."
      }
      footer={
        <>
          Already have an account?{" "}
          <Link href={signInHref} className="font-semibold text-brand">Sign in</Link>
        </>
      }
    >
      {done ? (
        <p className="text-[15px] text-slate-600">
          Check your email to verify your address, then sign in to continue. If
          email verification is disabled on the project, you can{" "}
          <Link href={signInHref} className="font-semibold text-brand">sign in now</Link>.
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

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}
