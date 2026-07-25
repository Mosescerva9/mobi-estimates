import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Static guards for the two Packet-1 SQL migrations. A full clean-Postgres
 * runtime test is the follow-up when a Postgres/Supabase harness is available;
 * these assertions lock in the security-critical shape of the migrations so a
 * later edit cannot silently drop the CAS, the strict JSONB validation, the
 * idempotent event, or the least-privilege grants.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

const MIGRATIONS = join(__dirname, "..", "supabase", "migrations");
const rpc = readFileSync(join(MIGRATIONS, "0036_save_engine_packet_manifest_rpc.sql"), "utf8").toLowerCase();
const grants = readFileSync(join(MIGRATIONS, "0037_least_privilege_table_grants.sql"), "utf8").toLowerCase();
const grantsSql = grants.replace(/^\s*--.*$/gm, "");

test("0036 is a staff-only security-definer function", () => {
  assert(rpc.includes("security definer"), "must be security definer");
  assert(rpc.includes("if not public.is_staff()"), "must gate on is_staff()");
  assert(rpc.includes("raise exception 'not authorized'"), "must reject non-staff");
});

test("0036 uses the established lock order (jobs then projects, FOR UPDATE)", () => {
  const jobLock = rpc.indexOf("from public.estimate_jobs");
  const projLock = rpc.indexOf("from public.projects");
  assert(jobLock > -1 && projLock > -1 && jobLock < projLock, "estimate_jobs must lock before projects");
  assert((rpc.match(/for update/g) ?? []).length >= 2, "both rows must be locked FOR UPDATE");
});

test("0036 performs a null-or-equal CAS on the engine link and refuses conflicts", () => {
  assert(rpc.includes("engine_project_conflict"), "must return an engine_project_conflict reason");
  assert(
    rpc.includes("engine_project_id is null or engine_project_id = p_engine_project_id"),
    "CAS write must be guarded to null-or-equal",
  );
});

test("0036 validates JSONB by key existence + jsonb_typeof, not only ->>", () => {
  assert(rpc.includes("jsonb_typeof"), "must use jsonb_typeof");
  assert(rpc.includes("? 'packet'") || rpc.includes("?'packet'"), "must check packet key existence");
  assert(rpc.includes("? 'sources'") || rpc.includes("?'sources'"), "must check sources key existence");
  assert(rpc.includes("manifest_not_object"), "must reject a non-object manifest");
  assert(rpc.includes("sources_not_array"), "must reject a non-array sources");
});

test("0036 requires lowercase 64-hex SHA-256 and a schema version", () => {
  assert(rpc.includes("[0-9a-f]{64}"), "must require lowercase 64-hex sha");
  assert(rpc.includes("missing_schema_version") && rpc.includes("engine_packet_v1"), "must require a schema version");
});

test("0036 rejects duplicates, noncontiguous pages, and page/count mismatches", () => {
  for (const reason of [
    "invalid_source_orders_or_duplicates",
    "page_sum_mismatch",
    "noncontiguous_pages",
    "source_count_mismatch",
  ]) {
    assert(rpc.includes(reason), `must reject: ${reason}`);
  }
});

test("0036 validates the exact accepted-document snapshot", () => {
  assert(rpc.includes("accepted_set_mismatch"), "must reject a stale/wrong accepted set");
  assert(rpc.includes("review_status = 'accepted'"), "must derive the snapshot from the accepted register");
});

test("0036 inserts at most one event per (project, packet sha256)", () => {
  assert(rpc.includes("if not exists"), "event insert must be conditional");
  assert(rpc.includes("payload #>> '{packet,sha256}'"), "idempotency must key on the packet sha256");
});

