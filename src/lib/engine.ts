/**
 * Server-only client for the Mobi estimating engine (FastAPI service).
 *
 * The engine runs as a separate service (see infra: Caddy -> uvicorn on the
 * VPS) and is reachable at MOBI_ENGINE_BASE_URL, gated by a shared secret in
 * MOBI_ENGINE_API_KEY. Never import this from a client component and never
 * expose either value with a NEXT_PUBLIC_ prefix.
 */

import { z } from "zod";

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

/** One source PDF's identity + packet page range (mirror of app/services/packet_assembly.py). */
export interface EnginePacketManifestSource {
  order: number;
  project_file_id: string | null;
  original_filename: string;
  storage_path: string | null;
  source_sha256: string;
  source_bytes: number;
  source_page_count: number;
  combined_page_start: number;
  combined_page_end: number;
}

/** Engine-authored manifest describing an assembled multi-document packet. */
export interface EnginePacketManifest {
  schema_version: string;
  packet: {
    sha256: string;
    bytes: number;
    page_count: number;
    source_count: number;
  };
  sources: EnginePacketManifestSource[];
}

export interface EnginePacketProject extends EngineProject {
  /**
   * A packet project ALWAYS has stored bytes, so unlike the base project its
   * content hash is never null — `packetResponseSchema` enforces a lowercase
   * 64-hex digest. Narrowed here so callers that bind the packet identity (the
   * manifest-save RPC) get that guarantee from the type, not a cast.
   */
  file_sha256: string;
  packet_manifest: EnginePacketManifest;
  /** True when the engine reused an existing identical packet project (retry-safe). */
  idempotent_reuse?: boolean;
}

/** One accepted source PDF to include in an assembled engine packet. */
export interface EnginePacketSource {
  file: Blob;
  fileName: string;
  projectFileId?: string | null;
  storagePath?: string | null;
  order: number;
  /** Lowercase 64-hex SHA-256 the portal computed for this exact source blob. */
  declaredSha256?: string | null;
  /** Byte length the portal read for this exact source blob. */
  bytes?: number | null;
}

const LOWER_SHA256 = /^[0-9a-f]{64}$/;

const packetSourceSchema = z.object({
  order: z.number().int().nonnegative(),
  project_file_id: z.string().nullable(),
  original_filename: z.string().min(1),
  storage_path: z.string().nullable(),
  source_sha256: z.string().regex(LOWER_SHA256, "source_sha256 must be lowercase 64-hex"),
  source_bytes: z.number().int().nonnegative(),
  source_page_count: z.number().int().positive(),
  combined_page_start: z.number().int().positive(),
  combined_page_end: z.number().int().positive(),
});

const packetManifestSchema = z.object({
  schema_version: z.string().min(1),
  packet: z.object({
    sha256: z.string().regex(LOWER_SHA256, "packet.sha256 must be lowercase 64-hex"),
    // A packet always has real content, so its byte count must be a positive,
    // whole, safe integer. `.safe()` rejects a value beyond Number.MAX_SAFE_INTEGER,
    // where integral arithmetic and equality stop being trustworthy; `.int()`
    // rejects a fractional value that would otherwise round into agreement with
    // the response/RPC byte count.
    bytes: z.number().int().positive().safe(),
    page_count: z.number().int().positive(),
    source_count: z.number().int().positive(),
  }),
  sources: z.array(packetSourceSchema).min(1),
});

const packetResponseSchema = z.object({
  project_id: z.string().min(1),
  name: z.string(),
  status: z.string().min(1),
  original_file_name: z.string().nullable(),
  page_count: z.number().int().positive(),
  file_sha256: z.string().regex(LOWER_SHA256),
  // The stored engine file IS the packet, so its size must be a positive, whole,
  // safe integer — never zero (an empty stored file), never fractional, never
  // beyond safe-integer precision.
  file_size_bytes: z.number().int().positive().safe(),
  created_at: z.string(),
  updated_at: z.string(),
  error_message: z.string().nullable(),
  portal_project_id: z.string().min(1),
  idempotent_reuse: z.boolean().optional(),
  packet_manifest: packetManifestSchema,
});

