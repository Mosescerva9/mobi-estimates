import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ESTIMATE_JOB_NOTICES } from "../src/lib/estimate-jobs";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const migrationPath = "supabase/migrations/0023_block_owner_ready_for_unsupported_or_test_only_evidence.sql";
const migration = readFileSync(join(process.cwd(), migrationPath), "utf8").toLowerCase();

assert(
  migration.includes("create or replace function public.estimate_job_delivery_safety_blocker"),
  "migration must define the reusable P0 delivery-safety blocker",
);
assert(
  migration.includes("unsupported_scope_locked") && migration.includes("test_only_evidence_locked"),
  "migration must return explicit unsupported-scope and test-only evidence blocker reasons",
);
assert(
  migration.includes("unsupported scope abstention") && migration.includes("test-only evidence blocker"),
  "blocked job reasons must name unsupported-scope abstention and test-only evidence",
);
assert(
  migration.includes("status = 'blocked'") && migration.includes("owner_ready_safety_blocked"),
  "QA completion must move unsafe jobs to blocked and write an audit event",
);
assert(
  migration.indexOf("v_safety_blocker := public.estimate_job_delivery_safety_blocker") <
    migration.indexOf("status = 'ready_for_owner_approval'"),
  "delivery-safety blocker must run before ready_for_owner_approval is written",
);
assert(
  migration.includes("p_expected_updated_at is null or v_job.updated_at <> p_expected_updated_at"),
  "QA handoff must keep the stale-form freshness guard fail-closed",
);

for (const token of [
  "scope_classification",
  "supported_scope",
  "abstain",
  "test_only_quantity_count",
  "testonlyquantitycount",
  "contains_test_only_quantities",
  "synthetic_fixture",
]) {
  assert(migration.includes(token), `migration must inspect ${token} safety marker`);
}

assert(
  ESTIMATE_JOB_NOTICES.unsupported_scope_locked.tone === "error" &&
    ESTIMATE_JOB_NOTICES.unsupported_scope_locked.message.toLowerCase().includes("unsupported scope abstention"),
  "admin notice must surface unsupported-scope abstention as an error",
);
assert(
  ESTIMATE_JOB_NOTICES.test_only_evidence_locked.tone === "error" &&
    ESTIMATE_JOB_NOTICES.test_only_evidence_locked.message.toLowerCase().includes("test-only evidence"),
  "admin notice must surface test-only evidence blocking as an error",
);

console.log("PASS unsupported-scope/test-only evidence owner-ready guard");
