const OWNER_REVIEW_READY_BADGE_CLASS = "bg-blue-50 text-blue-700";
const OWNER_REVIEW_BLOCKED_BADGE_CLASS = "bg-amber-100 text-amber-700";
const LATEST_READINESS_READY_BADGE_CLASS = "bg-blue-50 text-blue-700";
const LATEST_READINESS_BLOCKED_BADGE_CLASS = "bg-amber-50 text-amber-700";

/**
 * Owner-review readiness is an internal workflow state, not final estimate
 * delivery approval. Keep this styling away from green/success colors so the
 * admin UI cannot imply customer-ready/final-delivered status while the P0
 * final-delivery gate remains locked.
 */
export function ownerReviewReadinessBadgeClass(readyForOwnerReview: boolean): string {
  return readyForOwnerReview ? OWNER_REVIEW_READY_BADGE_CLASS : OWNER_REVIEW_BLOCKED_BADGE_CLASS;
}

/**
 * Latest readiness mirrors the owner-review package posture: ready means ready
 * for internal owner review only, never customer/final delivery.
 */
export function latestReadinessBadgeClass(readyForOwnerReview: boolean): string {
  return readyForOwnerReview ? LATEST_READINESS_READY_BADGE_CLASS : LATEST_READINESS_BLOCKED_BADGE_CLASS;
}
