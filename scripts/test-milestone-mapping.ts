import {
  CUSTOMER_MILESTONES,
  CUSTOMER_MILESTONE_COUNT,
  customerProgressForStatus,
} from "../src/lib/milestones";
import { ALL_STATUSES } from "../src/lib/projects";

/**
 * Customer milestone mapping is fail-closed and never advertises delivery.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

test("every known project status maps to a valid in-range milestone", () => {
  for (const status of ALL_STATUSES) {
    const p = customerProgressForStatus(status);
    assert(p.index >= 0 && p.index < CUSTOMER_MILESTONE_COUNT, `${status} index out of range`);
    assert(typeof p.nextStep === "string" && p.nextStep.length > 0, `${status} missing next step`);
  }
});

test("unknown/empty status fails closed to the earliest milestone", () => {
  for (const bad of ["", "totally_new_status", undefined, null]) {
    const p = customerProgressForStatus(bad as string);
    assert(p.index === 0 && !p.isClosed, `unknown status "${bad}" must map to Submitted`);
  }
});

test("gate-locked final statuses never exceed 'Ready after approval'", () => {
  for (const status of ["delivered", "revised", "approved", "ready_for_delivery"]) {
    const p = customerProgressForStatus(status);
    assert(p.index === CUSTOMER_MILESTONE_COUNT - 1, `${status} should cap at the last milestone`);
    assert(p.label === "Ready after approval", `${status} must show "Ready after approval"`);
  }
});

test("no milestone label implies delivery/completion", () => {
  for (const m of CUSTOMER_MILESTONES) {
    const l = m.label.toLowerCase();
    assert(!l.includes("delivered"), `milestone "${m.label}" implies delivery`);
    assert(!l.includes("complete"), `milestone "${m.label}" implies completion`);
  }
});

test("closed/canceled are terminal (not progress steps)", () => {
  for (const status of ["closed", "canceled"]) {
    const p = customerProgressForStatus(status);
    assert(p.isClosed && p.closedLabel, `${status} must be terminal`);
  }
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
