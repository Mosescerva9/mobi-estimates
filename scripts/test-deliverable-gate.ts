import {
  canCustomerAcknowledgeDeliverable,
  canSetFinalDeliveryProjectStatus,
  canUploadCustomerDeliverable,
  canViewCustomerDeliverables,
  customerDeliverableGateMessage,
  estimateJobBadgeClass,
  ESTIMATE_JOB_NOTICES,
  isFinalDeliveryProjectStatus,
} from "../src/lib/estimate-jobs";
import { statusBadgeClass, statusLabel } from "../src/lib/projects";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Offline guard for the customer deliverable upload gate: staff uploads to
 * the `deliverables` bucket become customer-visible immediately, so this
 * gate must stay locked until a future explicit final-delivery approval workflow
 * records owner approval plus the audit-required evidence/review/scope gates.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
function test(name: string, fn: () => void) {
  tests.push({ name, fn });
}

test("ready_for_owner_approval still keeps the gate locked until final-delivery approval exists", () => {
  assert(canUploadCustomerDeliverable("ready_for_owner_approval") === false, "expected gate to remain locked");
});

test("null status keeps the gate locked", () => {
  assert(canUploadCustomerDeliverable(null) === false, "expected gate to be locked for null status");
});

test("undefined status keeps the gate locked", () => {
  assert(canUploadCustomerDeliverable(undefined) === false, "expected gate to be locked for undefined status");
});

test("unknown status keeps the gate locked", () => {
  assert(canUploadCustomerDeliverable("not_a_real_status") === false, "expected gate to be locked for unknown status");
});

test("qa_pending keeps the gate locked", () => {
  assert(canUploadCustomerDeliverable("qa_pending") === false, "expected gate to be locked before QA completes");
});

test("pricing_review_pending keeps the gate locked", () => {
  assert(canUploadCustomerDeliverable("pricing_review_pending") === false, "expected gate to be locked during pricing review");
});

test("closed keeps the gate locked", () => {
  assert(canUploadCustomerDeliverable("closed") === false, "expected gate to be locked once job is closed");
});

test("customer deliverable downloads stay locked until final-delivery approval workflow exists", () => {
  assert(canViewCustomerDeliverables() === false, "expected customer deliverable visibility to be locked");
});

test("customer deliverable review and approval writes stay locked", () => {
  assert(canCustomerAcknowledgeDeliverable() === false, "expected customer deliverable acknowledgements to be locked");
});

const FORBIDDEN_TERMS = ["email", "sent", "sending", "notif", "auto-deliver", "automatically deliver"];

test("locked gate message does not imply email/send/autodelivery", () => {
  const message = customerDeliverableGateMessage("qa_pending").toLowerCase();
  for (const term of FORBIDDEN_TERMS) {
    assert(!message.includes(term), `expected locked message to omit "${term}", got: ${message}`);
  }
});

test("delivery gate message names explicit P0 requirements", () => {
  const message = customerDeliverableGateMessage("ready_for_owner_approval").toLowerCase();
  for (const term of ["deliverable access is locked", "p0 final-delivery gate", "explicit owner approval", "supported scope", "complete evidence", "required reviews"]) {
    assert(message.includes(term), `expected message to include "${term}", got: ${message}`);
  }
});

test("locked gate message reflects the current status label", () => {
  const message = customerDeliverableGateMessage("qa_pending");
  assert(message.includes("QA pending"), `expected message to surface the status label, got: ${message}`);
});

test("legacy delivery project statuses do not present as final-estimate approval", () => {
  assert(statusLabel("ready_for_delivery") === "Internal delivery review", "ready_for_delivery must be an internal workflow label");
  assert(statusLabel("delivered") === "Delivery record present", "delivered must not imply final estimate approval");
  assert(!statusBadgeClass("ready_for_delivery").includes("green"), "ready_for_delivery must not get success styling");
  assert(!statusBadgeClass("delivered").includes("green"), "delivered must not get success styling");
});

test("estimate job badges do not style internal approval states as final success", () => {
  assert(!estimateJobBadgeClass("ready_for_owner_approval").includes("green"), "ready_for_owner_approval must not get success styling");
  assert(!estimateJobBadgeClass("closed").includes("green"), "closed must not imply successful final delivery");
});

test("admin delivered/revised status transitions are locked by the P0 final-delivery gate", () => {
  assert(isFinalDeliveryProjectStatus("delivered") === true, "delivered must be treated as final-delivery status");
  assert(isFinalDeliveryProjectStatus("revised") === true, "revised must be treated as final-delivery status");
  assert(isFinalDeliveryProjectStatus("ready_for_delivery") === false, "ready_for_delivery remains an internal review label");
  assert(canSetFinalDeliveryProjectStatus() === false, "final-delivery status changes must fail closed");
  assert(
    ESTIMATE_JOB_NOTICES.final_delivery_locked.message.includes("complete evidence") &&
      ESTIMATE_JOB_NOTICES.final_delivery_locked.message.includes("explicit owner approval"),
    "locked notice must name audit-required evidence and owner approval gates",
  );
});

test("admin changeStatus enforces the final-delivery status lock before updating projects", () => {
  const actions = readFileSync(join(process.cwd(), "src/app/admin/projects/[id]/actions.ts"), "utf8");
  const guardIndex = actions.indexOf("isFinalDeliveryProjectStatus(toStatus)");
  const updateIndex = actions.indexOf('.from("projects").update({ status: toStatus })');
  assert(guardIndex > 0, "changeStatus must check final-delivery project statuses");
  assert(updateIndex > 0, "changeStatus project update statement not found");
  assert(guardIndex < updateIndex, "final-delivery gate must run before the project status update");
  assert(
    actions.includes('redirectWithEstimateJobNotice(projectId, "final_delivery_locked")'),
    "blocked transition must surface the whitelisted final_delivery_locked notice",
  );
});

function roadmapLifecycleRow(roadmap: string, status: "delivered" | "revised"): string {
  const row = roadmap
    .split("\n")
    .find((line) => new RegExp(`^\\|\\s*${status}\\s*\\|`, "i").test(line));
  assert(row, `ROADMAP must contain the ${status} lifecycle row`);
  return row;
}

const FORBIDDEN_ROADMAP_DELIVERY_ROW_TERMS = [
  "✅",
  "your estimate is ready",
  "revised estimate ready",
  "estimate-ready",
  "+ link",
  "automatic customer link",
  "customer estimate-ready",
];

test("roadmap lifecycle docs keep delivered/revised rows locked behind the P0 gate", () => {
  const roadmap = readFileSync(join(process.cwd(), "ROADMAP.md"), "utf8");
  for (const status of ["delivered", "revised"] as const) {
    const row = roadmapLifecycleRow(roadmap, status);
    const normalized = row.toLowerCase();
    assert(
      row.includes("Locked by P0 final-delivery gate"),
      `${status} lifecycle row must explicitly say it is locked by the P0 final-delivery gate: ${row}`,
    );
    for (const term of FORBIDDEN_ROADMAP_DELIVERY_ROW_TERMS) {
      assert(
        !normalized.includes(term.toLowerCase()),
        `${status} lifecycle row must not include stale customer-delivery claim "${term}": ${row}`,
      );
    }
  }
  assert(
    /final-estimate delivery requires complete evidence, supported scope, required reviews, and explicit owner approval/i.test(roadmap),
    "ROADMAP must name the P0 final-delivery requirements",
  );
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      const message = e instanceof Error ? e.message : String(e);
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${message}`);
    }
  }

  console.log("");
  console.log(`${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) {
    process.exit(1);
  }
}

main();
