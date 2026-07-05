"use server";

import { revalidatePath } from "next/cache";
import { requireStaff } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { ALL_STATUSES } from "@/lib/projects";
import {
  DOCUMENT_REVIEW_STATUSES,
  ESTIMATE_JOB_STATUSES,
  ensureEstimateJobForProject,
} from "@/lib/estimate-jobs";
import { buildIntakeReviewPacket } from "@/lib/intake-review";

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

export async function changeEstimateJobStatus(formData: FormData) {
  const staff = await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const status = String(formData.get("estimateJobStatus") || "");
  const blockedReason = String(formData.get("blockedReason") || "").trim() || null;

  if (!projectId || !estimateJobId || !(ESTIMATE_JOB_STATUSES as readonly string[]).includes(status)) return;

  const supabase = await createClient();
  const { data: updatedJob, error: updateError } = await supabase
    .from("estimate_jobs")
    .update({ status, blocked_reason: status === "blocked" ? blockedReason : null })
    .eq("id", estimateJobId)
    .eq("project_id", projectId)
    .select("id")
    .maybeSingle();

  if (updateError || !updatedJob) return;

  await supabase.from("estimate_job_events").insert({
    estimate_job_id: estimateJobId,
    project_id: projectId,
    event_type: "status_changed",
    actor_id: staff.id,
    actor_type: "staff",
    summary: `Estimate job status changed to ${status}.`,
    payload: { status, blocked_reason: blockedReason },
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
}

export async function updateDocumentReviewStatus(formData: FormData) {
  const staff = await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimateJobId = String(formData.get("estimateJobId") || "");
  const documentId = String(formData.get("documentId") || "");
  const reviewStatus = String(formData.get("reviewStatus") || "");
  const reviewNotes = String(formData.get("reviewNotes") || "").trim() || null;

  if (!projectId || !estimateJobId || !documentId || !(DOCUMENT_REVIEW_STATUSES as readonly string[]).includes(reviewStatus)) return;

  const supabase = await createClient();
  const { data: updatedDocument, error: updateError } = await supabase
    .from("estimate_job_documents")
    .update({ review_status: reviewStatus, review_notes: reviewNotes })
    .eq("id", documentId)
    .eq("estimate_job_id", estimateJobId)
    .select("id")
    .maybeSingle();

  if (updateError || !updatedDocument) return;

  await supabase.from("estimate_job_events").insert({
    estimate_job_id: estimateJobId,
    project_id: projectId,
    event_type: "document_review_updated",
    actor_id: staff.id,
    actor_type: "staff",
    summary: `Document review marked ${reviewStatus}.`,
    payload: { document_id: documentId, review_status: reviewStatus, review_notes: reviewNotes },
  });

  revalidatePath(`/admin/projects/${projectId}`);
}
