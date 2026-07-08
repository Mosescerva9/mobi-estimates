"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireStaff } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { ALL_STATUSES, PROJECT_FILES_BUCKET } from "@/lib/projects";
import {
  DOCUMENT_REVIEW_STATUSES,
  ESTIMATE_JOB_STATUSES,
  ESTIMATE_JOB_NOTICES,
  ensureEstimateJobForProject,
  isEstimateJobNoticeCode,
  type EstimateJobNoticeCode,
} from "@/lib/estimate-jobs";
import { buildIntakeReviewPacket } from "@/lib/intake-review";
import { buildPlanContextPacket } from "@/lib/plan-context";
import { engineConfigured, engineGetJson, enginePostJson, engineUploadPlan } from "@/lib/engine";

interface GuardedRpcResult {
  ok?: boolean;
  reason?: string;
}

/**
 * Redirects back to the project page with a whitelisted notice code so a
 * guarded EstimateJob RPC's `{ ok: false, reason }` (or an unreachable RPC)
 * surfaces to staff instead of failing silently behind a plain revalidate.
 * `fallback` is used for success codes (always valid) and as the safe
 * default when an RPC ever returns a `reason` outside the known set.
 */
function redirectWithEstimateJobNotice(
  projectId: string,
  reason: string | undefined,
  fallback: EstimateJobNoticeCode = "action_failed",
): never {
  const code = isEstimateJobNoticeCode(reason) ? reason : fallback;
  const params = new URLSearchParams({
    estimateJobNotice: code,
    estimateJobNoticeTone: ESTIMATE_JOB_NOTICES[code].tone,
  });
  redirect(`/admin/projects/${projectId}?${params.toString()}`);
}

/** Change a project's status and append a timeline entry (staff only). */
export async function changeStatus(formData: FormData) {
  const staff = await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const toStatus = String(formData.get("status") || "");
  const clientNote = String(formData.get("client_note") || "").trim() || null;
  const internalNote = String(formData.get("internal_note") || "").trim() || null;

  if (!projectId || !(ALL_STATUSES as readonly string[]).includes(toStatus)) {
    return; // invalid input — ignore (the UI only ever submits valid values)
  }

  const supabase = await createClient();

  const { data: current } = await supabase
    .from("projects")
    .select("status")
    .eq("id", projectId)
    .maybeSingle();

  // Update the project status (RLS: staff allowed).
  await supabase.from("projects").update({ status: toStatus }).eq("id", projectId);

  // Append a timeline entry (RLS: status_history insert is staff-only).
  await supabase.from("project_status_history").insert({
    project_id: projectId,
    from_status: current?.status ?? null,
    to_status: toStatus,
    changed_by: staff.id,
    client_note: clientNote,
    internal_note: internalNote,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
}

export interface EngineActionResult {
  ok: boolean;
  message: string;
}

/**
 * Push a project's uploaded PDF plan set into the estimating engine (staff only),
 * creating an engine-side project record and storing its id/status on the row.
 *
 * This is the plumbing between the portal and the engine. The engine currently
 * only ingests the PDF (no automated takeoff/pricing until a cost book is
 * seeded and extraction is enabled), so this does not yet produce a priced
 * estimate — it establishes the linked engine project the pipeline builds on.
 */
export async function sendToEngine(projectId: string): Promise<EngineActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: "Missing project id." };
  if (!engineConfigured()) {
    return { ok: false, message: "The estimating engine is not configured on this deployment." };
  }

  // Service role: read the project + its files and write engine sync fields
  // without depending on the caller's RLS scope.
  const admin = createAdminClient();

  const { data: project, error: projErr } = await admin
    .from("projects")
    .select("id, name, companies(legal_name)")
    .eq("id", projectId)
    .maybeSingle();
  if (projErr || !project) {
    return { ok: false, message: "Project not found." };
  }

  const { data: files } = await admin
    .from("project_files")
    .select("file_name, storage_path, created_at")
    .eq("project_id", projectId)
    .is("deleted_at", null)
    .order("created_at");

  const pdf = (files ?? []).find((f) => f.file_name?.toLowerCase().endsWith(".pdf"));
  if (!pdf) {
    return { ok: false, message: "No PDF plan file found on this project. The engine ingests PDF plan sets." };
  }

  const { data: blob, error: dlErr } = await admin.storage
    .from(PROJECT_FILES_BUCKET)
    .download(pdf.storage_path);
  if (dlErr || !blob) {
    return { ok: false, message: `Could not read the plan file from storage: ${dlErr?.message ?? "unknown error"}.` };
  }

  const company = project.companies as unknown as { legal_name: string | null } | null;

  let result;
  try {
    result = await engineUploadPlan({
      projectName: project.name,
      contractorName: company?.legal_name ?? null,
      file: blob,
      fileName: pdf.file_name,
    });
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Engine upload failed." };
  }

  const { error: updErr } = await admin
    .from("projects")
    .update({
      engine_project_id: result.project_id,
      engine_status: result.status,
      engine_page_count: result.page_count,
      engine_synced_at: new Date().toISOString(),
    })
    .eq("id", projectId);
  if (updErr) {
    return {
      ok: false,
      message: `Uploaded to the engine (${result.project_id}) but could not save the link: ${updErr.message}.`,
    };
  }

  revalidatePath(`/admin/projects/${projectId}`);
  return {
    ok: true,
    message: `Sent to the engine — ${result.page_count} page(s), status "${result.status}".`,
  };
}

