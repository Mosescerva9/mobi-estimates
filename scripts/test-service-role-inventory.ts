import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { SERVICE_ROLE_INVENTORY } from "../src/lib/supabase/service-role-inventory";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const ROOT = process.cwd();
const SOURCE_ROOT = join(ROOT, "src");
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);
const serviceRoleImportPattern = /createAdminClient\s*}/;
const serviceRoleSecretPattern = /SUPABASE_SERVICE_ROLE_KEY|service_role/i;

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      walk(full, out);
      continue;
    }
    if ([...SOURCE_EXTENSIONS].some((extension) => full.endsWith(extension))) {
      out.push(relative(ROOT, full).split("\\").join("/"));
    }
  }
  return out;
}

function hasUseClientDirective(source: string): boolean {
  const firstStatement = source
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith("//"));
  return firstStatement === '"use client";' || firstStatement === "'use client';";
}

const sourceFiles = walk(SOURCE_ROOT);
const inventoryPaths = new Set(SERVICE_ROLE_INVENTORY.map((entry) => entry.path));

const actualImports = sourceFiles.filter((file) => {
  const source = readFileSync(join(ROOT, file), "utf8");
  return serviceRoleImportPattern.test(source);
});

for (const file of actualImports) {
  assert(
    inventoryPaths.has(file),
    `${file} imports createAdminClient but is missing from SERVICE_ROLE_INVENTORY`,
  );
}

for (const entry of SERVICE_ROLE_INVENTORY) {
  assert(sourceFiles.includes(entry.path), `${entry.path} is inventoried but no longer exists`);
  const source = readFileSync(join(ROOT, entry.path), "utf8");
  assert(
    serviceRoleImportPattern.test(source),
    `${entry.path} is inventoried for service-role use but no longer imports createAdminClient`,
  );
  assert(entry.allowedOperations.length > 0, `${entry.path} must list allowed service-role operations`);
  assert(entry.requires.length > 0, `${entry.path} must list required guards before service-role use`);
  assert(entry.rationale.length >= 40, `${entry.path} must include a useful service-role rationale`);
}

for (const file of sourceFiles) {
  const source = readFileSync(join(ROOT, file), "utf8");
  if (!hasUseClientDirective(source)) continue;
  assert(
    !serviceRoleImportPattern.test(source) && !serviceRoleSecretPattern.test(source),
    `${file} is a client component and must not reference service-role Supabase APIs or secrets`,
  );
}

assert(
  readFileSync(join(ROOT, "src/lib/supabase/admin.ts"), "utf8").includes("SERVER-ONLY"),
  "admin.ts must retain explicit SERVER-ONLY warning",
);

console.log(
  `PASS service-role inventory: ${actualImports.length} createAdminClient import sites are inventoried and no client component references service-role secrets`,
);
