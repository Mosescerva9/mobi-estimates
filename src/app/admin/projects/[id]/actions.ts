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
  canSetFinalDeliveryProjectStatus,
  isFinalDeliveryProjectStatus,
  isEstimateJobNoticeCode,
  isIntroOfferNotAcceptedError,
  type EstimateJobNoticeCode,
} from "@/lib/estimate-jobs";
import { createStatusChangeNotifications } from "@/lib/notifications";
import { buildIntakeReviewPacket } from "@/lib/intake-review";
import { buildPlanContextPacket } from "@/lib/plan-context";
import {
  engineConfigured,
  engineGetJson,
  enginePostJson,
  engineUploadPacket,
  type EnginePacketSource,
} from "@/lib/engine";
import {
  resolveAcceptedPacketSources,
  type AcceptedEngineSource,
  type ActiveProjectFileRow,
  type RegisterDocumentRow,
} from "@/lib/engine-packet-sources";
import {
  LIVE_SCOPE_COPY,
  buildLiveScopeExtractionPayload,
  isExpectedLiveExtractionRun,
  isLiveReady,
  normalizeLiveReadiness,
  resolveEnabledTrade,
  sanitizeLiveExtractionRun,
} from "@/lib/live-scope-extraction";

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

  // Delivered/revised/approved are final-delivery surfaces. A status label must not be
  // used as a substitute for the audit-required delivery lock: complete
  // evidence, supported scope, required reviews, and explicit owner approval.
  // The current portal has no persisted final-delivery approval bundle, so this
  // transition fails closed until that workflow exists.
  if (isFinalDeliveryProjectStatus(toStatus) && !canSetFinalDeliveryProjectStatus()) {
    redirectWithEstimateJobNotice(projectId, "final_delivery_locked");
  }

  const supabase = await createClient();

  const { data: current } = await supabase
    .from("projects")
    .select("status, company_id")
    .eq("id", projectId)
    .maybeSingle();

  // Update the project status (RLS: staff allowed).
  const { error: updateErr } = await supabase
    .from("projects")
    .update({ status: toStatus })
    .eq("id", projectId);

  // Append a timeline entry (RLS: status_history insert is staff-only). Capture
  // its id so notifications can be keyed to this exact event (idempotency).
  const { data: historyRow, error: historyErr } = await supabase
    .from("project_status_history")
    .insert({
      project_id: projectId,
      from_status: current?.status ?? null,
      to_status: toStatus,
      changed_by: staff.id,
      client_note: clientNote,
      internal_note: internalNote,
    })
    .select("id")
    .maybeSingle();

  // Create tenant-scoped in-app notifications for the customer company and HELD
  // external-outbox rows (no sends in this packet). Best-effort: a notification
  // failure must not fail the status change. Copy is deterministic and never
  // includes the internal note.
  //
  // Only notify when the status update AND the status-history insert BOTH
  // succeeded and produced a canonical history id. Without a real event id the
  // notifications would be null-keyed and idempotency would be defeated, so we
  // skip notification creation entirely rather than write unkeyed rows.
  if (!updateErr && !historyErr && historyRow?.id && current?.company_id) {
    try {
      await createStatusChangeNotifications(supabase, {
        companyId: current.company_id,
        projectId,
        statusHistoryId: historyRow.id,
        toStatus,
      });
    } catch {
      /* non-fatal: status change already persisted */
    }
  }

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
}

export interface EngineActionResult {
  ok: boolean;
  message: string;
}

