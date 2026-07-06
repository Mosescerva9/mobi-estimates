import {
  ADMIN_CLARIFICATION_VISIBLE_LIMIT,
  adminClarificationWorkflowIsDisplayOnly,
  summarizeAdminClarificationWorkflow,
  visibleAdminClarificationCandidates,
  type AdminClarificationPackage,
} from "../src/lib/admin-clarification-package";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function candidate(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `candidate-${index}`,
    source_entry_kind: "open_question",
    source_entry_code: index % 2 === 0 ? "missing_quantity" : "missing_extraction_provenance",
    severity: index === 0 ? "critical" : "major",
    trade_code: index % 2 === 0 ? "electrical" : "plumbing",
    scope_item_id: `scope-${index}`,
    source: "assumptions_register",
    internal_reason: `Internal blocker ${index}: raw estimating evidence is incomplete.`,
    customer_safe_question: `Please confirm the ${index % 2 === 0 ? "measurement" : "plan sheet"} for this scope item.`,
    required_response_type: index % 2 === 0 ? "measurement" : "source_reference",
    blocks_delivery: index < 4,
    customer_visible_candidate: true,
    human_approval_required: true,
    ...overrides,
  };
}

const packageFixture: AdminClarificationPackage = {
  package_type: "internal_clarification_package_v1",
  customer_delivery_ready: false,
  customer_message_ready: false,
  send_ready: false,
  send_gate: "Clarification candidates require human approval and a separate messaging workflow before any external communication.",
  summary: {
    candidate_count: 7,
    blocking_candidate_count: 4,
    critical_candidate_count: 1,
    customer_safe_candidate_count: 7,
  },
  candidates: Array.from({ length: 7 }, (_, index) => candidate(index)),
};

const visibleCandidates = visibleAdminClarificationCandidates(packageFixture);
const summary = summarizeAdminClarificationWorkflow(packageFixture);

assert(ADMIN_CLARIFICATION_VISIBLE_LIMIT === 5, "admin clarification workflow should keep a small visible candidate cap");
assert(visibleCandidates.length === 5, "visible candidates must be capped to the admin limit");
assert(visibleCandidates[0].id === "candidate-0", "visible candidates must preserve original candidate order");
assert(summary.candidateCount === 7, "workflow summary must preserve candidate count");
assert(summary.blockingCandidateCount === 4, "workflow summary must preserve blocking candidate count");
assert(summary.criticalCandidateCount === 1, "workflow summary must preserve critical candidate count");
assert(summary.customerSafeCandidateCount === 7, "workflow summary must preserve customer-safe candidate count");
assert(summary.renderedCandidateCount === 5, "workflow summary must report rendered candidate count");
assert(summary.hiddenCandidateCount === 2, "workflow summary must report hidden candidate count");
assert(summary.customerDeliveryReady === false, "workflow must keep customer delivery locked");
assert(summary.customerMessageReady === false, "workflow must keep customer message readiness locked");
assert(summary.sendReady === false, "workflow must keep send readiness locked");
assert(adminClarificationWorkflowIsDisplayOnly(packageFixture), "safe fixture must be display-only");

const unsafeFixture: AdminClarificationPackage = {
  ...packageFixture,
  customer_message_ready: true,
  send_ready: true,
};
assert(!adminClarificationWorkflowIsDisplayOnly(unsafeFixture), "send/message-ready fixture must fail display-only guard");

const malformedFixture: AdminClarificationPackage = {
  customer_delivery_ready: "false" as unknown as boolean,
  customer_message_ready: "locked" as unknown as boolean,
  send_ready: 1 as unknown as boolean,
  summary: {
    candidate_count: -1,
    blocking_candidate_count: Number.NaN,
    critical_candidate_count: 2,
    customer_safe_candidate_count: 1,
  },
  candidates: undefined,
};
const malformedSummary = summarizeAdminClarificationWorkflow(malformedFixture);
assert(malformedSummary.candidateCount === 0, "negative counts must normalize to zero");
assert(malformedSummary.blockingCandidateCount === 0, "NaN counts must normalize to zero");
assert(malformedSummary.renderedCandidateCount === 0, "missing candidate arrays must render zero candidates");
assert(malformedSummary.hiddenCandidateCount === 0, "missing candidate arrays must hide zero candidates");
assert(malformedSummary.customerDeliveryReady === false, "truthy malformed customer delivery readiness must stay locked");
assert(malformedSummary.customerMessageReady === false, "truthy malformed customer message readiness must stay locked");
assert(malformedSummary.sendReady === false, "truthy malformed send readiness must stay locked");
assert(adminClarificationWorkflowIsDisplayOnly(malformedFixture), "malformed lock fields should default to display-only locked state");

console.log("admin clarification workflow harness checks passed");
