import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Verifies the staff live-measurement worker proxy foundation WITHOUT needing
 * any live secret. It exercises two things:
 *   1. Static source guarantees (no NEXT_PUBLIC_ worker secret, no caller header
 *      bag, server-side tenant/actor resolution, engine_project_id gate).
 *   2. Runtime behaviour of src/lib/takeoff-worker.ts against a stubbed fetch:
 *      it builds the five identity headers server-side, ignores browser-provided
 *      tenant/api-key, rejects paths, and fails closed when env is missing.
 */

const root = process.cwd();
const read = (rel: string) => readFileSync(join(root, rel), "utf8");

const workerLib = read("src/lib/takeoff-worker.ts");
const takeoffActions = read("src/app/admin/projects/[id]/takeoff-actions.ts");
const livePanel = read("src/app/admin/projects/[id]/LiveTakeoffWorkerPanel.tsx");
const workbenchPanel = read("src/app/admin/projects/[id]/TakeoffWorkbenchPanel.tsx");
const workbenchModel = read("src/lib/estimator-takeoff-workbench.ts");

// ---------------------------------------------------------------------------
// Static source guarantees
// ---------------------------------------------------------------------------

// The worker secret is server-only: never a NEXT_PUBLIC_ env, never in the
// browser bundle (client components must not import the server lib directly).
assert(!workerLib.includes("NEXT_PUBLIC_MOBI_WORKER"), "worker secret must never be NEXT_PUBLIC_");
assert(workerLib.includes("process.env.MOBI_WORKER_API_URL"), "worker lib must read MOBI_WORKER_API_URL server-side");
assert(workerLib.includes("process.env.MOBI_WORKER_API_KEY"), "worker lib must read MOBI_WORKER_API_KEY server-side");
assert(!livePanel.includes("process.env"), "client live panel must never read env (no server secret in the browser)");
assert(!livePanel.includes("@/lib/takeoff-worker"), "client live panel must not import the server-only worker lib");
assert(livePanel.includes('from "./takeoff-actions"'), "client live panel must go through server actions only");
assert(!workbenchPanel.includes("process.env"), "visual workbench client must never read env");
assert(!workbenchPanel.includes("@/lib/takeoff-worker"), "visual workbench client must not import server-only worker lib");
assert(workbenchPanel.includes('from "./takeoff-actions"'), "visual workbench must use server actions for worker calls");

// The header set is fixed and server-built — there is no caller-supplied header
// bag, api key, or tenant argument on the client-callable surface.
assert(workerLib.includes('"X-API-Key": workerApiKey()!'), "worker lib must attach the secret from server env only");
assert(workerLib.includes('"X-Mobi-Tenant-Id": context.tenantId'), "worker lib must set tenant header from context");
assert(workerLib.includes('"X-Mobi-Company-Id": context.companyId'), "worker lib must set company header from context");
assert(workerLib.includes('"X-Mobi-Actor-Role": context.actorRole'), "worker lib must set actor role header from context");
assert(workerLib.includes('"X-Mobi-Actor-Id": context.actorId'), "worker lib must set actor id header from context");
assert(workerLib.includes("assertSafePathSegment"), "worker lib must validate opaque path segments (reject paths)");
assert(workerLib.includes("WORKER_FETCH_TIMEOUT_MS"), "worker lib must bound live worker calls so staff UI cannot hang indefinitely");
assert(workerLib.includes("AbortController"), "worker lib must abort unresponsive worker fetches");
assert(workerLib.includes("Promise.race"), "worker lib must use a hard timeout race around worker fetches");
assert(workerLib.includes("Takeoff worker request timed out"), "worker timeout must return a staff-readable error");
assert(/headers:\s*Record<string, string>/.test(workerLib), "worker lib builds its own header record, not a caller's");

// Server actions revalidate staff and resolve identity server-side from the row.
assert(takeoffActions.includes("requireStaff"), "takeoff actions must revalidate staff server-side");
assert(takeoffActions.includes('.select("id, company_id, engine_project_id")'), "takeoff actions must load company_id + engine_project_id from the project row");
assert(takeoffActions.includes("has not been sent to the estimating engine"), "takeoff actions must require engine_project_id before worker calls");
assert(takeoffActions.includes("tenantId: data.company_id"), "takeoff actions must derive tenant from the project row, not the browser");
assert(takeoffActions.includes("real tenant") || takeoffActions.includes("tenant→company mapping"), "takeoff actions must flag that real tenant mapping is still required");

