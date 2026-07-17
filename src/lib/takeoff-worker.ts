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
 * Fixed, safe proof-path defaults for the create-job contract. The live worker
 * requires trade/scope_category/idempotency_key on every job; for the current
 * internal proof pathway these are constant. They are applied server-side only
 * and are never chosen by the browser.
 */
const DEFAULT_TAKEOFF_TRADE = "electrical";
const DEFAULT_TAKEOFF_SCOPE_CATEGORY = "ev_charging";
const DEFAULT_TAKEOFF_CONDITION = "RUNTIME-LINE";
const DEFAULT_TAKEOFF_DESCRIPTION = "Public C011 measured conduit line";
/** Defaults for the scale-confirmation contract (scale_source/scale_label are required). */
const DEFAULT_SCALE_SOURCE = "portal-manual";
const DEFAULT_SCALE_LABEL = "portal-confirmed-scale";

/**
 * Create-job input. The worker resolves the document strictly server-side from
 * the project row (see docs: `document_id == project_id` for this slice). The
 * caller passes ids/page/operation only — never a path. Trade/scope/condition
 * and the idempotency key fall back to fixed proof defaults when omitted.
 */
export interface CreateTakeoffJobInput {
  projectId: string;
  documentId: string;
  page: number;
  operation: TakeoffWorkerOperation;
  trade?: string;
  scopeCategory?: string;
  condition?: string;
  defaultDescription?: string;
  idempotencyKey?: string;
  requestedBy?: string;
}

export interface ConfirmScaleInput {
  sheetId: string;
  // Maps to the worker's `page_number` (>= 1).
  page: number;
  // Deterministic scale metadata: units_per_px plus the source/label the worker
  // requires. No plan pixels, no path.
  unitsPerPx: number;
  scaleSource?: string;
  scaleLabel?: string;
}

export interface MeasureLineInput {
  sheetId?: string;
  points: Array<[number, number]>;
  condition?: string;
}

/**
 * Normalized worker job response. The live worker wraps the job row as
 * `{ job, created }` (create) or `{ job }` (status/confirm/measure); we lift
 * `job_id`/`status` to the top level so callers keep the flat shape while the
 * full row stays available under `job`.
 */
export interface TakeoffJobResponse {
  job_id: string;
  status: string;
  created?: boolean;
  job: Record<string, unknown>;
}

export interface TakeoffArtifactsResponse {
  job_id: string;
  artifacts: Array<Record<string, unknown>>;
}

/** Raw `{ job, created }`/`{ job }` envelope returned by the live worker. */
interface WorkerJobEnvelope {
  job?: Record<string, unknown> | null;
  created?: boolean;
}

/** Lift `job_id`/`status` out of the worker's `{ job }` envelope to the top level. */
function normalizeJobResponse(payload: WorkerJobEnvelope): TakeoffJobResponse {
  const row = (payload?.job ?? {}) as Record<string, unknown>;
  const jobId = typeof row.job_id === "string" ? row.job_id : row.job_id != null ? String(row.job_id) : "";
  const status = typeof row.status === "string" ? row.status : row.status != null ? String(row.status) : "";
  const normalized: TakeoffJobResponse = { job_id: jobId, status, job: row };
  if (typeof payload?.created === "boolean") normalized.created = payload.created;
  return normalized;
}

/** Create (or idempotently return) a worker takeoff job for a resolved document. */
export async function createTakeoffJob(
  context: TakeoffWorkerContext,
  input: CreateTakeoffJobInput,
): Promise<TakeoffJobResponse> {
  const projectId = assertSafePathSegment(input.projectId, "project id");
  const documentId = assertSafePathSegment(input.documentId, "document id");
  // Stable enough to exercise the worker's idempotent-create behaviour: the same
  // project/document/page/operation maps to the same key.
  const idempotencyKey =
    input.idempotencyKey?.trim() || `${projectId}:${documentId}:${input.page}:${input.operation}`;
  const envelope = await workerFetch<WorkerJobEnvelope>(
    "POST",
    "/internal/takeoff/jobs",
    {
      project_id: projectId,
      document_id: documentId,
      operation: input.operation,
      trade: input.trade ?? DEFAULT_TAKEOFF_TRADE,
      scope_category: input.scopeCategory ?? DEFAULT_TAKEOFF_SCOPE_CATEGORY,
      condition: input.condition ?? DEFAULT_TAKEOFF_CONDITION,
      default_description: input.defaultDescription ?? DEFAULT_TAKEOFF_DESCRIPTION,
      idempotency_key: idempotencyKey,
      requested_by: input.requestedBy ?? context.actorId,
    },
    context,
  );
  return normalizeJobResponse(envelope);
}

/** Poll the current status of a worker takeoff job. */
export async function getTakeoffJob(
  context: TakeoffWorkerContext,
  jobId: string,
): Promise<TakeoffJobResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  const envelope = await workerFetch<WorkerJobEnvelope>(
    "GET",
    `/internal/takeoff/jobs/${id}`,
    undefined,
    context,
  );
  return normalizeJobResponse(envelope);
}

/** Confirm the sheet scale before any measurement is attempted. */
export async function confirmScale(
  context: TakeoffWorkerContext,
  jobId: string,
  input: ConfirmScaleInput,
): Promise<TakeoffJobResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  const envelope = await workerFetch<WorkerJobEnvelope>(
    "POST",
    `/internal/takeoff/jobs/${id}/confirm-scale`,
    {
      sheet_id: input.sheetId,
      page_number: input.page,
      scale_source: input.scaleSource?.trim() || DEFAULT_SCALE_SOURCE,
      scale_label: input.scaleLabel?.trim() || DEFAULT_SCALE_LABEL,
      units_per_px: input.unitsPerPx,
    },
    context,
  );
  return normalizeJobResponse(envelope);
}

/** Run a linear (measure_line) takeoff on confirmed-scale geometry. */
export async function measureLine(
  context: TakeoffWorkerContext,
  jobId: string,
  input: MeasureLineInput,
): Promise<TakeoffJobResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  const body: Record<string, unknown> = { geometry: { points: input.points } };
  if (input.sheetId?.trim()) body.sheet_id = input.sheetId.trim();
  if (input.condition?.trim()) body.condition = input.condition.trim();
  const envelope = await workerFetch<WorkerJobEnvelope>(
    "POST",
    `/internal/takeoff/jobs/${id}/measure-line`,
    body,
    context,
  );
  return normalizeJobResponse(envelope);
}

/** Fetch artifact metadata (opaque ids/type/hash/size only; no storage paths). */
export async function getArtifacts(
  context: TakeoffWorkerContext,
  jobId: string,
): Promise<TakeoffArtifactsResponse> {
  const id = assertSafePathSegment(jobId, "job id");
  // The worker returns `{ artifacts }`; re-attach the (validated) job id so the
  // caller keeps a flat, self-describing response.
  const payload = await workerFetch<{ artifacts?: Array<Record<string, unknown>> | null }>(
    "GET",
    `/internal/takeoff/jobs/${id}/artifacts`,
    undefined,
    context,
  );
  return { job_id: id, artifacts: Array.isArray(payload?.artifacts) ? payload.artifacts : [] };
}
