import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  canSetFinalDeliveryProjectStatus,
  canUploadCustomerDeliverable,
  canViewCustomerDeliverables,
  canCustomerAcknowledgeDeliverable,
  isFinalDeliveryProjectStatus,
} from "../src/lib/estimate-jobs";
import { customerProgressForStatus } from "../src/lib/milestones";

/**
 * The pre-existing final-delivery lock must remain intact — the free-offer flow
 * and the new customer surfaces cannot bypass it.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

test("final-delivery gate helpers still fail closed", () => {
  assert(canSetFinalDeliveryProjectStatus() === false, "project final-delivery status must stay locked");
  assert(canUploadCustomerDeliverable("ready_for_owner_approval") === false, "deliverable upload must stay locked");
  assert(canViewCustomerDeliverables() === false, "customer deliverable view must stay locked");
  assert(canCustomerAcknowledgeDeliverable() === false, "customer deliverable ack must stay locked");
});

test("delivered/revised/approved remain final-delivery statuses", () => {
  for (const s of ["delivered", "revised", "approved"]) {
    assert(isFinalDeliveryProjectStatus(s), `${s} must be a final-delivery status`);
  }
});

test("customer progress never surfaces a delivered/complete state", () => {
  for (const s of ["delivered", "revised", "approved"]) {
    const p = customerProgressForStatus(s);
    assert(p.label === "Ready after approval", `${s} must not display as delivered`);
  }
});

test("migration 0022 final-delivery triggers are still present", () => {
  const m = readFileSync(
    join(process.cwd(), "supabase/migrations/0022_lock_final_delivery_project_status.sql"),
    "utf8",
  );
  assert(m.includes("prevent_final_delivery_project_status"), "project-status tripwire missing");
  assert(m.includes("prevent_final_delivery_timeline_status"), "timeline-status tripwire missing");
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  console.log(`\n${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) process.exit(1);
}

main();
