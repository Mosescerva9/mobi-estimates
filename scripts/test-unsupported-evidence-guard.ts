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
  "abstention",
  "test_only_quantity_count",
  "testonlyquantitycount",
  "contains_test_only_quantities",
  "synthetic",
  "synthetic_fixture",
]) {
  assert(migration.includes(token), `migration must inspect ${token} safety marker`);
}

assert(
  !migration.includes("coalesce(v_scope->>'supported', v_state->>'supported_scope'") &&
    !migration.includes("coalesce(nullif(v_evidence->>'test_only_quantity_count', ''), nullif(v_state->>'test_only_quantity_count'") &&
    !migration.includes("coalesce(v_evidence->>'contains_test_only_quantities', v_state->>'contains_test_only_quantities'"),
  "every unsafe marker location must be checked independently so safe nested markers cannot mask unsafe root markers",
);
assert(
  migration.includes("or lower(btrim(coalesce(v_state->>'supported_scope', ''))) in") &&
    migration.includes("or coalesce(nullif(v_state->>'test_only_quantity_count', ''), '0')::int <> 0") &&
    migration.includes("or lower(btrim(coalesce(v_state->>'contains_test_only_quantities', ''))) = 'true'"),
  "root-level compatibility markers must independently block owner-ready status",
);
assert(
  migration.includes("lower(btrim(coalesce(v_scope->>'supported_scope', ''))) in") &&
    migration.includes("lower(btrim(coalesce(v_scope->>'scope_status', ''))) in") &&
    migration.includes("lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) in"),
  "nested compatibility aliases must independently block owner-ready status",
);
assert(
  migration.includes("::int <> 0") &&
    migration.includes("like '%test%only%'") &&
    migration.includes("lower(btrim(coalesce(v_state->>'source', ''))) like '%test%only%'") &&
    migration.includes("like '%synthetic%'") &&
    migration.includes("like '%fixture%'"),
  "test-only counters and provenance markers must fail closed for negative and aliased fixture/synthetic/test-only evidence",
);

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
assert(
  !ESTIMATE_JOB_NOTICES.unsupported_scope_locked.message.toLowerCase().includes("final estimate") &&
    !ESTIMATE_JOB_NOTICES.unsupported_scope_locked.message.toLowerCase().includes("customer delivery") &&
    !ESTIMATE_JOB_NOTICES.test_only_evidence_locked.message.toLowerCase().includes("final estimate") &&
    !ESTIMATE_JOB_NOTICES.test_only_evidence_locked.message.toLowerCase().includes("customer delivery"),
  "owner-ready safety notices must not imply final-estimate or customer-delivery authority",
);
assert(
  migration.includes("owner_ready_safety_blocked") &&
    ESTIMATE_JOB_NOTICES.unsupported_scope_locked.message.includes("owner-ready"),
  "owner-ready safety blocks must be persisted and surfaced with owner-ready context",
);

assert(
  migration.includes("create or replace function public.change_estimate_job_status") &&
    migration.includes("select id, project_id, status, automation_state") &&
    migration.includes("if p_status = 'ready_for_owner_approval' then") &&
    migration.includes("v_safety_blocker := public.estimate_job_delivery_safety_blocker(v_job.automation_state)") &&
    migration.includes("'manual owner-ready status change blocked by p0 supported-scope/test-only evidence guard.'") &&
    migration.includes("'requested_status', p_status::text"),
  "manual change_estimate_job_status owner-ready transitions must enforce the safety blocker and audit blocked attempts",
);
assert(
  migration.includes("create or replace function public.prevent_unsafe_owner_ready_estimate_job_write") &&
    migration.includes("before insert or update of status, automation_state on public.estimate_jobs") &&
    migration.includes("if new.status = 'ready_for_owner_approval' then") &&
    migration.includes("public.estimate_job_delivery_safety_blocker(new.automation_state)") &&
    migration.includes("unsafe_owner_ready_status"),
  "direct DB writes to ready_for_owner_approval must be blocked by a trigger when evidence is unsafe",
);

console.log("PASS unsupported-scope/test-only evidence owner-ready guard");
