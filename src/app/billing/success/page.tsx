import Link from "next/link";
import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { requireUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { hasActiveSubscription } from "@/lib/subscription";

export const metadata: Metadata = {
  title: "Payment received — Mobi Estimates",
  robots: { index: false },
};

export default async function CheckoutSuccessPage() {
  const user = await requireUser();
  if (isStaff(user.role)) redirect("/admin");

  const companyId = await getPrimaryCompanyId();
  if (!companyId) redirect("/onboarding");

  // The webhook is the source of truth and may land a moment after this page.
  const active = await hasActiveSubscription(companyId);

  return (
    <main className="grid min-h-screen place-items-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-green-100 text-2xl">
          {active ? "✓" : "⏳"}
        </div>
        <h1 className="mt-4 text-xl font-bold text-navy">
          {active ? "You're all set!" : "Payment received"}
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          {active
            ? "Your subscription is active. Welcome to Mobi Estimates — your portal is ready."
            : "We're activating your account. This usually takes a few seconds — refresh this page if your portal isn't unlocked yet."}
        </p>
        <Link
          href={active ? "/portal" : "/billing/success"}
          className="mt-6 inline-block w-full rounded-full bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-dark"
        >
          {active ? "Go to my portal" : "Refresh"}
        </Link>
      </div>
    </main>
  );
}
