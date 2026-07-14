import { latestReadinessBadgeClass, ownerReviewReadinessBadgeClass } from "../src/lib/automation-readiness-style";
import {
  canApproveFinalDelivery,
  canCustomerAcknowledgeDeliverable,
  canSetFinalDeliveryProjectStatus,
  canUploadCustomerDeliverable,
  canViewCustomerDeliverables,
  customerDeliverableGateMessage,
  isAuthorizedFinalDeliveryApprover,
  estimateJobBadgeClass,
  ESTIMATE_JOB_NOTICES,
  evaluateFinalDeliveryApprovalBundle,
  FINAL_DELIVERY_REQUIRED_REVIEWS,
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

const COMPLETE_FINAL_DELIVERY_BUNDLE = {
  completeEvidence: true,
  supportedScope: true,
  requiredReviews: Object.fromEntries(FINAL_DELIVERY_REQUIRED_REVIEWS.map((review) => [review, true])),
  ownerApproved: true,
  ownerApprover: "owner:moses",
  ownerApprovedAt: "2026-07-10T00:00:00Z",
  ownerApprovalScope: "final_customer_delivery",
  approvalProjectId: "project-delivery-lock",
  projectId: "project-delivery-lock",
  unsupportedScope: false,
  testOnlyEvidence: false,
};

test("future final-delivery approval bundle only passes when every P0 prerequisite is present", () => {
  const evaluation = evaluateFinalDeliveryApprovalBundle(COMPLETE_FINAL_DELIVERY_BUNDLE);
  assert(evaluation.allowed === true, `expected complete bundle to pass, got blockers ${evaluation.blockers.join(",")}`);
  assert(canApproveFinalDelivery(COMPLETE_FINAL_DELIVERY_BUNDLE) === true, "expected complete bundle helper to pass");
});

test("final-delivery approval bundle fails closed when approval data is missing", () => {
  const evaluation = evaluateFinalDeliveryApprovalBundle(null);
  assert(evaluation.allowed === false, "missing approval bundle must block final delivery");
  assert(evaluation.blockers.includes("missing_approval_bundle"), "missing bundle blocker must be explicit");
  assert(
    evaluation.missingReviews.length === FINAL_DELIVERY_REQUIRED_REVIEWS.length,
    "missing bundle must treat all required reviews as absent",
  );
});

test("final-delivery approval bundle blocks every individual P0 prerequisite omission", () => {
  const cases = [
    { name: "incomplete evidence", patch: { completeEvidence: false }, blocker: "incomplete_evidence" },
    { name: "unsupported scope", patch: { supportedScope: false }, blocker: "unsupported_scope" },
    { name: "explicit unsupported scope marker", patch: { unsupportedScope: true }, blocker: "unsupported_scope" },
    { name: "missing unsupported-scope proof", patch: { unsupportedScope: undefined }, blocker: "unsupported_scope" },
    { name: "test-only evidence", patch: { testOnlyEvidence: true }, blocker: "test_only_evidence" },
    { name: "missing test-only evidence proof", patch: { testOnlyEvidence: undefined }, blocker: "test_only_evidence" },
    { name: "missing owner approval", patch: { ownerApproved: false }, blocker: "missing_owner_approval" },
  ] as const;

  for (const item of cases) {
    const evaluation = evaluateFinalDeliveryApprovalBundle({ ...COMPLETE_FINAL_DELIVERY_BUNDLE, ...item.patch });
    assert(evaluation.allowed === false, `${item.name} must block final delivery`);
    assert(evaluation.blockers.includes(item.blocker), `${item.name} must return ${item.blocker}`);
  }
});

test("final-delivery approval bundle requires explicit unsupported-scope and test-only-evidence denials", () => {
  const omitted = {
    completeEvidence: true,
    supportedScope: true,
    requiredReviews: COMPLETE_FINAL_DELIVERY_BUNDLE.requiredReviews,
    ownerApproved: true,
    ownerApprover: "owner:moses",
  };

  const evaluation = evaluateFinalDeliveryApprovalBundle(omitted);

  assert(evaluation.allowed === false, "omitted negative safety proofs must fail closed");
  assert(evaluation.blockers.includes("unsupported_scope"), "missing unsupported-scope proof must block");
  assert(evaluation.blockers.includes("test_only_evidence"), "missing test-only-evidence proof must block");
});

test("final-delivery approval bundle blocks staff or missing owner approver identity", () => {
  const cases = [
    { name: "missing approver", ownerApprover: undefined },
    { name: "blank approver", ownerApprover: "   " },
    { name: "staff reviewer", ownerApprover: "qa_reviewer" },
    { name: "admin role", ownerApprover: "admin" },
  ] as const;

  for (const item of cases) {
    const evaluation = evaluateFinalDeliveryApprovalBundle({
      ...COMPLETE_FINAL_DELIVERY_BUNDLE,
      ownerApprover: item.ownerApprover,
    });
    assert(evaluation.allowed === false, `${item.name} must not satisfy owner approval`);
    assert(
      evaluation.blockers.includes("unauthorized_owner_approver"),
      `${item.name} must return unauthorized owner approver blocker`,
    );
  }
});

test("final-delivery approval bundle requires an auditable owner timestamp", () => {
  const cases = [
    { name: "missing timestamp", ownerApprovedAt: undefined, blocker: "invalid_owner_approval_timestamp" },
    { name: "blank timestamp", ownerApprovedAt: "   ", blocker: "invalid_owner_approval_timestamp" },
    { name: "timezone-free timestamp", ownerApprovedAt: "2026-07-10T00:00:00", blocker: "invalid_owner_approval_timestamp" },
    { name: "invalid timestamp", ownerApprovedAt: "not-a-date", blocker: "invalid_owner_approval_timestamp" },
    { name: "future timestamp", ownerApprovedAt: "2999-01-01T00:00:00Z", blocker: "future_owner_approval_timestamp" },
  ] as const;

  for (const item of cases) {
    const evaluation = evaluateFinalDeliveryApprovalBundle({
      ...COMPLETE_FINAL_DELIVERY_BUNDLE,
      ownerApprovedAt: item.ownerApprovedAt,
    });
    assert(evaluation.allowed === false, `${item.name} must not satisfy owner approval`);
    assert(evaluation.blockers.includes(item.blocker), `${item.name} must return ${item.blocker}`);
  }
});

test("final-delivery approval bundle requires final-delivery scope and same-project binding", () => {
  const cases = [
    { name: "missing scope", patch: { ownerApprovalScope: undefined }, blocker: "invalid_owner_approval_scope" },
    { name: "wrong scope", patch: { ownerApprovalScope: "qa_review" }, blocker: "invalid_owner_approval_scope" },
    { name: "missing approval project", patch: { approvalProjectId: undefined }, blocker: "unverified_owner_approval_project" },
    { name: "missing current project", patch: { projectId: undefined }, blocker: "unverified_owner_approval_project" },
    { name: "sentinel approval project", patch: { approvalProjectId: "null" }, blocker: "unverified_owner_approval_project" },
    { name: "different project", patch: { approvalProjectId: "other-project" }, blocker: "unverified_owner_approval_project" },
  ] as const;

  for (const item of cases) {
    const evaluation = evaluateFinalDeliveryApprovalBundle({
      ...COMPLETE_FINAL_DELIVERY_BUNDLE,
      ...item.patch,
    });
    assert(evaluation.allowed === false, `${item.name} must not satisfy owner approval`);
    assert(evaluation.blockers.includes(item.blocker), `${item.name} must return ${item.blocker}`);
  }
});

test("final-delivery owner approver allowlist is explicit and normalized", () => {
  assert(isAuthorizedFinalDeliveryApprover("Moses") === true, "Moses must be accepted as owner approver");
  assert(isAuthorizedFinalDeliveryApprover(" owner:moses ") === true, "owner:moses must be normalized and accepted");
  assert(isAuthorizedFinalDeliveryApprover("staff:moses") === false, "staff-like aliases must not be accepted");
});

test("final-delivery approval bundle requires every named human review", () => {
  for (const missingReview of FINAL_DELIVERY_REQUIRED_REVIEWS) {
    const requiredReviews = { ...COMPLETE_FINAL_DELIVERY_BUNDLE.requiredReviews, [missingReview]: false };
    const evaluation = evaluateFinalDeliveryApprovalBundle({ ...COMPLETE_FINAL_DELIVERY_BUNDLE, requiredReviews });
    assert(evaluation.allowed === false, `${missingReview} omission must block final delivery`);
    assert(evaluation.blockers.includes("missing_required_review"), `${missingReview} must return missing review blocker`);
    assert(evaluation.missingReviews.includes(missingReview), `${missingReview} must be named as missing`);
  }
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
  assert(statusLabel("approved") === "Approval record present", "approved must not imply final estimate approval");
  assert(!statusBadgeClass("ready_for_delivery").includes("green"), "ready_for_delivery must not get success styling");
  assert(!statusBadgeClass("delivered").includes("green"), "delivered must not get success styling");
  assert(!statusBadgeClass("approved").includes("green"), "approved must not get success styling");
});

test("estimate job badges do not style internal approval states as final success", () => {
  assert(!estimateJobBadgeClass("ready_for_owner_approval").includes("green"), "ready_for_owner_approval must not get success styling");
  assert(!estimateJobBadgeClass("closed").includes("green"), "closed must not imply successful final delivery");
});

const INTERNAL_READY_STYLE_FORBIDDEN_TERMS = ["green", "emerald", "success"];

function assertInternalReadyClassIsNotSuccess(className: string, label: string): void {
  const normalized = className.toLowerCase();
  for (const term of INTERNAL_READY_STYLE_FORBIDDEN_TERMS) {
    assert(!normalized.includes(term), `${label} must not use ${term}/success styling: ${className}`);
  }
}

test("automation readiness badge helpers do not style internal owner-review readiness as success", () => {
  assertInternalReadyClassIsNotSuccess(ownerReviewReadinessBadgeClass(true), "owner-review ready badge");
  assertInternalReadyClassIsNotSuccess(latestReadinessBadgeClass(true), "latest readiness ready badge");
  assert(ownerReviewReadinessBadgeClass(true).includes("blue"), "owner-review ready badge should remain internal/workflow-styled");
  assert(latestReadinessBadgeClass(true).includes("blue"), "latest readiness ready badge should remain internal/workflow-styled");
});

test("automation readiness UI uses audited badge helpers for owner-review readiness", () => {
  const source = readFileSync(join(process.cwd(), "src/app/admin/projects/[id]/AutomationV1Panel.tsx"), "utf8");
  assert(
    source.includes("ownerReviewReadinessBadgeClass(Boolean(ownerReviewPackage.ready_for_owner_review))"),
    "owner-review package badge must use the tested internal-readiness style helper",
  );
  assert(
    source.includes("latestReadinessBadgeClass(Boolean(readinessPacket.ready_for_owner_review))"),
    "latest readiness badge must use the tested internal-readiness style helper",
  );
  assert(
    !/ready_for_owner_review\s*\?\s*[`"'][^`"']*(green|emerald|success)/i.test(source),
    "inline ready_for_owner_review true branches must not use green/emerald/success styling",
  );
  assert(
    !source.includes("Ready for post-delivery revision intake"),
    "legacy delivery status copy must not imply post-delivery readiness while P0 lock is closed",
  );
  assert(
    source.includes("P0 final-delivery gate remains locked"),
    "legacy delivery status copy must explicitly preserve the P0 final-delivery lock",
  );
});

test("admin delivered/revised/approved status transitions are locked by the P0 final-delivery gate", () => {
  assert(isFinalDeliveryProjectStatus("delivered") === true, "delivered must be treated as final-delivery status");
  assert(isFinalDeliveryProjectStatus("revised") === true, "revised must be treated as final-delivery status");
  assert(isFinalDeliveryProjectStatus("approved") === true, "approved must be treated as final-delivery status");
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

test("database project insert policy blocks initial delivered/revised status writes", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0022_lock_final_delivery_project_status.sql"),
    "utf8",
  ).toLowerCase();

  assert(migration.includes("drop policy if exists projects_insert"), "migration must replace the broad projects_insert policy");
  assert(migration.includes("create policy projects_insert on public.projects"), "migration must recreate projects_insert");
  assert(migration.includes("for insert with check"), "insert policy must constrain the initial row state");
  assert(
    /create policy projects_insert on public\.projects[\s\S]*?for insert with check[\s\S]*?status not in \('delivered', 'revised', 'approved'\)[\s\S]*?\);/.test(migration),
    "direct project inserts must not be able to create delivered/revised/approved rows while P0 lock is closed",
  );
});

test("database project update policy blocks direct delivered/revised status writes", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0022_lock_final_delivery_project_status.sql"),
    "utf8",
  ).toLowerCase();

  assert(migration.includes("drop policy if exists projects_update"), "migration must replace the broad projects_update policy");
  assert(migration.includes("create policy projects_update on public.projects"), "migration must recreate projects_update");
  assert(migration.includes("for update using"), "migration must constrain project updates");
  assert(migration.includes("with check"), "migration must constrain the new row state");
  assert(
    migration.includes("status not in ('delivered', 'revised', 'approved')"),
    "direct project updates must not be able to set delivered/revised/approved while P0 lock is closed",
  );
});