/**
 * Strictly validate the engine's packet response at runtime against the EXACT
 * set of sources the portal submitted, before any DB write. This is the response
 * trust boundary: a manifest that does not reproduce the submitted source set
 * (ids/paths/names/hashes/bytes/order), the expected packet identity, the portal
 * project id, or (when known) the expected existing engine id is rejected so no
 * link is ever persisted from unverified engine data. Exported for unit testing.
 */
export function validateEnginePacketResponse(
  raw: unknown,
  submitted: EnginePacketSource[],
  opts: { portalProjectId: string; expectedEngineProjectId?: string | null },
): EnginePacketProject {
  const parsed = packetResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(`Engine packet response failed validation: ${parsed.error.issues[0]?.message ?? "invalid shape"}.`);
  }
  const body = parsed.data;
  const { packet, sources } = body.packet_manifest;

  if (body.portal_project_id !== opts.portalProjectId) {
    throw new Error("Engine response portal_project_id does not match the submitted portal project.");
  }
  if (opts.expectedEngineProjectId && body.project_id !== opts.expectedEngineProjectId) {
    throw new Error("Engine returned a project id that does not match the expected existing engine link.");
  }
  if (body.file_sha256 !== packet.sha256) {
    throw new Error("Engine response file_sha256 does not equal the packet manifest sha256.");
  }
  if (body.page_count !== packet.page_count) {
    throw new Error("Engine response page_count does not equal the packet manifest page count.");
  }
  // The stored engine file and the manifest must agree on the packet's byte
  // count exactly. Without this the byte count is unbound end to end: the RPC
  // would persist a manifest whose declared size never had to match the bytes
  // the engine actually stored.
  if (body.file_size_bytes !== packet.bytes) {
    throw new Error("Engine response file_size_bytes does not equal the packet manifest byte count.");
  }
  if (packet.source_count !== submitted.length || sources.length !== submitted.length) {
    throw new Error("Engine packet source_count does not match the submitted source set size.");
  }

  // Order must be a contiguous 0..n-1 permutation; pages must sum and cover.
  const orders = sources.map((s) => s.order);
  const expectedOrders = new Set(submitted.map((_, i) => i));
  if (orders.length !== expectedOrders.size || orders.some((o) => !expectedOrders.has(o))) {
    throw new Error("Engine packet manifest orders are not a contiguous 0..n-1 set.");
  }
  const byOrder = new Map(sources.map((s) => [s.order, s]));
  const submittedByOrder = new Map(submitted.map((s) => [s.order, s]));

  let expectedStart = 1;
  let summedPages = 0;
  for (let order = 0; order < submitted.length; order += 1) {
    const returned = byOrder.get(order)!;
    const sub = submittedByOrder.get(order);
    if (!sub) {
      throw new Error("Submitted source ordering is not a contiguous 0..n-1 set.");
    }
    if ((returned.project_file_id ?? null) !== (sub.projectFileId ?? null)) {
      throw new Error(`Engine manifest source project_file_id mismatch at order ${order}.`);
    }
    if ((returned.storage_path ?? null) !== (sub.storagePath ?? null)) {
      throw new Error(`Engine manifest source storage_path mismatch at order ${order}.`);
    }
    if (returned.original_filename !== sub.fileName) {
      throw new Error(`Engine manifest source filename mismatch at order ${order}.`);
    }
    if (sub.declaredSha256 && returned.source_sha256 !== sub.declaredSha256.toLowerCase()) {
      throw new Error(`Engine manifest source sha256 mismatch at order ${order}.`);
    }
    if (typeof sub.bytes === "number" && returned.source_bytes !== sub.bytes) {
      throw new Error(`Engine manifest source byte count mismatch at order ${order}.`);
    }
    if (returned.combined_page_start !== expectedStart) {
      throw new Error(`Engine manifest source page range is not contiguous at order ${order}.`);
    }
    if (returned.combined_page_end < returned.combined_page_start) {
      throw new Error(`Engine manifest source page range is inverted at order ${order}.`);
    }
    summedPages += returned.source_page_count;
    if (returned.combined_page_end - returned.combined_page_start + 1 !== returned.source_page_count) {
      throw new Error(`Engine manifest source page span does not match its page count at order ${order}.`);
    }
    expectedStart = returned.combined_page_end + 1;
  }
  if (summedPages !== packet.page_count || expectedStart - 1 !== packet.page_count) {
    throw new Error("Engine manifest source pages do not sum to and cover the packet page count.");
  }

  return body as unknown as EnginePacketProject;
}

