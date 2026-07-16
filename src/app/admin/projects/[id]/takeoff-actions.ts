"use server";

/**
 * Staff-only server actions for the live OpenTakeoff worker pathway.
 *
 * SECURITY POSTURE — every action here:
 *   1. revalidates the current staff user server-side via requireStaff();
 *   2. resolves tenant/company/engine identity from the Supabase project row
 *      through the service-role admin client — the browser never chooses the
 *      tenant and never supplies the worker api key or identity headers;
 *   3. requires project.engine_project_id before making any worker call
 *      (a project must have been sent to the engine first);
 *   4. forwards only operation geometry/sheet/page/scale inputs to the worker.
 *
 * NOTE ON TENANT MAPPING: for the current portal convention we use the
 * project's company_id as BOTH tenantId and companyId. This mirrors the engine
 * client (see src/lib/engine.ts) and must be replaced with a real tenant→company
 * mapping before any customer-facing launch of this pathway.
 */

import { requireStaff } from "@/lib/auth";
import { createAdminClient } from "@/lib/supabase/admin";
import {
  confirmScale,
  createTakeoffJob,
  getArtifacts,
  getTakeoffJob,
  measureLine,
  workerConfigured,
  type TakeoffActorRole,
  type TakeoffWorkerContext,
  type TakeoffWorkerOperation,
} from "@/lib/takeoff-worker";

export interface TakeoffWorkerActionResult {
  ok: boolean;
  message: string;
  data?: unknown;
}

const WORKER_OPERATIONS: readonly TakeoffWorkerOperation[] = ["measure_line", "measure_polygon"];

/**
 * Resolve the server-owned worker context for a project. Returns an error
 * result string when the project cannot host a worker call so callers can fail
 * closed with a staff-facing message rather than a thrown 500.
 */
async function resolveWorkerContext(
  projectId: string,
  staffRole: TakeoffActorRole,
  staffId: string,
): Promise<{ context: TakeoffWorkerContext; documentId: string } | { error: string }> {
  if (!projectId) return { error: "Missing project id." };

  const admin = createAdminClient();
  const { data } = await admin
    .from("projects")
    .select("id, company_id, engine_project_id")
    .eq("id", projectId)
    .maybeSingle();

  if (!data) return { error: "Project not found." };
  if (!data.company_id) return { error: "Project has no company; cannot resolve tenant." };
  if (!data.engine_project_id) {
    return { error: "Project has not been sent to the estimating engine yet." };
  }

  // company_id doubles as tenantId under the current portal convention (see note above).
  const context: TakeoffWorkerContext = {
    tenantId: data.company_id,
    companyId: data.company_id,
    actorRole: staffRole,
    actorId: staffId,
  };
  // Worker doc-resolution slice: document_id == project_id (see worker API doc).
  return { context, documentId: data.id };
}

/** Staff-only: create (or idempotently return) a live worker takeoff job. */
export async function createLiveTakeoffJob(
  projectId: string,
  input: { page: number; operation: TakeoffWorkerOperation },
): Promise<TakeoffWorkerActionResult> {
  const staff = await requireStaff();
  if (!workerConfigured()) {
    return { ok: false, message: "The takeoff worker API is not configured on this deployment." };
  }
  if (!WORKER_OPERATIONS.includes(input.operation)) {
    return { ok: false, message: "Unsupported worker operation." };
  }
  if (!Number.isInteger(input.page) || input.page < 1) {
    return { ok: false, message: "Page must be a positive integer." };
  }

  const resolved = await resolveWorkerContext(projectId, staff.role as TakeoffActorRole, staff.id);
  if ("error" in resolved) return { ok: false, message: resolved.error };

  try {
    const data = await createTakeoffJob(resolved.context, {
      projectId,
      documentId: resolved.documentId,
      page: input.page,
      operation: input.operation,
    });
    return { ok: true, message: `Worker job ${data.job_id} is ${data.status}.`, data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not create worker job." };
  }
}

/** Staff-only: poll a live worker takeoff job's status. */
export async function getLiveTakeoffJob(
  projectId: string,
  jobId: string,
): Promise<TakeoffWorkerActionResult> {
  const staff = await requireStaff();
  const resolved = await resolveWorkerContext(projectId, staff.role as TakeoffActorRole, staff.id);
  if ("error" in resolved) return { ok: false, message: resolved.error };
  try {
    const data = await getTakeoffJob(resolved.context, jobId);
    return { ok: true, message: `Worker job ${data.job_id} is ${data.status}.`, data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load worker job." };
  }
}

/** Staff-only: confirm sheet scale on a live worker takeoff job. */
export async function confirmLiveTakeoffScale(
  projectId: string,
  jobId: string,
  input: { sheetId: string; page: number; unitsPerPx: number; scaleLabel?: string },
): Promise<TakeoffWorkerActionResult> {
  const staff = await requireStaff();
  if (!Number.isFinite(input.unitsPerPx) || input.unitsPerPx <= 0) {
    return { ok: false, message: "Scale (units_per_px) must be a positive number." };
  }
  const resolved = await resolveWorkerContext(projectId, staff.role as TakeoffActorRole, staff.id);
  if ("error" in resolved) return { ok: false, message: resolved.error };
  try {
    const data = await confirmScale(resolved.context, jobId, input);
    return { ok: true, message: `Scale confirmed; job is ${data.status}.`, data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not confirm scale." };
  }
}

/** Staff-only: run a linear (measure_line) worker measurement. */
export async function measureLiveTakeoffLine(
  projectId: string,
  jobId: string,
  input: {
    sheetId: string;
    page: number;
    points: Array<[number, number]>;
  },
): Promise<TakeoffWorkerActionResult> {
  const staff = await requireStaff();
  const points = Array.isArray(input.points) ? input.points : [];
  const geometryValid =
    points.length >= 2 && points.every((p) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite));
  if (!geometryValid) {
    return { ok: false, message: "A line needs at least two valid [x, y] points." };
  }
  const resolved = await resolveWorkerContext(projectId, staff.role as TakeoffActorRole, staff.id);
  if ("error" in resolved) return { ok: false, message: resolved.error };
  try {
    const data = await measureLine(resolved.context, jobId, input);
    return { ok: true, message: `Measurement submitted; job is ${data.status}.`, data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not run measurement." };
  }
}

/** Staff-only: fetch artifact metadata for a live worker takeoff job. */
export async function getLiveTakeoffArtifacts(
  projectId: string,
  jobId: string,
): Promise<TakeoffWorkerActionResult> {
  const staff = await requireStaff();
  const resolved = await resolveWorkerContext(projectId, staff.role as TakeoffActorRole, staff.id);
  if ("error" in resolved) return { ok: false, message: resolved.error };
  try {
    const data = await getArtifacts(resolved.context, jobId);
    return { ok: true, message: "Artifact metadata loaded.", data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not load artifacts." };
  }
}
