import Link from "next/link";
import type { Metadata } from "next";
import { createAdminClient } from "@/lib/supabase/admin";
import { AuthShell, btnClass } from "@/components/AuthShell";
import { ClaimForm } from "./ClaimForm";

export const metadata: Metadata = {
  title: "Finish setting up your account — Mobi Estimates",
  robots: { index: false },
};

export default async function CheckoutCompletePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  if (!token) {
    return (
      <AuthShell title="Missing link">
        <p className="text-sm text-slate-600">
          This page needs a valid link from your checkout confirmation email or the payment redirect.
        </p>
      </AuthShell>
    );
  }

  const admin = createAdminClient();
  const { data: claim } = await admin
    .from("checkout_claims")
    .select("email, paid_at, claimed_at, auth_user_id")
    .eq("claim_token", token)
    .maybeSingle();

  if (!claim) {
    return (
      <AuthShell title="We couldn't find that purchase">
        <p className="text-sm text-slate-600">
          This link may have expired or been mistyped. If you just paid, check your email for the confirmation link,
          or contact support.
        </p>
      </AuthShell>
    );
  }

  if (!claim.paid_at) {
    return (
      <AuthShell title="Confirming your payment…">
        <p className="text-sm text-slate-600">
          This usually takes just a few seconds. Refresh this page if it doesn&apos;t update.
        </p>
        <Link href={`/checkout/complete?token=${token}`} className={`${btnClass} mt-6 inline-block text-center`}>
          Refresh
        </Link>
      </AuthShell>
    );
  }

  if (claim.claimed_at) {
    return (
      <AuthShell title="You're already set up">
        <p className="text-sm text-slate-600">This purchase already has an account and company attached.</p>
        <Link href="/login" className={`${btnClass} mt-6 inline-block text-center`}>
          Log in
        </Link>
      </AuthShell>
    );
  }

  if (claim.auth_user_id) {
    return (
      <AuthShell title="Finish setting up your company">
        <p className="text-sm text-slate-600">
          This purchase is linked to an account, but company setup still needs to be finished before your portal unlocks.
        </p>
        <Link href={`/login?redirect=${encodeURIComponent("/billing/success")}`} className={`${btnClass} mt-6 inline-block text-center`}>
          Continue setup
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Payment received" subtitle="Set a password, or enter your existing password if this email already has a Mobi account.">
      <ClaimForm token={token} email={claim.email ?? ""} />
    </AuthShell>
  );
}
