"use client";

import { useState } from "react";
import {
  MonthlyPlanCard,
  PayPerProjectCard,
  PromoBanner,
  monthlyOffers,
  payPerProjectOffer,
} from "@/components/PricingCards";
import type { OfferId } from "@/lib/pricing";

/**
 * In-app plan chooser (post-onboarding paywall). Visually identical to the
 * public /pricing page — both render from the centralized config — but here the
 * user is already authenticated, so each CTA starts Stripe checkout directly.
 */
export function BillingPlans({
  currentStatus,
  paymentsLive,
}: {
  currentStatus: string | null;
  paymentsLive: boolean;
}) {
  const [loading, setLoading] = useState<OfferId | null>(null);
  const [error, setError] = useState<string | null>(null);

  const monthly = monthlyOffers();
  const ppp = payPerProjectOffer();

  async function start(plan: OfferId) {
    setError(null);
    setLoading(plan);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan }),
      });
      const data = await res.json();
      if (!res.ok || !data.url) {
        throw new Error(data.error || "Could not start checkout.");
      }
      window.location.href = data.url as string;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setLoading(null);
    }
  }

  function ctaButton(plan: OfferId, label: string, primary: boolean) {
    return (
      <button
        onClick={() => start(plan)}
        disabled={!paymentsLive || loading !== null}
        className={
          "block w-full rounded-full px-5 py-3 text-center font-semibold transition disabled:opacity-60 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30 " +
          (primary
            ? "bg-brand text-white hover:bg-brand-dark"
            : "border border-slate-300 text-navy hover:border-brand hover:text-brand")
        }
      >
        {loading === plan ? "Starting…" : label}
      </button>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto w-full max-w-5xl">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-navy">Choose the estimating plan that fits your business</h1>
          <p className="mx-auto mt-1 max-w-xl text-slate-500">
            Increase your estimating capacity without immediately hiring another
            full-time estimator. Choose a monthly plan or order one estimate.
          </p>
        </div>

        {currentStatus === "past_due" && (
          <p className="mx-auto mt-5 max-w-xl rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-center text-sm text-amber-800">
            Your last payment didn&rsquo;t go through. Choose a plan or update payment to restore access.
          </p>
        )}

        {!paymentsLive && (
          <p className="mx-auto mt-5 max-w-xl rounded-lg border border-slate-300 bg-white px-4 py-3 text-center text-sm text-slate-500">
            Checkout is being finalized. You can review plans now; the buttons go live shortly.
          </p>
        )}

        {error && (
          <p className="mx-auto mt-5 max-w-xl rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-center text-sm text-red-700">
            {error}
          </p>
        )}

        <PromoBanner />

        <section aria-label="Monthly subscription plans" className="mt-8">
          <div className="grid gap-6 md:grid-cols-3 md:items-start">
            {monthly.map((offer) => (
              <MonthlyPlanCard
                key={offer.id}
                offer={offer}
                cta={ctaButton(offer.id, offer.ctaLabel, offer.mostPopular)}
              />
            ))}
          </div>
        </section>

        <section aria-label="One-time option" className="mt-8">
          <PayPerProjectCard cta={ctaButton(ppp.id, ppp.ctaLabel, false)} />
        </section>
      </div>
    </main>
  );
}