test("database status-history policy blocks customer-visible delivered/revised timeline writes", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0022_lock_final_delivery_project_status.sql"),
    "utf8",
  ).toLowerCase();

  assert(
    migration.includes("drop policy if exists status_history_insert_staff"),
    "migration must replace the broad status_history_insert_staff policy",
  );
  assert(
    migration.includes("create policy status_history_insert_staff on public.project_status_history"),
    "migration must recreate status-history insert policy",
  );
  assert(
    /for insert\s+with check\s*\([\s\S]*public\.is_staff\(\)[\s\S]*to_status not in \('delivered', 'revised', 'approved'\)[\s\S]*\);/.test(migration),
    "direct timeline inserts must not be able to expose delivered/revised/approved while P0 lock is closed",
  );
});

test("database triggers block privileged final-delivery status writes that bypass RLS", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0022_lock_final_delivery_project_status.sql"),
    "utf8",
  ).toLowerCase();

  for (const required of [
    "create or replace function public.prevent_final_delivery_project_status()",
    "create trigger trg_prevent_final_delivery_project_status",
    "before insert or update of status on public.projects",
    "create or replace function public.prevent_final_delivery_timeline_status()",
    "create trigger trg_prevent_final_delivery_timeline_status",
    "before insert or update of to_status on public.project_status_history",
    "complete evidence, supported scope, required reviews, and explicit owner approval",
  ]) {
    assert(migration.includes(required), `migration must include privileged-write tripwire: ${required}`);
  }

  assert(
    /if new\.status in \('delivered', 'revised', 'approved'\)[\s\S]*raise exception/.test(migration),
    "project trigger must raise before delivered/revised/approved status can be written",
  );
  assert(
    /if new\.to_status in \('delivered', 'revised', 'approved'\)[\s\S]*raise exception/.test(migration),
    "timeline trigger must raise before delivered/revised/approved status can be written",
  );
});

