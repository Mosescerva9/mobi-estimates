import type { ReactNode } from "react";
import { type Offer, formatUSD, monthlyOffers, payPerProjectOffer } from "@/lib/pricing";
import { INTRO_OFFER } from "@/lib/intro-offer";

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
        Choose the estimating support that fits your business
      </h1>
      <p className="mx-auto mt-3 max-w-2xl text-slate-600">
        Reserve review-assisted estimating support while final customer estimate
        delivery remains gated behind complete evidence, supported scope,
        required reviews, and owner approval.
      </p>
    </header>
  );
}

/**
 * Acquisition banner: the approved intro offer (one qualifying estimate free per
 * new company, no card, reviewed before acceptance). Regular pricing applies
 * from month one after that — there is no first-month discount.
 */
export function PromoBanner() {
  return (
    <div className="mx-auto mt-8 max-w-2xl rounded-2xl border border-brand/30 bg-brand/5 px-5 py-4 text-center">
      <p className="text-base font-bold text-brand">{INTRO_OFFER.headline}</p>
      <p className="mt-1 text-sm text-slate-600">{INTRO_OFFER.qualifyingRule}</p>
      <p className="mt-1 text-sm text-slate-600">{INTRO_OFFER.afterOffer}</p>
    </div>
  );
}

/**
 * A single monthly subscription card. The CTA is injected by the caller so the
 * same markup serves the public pricing page (a link) and the in-app billing
 * page (a button that starts checkout). The regular monthly price is charged
 * from month one — there is no discounted first-month price.
 */
export function MonthlyPlanCard({ offer, cta }: { offer: Offer; cta: ReactNode }) {
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

      <p className="mt-4">
        <span className="text-3xl font-extrabold text-navy">{formatUSD(offer.regularAmountCents)}</span>{" "}
        <span className="text-slate-600">/month</span>
      </p>
      <p className="mt-1 text-sm text-slate-600">
        Billed monthly at the regular price from month one. No free trial.
      </p>
      {/* Non-visual summary so screen readers never rely on layout/color alone. */}
      <p className="sr-only">
        {offer.name}: {formatUSD(offer.regularAmountCents)} per month, billed from
        the first month. This is a monthly subscription. No free trial and no
        first-month discount.
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
            <span className="text-slate-600">one-time</span>
          </p>
          <p className="mt-2 max-w-xl text-sm text-slate-600">
            For contractors who need one review-assisted estimating request
            without a monthly subscription. It is one request, billed once — it
            does not create a monthly subscription.
          </p>
          <p className="mt-2 max-w-xl text-sm font-medium text-navy">
            Need one estimate? Get it for {formatUSD(offer.regularAmountCents)}.
            Bid consistently? Join a monthly plan and lower your cost per estimate.
          </p>
          {/* Non-visual summary so the one-time nature is never layout-dependent. */}
          <p className="sr-only">
            {offer.name}: {formatUSD(offer.regularAmountCents)} one-time payment for a
            single estimate. Not a monthly subscription. No recurring billing. No free trial.
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
    q: "Is there a free trial?",
    a: `Not a trial, but ${INTRO_OFFER.summary.charAt(0).toLowerCase()}${INTRO_OFFER.summary.slice(1)} ${INTRO_OFFER.reviewNote} After that, regular monthly or pay-per-project pricing applies.`,
  },
  {
    q: "Do new monthly subscribers get a first-month discount?",
    a: "No. The regular monthly price applies from month one. There is no 50%-off-first-month promotion.",
  },
  {
    q: "Can I purchase only one estimate?",
    a: "Yes. The Pay Per Project option is a one-time payment of $599 for one estimate. It does not create a monthly subscription.",
  },
  {
    q: "Does the free estimate mean you'll win my bid?",
    a: "No. Mobi helps you track bid progress and follow-up steps. We don't promise a turnaround time or a guaranteed win, and final estimate delivery stays behind our human review and approval gates.",
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

export { PRICING_FAQ, monthlyOffers, payPerProjectOffer };
