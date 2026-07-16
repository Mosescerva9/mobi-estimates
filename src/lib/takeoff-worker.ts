/**
 * Server-only client for the deployable OpenTakeoff worker API.
 *
 * The worker runs as a separate authenticated service on the VPS
 * (`/internal/takeoff/*`, behind Caddy) and is reachable at
 * MOBI_WORKER_API_URL, gated by a shared secret in MOBI_WORKER_API_KEY.
 *
 * SECURITY CONTRACT — read before importing:
 *   - NEVER import this module from a client component and NEVER expose either
 *     env value with a NEXT_PUBLIC_ prefix. The browser must never receive or
 *     reference the worker secret.
 *   - The worker secret (X-API-Key) and the tenant/company/actor identity
 *     headers are built HERE, from server-supplied context only. The browser
 *     never chooses tenant identity and never supplies raw headers.
 *   - This client accepts operation geometry/sheet/page/scale inputs only. It
 *     does NOT accept a `headers` bag, an api key, tenant headers, or a
 *     filesystem path from any caller. Job ids are validated as opaque path
 *     segments so a caller cannot smuggle a traversal or a second path.
 *
 * See docs/mvp/opentakeoff-worker-api.md for the worker API surface.
 */

// Read lazily (not captured at import) so the secret is only touched at call
// time on the server, and so config can be toggled per environment/test.
function workerBaseUrl(): string | undefined {
  return process.env.MOBI_WORKER_API_URL;
}
function workerApiKey(): string | undefined {
  return process.env.MOBI_WORKER_API_KEY;
}

export type TakeoffActorRole = "estimator" | "reviewer" | "admin";

const TAKEOFF_ACTOR_ROLES: readonly TakeoffActorRole[] = ["estimator", "reviewer", "admin"];

/**
 * Server-resolved worker call context. Every field is derived server-side:
 * tenant/company from the Supabase project row, and the actor from the
 * authenticated staff session. None of these come from the browser.
 */
export interface TakeoffWorkerContext {
  tenantId: string;
  companyId: string;
  actorRole: TakeoffActorRole;
  actorId: string;
}

const MALFORMED_IDENTITY_SENTINELS = new Set(["none", "null", "undefined", "nan"]);

function normalizeIdentityComponent(value: string | null | undefined): string {
  const normalized = value?.trim() ?? "";
  if (!normalized) return "";
  if (MALFORMED_IDENTITY_SENTINELS.has(normalized.toLowerCase())) return "";
  return normalized;
}

/** True when both the worker URL and API key are configured on this deployment. */
export function workerConfigured(): boolean {
  return Boolean(workerBaseUrl() && workerApiKey());
}

function requireWorkerContext(context: TakeoffWorkerContext | null | undefined): TakeoffWorkerContext {
  const tenantId = normalizeIdentityComponent(context?.tenantId);
  const companyId = normalizeIdentityComponent(context?.companyId);
  const actorId = normalizeIdentityComponent(context?.actorId);
  const actorRole = context?.actorRole;
  if (!tenantId || !companyId) {
    throw new Error("Takeoff worker tenant context is required for worker calls.");
  }
  if (!actorId) {
    throw new Error("Takeoff worker actor id is required for worker calls.");
  }
  if (!actorRole || !TAKEOFF_ACTOR_ROLES.includes(actorRole)) {
    throw new Error("Takeoff worker actor role must be estimator, reviewer, or admin.");
  }
  return { tenantId, companyId, actorId, actorRole };
}

/**
 * Build the ONLY headers the worker call may carry. Nothing else is forwarded —
 * there is no caller-supplied header bag. The secret and identity come from the
 * server-resolved context, never from the browser.
 */
function workerHeaders(context: TakeoffWorkerContext): Record<string, string> {
  return {
    "X-API-Key": workerApiKey()!,
    "X-Mobi-Tenant-Id": context.tenantId,
    "X-Mobi-Company-Id": context.companyId,
    "X-Mobi-Actor-Role": context.actorRole,
    "X-Mobi-Actor-Id": context.actorId,
  };
}

/**
 * Validate an opaque worker path segment (e.g. a job id). Rejects anything that
 * could smuggle a path/traversal so a caller can never turn a job id into a
 * filesystem path or a second URL path.
 */
function assertSafePathSegment(value: string, label: string): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) throw new Error(`Takeoff worker ${label} is required.`);
  if (!/^[A-Za-z0-9_-]+$/.test(trimmed)) {
    throw new Error(`Takeoff worker ${label} must be an opaque id (no paths).`);
  }
  return trimmed;
}

