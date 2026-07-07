import { readFileSync } from "node:fs";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const panelPath = "src/app/admin/projects/[id]/AutomationV1Panel.tsx";
const actionsPath = "src/app/admin/projects/[id]/actions.ts";
const panel = readFileSync(panelPath, "utf8");
const actions = readFileSync(actionsPath, "utf8");

assert(panel.startsWith('"use client";'), "admin automation panel must remain an explicit client component");
assert(panel.includes("type AdminClarificationPackage as ClarificationPackage"), "admin panel must type the internal clarification package through the shared helper");
assert(panel.includes("@/lib/admin-clarification-package"), "admin panel must use the shared admin clarification helper");
assert(panel.includes("visibleAdminClarificationCandidates"), "admin panel must use the shared visible-candidate helper");
assert(panel.includes("summarizeAdminClarificationWorkflow"), "admin panel must use the shared workflow summary helper");
assert(panel.includes("adminClarificationPackageFromOwnerReview"), "admin panel must use the shared owner-review extraction helper");
assert(!panel.includes("ownerReviewPackage?.review_packet?.clarification_package"), "admin panel should not hand-roll nested owner-review clarification extraction");
assert(panel.includes("Internal clarification candidates"), "admin panel must render clarification candidate visibility");
assert(panel.includes("Customer-safe question candidate"), "admin panel must render the safe candidate question label");
assert(panel.includes("Internal reason"), "admin panel must keep the internal reason visibly separated");
assert(panel.includes("Message/send gate"), "admin panel must render message/send gate status");
assert(panel.includes('clarificationWorkflowSummary.sendReady ? "unlocked" : "locked"'), "admin panel must show send gate through the shared workflow summary");
assert(panel.includes("Human approval and a separate communication workflow"), "admin panel must require human approval before customer communication");
assert(panel.includes("external messaging stays locked"), "admin panel must state external messaging is locked");
assert(panel.includes("ADMIN_CLARIFICATION_VISIBLE_LIMIT"), "admin panel must use the shared visible candidate limit");
assert(!panel.includes("clarificationCandidates.slice(0, 5)"), "admin panel should not hard-code candidate caps inline");
assert(panel.includes("blocking_clarification_candidate_count"), "admin owner-review summary must include blocking clarification count");
assert(panel.includes("clarification_candidate_count"), "admin owner-review summary must include clarification count");

const ownerReviewSection = panel.slice(panel.indexOf("Owner-review package"), panel.indexOf("Latest readiness"));
assert(ownerReviewSection.includes("This is an internal owner-review packet only"), "owner-review clarification UI must stay under internal-only guardrail copy");
assert(ownerReviewSection.includes("It cannot approve, send, bill, publish, or deliver"), "owner-review package must keep explicit no-send/no-deliver guardrails");
assert(!ownerReviewSection.includes("window.prompt"), "clarification package visibility must not add prompt-driven mutation controls");
assert(!ownerReviewSection.includes("enginePostJson"), "clarification package visibility must not add backend mutation calls in the client panel");

assert(
  actions.includes("/owner-review/package") && !actions.includes("/clarifications/package"),
  "admin clarification visibility should reuse owner-review package data and not add a separate action yet",
);
assert(
  !/customer_message_ready\s*:\s*true|send_ready\s*:\s*true|customer_delivery_ready\s*:\s*true/.test(panel),
  "admin panel must not hard-code clarification delivery/message/send readiness to true",
);

console.log("admin clarification package checks passed");
