import type { ReactNode } from "react";
import { type Offer, formatUSD, monthlyOffers, payPerProjectOffer } from "@/lib/pricing";

/** Brand wordmark used across the marketing/pricing surface. */
export function MobiWordmark() {
  return (
    <span className="inline-block text-2xl font-extrabold tracking-tight text-navy">
      MOBI <span className="font-semibold text-brand">Estimates</span>
    </span>
  );
}

/** Pricing-page header: headline + supporting copy (approved wording). */
export function PricingHeader() {
  return (
    <header className="text-center">
      <MobiWordmark />
      <h1 className="mx-auto mt-4 max-w-2xl text-balance text-3xl font-bold text-navy sm:text-4xl">
        Choose the estimating plan that fits your business
      </h1>
      <p className="mx-auto mt-3 max-w-2xl text-slate-600">
        Increase your estimating capacity without immediately hiring another
        full-time estimator. Choose a monthly plan or order one estimate for a
        one-time price.
      </p>
    </header>
  );
}

/** Promotion banner with the required clarifying line directly beneath it. */
export function PromoBanner() {
  return (
    <div className="mx-auto mt-8 max-w-2xl rounded-2xl border border-brand/30 bg-brand/5 px-5 py-4 text-center">
      <p className="text-base font-bold text-brand">
        Get 50% off your first month on any monthly plan
      </p>
      <p className="mt-1 text-sm text-slate-600">
        Regular monthly pricing begins with your second month. Pay Per Project is
        not included in this promotion.
      </p>
    </div>
  );
}

/**
 * A single monthly subscription card. The CTA is injected by the caller so the
 * same markup serves the public pricing page (a link) and the in-app billing
 * page (a button that starts checkout).
 */
export function MonthlyPlanCard({ offer, cta }: { offer: Offer; cta: ReactNode }) {
  const first = offer.firstMonthAmountCents ?? offer.regularAmountCents;
  const headingId = `plan-${offer.id}`;
  return (
    <article
      aria-labelledby={headingId}
      className={
        "relative flex flex-col rounded-2xl border bg-white p-6 shadow-sm " +
        (offer.mostPopular
          ? "border-brand ring-2 ring-brand/30 md:-mt-2 md:mb-2"
          : "border-slate-200")
      }
    >
      {offer.mostPopular && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand px-3 py-1 text-xs font-bold uppercase tracking-wide text-white">
          Most Popular
        </span>
      )}

      <h3 id={headingId} className="mt-1 text-lg font-bold text-navy">
        {offer.name}
      </h3>
      <p className="mt-1 text-sm text-slate-500">{offer.tagline}</p>

      <span className="mt-4 inline-flex w-fit items-center rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-amber-800">
        50% off your first month
      </span>

      <p className="mt-3">
        <span className="text-3xl font-extrabold text-navy">{formatUSD(first)}</span>{" "}
        <span className="text-slate-600">for your first month</span>
      </p>
      <p className="mt-1 text-sm text-slate-600">
        Then {formatUSD(offer.regularAmountCents)}/month beginning with your second month.
      </p>
      {/* Non-visual summary so screen readers never rely on layout/color alone. */}
      <p className="sr-only">
        {offer.name}: {formatUSD(first)} for the first month, then{" "}
        {formatUSD(offer.regularAmountCents)} per month beginning with the second
        month. This is a monthly subscription. No free trial.
      </p>

      <div className="mt-6">{cta}</div>
    </article>
  );
}

/** The single Pay Per Project one-time option, visually separated as ONE-TIME OPTION. */
export function PayPerProjectCard({ cta }: { cta: ReactNode }) {
  const offer = payPerProjectOffer();
  return (
    <article
      aria-labelledby="offer-pay-per-project"
      className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 sm:p-7"
    >
      <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-slate-600">
        One-time option
      </span>
      <div className="mt-3 sm:flex sm:items-end sm:justify-between sm:gap-6">
        <div>
          <h3 id="offer-pay-per-project" className="text-lg font-bold text-navy">
            {offer.name}
          </h3>
          <p className="mt-2">
            <span className="text-3xl font-extrabold text-navy">
              {formatUSD(offer.regularAmountCents)}
            </span>{" "}
            <span className="text-slate-600">per project</span>
          </p>
          <p className="mt-2 max-w-xl text-sm text-slate-600">
            One estimate, billed once. It is a one-time purchase — it does not
            create a monthly subscription, and the 50% first-month discount does
            not apply.
          </p>
        </div>
        <div className="mt-5 shrink-0 sm:mt-0">{cta}</div>
      </div>
    </article>
  );
}

/** Pricing-page FAQ (approved answers; mirrors the seeded FAQ entries). */
const PRICING_FAQ: { q: string; a: string }[] = [
  {
    q: "Do you offer a free trial?",
    a: "No. Mobi Estimates does not offer a free trial. New monthly subscribers receive 50% off their first month, and regular monthly pricing begins with the second month.",
  },
  {
    q: "Is the 50% discount recurring?",
    a: "No. The 50% discount applies only to the first month of a new monthly subscription. Regular pricing begins with the second month.",
  },
  {
    q: "Can I purchase only one estimate?",
    a: "Yes. The Pay Per Project option is a one-time payment of $199 for one estimate. It does not create a monthly subscription.",
  },
  {
    q: "Where does the Join Now button take me?",
    a: "The Join Now button takes you to the pricing page, where you can compare the available options and choose the plan that fits your business.",
  },
];

export function PricingFAQ() {
  return (
    <section aria-labelledby="pricing-faq" className="mx-auto mt-16 max-w-3xl">
      <h2 id="pricing-faq" className="text-center text-2xl font-bold text-navy">
        Frequently asked questions
      </h2>
      <dl className="mt-6 space-y-4">
        {PRICING_FAQ.map((item) => (
          <div key={item.q} className="rounded-xl border border-slate-200 bg-white p-5">
            <dt className="font-semibold text-navy">{item.q}</dt>
            <dd className="mt-1 text-sm text-slate-600">{item.a}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export { monthlyOffers, payPerProjectOffer };