/**
 * Push a portal project's ENTIRE accepted PDF set into the estimating engine as
 * ONE deterministic packet (staff only), creating (or idempotently reusing) a
 * single engine-side project and storing its id/status on the row plus the
 * source manifest on the internal estimate job.
 *
 * A real solicitation package arrives as several PDFs (project manual, drawings,
 * addenda). The engine models one stored PDF per project and the OpenTakeoff
 * worker resolves a document by `document_id == engine_project_id` whose SHA-256
 * must match the stored file. To cross the whole package into one engine project
 * without breaking that contract, the engine deterministically merges every
 * accepted PDF into one packet whose SHA-256 becomes the project's stored file
 * hash, and returns a manifest preserving each source's identity, bytes,
 * SHA-256, page count, and contiguous packet page range.
 *
 * Fail-closed / retry-safe:
 *  - every accepted PDF is included or the whole upload fails closed (the engine
 *    never silently omits a source);
 *  - assembly is deterministic, so a retry re-uses the same engine project id
 *    rather than creating a second linked engine project;
 *  - a clean "sent" result is reported only when BOTH the engine link and the
 *    packet manifest persisted — a partial persistence returns ok:false so the
 *    staff-safe retry can complete it.
 *
 * The engine only ingests the packet here (no automated takeoff/pricing), so
 * this does not produce a priced estimate, proposal, or any customer-facing
 * deliverable — it establishes the linked engine project the pipeline builds on.
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
    .select("id, name, company_id, engine_project_id, companies(legal_name)")
    .eq("id", projectId)
    .maybeSingle();
  if (projErr || !project) {
    return { ok: false, message: "Project not found." };
  }

  const companyId = typeof project.company_id === "string" ? project.company_id : "";
  if (!companyId) {
    return { ok: false, message: "Project is missing a company; cannot establish engine tenant identity." };
  }
  const company = project.companies as unknown as { legal_name: string | null } | null;
  const engineContext = { tenantId: companyId, companyId };

  // Derive the EXACT accepted document set from the internal estimate job's
  // register — NOT every non-deleted project_files PDF. Fail closed on an
  // undecided, stale, unsupported, or empty accepted set so ignored / pending /
  // needs-replacement / non-PDF documents are never packaged.
  const accepted = await deriveAcceptedEngineSources(admin, projectId, companyId);
  if (!accepted.ok) return { ok: false, message: accepted.message };
  const acceptedDocs = accepted.acceptedDocs;
  const estimateJobId = accepted.jobId;

  // Download + snapshot each accepted source (SHA-256 + byte length) so the
  // engine's response manifest can be validated against this exact submitted
  // set. A single unreadable source fails the whole packet closed.
  const sources: EnginePacketSource[] = [];
  for (let index = 0; index < acceptedDocs.length; index += 1) {
    const doc = acceptedDocs[index];
    const { data: blob, error: dlErr } = await admin.storage
      .from(PROJECT_FILES_BUCKET)
      .download(doc.storage_path);
    if (dlErr || !blob) {
      return {
        ok: false,
        message: `Could not read "${doc.file_name}" from storage: ${dlErr?.message ?? "unknown error"}. No documents were sent.`,
      };
    }
    const buffer = await blob.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", buffer);
    const sha256 = Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    sources.push({
      file: blob,
      fileName: doc.file_name,
      projectFileId: doc.project_file_id,
      storagePath: doc.storage_path,
      order: index,
      declaredSha256: sha256,
      bytes: buffer.byteLength,
    });
  }

  // A retry over an established link must name the expected engine id so the
  // engine (and the CAS write below) reject a mismatch instead of forking or
  // overwriting the link.
  const existingEngineId =
    typeof project.engine_project_id === "string" && project.engine_project_id
      ? project.engine_project_id
      : null;

  let result;
  try {
    result = await engineUploadPacket({
      projectName: project.name,
      portalProjectId: projectId,
      contractorName: company?.legal_name ?? null,
      expectedEngineProjectId: existingEngineId,
      sources,
      context: engineContext,
    });
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Engine packet upload failed." };
  }

  // ONE staff-only, security-definer CAS RPC persists the engine link (id +
  // status + page count) AND the packet manifest AND at most one event —
  // atomically, in the locked order estimate_jobs -> projects. It re-validates
  // the manifest against the accepted document snapshot server-side and refuses
  // to replace a conflicting established link.
  const persisted = await persistEnginePacketLinkAndManifest({
    projectId,
    estimateJobId,
    engineProjectId: result.project_id,
    engineStatus: result.status,
    enginePageCount: result.page_count,
    engineFileSizeBytes: result.file_size_bytes,
    engineFileSha256: result.file_sha256,
    manifest: result.packet_manifest,
  });

  revalidatePath(`/admin/projects/${projectId}`);

  const sourceCount = result.packet_manifest.packet.source_count;
  if (!persisted.ok) {
    if (persisted.reason === "engine_project_conflict") {
      return {
        ok: false,
        message: `The engine packet (${result.project_id}) was assembled, but this project is already linked to a different engine project; the established link was not replaced.`,
      };
    }
    return {
      ok: false,
      message: `Sent ${sourceCount} document(s) as one engine packet (${result.page_count} page(s)) but the engine link/manifest was not saved (${persisted.reason}). Retry is safe.`,
    };
  }

  return {
    ok: true,
    message: `Sent ${sourceCount} document(s) as one engine packet — ${result.page_count} page(s), status "${result.status}".`,
  };
}

type AcceptedEngineSourcesResult =
  | { ok: true; jobId: string; acceptedDocs: AcceptedEngineSource[] }
  | { ok: false; message: string };

/**
 * Resolve the exact accepted document set to package for the engine.
 *
 * The register records the review decision, but ACTIVE `project_files` is the
 * authority on which files exist and what their identity is: every accepted row
 * must join to a non-soft-deleted file in the SAME project and company with an
 * identical id, storage path, and file name. That join is enforced by the pure
 * `resolveAcceptedPacketSources` (see src/lib/engine-packet-sources.ts) BEFORE
 * any service-role download or packet call, so a stale extra accepted row, a
 * soft-deleted file, a cross-project/company file, or a path/name-divergent row
 * can never be read with elevated privileges or shipped to the engine.
 *
 * Every id here is server-owned (the route's project id and the project's own
 * company id); nothing is taken from browser input. Ignored documents are
 * intentionally excluded, never sent.
 */