/** Assign / reassign estimator and reviewer (staff only). */
export async function assignStaff(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimatorId = String(formData.get("estimator_id") || "") || null;
  const reviewerId = String(formData.get("reviewer_id") || "") || null;
  if (!projectId) return;

  const supabase = await createClient();
  await supabase
    .from("project_assignments")
    .upsert(
      { project_id: projectId, estimator_id: estimatorId, reviewer_id: reviewerId },
      { onConflict: "project_id" },
    );

  revalidatePath(`/admin/projects/${projectId}`);
}

export async function regenerateIntakeReview(formData: FormData) {
  const staff = await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  if (!projectId) return;

  const supabase = await createClient();
  const job = await ensureEstimateJobForProject(supabase, projectId);

  const [{ data: project }, { data: scope }, { data: documents }] = await Promise.all([
    supabase
      .from("projects")
      .select("name, company_id, project_type, address, bid_due_at, requested_completion_at, prevailing_wage, is_public")
      .eq("id", projectId)
      .maybeSingle(),
    supabase.from("project_scopes").select("data").eq("project_id", projectId).maybeSingle(),
    supabase
      .from("estimate_job_documents")
      .select("file_name, category, document_type, page_count, processing_status")
      .eq("estimate_job_id", job.id)
      .order("received_at", { ascending: true }),
  ]);

  if (!project) return;
  const packet = buildIntakeReviewPacket({
    project,
    scope: (scope?.data ?? {}) as Record<string, string | null>,
    documents: documents ?? [],
  });

  const { data: updatedJob, error: updateError } = await supabase
    .from("estimate_jobs")
    .update({ intake_review: packet, status: packet.recommended_next_status })
    .eq("id", job.id)
    .select("id")
    .maybeSingle();

  if (updateError || !updatedJob) return;

  await supabase.from("estimate_job_events").insert({
    estimate_job_id: job.id,
    project_id: projectId,
    event_type: "intake_review_generated",
    actor_id: staff.id,
    actor_type: "staff",
    summary: "Intake review packet regenerated.",
    payload: packet,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
}

/**
 * Staff-only repair action: re-derives the EstimateJob (creating it if
 * missing) and re-registers any customer project_files that are not yet in
 * the document register. Used when the "Document register health" summary on
 * the project page shows a gap between uploaded customer files and
 * registered documents.
 */
export async function syncEstimateJobDocumentRegister(formData: FormData) {
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "") || null;
  await requireStaff();
  if (!projectId) return;

  let job;
  try {
    job = await ensureEstimateJobForProject(createAdminClient(), projectId);
  } catch {
    redirectWithEstimateJobNotice(projectId, "action_failed");
  }

  if (estimateJobId && job.id !== estimateJobId) {
    redirectWithEstimateJobNotice(projectId, "document_register_stale");
  }

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
  redirectWithEstimateJobNotice(projectId, "document_register_synced");
}

export async function changeEstimateJobStatus(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const status = String(formData.get("estimateJobStatus") || "");
  const blockedReason = String(formData.get("blockedReason") || "").trim() || null;

  if (!projectId || !estimateJobId || !(ESTIMATE_JOB_STATUSES as readonly string[]).includes(status)) return;

  const supabase = await createClient();
  await supabase.rpc("change_estimate_job_status", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
    p_status: status,
    p_blocked_reason: blockedReason,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
}

export async function updateDocumentReviewStatus(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const documentId = String(formData.get("documentId") || "");
  const reviewStatus = String(formData.get("reviewStatus") || "");
  const reviewNotes = String(formData.get("reviewNotes") || "").trim() || null;

  if (!projectId || !estimateJobId || !documentId || !(DOCUMENT_REVIEW_STATUSES as readonly string[]).includes(reviewStatus)) return;

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("update_estimate_job_document_review", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
    p_document_id: documentId,
    p_review_status: reviewStatus,
    p_review_notes: reviewNotes,
  });

  revalidatePath(`/admin/projects/${projectId}`);

  const result = data as GuardedRpcResult | null;
  if (error || !result?.ok) redirectWithEstimateJobNotice(projectId, result?.reason);
  redirectWithEstimateJobNotice(projectId, "document_review_status_updated");
}

/**
 * Aggregate handoff after per-document review. It refreshes the document
 * register first, then delegates the status transition + audit event to a
 * database RPC so they complete atomically.
 */
export async function completeDocumentReview(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  if (!projectId || !estimateJobId) return;

  // Before completing review, refresh the internal document register from
  // project_files so a stale/failed prior sync cannot hide newly uploaded docs.
  try {
    const job = await ensureEstimateJobForProject(createAdminClient(), projectId);
    if (job.id !== estimateJobId) return;
  } catch {
    return;
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("complete_estimate_document_review", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");

  const result = data as GuardedRpcResult | null;
  if (error || !result?.ok) redirectWithEstimateJobNotice(projectId, result?.reason);
  redirectWithEstimateJobNotice(projectId, "document_review_completed");
}

/**
 * Staff handoff from document review to takeoff. Refreshes the document
 * register first (same reasoning as completeDocumentReview), then delegates
 * the status transition + audit event to a database RPC so they complete
 * atomically.
 */
export async function startTakeoff(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  if (!projectId || !estimateJobId) return;

  try {
    const job = await ensureEstimateJobForProject(createAdminClient(), projectId);
    if (job.id !== estimateJobId) return;
  } catch {
    return;
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("start_estimate_takeoff", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");

  const result = data as GuardedRpcResult | null;
  if (error || !result?.ok) redirectWithEstimateJobNotice(projectId, result?.reason);
  redirectWithEstimateJobNotice(projectId, "takeoff_started");
}

/**
 * Staff handoff from takeoff back to pricing review. Delegates the status
 * transition + audit event to a database RPC so they complete atomically.
 * This only advances the internal job status — it does not create pricing,
 * a final estimate, or any customer-facing deliverable.
 */
export async function completeTakeoff(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const takeoffNotes = String(formData.get("takeoffNotes") || "").trim() || null;
  if (!projectId || !estimateJobId) return;

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("complete_estimate_takeoff", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
    p_takeoff_notes: takeoffNotes,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");

  const result = data as GuardedRpcResult | null;
  if (error || !result?.ok) redirectWithEstimateJobNotice(projectId, result?.reason);
  redirectWithEstimateJobNotice(projectId, "takeoff_completed");
}

/**
 * Staff handoff from pricing review to QA. Delegates the status transition +
 * audit event to a database RPC so they complete atomically. This only
 * advances the internal job status — it does not create a final estimate,
 * customer deliverable, approval package, email, or customer-visible pricing.
 */
export async function completePricingReview(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const pricingNotes = String(formData.get("pricingNotes") || "").trim() || null;
  const expectedJobUpdatedAt = String(formData.get("expectedJobUpdatedAt") || "") || null;
  if (!projectId || !estimateJobId) return;

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("complete_pricing_review", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
    p_pricing_notes: pricingNotes,
    p_expected_updated_at: expectedJobUpdatedAt,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");

  const result = data as GuardedRpcResult | null;
  if (error || !result?.ok) redirectWithEstimateJobNotice(projectId, result?.reason);
  redirectWithEstimateJobNotice(projectId, "pricing_review_completed");
}

/**
 * Staff handoff from QA to internal owner approval. Delegates the status
 * transition + audit event to a database RPC so they complete atomically.
 * This only marks the job ready for internal owner (Moses) review — it does
 * not send, publish, or deliver a final estimate to the customer, and does
 * not create a final estimate, customer deliverable, approval package, or
 * email.
 */
export async function completeQaReview(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const qaNotes = String(formData.get("qaNotes") || "").trim() || null;
  const expectedJobUpdatedAt = String(formData.get("expectedJobUpdatedAt") || "") || null;
  if (!projectId || !estimateJobId) return;

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("complete_qa_review", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
    p_qa_notes: qaNotes,
    p_expected_updated_at: expectedJobUpdatedAt,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");

  const result = data as GuardedRpcResult | null;
  if (error || !result?.ok) redirectWithEstimateJobNotice(projectId, result?.reason);
  redirectWithEstimateJobNotice(projectId, "qa_review_completed");
}

/**
 * Staff-only internal revision request from ready_for_owner_approval back to
 * QA or pricing review. Delegates the status transition + audit event to a
 * database RPC so they complete atomically. This is an internal revision loop
 * only — it does not approve, send, publish, or deliver a final estimate to
 * the customer, and does not create a final estimate, customer deliverable,
 * approval package, or email.
 */
export async function requestOwnerRevision(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const revisionTarget = String(formData.get("revisionTarget") || "");
  const revisionNotes = String(formData.get("revisionNotes") || "").trim() || null;
  if (!projectId || !estimateJobId) return;

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("request_owner_revision", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
    p_revision_target: revisionTarget,
    p_revision_notes: revisionNotes,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");

  const result = data as GuardedRpcResult | null;
  if (error || !result?.ok) redirectWithEstimateJobNotice(projectId, result?.reason);
  redirectWithEstimateJobNotice(projectId, "owner_revision_requested");
}

/**
 * Build and save the deterministic Plan Context Intake v1 packet (staff only).
 * This is a pure, internal read/summarize step over already-registered project
 * and document data — no OCR, AI extraction, quantity takeoff, or pricing runs
 * here, and it does not touch job status.
 */
export async function generatePlanContext(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  if (!projectId || !estimateJobId) return;

  const supabase = await createClient();

  const [{ data: project }, { data: scope }, { data: job }, { data: documents }] = await Promise.all([
    supabase
      .from("projects")
      .select("name, project_type, address, bid_due_at, requested_completion_at, prevailing_wage, is_public")
      .eq("id", projectId)
      .maybeSingle(),
    supabase.from("project_scopes").select("data").eq("project_id", projectId).maybeSingle(),
    supabase.from("estimate_jobs").select("id, status").eq("id", estimateJobId).eq("project_id", projectId).maybeSingle(),
    supabase
      .from("estimate_job_documents")
      .select("id, file_name, category, document_type, page_count, processing_status, review_status, sheet_index")
      .eq("estimate_job_id", estimateJobId)
      .order("received_at", { ascending: true }),
  ]);

  if (!project || !job) return;

  const packet = buildPlanContextPacket({
    project,
    scope: (scope?.data ?? {}) as Record<string, string | null>,
    estimateJobStatus: job.status,
    documents: documents ?? [],
  });

  await supabase.rpc("save_plan_context_intake", {
    p_project_id: projectId,
    p_estimate_job_id: estimateJobId,
    p_plan_context: packet,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
}

export interface AutomationActionResult {
  ok: boolean;
  message: string;
  data?: unknown;
}

async function getEngineProjectId(projectId: string): Promise<string | null> {
  const admin = createAdminClient();
  const { data } = await admin
    .from("projects")
    .select("engine_project_id")
    .eq("id", projectId)
    .maybeSingle();
  return data?.engine_project_id ?? null;
}

function sanitizeEngineScopeEvidence(detail: unknown) {
  if (!detail || typeof detail !== "object") return null;
  const packet = detail as {
    scope_item?: {
      id?: unknown;
      trade_code?: unknown;
      description?: unknown;
      review_status?: unknown;
      conflict_status?: unknown;
    };
    evidence?: Array<{
      extracted_text_quote?: unknown;
      verified_sheet_number?: unknown;
      pdf_page_number?: unknown;
      provider_confidence?: unknown;
      requires_human_verification?: unknown;
    }>;
  };
  const item = packet.scope_item;
  if (!item || typeof item.id !== "string") return null;
  return {
    id: item.id,
    trade_code: typeof item.trade_code === "string" ? item.trade_code : undefined,
    description: typeof item.description === "string" ? item.description : undefined,
    review_status: typeof item.review_status === "string" ? item.review_status : undefined,
    conflict_status: typeof item.conflict_status === "string" ? item.conflict_status : undefined,
    evidence: Array.isArray(packet.evidence)
      ? packet.evidence.slice(0, 3).map((evidence) => ({
          extracted_text_quote:
            typeof evidence.extracted_text_quote === "string" ? evidence.extracted_text_quote.slice(0, 500) : undefined,
          verified_sheet_number:
            typeof evidence.verified_sheet_number === "string" ? evidence.verified_sheet_number : undefined,
          pdf_page_number:
            typeof evidence.pdf_page_number === "number" ? evidence.pdf_page_number : undefined,
          provider_confidence:
            typeof evidence.provider_confidence === "number" ? evidence.provider_confidence : undefined,
          requires_human_verification: Boolean(evidence.requires_human_verification),
        }))
      : [],
  };
}

/** Staff-only: run the safe backend-local estimate draft stages in sequence. */
export async function runAutomationDraftChain(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: "Missing project id." };
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  if (!engineConfigured()) return { ok: false, message: "The estimating engine is not configured on this deployment." };

  try {
    const base = `/api/v1/projects/${engineProjectId}`;
    await enginePostJson(`${base}/process`);
    await enginePostJson(`${base}/coverage/draft`);
    await enginePostJson(`${base}/coverage/generic-scope/draft`);
    await enginePostJson(`${base}/pricing/generic-methods/draft`, {});
    await enginePostJson(`${base}/quantity-requirements/draft`);
    await enginePostJson(`${base}/qa/findings/draft`);
    const readiness = await engineGetJson(`${base}/estimate-readiness`);
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Automation draft chain completed. Review readiness/blockers below.", data: readiness };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Automation draft chain failed." };
  }
}

/** Staff-only: fetch the latest engine readiness packet for this project. */
export async function getAutomationReadiness(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: "Missing project id." };
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(`/api/v1/projects/${engineProjectId}/estimate-readiness`);
    return { ok: true, message: "Readiness loaded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load readiness." };
  }
}

export async function getOwnerReviewPackage(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: "Missing project id." };
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(`/api/v1/projects/${engineProjectId}/owner-review/package`);
    return { ok: true, message: "Owner-review package loaded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load owner-review package." };
  }
}

/** Staff-only: load open quantity requirements and scope items needing pricing basis. */
export async function getAutomationInputNeeds(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const base = `/api/v1/projects/${engineProjectId}`;
    const [quantityRequirements, scopeItems, readiness] = await Promise.all([
      engineGetJson(`${base}/quantity-requirements`),
      engineGetJson(`${base}/scope-items?limit=200`),
      engineGetJson(`${base}/estimate-readiness`),
    ]);
    const pricingNeeds =
      typeof readiness === "object" && readiness !== null && "details" in readiness
        ? (readiness as { details?: { missing_pricing_inputs?: unknown } }).details?.missing_pricing_inputs
        : undefined;
    const scopeItemList =
      typeof scopeItems === "object" && scopeItems !== null && "items" in scopeItems
        ? (scopeItems as { items?: Array<{ id?: unknown }> }).items
        : [];
    const scopeEvidence = (
      await Promise.all(
        (Array.isArray(scopeItemList) ? scopeItemList : [])
          .filter((item): item is { id: string } => typeof item.id === "string")
          .slice(0, 25)
          .map(async (item) => {
            try {
              return sanitizeEngineScopeEvidence(await engineGetJson(`${base}/scope-items/${item.id}`));
            } catch {
              return null;
            }
          }),
      )
    ).filter((item): item is NonNullable<typeof item> => item !== null);
    return {
      ok: true,
      message: "Input needs loaded.",
      data: {
        quantityRequirements,
        scopeItems,
        pricingNeeds: Array.isArray(pricingNeeds) ? pricingNeeds : [],
        scopeEvidence,
      },
    };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load input needs." };
  }
}

export async function applyAutomationQuantityInput(
  projectId: string,
  requirementId: string,
  quantity: string,
  unit: string,
): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineProjectId}/quantity-requirements/${requirementId}/apply`,
      { quantity, unit, source: "admin_verified_quantity" },
    );
    await enginePostJson(`/api/v1/projects/${engineProjectId}/qa/findings/draft`);
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Verified quantity applied.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not apply quantity." };
  }
}

export async function applyAutomationPricingInput(
  projectId: string,
  scopeItemId: string,
  pricingMethod: string,
  amount: string,
): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineProjectId}/pricing/generic-inputs/${scopeItemId}/apply`,
      { pricing_method: pricingMethod, amount, source: "admin_verified_pricing" },
    );
    await enginePostJson(`/api/v1/projects/${engineProjectId}/qa/findings/draft`);
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Verified pricing basis applied.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not apply pricing basis." };
  }
}