/**
 * Upload every accepted PDF for a portal project as ONE deterministic engine
 * packet, creating (or idempotently reusing) a single engine-side project keyed
 * on the immutable ``portalProjectId``. The engine merges the sources
 * server-side and returns a source manifest; the engine project's stored SHA-256
 * is the packet SHA-256, preserving the single-document + OpenTakeoff worker
 * identity contract. Ordering is deterministic and every source is included or
 * the whole upload fails closed. When ``expectedEngineProjectId`` is supplied
 * (a retry over an established link), the engine rejects a mismatch (409) rather
 * than replacing the link, and the response is validated to that id. The
 * response is strictly validated against the submitted source snapshot before
 * being returned, so callers never persist unverified engine data.
 */
export async function engineUploadPacket(opts: {
  projectName: string;
  portalProjectId: string;
  contractorName?: string | null;
  expectedEngineProjectId?: string | null;
  sources: EnginePacketSource[];
  context: EngineTenantContext;
}): Promise<EnginePacketProject> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  if (!opts.portalProjectId) {
    throw new Error("A portal project id is required to build an engine packet.");
  }
  if (opts.sources.length === 0) {
    throw new Error("At least one PDF plan file is required to build an engine packet.");
  }
  const tenantContext = requireEngineTenantContext(opts.context);

  const form = new FormData();
  form.append("project_name", opts.projectName);
  form.append("portal_project_id", opts.portalProjectId);
  if (opts.contractorName) form.append("contractor_name", opts.contractorName);
  if (opts.expectedEngineProjectId) {
    form.append("expected_engine_project_id", opts.expectedEngineProjectId);
  }
  const metadata = opts.sources.map((source) => ({
    project_file_id: source.projectFileId ?? null,
    storage_path: source.storagePath ?? null,
    order: source.order,
    declared_sha256: source.declaredSha256 ?? null,
  }));
  form.append("sources_metadata", JSON.stringify(metadata));
  for (const source of opts.sources) {
    form.append("plans", source.file, source.fileName);
  }

  const res = await fetch(`${BASE_URL}/api/v1/projects/upload-packet`, {
    method: "POST",
    headers: engineHeaders(tenantContext),
    body: form,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return validateEnginePacketResponse(await res.json(), opts.sources, {
    portalProjectId: opts.portalProjectId,
    expectedEngineProjectId: opts.expectedEngineProjectId,
  });
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

/** The engine's GET /sheets endpoint caps `limit` at 200 per request (app/routers_processing.py). */
export const ENGINE_SHEETS_PAGE_LIMIT = 200;

/**
 * Sane hard cap on the total number of sheets a project may page through. This
 * mirrors the engine's own ingestion cap (`ProcessingSettings.max_page_count`,
 * default 1000 — app/config.py): a project can never have more sheet rows than
 * pages it was allowed to ingest. Paging past this is treated as a malformed/
 * runaway response and fails closed rather than looping unbounded.
 */
export const ENGINE_SHEETS_MAX_TOTAL = 1000;

/** Minimal shape validation for one page of the engine's sheet list response. */
function isWellFormedSheetPage(raw: unknown): raw is EngineSheetListResponse {
  if (!raw || typeof raw !== "object") return false;
  const page = raw as Partial<EngineSheetListResponse>;
  return (
    Array.isArray(page.items) &&
    Number.isInteger(page.total) &&
    (page.total as number) >= 0 &&
    Number.isInteger(page.limit) &&
    (page.limit as number) >= 1 &&
    Number.isInteger(page.offset) &&
    (page.offset as number) >= 0 &&
    page.items.every(
      (item) =>
        item &&
        typeof item === "object" &&
        typeof (item as EngineSheetSummary).sheet_id === "string" &&
        (item as EngineSheetSummary).sheet_id.length > 0 &&
        Number.isInteger((item as EngineSheetSummary).pdf_page_number),
    )
  );
}

/**
 * Page through a sheet-list endpoint (bounded at `ENGINE_SHEETS_PAGE_LIMIT` per
 * request, following the engine's own `limit<=200` contract) and return every
 * item across the whole project, preserving the server's deterministic
 * `pdf_page_number ASC` ordering. `fetchPage` is injected so this pure loop is
 * unit-testable without a real network call.
 *
 * Fails closed (throws) rather than looping forever on:
 *  - a malformed page (wrong shape, non-integer total/limit/offset, malformed items);
 *  - a `total` that changes mid-pagination (non-deterministic backing data);
 *  - a `total` beyond `ENGINE_SHEETS_MAX_TOTAL` (runaway/unexpected project size);
 *  - a non-final page that returns zero items or fewer than `limit` items
 *    (non-progress: the walk would stall or silently skip sheets);
 *  - a duplicate `sheet_id` across pages (non-deterministic/overlapping pages).
 */
export async function fetchAllEngineSheets(
  fetchPage: (limit: number, offset: number) => Promise<unknown>,
): Promise<EngineSheetListResponse> {
  const items: EngineSheetSummary[] = [];
  const seen = new Set<string>();
  let offset = 0;
  let total: number | null = null;
  const maxIterations = Math.ceil(ENGINE_SHEETS_MAX_TOTAL / ENGINE_SHEETS_PAGE_LIMIT) + 1;

  for (let iteration = 0; iteration < maxIterations; iteration += 1) {
    const raw = await fetchPage(ENGINE_SHEETS_PAGE_LIMIT, offset);
    if (!isWellFormedSheetPage(raw)) {
      throw new Error("Engine sheet list page failed validation: malformed shape.");
    }
    if (raw.limit !== ENGINE_SHEETS_PAGE_LIMIT || raw.offset !== offset) {
      throw new Error("Engine sheet list page failed validation: unexpected limit/offset echo.");
    }
    // A page may never exceed the limit it was asked for. Without this, a server
    // returning oversized pages could hand back far more rows than the sane cap
    // below allows, since that cap is only checked against the declared `total`.
    if (raw.items.length > ENGINE_SHEETS_PAGE_LIMIT) {
      throw new Error("Engine sheet list page returned more items than the requested limit.");
    }
    if (total === null) {
      if (raw.total > ENGINE_SHEETS_MAX_TOTAL) {
        throw new Error(
          `Engine sheet list total (${raw.total}) exceeds the sane cap (${ENGINE_SHEETS_MAX_TOTAL}).`,
        );
      }
      total = raw.total;
    } else if (raw.total !== total) {
      throw new Error("Engine sheet list total changed mid-pagination.");
    }

    const isFinalPage = offset + raw.items.length >= total;
    if (!isFinalPage && raw.items.length < ENGINE_SHEETS_PAGE_LIMIT) {
      throw new Error("Engine sheet list page made non-progress: a non-final page returned too few items.");
    }
    if (raw.items.length === 0 && !isFinalPage) {
      throw new Error("Engine sheet list page made non-progress: zero items returned before total was reached.");
    }

    for (const item of raw.items) {
      if (seen.has(item.sheet_id)) {
        throw new Error(`Engine sheet list returned duplicate sheet_id ${item.sheet_id}.`);
      }
      seen.add(item.sheet_id);
      items.push(item);
    }

    offset += raw.items.length;
    if (offset >= total) {
      return { items, total, limit: ENGINE_SHEETS_PAGE_LIMIT, offset: 0 };
    }
  }
  throw new Error("Engine sheet list pagination exceeded the maximum iteration count.");
}

/** List EVERY one of the engine's processed sheets for a synced project (real
 * sheet_id/page/title register), fetched via bounded server-side pagination so
 * a project with more than one page of sheets (e.g. a >200-page joined packet)
 * is not silently truncated to the first page. */
export async function engineListSheets(
  engineProjectId: string,
  context: EngineTenantContext,
): Promise<EngineSheetListResponse> {
  return fetchAllEngineSheets((limit, offset) =>
    engineGetJson<EngineSheetListResponse>(
      `/api/v1/projects/${engineProjectId}/sheets?limit=${limit}&offset=${offset}`,
      context,
    ),
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
