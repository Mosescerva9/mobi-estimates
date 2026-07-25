import { readFileSync, readdirSync } from "node:fs";
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
const sendToEngineSource = readFileSync(
  join(__dirname, "..", "src", "app", "admin", "projects", "[id]", "actions.ts"),
  "utf8",
);

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

test("0036 validates the exact accepted-document snapshot through active project files", () => {
  assert(rpc.includes("accepted_set_mismatch"), "must reject a stale/wrong accepted set");
  assert(rpc.includes("review_status = 'accepted'"), "must derive the snapshot from the accepted register");
  assert(rpc.includes("join public.project_files"), "accepted rows must resolve through project_files");
  assert(rpc.includes("f.deleted_at is null"), "soft-deleted project files must be rejected");
  assert(rpc.includes("f.project_id = d.project_id"), "register/project-file project identity must match");
  assert(rpc.includes("f.company_id = d.company_id"), "register/project-file company identity must match");
  assert(rpc.includes("f.storage_path = d.storage_path"), "register/project-file storage paths must match");
  assert(rpc.includes("f.file_name = d.file_name"), "register/project-file names must match");
  assert(rpc.includes("v_active_accepted_count is distinct from v_source_count"), "every accepted row must have active-file backing");
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

test("0036 binds a separately supplied positive integral engine byte count", () => {
  assert(rpc.includes("p_engine_file_size_bytes bigint"), "RPC must accept a separately validated engine byte count");
  assert(rpc.includes("missing_engine_file_size_bytes"), "NULL engine byte count must fail closed");
  assert(rpc.includes("nonpositive_engine_file_size_bytes"), "nonpositive engine byte count must fail closed");
  assert(rpc.includes("engine_file_size_bytes_mismatch"), "engine and manifest byte counts must match");
  assert(rpc.includes("v_packet_bytes <= 0"), "manifest packet bytes must be positive");
  assert(
    rpc.includes("coalesce(v_packet->>'bytes', '') !~ '^[0-9]+$'"),
    "manifest packet bytes must be integral before bigint cast",
  );
});

test("0036 binds the stored packet's content hash to the manifest sha256", () => {
  // The byte count alone cannot pin content: two different packets of equal size
  // share it. The packet sha256 is also this function's event-idempotency key,
  // so an unbound hash would let a manifest be persisted -- or an event
  // suppressed as a duplicate -- against content it does not describe.
  assert(rpc.includes("p_engine_file_sha256 text"), "RPC must accept the stored packet's sha256");
  assert(rpc.includes("missing_engine_file_sha256"), "NULL engine packet hash must fail closed");
  assert(rpc.includes("invalid_engine_file_sha256"), "a non-64-hex engine packet hash must fail closed");
  assert(rpc.includes("engine_file_sha256_mismatch"), "engine and manifest packet hashes must match");
  assert(
    rpc.includes("p_engine_file_sha256 !~ '^[0-9a-f]{64}$'"),
    "the engine packet hash must be lowercase 64-hex like every other hash here",
  );
  assert(
    rpc.includes("p_engine_file_sha256 is distinct from v_packet_sha"),
    "the hash comparison must be NULL-safe (is distinct from, never bare <>)",
  );
});

test("0036 exposes the new 8-arg signature and grants execute to authenticated", () => {
  assert(
    rpc.includes("save_engine_packet_manifest(\n  p_project_id uuid,") ||
      rpc.includes("p_engine_status text") ,
    "must carry the engine status/page-count parameters",
  );
  assert(
    rpc.includes("(uuid, uuid, uuid, text, integer, bigint, text, jsonb)"),
    "grant must reference the 8-arg signature",
  );
  // Every superseded arity must be dropped, or an older, weaker overload stays
  // callable alongside the hardened one.
  for (const superseded of [
    "(uuid, uuid, uuid, jsonb)",
    "(uuid, uuid, uuid, text, integer, jsonb)",
    "(uuid, uuid, uuid, text, integer, bigint, jsonb)",
  ]) {
    assert(
      rpc.includes(`drop function if exists public.save_engine_packet_manifest${superseded}`),
      `the superseded ${superseded} overload must be dropped`,
    );
  }
});

test("the only RPC caller supplies every packet-identity argument the RPC binds", () => {
  // The RPC can only bind the manifest to real packet content if the caller
  // actually passes the stored file's page count, byte count, and hash. Guard
  // the call site so a future edit cannot quietly drop one back to an unbound
  // manifest-declared value.
  const call = sendToEngineSource.slice(
    sendToEngineSource.indexOf('supabase.rpc("save_engine_packet_manifest"'),
  );
  assert(call.length > 0, "actions.ts must call save_engine_packet_manifest");
  for (const arg of [
    "p_engine_page_count:",
    "p_engine_file_size_bytes:",
    "p_engine_file_sha256:",
    "p_packet_manifest:",
  ]) {
    assert(call.slice(0, 800).includes(arg), `the RPC call must pass ${arg}`);
  }
  // Those two values come from the validated engine response, and are re-checked
  // locally before the call rather than being trusted onward blindly.
  assert(
    sendToEngineSource.includes("engineFileSizeBytes: result.file_size_bytes") &&
      sendToEngineSource.includes("engineFileSha256: result.file_sha256"),
    "the byte count and hash must come from the validated engine packet response",
  );
  assert(
    sendToEngineSource.includes("/^[0-9a-f]{64}$/.test(args.engineFileSha256)"),
    "the packet hash must be re-validated as lowercase 64-hex before the RPC call",
  );
  assert(
    sendToEngineSource.includes("Number.isSafeInteger(args.engineFileSizeBytes)"),
    "the packet byte count must be re-validated as a safe integer before the RPC call",
  );
});

/**
 * Parsed view of 0037's grant statements: [privileges, target, roles] per
 * statement, comments already stripped. The tests below assert on this instead
 * of on substrings so a NEW grant to a browser role cannot slip in unnoticed.
 */
type GrantStatement = { privileges: string[]; target: string; roles: string[] };

const grantStatements: GrantStatement[] = [
  ...grantsSql.matchAll(
    /\bgrant\s+([a-z,\s]+?)\s+on\s+(public\.[a-z_]+|all tables in schema public|all sequences in schema public)\s+to\s+([a-z_,\s]+);/g,
  ),
].map((m) => ({
  privileges: m[1].split(",").map((p) => p.trim()).filter(Boolean),
  target: m[2].replace(/\s+/g, " ").trim(),
  roles: m[3].split(",").map((r) => r.trim()).filter(Boolean),
}));

/** Every table 0037 grants `role` something, mapped to the granted privileges. */
function grantsForRole(role: string): Map<string, Set<string>> {
  const byTable = new Map<string, Set<string>>();
  for (const stmt of grantStatements) {
    if (!stmt.roles.includes(role)) continue;
    const existing = byTable.get(stmt.target) ?? new Set<string>();
    for (const privilege of stmt.privileges) existing.add(privilege);
    byTable.set(stmt.target, existing);
  }
  return byTable;
}

/** Public tables this repo's migrations create, for typo/coverage checks. */
const declaredTables = new Set(
  [
    ...readdirSync(MIGRATIONS)
      .filter((f) => f.endsWith(".sql"))
      .map((f) => readFileSync(join(MIGRATIONS, f), "utf8").toLowerCase())
      .join("\n")
      .matchAll(/create table (?:if not exists )?public\.([a-z_]+)/g),
  ].map((m) => m[1]),
);

const CUSTOMER_FLOW_TABLES = [
  "profiles",
  "companies",
  "company_members",
  "company_preferences",
  "onboarding_progress",
  "projects",
  "project_files",
];

/**
 * The complete set of tables `authenticated` may touch, with the exact
 * operations. Anything beyond the customer-flow allowlist is a signed-in
 * surface (portal or the staff console, which also runs as `authenticated`)
 * whose rows are already scoped by an RLS policy. Adding a table here without
 * a call site is a privilege widening.
 */
const AUTHENTICATED_GRANTS: Record<string, string[]> = {
  ...Object.fromEntries(
    CUSTOMER_FLOW_TABLES.map((t) => [t, ["select", "insert", "update", "delete"]]),
  ),
  plans: ["select"],
  subscriptions: ["select"],
  pay_per_project_orders: ["select"],
  deliverables: ["select", "insert", "update"],
  notifications: ["select", "insert"],
  notification_outbox: ["insert"],
  project_scopes: ["select", "insert", "update"],
  project_status_history: ["select", "insert"],
  project_assignments: ["select", "insert", "update"],
  intro_offer_claims: ["select"],
  estimate_jobs: ["select", "insert", "update"],
  estimate_job_documents: ["select"],
  estimate_job_events: ["select", "insert"],
};

/** Tables no browser-reachable role may hold a single privilege on. */
const SERVICE_ROLE_ONLY_TABLES = [
  "audit_logs",
  "webhook_events",
  "checkout_claims",
  "lead_captures",
  "canonical_takeoff_evidence",
  "opentakeoff_worker_jobs",
  "opentakeoff_worker_job_artifacts",
  "agreement_acceptances",
  "project_constraints",
  "project_counters",
  "project_questions",
  "question_responses",
  "revision_requests",
  "support_tickets",
  "training_completions",
  "training_modules",
  "service_agreements",
  "faq_entries",
];

test("0037 revokes every table privilege from anon/authenticated before granting", () => {
  // The production baseline has Supabase's default `grant all` on all 35 public
  // tables for anon AND authenticated. A migration that only adds grants leaves
  // that baseline fully intact, so the schema-wide revoke is what makes the
  // outcome identical from a clean local stack and from production.
  for (const role of ["anon", "authenticated"]) {
    assert(
      new RegExp(`revoke all privileges on all tables in schema public from ${role};`).test(grantsSql),
      `must revoke all table privileges from ${role} (production baseline holds grant all)`,
    );
  }
  // Fail-safe ordering: nothing may be granted before the last revoke runs, or a
  // re-grant would be silently stripped again.
  const lastRevoke = grantsSql.lastIndexOf("revoke ");
  const firstGrant = grantsSql.indexOf("grant ");
  assert(lastRevoke > -1 && firstGrant > -1, "0037 must both revoke and grant");
  assert(firstGrant > lastRevoke, "every revoke must precede every grant");
});

test("0037 leaves anon with nothing but the signed-out pricing catalog read", () => {
  const anonGrants = grantsForRole("anon");
  assert(anonGrants.size === 1, `anon must hold exactly one grant, found: ${[...anonGrants.keys()].join(", ")}`);
  const plans = anonGrants.get("public.plans");
  assert(plans !== undefined, "the one anon grant must be on public.plans (/start reads it signed out)");
  assert(
    plans.size === 1 && plans.has("select"),
    `anon may only SELECT public.plans, found: ${[...(plans ?? [])].join(", ")}`,
  );
  // Ordinary DML on any table is the thing the production baseline wrongly kept.
  for (const [table, privileges] of anonGrants) {
    for (const dml of ["insert", "update", "delete"]) {
      assert(!privileges.has(dml), `anon must not hold ${dml} on ${table}`);
    }
  }
});

test("0037 grants authenticated exactly the enumerated surfaces, and nothing more", () => {
  const actual = grantsForRole("authenticated");
  const expectedTables = Object.keys(AUTHENTICATED_GRANTS).sort();
  const actualTables = [...actual.keys()].map((t) => t.replace("public.", "")).sort();
  assert(
    JSON.stringify(actualTables) === JSON.stringify(expectedTables),
    `authenticated grant set drifted.\n  expected: ${expectedTables.join(", ")}\n  actual:   ${actualTables.join(", ")}`,
  );
  for (const [table, privileges] of Object.entries(AUTHENTICATED_GRANTS)) {
    const granted = [...(actual.get(`public.${table}`) ?? [])].sort();
    assert(
      JSON.stringify(granted) === JSON.stringify([...privileges].sort()),
      `authenticated privileges on ${table} drifted: expected [${[...privileges].sort()}], got [${granted}]`,
    );
  }
  // No blanket grant may reach a browser role, whatever the table list says.
  for (const stmt of grantStatements) {
    if (stmt.target.startsWith("all ")) {
      assert(
        !stmt.roles.includes("anon") && !stmt.roles.includes("authenticated"),
        `schema-wide grant on ${stmt.target} must not include a browser role`,
      );
    }
  }
});

test("0037 keeps staff/service-role-only tables closed to both browser roles", () => {
  const anon = grantsForRole("anon");
  const authenticated = grantsForRole("authenticated");
  for (const table of SERVICE_ROLE_ONLY_TABLES) {
    assert(!anon.has(`public.${table}`), `${table} must stay closed to anon`);
    assert(!authenticated.has(`public.${table}`), `${table} must stay closed to authenticated`);
  }
  // The outbox carries recipient contact info: staff enqueue held rows through
  // the RLS insert policy, but nothing may read it back through a browser role.
  const outbox = authenticated.get("public.notification_outbox");
  assert(outbox !== undefined && outbox.size === 1 && outbox.has("insert"), "notification_outbox is insert-only for authenticated");
  assert(!anon.has("public.notification_outbox"), "notification_outbox must stay closed to anon");
});

test("0037 only names tables this repo's migrations actually create", () => {
  // A typo'd table name makes the GRANT fail at apply time (and, if the file is
  // ever split, silently skips the hardening for the real table).
  for (const stmt of grantStatements) {
    if (!stmt.target.startsWith("public.")) continue;
    const table = stmt.target.replace("public.", "");
    assert(declaredTables.has(table), `0037 grants on public.${table}, which no migration creates`);
  }
  assert(declaredTables.size > 30, "table inventory parse failed (expected the full public schema)");
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
  for (const table of CUSTOMER_FLOW_TABLES) {
    assert(
      new RegExp(`grant select, insert, update, delete on public\\.${table}\\b`).test(grants),
      `must grant customer CRUD on ${table}`,
    );
  }
  // The allowlist is for `authenticated` only — anon never receives customer DML.
  for (const stmt of grantStatements) {
    if (CUSTOMER_FLOW_TABLES.some((t) => stmt.target === `public.${t}`)) {
      assert(
        stmt.roles.length === 1 && stmt.roles[0] === "authenticated",
        `${stmt.target} customer-flow grant must go to authenticated alone, not ${stmt.roles.join(", ")}`,
      );
    }
  }
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
