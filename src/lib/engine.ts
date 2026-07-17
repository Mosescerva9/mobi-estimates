/**
 * Server-only client for the Mobi estimating engine (FastAPI service).
 *
 * The engine runs as a separate service (see infra: Caddy -> uvicorn on the
 * VPS) and is reachable at MOBI_ENGINE_BASE_URL, gated by a shared secret in
 * MOBI_ENGINE_API_KEY. Never import this from a client component and never
 * expose either value with a NEXT_PUBLIC_ prefix.
 */

const BASE_URL = process.env.MOBI_ENGINE_BASE_URL;
const API_KEY = process.env.MOBI_ENGINE_API_KEY;

export interface EngineTenantContext {
  tenantId: string;
  companyId: string;
}

const MALFORMED_TENANT_IDENTITY_SENTINELS = new Set(["none", "null", "undefined", "nan"]);

function normalizeTenantIdentityComponent(value: string | null | undefined): string {
  const normalized = value?.trim() ?? "";
  if (!normalized) return "";
  if (MALFORMED_TENANT_IDENTITY_SENTINELS.has(normalized.toLowerCase())) return "";
  return normalized;
}

function requireEngineTenantContext(context: EngineTenantContext | null | undefined): EngineTenantContext {
  const tenantId = normalizeTenantIdentityComponent(context?.tenantId);
  const companyId = normalizeTenantIdentityComponent(context?.companyId);
  if (!tenantId || !companyId) {
    throw new Error("Engine tenant context is required for project-scoped engine calls.");
  }
  return { tenantId, companyId };
}

function engineHeaders(context: EngineTenantContext): Record<string, string> {
  return {
    "X-API-Key": API_KEY!,
    "X-Mobi-Tenant-Id": context.tenantId,
    "X-Mobi-Company-Id": context.companyId,
  };
}

/** True when both the engine URL and API key are configured. */
export function engineConfigured(): boolean {
  return Boolean(BASE_URL && API_KEY);
}

/** Mirror of the engine's ProjectStatusResponse (app/schemas.py). */
export interface EngineProject {
  project_id: string;
  name: string;
  status: string;
  original_file_name: string | null;
  page_count: number;
  file_sha256: string | null;
  file_size_bytes: number;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}

async function engineErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    // Engine envelope: { error: { code, message } }; FastAPI default: { detail }.
    return body?.error?.message || body?.detail || `Engine returned ${res.status}.`;
  } catch {
    return `Engine returned ${res.status}.`;
  }
}

export async function engineGetJson<T>(path: string, context: EngineTenantContext): Promise<T> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const tenantContext = requireEngineTenantContext(context);
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "GET",
    headers: engineHeaders(tenantContext),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as T;
}

export async function enginePostJson<T>(path: string, body: unknown | undefined, context: EngineTenantContext): Promise<T> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const tenantContext = requireEngineTenantContext(context);
  const headers: Record<string, string> = engineHeaders(tenantContext);
  const init: RequestInit = { method: "POST", headers, cache: "no-store" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as T;
}

/**
 * Upload a PDF plan set to the engine, creating an engine-side project record.
 * The engine validates and stores the PDF; it does not run takeoff/pricing here.
 */
export async function engineUploadPlan(opts: {
  projectName: string;
  contractorName?: string | null;
  file: Blob;
  fileName: string;
  context: EngineTenantContext;
}): Promise<EngineProject> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const tenantContext = requireEngineTenantContext(opts.context);

  const form = new FormData();
  form.append("project_name", opts.projectName);
  if (opts.contractorName) form.append("contractor_name", opts.contractorName);
  form.append("plan", opts.file, opts.fileName);

  const res = await fetch(`${BASE_URL}/api/v1/projects/upload`, {
    method: "POST",
    headers: engineHeaders(tenantContext),
    body: form,
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as EngineProject;
}

/**
 * Mirror of the engine's SheetSummary (app/processing_schemas.py). This is the
 * REAL per-sheet register the OpenTakeoff worker's confirm-scale call requires
 * a `sheet_id` from (see docs/mvp/opentakeoff-worker-api.md): a `sheet_id`
 * must reference a row here whose `pdf_page_number` matches the confirmed
 * page, so the takeoff workbench lists these — not the portal's own
 * (currently unpopulated) estimate_job_documents.sheet_index — to offer real,
 * measurable sheet identities.
 */
export interface EngineSheetSummary {
  sheet_id: string;
  pdf_page_number: number;
  detected_sheet_number: string | null;
  verified_sheet_number: string | null;
  detected_sheet_title: string | null;
  verified_sheet_title: string | null;
  text_layer_quality: string;
  processing_status: string;
  review_status: string;
}

export interface EngineSheetListResponse {
  items: EngineSheetSummary[];
  total: number;
  limit: number;
  offset: number;
}

/** List the engine's processed sheets for a synced project (real sheet_id/page/title register). */
export async function engineListSheets(
  engineProjectId: string,
  context: EngineTenantContext,
): Promise<EngineSheetListResponse> {
  return engineGetJson<EngineSheetListResponse>(
    `/api/v1/projects/${engineProjectId}/sheets?limit=200`,
    context,
  );
}

/**
 * Fetch a rendered sheet raster (PNG) from the engine. Returns null on 404
 * (not processed yet) so callers can show a friendly "not available" state
 * instead of a raw error. Binary only — never a filesystem path.
 */
export async function engineFetchSheetImage(
  engineProjectId: string,
  sheetId: string,
  variant: "image" | "thumbnail",
  context: EngineTenantContext,
): Promise<{ contentType: string; bytes: ArrayBuffer } | null> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const tenantContext = requireEngineTenantContext(context);
  const res = await fetch(
    `${BASE_URL}/api/v1/projects/${engineProjectId}/sheets/${sheetId}/${variant}`,
    { method: "GET", headers: engineHeaders(tenantContext), cache: "no-store" },
  );
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  const contentType = res.headers.get("content-type") || "image/png";
  const bytes = await res.arrayBuffer();
  return { contentType, bytes };
}

/** Fetch the current status of an engine-side project. */
export async function engineGetStatus(engineProjectId: string, context: EngineTenantContext): Promise<EngineProject> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const tenantContext = requireEngineTenantContext(context);
  const res = await fetch(`${BASE_URL}/api/v1/projects/${engineProjectId}/status`, {
    method: "GET",
    headers: engineHeaders(tenantContext),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as EngineProject;
}
