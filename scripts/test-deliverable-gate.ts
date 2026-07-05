import { canUploadCustomerDeliverable, customerDeliverableGateMessage } from "../src/lib/estimate-jobs";

/**
 * Offline guard for the customer deliverable upload gate: staff uploads to
 * the `deliverables` bucket become customer-visible immediately, so this
 * gate must stay locked until the job is explicitly ready_for_owner_approval.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
function test(name: string, fn: () => void) {
  tests.push({ name, fn });
}

test("ready_for_owner_approval unlocks the gate", () => {
  assert(canUploadCustomerDeliverable("ready_for_owner_approval") === true, "expected gate to be unlocked");
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

const FORBIDDEN_TERMS = ["email", "sent", "sending", "notif", "auto-deliver", "automatically deliver"];

test("locked gate message does not imply email/send/autodelivery", () => {
  const message = customerDeliverableGateMessage("qa_pending").toLowerCase();
  for (const term of FORBIDDEN_TERMS) {
    assert(!message.includes(term), `expected locked message to omit "${term}", got: ${message}`);
  }
});

test("unlocked gate message does not imply email/send/autodelivery", () => {
  const message = customerDeliverableGateMessage("ready_for_owner_approval").toLowerCase();
  for (const term of FORBIDDEN_TERMS) {
    assert(!message.includes(term), `expected unlocked message to omit "${term}", got: ${message}`);
  }
});

test("locked gate message reflects the current status label", () => {
  const message = customerDeliverableGateMessage("qa_pending");
  assert(message.includes("QA pending"), `expected message to surface the status label, got: ${message}`);
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
