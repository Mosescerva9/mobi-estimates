import { estimateDocumentRegisterHealth, isEstimateJobNoticeCode } from "../src/lib/estimate-jobs";

/**
 * Offline guard for the document-register health helper used by the admin
 * project page and EstimateJobPanel to surface missing/stale EstimateJob
 * document registrations after a customer upload.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
function test(name: string, fn: () => void) {
  tests.push({ name, fn });
}

test("no customer files and no documents is healthy", () => {
  const result = estimateDocumentRegisterHealth([], []);
  assert(result.customerFileCount === 0, `expected 0 customer files, got ${result.customerFileCount}`);
  assert(result.registeredCount === 0, `expected 0 registered, got ${result.registeredCount}`);
  assert(result.missingCount === 0, `expected 0 missing, got ${result.missingCount}`);
});

test("all customer files registered reports zero missing", () => {
  const result = estimateDocumentRegisterHealth(["a", "b", "c"], ["a", "b", "c"]);
  assert(result.customerFileCount === 3, `expected 3 customer files, got ${result.customerFileCount}`);
  assert(result.registeredCount === 3, `expected 3 registered, got ${result.registeredCount}`);
  assert(result.missingCount === 0, `expected 0 missing, got ${result.missingCount}`);
});

test("one unregistered customer file is reported as missing", () => {
  const result = estimateDocumentRegisterHealth(["a", "b", "c"], ["a", "b"]);
  assert(result.missingCount === 1, `expected 1 missing, got ${result.missingCount}`);
});

test("null document project_file_id is ignored, not treated as a match", () => {
  const result = estimateDocumentRegisterHealth(["a", "b"], ["a", null]);
  assert(result.registeredCount === 2, `expected registeredCount to count the row, got ${result.registeredCount}`);
  assert(result.missingCount === 1, `expected file "b" to still be missing, got ${result.missingCount}`);
});

test("a stale extra document row does not mask a missing customer file", () => {
  // "old-deleted-file" is a doc row left over from a file no longer in project_files;
  // it must not be counted as covering the still-uploaded "b".
  const result = estimateDocumentRegisterHealth(["a", "b"], ["a", "old-deleted-file"]);
  assert(result.missingCount === 1, `expected "b" to be reported missing, got ${result.missingCount}`);
  assert(result.registeredCount === 2, `expected registeredCount to reflect all doc rows, got ${result.registeredCount}`);
});

test("duplicate document rows for the same file don't double-count as missing", () => {
  const result = estimateDocumentRegisterHealth(["a"], ["a", "a"]);
  assert(result.missingCount === 0, `expected 0 missing with duplicate registration, got ${result.missingCount}`);
});

test("document_register_synced is a whitelisted notice code", () => {
  assert(isEstimateJobNoticeCode("document_register_synced"), "expected document_register_synced to be whitelisted");
});

test("document_register_stale and job_not_found remain whitelisted notice codes", () => {
  assert(isEstimateJobNoticeCode("document_register_stale"), "expected document_register_stale to be whitelisted");
  assert(isEstimateJobNoticeCode("job_not_found"), "expected job_not_found to be whitelisted");
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
