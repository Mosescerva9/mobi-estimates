import Link from "next/link";
import type { Metadata } from "next";
import { requireUser } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { createClient } from "@/lib/supabase/server";
import { statusBadgeClass, statusLabel } from "@/lib/projects";
import { ManageBillingButton } from "./ManageBillingButton";

export const metadata: Metadata = {
  title: "Subscription — Mobi Estimates",
  robots: { index: false },
};

function fmtDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function price(cents: number | null, currency: string): string {
  if (cents == null) return "Custom";
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: currency.toUpperCase(), minimumFractionDigits: 0 });
}

export default async function SubscriptionPage() {
  await requireUser();
  const companyId = await getPrimaryCompanyId();
  const supabase = await createClient();

  const { data: sub } = companyId
    ? await supabase
        .from("subscriptions")
        .select("status, current_period_end, cancel_at_period_end, stripe_customer_id, plans(name, price_cents, currency, active_capacity, turnaround_note)")
        .eq("company_id", companyId)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle()
    : { data: null };

  const subscription = sub as unknown as {
    status: string;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    stripe_customer_id: string | null;
    plans: { name: string; price_cents: number | null; currency: string; active_capacity: number | null; turnaround_note: string | null } | null;
  } | null;

  const hasPlan = !!subscription && subscription.status !== "pending";

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold text-navy">Subscription &amp; billing</h1>
      <p className="mt-1 text-slate-500">View your plan, update your payment method, or cancel.</p>

      {!hasPlan ? (
        <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <p className="text-slate-600">You don&rsquo;t have an active plan yet.</p>
          <Link href="/billing"
            className="mt-4 inline-block rounded-full bg-brand px-5 py-2.5 font-semibold text-white hover:bg-brand-dark">
            Choose a plan
          </Link>
        </div>
      ) : (
        <div className="mt-6 space-y-6">
          <section className="rounded-2xl border border-slate-200 bg-white p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-navy">{subscription!.plans?.name ?? "Plan"}</h2>
                <p className="mt-1 text-slate-500">
                  {price(subscription!.plans?.price_cents ?? null, subscription!.plans?.currency ?? "usd")}
                  <span className="text-sm">/mo</span>
                </p>
              </div>
              <span className={`inline-block rounded-full px-3 py-1 text-sm font-semibold ${statusBadgeClass(subscription!.status)}`}>
                {statusLabel(subscription!.status)}
              </span>
            </div>

            <dl className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {subscription!.cancel_at_period_end ? "Access until" : "Renews on"}
                </dt>
                <dd className="mt-0.5 text-sm text-slate-700">{fmtDate(subscription!.current_period_end)}</dd>
              </div>
              {subscription!.plans?.active_capacity != null && (
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Monthly capacity</dt>
                  <dd className="mt-0.5 text-sm text-slate-700">{subscription!.plans.active_capacity} estimates / mo</dd>
                </div>
              )}
            </dl>

            {subscription!.status === "past_due" && (
              <p className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                Your last payment didn&rsquo;t go through. Update your payment method to restore access.
              </p>
            )}
            {subscription!.cancel_at_period_end && (
              <p className="mt-4 rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Your subscription is set to cancel at the end of the current period.
              </p>
            )}

            <div className="mt-6">
              <ManageBillingButton />
              <p className="mt-2 text-xs text-slate-400">
                Opens the secure Stripe portal to update your card, view invoices, or cancel.
              </p>
            </div>
          </section>

          <p className="text-center text-sm text-slate-500">
            Need a different plan?{" "}
            <Link href="/billing" className="font-semibold text-brand hover:underline">Compare plans</Link>
          </p>
        </div>
      )}
    </div>
  );
}
