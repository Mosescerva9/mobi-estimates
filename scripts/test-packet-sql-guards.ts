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
 * ---------------------------------------------------------------------------
 * 0037 statement-level parser.
 *
 * The previous version of these guards scanned 0037 with a permissive regex and
 * asserted on whatever it happened to match. That fails OPEN: a statement the
 * regex did not understand -- `grant select on public.plans to anon, PUBLIC;`,
 * `to "anon"`, `to group anon`, `grant anon to authenticated;` -- was simply not
 * seen, so no assertion fired and the widening shipped. Everything below instead
 * tokenizes the file into statements and requires EVERY executable statement to
 * parse under an explicit grammar. An unrecognised statement is a failure, not a
 * skipped one.
 * ---------------------------------------------------------------------------
 */

/** Table privileges Postgres accepts (MAINTAIN is PG17+). */
const TABLE_PRIVILEGES = new Set([
  "select",
  "insert",
  "update",
  "delete",
  "truncate",
  "references",
  "trigger",
  "maintain",
]);
const SEQUENCE_PRIVILEGES = new Set(["usage", "select", "update"]);
/** The only grantees this migration may ever name. Notably excludes PUBLIC. */
const API_ROLES = new Set(["anon", "authenticated", "service_role"]);

/**
 * Split SQL into statements, dropping comments and respecting string and
 * dollar-quoted literals so a `;` or `--` inside one cannot end a statement
 * early (and so a payload hidden in a literal cannot escape the grammar).
 */
function splitStatements(sql: string): string[] {
  const statements: string[] = [];
  let current = "";
  let i = 0;
  while (i < sql.length) {
    const rest = sql.slice(i);
    if (rest.startsWith("--")) {
      const newline = sql.indexOf("\n", i);
      i = newline === -1 ? sql.length : newline;
      current += " ";
      continue;
    }
    if (rest.startsWith("/*")) {
      const end = sql.indexOf("*/", i + 2);
      assert(end > -1, "0037 has an unterminated block comment");
      i = end + 2;
      current += " ";
      continue;
    }
    const dollarTag = /^\$[a-z0-9_]*\$/.exec(rest);
    if (dollarTag) {
      const tag = dollarTag[0];
      const end = sql.indexOf(tag, i + tag.length);
      assert(end > -1, `0037 has an unterminated dollar-quoted literal (${tag})`);
      current += sql.slice(i, end + tag.length);
      i = end + tag.length;
      continue;
    }
    if (sql[i] === "'") {
      const end = sql.indexOf("'", i + 1);
      assert(end > -1, "0037 has an unterminated string literal");
      current += sql.slice(i, end + 1);
      i = end + 1;
      continue;
    }
    if (sql[i] === ";") {
      statements.push(current);
      current = "";
      i += 1;
      continue;
    }
    current += sql[i];
    i += 1;
  }
  assert(current.trim() === "", `0037 has a trailing unterminated statement: ${current.trim().slice(0, 60)}`);
  return statements.map(normalizeStatement).filter((s) => s.length > 0);
}

/**
 * Canonical form: single-spaced, `, `-separated. This is what defeats formatting
 * tricks -- `to anon,public`, `to  anon ,  public`, and a role list split across
 * lines all normalize to the same text and hit the same grammar.
 */
function normalizeStatement(statement: string): string {
  return statement.replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ").trim().toLowerCase();
}

type PrivilegeStatement = { kind: "grant" | "revoke"; privileges: string[]; target: string; roles: string[] };
type DefaultAclStatement = { kind: "default-acl"; owner: string; privileges: string[]; objectType: string; roles: string[] };
type ParsedStatement = PrivilegeStatement | DefaultAclStatement;

const GRANT_RE =
  /^grant ([a-z]+(?:, [a-z]+)*) on (public\.[a-z_][a-z0-9_]*|all tables in schema public|all sequences in schema public) to ([a-z_][a-z0-9_]*(?:, [a-z_][a-z0-9_]*)*)$/;
const REVOKE_RE =
  /^revoke (all privileges|all|[a-z]+(?:, [a-z]+)*) on (public\.[a-z_][a-z0-9_]*|all tables in schema public|all sequences in schema public) from ([a-z_][a-z0-9_]*(?:, [a-z_][a-z0-9_]*)*)$/;
const DEFAULT_ACL_RE =
  /^alter default privileges for role ([a-z_][a-z0-9_]*) in schema public (revoke|grant) (all|[a-z]+(?:, [a-z]+)*) on (tables|sequences) (?:from|to) ([a-z_][a-z0-9_]*(?:, [a-z_][a-z0-9_]*)*)$/;
