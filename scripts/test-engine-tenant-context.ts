import { readFileSync } from "node:fs";
import { join } from "node:path";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const root = process.cwd();
const engineClient = readFileSync(join(root, "src/lib/engine.ts"), "utf8");
const adminActions = readFileSync(join(root, "src/app/admin/projects/[id]/actions.ts"), "utf8");
const portalActions = readFileSync(join(root, "src/app/portal/projects/[id]/actions.ts"), "utf8");

assert(engineClient.includes("export interface EngineTenantContext"), "engine client must define an explicit tenant context type");
assert(engineClient.includes("requireEngineTenantContext"), "engine client must fail closed when tenant context is missing");
assert(engineClient.includes("MALFORMED_TENANT_IDENTITY_SENTINELS"), "engine client must reject null/undefined tenant identity sentinels before project-scoped calls");
assert(engineClient.includes("normalized.toLowerCase()"), "engine tenant sentinel rejection must be case-insensitive");
assert(engineClient.includes('"X-Mobi-Tenant-Id": context.tenantId'), "engine client must send tenant header");
assert(engineClient.includes('"X-Mobi-Company-Id": context.companyId'), "engine client must send company header");
assert(!engineClient.includes('headers: { "X-API-Key": API_KEY! }'), "project-scoped engine calls must not use API-key-only headers");

assert(adminActions.includes("getEngineProjectContext"), "admin actions must load engine project context, not only engine project id");
assert(adminActions.includes('.select("engine_project_id, company_id")'), "admin automation actions must load company_id with engine_project_id");
assert(adminActions.includes("context: engineContext"), "sendToEngine must attach tenant context during engine upload");
assert(adminActions.includes("undefined, engineContext"), "admin engine mutations without JSON body must still pass tenant context");
assert(adminActions.includes(", engineContext"), "admin engine reads/writes must pass tenant context");

assert(portalActions.includes('.select("id, engine_project_id, company_id")'), "portal revision actions must load company_id with engine_project_id");
assert(portalActions.includes("{ tenantId: companyId, companyId }"), "portal customer-safe engine calls must pass tenant/company headers");

console.log("Engine tenant context static checks passed.");