async function deriveAcceptedEngineSources(
  admin: ReturnType<typeof createAdminClient>,
  projectId: string,
  companyId: string,
): Promise<AcceptedEngineSourcesResult> {
  let job;
  try {
    job = await ensureEstimateJobForProject(admin, projectId);
  } catch (error) {
    if (isIntroOfferNotAcceptedError(error)) {
      return {
        ok: false,
        message:
          "The free-offer qualification hasn't been accepted for this company, so there is no internal estimate job to source the accepted document set from.",
      };
    }
    return { ok: false, message: "Could not resolve the internal estimate job for this project." };
  }
  if (!job?.id) return { ok: false, message: "No internal estimate job exists for this project." };

  // Read the FULL identity of every active file (not just its id) so the
  // register's copy of path/name/project/company can be proven against it.
  const { data: activeFiles, error: filesErr } = await admin
    .from("project_files")
    .select("id, project_id, company_id, storage_path, file_name")
    .eq("project_id", projectId)
    .is("deleted_at", null);
  if (filesErr) return { ok: false, message: `Could not read project files: ${filesErr.message}.` };

  // Read the register unfiltered by project/company so a cross-project or
  // cross-company row is REJECTED by the resolver rather than silently filtered
  // out of the comparison (which would let it pass as "not present").
  const { data: docs, error: docsErr } = await admin
    .from("estimate_job_documents")
    .select("id, project_file_id, project_id, company_id, file_name, storage_path, review_status, received_at")
    .eq("estimate_job_id", job.id)
    .order("received_at", { ascending: true })
    .order("id", { ascending: true });
  if (docsErr) return { ok: false, message: `Could not read the document register: ${docsErr.message}.` };

  const resolved = resolveAcceptedPacketSources({
    projectId,
    companyId,
    activeFiles: (activeFiles ?? []) as ActiveProjectFileRow[],
    register: (docs ?? []) as RegisterDocumentRow[],
  });
  if (!resolved.ok) return { ok: false, message: resolved.message };

  return { ok: true, jobId: job.id, acceptedDocs: resolved.acceptedDocs };
}

/**
 * Persist the engine link (id + status + page count + packet byte count + packet
 * content hash) AND the packet manifest via
 * the ONE staff-only, security-definer save_engine_packet_manifest CAS RPC. The
 * RPC is called with the authenticated staff client because its is_staff() gate
 * keys on auth.uid(); it bypasses RLS as security-definer to write the locked
 * link + manifest + at-most-one event atomically. It re-validates the manifest
 * structure and the accepted-document snapshot server-side and returns a
 * conflict result rather than replacing an established, different engine link.
 * Never throws, so a persistence gap surfaces as a safe-retry result.
 */
