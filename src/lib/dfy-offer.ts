/**
 * Authoritative configuration for the Done-For-You "Estimator Business Setup"
 * product ($997 one-time).
 *
 * This offer belongs to the education/community business (YouTube -> Skool ->
 * DFY upsell) and is deliberately SEPARATE from the approved Mobi Estimates
 * offers in src/lib/pricing.ts — do not merge them. Buyers are community
 * members, not portal clients: no subscription, no company, no entitlement.
 *
 * Truth-in-marketing rules (same posture as the rest of the repo):
 *   • Education and business setup only — NO income claims, NO guarantees.
 *   • This is NOT an estimating service: no estimates are produced for the
 *     buyer's clients.
 *   • Document templates are drafts for the buyer's attorney to review.
 */

export interface DfyOffer {
  /** Stable identifier carried in Stripe metadata (plan_code / offer_code). */
  code: "dfy_setup";
  name: string;
  /** One-time price in cents: $997 = 99_700. */
  amountCents: number;
  /** Env var holding the one-time Stripe Price ID (server-only). */
  stripePriceEnvVar: string;
  ctaLabel: string;
  /** What the buyer receives — scope is fixed so delivery doesn't sprawl. */
  deliverables: string[];
  /** Explicit boundaries, shown on the sales page to prevent misunderstandings. */
  boundaries: string[];
  /** Required earnings/education disclaimer, shown near the buy button. */
  disclaimer: string;
}

export const DFY_OFFER: DfyOffer = {
  code: "dfy_setup",
  name: "Estimator Business Setup (Done-For-You)",
  amountCents: 99_700, // $997, one-time
  stripePriceEnvVar: "STRIPE_PRICE_DFY_SETUP",
  ctaLabel: "Book My Setup",
  deliverables: [
    "45-minute recorded onboarding call to plan your estimating business",
    "Niche and pricing worksheet completed together on the call",
    "Proposal template and service agreement template (drafts for your attorney to review)",
    "AI prompt library for takeoffs, scope reviews, and change orders",
    "Estimating spreadsheet and template stack",
    "Client portal and project-intake workflow configured for your business",
    "30 days of async Q&A after setup",
  ],
  boundaries: [
    "Not an estimating service — no estimates are produced for your clients.",
    "Not income or business advice — no earnings are promised or implied.",
    "Templates are starting points for your attorney to review, not legal advice.",
    "One setup per purchase; ongoing support ends 30 days after delivery.",
  ],
  disclaimer:
    "This is an educational and business-setup product. Your results depend on " +
    "your own effort, experience, and market. No income or revenue outcome is " +
    "promised or implied.",
};

/** Resolve the DFY Stripe Price ID from the environment (server-only). */
export function getDfyStripePriceId(): string | null {
  return process.env[DFY_OFFER.stripePriceEnvVar] || null;
}

/** Checkout can run only when Stripe and the one-time price are both configured. */
export function dfyCheckoutReady(): boolean {
  return !!process.env.STRIPE_SECRET_KEY && !!getDfyStripePriceId();
}
