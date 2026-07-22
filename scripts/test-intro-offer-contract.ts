import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  INTRO_OFFER_CLAIM_STATUSES,
  INTRO_OFFER_OCCUPYING_STATUSES,
  INTRO_OFFER_REJECTION_REASON_CLASSES,
  isIntroOfferOccupyingStatus,
  isIntroOfferRejectionReasonClass,
  introOfferRejectionPublicCopy,
} from "../src/lib/intro-offer";

/**
 * Intro-offer entitlement contract: the TS lifecycle/reason model and the
 * migration 0030 concurrency/eligibility/RLS guarantees must stay aligned and
 * fail closed.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

const MIGRATION = readFileSync(
  join(process.cwd(), "supabase/migrations/0030_intro_offer_claims.sql"),
  "utf8",
);

const ENTITLEMENT_MIGRATION = readFileSync(
  join(process.cwd(), "supabase/migrations/0034_lock_customer_project_creation.sql"),
  "utf8",
);

const QUALIFICATION_MIGRATION = readFileSync(
  join(process.cwd(), "supabase/migrations/0035_intro_offer_acceptance_job_gate.sql"),
  "utf8",
);

const ROUTE = readFileSync(
  join(process.cwd(), "src/app/api/projects/route.ts"),
  "utf8",
);

const ADMIN_ACTIONS = readFileSync(
  join(process.cwd(), "src/app/admin/projects/[id]/actions.ts"),
  "utf8",
);

const ESTIMATE_JOBS = readFileSync(
  join(process.cwd(), "src/lib/estimate-jobs.ts"),
  "utf8",
);

test("projects API enforces the one-per-company boundary with NO fail-open (billing config independent)", () => {
  // The old fail-open branch (allow a repeat submission when billing is not
  // enforced and the free claim is used) must be gone.
  assert(!ROUTE.includes("billingEnforced"), "route must not gate the free-offer boundary on billingEnforced()");
  // The free path must provision atomically via the RPC, not insert-then-attach.
  assert(ROUTE.includes("create_free_offer_project"), "free path must use the atomic create_free_offer_project RPC");
  assert(!ROUTE.includes("attach_intro_offer_claim"), "free path must not use the insert-then-attach flow");
  // Failed free provisioning must atomically release the claim, cancel and
  // soft-delete the incomplete project, and verify the RPC response.
  assert(
    ROUTE.includes("fail_free_offer_project_provisioning"),
    "free-path rollback must use the atomic failed-provisioning RPC",
  );
  assert(ROUTE.includes("result?.ok === true"), "free-path rollback must verify the atomic RPC result");
  assert(
    MIGRATION.includes("revoke all on function public.release_intro_offer_claim(uuid, uuid) from authenticated"),
    "legacy non-atomic release RPC must not remain executable by authenticated users",
  );
  assert(
    !MIGRATION.includes("grant execute on function public.release_intro_offer_claim(uuid, uuid) to authenticated"),
    "legacy release RPC must not be granted back to authenticated users",
  );
});

test("customer project creation is RPC-only and every paid path is entitlement-atomic", () => {
  assert(
    ENTITLEMENT_MIGRATION.includes("drop policy if exists projects_insert on public.projects"),
    "latest migration must remove the legacy customer-member project insert policy",
  );
  assert(
    /create policy projects_insert_staff[\s\S]*for insert with check \([\s\S]*public\.is_staff\(\)/.test(
      ENTITLEMENT_MIGRATION,
    ),
    "direct project inserts must be staff-only",
  );
  assert(
    /create or replace function public\.create_entitled_project[\s\S]*security definer[\s\S]*set search_path = public/.test(
      ENTITLEMENT_MIGRATION,
    ),
    "paid project creation must use a pinned SECURITY DEFINER RPC",
  );
  assert(
    ENTITLEMENT_MIGRATION.includes("not public.is_member_of(p_company)"),
    "entitlement RPC must enforce tenant membership",
  );
  assert(
    /from public\.companies[\s\S]*for update/.test(ENTITLEMENT_MIGRATION),
    "entitlement decisions must serialize on the company row",
  );
  assert(
    /from public\.subscriptions[\s\S]*status = 'active'/.test(ENTITLEMENT_MIGRATION),
    "RPC must validate an active subscription",
  );
  assert(
    /from public\.pay_per_project_orders[\s\S]*consumed_project_id is null[\s\S]*for update/.test(
      ENTITLEMENT_MIGRATION,
    ),
    "RPC must lock exactly one unused paid project credit",
  );
  assert(
    ENTITLEMENT_MIGRATION.includes("insert into public.projects") &&
      ENTITLEMENT_MIGRATION.includes("set consumed_project_id = v_project"),
    "project insertion and paid-credit consumption must occur in one RPC transaction",
  );
  assert(ROUTE.includes('supabase.rpc("create_entitled_project"'), "API paid path must call the entitlement RPC");
  assert(!ROUTE.includes('.from("projects")\n      .insert('), "API must not directly insert customer projects");
  assert(!ROUTE.includes('supabase.rpc("consume_ppp_credit"'), "API must not separately consume paid credit");
});

test("free requests cannot enter estimating until staff accepts qualification", () => {
  assert(
    /if \(!needsFreeClaim\) \{[\s\S]*ensureEstimateJobForProject\(admin, projectId\)/.test(ROUTE),
    "project submission must provision an EstimateJob only for paid/subscription projects",
  );
  assert(
    ROUTE.includes("pendingReview: needsFreeClaim"),
    "free submission response must expose the pending-review state",
  );

  const acceptAt = QUALIFICATION_MIGRATION.indexOf("set status = 'accepted'");
  const jobAt = QUALIFICATION_MIGRATION.indexOf("insert into public.estimate_jobs", acceptAt);
  assert(acceptAt > -1 && jobAt > acceptAt, "acceptance must update the claim before creating the EstimateJob");
  assert(
    /create or replace function public\.decide_intro_offer_claim[\s\S]*security definer[\s\S]*set search_path = public/.test(
      QUALIFICATION_MIGRATION,
    ),
    "atomic qualification RPC must be SECURITY DEFINER with a pinned search_path",
  );
  assert(
    QUALIFICATION_MIGRATION.includes("if v_claim.status in ('accepted', 'consumed')"),
    "acceptance must be idempotent",
  );

  const rejectAt = QUALIFICATION_MIGRATION.indexOf("set status = 'rejected'");
  const cancelAt = QUALIFICATION_MIGRATION.indexOf("set status = 'canceled', deleted_at = now()", rejectAt);
  const historyAt = QUALIFICATION_MIGRATION.indexOf("insert into public.project_status_history", cancelAt);
  assert(
    rejectAt > -1 && cancelAt > rejectAt && historyAt > cancelAt,
    "rejection must atomically reject, cancel/soft-delete, then append audit history",
  );
  assert(QUALIFICATION_MIGRATION.includes("already_rejected"), "rejection must be idempotent");
  assert(
    !/delete\s+from\s+public\.projects/i.test(QUALIFICATION_MIGRATION),
    "qualification decisions must never hard-delete a project",
  );

  assert(
    /before insert or update of status on public\.estimate_jobs/.test(QUALIFICATION_MIGRATION),
    "database trigger must guard EstimateJob creation and status advancement",
  );
  assert(
    QUALIFICATION_MIGRATION.includes("not in ('accepted', 'consumed')") &&
      QUALIFICATION_MIGRATION.includes("intro_offer_not_accepted"),
    "trigger must fail closed for requested/rejected/released claims",
  );
  assert(
    ADMIN_ACTIONS.includes('redirectWithEstimateJobNotice(projectId, "intro_offer_pending_acceptance")'),
    "staff repair/regeneration actions must surface the qualification gate safely",
  );
  assert(
    ESTIMATE_JOBS.includes("isIntroOfferNotAcceptedError") &&
      ESTIMATE_JOBS.includes("intro_offer_pending_acceptance"),
    "EstimateJob helpers must classify and explain the database qualification guard",
  );
});

test("occupying statuses are exactly requested/accepted/consumed", () => {
  assert(
    JSON.stringify([...INTRO_OFFER_OCCUPYING_STATUSES]) ===
      JSON.stringify(["requested", "accepted", "consumed"]),
    "occupying statuses drifted",
  );
  assert(isIntroOfferOccupyingStatus("requested"), "requested must occupy the slot");
  assert(!isIntroOfferOccupyingStatus("rejected"), "rejected must NOT occupy the slot (retry allowed)");
  assert(!isIntroOfferOccupyingStatus("released"), "released must NOT occupy the slot (retry allowed)");
});

test("all claim statuses appear in the DB check constraint", () => {
  for (const status of INTRO_OFFER_CLAIM_STATUSES) {
    assert(MIGRATION.includes(`'${status}'`), `migration missing status '${status}'`);
  }
});

test("rejection reason classes match between TS and the DB constraint", () => {
  for (const rc of INTRO_OFFER_REJECTION_REASON_CLASSES) {
    assert(isIntroOfferRejectionReasonClass(rc), `TS guard rejects known class ${rc}`);
    assert(MIGRATION.includes(`'${rc}'`), `migration missing reason class '${rc}'`);
    assert(introOfferRejectionPublicCopy(rc).length > 0, `${rc} has no public copy`);
  }
  // Unknown class falls back to safe generic copy (never throws / leaks).
  assert(
    introOfferRejectionPublicCopy("__nope__") === introOfferRejectionPublicCopy("other"),
    "unknown reason class must fall back to generic public copy",
  );
});

test("partial unique index enforces one occupying claim per company", () => {
  assert(
    /create unique index[^;]*uniq_intro_offer_active_per_company[^;]*where status in \('requested', 'accepted', 'consumed'\)/is.test(
      MIGRATION,
    ),
    "partial unique index over occupying statuses is missing/incorrect",
  );
});

test("write RPCs are security-definer with a pinned search_path", () => {
  for (const fn of [
    "attach_intro_offer_claim",
    "release_intro_offer_claim",
    "decide_intro_offer_claim",
  ]) {
    const re = new RegExp(
      `create or replace function public\\.${fn}[\\s\\S]*?security definer[\\s\\S]*?set search_path = public`,
      "i",
    );
    assert(re.test(MIGRATION), `${fn} is not security definer with a pinned search_path`);
  }
});

test("attach is concurrency-safe and fails closed on auth", () => {
  assert(MIGRATION.includes("unique_violation"), "attach must translate unique_violation to already_claimed");
  assert(MIGRATION.includes("already_claimed"), "attach must return already_claimed");
  assert(
    MIGRATION.includes("not authorized to claim the intro offer for this company"),
    "attach must fail closed on non-membership",
  );
});

test("claims are audit-preserving (no hard delete)", () => {
  assert(!/delete\s+from\s+public\.intro_offer_claims/i.test(MIGRATION), "claims must never be hard-deleted");
  assert(MIGRATION.includes("'released'"), "rollback must release (not delete) a claim");
});

test("eligibility means a genuinely UNUSED acquisition offer (old/paid companies excluded)", () => {
  const fn = MIGRATION.slice(
    MIGRATION.indexOf("create or replace function public.intro_offer_company_eligible"),
    MIGRATION.indexOf("revoke all on function public.intro_offer_company_eligible"),
  );
  assert(fn.length > 0, "intro_offer_company_eligible definition not found");
  // Occupying claim disqualifies.
  assert(
    /status in \('requested', 'accepted', 'consumed'\)/.test(fn),
    "eligibility must reject a company holding an occupying claim",
  );
  // Prior paid subscription history disqualifies (not just the never-active 'pending').
  assert(
    /from public\.subscriptions[\s\S]*status in \('active', 'past_due', 'canceled', 'suspended'\)/.test(fn),
    "eligibility must reject companies with prior paid subscription history",
  );
  // Prior paid pay-per-project order disqualifies.
  assert(
    /from public\.pay_per_project_orders[\s\S]*status = 'paid'/.test(fn),
    "eligibility must reject companies with a paid pay-per-project order",
  );
});

test("prior NON-intro projects disqualify, but rejected/released-only projects allow a retry", () => {
  const fn = MIGRATION.slice(
    MIGRATION.indexOf("create or replace function public.intro_offer_company_eligible"),
    MIGRATION.indexOf("revoke all on function public.intro_offer_company_eligible"),
  );
  // A project counts against eligibility only when NOT linked to any intro claim.
  // A project tied to a rejected/released claim is still an intro project (linked),
  // so it does NOT disqualify a retry — exactly the "not exists (claim for p.id)" test.
  assert(
    /from public\.projects p[\s\S]*not exists[\s\S]*from public\.intro_offer_claims c[\s\S]*c\.project_id = p\.id/.test(
      fn,
    ),
    "eligibility must exclude prior non-intro projects while allowing rejected/released retries",
  );
});

test("reservation re-checks eligibility server-side (stale preflight cannot bypass)", () => {
  const attach = MIGRATION.slice(
    MIGRATION.indexOf("create or replace function public.attach_intro_offer_claim"),
    MIGRATION.indexOf("create or replace function public.release_intro_offer_claim"),
  );
  assert(
    /intro_offer_company_eligible\(p_company/.test(attach),
    "attach_intro_offer_claim must re-check eligibility server-side",
  );
  const create = MIGRATION.slice(
    MIGRATION.indexOf("create or replace function public.create_free_offer_project"),
  );
  assert(
    /intro_offer_company_eligible\(p_company/.test(create),
    "create_free_offer_project must re-check eligibility server-side",
  );
});

test("create_free_offer_project is transaction-safe: claim-first, no hard delete, tenant + concurrency guards", () => {
  const create = MIGRATION.slice(
    MIGRATION.indexOf("create or replace function public.create_free_offer_project"),
  );
  assert(create.length > 0, "create_free_offer_project definition not found");
  assert(/security definer[\s\S]*set search_path = public/.test(create), "must be security definer + pinned search_path");
  // Tenant check: only a member/staff of the company may provision.
  assert(
    create.includes("not authorized to create a free-offer project for this company"),
    "create must fail closed on non-membership (tenant check)",
  );
  // Claim-first: the occupying claim is inserted BEFORE the project, so a concurrent
  // loser trips the unique index and NO project is ever created for it.
  const claimAt = create.indexOf("insert into public.intro_offer_claims");
  const projectAt = create.indexOf("insert into public.projects");
  assert(claimAt > -1 && projectAt > -1 && claimAt < projectAt, "claim must be inserted before the project (claim-first)");
  // No second free project under concurrency: unique_violation -> already_claimed.
  assert(create.includes("unique_violation"), "create must translate a concurrent conflict to already_claimed");
  assert(create.includes("already_claimed"), "create must return already_claimed on the concurrency loser");
  // No new hard-delete path: the free flow never deletes a project.
  assert(!/delete\s+from\s+public\.projects/i.test(create), "create must not introduce a project hard-delete path");
});

test("failed provisioning cleanup is atomic, idempotent, soft-deleted, and audited", () => {
  const cleanup = MIGRATION.slice(
    MIGRATION.indexOf("create or replace function public.fail_free_offer_project_provisioning"),
    MIGRATION.indexOf("create or replace function public.decide_intro_offer_claim"),
  );
  assert(cleanup.length > 0, "failed-provisioning cleanup RPC definition not found");
  assert(cleanup.includes("status = 'released'"), "cleanup must release the occupying claim");
  assert(
    cleanup.includes("status = 'canceled', deleted_at = now()"),
    "cleanup must cancel and soft-delete the incomplete project",
  );
  assert(
    cleanup.includes("insert into public.project_status_history"),
    "cleanup must retain an audit timeline event",
  );
  assert(cleanup.includes("already_released"), "cleanup must be idempotent after successful completion");
  assert(!/delete\s+from\s+public\.projects/i.test(cleanup), "cleanup must never hard-delete the free project");
});

test("migration trigger and policy definitions are rerun-safe", () => {
  assert(
    MIGRATION.includes("drop trigger if exists trg_intro_offer_claims_updated"),
    "updated-at trigger must be dropped before recreation",
  );
  assert(
    MIGRATION.includes("drop policy if exists intro_offer_claims_select_staff"),
    "staff-select policy must be dropped before recreation",
  );
});

test("base table is RLS default-deny for customers; client reads omit internal_note", () => {
  assert(MIGRATION.includes("enable row level security"), "RLS must be enabled");
  assert(MIGRATION.includes("intro_offer_claims_select_staff"), "only staff may select the base table");
  // The client-safe status RPC must not select internal_note. Anchor to the
  // function DEFINITION (not an earlier doc-comment mention of its name).
  const statusFn = MIGRATION.slice(
    MIGRATION.indexOf("create or replace function public.intro_offer_status_for_project"),
  );
  assert(statusFn.length > 0, "status RPC definition not found");
  assert(!statusFn.includes("internal_note"), "client-safe status RPC must not expose internal_note");
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