// The worker call must carry the ENGINE project id (not the portal id) for both
// project_id and document_id; the engine id is validated and fails closed.
assert(takeoffActions.includes("resolveWorkerJobIds"), "takeoff actions must resolve worker ids from the engine id");
assert(takeoffActions.includes("engineProjectId: resolved.engineProjectId"), "takeoff actions must feed the engine id into worker id resolution");
assert(takeoffActions.includes("projectId: workerIds.projectId"), "create must send the resolved (engine) project id to the worker");
assert(takeoffActions.includes("documentId: workerIds.documentId"), "create must send the resolved (engine) document id to the worker");
assert(!takeoffActions.includes("documentId: resolved.documentId"), "create must NOT send the portal id as the worker document id");
assert(takeoffActions.includes("retryTakeoffJob"), "takeoff actions must expose a durable retry action");
assert(takeoffActions.includes("retryLiveTakeoffJob"), "takeoff actions must expose the staff-only retryLiveTakeoffJob action");
assert(/retryTakeoffJob\(resolved\.context, jobId\)/.test(takeoffActions), "retryLiveTakeoffJob must retry via the server-resolved worker context");

// --- Failed-job retry control is wired into the live workbench UI (MVP gap) ---
// The staff retry button must (a) call the staff-only retryLiveTakeoffJob action,
// (b) render only for an exactly-`failed` job via the shared pure eligibility
// helper, (c) share the pending/disabled worker-action gating, and (d) retain the
// original failed job lineage rather than hiding it behind the adopted retry job.
assert(workbenchPanel.includes("retryLiveTakeoffJob"), "workbench must wire the staff-only retry action");
assert(workbenchPanel.includes("canRetryWorkerJob"), "workbench must gate the retry control on the shared pure eligibility helper");
assert(workbenchModel.includes("export function canRetryWorkerJob"), "the retry eligibility helper must be a pure, client-safe export");
assert(/canRetryWorkerJob\(workerStatus\)/.test(workbenchPanel), "workbench must test retry eligibility against the current worker job status");
assert(workbenchPanel.includes("Retry failed job"), "workbench must show a staff-visible retry control label");
assert(/retryEligible && jobId \? <button[^>]*onClick=\{retryFailedJob\}/.test(workbenchPanel), "retry button must render only when eligible and invoke retryFailedJob on click (no auto-retry)");
assert(workbenchPanel.includes("workerPending") && /disabled=\{!ready \|\| workerPending\}/.test(workbenchPanel), "retry button must share pending/disabled gating to prevent repeated clicks");
assert(workbenchPanel.includes("retriedFromJob"), "workbench must retain the original failed job lineage when adopting the retry attempt");
assert(workbenchPanel.includes("original failed job and its error are retained unchanged"), "workbench must state that the original failed job/error is not mutated or hidden");

// The old replay fixture must not be presented as the real workbench. The new
// visual workbench carries client-safe document/sheet view models only.
assert(workbenchPanel.includes("Estimator visual takeoff workbench"), "workbench panel must expose the visual takeoff surface");
assert(workbenchPanel.includes("measureLiveTakeoffPolygon"), "workbench must wire polygon submission through server actions");
assert(workbenchPanel.includes("measureLiveTakeoffCount"), "workbench must wire count submission through server actions");
assert(/setMode\("count"\)/.test(workbenchPanel), "workbench must expose a count measurement mode control");
assert(takeoffActions.includes("measureLiveTakeoffCount"), "takeoff actions must expose a staff-only count action");
assert(workbenchPanel.includes("CLIENT_WORKER_ACTION_TIMEOUT_MS"), "workbench client must bound pending server-action worker calls");
assert(workbenchPanel.includes("Worker action timed out in the browser"), "workbench client timeout must be staff-visible");
assert(workbenchPanel.includes("buildWorkbenchIdempotencyKey"), "visual workbench submissions must use geometry-specific idempotency keys");
assert(workbenchPanel.includes("pointKey"), "visual workbench idempotency must include drawn geometry so new measurements do not reuse old jobs");
assert(workbenchPanel.includes('preserveAspectRatio="none"'), "visual workbench SVG must not letterbox natural-raster coordinate mapping");
assert(workbenchModel.includes("signedUrl: string"), "workbench document model may carry signed URLs");
assert(!/storage_path\??:/.test(workbenchModel), "workbench client model must not expose storage_path");

