import Link from "next/link";
import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { requireUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { hasPortalEntitlement } from "@/lib/subscription";
import { finalizeClaim } from "@/app/checkout/complete/actions";

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
  // Entitlement = active subscription OR a paid Pay Per Project order. For the
  // pay-first flow, this page also provides an idempotent recovery point after
  // onboarding: if the customer has a paid unclaimed checkout_claim, try to
  // attach it to their company before deciding whether the portal is unlocked.
  let active = await hasPortalEntitlement(companyId);
  if (!active) {
    try {
      const { claimed } = await finalizeClaim(companyId);
      if (claimed) active = await hasPortalEntitlement(companyId);
    } catch (claimErr) {
      console.error("Failed to finalize checkout claim from billing success page:", claimErr);
    }
  }

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
            ? "Your payment is confirmed. Welcome to Mobi Estimates — your portal is ready."
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