async function persistEnginePacketLinkAndManifest(args: {
  projectId: string;
  estimateJobId: string;
  engineProjectId: string;
  engineStatus: string;
  enginePageCount: number;
  engineFileSizeBytes: number;
  engineFileSha256: string;
  manifest: unknown;
}): Promise<{ ok: boolean; reason: string }> {
  // Validate the stored packet's byte count and content hash HERE too,
  // independently of the response schema, before handing them to the RPC as the
  // values the manifest must equal. A non-integral / nonpositive / unsafe size
  // or a non-64-hex digest is never sent: the RPC compares both for exact
  // equality with the manifest, so a bad value could otherwise either be
  // rejected as a confusing mismatch or, worse, agree with an equally bad
  // manifest value.
  if (
    !Number.isSafeInteger(args.engineFileSizeBytes) ||
    args.engineFileSizeBytes <= 0
  ) {
    return { ok: false, reason: "invalid engine packet byte count" };
  }
  if (!/^[0-9a-f]{64}$/.test(args.engineFileSha256)) {
    return { ok: false, reason: "invalid engine packet content hash" };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("save_engine_packet_manifest", {
    p_project_id: args.projectId,
    p_estimate_job_id: args.estimateJobId,
    p_engine_project_id: args.engineProjectId,
    p_engine_status: args.engineStatus,
    p_engine_page_count: args.enginePageCount,
    p_engine_file_size_bytes: args.engineFileSizeBytes,
    p_engine_file_sha256: args.engineFileSha256,
    p_packet_manifest: args.manifest,
  });
  if (error) return { ok: false, reason: "link/manifest write failed" };
  const result = data as { ok?: boolean; reason?: string } | null;
  if (!result?.ok) return { ok: false, reason: result?.reason ?? "link/manifest write rejected" };
  return { ok: true, reason: "recorded" };
}

/**
 * Staff accept/reject of a company's free-offer (intro offer) qualification.
 * Delegates to the security-definer decide_intro_offer_claim RPC, which
 * atomically:
 *   - on accept: flips requested -> accepted AND provisions the EstimateJob
 *     (a database trigger blocks any EstimateJob write until this happens);
 *   - on reject: flips requested -> rejected AND cancels + soft-deletes the
 *     project AND appends an audit timeline event — never a hard delete.
 * The optional internal note is stored server-side and never surfaced to
 * customers; the customer only ever sees a fixed public status/reason copy.
 */
export async function decideIntroOfferClaim(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const decision = String(formData.get("decision") || "");
  const reasonClass = String(formData.get("reasonClass") || "").trim() || null;
  const internalNote = String(formData.get("internalNote") || "").trim() || null;
  if (!projectId || (decision !== "accept" && decision !== "reject")) return;

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("decide_intro_offer_claim", {
    p_project: projectId,
    p_decision: decision,
    p_reason_class: reasonClass,
    p_internal_note: internalNote,
  });
  const result = data as { ok?: boolean; status?: string } | null;

  if (!error && result?.ok && decision === "accept") {
    // The RPC already created the EstimateJob row; register any files the
    // customer already uploaded into the internal document register (safe —
    // ensureEstimateJobForProject finds the existing job and never re-inserts).
    try {
      await ensureEstimateJobForProject(createAdminClient(), projectId);
    } catch {
      /* best-effort document sync; the job itself is already provisioned */
    }
  }

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");

  if (!error && result?.ok && decision === "reject") {
    // Rejection atomically cancels and soft-deletes the project, so its
    // detail page is no longer reachable — return to the queue instead of a 404.
    redirect("/admin");
  }
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
  let job;
  try {
    job = await ensureEstimateJobForProject(supabase, projectId);
  } catch (error) {
    if (isIntroOfferNotAcceptedError(error)) {
      redirectWithEstimateJobNotice(projectId, "intro_offer_pending_acceptance");
    }
    redirectWithEstimateJobNotice(projectId, "action_failed");
  }

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
  } catch (error) {
    if (isIntroOfferNotAcceptedError(error)) {
      redirectWithEstimateJobNotice(projectId, "intro_offer_pending_acceptance");
    }
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

interface EngineProjectContext {
  engineProjectId: string;
  tenantId: string;
  companyId: string;
}

async function getEngineProjectContext(projectId: string): Promise<EngineProjectContext | null> {
  const admin = createAdminClient();
  const { data } = await admin
    .from("projects")
    .select("engine_project_id, company_id")
    .eq("id", projectId)
    .maybeSingle();
  if (!data?.engine_project_id || !data.company_id) return null;
  return {
    engineProjectId: data.engine_project_id,
    tenantId: data.company_id,
    companyId: data.company_id,
  };
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  if (!engineConfigured()) return { ok: false, message: "The estimating engine is not configured on this deployment." };

  try {
    const base = `/api/v1/projects/${engineContext.engineProjectId}`;
    await enginePostJson(`${base}/process`, undefined, engineContext);
    await enginePostJson(`${base}/coverage/draft`, undefined, engineContext);
    await enginePostJson(`${base}/coverage/generic-scope/draft`, undefined, engineContext);
    await enginePostJson(`${base}/pricing/generic-methods/draft`, {}, engineContext);
    await enginePostJson(`${base}/quantity-requirements/draft`, undefined, engineContext);
    await enginePostJson(`${base}/qa/findings/draft`, undefined, engineContext);
    const readiness = await engineGetJson(`${base}/estimate-readiness`, engineContext);
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(`/api/v1/projects/${engineContext.engineProjectId}/estimate-readiness`, engineContext);
    return { ok: true, message: "Readiness loaded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load readiness." };
  }
}

export async function getOwnerReviewPackage(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: "Missing project id." };
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(`/api/v1/projects/${engineContext.engineProjectId}/owner-review/package`, engineContext);
    return { ok: true, message: "Owner-review package loaded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load owner-review package." };
  }
}