/**
 * The one permitted DO block: MAINTAIN only exists on PG17+, so revoking it from
 * the default ACL has to be version-gated or the file stops parsing on PG15/16.
 * The shape is pinned end to end -- version predicate, a single EXECUTE, and
 * nothing else -- so the block cannot become a hiding place for other DDL.
 */
const CONDITIONAL_DEFAULT_ACL_RE =
  /^do \$\$ begin if current_setting\('server_version_num'\)::int >= 170000 then execute '([^']*)'; end if; end \$\$$/;

function parseRoleList(raw: string, statement: string): string[] {
  const roles = raw.split(", ").map((r) => r.trim());
  for (const role of roles) {
    assert(
      role !== "public",
      `0037 grants to PUBLIC, which reaches anon and every future role: ${statement}`,
    );
    assert(
      API_ROLES.has(role),
      `0037 names a grantee outside {${[...API_ROLES].join(", ")}}: "${role}" in: ${statement}`,
    );
  }
  assert(new Set(roles).size === roles.length, `0037 repeats a grantee: ${statement}`);
  return roles;
}

function parsePrivilegeList(raw: string, target: string, statement: string): string[] {
  const privileges = raw.split(", ").map((p) => p.trim());
  assert(new Set(privileges).size === privileges.length, `0037 repeats a privilege: ${statement}`);
  const allowed = target.includes("sequences") ? SEQUENCE_PRIVILEGES : TABLE_PRIVILEGES;
  for (const privilege of privileges) {
    assert(
      allowed.has(privilege),
      `0037 names an unknown/blanket privilege "${privilege}" on ${target}: ${statement}`,
    );
  }
  return privileges;
}

/**
 * Parse one statement or fail. Anything that is not a GRANT/REVOKE/ALTER DEFAULT
 * PRIVILEGES in the exact expected shape is rejected -- including role-membership
 * grants (`grant anon to authenticated`), `with grant option`, quoted or GROUP
 * role forms, and any other DDL someone drops into this file.
 */
function parseStatement(statement: string): ParsedStatement {
  const grant = GRANT_RE.exec(statement);
  if (grant) {
    return {
      kind: "grant",
      privileges: parsePrivilegeList(grant[1], grant[2], statement),
      target: grant[2],
      roles: parseRoleList(grant[3], statement),
    };
  }
  const revoke = REVOKE_RE.exec(statement);
  if (revoke) {
    return {
      kind: "revoke",
      privileges:
        revoke[1] === "all privileges" || revoke[1] === "all"
          ? ["all privileges"]
          : parsePrivilegeList(revoke[1], revoke[2], statement),
      target: revoke[2],
      roles: parseRoleList(revoke[3], statement),
    };
  }
  const defaultAcl = DEFAULT_ACL_RE.exec(statement);
  if (defaultAcl) {
    assert(
      defaultAcl[2] === "revoke",
      `0037 may only narrow default privileges, never grant them: ${statement}`,
    );
    // `for role supabase_admin` is not merely undesirable: postgres is not a
    // member of supabase_admin, so the statement would fail and abort the
    // migration. See the limitation note in 0037.
    assert(
      defaultAcl[1] === "postgres",
      `0037 may only alter default privileges FOR ROLE postgres, not ${defaultAcl[1]}: ${statement}`,
    );
    return {
      kind: "default-acl",
      owner: defaultAcl[1],
      privileges: defaultAcl[3] === "all" ? ["all"] : defaultAcl[3].split(", "),
      objectType: defaultAcl[4],
      roles: parseRoleList(defaultAcl[5], statement),
    };
  }
  const conditional = CONDITIONAL_DEFAULT_ACL_RE.exec(statement);
  if (conditional) {
    const inner = parseStatement(normalizeStatement(conditional[1]));
    assert(
      inner.kind === "default-acl",
      `the version-gated block may only carry an ALTER DEFAULT PRIVILEGES statement: ${statement}`,
    );
    return inner;
  }
  throw new Error(`0037 contains a statement these guards do not parse (fail closed): ${statement}`);
}

/** Stable identity for a privilege statement, order-insensitive within a list. */
function statementKey(stmt: PrivilegeStatement): string {
  return `${stmt.kind} [${[...stmt.privileges].sort().join(",")}] on ${stmt.target} -> ${[...stmt.roles].sort().join(",")}`;
}

