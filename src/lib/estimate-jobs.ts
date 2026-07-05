import type { SupabaseClient } from "@supabase/supabase-js";

export const ESTIMATE_JOB_STATUSES = [
  "intake_received",
  "intake_review_pending",
  "intake_needs_info",
  "ready_for_document_processing",
  "document_processing",
  "document_review_pending",
  "takeoff_ready",
  "takeoff_in_progress",
  "pricing_review_pending",
  "qa_pending",
  "ready_for_owner_approval",
  "blocked",
  "canceled",
  "closed",
] as const;

export type EstimateJobStatus = (typeof ESTIMATE_JOB_STATUSES)[number];

const STATUS_LABELS: Record<EstimateJobStatus, string> = {
  intake_received: "Intake received",
  intake_review_pending: "Intake review pending",
  intake_needs_info: "Needs intake info",
  ready_for_document_processing: "Ready for document processing",
  document_processing: "Document processing",
  document_review_pending: "Document review pending",
  takeoff_ready: "Takeoff ready",
  takeoff_in_progress: "Takeoff in progress",
  pricing_review_pending: "Pricing review pending",
  qa_pending: "QA pending",
  ready_for_owner_approval: "Ready for owner approval",
  blocked: "Blocked",
  canceled: "Canceled",
  closed: "Closed",
};

export function estimateJobStatusLabel(status: string): string {
  return STATUS_LABELS[status as EstimateJobStatus] ?? status;
}

export const DOCUMENT_REVIEW_STATUSES = ["pending", "accepted", "needs_replacement", "ignored"] as const;
export type DocumentReviewStatus = (typeof DOCUMENT_REVIEW_STATUSES)[number];

export function estimateJobBadgeClass(status: string): string {
  if (status === "blocked" || status === "intake_needs_info") return "bg-amber-50 text-amber-700";
  if (status === "closed") return "bg-green-50 text-green-700";
  if (status === "canceled") return "bg-slate-100 text-slate-600";
  if (status === "ready_for_owner_approval") return "bg-green-50 text-green-700";
  return "bg-blue-50 text-blue-700";
}

interface EnsureEstimateJobInput {
  projectId: string;
  companyId: string;
  bidDueAt?: string | null;
  requestedCompletionAt?: string | null;
  createdBy?: string | null;
}

interface RegisterProjectFileInput {
  id: string;
  project_id: string;
  company_id: string;
  storage_path: string;
  file_name: string;
  category: string;
  created_at?: string | null;
}

interface SupabaseErrorLike {
  code?: string;
  message?: string;
}

function isUniqueViolation(error: unknown): boolean {
  const err = error as SupabaseErrorLike;
  return err?.code === "23505" || Boolean(err?.message?.toLowerCase().includes("duplicate key"));
}

function documentTypeForCategory(category: string): string {
  const normalized = category.toLowerCase();
  if (normalized.includes("drawing")) return "plan_set";
  if (normalized.includes("spec")) return "spec_book";
  if (normalized.includes("addenda") || normalized.includes("addendum")) return "addendum";
  if (normalized.includes("scope") || normalized.includes("bid")) return "scope_sheet";
  return "other";
}

export async function ensureEstimateJob(
  supabase: SupabaseClient,
  input: EnsureEstimateJobInput,
) {
  const { data: existing, error: selectError } = await supabase
    .from("estimate_jobs")
    .select("id")
    .eq("project_id", input.projectId)
    .maybeSingle();

  if (selectError) throw selectError;
  if (existing?.id) return existing;

  const intakeSummary = {
    source: "project_submission",
    requested_completion_at: input.requestedCompletionAt ?? null,
  };

  const { data: job, error: insertError } = await supabase
    .from("estimate_jobs")
    .insert({
      project_id: input.projectId,
      company_id: input.companyId,
      bid_due_at: input.bidDueAt ?? null,
      target_delivery_at: input.requestedCompletionAt ?? null,
      created_by: input.createdBy ?? null,
      intake_summary: intakeSummary,
    })
    .select("id")
    .single();

  if (insertError) {
    if (isUniqueViolation(insertError)) {
      const { data: concurrentJob, error: concurrentSelectError } = await supabase
        .from("estimate_jobs")
        .select("id")
        .eq("project_id", input.projectId)
        .single();
      if (concurrentSelectError) throw concurrentSelectError;
      return concurrentJob;
    }
    throw insertError;
  }

  await supabase.from("estimate_job_events").insert({
    estimate_job_id: job.id,
    project_id: input.projectId,
    event_type: "job_created",
    actor_id: input.createdBy ?? null,
    actor_type: "system",
    summary: "Internal estimate job created from project submission.",
    payload: intakeSummary,
  });

  return job;
}

export async function registerEstimateJobDocuments(
  supabase: SupabaseClient,
  estimateJobId: string,
  files: RegisterProjectFileInput[],
) {
  if (files.length === 0) return { registered: 0 };

  const projectFileIds = files.map((file) => file.id);
  const { data: existingRows, error: existingError } = await supabase
    .from("estimate_job_documents")
    .select("project_file_id")
    .eq("estimate_job_id", estimateJobId)
    .in("project_file_id", projectFileIds);
  if (existingError) throw existingError;

  const existingFileIds = new Set(
    (existingRows ?? [])
      .map((row) => row.project_file_id as string | null)
      .filter((id): id is string => Boolean(id)),
  );

  const rows = files.map((file) => ({
    estimate_job_id: estimateJobId,
    project_file_id: file.id,
    company_id: file.company_id,
    project_id: file.project_id,
    storage_path: file.storage_path,
    file_name: file.file_name,
    category: file.category,
    document_type: documentTypeForCategory(file.category),
    received_at: file.created_at ?? new Date().toISOString(),
  }));

  const { error } = await supabase
    .from("estimate_job_documents")
    .upsert(rows, { onConflict: "estimate_job_id,project_file_id", ignoreDuplicates: true });
  if (error) throw error;

  const newlyRegisteredRows = rows.filter((row) => !existingFileIds.has(row.project_file_id));
  if (newlyRegisteredRows.length > 0) {
    await supabase.from("estimate_job_events").insert(
      newlyRegisteredRows.map((row) => ({
        estimate_job_id: estimateJobId,
        project_id: row.project_id,
        event_type: "document_registered",
        actor_type: "system",
        summary: `Registered document: ${row.file_name}`,
        payload: {
          project_file_id: row.project_file_id,
          category: row.category,
          storage_path: row.storage_path,
        },
      })),
    );
  }

  return { registered: newlyRegisteredRows.length };
}

export async function ensureEstimateJobForProject(supabase: SupabaseClient, projectId: string) {
  const { data: project, error: projectError } = await supabase
    .from("projects")
    .select("id, company_id, bid_due_at, requested_completion_at, created_by")
    .eq("id", projectId)
    .maybeSingle();

  if (projectError) throw projectError;
  if (!project) throw new Error("Project not found.");

  const job = await ensureEstimateJob(supabase, {
    projectId: project.id,
    companyId: project.company_id,
    bidDueAt: project.bid_due_at,
    requestedCompletionAt: project.requested_completion_at,
    createdBy: project.created_by,
  });

  const { data: files, error: filesError } = await supabase
    .from("project_files")
    .select("id, project_id, company_id, storage_path, file_name, category, created_at")
    .eq("project_id", projectId)
    .is("deleted_at", null);

  if (filesError) throw filesError;
  await registerEstimateJobDocuments(supabase, job.id, files ?? []);
  return job;
}