async function workerErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    // Engine envelope: { error: { code, message } }; FastAPI default: { detail }.
    return body?.error?.message || body?.detail || `Takeoff worker returned ${res.status}.`;
  } catch {
    return `Takeoff worker returned ${res.status}.`;
  }
}

async function workerFetch<T>(
  method: "GET" | "POST",
  path: string,
  body: unknown | undefined,
  context: TakeoffWorkerContext,
): Promise<T> {
  if (!workerConfigured()) {
    throw new Error("The takeoff worker API is not configured on this deployment.");
  }
  const workerContext = requireWorkerContext(context);
  const headers: Record<string, string> = workerHeaders(workerContext);
  const init: RequestInit = { method, headers, cache: "no-store" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${workerBaseUrl()}${path}`, init);
  if (!res.ok) {
    throw new Error(await workerErrorMessage(res));
  }
  return (await res.json()) as T;
}

// --- Worker request/response shapes (operation inputs only) ---

export type TakeoffWorkerOperation = "measure_line" | "measure_polygon";

/**
 * Create-job input. The worker resolves the document strictly server-side from
 * the project row (see docs: `document_id == project_id` for this slice). The
 * caller passes ids/page/operation only — never a path.
 */
export interface CreateTakeoffJobInput {
  projectId: string;
  documentId: string;
  page: number;
  operation: TakeoffWorkerOperation;
}

export interface ConfirmScaleInput {
  sheetId: string;
  page: number;
  // Deterministic scale metadata, e.g. units_per_px, matching the worker's
  // scale-confirmation contract. No plan pixels, no path.
  unitsPerPx: number;
  scaleLabel?: string;
}

export interface MeasureLineInput {
  sheetId: string;
  page: number;
  points: Array<[number, number]>;
}

export interface TakeoffJobResponse {
  job_id: string;
  status: string;
  project_id?: string;
  document_id?: string;
  page?: number;
  operation?: string;
}

export interface TakeoffArtifactMeta {
  artifact_id: string;
  type: string;
  hash: string;
  size_bytes: number;
  signed_url: string | null;
  expires_at: string | null;
}

export interface TakeoffArtifactsResponse {
  job_id: string;
  status: string;
  artifacts: TakeoffArtifactMeta[];
}

/** Create (or idempotently return) a worker takeoff job for a resolved document. */
export async function createTakeoffJob(
  context: TakeoffWorkerContext,
  input: CreateTakeoffJobInput,
): Promise<TakeoffJobResponse> {
  const projectId = assertSafePathSegment(input.projectId, "project id");
  const documentId = assertSafePathSegment(input.documentId, "document id");
  return workerFetch<TakeoffJobResponse>(
    "POST",
    "/internal/takeoff/jobs",
    {
      project_id: projectId,
      document_id: documentId,
      page: input.page,
      operation: input.operation,
    },
    context,
  );
}

/** Poll the current status of a worker takeoff job. */
export async function getTakeoffJob(
  context: TakeoffWorkerContext,
  jobId: string,
): Promise<TakeoffJobResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  return workerFetch<TakeoffJobResponse>("GET", `/internal/takeoff/jobs/${id}`, undefined, context);
}

/** Confirm the sheet scale before any measurement is attempted. */
export async function confirmScale(
  context: TakeoffWorkerContext,
  jobId: string,
  input: ConfirmScaleInput,
): Promise<TakeoffJobResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  return workerFetch<TakeoffJobResponse>(
    "POST",
    `/internal/takeoff/jobs/${id}/confirm-scale`,
    {
      sheet_id: input.sheetId,
      page: input.page,
      units_per_px: input.unitsPerPx,
      scale_label: input.scaleLabel,
    },
    context,
  );
}

/** Run a linear (measure_line) takeoff on confirmed-scale geometry. */
export async function measureLine(
  context: TakeoffWorkerContext,
  jobId: string,
  input: MeasureLineInput,
): Promise<TakeoffJobResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  return workerFetch<TakeoffJobResponse>(
    "POST",
    `/internal/takeoff/jobs/${id}/measure-line`,
    {
      sheet_id: input.sheetId,
      page: input.page,
      points: input.points,
    },
    context,
  );
}

/** Fetch artifact metadata (opaque ids/type/hash/size only; no storage paths). */
export async function getArtifacts(
  context: TakeoffWorkerContext,
  jobId: string,
): Promise<TakeoffArtifactsResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  return workerFetch<TakeoffArtifactsResponse>(
    "GET",
    `/internal/takeoff/jobs/${id}/artifacts`,
    undefined,
    context,
  );
}
