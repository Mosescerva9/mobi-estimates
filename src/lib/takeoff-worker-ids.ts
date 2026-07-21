/**
 * Pure, dependency-free resolution of the worker job identifiers.
 *
 * The portal and the estimating engine keep SEPARATE project ids: a Supabase
 * `projects` row has its own portal `id`, plus an `engine_project_id` that is the
 * project's identity inside the engine/worker (set once the project is sent to
 * the engine). The OpenTakeoff worker resolves its document strictly from the
 * ENGINE project id — for this single-document slice `document_id == project_id`,
 * both being the engine id. Sending the portal id to the worker resolves the
 * wrong (or no) document.
 *
 * This module is intentionally free of server-only imports so it can be unit
 * tested directly. `takeoff-actions.ts` uses it to fail closed when a project has
 * no valid engine id, and to send the engine id (never the portal id) to the
 * worker for both `project_id` and `document_id`.
 */

// The engine mints project ids as UUIDs. Accept a canonical UUID only, so an
// absent/blank/malformed value fails closed instead of being sent as-is.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** True when `value` is a well-formed engine project id (a UUID). */
export function isValidEngineProjectId(value: string | null | undefined): boolean {
  return typeof value === "string" && UUID_RE.test(value.trim());
}

export interface WorkerJobIds {
  /** Sent to the worker as both project_id and document_id (the engine id). */
  projectId: string;
  documentId: string;
}

/**
 * Resolve the ids the worker call must carry. The engine project id is used for
 * BOTH the worker `project_id` and `document_id`; the portal project id is never
 * sent to the worker (it is only used for portal-side authorization/lookup).
 *
 * Fails closed (throws) when the engine project id is absent or malformed — the
 * portal id is never silently substituted.
 */
export function resolveWorkerJobIds(input: {
  portalProjectId: string;
  engineProjectId: string | null | undefined;
}): WorkerJobIds {
  const engineProjectId = input.engineProjectId?.trim() ?? "";
  if (!isValidEngineProjectId(engineProjectId)) {
    throw new Error(
      "Project has no valid engine_project_id; it must be sent to the estimating engine before any worker call.",
    );
  }
  return { projectId: engineProjectId, documentId: engineProjectId };
}