function defaultAclKey(stmt: DefaultAclStatement): string {
  return `[${[...stmt.privileges].sort().join(",")}] on ${stmt.objectType} -> ${[...stmt.roles].sort().join(",")}`;
}

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

/** Every GRANT 0037 may contain, exactly. Each one names a single grantee. */
const EXPECTED_GRANT_KEYS = [
  "grant [select] on public.plans -> anon",
  ...Object.entries(AUTHENTICATED_GRANTS).map(
    ([table, privileges]) => `grant [${[...privileges].sort().join(",")}] on public.${table} -> authenticated`,
  ),
  "grant [delete,insert,select,update] on all tables in schema public -> service_role",
  "grant [select,update,usage] on all sequences in schema public -> service_role",
].sort();

/** Every REVOKE 0037 may contain, exactly. */
const EXPECTED_REVOKE_KEYS = [
  "revoke [all privileges] on all tables in schema public -> anon",
  "revoke [all privileges] on all tables in schema public -> authenticated",
  ...["anon", "authenticated", "service_role"].map(
    (role) => `revoke [references,trigger,truncate] on all tables in schema public -> ${role}`,
  ),
].sort();

/**
 * Every default-privileges change 0037 may contain, exactly. Production's
 * pg_default_acl grants future postgres-owned tables ALL privileges and future
 * sequences usage/select/update to anon, authenticated and service_role, so
 * without these four the next `create table` re-opens the schema to browsers.
 * Removing or weakening any one of them is a widening; the equality check below
 * catches both directions.
 */
const EXPECTED_DEFAULT_ACL_KEYS = [
  "[all] on tables -> anon,authenticated",
  "[all] on sequences -> anon,authenticated",
  "[references,trigger,truncate] on tables -> service_role",
  "[maintain] on tables -> service_role",
  "[update] on sequences -> service_role",
].sort();

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

type GrantAudit = {
  grants: PrivilegeStatement[];
  revokes: PrivilegeStatement[];
  defaultAcls: DefaultAclStatement[];
};

/**
 * Parse 0037 and enforce every invariant. Throws on the first violation. The
 * real migration must pass this; the mutation tests below feed it deliberately
 * widened variants and require it to throw.
 */
function auditGrantsMigration(sql: string): GrantAudit {
  const parsed = splitStatements(sql).map(parseStatement);
  const grantStatements = parsed.filter((s): s is PrivilegeStatement => s.kind === "grant");
  const revokeStatements = parsed.filter((s): s is PrivilegeStatement => s.kind === "revoke");
  const defaultAcls = parsed.filter((s): s is DefaultAclStatement => s.kind === "default-acl");

  // 1) Exact grant set. Equality in both directions: a new grant fails, and so
  //    does silently dropping one a customer/staff flow depends on.
  const actualGrantKeys = grantStatements.map(statementKey).sort();
  assert(
    JSON.stringify(actualGrantKeys) === JSON.stringify(EXPECTED_GRANT_KEYS),
    `0037 grant set drifted.\n  unexpected: ${actualGrantKeys.filter((k) => !EXPECTED_GRANT_KEYS.includes(k)).join(" | ") || "none"}\n  missing:    ${EXPECTED_GRANT_KEYS.filter((k) => !actualGrantKeys.includes(k)).join(" | ") || "none"}`,
  );

  // 2) Every grant names exactly one grantee. `to anon, PUBLIC` and
  //    `to anon, authenticated` are rejected here even before the set equality.
  for (const stmt of grantStatements) {
    assert(
      stmt.roles.length === 1,
      `0037 grants must name exactly one grantee, found ${stmt.roles.join(", ")} on ${stmt.target}`,
    );
  }

  // 3) Exact revoke set, and the fail-safe ordering that makes the outcome the
  //    same from a clean local stack and from the production `grant all`
  //    baseline. Default-privileges statements only affect future objects, so
  //    they are exempt from the ordering rule.
  const actualRevokeKeys = revokeStatements.map(statementKey).sort();
  assert(
    JSON.stringify(actualRevokeKeys) === JSON.stringify(EXPECTED_REVOKE_KEYS),
    `0037 revoke set drifted.\n  unexpected: ${actualRevokeKeys.filter((k) => !EXPECTED_REVOKE_KEYS.includes(k)).join(" | ") || "none"}\n  missing:    ${EXPECTED_REVOKE_KEYS.filter((k) => !actualRevokeKeys.includes(k)).join(" | ") || "none"}`,
  );
  const lastRevoke = parsed.map((s) => s.kind).lastIndexOf("revoke");
  const firstGrant = parsed.map((s) => s.kind).indexOf("grant");
  assert(lastRevoke > -1 && firstGrant > -1, "0037 must both revoke and grant");
  assert(firstGrant > lastRevoke, "every revoke must precede every grant, or a re-grant is stripped again");

  // 4) Exact default-privileges set (blocker: future objects inherit Supabase's
  //    broad defaults otherwise).
  const actualDefaultAclKeys = defaultAcls.map(defaultAclKey).sort();
  assert(
    JSON.stringify(actualDefaultAclKeys) === JSON.stringify(EXPECTED_DEFAULT_ACL_KEYS),
    `0037 default-privileges set drifted.\n  unexpected: ${actualDefaultAclKeys.filter((k) => !EXPECTED_DEFAULT_ACL_KEYS.includes(k)).join(" | ") || "none"}\n  missing:    ${EXPECTED_DEFAULT_ACL_KEYS.filter((k) => !actualDefaultAclKeys.includes(k)).join(" | ") || "none"}`,
  );

  // 5) Named tables must exist, or the GRANT fails at apply time.
  for (const stmt of [...grantStatements, ...revokeStatements]) {
    if (!stmt.target.startsWith("public.")) continue;
    const table = stmt.target.replace("public.", "");
    assert(declaredTables.has(table), `0037 names public.${table}, which no migration creates`);
  }
  assert(declaredTables.size > 30, "table inventory parse failed (expected the full public schema)");

  return { grants: grantStatements, revokes: revokeStatements, defaultAcls };
}

