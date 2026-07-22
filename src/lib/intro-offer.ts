/**
 * Centralized, authoritative contract for the customer-acquisition intro offer.
 *
 * This is the SINGLE source of truth for the approved acquisition wording,
 * the claim lifecycle statuses, and the fixed public rejection reason classes.
 * Do NOT scatter offer copy across pages/components — import from here.
 *
 * Owner-approved offer (do not change wording without business sign-off):
 *   • One qualifying estimate free per new company.
 *   • No card required.
 *   • Supported scope and project complexity are reviewed before acceptance.
 *   • No guaranteed turnaround and no guaranteed win — Mobi helps contractors
 *     track bid progress and follow-up steps, it does not promise outcomes.
 *   • After the free qualifying estimate, regular pay-per-project or monthly
 *     pricing applies immediately (no stacked first-month discount).
 */

export const INTRO_OFFER_CODE = "first_estimate_free";

/** Primary approved call-to-action label for the acquisition funnel. */
export const INTRO_OFFER_CTA = "Book a Free Estimate";

/**
 * Approved offer copy. Wording may be refined for clarity but must always keep:
 * one qualifying estimate per new company, no card, supported scope/complexity
 * reviewed before acceptance, and no guaranteed turnaround/win.
 */
export const INTRO_OFFER = {
  code: INTRO_OFFER_CODE,
  cta: INTRO_OFFER_CTA,
  eyebrow: "First estimate free for new companies",
  headline: "Your first qualifying estimate is free",
  /** One-line summary safe for badges and hero subtext. */
  summary:
    "One qualifying estimate free per new company. No card required.",
  /** The qualifying/no-card rule, stated in full. */
  qualifyingRule:
    "One qualifying estimate is free for each new company, with no card required. Supported scope and project complexity are reviewed before acceptance.",
  /** What happens after the free estimate — no stacked discount. */
  afterOffer:
    "After your free qualifying estimate, regular pay-per-project or monthly pricing applies.",
  /** Honest positioning — track progress, never promise wins. */
  noGuarantee:
    "Mobi helps you track bid progress and follow-up steps. We don't promise a turnaround time or a guaranteed win.",
  /** Reviewed-before-acceptance disclosure line. */
  reviewNote:
    "Supported scope and project complexity are reviewed by a person before your free estimate is accepted.",
} as const;

/**
 * Claim lifecycle statuses (mirror the DB check constraint in migration 0030).
 *
 *   requested  — the company asked for its free qualifying estimate; awaiting
 *                staff review. Occupies the one-per-company slot.
 *   accepted   — staff qualified the request; the free estimate proceeds.
 *                Occupies the slot (the free offer has been used).
 *   consumed   — the free entitlement has been fully used/closed out.
 *                Occupies the slot. Reserved for future final-delivery close-out.
 *   rejected   — staff declined qualification with a fixed public reason class;
 *                frees the slot so the company may retry a supported request.
 *   released   — system auto-release when provisioning failed after reserving;
 *                frees the slot. Audit-preserving (never hard-deleted).
 */
export const INTRO_OFFER_CLAIM_STATUSES = [
  "requested",
  "accepted",
  "consumed",
  "rejected",
  "released",
] as const;
export type IntroOfferClaimStatus = (typeof INTRO_OFFER_CLAIM_STATUSES)[number];

/** Statuses that occupy the one-non-rejected-claim-per-company slot. */
export const INTRO_OFFER_OCCUPYING_STATUSES = [
  "requested",
  "accepted",
  "consumed",
] as const satisfies readonly IntroOfferClaimStatus[];

export function isIntroOfferOccupyingStatus(status: string | null | undefined): boolean {
  return (INTRO_OFFER_OCCUPYING_STATUSES as readonly string[]).includes(status ?? "");
}

/**
 * Fixed public rejection reason classes. The customer only ever sees the
 * `publicCopy`; internal notes are NEVER surfaced. Keep the keys in sync with
 * the DB check constraint in migration 0030.
 */
export const INTRO_OFFER_REJECTION_REASONS = {
  unsupported_scope: {
    publicCopy:
      "The scope in this request isn't supported for the free qualifying estimate yet.",
  },
  incomplete_documents: {
    publicCopy:
      "We need more complete plans or documents before this request can qualify.",
  },
  complexity_out_of_range: {
    publicCopy:
      "This project's complexity is outside the range covered by the free qualifying estimate.",
  },
  duplicate_request: {
    publicCopy:
      "This request looks like a duplicate of another submission from your company.",
  },
  other: {
    publicCopy:
      "This request wasn't accepted for the free qualifying estimate. Our team can follow up with next steps.",
  },
} as const satisfies Record<string, { publicCopy: string }>;

export type IntroOfferRejectionReasonClass = keyof typeof INTRO_OFFER_REJECTION_REASONS;

export const INTRO_OFFER_REJECTION_REASON_CLASSES = Object.keys(
  INTRO_OFFER_REJECTION_REASONS,
) as IntroOfferRejectionReasonClass[];

export function isIntroOfferRejectionReasonClass(
  value: string | null | undefined,
): value is IntroOfferRejectionReasonClass {
  return (
    Boolean(value) &&
    Object.prototype.hasOwnProperty.call(INTRO_OFFER_REJECTION_REASONS, value as string)
  );
}

/** Safe public rejection copy for a reason class; falls back to the generic "other" copy. */
export function introOfferRejectionPublicCopy(
  reasonClass: string | null | undefined,
): string {
  return isIntroOfferRejectionReasonClass(reasonClass)
    ? INTRO_OFFER_REJECTION_REASONS[reasonClass].publicCopy
    : INTRO_OFFER_REJECTION_REASONS.other.publicCopy;
}

/** Customer-facing status labels for the free-offer claim. */
export function introOfferClaimStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case "requested":
      return "Free estimate requested — in review";
    case "accepted":
      return "Free estimate accepted";
    case "consumed":
      return "Free estimate used";
    case "rejected":
      return "Not accepted for the free estimate";
    case "released":
      return "Free estimate request reset";
    default:
      return "Free estimate";
  }
}
