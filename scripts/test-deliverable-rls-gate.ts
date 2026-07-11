import { readFileSync } from "node:fs";
import { join } from "node:path";
import assert from "node:assert/strict";
import { test } from "node:test";

const migrationPath = join(
  process.cwd(),
  "supabase/migrations/0021_restrict_deliverables_write_to_admin.sql",
);
const migration = readFileSync(migrationPath, "utf8");

function policyBody(policyName: string): string {
  const escaped = policyName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = migration.match(new RegExp(`create policy ${escaped}[\\s\\S]*?;`, "i"));
  assert(match, `missing policy ${policyName}`);
  return match[0].toLowerCase();
}

test("deliverables table writes are locked until final-delivery approval workflow exists", () => {
  const insertPolicy = policyBody("deliverables_insert_locked");
  assert(insertPolicy.includes("for insert"), "insert policy must cover metadata inserts");
  assert(insertPolicy.includes("with check (false)"), "metadata inserts must be fail-closed");
  assert(!insertPolicy.includes("public.is_admin()"), "metadata inserts must not allow admin bypass");
  assert(!insertPolicy.includes("public.is_staff()"), "metadata inserts must not allow estimator/reviewer staff");

  const updatePolicy = policyBody("deliverables_update_locked");
  assert(updatePolicy.includes("for update"), "update policy must cover metadata mutations");
  assert(updatePolicy.includes("using (false)"), "metadata updates must be fail-closed");
  assert(updatePolicy.includes("with check (false)"), "metadata updates must be fail-closed");
  assert(!updatePolicy.includes("public.is_admin()"), "metadata updates must not allow admin bypass");
  assert(!updatePolicy.includes("public.is_staff()"), "metadata updates must not allow estimator/reviewer staff");
});

test("deliverables storage object writes are locked until final-delivery approval workflow exists", () => {
  for (const policyName of ["\"deliverables_insert\"", "\"deliverables_update\"", "\"deliverables_delete\""]) {
    const body = policyBody(policyName);
    assert(body.includes("bucket_id = 'deliverables'"), `${policyName} must target the deliverables bucket`);
    assert(body.includes("false"), `${policyName} must be fail-closed`);
    assert(!body.includes("public.is_admin()"), `${policyName} must not allow admin bypass`);
    assert(!body.includes("public.is_staff()"), `${policyName} must not allow estimator/reviewer staff`);
  }
});

test("migration removes the older broad staff-write policies", () => {
  assert(migration.includes("drop policy if exists deliverables_update_client"));
  assert(migration.includes("drop policy if exists deliverables_write_staff"));
  assert(migration.includes("drop policy if exists deliverables_update_admin"));
  assert(migration.includes("drop policy if exists deliverables_insert_admin"));
  assert(migration.includes('drop policy if exists "deliverables_insert"'));
  assert(migration.includes('drop policy if exists "deliverables_update"'));
  assert(migration.includes('drop policy if exists "deliverables_delete"'));
});