test("customer deliverable acknowledgement actions enforce the P0 lock before DB writes", () => {
  const actions = readFileSync(join(process.cwd(), "src/app/portal/estimates/actions.ts"), "utf8");
  const guardIndex = actions.indexOf("if (!canCustomerAcknowledgeDeliverable()) return");
  const updateIndex = actions.indexOf('.from("deliverables").update(patch)');
  assert(guardIndex > 0, "customer deliverable actions must check canCustomerAcknowledgeDeliverable");
  assert(updateIndex > 0, "customer deliverable update statement not found");
  assert(guardIndex < updateIndex, "customer acknowledgement gate must run before deliverable DB updates");
});

test("customer portal pages do not query or sign deliverables while the P0 lock is closed", () => {
  const portalFiles = [
    "src/app/portal/page.tsx",
    "src/app/portal/estimates/page.tsx",
    "src/app/portal/projects/[id]/page.tsx",
  ];

  for (const file of portalFiles) {
    const source = readFileSync(join(process.cwd(), file), "utf8");
    assert(
      source.includes("const customerDeliverablesUnlocked = canViewCustomerDeliverables();"),
      `${file} must use the shared customer deliverable lock`,
    );
    const firstDeliverablesQuery = source.indexOf('.from("deliverables")');
    assert(firstDeliverablesQuery > 0, `${file} must contain a deliverables query so the guard remains meaningful`);
    const guardBeforeQuery = source.lastIndexOf("customerDeliverablesUnlocked", firstDeliverablesQuery);
    assert(
      guardBeforeQuery >= 0 && guardBeforeQuery < firstDeliverablesQuery,
      `${file} must gate deliverable queries behind customerDeliverablesUnlocked`,
    );
    const deliverablesStorageIndex = source.indexOf(".from(DELIVERABLES_BUCKET)", firstDeliverablesQuery);
    if (deliverablesStorageIndex > 0) {
      const rowLengthGateIndex = Math.max(
        source.lastIndexOf("delRows.length > 0", deliverablesStorageIndex),
        source.lastIndexOf("rows.length > 0", deliverablesStorageIndex),
      );
      assert(
        rowLengthGateIndex >= 0,
        `${file} must only create deliverable signed URLs after the locked query produced rows`,
      );
    }
  }
});