export async function getAutomationCustomerRevisions(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(`/api/v1/projects/${engineProjectId}/customer-revisions`);
    return { ok: true, message: "Customer revisions loaded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load customer revisions." };
  }
}

export async function parseAutomationCustomerRevision(
  projectId: string,
  text: string,
): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  if (!text.trim()) return { ok: false, message: "Paste customer revision text before parsing." };
  try {
    const data = await enginePostJson(`/api/v1/projects/${engineProjectId}/customer-revisions/parse`, {
      source: "admin_review_panel",
      actor: "customer",
      text: text.trim(),
    });
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Customer revision text parsed into internal requests.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not parse customer revision text." };
  }
}

export async function decideAutomationCustomerRevision(
  projectId: string,
  requestId: string,
  decision: "accepted" | "rejected" | "needs_clarification",
  notes?: string,
): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineProjectId}/customer-revisions/${requestId}/decide`,
      { decision, reviewer: "admin", notes: notes?.trim() || undefined },
    );
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Customer revision decision recorded internally.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not decide customer revision." };
  }
}

export async function getAutomationRevisionRescopeVersions(
  projectId: string,
  requestId: string,
): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(
      `/api/v1/projects/${engineProjectId}/customer-revisions/${requestId}/rescope-versions`,
    );
    return { ok: true, message: "Rescope version history loaded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load rescope version history." };
  }
}

export async function resolveAutomationRevisionRescope(
  projectId: string,
  requestId: string,
  notes?: string,
): Promise<AutomationActionResult> {
  await requireStaff();
  const engineProjectId = await getEngineProjectId(projectId);
  if (!engineProjectId) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineProjectId}/customer-revisions/${requestId}/resolve-rescope`,
      { actor: "admin", notes: notes?.trim() || undefined },
    );
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Revision rescope resolved internally and version snapshot recorded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not resolve revision rescope." };
  }
}