/** Staff-only: load open quantity requirements and scope items needing pricing basis. */
export async function getAutomationInputNeeds(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const base = `/api/v1/projects/${engineContext.engineProjectId}`;
    const [quantityRequirements, scopeItems, readiness] = await Promise.all([
      engineGetJson(`${base}/quantity-requirements`, engineContext),
      engineGetJson(`${base}/scope-items?limit=200`, engineContext),
      engineGetJson(`${base}/estimate-readiness`, engineContext),
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
              return sanitizeEngineScopeEvidence(await engineGetJson(`${base}/scope-items/${item.id}`, engineContext));
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineContext.engineProjectId}/quantity-requirements/${requirementId}/apply`,
      { quantity, unit, source: "admin_verified_quantity" },
      engineContext,
    );
    await enginePostJson(`/api/v1/projects/${engineContext.engineProjectId}/qa/findings/draft`, undefined, engineContext);
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineContext.engineProjectId}/pricing/generic-inputs/${scopeItemId}/apply`,
      { pricing_method: pricingMethod, amount, source: "admin_verified_pricing" },
      engineContext,
    );
    await enginePostJson(`/api/v1/projects/${engineContext.engineProjectId}/qa/findings/draft`, undefined, engineContext);
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Verified pricing basis applied.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not apply pricing basis." };
  }
}