test("database policies lock customer-visible deliverable metadata and storage", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0021_restrict_deliverables_write_to_admin.sql"),
    "utf8",
  ).toLowerCase();

  for (const policy of [
    "drop policy if exists deliverables_select",
    "drop policy if exists deliverables_update_client",
    "drop policy if exists deliverables_write_staff",
    "create policy deliverables_select_locked on public.deliverables",
    "create policy deliverables_update_locked on public.deliverables",
    "create policy deliverables_insert_locked on public.deliverables",
  ]) {
    assert(migration.includes(policy), `migration must include metadata policy guard: ${policy}`);
  }

  const lockedStoragePatterns: Array<[string, RegExp]> = [
    ["select", /create policy "deliverables_select" on storage\.objects[\s\S]*?for select to authenticated[\s\S]*?using \(bucket_id = 'deliverables' and false\);/],
    ["insert", /create policy "deliverables_insert" on storage\.objects[\s\S]*?for insert to authenticated[\s\S]*?with check \(bucket_id = 'deliverables' and false\);/],
    ["update", /create policy "deliverables_update" on storage\.objects[\s\S]*?for update to authenticated[\s\S]*?using \(bucket_id = 'deliverables' and false\)[\s\S]*?with check \(bucket_id = 'deliverables' and false\);/],
    ["delete", /create policy "deliverables_delete" on storage\.objects[\s\S]*?for delete to authenticated[\s\S]*?using \(bucket_id = 'deliverables' and false\);/],
  ];
  for (const [operation, pattern] of lockedStoragePatterns) {
    assert(pattern.test(migration), `storage ${operation} policy must fail closed for the deliverables bucket`);
  }

  assert(migration.includes("for select using (false)"), "metadata SELECT must fail closed");
  assert(migration.includes("for update using (false)"), "metadata UPDATE must fail closed");
  assert(migration.includes("for insert with check (false)"), "metadata INSERT must fail closed");
});

test("database trigger blocks privileged customer-visible deliverable writes that bypass RLS", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0021_restrict_deliverables_write_to_admin.sql"),
    "utf8",
  ).toLowerCase();

  for (const required of [
    "create or replace function public.prevent_customer_visible_deliverable_write()",
    "create trigger trg_prevent_customer_visible_deliverable_write",
    "before insert or update on public.deliverables",
    "complete evidence, supported scope, required reviews, and explicit owner approval",
  ]) {
    assert(migration.includes(required), `migration must include deliverables service-role tripwire: ${required}`);
  }

  assert(
    /raise exception 'p0 final-delivery gate locked: customer-visible deliverables require complete evidence, supported scope, required reviews, and explicit owner approval'/.test(
      migration,
    ),
    "deliverables trigger must raise before privileged insert/update can expose customer-visible artifacts",
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