let auditResult: GrantAudit | null = null;
/** Memoized audit of the real 0037, so a parse failure fails tests, not the run. */
function migrationAudit(): GrantAudit {
  auditResult ??= auditGrantsMigration(grants);
  return auditResult;
}

/** Every table 0037 grants `role` something, mapped to the granted privileges. */
function grantsForRole(role: string): Map<string, Set<string>> {
  const byTable = new Map<string, Set<string>>();
  for (const stmt of migrationAudit().grants) {
    if (!stmt.roles.includes(role)) continue;
    const existing = byTable.get(stmt.target) ?? new Set<string>();
    for (const privilege of stmt.privileges) existing.add(privilege);
    byTable.set(stmt.target, existing);
  }
  return byTable;
}

test("0037 parses end to end: every executable statement matches the expected grammar", () => {
  // Pin the statement inventory too, so a whole section cannot be deleted while
  // the per-statement checks still pass.
  const result = migrationAudit();
  assert(result.grants.length === 23, `expected 23 grants, found ${result.grants.length}`);
  assert(result.revokes.length === 5, `expected 5 revokes, found ${result.revokes.length}`);
  assert(result.defaultAcls.length === 5, `expected 5 default-privilege revokes, found ${result.defaultAcls.length}`);
});

test("0037 revokes every table privilege from anon/authenticated before granting", () => {
  // The production baseline has Supabase's default `grant all` on all 35 public
  // tables for anon AND authenticated. A migration that only adds grants leaves
  // that baseline fully intact, so the schema-wide revoke is what makes the
  // outcome identical from a clean local stack and from production.
  for (const role of ["anon", "authenticated"]) {
    assert(
      migrationAudit().revokes.some(
        (s) =>
          s.roles.includes(role) &&
          s.target === "all tables in schema public" &&
          s.privileges.includes("all privileges"),
      ),
      `must revoke all table privileges from ${role} (production baseline holds grant all)`,
    );
  }
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
  for (const stmt of migrationAudit().grants) {
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

test("0037 never uses grant all and strips TRUNCATE/TRIGGER/REFERENCES from every API role", () => {
  for (const stmt of migrationAudit().grants) {
    for (const privilege of ["truncate", "trigger", "references", "maintain"]) {
      assert(!stmt.privileges.includes(privilege), `must not grant ${privilege} (on ${stmt.target})`);
    }
  }
  for (const role of ["anon", "authenticated", "service_role"]) {
    assert(
      migrationAudit().revokes.some(
        (s) =>
          s.roles.includes(role) &&
          s.target === "all tables in schema public" &&
          ["truncate", "references", "trigger"].every((p) => s.privileges.includes(p)),
      ),
      `must strip truncate/references/trigger from ${role}`,
    );
  }
});

test("0037 grants customer-flow CRUD to authenticated for the named tables", () => {
  const authenticated = grantsForRole("authenticated");
  for (const table of CUSTOMER_FLOW_TABLES) {
    const granted = [...(authenticated.get(`public.${table}`) ?? [])].sort();
    assert(
      JSON.stringify(granted) === JSON.stringify(["delete", "insert", "select", "update"]),
      `must grant customer CRUD on ${table}, found [${granted}]`,
    );
  }
  // The allowlist is for `authenticated` only — anon never receives customer DML.
  for (const stmt of migrationAudit().grants) {
    if (CUSTOMER_FLOW_TABLES.some((t) => stmt.target === `public.${t}`)) {
      assert(
        stmt.roles.length === 1 && stmt.roles[0] === "authenticated",
        `${stmt.target} customer-flow grant must go to authenticated alone, not ${stmt.roles.join(", ")}`,
      );
    }
  }
});

test("0037 restores ordinary DML and sequence access to service_role without destructive grants", () => {
  const serviceRole = grantsForRole("service_role");
  const tables = [...(serviceRole.get("all tables in schema public") ?? [])].sort();
  assert(
    JSON.stringify(tables) === JSON.stringify(["delete", "insert", "select", "update"]),
    `service_role must receive ordinary table DML only, found [${tables}]`,
  );
  const sequences = [...(serviceRole.get("all sequences in schema public") ?? [])].sort();
  assert(
    JSON.stringify(sequences) === JSON.stringify(["select", "update", "usage"]),
    `service_role must receive sequence access needed by inserts, found [${sequences}]`,
  );
});

test("0037 closes the FUTURE-object hole: default privileges grant browsers nothing", () => {
  // Production's pg_default_acl (verified read-only on the live catalog) gives
  // every future postgres-owned table ALL privileges and every future sequence
  // usage/select/update to anon, authenticated and service_role. Existing-object
  // revokes cannot reach objects that do not exist yet.
  for (const objectType of ["tables", "sequences"]) {
    for (const role of ["anon", "authenticated"]) {
      assert(
        migrationAudit().defaultAcls.some(
          (s) => s.objectType === objectType && s.roles.includes(role) && s.privileges.includes("all"),
        ),
        `future ${objectType} must grant nothing to ${role} by default`,
      );
    }
  }
  // service_role keeps ordinary DML on future tables and usage/select on future
  // sequences; the destructive/definition privileges are stripped, MAINTAIN
  // included (it is in PG17's default ACL and production runs PG17).
  const serviceTableRevokes = migrationAudit().defaultAcls
    .filter((s) => s.objectType === "tables" && s.roles.includes("service_role"))
    .flatMap((s) => s.privileges)
    .sort();
  assert(
    JSON.stringify(serviceTableRevokes) === JSON.stringify(["maintain", "references", "trigger", "truncate"]),
    `future-table service_role revokes drifted: [${serviceTableRevokes}]`,
  );
  const serviceSequenceRevokes = migrationAudit().defaultAcls
    .filter((s) => s.objectType === "sequences" && s.roles.includes("service_role"))
    .flatMap((s) => s.privileges);
  assert(
    JSON.stringify(serviceSequenceRevokes) === JSON.stringify(["update"]),
    `future-sequence service_role revokes drifted: [${serviceSequenceRevokes}]`,
  );
  // Only postgres' own defaults may be altered: postgres is not a member of
  // supabase_admin, so touching that role's defaults would abort the migration.
  for (const stmt of migrationAudit().defaultAcls) {
    assert(stmt.owner === "postgres", `default privileges may only be altered FOR ROLE postgres, not ${stmt.owner}`);
  }
  assert(
    !/alter default privileges[^;]*for role supabase_admin/.test(grants),
    "0037 must not attempt to alter supabase_admin's defaults (it would fail: postgres is not a member)",
  );
  // The limitation has to stay documented in the file, or the next reader will
  // read the remaining broad supabase_admin default ACL as an oversight.
  assert(grants.includes("supabase_admin"), "0037 must document the supabase_admin default-ACL limitation");
  assert(
    grants.includes("pg_default_acl"),
    "0037 must document the post-apply pg_default_acl verification (no runtime Postgres is available here)",
  );
});

/**
 * Mutation coverage. Each case is a widening (or a silent removal) that a real
 * edit could plausibly introduce; the audit must reject every one of them. The
 * first two are the exact bypasses that blocked this change in review.
 */
const MUTATIONS: { name: string; mutate: (sql: string) => string }[] = [
  {
    name: "an extra PUBLIC grantee on the anon grant",
    mutate: (sql) => sql.replace("grant select on public.plans to anon;", "grant select on public.plans to anon, PUBLIC;"),
  },
  {
    name: "an extra role appended to a single-role grant",
    mutate: (sql) =>
      sql.replace("grant select on public.plans to anon;", "grant select on public.plans to anon, authenticated;"),
  },
  {
    name: "a quoted grantee the loose parser skipped",
    mutate: (sql) => sql.replace("grant select on public.plans to anon;", 'grant select on public.plans to "anon";'),
  },
  {
    name: "a GROUP grantee",
    mutate: (sql) => sql.replace("grant select on public.plans to anon;", "grant select on public.plans to group anon;"),
  },
  {
    name: "WITH GRANT OPTION",
    mutate: (sql) =>
      sql.replace("grant select on public.plans to anon;", "grant select on public.plans to anon with grant option;"),
  },
  {
    name: "a role-membership grant (valid SQL, no ON clause)",
    mutate: (sql) => `${sql}\ngrant service_role to authenticated;\n`,
  },
  {
    name: "whitespace/comma tricks around an extra grantee",
    mutate: (sql) =>
      sql.replace("grant select on public.plans to anon;", "grant\n  select\n  on public.plans\n  to anon ,authenticated;"),
  },
  {
    name: "a new grant on a service-role-only table",
    mutate: (sql) => `${sql}\ngrant select on public.audit_logs to authenticated;\n`,
  },
  {
    name: "a blanket grant to a browser role",
    mutate: (sql) => `${sql}\ngrant select on all tables in schema public to authenticated;\n`,
  },
  {
    name: "grant all privileges (unparsed blanket form)",
    mutate: (sql) => sql.replace("grant select on public.plans to anon;", "grant all privileges on public.plans to anon;"),
  },
  {
    name: "an unrelated DDL statement smuggled into the file",
    mutate: (sql) => `${sql}\nalter table public.plans disable row level security;\n`,
  },
  {
    name: "removing the future-table default-ACL revoke",
    mutate: (sql) =>
      sql.replace(
        "alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;",
        "",
      ),
  },
  {
    name: "removing the future-sequence default-ACL revoke",
    mutate: (sql) =>
      sql.replace(
        "alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;",
        "",
      ),
  },
  {
    name: "narrowing the future-table revoke to one browser role",
    mutate: (sql) =>
      sql.replace(
        "revoke all on tables from anon, authenticated;",
        "revoke all on tables from anon;",
      ),
  },
  {
    name: "weakening the future-table revoke to SELECT only",
    mutate: (sql) =>
      sql.replace(
        "revoke all on tables from anon, authenticated;",
        "revoke select on tables from anon, authenticated;",
      ),
  },
  {
    name: "dropping MAINTAIN from the future-table service_role revoke",
    mutate: (sql) =>
      sql.replace("revoke maintain on tables from service_role", "revoke truncate on tables from service_role"),
  },
  {
    name: "granting default privileges instead of revoking them",
    mutate: (sql) =>
      sql.replace(
        "alter default privileges for role postgres in schema public revoke update on sequences from service_role;",
        "alter default privileges for role postgres in schema public grant update on sequences to authenticated;",
      ),
  },
  {
    name: "altering supabase_admin's defaults (would abort the migration)",
    mutate: (sql) =>
      `${sql}\nalter default privileges for role supabase_admin in schema public revoke all on tables from anon;\n`,
  },
  {
    name: "smuggling DDL into the version-gated block",
    mutate: (sql) =>
      sql.replace(
        "execute 'alter default privileges for role postgres in schema public revoke maintain on tables from service_role'",
        "execute 'grant select on public.audit_logs to anon'",
      ),
  },
  {
    name: "dropping the schema-wide revoke of anon's table privileges",
    mutate: (sql) => sql.replace("revoke all privileges on all tables in schema public from anon;", ""),
  },
  {
    name: "moving a grant ahead of the fail-safe revokes",
    mutate: (sql) =>
      `grant select on public.plans to authenticated;\n${sql.replace(
        /grant select on public\.plans\s+to authenticated;/,
        "",
      )}`,
  },
];

for (const mutation of MUTATIONS) {
  test(`0037 guards reject: ${mutation.name}`, () => {
    const mutated = mutation.mutate(grants);
    assert(mutated !== grants, `mutation "${mutation.name}" did not change the migration (stale anchor text)`);
    let threw = false;
    try {
      auditGrantsMigration(mutated);
    } catch {
      threw = true;
    }
    assert(threw, `the guards accepted a widened 0037: ${mutation.name}`);
  });
}

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
