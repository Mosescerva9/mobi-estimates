/**
 * Customer-facing progress milestones.
 *
 * A pure, fail-closed mapping from the internal `project_status` enum to honest
 * customer milestones. It intentionally NEVER exposes a "delivered/complete"
 * milestone: final delivery stays behind the existing final-delivery approval
 * gate (see src/lib/estimate-jobs.ts). Every known status maps to at most
 * "Ready after approval", and any unknown status falls back to the earliest
 * milestone ("Submitted") rather than implying more progress than is real.
 *
 * No server imports here — safe for both client and server, and unit-testable.
 */

export const CUSTOMER_MILESTONES = [
  { key: "submitted", label: "Submitted" },
  { key: "qualification", label: "Qualification & document review" },
  { key: "scope", label: "Scope & takeoff" },
  { key: "pricing", label: "Pricing & QA" },
  { key: "ready", label: "Ready after approval" },
] as const;

export type CustomerMilestoneKey = (typeof CUSTOMER_MILESTONES)[number]["key"];
export const CUSTOMER_MILESTONE_COUNT = CUSTOMER_MILESTONES.length;

/** Terminal statuses that are not a progress step. */
const CLOSED_STATUSES: Record<string, string> = {
  closed: "Closed",
  canceled: "Canceled",
};

/**
 * Internal project_status -> milestone index. Kept explicit (not a range) so an
 * unknown/new status is caught by the fail-closed default rather than silently
 * mapping to whatever bucket a range happens to cover. Delivered/revised/approved
 * are capped at "Ready after approval" and never advertised as delivered.
 */
const STATUS_TO_MILESTONE_INDEX: Record<string, number> = {
  draft: 0,
  submitted: 0,
  needs_information: 0,
  under_internal_review: 1,
  accepted: 1,
  scheduled: 1,
  document_review: 1,
  takeoff_in_progress: 2,
  pricing_in_progress: 3,
  clarification_required: 3,
  qa_review: 3,
  revision_requested: 3,
  ready_for_delivery: 4,
  // Gate-locked final statuses: shown only as "Ready after approval" — never as
  // delivered/complete. Delivery stays behind the final-delivery approval gate.
  delivered: 4,
  revised: 4,
  approved: 4,
};

const NEXT_STEP_BY_INDEX: string[] = [
  "We've received your project and will confirm scope and next steps.",
  "Our team is reviewing your documents and confirming supported scope.",
  "We're measuring quantities and building the takeoff.",
  "We're pricing the work and running quality checks.",
  "Your estimate is in final internal review. It is released only after our human approval gates are met.",
];

export interface CustomerProgress {
  /** 0-based index of the current milestone (0..CUSTOMER_MILESTONE_COUNT-1). */
  index: number;
  /** The current milestone label. */
  label: string;
  /** Honest next-step / current-state explanation. */
  nextStep: string;
  /** True for closed/canceled projects (no active progress). */
  isClosed: boolean;
  /** Terminal label when isClosed (e.g. "Closed", "Canceled"); else null. */
  closedLabel: string | null;
}

/**
 * Map an internal project status to customer-facing progress. Fail-closed:
 * unknown statuses resolve to the earliest milestone ("Submitted").
 */
export function customerProgressForStatus(status: string | null | undefined): CustomerProgress {
  const key = (status ?? "").toString();

  if (Object.prototype.hasOwnProperty.call(CLOSED_STATUSES, key)) {
    return {
      index: 0,
      label: CUSTOMER_MILESTONES[0].label,
      nextStep: "This project is closed. Contact us if you need to reopen or resubmit it.",
      isClosed: true,
      closedLabel: CLOSED_STATUSES[key],
    };
  }

  const index = Object.prototype.hasOwnProperty.call(STATUS_TO_MILESTONE_INDEX, key)
    ? STATUS_TO_MILESTONE_INDEX[key]
    : 0; // fail closed to "Submitted"

  return {
    index,
    label: CUSTOMER_MILESTONES[index].label,
    nextStep: NEXT_STEP_BY_INDEX[index] ?? NEXT_STEP_BY_INDEX[0],
    isClosed: false,
    closedLabel: null,
  };
}
