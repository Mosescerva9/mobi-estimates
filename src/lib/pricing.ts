/**
 * Centralized, authoritative pricing configuration for Mobi Estimates.
 *
 * This is the SINGLE source of truth for every public price, CTA label, and
 * Stripe mapping used by both the website and the checkout/server logic. Do NOT
 * hard-code prices, names, or CTAs anywhere else — import from here.
 *
 * Approved offer (do not change without business sign-off):
 *   • Three monthly subscription plans: Starter, Growth, Estimating Department.
 *   • One Pay Per Project one-time option ($599, never a subscription).
 *   • New companies may receive ONE qualifying estimate free (no card). See
 *     src/lib/intro-offer.ts for that acquisition offer's authoritative copy.
 *   • After the free qualifying estimate, the regular monthly price applies from
 *     month one — there is NO 50%-off-first-month promotion and NO free trial.
 *   • Pay Per Project is a one-time $599 charge and never recurs.
 *
 * The retired "50% off the first month" promotion has been fully removed: no
 * discounted first-month price, no Stripe coupon, and no coupon readiness gate.
 *
 * All amounts are integers in cents. Verified conversions:
 *   $599 = 59_900   $995 = 99_500   $1,995 = 199_500   $2,995 = 299_500
 */

export type BillingType = "monthly" | "one_time";

export type OfferId =
  | "starter"
  | "growth"
  | "estimating_department"
  | "pay_per_project";

export interface Offer {
  /** Internal, stable identifier. Validated server-side; never trust button text. */
  id: OfferId;
  /** Public display name. */
  name: string;
  /** One-line supporting description (no fabricated guarantees/limits). */
  tagline: string;
  billingType: BillingType;
  /** Whether Stripe should create a recurring subscription. */
  recurring: boolean;
  /** Standard price in cents (monthly rate, or the one-time price). Charged from month one. */
  regularAmountCents: number;
  /** Approved call-to-action label. */
  ctaLabel: string;
  /** Name of the env var holding this offer's Stripe Price ID (server-only). */
  stripePriceEnvVar: string;
  /** Display order, ascending. */
  order: number;
  /** Marks the visually emphasized "Most Popular" plan. */
  mostPopular: boolean;
}

export const OFFERS: Offer[] = [
  {
    id: "starter",
    name: "Starter",
    tagline: "Add estimating capacity without hiring another full-time estimator.",
    billingType: "monthly",
    recurring: true,
    regularAmountCents: 99_500, // $995/mo
    ctaLabel: "Choose This Plan",
    stripePriceEnvVar: "STRIPE_PRICE_STARTER",
    order: 1,
    mostPopular: false,
  },
  {
    id: "growth",
    name: "Growth",
    tagline: "More monthly estimating capacity so you can submit more bids.",
    billingType: "monthly",
    recurring: true,
    regularAmountCents: 199_500, // $1,995/mo
    ctaLabel: "Choose This Plan",
    stripePriceEnvVar: "STRIPE_PRICE_GROWTH",
    order: 2,
    mostPopular: true,
  },
  {
    id: "estimating_department",
    name: "Estimating Department",
    tagline: "Your outsourced estimating department for steady monthly bid volume.",
    billingType: "monthly",
    recurring: true,
    regularAmountCents: 299_500, // $2,995/mo
    ctaLabel: "Choose This Plan",
    stripePriceEnvVar: "STRIPE_PRICE_ESTIMATING_DEPARTMENT",
    order: 3,
    mostPopular: false,
  },
  {
    id: "pay_per_project",
    name: "One Project Estimate",
    tagline: "One professional construction estimate. One-time purchase — not a subscription.",
    billingType: "one_time",
    recurring: false,
    regularAmountCents: 59_900, // $599, one-time
    ctaLabel: "Order One Estimate",
    stripePriceEnvVar: "STRIPE_PRICE_PAY_PER_PROJECT",
    order: 4,
    mostPopular: false,
  },
];

const OFFERS_BY_ID = new Map<OfferId, Offer>(OFFERS.map((o) => [o.id, o]));

/** All approved offer identifiers (for server-side validation). */
export const APPROVED_OFFER_IDS = OFFERS.map((o) => o.id) as OfferId[];

export function isApprovedOfferId(value: unknown): value is OfferId {
  return typeof value === "string" && OFFERS_BY_ID.has(value as OfferId);
}

export function getOffer(id: OfferId): Offer {
  const offer = OFFERS_BY_ID.get(id);
  if (!offer) throw new Error(`Unknown offer id: ${id}`);
  return offer;
}

/** The three monthly subscription plans, in display order. */
export function monthlyOffers(): Offer[] {
  return OFFERS.filter((o) => o.billingType === "monthly").sort((a, b) => a.order - b.order);
}

/** The single Pay Per Project one-time option. */
export function payPerProjectOffer(): Offer {
  return getOffer("pay_per_project");
}

/**
 * Resolve an offer's Stripe Price ID from the environment (server-only).
 * Returns null when not yet configured so callers can fail safely.
 */
export function getStripePriceId(offer: Offer): string | null {
  return process.env[offer.stripePriceEnvVar] || null;
}

/**
 * Whether checkout is actually ready to accept payment for every currently
 * configured offer: the Stripe secret key and each offer's Stripe Price ID.
 * Customer-facing checkout buttons should be gated on this rather than on the
 * Stripe secret key alone, since a missing price env var still fails the
 * checkout request even once the secret key is present.
 *
 * The retired first-month coupon is no longer part of readiness — the regular
 * price applies from month one, so no coupon needs to be configured.
 */
export function checkoutReadiness(): boolean {
  if (!process.env.STRIPE_SECRET_KEY) return false;
  for (const offer of OFFERS) {
    if (!getStripePriceId(offer)) return false;
  }
  return true;
}

/** Format a cents amount as USD, showing cents only when not a whole dollar. */
export function formatUSD(cents: number): string {
  const hasCents = cents % 100 !== 0;
  return (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: hasCents ? 2 : 0,
    maximumFractionDigits: 2,
  });
}
