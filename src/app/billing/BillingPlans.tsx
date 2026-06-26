"use client";

import { useState } from "react";

export interface PlanCard {
  code: string;
  name: string;
  description: string | null;
  priceCents: number | null;
  currency: string;
  activeCapacity: number | null;
  maxActiveProjects: number | null;
  turnaroundNote: string | null;
  available: boolean;
}

function price(cents: number | null, currency: string) {
  if (cents == null) return "Custom";
  const amount = (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 0,
  });
  return amount;
}

export function BillingPlans({
  plans,
  currentStatus,
  paymentsLive,
}: {
  plans: PlanCard[];
  currentStatus: string | null;
  paymentsLive: boolean;
}) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start(planCode: string) {
    setError(null);
    setLoading(planCode);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ planCode }),
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

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto w-full max-w-5xl">
        <div className="text-center">
          <span className="inline-block text-2xl font-extrabold tracking-tight text-navy">
            MOBI <span className="font-semibold text-brand">Estimates</span>
          </span>
          <h1 className="mt-4 text-2xl font-bold text-navy">Choose your plan</h1>
          <p className="mx-auto mt-1 max-w-xl text-slate-500">
            Pick a monthly capacity plan to unlock your portal and start submitting
            projects. Cancel anytime.
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

        {/* Monthly estimating subscriptions — placed above the project-based
            section. All three plans sit side by side in a single row on tablet
            and desktop; on small screens the row scrolls horizontally (snap)
            instead of stacking vertically. */}
        <section aria-labelledby="monthly-plans-heading" className="mt-10">
          <h2 id="monthly-plans-heading" className="text-xl font-bold text-navy">
            Monthly estimating subscriptions
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Ongoing capacity plans for teams that estimate every month.
          </p>

          <div className="mt-6 flex snap-x snap-mandatory gap-6 overflow-x-auto px-1 pb-2 pt-3 md:overflow-x-visible md:pb-0 md:pt-3">
            {plans.map((plan) => {
              const popular = plan.code === "growth";
              return (
                <div
                  key={plan.code}
                  className={
                    "relative flex w-[82%] shrink-0 snap-center flex-col rounded-2xl border bg-white p-6 shadow-sm sm:w-[330px] md:w-auto md:flex-1 " +
                    (popular ? "border-brand ring-2 ring-brand/30" : "border-slate-200")
                  }
                >
                  {popular && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand px-3 py-1 text-xs font-bold uppercase tracking-wide text-white">
                      Most Popular
                    </span>
                  )}
                  <h3 className="text-lg font-bold text-navy">{plan.name}</h3>
                  <div className="mt-2">
                    <span className="text-3xl font-extrabold text-navy">
                      {price(plan.priceCents, plan.currency)}
                    </span>
                    <span className="text-slate-500">/mo</span>
                  </div>
                  {plan.description && (
                    <p className="mt-2 text-sm text-slate-500">{plan.description}</p>
                  )}
                  <ul className="mt-4 space-y-2 text-sm text-slate-600">
                    {plan.activeCapacity != null && (
                      <li>✓ Up to {plan.activeCapacity} estimates per month</li>
                    )}
                    {plan.maxActiveProjects != null && (
                      <li>
                        ✓ {plan.maxActiveProjects} active project
                        {plan.maxActiveProjects === 1 ? "" : "s"} at a time
                      </li>
                    )}
                    {plan.turnaroundNote && <li>✓ {plan.turnaroundNote}</li>}
                    <li>✓ Cancel anytime</li>
                  </ul>
                  <button
                    onClick={() => start(plan.code)}
                    disabled={!plan.available || loading !== null}
                    className={
                      "mt-6 w-full rounded-full px-5 py-3 font-semibold transition disabled:opacity-60 " +
                      (popular
                        ? "bg-brand text-white hover:bg-brand-dark"
                        : "border border-slate-300 text-navy hover:border-brand hover:text-brand")
                    }
                  >
                    {loading === plan.code ? "Starting…" : "Get Started"}
                  </button>
                </div>
              );
            })}
          </div>
        </section>

        {/* Project-based estimating (pay per project) — same side-by-side
            layout as the monthly section: cards share a single horizontal row
            on tablet/desktop and scroll horizontally on small screens. */}
        <section aria-labelledby="per-project-heading" className="mt-12">
          <h2 id="per-project-heading" className="text-xl font-bold text-navy">
            Project-based estimating
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Pay per project — no monthly commitment.
          </p>

          <div className="mt-6 flex snap-x snap-mandatory gap-6 overflow-x-auto px-1 pb-2 md:overflow-x-visible md:pb-0">
            <div className="flex w-[82%] shrink-0 snap-center flex-col rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center sm:w-[330px] md:w-auto md:flex-1">
              <h3 className="text-base font-bold text-navy">Single Project Estimate</h3>
              <p className="mt-1 text-sm text-slate-500">
                One-time professional estimate, starting at $500. No monthly commitment.
              </p>
              {/* TODO: point this at the confirmed quote destination (support email or
                  quote form) once provided — see OWNER_DECISIONS.md §7. */}
              <a
                href="#single-project"
                className="mt-4 inline-block self-center rounded-full border border-slate-300 px-5 py-2.5 text-sm font-semibold text-navy hover:border-brand hover:text-brand"
              >
                Get a Project Quote
              </a>
              <p id="single-project" className="mt-3 text-xs text-slate-400">
                Quote requests open soon — your Mobi contact will send a fixed scope and price.
              </p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