// ---------------------------------------------------------------------------
// Runtime behaviour (stubbed fetch, no live secret)
// ---------------------------------------------------------------------------

const CONTEXT = {
  tenantId: "company-abc",
  companyId: "company-abc",
  actorRole: "estimator" as const,
  actorId: "staff-123",
};

async function main() {
  // The worker lib reads env lazily, so one import supports both phases.
  const worker = await import("../src/lib/takeoff-worker");

  // --- Engine-id resolution (B1): a portal row whose engine_project_id differs
  // from its portal id must send the ENGINE id to the worker for BOTH the
  // project_id and document_id, and fail closed on a missing/invalid engine id.
  const ids = await import("../src/lib/takeoff-worker-ids");
  const PORTAL_ID = "portal-1111";
  const ENGINE_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
  const resolvedIds = ids.resolveWorkerJobIds({ portalProjectId: PORTAL_ID, engineProjectId: ENGINE_ID });
  assert.equal(resolvedIds.projectId, ENGINE_ID, "worker project_id must be the engine id, not the portal id");
  assert.equal(resolvedIds.documentId, ENGINE_ID, "worker document_id must be the engine id, not the portal id");
  assert.notEqual(resolvedIds.projectId, PORTAL_ID, "worker must never receive the portal id as project_id");
  for (const bad of [null, undefined, "", "   ", "not-a-uuid", PORTAL_ID]) {
    assert.throws(
      () => ids.resolveWorkerJobIds({ portalProjectId: PORTAL_ID, engineProjectId: bad as never }),
      /engine_project_id/,
      `missing/invalid engine id (${String(bad)}) must fail closed, never substitute the portal id`,
    );
  }
  assert.equal(ids.isValidEngineProjectId(ENGINE_ID), true, "a UUID is a valid engine id");
  assert.equal(ids.isValidEngineProjectId(PORTAL_ID), false, "a non-UUID portal id is not a valid engine id");

  // --- Fails closed when env is missing ---
  delete process.env.MOBI_WORKER_API_URL;
  delete process.env.MOBI_WORKER_API_KEY;
  assert.equal(worker.workerConfigured(), false, "workerConfigured must be false without env");
  await assert.rejects(
    () => worker.getTakeoffJob(CONTEXT, "job_1"),
    /not configured/,
    "worker calls must fail closed when env is missing",
  );

  // --- Configure via env (the only source of the secret) ---
  process.env.MOBI_WORKER_API_URL = "https://worker.example.test";
  process.env.MOBI_WORKER_API_KEY = "test-secret-key";
  assert.equal(worker.workerConfigured(), true, "workerConfigured must be true once env is set");

  // Stub fetch to capture the outgoing request without any network call.
  const realFetch = globalThis.fetch;
  let captured: { url: string; headers: Record<string, string>; body: unknown } | null = null;
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    captured = {
      url: String(url),
      headers,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    // The live worker wraps the job row: create => { job, created }, and
    // status/confirm/measure => { job }. The client must normalize either.
    return new Response(JSON.stringify({ job: { job_id: "job_9", status: "queued" }, created: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;

  try {
  // Attacker-controlled fields on the input object must NOT reach the worker as
  // identity — the server context is the only source of tenant/api-key/actor.
  const dirtyInput = {
    projectId: "proj-1",
    documentId: "proj-1",
    page: 4,
    operation: "measure_line" as const,
    // These are not part of the input type; simulate a hostile caller.
    tenantId: "attacker-tenant",
    apiKey: "attacker-key",
    headers: { "X-API-Key": "attacker-key" },
  };
  const res = await worker.createTakeoffJob(CONTEXT, dirtyInput as never);
  // The wrapped `{ job, created }` envelope is normalized to a flat shape.
  assert.equal(res.job_id, "job_9", "job_id must be lifted out of the { job } envelope");
  assert.equal(res.status, "queued", "status must be lifted out of the { job } envelope");
  assert.equal(res.created, true, "created flag must be surfaced from the create envelope");
  assert.ok(captured, "fetch should have been called");

  const h = captured!.headers;
  // The five identity headers come from the server context / env.
  assert.equal(h["X-API-Key"], "test-secret-key", "secret must come from server env, not the caller");
  assert.equal(h["X-Mobi-Tenant-Id"], "company-abc", "tenant must come from server context, not the caller");
  assert.equal(h["X-Mobi-Company-Id"], "company-abc", "company must come from server context");
  assert.equal(h["X-Mobi-Actor-Role"], "estimator", "actor role must come from server context");
  assert.equal(h["X-Mobi-Actor-Id"], "staff-123", "actor id must come from server context");

  // No attacker-provided header leaked through and no unexpected header exists.
  const allowed = new Set([
    "X-API-Key",
    "X-Mobi-Tenant-Id",
    "X-Mobi-Company-Id",
    "X-Mobi-Actor-Role",
    "X-Mobi-Actor-Id",
    "Content-Type",
  ]);
  for (const key of Object.keys(h)) {
    assert.ok(allowed.has(key), `unexpected header forwarded to worker: ${key}`);
  }
  // The body carries operation inputs only — never identity.
  const body = captured!.body as Record<string, unknown>;
  assert.equal(body.project_id, "proj-1");
  assert.equal(body.document_id, "proj-1");
  assert.equal(body.operation, "measure_line");
  assert.ok(!("tenantId" in body) && !("apiKey" in body) && !("headers" in body), "identity/api-key must not be echoed in the body");
  // Current FastAPI CreateJobRequest contract: trade/scope_category/idempotency_key
  // are REQUIRED and `page` is FORBIDDEN (extra="forbid"). This is the exact shape
  // whose mismatch produced the live "Request validation failed" response.
  assert.equal(body.trade, "electrical", "create must send a trade (default: electrical)");
  assert.equal(body.scope_category, "ev_charging", "create must send a scope_category (default: ev_charging)");
  assert.equal(typeof body.idempotency_key, "string", "create must send a string idempotency_key");
  assert.ok((body.idempotency_key as string).length > 0, "idempotency_key must be non-empty");
  assert.equal(body.default_description, "Public C011 measured conduit line", "create must send the proof default_description");
  assert.ok(!("page" in body), "create must NOT send `page` (worker forbids unknown fields)");
  assert.ok(!("points" in body) && !("sheet_key" in body), "create must not smuggle geometry/provider selectors");

  // --- confirm-scale payload matches the live ConfirmScaleRequest contract ---
  // Required: sheet_id, page_number, scale_source, scale_label. `page`/`units_per_px`
  // alone (the old shape) was rejected. units_per_px is optional but must be > 0.
  const confirmRes = await worker.confirmScale(CONTEXT, "job_9", {
    sheetId: "11111111-1111-1111-1111-111111111111",
    page: 4,
    unitsPerPx: 12.5,
  });
  assert.equal(confirmRes.job_id, "job_9", "confirm response { job } must be normalized");
  const confirmBody = captured!.body as Record<string, unknown>;
  assert.equal(confirmBody.sheet_id, "11111111-1111-1111-1111-111111111111");
  assert.equal(confirmBody.page_number, 4, "confirm must send page_number, not page");
  assert.ok(!("page" in confirmBody), "confirm must NOT send legacy `page` (worker forbids unknown fields)");
  assert.equal(typeof confirmBody.scale_source, "string", "confirm must send a required scale_source");
  assert.ok((confirmBody.scale_source as string).length > 0, "scale_source must be non-empty");
  assert.equal(typeof confirmBody.scale_label, "string", "confirm must send a required scale_label");
  assert.ok((confirmBody.scale_label as string).length > 0, "scale_label must be non-empty");
  assert.equal(confirmBody.units_per_px, 12.5, "confirm must pass units_per_px through");

  // --- measure-line payload matches the live MeasureRequest contract ---
  // Requires `geometry: { points }`; the old flat `points`/`page` shape was rejected.
  const measureRes = await worker.measureLine(CONTEXT, "job_9", {
    sheetId: "22222222-2222-2222-2222-222222222222",
    points: [
      [0, 0],
      [10, 0],
    ],
  });
  assert.equal(measureRes.job_id, "job_9", "measure response { job } must be normalized");
  const measureBody = captured!.body as Record<string, unknown>;
  const geometry = measureBody.geometry as Record<string, unknown> | undefined;
  assert.ok(geometry && Array.isArray(geometry.points), "measure must nest points under geometry");
  assert.equal((geometry!.points as unknown[]).length, 2, "measure must forward all points");
  assert.ok(!("points" in measureBody), "measure must NOT send top-level points (worker forbids unknown fields)");
  assert.ok(!("page" in measureBody), "measure must NOT send `page` (worker forbids unknown fields)");
  assert.equal(measureBody.sheet_id, "22222222-2222-2222-2222-222222222222", "measure may pass sheet_id");

  // --- measure-polygon payload matches the live MeasureRequest contract ---
  const polygonRes = await worker.measurePolygon(CONTEXT, "job_9", {
    sheetId: "33333333-3333-3333-3333-333333333333",
    vertices: [
      [0, 0],
      [10, 0],
      [10, 10],
    ],
  });
  assert.equal(polygonRes.job_id, "job_9", "polygon measure response { job } must be normalized");
  const polygonBody = captured!.body as Record<string, unknown>;
  const polygonGeometry = polygonBody.geometry as Record<string, unknown> | undefined;
  assert.ok(polygonGeometry && Array.isArray(polygonGeometry.vertices), "polygon measure must nest vertices under geometry");
  assert.equal((polygonGeometry!.vertices as unknown[]).length, 3, "polygon measure must forward all vertices");
  assert.ok(!("vertices" in polygonBody), "polygon measure must NOT send top-level vertices");
  assert.equal(polygonBody.sheet_id, "33333333-3333-3333-3333-333333333333", "polygon measure may pass sheet_id");

  // --- measure-count payload matches the live MeasureRequest contract ---
  // Count markers are nested under geometry.points (each marker = one EA).
  const countRes = await worker.measureCount(CONTEXT, "job_9", {
    sheetId: "44444444-4444-4444-4444-444444444444",
    markers: [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
    ],
    condition: "EV-COUNT",
  });
  assert.equal(countRes.job_id, "job_9", "count measure response { job } must be normalized");
  const countBody = captured!.body as Record<string, unknown>;
  const countGeometry = countBody.geometry as Record<string, unknown> | undefined;
  assert.ok(countGeometry && Array.isArray(countGeometry.points), "count measure must nest markers under geometry.points");
  assert.equal((countGeometry!.points as unknown[]).length, 4, "count measure must forward all markers");
  assert.ok(!("markers" in countBody), "count measure must NOT send a top-level markers field");
  assert.ok(!("page" in countBody), "count measure must NOT send `page` (worker forbids unknown fields)");
  assert.equal(countBody.sheet_id, "44444444-4444-4444-4444-444444444444", "count measure may pass sheet_id");
  assert.equal(countBody.condition, "EV-COUNT", "count measure may pass a condition");

  // --- retry contract (B5): POST /jobs/{id}/retry, returns normalized job ---
  const retryRes = await worker.retryTakeoffJob(CONTEXT, "job_9");
  assert.equal(retryRes.job_id, "job_9", "retry response { job } must be normalized");
  assert.ok(String(captured!.url).endsWith("/internal/takeoff/jobs/job_9/retry"), "retry must POST to the retry endpoint");
  await assert.rejects(() => worker.retryTakeoffJob(CONTEXT, "a/b"), /opaque id/, "retry job id must reject paths");

  // --- Reject paths in opaque id positions ---
  await assert.rejects(() => worker.getTakeoffJob(CONTEXT, "../../etc/passwd"), /opaque id/, "job id must reject path traversal");
  await assert.rejects(() => worker.getArtifacts(CONTEXT, "a/b"), /opaque id/, "artifact job id must reject slashes");

  // --- Fail closed on missing/malformed tenant context even when configured ---
  await assert.rejects(
    () => worker.getTakeoffJob({ ...CONTEXT, tenantId: "" }, "job_1"),
    /tenant context is required/,
    "missing tenant must fail closed",
  );
  await assert.rejects(
    () => worker.getTakeoffJob({ ...CONTEXT, tenantId: "null" }, "job_1"),
    /tenant context is required/,
    "sentinel tenant identity must fail closed",
  );
  await assert.rejects(
    () => worker.getTakeoffJob({ ...CONTEXT, actorRole: "client" as never }, "job_1"),
    /actor role must be/,
    "non-staff actor role must fail closed",
  );
  } finally {
    globalThis.fetch = realFetch;
  }

  console.log("takeoff worker proxy checks passed");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