test("0036 validates jsonb scalars NULL-safely (is distinct from, never bare <>)", () => {
  // A missing jsonb key yields SQL NULL, and `NULL <> 'number'` is NULL -- not
  // TRUE -- so a bare-`<>` guard silently passes a manifest that OMITS the key.
  assert(
    !/jsonb_typeof\([^)]*\)\s*<>/.test(rpc),
    "jsonb_typeof comparisons must use `is distinct from`, not bare `<>` (NULL fails open)",
  );
  assert(rpc.includes("is distinct from 'number'"), "numeric type checks must be NULL-safe");
  assert(rpc.includes("is distinct from 'string'"), "string type checks must be NULL-safe");
  assert(
    rpc.includes("v_page_count is null") && rpc.includes("v_source_count is null"),
    "derived packet counts must be explicitly rejected when NULL",
  );
  assert(
    rpc.includes("missing_engine_page_count"),
    "a null p_engine_page_count must be rejected, not compared against a null manifest value",
  );
  assert(
    !/v_stats\.\w+\s*<>/.test(rpc),
    "aggregate structural comparisons must use `is distinct from`",
  );
});

test("0036 rejects non-integral numeric source fields before any ::int cast", () => {
  for (const field of ["order", "source_bytes", "source_page_count", "combined_page_start", "combined_page_end"]) {
    assert(
      rpc.includes(`coalesce(e->>'${field}', '') !~ '^[0-9]+$'`),
      `must reject a non-integral ${field} with a validation reason, not a cast error`,
    );
  }
});

test("0036 strips the default PUBLIC execute grant from the security-definer function", () => {
  // Postgres grants EXECUTE to PUBLIC by default; a definer-rights function left
  // that way is reachable by anon and every future role.
  assert(
    /revoke execute on function\s+public\.save_engine_packet_manifest\([^)]*\)\s+from public;/.test(rpc),
    "must revoke the default PUBLIC execute grant",
  );
  assert(
    /revoke execute on function\s+public\.save_engine_packet_manifest\([^)]*\)\s+from anon;/.test(rpc),
    "must revoke execute from anon",
  );
  const revokeAt = rpc.indexOf("revoke execute on function");
  const grantAt = rpc.indexOf("grant execute on function");
  assert(revokeAt > -1 && grantAt > revokeAt, "the revoke must precede the authenticated grant");
});

test("0036 exposes the new 6-arg signature and grants execute to authenticated", () => {
  assert(
    rpc.includes("save_engine_packet_manifest(\n  p_project_id uuid,") ||
      rpc.includes("p_engine_status text") ,
    "must carry the engine status/page-count parameters",
  );
  assert(
    rpc.includes("(uuid, uuid, uuid, text, integer, jsonb)"),
    "grant must reference the 6-arg signature",
  );
});

test("0037 never uses grant all and strips TRUNCATE/TRIGGER/REFERENCES from every API role", () => {
  assert(!/grant\s+all/.test(grantsSql), "must not use grant all");
  assert(
    grants.includes("revoke truncate, references, trigger on all tables in schema public from anon"),
    "must strip dangerous privileges from anon",
  );
  assert(
    grants.includes("revoke truncate, references, trigger on all tables in schema public from authenticated"),
    "must strip dangerous privileges from authenticated",
  );
  assert(
    grants.includes("revoke truncate, references, trigger on all tables in schema public from service_role"),
    "must strip dangerous privileges from service_role",
  );
});

test("0037 grants customer-flow CRUD to authenticated for the named tables", () => {
  for (const table of [
    "profiles",
    "companies",
    "company_members",
    "company_preferences",
    "onboarding_progress",
    "projects",
    "project_files",
  ]) {
    assert(
      new RegExp(`grant select, insert, update, delete on public\\.${table}\\b`).test(grants),
      `must grant customer CRUD on ${table}`,
    );
  }
});

test("0037 keeps pure service-role tables closed to both API roles", () => {
  assert(grants.includes("revoke all on public.notification_outbox from anon, authenticated"), "notification_outbox stays closed");
  assert(grants.includes("revoke all on public.webhook_events"), "webhook_events stays closed");
});

test("0037 restores ordinary DML and sequence access to service_role without destructive grants", () => {
  assert(
    grants.includes("grant select, insert, update, delete on all tables in schema public to service_role"),
    "service_role must receive ordinary table DML",
  );
  assert(
    grants.includes("grant usage, select, update on all sequences in schema public to service_role"),
    "service_role must receive sequence access needed by inserts",
  );
  assert(
    !/grant\s+(truncate|trigger|references)[^;]*service_role/.test(grantsSql),
    "must not grant destructive privileges to service_role",
  );
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  console.log(`\n${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) process.exit(1);
}

main();
