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

/**
 * Whitelisted admin-only notices shown on the project page after a guarded
 * EstimateJob RPC call. Keyed by RPC `reason` (for blocked calls) or by a
 * fixed success code chosen by the calling server action. The admin page
 * only ever renders `message` text looked up by this map — never raw text
 * from the URL — so the query param can't be used to inject arbitrary copy.
 */
export type EstimateJobNoticeTone = "success" | "error";

export const ESTIMATE_JOB_NOTICES = {
  stale_job_form: {
    tone: "error",
    message: "This job changed after the page loaded. Refresh and try again if the action is still needed.",
  },
  invalid_status: {
    tone: "error",
    message: "The job is no longer in the required status for that action.",
  },
  invalid_revision_target: {
    tone: "error",
    message: "Choose QA pending or Pricing review pending as the revision target.",
  },
  job_not_found: {
    tone: "error",
    message: "That estimate job could not be found. It may have been removed.",
  },
  project_not_found: {
    tone: "error",
    message: "That project could not be found.",
  },
  document_register_stale: {
    tone: "error",
    message: "The document register changed after the page loaded. Refresh and try again.",
  },
  pending_documents: {
    tone: "error",
    message: "All registered documents must be reviewed before this action can continue.",
  },
  replacement_documents_required: {
    tone: "error",
    message: "One or more documents need replacement before this action can continue.",
  },
  no_accepted_documents: {
    tone: "error",
    message: "At least one document must be accepted before this action can continue.",
  },
  no_documents: {
    tone: "error",
    message: "No documents are registered yet for this job.",
  },
  invalid_review_status: {
    tone: "error",
    message: "That review status is not valid.",
  },
  document_review_locked: {
    tone: "error",
    message: "Document review is locked for the current job status.",
  },
  document_not_found: {
    tone: "error",
    message: "That document could not be found on this job.",
  },
  action_failed: {
    tone: "error",
    message: "This action could not be completed. Refresh and try again.",
  },
  pricing_review_completed: {
    tone: "success",
    message: "Pricing review completed. Job advanced to QA.",
  },
  qa_review_completed: {
    tone: "success",
    message: "QA review completed. Job marked ready for internal owner approval.",
  },
  owner_revision_requested: {
    tone: "success",
    message: "Revision requested. Job returned for corrections.",
  },
  takeoff_started: {
    tone: "success",
    message: "Takeoff started.",
  },
  takeoff_completed: {
    tone: "success",
    message: "Takeoff completed. Job advanced to pricing review.",
  },
  document_review_completed: {
    tone: "success",
    message: "Document review completed.",
  },
  document_review_status_updated: {
    tone: "success",
    message: "Document review status saved.",
  },
  document_register_synced: {
    tone: "success",
    message: "Document register synced from customer files.",
  },
} as const satisfies Record<string, { tone: EstimateJobNoticeTone; message: string }>;

export type EstimateJobNoticeCode = keyof typeof ESTIMATE_JOB_NOTICES;

export function isEstimateJobNoticeCode(value: string | null | undefined): value is EstimateJobNoticeCode {
  return Boolean(value) && Object.prototype.hasOwnProperty.call(ESTIMATE_JOB_NOTICES, value as string);
}

/** Looks up a notice by code, ignoring anything not in the whitelist above. */
export function resolveEstimateJobNotice(
  code: string | null | undefined,
): { code: EstimateJobNoticeCode; tone: EstimateJobNoticeTone; message: string } | null {
  if (!isEstimateJobNoticeCode(code)) return null;
  return { code, ...ESTIMATE_JOB_NOTICES[code] };
}

/**
 * Whitelisted admin-only filter groups for the internal evidence timeline.
 * `estimateJobEventFilterGroup` maps a raw `event_type` (written by the
 * EstimateJob RPCs) into one of these groups so the admin page can filter by
 * `?estimateJobEventFilter=` without trusting the query param itself. Unknown
 * query-param values resolve to "all"; unknown stored event types group under "status".
 */
