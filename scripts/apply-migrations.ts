import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/**
 * Apply re-runnable migrations to a live Supabase project.
 *
 * `supabase db push` remains the canonical path. This exists for the case it
 * doesn't cover: applying a migration from an environment that has no Supabase
 * CLI and no direct database port — a restricted network, or CI. It talks to the
 * project over HTTPS instead.
 *
 * Two transports, whichever the environment can reach:
 *
 *   SUPABASE_DB_URL      — a postgres:// connection string, executed with psql.
 *   SUPABASE_ACCESS_TOKEN — a personal access token (sbp_…), executed through
 *                          the Management API query endpoint. This is the one
 *                          that works when port 5432 is blocked.
 *
 * It refuses any migration not marked `Idempotent: safe to re-run.` Without a
 * migration ledger there is nothing to stop a file being applied twice, so the
 * tool is limited to files that say re-running them is harmless — which is what
 * makes it safe to point at production without knowing what has already run.
 */

const MIGRATIONS_DIR = path.join(process.cwd(), "supabase", "migrations");
const IDEMPOTENT_MARKER = "Idempotent: safe to re-run.";

interface Migration {
  version: string;
  file: string;
  sql: string;
}

function loadMigrations(versions: string[]): Migration[] {
  const files = fs.readdirSync(MIGRATIONS_DIR).filter((f) => f.endsWith(".sql")).sort();
  const selected: Migration[] = [];

  for (const version of versions) {
    const file = files.find((f) => f.startsWith(`${version}_`) || f === version);
    if (!file) {
      throw new Error(`No migration matching "${version}" in supabase/migrations.`);
    }
    const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, file), "utf8");
    if (!sql.includes(IDEMPOTENT_MARKER)) {
      throw new Error(
        `${file} is not marked "${IDEMPOTENT_MARKER}", so this tool will not apply it. ` +
          `Use \`supabase db push\`, which tracks what has already run.`,
      );
    }
    selected.push({ version: file.split("_")[0], file, sql });
  }

  return selected;
}

async function applyViaManagementApi(migration: Migration, token: string, ref: string): Promise<void> {
  const res = await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    // One statement string per migration, wrapped so a failure part-way through
    // leaves no half-applied schema.
    body: JSON.stringify({ query: `begin;\n${migration.sql}\ncommit;` }),
  });
  if (!res.ok) {
    throw new Error(`${migration.file} failed (${res.status}): ${(await res.text()).slice(0, 600)}`);
  }
}

function applyViaPsql(migration: Migration, dbUrl: string): void {
  execFileSync(
    "psql",
    ["--no-psqlrc", "--quiet", "--single-transaction", "-v", "ON_ERROR_STOP=1", "-f", path.join(MIGRATIONS_DIR, migration.file), dbUrl],
    { stdio: ["ignore", "inherit", "inherit"] },
  );
}

/** Project ref is the first label of the Supabase project URL. */
function projectRef(): string {
  const explicit = process.env.SUPABASE_PROJECT_REF?.trim();
  if (explicit) return explicit;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const host = url ? new URL(url).hostname : "";
  const ref = host.split(".")[0];
  if (!ref) {
    throw new Error("Set SUPABASE_PROJECT_REF or NEXT_PUBLIC_SUPABASE_URL so the project is known.");
  }
  return ref;
}

async function main(): Promise<void> {
  const args = process.argv.slice(2).filter((a) => a !== "--");
  const dryRun = args.includes("--dry-run");
  const versions = args.filter((a) => !a.startsWith("--"));

  if (versions.length === 0) {
    console.error("Usage: npm run db:apply-migrations -- 0036 0037 [--dry-run]");
    process.exit(2);
  }

  const migrations = loadMigrations(versions);
  const dbUrl = process.env.SUPABASE_DB_URL?.trim();
  const token = process.env.SUPABASE_ACCESS_TOKEN?.trim();

  if (dryRun) {
    for (const m of migrations) {
      console.log(`would apply ${m.file} (${m.sql.split("\n").length} lines)`);
    }
    return;
  }

  if (!dbUrl && !token) {
    console.error(
      [
        "No way to reach the database. Set one of:",
        "",
        "  SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres",
        "    Supabase → Project Settings → Database → Connection string.",
        "    Use the POOLER string, not db.<ref>.supabase.co — the direct host resolves",
        "    to IPv6 only, which fails outright on an IPv4-only network.",
        "",
        "  SUPABASE_ACCESS_TOKEN=sbp_...",
        "    https://supabase.com/dashboard/account/tokens — HTTPS only, so this is the",
        "    one that works when outbound 5432 is blocked.",
        "",
        "Or paste the migration files into the Supabase SQL editor by hand.",
      ].join("\n"),
    );
    process.exit(2);
  }

  const target = dbUrl ? "direct connection" : `Management API (project ${projectRef()})`;
  console.log(`Applying ${migrations.length} migration(s) via ${target}.`);

  for (const migration of migrations) {
    process.stdout.write(`  ${migration.file} … `);
    if (dbUrl) {
      applyViaPsql(migration, dbUrl);
    } else {
      await applyViaManagementApi(migration, token!, projectRef());
    }
    console.log("ok");
  }

  console.log("");
  console.log("Done. Verify with: npm run check:intake-readiness");
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
