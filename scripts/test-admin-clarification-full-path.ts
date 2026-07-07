import {
  adminClarificationPackageFromOwnerReview,
  adminClarificationWorkflowIsDisplayOnly,
  summarizeAdminClarificationWorkflow,
  visibleAdminClarificationCandidates,
  type AdminOwnerReviewPackageWithClarifications,
} from "../src/lib/admin-clarification-package";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const ownerReviewFixture: AdminOwnerReviewPackageWithClarifications = {
  customer_delivery_ready: false,
  ready_for_owner_review: false,
  review_packet: {
    clarification_package: {
      package_type: "internal_clarification_package_v1",
      customer_delivery_ready: false,
      customer_message_ready: false,
      send_ready: false,
      send_gate: "Clarification candidates require human approval and a separate messaging workflow before any external communication.",
      summary: {
        candidate_count: 2,
        blocking_candidate_count: 2,
        critical_candidate_count: 1,
        customer_safe_candidate_count: 2,
      },
      candidates: [
        {
          id: "candidate-a",
          source_entry_kind: "open_question",
          source_entry_code: "missing_quantity",
          severity: "critical",
          trade_code: "electrical",
          scope_item_id: "scope-a",
          source: "assumptions_register",
          internal_reason: "Internal quantity blocker: missing verified feeder length.",
          customer_safe_question: "Please confirm the feeder length for the electrical scope item.",
          required_response_type: "measurement",
          blocks_delivery: true,
          customer_visible_candidate: true,
          human_approval_required: true,
        },
        {
          id: "candidate-b",
          source_entry_kind: "open_question",
          source_entry_code: "missing_extraction_provenance",
          severity: "major",
          trade_code: "plumbing",
          scope_item_id: "scope-b",
          source: "assumptions_register",
          internal_reason: "Internal source blocker: no verified plan sheet reference.",
          customer_safe_question: "Please point us to the plan sheet that shows the plumbing fixture schedule.",
          required_response_type: "source_reference",
          blocks_delivery: true,
          customer_visible_candidate: true,
          human_approval_required: true,
        },
      ],
    },
  },
};

const pkg = adminClarificationPackageFromOwnerReview(ownerReviewFixture);
assert(pkg?.package_type === "internal_clarification_package_v1", "admin helper must extract the backend owner-review embedded clarification package");

const summary = summarizeAdminClarificationWorkflow(pkg);
assert(summary.candidateCount === 2, "admin summary must preserve backend candidate count");
assert(summary.blockingCandidateCount === 2, "admin summary must preserve backend blocking candidate count");
assert(summary.criticalCandidateCount === 1, "admin summary must preserve backend critical candidate count");
assert(summary.customerSafeCandidateCount === 2, "admin summary must preserve backend customer-safe candidate count");
assert(summary.customerDeliveryReady === false, "admin summary must keep backend customer delivery locked");
assert(summary.customerMessageReady === false, "admin summary must keep backend customer message readiness locked");
assert(summary.sendReady === false, "admin summary must keep backend send readiness locked");
assert(adminClarificationWorkflowIsDisplayOnly(pkg), "full owner-review-to-admin path must stay display-only");

const visible = visibleAdminClarificationCandidates(pkg);
assert(visible.length === 2, "admin helper must render all candidates when under cap");
assert(visible.every((candidate) => candidate.customer_safe_question && candidate.internal_reason), "admin-visible candidates must preserve both customer-safe question and internal reason fields");
assert(visible.every((candidate) => candidate.human_approval_required === true), "admin-visible candidates must retain human approval requirement");

const ownerReviewWithoutPackage: AdminOwnerReviewPackageWithClarifications = {
  customer_delivery_ready: false,
  ready_for_owner_review: true,
  review_packet: {},
};
assert(adminClarificationPackageFromOwnerReview(ownerReviewWithoutPackage) === undefined, "missing embedded package should remain absent, not synthesized as sendable content");
assert(adminClarificationWorkflowIsDisplayOnly(adminClarificationPackageFromOwnerReview(ownerReviewWithoutPackage)), "missing embedded package must still be display-only locked");

const unsafeOwnerReviewFixture: AdminOwnerReviewPackageWithClarifications = {
  ...ownerReviewFixture,
  review_packet: {
    clarification_package: {
      ...ownerReviewFixture.review_packet!.clarification_package!,
      customer_delivery_ready: true,
      customer_message_ready: true,
      send_ready: true,
    },
  },
};
assert(!adminClarificationWorkflowIsDisplayOnly(adminClarificationPackageFromOwnerReview(unsafeOwnerReviewFixture)), "admin display-only guard must fail if backend ever marks embedded package sendable");

console.log("admin clarification full-path regression checks passed");