export const ESTIMATE_JOB_EVENT_FILTERS = [
  "all",
  "document_review",
  "takeoff",
  "pricing",
  "qa",
  "owner_revision",
  "plan_context",
  "status",
] as const;

export type EstimateJobEventFilter = (typeof ESTIMATE_JOB_EVENT_FILTERS)[number];

const ESTIMATE_JOB_EVENT_FILTER_LABELS: Record<EstimateJobEventFilter, string> = {
  all: "All",
  document_review: "Document review",
  takeoff: "Takeoff",
  pricing: "Pricing",
  qa: "QA",
  owner_revision: "Owner revision",
  plan_context: "Plan context",
  status: "Status",
};

export function estimateJobEventFilterLabel(filter: EstimateJobEventFilter): string {
  return ESTIMATE_JOB_EVENT_FILTER_LABELS[filter];
}

/** event_type values written by the EstimateJob RPCs (supabase/migrations/0010-0020), grouped for filtering. */
const EVENT_TYPE_FILTER_GROUPS: Record<string, Exclude<EstimateJobEventFilter, "all">> = {
  document_registered: "document_review",
  document_review_updated: "document_review",
  document_review_completed: "document_review",
  takeoff_started: "takeoff",
  takeoff_completed: "takeoff",
  pricing_review_completed: "pricing",
  qa_review_completed: "qa",
  owner_revision_requested: "owner_revision",
  plan_context_generated: "plan_context",
  job_created: "status",
  status_changed: "status",
  intake_review_generated: "status",
};

/** Falls back to "status" for any event_type not in the known map above. */
export function estimateJobEventFilterGroup(eventType: string): EstimateJobEventFilter {
  return EVENT_TYPE_FILTER_GROUPS[eventType] ?? "status";
}

export function isEstimateJobEventFilter(value: string | null | undefined): value is EstimateJobEventFilter {
  return Boolean(value) && (ESTIMATE_JOB_EVENT_FILTERS as readonly string[]).includes(value as string);
}

/** Looks up the filter against the fixed whitelist above; anything else (or missing) resolves to "all". */
export function resolveEstimateJobEventFilter(value: string | null | undefined): EstimateJobEventFilter {
  return isEstimateJobEventFilter(value) ? value : "all";
}

/**
 * Customer-visible deliverable uploads must wait for explicit internal
 * owner approval, not just QA sign-off. This is the single gate the admin
 * project page and DeliverableUpload consult before allowing an upload.
 */
export function canUploadCustomerDeliverable(estimateJobStatus: string | null | undefined): boolean {
  return estimateJobStatus === "ready_for_owner_approval";
}

/** Fixed, non-committal copy for the deliverable gate — never mentions email/send/auto-delivery. */
export function customerDeliverableGateMessage(estimateJobStatus: string | null | undefined): string {
  if (canUploadCustomerDeliverable(estimateJobStatus)) {
    return "Internal owner approval status confirmed. Uploads here become downloadable in the customer portal immediately.";
  }
  const label = estimateJobStatus ? estimateJobStatusLabel(estimateJobStatus) : "No estimate job status";
  return `Customer deliverable uploads are locked until the internal owner approves this job (current status: ${label}).`;
}

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

export interface EstimateDocumentRegisterHealth {
  customerFileCount: number;
  registeredCount: number;
  missingCount: number;
}

/**
 * Pure anti-join of customer project_file ids against the project_file_id
 * each estimate_job_documents row was registered from. A doc row with a null
 * project_file_id (legacy/manual) counts toward `registeredCount` but never
 * masks a customer file that has no matching doc.
 */
export function estimateDocumentRegisterHealth(
  projectFileIds: string[],
  documentProjectFileIds: Array<string | null>,
): EstimateDocumentRegisterHealth {
  const registeredFileIds = new Set(
    documentProjectFileIds.filter((id): id is string => Boolean(id)),
  );
  const missingCount = projectFileIds.filter((id) => !registeredFileIds.has(id)).length;

  return {
    customerFileCount: projectFileIds.length,
    registeredCount: documentProjectFileIds.length,
    missingCount,
  };
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