export async function getAutomationCustomerRevisions(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(`/api/v1/projects/${engineContext.engineProjectId}/customer-revisions`, engineContext);
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  if (!text.trim()) return { ok: false, message: "Paste customer revision text before parsing." };
  try {
    const data = await enginePostJson(`/api/v1/projects/${engineContext.engineProjectId}/customer-revisions/parse`, {
      source: "admin_review_panel",
      actor: "customer",
      text: text.trim(),
    }, engineContext);
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineContext.engineProjectId}/customer-revisions/${requestId}/decide`,
      { decision, reviewer: "admin", notes: notes?.trim() || undefined },
      engineContext,
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await engineGetJson(
      `/api/v1/projects/${engineContext.engineProjectId}/customer-revisions/${requestId}/rescope-versions`,
      engineContext,
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
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: "Project has not been sent to the estimating engine yet." };
  try {
    const data = await enginePostJson(
      `/api/v1/projects/${engineContext.engineProjectId}/customer-revisions/${requestId}/resolve-rescope`,
      { actor: "admin", notes: notes?.trim() || undefined },
      engineContext,
    );
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: "Revision rescope resolved internally and version snapshot recorded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not resolve revision rescope." };
  }
}

/**
 * Staff-only: report whether live GPT-5.6 scope analysis is available for this
 * project and which trades are enabled. This is a safe read of the engine's
 * live-readiness surface — it never returns key material or starts a run.
 */
export async function getLiveScopeExtractionReadiness(projectId: string): Promise<AutomationActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: LIVE_SCOPE_COPY.missingId };
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: LIVE_SCOPE_COPY.notSynced };
  if (!engineConfigured()) return { ok: false, message: LIVE_SCOPE_COPY.notConfigured };
  try {
    const raw = await engineGetJson(
      `/api/v1/projects/${engineContext.engineProjectId}/extraction/live-readiness`,
      engineContext,
    );
    const packet = normalizeLiveReadiness(raw);
    return {
      ok: true,
      message: isLiveReady(packet) ? "Live analysis is available." : LIVE_SCOPE_COPY.notEnabled,
      data: packet,
    };
  } catch {
    // Never leak the underlying engine/config error; fail closed.
    return { ok: false, message: LIVE_SCOPE_COPY.notEnabled };
  }
}

/**
 * Staff-only: explicitly start ONE live GPT-5.6 scope extraction for an enabled
 * trade on an already-synced engine project.
 *
 * Fail-closed contract:
 *  - Requires staff auth, a synced engine project, and a configured engine.
 *  - Re-checks live readiness and refuses ("Live analysis is not enabled") when
 *    live GPT is not armed — it never silently falls back to the offline mock.
 *  - Validates the trade against the server-fetched enabled-trade allowlist.
 *  - Posts a fixed, explicit payload (live provider on, force off, dry_run off,
 *    no caller-supplied sheet ids) and returns only a sanitized run status/id.
 *  - Scope items/evidence created by the run remain pending/blocked human
 *    review; this action approves, prices, delivers, and messages nothing.
 */
export async function startLiveScopeExtraction(
  projectId: string,
  tradeCode: string,
): Promise<AutomationActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: LIVE_SCOPE_COPY.missingId };
  const engineContext = await getEngineProjectContext(projectId);
  if (!engineContext) return { ok: false, message: LIVE_SCOPE_COPY.notSynced };
  if (!engineConfigured()) return { ok: false, message: LIVE_SCOPE_COPY.notConfigured };

  // Re-fetch readiness server-side so the run cannot be started against a stale
  // client view, and so the trade is validated against the authoritative list.
  let packet;
  try {
    packet = normalizeLiveReadiness(
      await engineGetJson(
        `/api/v1/projects/${engineContext.engineProjectId}/extraction/live-readiness`,
        engineContext,
      ),
    );
  } catch {
    return { ok: false, message: LIVE_SCOPE_COPY.notEnabled };
  }

  if (!isLiveReady(packet)) return { ok: false, message: LIVE_SCOPE_COPY.notEnabled };

  const trade = resolveEnabledTrade(tradeCode, packet.enabledTrades);
  if (!trade) return { ok: false, message: LIVE_SCOPE_COPY.tradeNotEnabled };

  try {
    const raw = await enginePostJson(
      `/api/v1/projects/${engineContext.engineProjectId}/trades/${trade}/extractions`,
      buildLiveScopeExtractionPayload(),
      engineContext,
    );
    // Sanitize the untrusted engine response, then validate it against the exact
    // expected live-start contract BEFORE reporting success or revalidating. An
    // off-contract / malformed / mismatched-trade response fails closed to the
    // fixed failure copy with no data — never a false "started" claim.
    const run = sanitizeLiveExtractionRun(raw);
    if (!isExpectedLiveExtractionRun(run, trade)) {
      return { ok: false, message: LIVE_SCOPE_COPY.failure };
    }
    revalidatePath(`/admin/projects/${projectId}`);
    return { ok: true, message: LIVE_SCOPE_COPY.success, data: run };
  } catch {
    // Do not surface provider raw payloads, credentials, paths, or internal
    // errors — return fixed safe failure copy only.
    return { ok: false, message: LIVE_SCOPE_COPY.failure };
  }
}
