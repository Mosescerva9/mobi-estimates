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

// The header set is fixed and server-built — there is no caller-supplied header
// bag, api key, or tenant argument on the client-callable surface.
assert(workerLib.includes('"X-API-Key": workerApiKey()!'), "worker lib must attach the secret from server env only");
assert(workerLib.includes('"X-Mobi-Tenant-Id": context.tenantId'), "worker lib must set tenant header from context");
assert(workerLib.includes('"X-Mobi-Company-Id": context.companyId'), "worker lib must set company header from context");
assert(workerLib.includes('"X-Mobi-Actor-Role": context.actorRole'), "worker lib must set actor role header from context");
assert(workerLib.includes('"X-Mobi-Actor-Id": context.actorId'), "worker lib must set actor id header from context");
assert(workerLib.includes("assertSafePathSegment"), "worker lib must validate opaque path segments (reject paths)");
assert(/headers:\s*Record<string, string>/.test(workerLib), "worker lib builds its own header record, not a caller's");

// Server actions revalidate staff and resolve identity server-side from the row.
assert(takeoffActions.includes("requireStaff"), "takeoff actions must revalidate staff server-side");
assert(takeoffActions.includes('.select("id, company_id, engine_project_id")'), "takeoff actions must load company_id + engine_project_id from the project row");
assert(takeoffActions.includes("has not been sent to the estimating engine"), "takeoff actions must require engine_project_id before worker calls");
assert(takeoffActions.includes("tenantId: data.company_id"), "takeoff actions must derive tenant from the project row, not the browser");
assert(takeoffActions.includes("real tenant") || takeoffActions.includes("tenant→company mapping"), "takeoff actions must flag that real tenant mapping is still required");

// The demo fixture stays labelled as proof/demo, distinct from the live path.
assert(workbenchPanel.includes("Proof / demo fixture"), "workbench panel must label the fixture as proof/demo");
assert(workbenchPanel.includes("LiveTakeoffWorkerPanel"), "workbench panel must expose the live worker pathway");

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
    return new Response(JSON.stringify({ job_id: "job_9", status: "queued" }), {
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
  assert.equal(res.job_id, "job_9");
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
  assert.equal(body.operation, "measure_line");
  assert.ok(!("tenantId" in body) && !("apiKey" in body) && !("headers" in body), "identity/api-key must not be echoed in the body");

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
